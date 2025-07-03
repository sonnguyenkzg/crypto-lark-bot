#!/usr/bin/env python3
"""
Get Your Lark User ID
"""
import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def get_user_id():
    """Send a message asking you to respond, then we can see your user ID."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        
        # Send message asking for response
        message = (
            "🆔 **User ID Detection**\n"
            "📝 Please reply to this message with any text\n"
            "🎯 I need to see your user ID to configure the bot\n\n"
            "💡 Just type anything like: 'hello' or 'test'\n"
            "📍 Reply in this #commands topic"
        )
        
        success = await topic_manager.send_to_commands(message)
        
        if success:
            print("✅ Message sent to #commands topic")
            print("📝 Now go to #commands topic and reply with any message")
            print("🔍 Then we'll try to capture your user ID")
        else:
            print("❌ Failed to send message")

if __name__ == "__main__":
    print("🆔 Getting Your Lark User ID...")
    asyncio.run(get_user_id())