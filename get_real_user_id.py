import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def show_user_info():
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        
        message = (
            "🆔 **To Get Your Real User ID:**\n\n"
            "1️⃣ **Check your Lark profile:**\n"
            "   • Click your avatar/picture\n"
            "   • Look for 'User ID' field\n"
            "   • Should start with 'ou_'\n\n"
            "2️⃣ **Or tell me what you see:**\n"
            "   • What's your name in Lark?\n"
            "   • Any ID numbers you can find?\n\n"
            "💡 Once we find it, we'll put it in your .env file!"
        )
        
        await topic_manager.send_to_commands(message)
        print("✅ Instructions sent!")
        print("\n💡 Check your Lark profile for User ID starting with 'ou_'")

asyncio.run(show_user_info())