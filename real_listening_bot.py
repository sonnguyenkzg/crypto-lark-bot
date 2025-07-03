#!/usr/bin/env python3
"""
Real Listening Bot - Actually responds to your /help commands
"""
import asyncio
import logging
import sys
import json
from aiohttp import web
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.message_parser import LarkMessageParser
from bot.services.topic_manager import LarkTopicManager, TopicType
from bot.utils.handler_registry import HandlerRegistry, CommandContext
from bot.handlers.help_handler import HelpHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealBot:
    def __init__(self):
        self.config = Config
        self.api_client = None
        self.topic_manager = None
        self.message_parser = LarkMessageParser()
        self.handler_registry = HandlerRegistry(Config)
        
    async def initialize(self):
        try:
            self.config.validate_config()
            
            self.api_client = LarkAPIClient(
                app_id=self.config.LARK_APP_ID,
                app_secret=self.config.LARK_APP_SECRET
            )
            
            self.topic_manager = LarkTopicManager(self.api_client, self.config)
            
            help_handler = HelpHandler()
            self.handler_registry.register(help_handler)
            
            from bot.utils.handler_registry import authorization_middleware
            self.handler_registry.add_middleware(authorization_middleware)
            
            logger.info("✅ Bot initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Init failed: {e}")
            return False
    
    async def handle_webhook(self, request):
        """Handle Lark webhook."""
        try:
            body = await request.text()
            data = json.loads(body)
            
            # Webhook verification
            if data.get("type") == "url_verification":
                challenge = data.get("challenge", "")
                logger.info(f"🔐 Webhook verification: {challenge}")
                return web.json_response({"challenge": challenge})
            
            # Message event
            elif data.get("type") == "event_callback":
                event = data.get("event", {})
                if event.get("type") == "message":
                    await self.process_message(event.get("message", {}))
                return web.json_response({"success": True})
            
            return web.json_response({"success": True})
            
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def process_message(self, message_data):
        """Process incoming message."""
        try:
            logger.info(f"📨 Received message: {json.dumps(message_data, indent=2)}")
            
            message = self.message_parser.parse_message(message_data)
            
            if message.is_from_bot:
                logger.info("🤖 Ignoring bot message")
                return
            
            if not self.message_parser.is_command(message):
                logger.info(f"📝 Not a command: {message.content}")
                return
            
            if not self.topic_manager.is_topic_message(message.thread_id, TopicType.COMMANDS):
                logger.info(f"📍 Wrong topic: {message.thread_id}")
                return
            
            command, args = self.message_parser.parse_command(message)
            logger.info(f"🎯 COMMAND: /{command} {args} from {message.sender_id}")
            
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
            
            async with self.api_client:
                success = await self.handler_registry.execute_command(context)
            
            if success:
                logger.info(f"✅ Command executed: /{command}")
            else:
                logger.error(f"❌ Command failed: /{command}")
                
        except Exception as e:
            logger.error(f"❌ Message processing error: {e}")
    
    async def start_webhook_server(self, port=8080):
        """Start webhook server."""
        try:
            if not await self.initialize():
                return False
            
            # Send startup message
            async with self.api_client:
                startup_msg = (
                    "🎮 **Real Listening Bot Started!**\n"
                    f"📅 {Config.get_current_time() if hasattr(Config, 'get_current_time') else 'Now'}\n"
                    "🎯 I can now hear your actual /help commands!\n\n"
                    "💡 **Try typing /help in #commands topic**\n"
                    "🔗 **Webhook:** http://localhost:8080/webhook\n\n"
                    "⚠️ **Note:** You need to configure this webhook URL in your Lark app settings"
                )
                await self.topic_manager.send_to_dailyreport(startup_msg)
            
            # Setup webhook routes
            app = web.Application()
            app.router.add_post('/webhook', self.handle_webhook)
            app.router.add_get('/', lambda r: web.json_response({"status": "Bot is running"}))
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            
            logger.info(f"✅ Webhook server started on port {port}")
            logger.info(f"🔗 Webhook URL: http://localhost:{port}/webhook")
            logger.info("💡 Configure this URL in your Lark app webhook settings")
            logger.info("🎯 Try typing /help in #commands topic!")
            
            # Keep running
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")

async def main():
    if not hasattr(Config, 'get_current_time'):
        from datetime import datetime
        Config.get_current_time = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    bot = RealBot()
    await bot.start_webhook_server()

if __name__ == "__main__":
    print("🎮 Real Listening Bot - Will respond to your actual /help commands!")
    print("⚠️  You need to configure webhook URL in Lark app settings")
    asyncio.run(main())