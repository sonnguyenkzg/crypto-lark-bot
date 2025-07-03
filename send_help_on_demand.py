#!/usr/bin/env python3
"""
Send Help Response On Demand
Run this script whenever you want to send /help response
"""
import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager
from bot.handlers.help_handler import HelpHandler

async def send_help_response():
    """Send help response directly to commands topic."""
    try:
        config = Config
        
        async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
            topic_manager = LarkTopicManager(api_client, config)
            help_handler = HelpHandler()
            
            # Get your user ID from config
            your_user_id = config.LARK_AUTHORIZED_USERS[0] if config.LARK_AUTHORIZED_USERS else "unknown"
            
            print(f"🎯 Sending /help response for user: {your_user_id}")
            
            # Create context
            class Context:
                def __init__(self):
                    self.sender_id = your_user_id
                    self.args = []
                    self.config = config
                    self.topic_manager = topic_manager
            
            context = Context()
            
            # Execute help command
            success = await help_handler.execute(context)
            
            if success:
                print("✅ Help response sent to #commands topic!")
                print("📱 Check your Lark #commands topic now")
            else:
                print("❌ Failed to send help response")
                
    except Exception as e:
        print(f"❌ Error: {e}")

async def interactive_menu():
    """Interactive menu for different commands."""
    while True:
        print("\n" + "="*40)
        print("🎮 Lark Bot Command Sender")
        print("="*40)
        print("1. Send /help response")
        print("2. Send /help start response") 
        print("3. Send custom help response")
        print("4. Exit")
        
        choice = input("\nChoose option (1-4): ").strip()
        
        if choice == "1":
            await send_help_response()
        elif choice == "2":
            await send_help_start()
        elif choice == "3":
            command = input("Enter command to get help for: ").strip()
            await send_custom_help(command)
        elif choice == "4":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice")

async def send_help_start():
    """Send help for start command."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        your_user_id = config.LARK_AUTHORIZED_USERS[0] if config.LARK_AUTHORIZED_USERS else "unknown"
        
        class Context:
            def __init__(self):
                self.sender_id = your_user_id
                self.args = ["start"]  # Specific help for start
                self.config = config
                self.topic_manager = topic_manager
        
        context = Context()
        success = await help_handler.execute(context)
        
        if success:
            print("✅ Help for /start sent!")
        else:
            print("❌ Failed")

async def send_custom_help(command):
    """Send help for custom command."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        your_user_id = config.LARK_AUTHORIZED_USERS[0] if config.LARK_AUTHORIZED_USERS else "unknown"
        
        class Context:
            def __init__(self):
                self.sender_id = your_user_id
                self.args = [command] if command else []
                self.config = config
                self.topic_manager = topic_manager
        
        context = Context()
        success = await help_handler.execute(context)
        
        if success:
            print(f"✅ Help for /{command} sent!")
        else:
            print("❌ Failed")

if __name__ == "__main__":
    print("🎮 Manual Help Response Sender")
    print("Since the bot can't hear your messages, use this to send responses manually")
    
    asyncio.run(interactive_menu())