#!/usr/bin/env python3
"""
Real Webhook-Based Lark Bot - Based on Production Architecture
FIXED: Added message deduplication to prevent duplicate executions
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

# Message deduplication cache - ADDED TO FIX DUPLICATE MESSAGES
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

def is_duplicate_message(event_id: str, message_id: str, message_content: str) -> bool:
    """Check if this message was already processed - ENHANCED with multiple keys"""
    cleanup_message_cache()  # Clean old entries
    
    # Create multiple unique keys for better deduplication
    event_key = f"event:{event_id}"
    message_key = f"msg:{message_id}"
    content_key = f"content:{hash(message_content)}"  # Hash of message content
    
    # Check all possible duplicate scenarios
    if (event_key in _PROCESSED_MESSAGES or 
        message_key in _PROCESSED_MESSAGES or 
        content_key in _PROCESSED_MESSAGES):
        return True
    
    # Mark all keys as processed
    current_time = time.time()
    _PROCESSED_MESSAGES[event_key] = current_time
    _PROCESSED_MESSAGES[message_key] = current_time
    _PROCESSED_MESSAGES[content_key] = current_time
    
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
        print("🔥🔥🔥 WEBHOOK TRIGGERED!")
        print("RAW BODY:", raw)

        body_json = json.loads(raw)

        logger.info(f"📨 Webhook received: {json.dumps(body_json, indent=2)[:300]}...")

        # Handle URL verification (still schema 1.0 format)
        if body_json.get("type") == "url_verification":
            challenge = body_json.get("challenge", "")
            logger.info(f"🔐 URL verification challenge: {challenge}")
            return JSONResponse({"challenge": challenge})

        # Handle message event for schema 2.0
        event_type = body_json.get("header", {}).get("event_type")
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
        # Get event and message IDs for deduplication - ENHANCED FIX WITH TIMESTAMP
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
        
        # CRITICAL: Enhanced duplicate check with multiple keys
        if is_duplicate_message(event_id, message_id, message_content):
            logger.warning(f"🚫 DUPLICATE MESSAGE BLOCKED - event_id: {event_id[:8]}..., message_id: {message_id[:10]}...")
            return
        
        logger.info(f"✅ NEW MESSAGE ACCEPTED - Processing: {json.dumps(message_data, indent=2)[:200]}...")

        # Parse message
        message = message_parser.parse_message(event)

        # Debug: Check sender ID
        print("👤 Extracted sender_id:", message.sender_id)

        # Skip bot messages
        if message.is_from_bot:
            logger.info("🤖 Ignoring bot message")
            return

        # Check if it's a command
        if not message_parser.is_command(message):
            logger.info(f"📝 Not a command: {message.content}")
            return

        # Check if it's in commands topic
        if not topic_manager.is_topic_message(message.thread_id, TopicType.COMMANDS):
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