#!/usr/bin/env python3
"""
Manual Help Handler Test Script
Tests the Help Handler directly and sends responses to Lark
"""

import asyncio
import logging
import sys
import os

# Add bot modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager
from bot.handlers.help_handler import HelpHandler
from bot.utils.handler_registry import CommandContext

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockMessage:
    """Mock message for testing."""
    def __init__(self, content, sender_id="test_user", thread_id=None):
        self.content = content
        self.sender_id = sender_id
        self.thread_id = thread_id
        self.chat_id = "test_chat"

async def test_help_handler():
    """Test Help Handler manually and send results to Lark."""
    
    print("🧪 Manual Help Handler Test")
    print("=" * 50)
    
    try:
        # Initialize components
        config = Config
        config.validate_config()
        
        api_client = LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET)
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        print("✅ Components initialized")
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "General Help",
                "command": "help",
                "args": [],
                "description": "Test general help command"
            },
            {
                "name": "Specific Help - Start",
                "command": "help", 
                "args": ["start"],
                "description": "Test help for start command"
            },
            {
                "name": "Specific Help - Add",
                "command": "help",
                "args": ["add"], 
                "description": "Test help for add command"
            },
            {
                "name": "Unknown Command Help",
                "command": "help",
                "args": ["unknown"],
                "description": "Test help for unknown command"
            },
            {
                "name": "Help Alias Test",
                "command": "h",
                "args": [],
                "description": "Test help alias"
            }
        ]
        
        async with api_client:
            # Send test start message
            start_msg = (
                "🧪 **Manual Help Handler Test Started**\n"
                f"📅 {config.get_current_time() if hasattr(config, 'get_current_time') else 'Unknown'}\n"
                f"🎯 Testing {len(test_scenarios)} scenarios\n\n"
                "Results will appear below..."
            )
            
            await topic_manager.send_to_commands(start_msg)
            print("✅ Test start message sent")
            
            # Test each scenario
            for i, scenario in enumerate(test_scenarios, 1):
                print(f"\n🧪 Test {i}: {scenario['name']}")
                print(f"   Command: /{scenario['command']} {' '.join(scenario['args'])}")
                
                try:
                    # Create mock context
                    mock_message = MockMessage(
                        content=f"/{scenario['command']} {' '.join(scenario['args'])}",
                        sender_id="manual_test_user",
                        thread_id=config.LARK_TOPIC_COMMANDS
                    )
                    
                    context = CommandContext(
                        message=mock_message,
                        command=scenario['command'],
                        args=scenario['args'],
                        sender_id="manual_test_user",
                        chat_id=config.LARK_CHAT_ID,
                        thread_id=config.LARK_TOPIC_COMMANDS,
                        topic_manager=topic_manager,
                        api_client=api_client,
                        config=config
                    )
                    
                    # Execute help handler
                    success = await help_handler.handle(context)
                    
                    if success:
                        print(f"   ✅ {scenario['name']} - SUCCESS")
                        
                        # Send test separator
                        separator = f"\n{'='*30}\n🧪 **Test {i} Complete: {scenario['name']}**\n{'='*30}\n"
                        await topic_manager.send_to_commands(separator)
                        
                    else:
                        print(f"   ❌ {scenario['name']} - FAILED")
                        
                        # Send error message
                        error_msg = f"❌ **Test {i} Failed: {scenario['name']}**\nCommand: /{scenario['command']} {' '.join(scenario['args'])}"
                        await topic_manager.send_to_commands(error_msg)
                
                except Exception as e:
                    print(f"   💥 {scenario['name']} - ERROR: {e}")
                    
                    # Send error message
                    error_msg = f"💥 **Test {i} Error: {scenario['name']}**\nError: {str(e)}"
                    await topic_manager.send_to_commands(error_msg)
                
                # Small delay between tests
                await asyncio.sleep(1)
            
            # Send completion message
            completion_msg = (
                f"🎉 **Manual Help Handler Test Complete**\n"
                f"📊 Tested {len(test_scenarios)} scenarios\n"
                f"✅ Check #commands topic for all test results\n\n"
                f"📋 **Test Summary:**\n" +
                "\n".join([f"• {scenario['name']}" for scenario in test_scenarios])
            )
            
            await topic_manager.send_to_commands(completion_msg)
            print(f"\n🎉 All {len(test_scenarios)} tests completed!")
            print("✅ Check #commands topic for detailed results")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        
        # Try to send error to Lark
        try:
            async with api_client:
                error_msg = f"💥 **Manual Test Failed**\nError: {str(e)}"
                await topic_manager.send_to_commands(error_msg)
        except:
            pass

async def interactive_test():
    """Interactive test mode."""
    print("\n🎮 Interactive Test Mode")
    print("Type help commands to test (or 'quit' to exit):")
    print("Examples: help, help start, h, help add")
    
    try:
        config = Config
        config.validate_config()
        
        api_client = LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET)
        topic_manager = LarkTopicManager(api_client, config)
        help_handler = HelpHandler()
        
        async with api_client:
            while True:
                try:
                    user_input = input("\n> ").strip()
                    
                    if user_input.lower() in ['quit', 'exit', 'q']:
                        print("👋 Goodbye!")
                        break
                    
                    if not user_input:
                        continue
                    
                    # Parse command
                    parts = user_input.split()
                    command = parts[0]
                    args = parts[1:] if len(parts) > 1 else []
                    
                    print(f"🧪 Testing: /{command} {' '.join(args)}")
                    
                    # Create context
                    mock_message = MockMessage(
                        content=f"/{command} {' '.join(args)}",
                        sender_id="interactive_test",
                        thread_id=config.LARK_TOPIC_COMMANDS
                    )
                    
                    context = CommandContext(
                        message=mock_message,
                        command=command,
                        args=args,
                        sender_id="interactive_test",
                        chat_id=config.LARK_CHAT_ID,
                        thread_id=config.LARK_TOPIC_COMMANDS,
                        topic_manager=topic_manager,
                        api_client=api_client,
                        config=config
                    )
                    
                    # Execute
                    success = await help_handler.handle(context)
                    
                    if success:
                        print("✅ Command sent to #commands topic")
                    else:
                        print("❌ Command failed")
                        
                except KeyboardInterrupt:
                    print("\n👋 Goodbye!")
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    
    except Exception as e:
        print(f"❌ Setup failed: {e}")

async def main():
    """Main function with menu."""
    
    if not hasattr(Config, 'get_current_time'):
        from datetime import datetime
        Config.get_current_time = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("🧪 Help Handler Manual Test")
    print("=" * 30)
    print("Choose test mode:")
    print("1. Automated test (runs all scenarios)")
    print("2. Interactive test (type commands)")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        await test_help_handler()
    elif choice == "2":
        await interactive_test()
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    asyncio.run(main())