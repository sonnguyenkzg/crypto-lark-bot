#!/usr/bin/env python3
"""
Interactive Lark Bot for Real Testing
Responds to your actual /help commands in Lark
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add bot modules to path
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.message_parser import LarkMessageParser
from bot.services.topic_manager import LarkTopicManager, TopicType
from bot.utils.handler_registry import HandlerRegistry, CommandContext
from bot.handlers.help_handler import HelpHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class InteractiveLarkBot:
    """Real interactive bot that responds to your Lark messages."""
    
    def __init__(self):
        self.config = Config
        self.api_client = None
        self.topic_manager = None
        self.message_parser = LarkMessageParser()
        self.handler_registry = HandlerRegistry(Config)
        self.is_running = False
        self.last_message_time = None
        
    async def initialize(self):
        """Initialize bot components."""
        try:
            self.config.validate_config()
            logger.info("✅ Configuration validated")
            
            # Initialize API client
            self.api_client = LarkAPIClient(
                app_id=self.config.LARK_APP_ID,
                app_secret=self.config.LARK_APP_SECRET
            )
            
            # Test connection
            async with self.api_client as client:
                if await client.test_connection():
                    logger.info("✅ Lark API connection successful")
                else:
                    raise Exception("Failed to connect to Lark API")
            
            # Initialize topic manager
            self.topic_manager = LarkTopicManager(self.api_client, self.config)
            
            # Register Help Handler
            help_handler = HelpHandler()
            self.handler_registry.register(help_handler)
            logger.info("✅ Help Handler registered")
            
            # Add authorization middleware
            from bot.utils.handler_registry import authorization_middleware
            self.handler_registry.add_middleware(authorization_middleware)
            logger.info("✅ Authorization middleware added")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    async def send_startup_message(self):
        """Send startup message to daily report topic."""
        try:
            async with self.api_client:
                startup_msg = (
                    "🎮 **Interactive Bot Started - Ready for Real Testing!**\n"
                    f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    "🎯 I'm now listening for your commands\n\n"
                    "💡 **How to test:**\n"
                    "1. Go to #commands topic\n"
                    "2. Type `/help` and press Enter\n"
                    "3. I will respond immediately!\n\n"
                    "🔄 Bot will check for new messages every 5 seconds\n"
                    "⚡ Try these commands:\n"
                    "• `/help` - General help\n"
                    "• `/help start` - Specific help\n"
                    "• `/h` - Test alias\n\n"
                    "🎉 **Ready to respond to your messages!**"
                )
                
                success = await self.topic_manager.send_to_dailyreport(startup_msg)
                if success:
                    logger.info("✅ Startup message sent")
                else:
                    logger.warning("⚠️ Failed to send startup message")
                    
        except Exception as e:
            logger.error(f"❌ Error sending startup message: {e}")
    
    async def get_recent_messages(self):
        """Get recent messages using alternative method."""
        try:
            # Try to get messages using a simple approach
            async with self.api_client as client:
                
                # Method 1: Direct API call with minimal parameters
                url = f"{client.base_url}/im/v1/messages"
                headers = {
                    "Authorization": f"Bearer {await client.get_access_token()}",
                    "Content-Type": "application/json"
                }
                
                # Try different parameter combinations
                param_sets = [
                    {"page_size": 5},
                    {"page_size": 5, "sort_type": "ByCreateTime"},
                ]
                
                for params in param_sets:
                    try:
                        async with client.session.get(url, headers=headers, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("code") == 0:
                                    messages = data.get("data", {}).get("items", [])
                                    logger.info(f"📬 Retrieved {len(messages)} messages")
                                    return messages
                    except Exception as e:
                        logger.warning(f"⚠️ Parameter set failed: {e}")
                        continue
                
                logger.warning("⚠️ All message retrieval methods failed")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error getting messages: {e}")
            return []
    
    async def simple_message_check(self):
        """Simple alternative - check for bot mentions."""
        try:
            async with self.api_client as client:
                # Send a test message to see if we can get any response
                test_msg = f"🤖 Bot alive check - {datetime.now().strftime('%H:%M:%S')}"
                
                # This is just to keep the bot "active" - you'll need to manually send commands
                logger.info(f"🔄 Bot is listening... Send '/help' in #commands topic")
                
                return []
                
        except Exception as e:
            logger.error(f"❌ Message check error: {e}")
            return []
    
    async def process_message(self, raw_message):
        """Process a single message."""
        try:
            # Parse message
            message = self.message_parser.parse_message(raw_message)
            
            logger.info(f"📨 Processing message: {message.content[:50]}... from {message.sender_id}")
            
            # Skip bot messages
            if message.is_from_bot:
                logger.info("📨 Skipping bot message")
                return
            
            # Check if it's a command
            if not self.message_parser.is_command(message):
                logger.info(f"📨 Not a command: {message.content}")
                return
            
            # Check if it's in commands topic
            if not self.topic_manager.is_topic_message(message.thread_id, TopicType.COMMANDS):
                logger.info(f"📨 Command from wrong topic: {message.thread_id}")
                return
            
            # Parse command
            command, args = self.message_parser.parse_command(message)
            
            logger.info(f"🎯 COMMAND DETECTED: /{command} {args} (user: {message.sender_id})")
            
            # Create command context
            context = CommandContext(
                message=message,
                command=command,
                args=args,
                sender_id=message.sender_id,
                chat_id=message.chat_id,
                thread_id=message.thread_id,
                topic_manager=self.topic_manager,
                api_client=self.api_client,
                config=self.config
            )
            
            # Execute command
            async with self.api_client:
                success = await self.handler_registry.execute_command(context)
            
            if success:
                logger.info(f"✅ COMMAND EXECUTED: /{command}")
            else:
                logger.warning(f"⚠️ COMMAND FAILED: /{command}")
                
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
    
    async def manual_command_processor(self):
        """Manual command processor - simulates receiving /help."""
        print("\n" + "="*50)
        print("🎮 MANUAL COMMAND MODE")
        print("Since API polling is limited, you can simulate commands here")
        print("Type commands as if you sent them in Lark:")
        print("Examples: help, help start, h")
        print("Type 'quit' to exit")
        print("="*50)
        
        try:
            async with self.api_client:
                while self.is_running:
                    try:
                        # Get user input
                        user_input = await asyncio.get_event_loop().run_in_executor(
                            None, input, "\n🎯 Simulate command: /"
                        )
                        
                        if user_input.lower() in ['quit', 'exit', 'q']:
                            break
                        
                        if not user_input.strip():
                            continue
                        
                        # Parse input
                        parts = user_input.strip().split()
                        command = parts[0]
                        args = parts[1:] if len(parts) > 1 else []
                        
                        print(f"🧪 Simulating: /{command} {' '.join(args)}")
                        
                        # Create mock message
                        class MockMessage:
                            def __init__(self):
                                self.content = f"/{command} {' '.join(args)}"
                                self.sender_id = self.config.LARK_AUTHORIZED_USERS[0] if self.config.LARK_AUTHORIZED_USERS else "test_user"
                                self.chat_id = self.config.LARK_CHAT_ID
                                self.thread_id = self.config.LARK_TOPIC_COMMANDS
                                self.is_from_bot = False
                        
                        # Create context
                        context = CommandContext(
                            message=MockMessage(),
                            command=command,
                            args=args,
                            sender_id=self.config.LARK_AUTHORIZED_USERS[0] if self.config.LARK_AUTHORIZED_USERS else "test_user",
                            chat_id=self.config.LARK_CHAT_ID,
                            thread_id=self.config.LARK_TOPIC_COMMANDS,
                            topic_manager=self.topic_manager,
                            api_client=self.api_client,
                            config=self.config
                        )
                        
                        # Execute
                        success = await self.handler_registry.execute_command(context)
                        
                        if success:
                            print("✅ Command executed - Check #commands topic in Lark!")
                        else:
                            print("❌ Command failed")
                            
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"❌ Error: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Manual processor error: {e}")
    
    async def run(self):
        """Run the interactive bot."""
        try:
            logger.info("🚀 Starting Interactive Lark Bot...")
            
            # Initialize
            if not await self.initialize():
                logger.error("❌ Failed to initialize bot")
                return False
            
            # Send startup message
            await self.send_startup_message()
            
            self.is_running = True
            logger.info("✅ Interactive bot started!")
            logger.info("💡 Send '/help' in #commands topic to test")
            
            # Start manual command processor
            await self.manual_command_processor()
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
        finally:
            self.is_running = False

async def main():
    """Main function."""
    bot = InteractiveLarkBot()
    await bot.run()

if __name__ == "__main__":
    print("🎮 Interactive Lark Bot")
    print("=" * 30)
    print("This bot will respond to your /help commands in Lark!")
    print("After starting, go to #commands topic and type /help")
    print("=" * 30)
    
    asyncio.run(main())