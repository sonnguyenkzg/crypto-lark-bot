#!/usr/bin/env python3
"""
Real Webhook-Based Lark Bot - Based on Production Architecture
FIXED: Proper message deduplication that allows repeated commands
ADDED: Comprehensive debug logging for troubleshooting
"""
import asyncio
import json
import logging
import time
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.message_parser import LarkMessageParser
from bot.services.topic_manager import LarkTopicManager, TopicType
from bot.utils.handler_registry import HandlerRegistry, CommandContext
from bot.handlers.help_handler import HelpHandler
from bot.handlers.start_handler import StartHandler
from bot.handlers.list_handler import ListHandler
from bot.handlers.add_handler import AddHandler
from bot.handlers.remove_handler import RemoveHandler
from bot.handlers.check_handler import CheckHandler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Message deduplication cache - FIXED: Only use unique message identifiers
_PROCESSED_MESSAGES = {}
_MESSAGE_CACHE_TTL = 300  # 5 minutes TTL

def cleanup_message_cache():
    """Clean old messages from cache"""
    current_time = time.time()
    expired_keys = [
        msg_id for msg_id, timestamp in _PROCESSED_MESSAGES.items()
        if current_time - timestamp > _MESSAGE_CACHE_TTL
    ]
    for key in expired_keys:
        del _PROCESSED_MESSAGES[key]

def is_duplicate_message(event_id: str, message_id: str) -> bool:
    """
    Check if this message was already processed
    FIXED: Only use unique identifiers (event_id and message_id), NOT content hash
    This allows repeated commands like /check to work properly
    """
    cleanup_message_cache()  # Clean old entries
    
    # Create unique keys based on message identifiers only
    event_key = f"event:{event_id}"
    message_key = f"msg:{message_id}"
    
    # Check if we've already processed this exact message
    if event_key in _PROCESSED_MESSAGES or message_key in _PROCESSED_MESSAGES:
        return True
    
    # Mark this message as processed
    current_time = time.time()
    _PROCESSED_MESSAGES[event_key] = current_time
    _PROCESSED_MESSAGES[message_key] = current_time
    
    return False

# Global instances
api_client = None
topic_manager = None
message_parser = LarkMessageParser()
handler_registry = HandlerRegistry(Config)

app = FastAPI(title="Lark Crypto Bot", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup."""
    global api_client, topic_manager
    
    try:
        # Initialize components
        Config.validate_config()
        
        api_client = LarkAPIClient(Config.LARK_APP_ID, Config.LARK_APP_SECRET)
        topic_manager = LarkTopicManager(api_client, Config)
        
        # Register handlers
        help_handler = HelpHandler()
        start_handler = StartHandler()
        list_handler = ListHandler()
        add_handler = AddHandler()
        remove_handler = RemoveHandler()
        check_handler = CheckHandler()

        handler_registry.register(check_handler)
        handler_registry.register(remove_handler)
        handler_registry.register(add_handler)
        handler_registry.register(list_handler)
        handler_registry.register(help_handler)
        handler_registry.register(start_handler)
        
        # Add middleware
        from bot.utils.handler_registry import authorization_middleware
        handler_registry.add_middleware(authorization_middleware)
        
        logger.info("✅ Lark Bot initialized successfully")
        
        # Send startup message as rich card
        async with api_client:
            startup_card = {
                "config": {
                    "wide_screen_mode": True,
                    "enable_forward": True
                },
                "header": {
                    "template": "green",
                    "title": {
                        "tag": "plain_text",
                        "content": "🎯 Real Webhook Bot Started!"
                    },
                    "subtitle": {
                        "tag": "plain_text",
                        "content": f"Started at: {Config.get_current_time() if hasattr(Config, 'get_current_time') else 'Now'}"
                    }
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "🎉 **I can now hear your actual commands!**"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "💡 **Try typing /help in #commands topic**"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "⚡ **Instant responses!**"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "**Available Commands:**"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "• **/help** - Show all commands\n• **/check** - Check wallet balances\n• **/list** - List all wallets\n• **/add** - Add new wallet\n• **/remove** - Remove wallet"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "🔗 **Webhook endpoint:** /webhook\n✅ **Ready for real-time interaction!**"
                        }
                    }
                ]
            }
            
            await topic_manager.send_command_response(startup_card, msg_type="interactive")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")

@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "Bot is running", "webhook": "/webhook"}

@app.post("/webhook")
async def lark_webhook(request: Request):
    try:
        # Get request body
        body = await request.body()
        raw = body.decode("utf-8")
        body_json = json.loads(raw)

        # ENHANCED DEBUG: Show all event types and details
        event_type = body_json.get("header", {}).get("event_type")
        print("=" * 80)
        print("🔥🔥🔥 WEBHOOK TRIGGERED!")
        print(f"🔍 EVENT TYPE: {event_type}")
        
        if event_type == "im.message.receive_v1":
            print("📨 MESSAGE EVENT RECEIVED!")
            event_data = body_json.get("event", {})
            message_data = event_data.get("message", {})
            sender_data = event_data.get("sender", {})
            
            # Message details
            thread_id = message_data.get("thread_id", "")
            content = message_data.get("content", "")
            chat_id = message_data.get("chat_id", "")
            message_id = message_data.get("message_id", "")
            
            # Sender details
            sender_id_obj = sender_data.get("sender_id", {})
            open_id = sender_id_obj.get("open_id", "")
            user_id = sender_id_obj.get("user_id", "")
            union_id = sender_id_obj.get("union_id", "")
            
            print(f"📋 MESSAGE DETAILS:")
            print(f"   Message ID: {message_id}")
            print(f"   Chat ID: {chat_id}")
            print(f"   Thread ID: {thread_id}")
            print(f"   Content: {content}")
            print()
            print(f"👤 SENDER DETAILS:")
            print(f"   Open ID: {open_id}")
            print(f"   User ID: {user_id}")
            print(f"   Union ID: {union_id}")
            print()
            print(f"🎯 TOPIC COMPARISON:")
            print(f"   Expected Commands Thread: omt_1b138b4e444c577b")
            print(f"   Actual Thread ID: {thread_id}")
            print(f"   Is Commands Topic: {thread_id == 'omt_1b138b4e444c577b'}")
            print()
            print(f"🔐 AUTHORIZATION CHECK:")
            print(f"   Current Auth User: ou_8306cee2e3b33c84b1799760f98d6e0b")
            print(f"   Message Open ID: {open_id}")
            print(f"   Authorization Match: {open_id == 'ou_8306cee2e3b33c84b1799760f98d6e0b'}")
            print()
            
        print("RAW BODY:", raw[:500] + "..." if len(raw) > 500 else raw)
        print("=" * 80)

        logger.info(f"📨 Webhook received: {json.dumps(body_json, indent=2)[:300]}...")

        # Handle URL verification (still schema 1.0 format)
        if body_json.get("type") == "url_verification":
            challenge = body_json.get("challenge", "")
            logger.info(f"🔐 URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})

        # Handle message event for schema 2.0
        if event_type == "im.message.receive_v1":
            event = body_json.get("event", {})
            # IMPORTANT: Pass the header to the event for deduplication
            event["header"] = body_json.get("header", {})
            
            await process_message_event(event)
            return JSONResponse({"success": True})

        logger.info(f"ℹ️ Unknown or unhandled event type: {event_type}")
        return JSONResponse({"success": True})

    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def process_message_event(event):
    """Process incoming message event."""
    try:
        # Get event and message IDs for deduplication
        header = event.get("header", {})
        message_data = event.get("message", {})
        
        event_id = header.get("event_id", "")
        message_id = message_data.get("message_id", "")
        message_content = message_data.get("content", "")
        message_create_time = int(message_data.get("create_time", "0"))
        
        # Check if message is too old (older than 60 seconds)
        current_time_ms = int(time.time() * 1000)
        message_age_seconds = (current_time_ms - message_create_time) / 1000
        
        logger.info(f"🔍 Checking message: event_id={event_id[:8]}..., message_id={message_id[:10]}..., age={message_age_seconds:.1f}s")
        
        # IGNORE OLD MESSAGES (older than 60 seconds)
        if message_age_seconds > 60:
            logger.warning(f"🕐 IGNORING OLD MESSAGE - Age: {message_age_seconds:.1f}s (>{60}s)")
            return
        
        # FIXED: Only check for actual duplicate messages, not content duplicates
        if is_duplicate_message(event_id, message_id):
            logger.warning(f"🚫 DUPLICATE MESSAGE BLOCKED - event_id: {event_id[:8]}..., message_id: {message_id[:10]}...")
            return
        
        logger.info(f"✅ NEW MESSAGE ACCEPTED - Processing: {json.dumps(message_data, indent=2)[:200]}...")

        # Parse message
        message = message_parser.parse_message(event)
        
        # ENHANCED DEBUG: Show parsing results
        print("🔍 PARSING RESULTS:")
        raw_sender = event.get("sender", {}).get("sender_id", {})
        print(f"Raw sender_id object: {raw_sender}")
        print(f"Parsed message.sender_id: {message.sender_id}")
        print(f"Parsed message.content: {message.content}")
        print(f"Parsed message.thread_id: {message.thread_id}")
        print(f"Parsed message.chat_id: {message.chat_id}")
        print(f"Is from bot: {message.is_from_bot}")
        print()

        # Skip bot messages
        if message.is_from_bot:
            logger.info("🤖 Ignoring bot message")
            return

        # Check if it's a command
        is_command = message_parser.is_command(message)
        print(f"🎯 COMMAND CHECK:")
        print(f"   Is command: {is_command}")
        print(f"   Content: '{message.content}'")
        print(f"   Starts with '/': {message.content.strip().startswith('/')}")
        print()
        
        if not is_command:
            logger.info(f"📝 Not a command: {message.content}")
            return

        # Check if it's in commands topic
        is_commands_topic = topic_manager.is_topic_message(message.thread_id, TopicType.COMMANDS)
        print(f"📍 TOPIC CHECK:")
        print(f"   Message thread_id: {message.thread_id}")
        print(f"   Expected commands topic: {getattr(Config, 'LARK_TOPIC_COMMANDS', 'Not set')}")
        print(f"   Is commands topic: {is_commands_topic}")
        print()
        
        if not is_commands_topic:
            logger.info(f"📍 Command not in commands topic: {message.thread_id}")
            return

        # Parse command
        command, args = message_parser.parse_command(message)

        logger.info(f"🎯 COMMAND RECEIVED: /{command} {args} from {message.sender_id}")

        # Create context
        context = CommandContext(
            message=message,
            command=command,
            args=args,
            sender_id=message.sender_id,
            chat_id=message.chat_id,
            thread_id=message.thread_id,
            topic_manager=topic_manager,
            api_client=api_client,
            config=Config
        )

        # Execute command
        async with api_client:
            success = await handler_registry.execute_command(context)

        if success:
            logger.info(f"✅ COMMAND EXECUTED: /{command}")
        else:
            logger.error(f"❌ COMMAND FAILED: /{command}")

    except Exception as e:
        logger.error(f"❌ Message processing error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Add missing method
    if not hasattr(Config, 'get_current_time'):
        from datetime import datetime
        Config.get_current_time = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("🎯 Starting REAL Webhook Lark Bot")
    print("=" * 50)
    print("Based on production architecture from research!")
    print("This bot will ACTUALLY listen to your /help commands")
    print("=" * 50)
    
    # Run the FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")