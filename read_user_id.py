#!/usr/bin/env python3
"""
Read User ID from your reply
"""
import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def read_recent_messages():
    """Try to read recent messages to find your user ID."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        
        # Send a message with your user ID info
        message = (
            "🔍 **Checking for Your User ID...**\n"
            "📋 Looking at recent messages...\n\n"
            "💡 **Alternative Methods:**\n"
            "1. Check your Lark profile settings\n"
            "2. Look for User ID in your profile\n"
            "3. Ask admin for your user ID\n\n"
            "🎯 **Your .env file shows:**\n"
            f"LARK_AUTHORIZED_USERS: {config.LARK_AUTHORIZED_USERS}\n\n"
            "📝 **Is your user ID already in there?**"
        )
        
        topic_manager = LarkTopicManager(api_client, config)
        success = await topic_manager.send_to_commands(message)
        
        if success:
            print("✅ Sent user ID check message")
            print(f"🔍 Your .env shows authorized users: {config.LARK_AUTHORIZED_USERS}")
            
            # Check if there's already a user ID
            if config.LARK_AUTHORIZED_USERS and config.LARK_AUTHORIZED_USERS != [""]:
                print(f"💡 Found user ID in config: {config.LARK_AUTHORIZED_USERS[0]}")
                return config.LARK_AUTHORIZED_USERS[0]
            else:
                print("⚠️ No user ID found in config")
                return None
        
        return None

if __name__ == "__main__":
    print("🔍 Reading your user ID...")
    user_id = asyncio.run(read_recent_messages())
    
    if user_id:
        print(f"\n✅ Found your user ID: {user_id}")
        print("\n📋 Next step: Test the help command with your real user ID")
    else:
        print("\n❌ Need to find your user ID manually")
        print("\n💡 Check your .env file or Lark profile")