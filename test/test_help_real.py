import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager
from bot.handlers.help_handler import HelpHandler

async def test_help_real():
    config = Config
    
    # Get the authorized user ID from config
    your_user_id = config.LARK_AUTHORIZED_USERS[0] if config.LARK_AUTHORIZED_USERS else "unknown"
    print(f"🆔 Using your user ID: {your_user_id}")
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        class RealContext:
            def __init__(self):
                self.sender_id = your_user_id  # Use ID from config
                self.args = []
                self.config = config
                self.topic_manager = topic_manager
        
        context = RealContext()
        success = await help_handler.execute(context)
        
        if success:
            print("✅ Help with YOUR real user ID sent!")
        else:
            print("❌ Failed")

asyncio.run(test_help_real())