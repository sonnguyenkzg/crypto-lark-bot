#!/usr/bin/env python3
"""
Test Help Bot for Real Lark Testing
Minimal bot to test the Help Handler in actual Lark environment
"""

import asyncio
import logging
import sys
import os

# Add bot modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

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

class TestHelpBot:
    """Simple test bot for Help Handler."""
    
    def __init__(self):
        self.config = Config
        self.api_client = None
        self.topic_manager = None
        self.message_parser = LarkMessageParser()
        self.handler_registry = HandlerRegistry(Config)
        self.is_running = False
        
    async def initialize(self):
        """Initialize bot components."""
        try:
            # Validate configuration
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
                    "🧪 **Test Help Bot Started**\n"
                    f"📅 {Config.get_current_time()}\n"
                    "🎯 Ready to test Help Handler\n\n"
                    "💡 **Test Commands:**\n"
                    "• Send `/help` in #commands topic\n"
                    "• Send `/help start` for specific help\n"
                    "• Send `/h` to test aliases\n"
                    "• Send `/help unknown` to test error handling"
                )
                
                success = await self.topic_manager.send_to_dailyreport(startup_msg)
                if success:
                    logger.info("✅ Startup message sent")
                else:
                    logger.warning("⚠️ Failed to send startup message")
                    
        except Exception as e:
            logger.error(f"❌ Error sending startup message: {e}")
    
    async def process_message(self, raw_message):
        """Process a single message."""
        try:
            # Parse message
            message = self.message_parser.parse_message(raw_message)
            
            # Check if it's a command in the commands topic
            if not self.message_parser.is_command(message):
                return
            
            if not self.topic_manager.is_topic_message(message.thread_id, TopicType.COMMANDS):
                logger.info(f"📨 Ignoring command from non-commands topic: {message.thread_id}")
                return
            
            # Parse command
            command, args = self.message_parser.parse_command(message)
            
            logger.info(f"📨 Command received: /{command} {args} (user: {message.sender_id})")
            
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
            success = await self.handler_registry.execute_command(context)
            
            if success:
                logger.info(f"✅ Command executed successfully: /{command}")
            else:
                logger.warning(f"⚠️ Command execution failed: /{command}")
                
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
    
    async def run_polling(self, poll_interval: int = 10):
        """Run message polling loop."""
        try:
            logger.info(f"🔄 Starting message polling (interval: {poll_interval}s)")
            
            async with self.api_client:
                last_message_time = None
                
                while self.is_running:
                    try:
                        # Get recent messages from commands topic
                        messages = await self.api_client.get_chat_messages(
                            self.config.LARK_CHAT_ID, 
                            limit=5
                        )
                        
                        # Filter for new messages in commands topic
                        new_messages = []
                        for msg in messages:
                            # Check if in commands topic
                            if msg.get("thread_id") != self.config.LARK_TOPIC_COMMANDS:
                                continue
                            
                            # Check if new
                            from datetime import datetime
                            msg_time = datetime.fromtimestamp(int(msg.get("create_time", 0)) / 1000)
                            
                            if last_message_time and msg_time <= last_message_time:
                                continue
                            
                            new_messages.append((msg, msg_time))
                        
                        # Update last seen time
                        if new_messages:
                            last_message_time = max(msg_time for _, msg_time in new_messages)
                        
                        # Process new messages
                        for msg, _ in reversed(new_messages):  # Process oldest first
                            await self.process_message(msg)
                        
                        # Wait before next poll
                        await asyncio.sleep(poll_interval)
                        
                    except Exception as e:
                        logger.error(f"❌ Polling error: {e}")
                        await asyncio.sleep(poll_interval)
                        
        except Exception as e:
            logger.error(f"❌ Fatal polling error: {e}")
    
    async def start(self):
        """Start the test bot."""
        try:
            logger.info("🚀 Starting Test Help Bot...")
            
            # Initialize
            if not await self.initialize():
                logger.error("❌ Failed to initialize bot")
                return False
            
            # Send startup message
            await self.send_startup_message()
            
            # Start polling
            self.is_running = True
            logger.info("✅ Test Help Bot started successfully!")
            logger.info("💡 Send '/help' in the #commands topic to test")
            
            await self.run_polling()
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            self.is_running = False
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            return False
    
    def stop(self):
        """Stop the test bot."""
        self.is_running = False
        logger.info("🛑 Stopping Test Help Bot...")

async def main():
    """Main function."""
    bot = TestHelpBot()
    await bot.start()

if __name__ == "__main__":
    # Add missing method to Config for compatibility
    if not hasattr(Config, 'get_current_time'):
        from datetime import datetime
        Config.get_current_time = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    asyncio.run(main())