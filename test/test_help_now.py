import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager
from bot.handlers.help_handler import HelpHandler

async def test_help():
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        # Create fake context with any user ID
        class FakeContext:
            def __init__(self):
                self.sender_id = "any_user"  # We'll use any ID for now
                self.args = []
                self.config = config
                self.topic_manager = topic_manager
        
        context = FakeContext()
        
        # Just run the help command
        success = await help_handler.execute(context)
        
        if success:
            print("✅ Help command sent to #commands topic!")
        else:
            print("❌ Failed")

asyncio.run(test_help())