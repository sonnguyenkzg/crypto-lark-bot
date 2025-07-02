#!/usr/bin/env python3
"""
Lark Crypto Wallet Monitor Bot - Polling Version
Equivalent to your Telegram bot but for Lark
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LarkBotConfig:
    """Configuration for Lark bot (similar to your Config class)"""
    
    LARK_APP_ID = os.getenv('LARK_APP_ID')
    LARK_APP_SECRET = os.getenv('LARK_APP_SECRET')
    LARK_CHAT_ID = os.getenv('LARK_CHAT_ID', '')  # Default chat for testing
    
    # Authorization (similar to your Telegram setup)
    AUTHORIZED_USERS = os.getenv('LARK_AUTHORIZED_USERS', '').split(',')
    AUTHORIZED_USERS = [user.strip() for user in AUTHORIZED_USERS if user.strip()]
    
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'DEV')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def setup_logging(cls):
        """Setup logging (same as your Telegram bot)"""
        logging.basicConfig(
            level=getattr(logging, cls.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('lark_bot.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    @classmethod
    def validate_config(cls):
        """Validate configuration (similar to your Telegram validation)"""
        if not cls.LARK_APP_ID or not cls.LARK_APP_SECRET:
            raise ValueError("LARK_APP_ID and LARK_APP_SECRET are required")

class LarkAPI:
    """Lark API client (equivalent to your Telegram API calls)"""
    
    def __init__(self):
        self.app_id = LarkBotConfig.LARK_APP_ID
        self.app_secret = LarkBotConfig.LARK_APP_SECRET
        self.base_url = "https://open.larksuite.com/open-apis"
        self.tenant_access_token = None
        self.token_expires = 0
        self.logger = logging.getLogger(__name__)
    
    def get_tenant_access_token(self) -> Optional[str]:
        """Get access token (equivalent to your Telegram token)"""
        if self.tenant_access_token and time.time() < self.token_expires:
            return self.tenant_access_token
            
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                self.tenant_access_token = result.get('tenant_access_token')
                self.token_expires = time.time() + 5400  # 1.5 hours
                return self.tenant_access_token
            else:
                self.logger.error(f"Token error: {result.get('msg')}")
                return None
        except Exception as e:
            self.logger.error(f"Token exception: {e}")
            return None
    
    def send_message(self, chat_id: str, text: str) -> bool:
        """Send message (equivalent to update.message.reply_text)"""
        token = self.get_tenant_access_token()
        if not token:
            return False
        
        url = f"{self.base_url}/im/v1/messages"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        data = {
            'receive_id': chat_id,
            'receive_id_type': 'chat_id',
            'msg_type': 'text',
            'content': json.dumps({'text': text})
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                return True
            else:
                self.logger.error(f"Send failed: {result.get('msg')}")
                return False
        except Exception as e:
            self.logger.error(f"Send error: {e}")
            return False
    
    def get_chat_messages(self, chat_id: str, start_time: int = None) -> list:
        """Get messages from chat (for polling - equivalent to Telegram updates)"""
        token = self.get_tenant_access_token()
        if not token:
            return []
        
        url = f"{self.base_url}/im/v1/messages"
        headers = {'Authorization': f'Bearer {token}'}
        params = {
            'container_id_type': 'chat',
            'container_id': chat_id,
            'page_size': 20
        }
        
        # Don't use start_time parameter - just get recent messages
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('items', [])
            else:
                self.logger.error(f"Get messages failed: {result.get('msg')}")
                return []
        except Exception as e:
            self.logger.error(f"Get messages error: {e}")
            return []

class LarkMessage:
    """Message wrapper (equivalent to your Telegram Update)"""
    
    def __init__(self, message_data: dict, api: LarkAPI):
        self.data = message_data
        self.api = api
        
    @property
    def text(self) -> str:
        """Get message text"""
        try:
            # Content is nested in body.content for Lark API
            body = self.data.get('body', {})
            content_str = body.get('content', '{}')
            content = json.loads(content_str)
            return content.get('text', '')
        except:
            return ''
    
    @property
    def chat_id(self) -> str:
        """Get chat ID"""
        return self.data.get('chat_id', '')
    
    @property
    def user_id(self) -> str:
        """Get sender user ID"""
        return self.data.get('sender', {}).get('id', {}).get('open_id', '')
    
    @property
    def user_name(self) -> str:
        """Get sender name"""
        return self.data.get('sender', {}).get('sender_id', {}).get('open_id', 'User')
    
    def is_bot_message(self) -> bool:
        """Check if message is from bot"""
        return self.data.get('sender', {}).get('sender_type') == 'app'
    
    def is_command(self) -> bool:
        """Check if message is a command"""
        text = self.text.strip()
        return text.startswith('/') or '@_user_1' in text  # @_user_1 is bot mention
    
    async def reply_text(self, text: str) -> bool:
        """Reply to message (equivalent to update.message.reply_text)"""
        return self.api.send_message(self.chat_id, text)

class BaseHandler:
    """Base handler class (same as your Telegram BaseHandler)"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @property
    def command_name(self) -> str:
        raise NotImplementedError
    
    @property
    def description(self) -> str:
        raise NotImplementedError
    
    async def check_authorization(self, message: LarkMessage) -> bool:
        """Check if user is authorized (same logic as your Telegram bot)"""
        user_id = message.user_id
        authorized_users = LarkBotConfig.AUTHORIZED_USERS
        
        if not authorized_users or user_id in authorized_users:
            return True
        
        await message.reply_text("❌ You are not authorized to use this bot.")
        self.logger.warning(f"Unauthorized access attempt from user {user_id}")
        return False
    
    async def handle(self, message: LarkMessage) -> None:
        """Handle the command"""
        raise NotImplementedError

class CheckHandler(BaseHandler):
    """Check handler (simplified version of your Telegram CheckHandler)"""
    
    @property
    def command_name(self) -> str:
        return "check"
    
    @property
    def description(self) -> str:
        return "Check wallet balances"
    
    async def handle(self, message: LarkMessage) -> None:
        """Handle the /check command"""
        if not await self.check_authorization(message):
            return
        
        # Simple response for now (you can port your full logic later)
        response = """💰 **Wallet Balance Check**

⏰ **Time:** 2025-07-02 12:00 GMT+7

• **KZP Store 1:** 50,000.00 USDT
• **KZP Store 2:** 25,000.00 USDT
• **KZP Office:** 10,000.00 USDT

📊 **Total:** 125,000.00 USDT"""
        
        await message.reply_text(response)
        self.logger.info(f"Check command completed for user {message.user_name}")

class HelpHandler(BaseHandler):
    """Help handler (same as your Telegram HelpHandler)"""
    
    @property
    def command_name(self) -> str:
        return "help"
    
    @property
    def description(self) -> str:
        return "Show all available commands"
    
    async def handle(self, message: LarkMessage) -> None:
        """Handle the /help command"""
        if not await self.check_authorization(message):
            return
        
        help_text = """📖 **Available Commands**

**Wallet Management:**
• /start - Initialize and show welcome
• /help - Show this help message
• /list - Display all configured wallets
• /check - Check all wallet balances

**Examples:**
• /check - Check all wallets
• @Crypto Wallet Monitor Test /help - Mention bot

💰 **Daily Reports:** Sent automatically at 12:00 AM GMT+7"""
        
        await message.reply_text(help_text)

class LarkBot:
    """Main bot class (equivalent to your Telegram Application)"""
    
    def __init__(self):
        self.api = LarkAPI()
        self.handlers = {}
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.last_message_time = int(time.time() * 1000)  # milliseconds
        
        # Register handlers (same as your setup_handlers)
        self.register_handler(CheckHandler())
        self.register_handler(HelpHandler())
    
    def register_handler(self, handler: BaseHandler):
        """Register command handler"""
        self.handlers[handler.command_name] = handler
        self.logger.info(f"Registered handler: {handler.command_name}")
    
    def parse_command(self, text: str) -> tuple:
        """Parse command from text"""
        text = text.strip()
        
        # Handle @mentions (remove @_user_1)
        if '@_user_1' in text:
            text = text.replace('@_user_1', '').strip()
        
        # Handle commands
        if text.startswith('/'):
            parts = text.split()
            command = parts[0][1:]  # Remove /
            args = parts[1:] if len(parts) > 1 else []
            return command, args
        
        return None, []
    
    async def handle_message(self, message: LarkMessage):
        """Handle incoming message"""
        if message.is_bot_message():
            return
        
        if not message.is_command():
            return
        
        command, args = self.parse_command(message.text)
        
        if command in self.handlers:
            try:
                await self.handlers[command].handle(message)
            except Exception as e:
                self.logger.error(f"Error handling command {command}: {e}")
                await message.reply_text(f"❌ Error processing command: {e}")
        elif command:
            # Unknown command (same as your handle_unknown_command)
            unknown_message = f"""❌ Unknown command: `/{command}`

💡 **Available commands:**
• /help - Show all commands  
• /check - Check balances

Use /help for detailed usage information."""
            
            await message.reply_text(unknown_message)
    
    async def poll_messages(self, chat_id: str):
        """Poll for new messages (equivalent to run_polling)"""
        self.logger.info(f"Starting message polling for chat {chat_id}")
        
        while self.running:
            try:
                # Get new messages
                messages = self.api.get_chat_messages(chat_id, self.last_message_time)
                
                # Debug: log all messages received
                if messages:
                    self.logger.info(f"📨 Received {len(messages)} messages")
                    for i, msg_data in enumerate(messages):
                        msg_time = int(msg_data.get('create_time', 0))
                        sender_type = msg_data.get('sender', {}).get('sender_type', 'unknown')
                        content = msg_data.get('content', '{}')
                        msg_type = msg_data.get('msg_type', 'unknown')
                        
                        self.logger.info(f"  Message {i+1}: time={msg_time}, sender_type={sender_type}, msg_type={msg_type}")
                        
                        # Get content from body.content (correct location for Lark API)
                        body = msg_data.get('body', {})
                        content = body.get('content', '{}')
                        self.logger.info(f"    Body content: {content}")
                        
                        try:
                            if content and content != '{}':
                                parsed_content = json.loads(content)
                                text = parsed_content.get('text', '')
                                self.logger.info(f"    Parsed content: {parsed_content}")
                                self.logger.info(f"    Extracted text: '{text}'")
                            else:
                                self.logger.info(f"    Empty or invalid content")
                        except Exception as e:
                            self.logger.info(f"    Parse error: {e}")
                
                for msg_data in messages:
                    msg_time = int(msg_data.get('create_time', 0))
                    if msg_time > self.last_message_time:
                        self.last_message_time = msg_time
                        
                        message = LarkMessage(msg_data, self.api)
                        self.logger.info(f"🔍 Processing message: '{message.text}' from {message.user_name}")
                        await self.handle_message(message)
                
                await asyncio.sleep(5)  # Poll every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Polling error: {e}")
                await asyncio.sleep(10)
    
    def run_polling(self, chat_id: str = None):
        """Run bot with polling (same as your application.run_polling)"""
        chat_id = chat_id or LarkBotConfig.LARK_CHAT_ID
        if not chat_id:
            raise ValueError("LARK_CHAT_ID is required for polling")
        
        self.running = True
        
        # Setup signal handlers (same as your setup_signal_handlers)
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down...")
            self.running = False
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Run polling
        asyncio.run(self.poll_messages(chat_id))

def main():
    """Main function (same as your Telegram main)"""
    try:
        print("🤖 Starting Lark Crypto Wallet Monitor Bot...")
        
        # Validate configuration (same as your Telegram bot)
        LarkBotConfig.validate_config()
        logger = LarkBotConfig.setup_logging()
        logger.info("Configuration validated successfully")
        
        # Create and run bot
        bot = LarkBot()
        
        logger.info("=== Bot Startup Complete ===")
        logger.info(f"Environment: {LarkBotConfig.ENVIRONMENT}")
        logger.info(f"Authorized users: {len(LarkBotConfig.AUTHORIZED_USERS)}")
        logger.info(f"Registered commands: {', '.join(bot.handlers.keys())}")
        logger.info("Bot is now running... Press Ctrl+C to stop")
        logger.info("===========================")
        
        # Run polling (same as your Telegram bot)
        bot.run_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()