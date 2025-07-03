import asyncio
import sys
import json
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def test_listening():
    """Test if bot can receive/read messages."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        
        print("🧪 Testing LISTENING capability...")
        
        # Step 1: Send instruction message
        instruction = (
            "📢 **LISTENING TEST**\n"
            "🎯 I will try to read recent messages\n"
            "💡 Send a test message after this:\n"
            "Just type: `test message` in #commands\n"
            "Then I'll check if I can see it"
        )
        
        await topic_manager.send_to_commands(instruction)
        print("✅ Instruction sent to #commands")
        
        # Step 2: Wait for user to send message
        print("\n📝 Now go to #commands and type: test message")
        print("⏳ Press Enter when you've sent the message...")
        input()
        
        # Step 3: Try to read messages
        print("🔍 Trying to read recent messages...")
        
        try:
            # Method 1: Try basic message reading
            messages = await api_client.get_chat_messages(config.LARK_CHAT_ID, limit=5)
            
            if messages:
                print(f"✅ Got {len(messages)} messages!")
                
                # Show message details
                for i, msg in enumerate(messages[:3]):  # Show first 3
                    print(f"\n📨 Message {i+1}:")
                    print(f"   Content: {json.dumps(msg, indent=2)[:200]}...")
                
                return True
            else:
                print("❌ Got 0 messages")
                return False
                
        except Exception as e:
            print(f"❌ LISTENING failed: {e}")
            return False

if __name__ == "__main__":
    print("🧪 Testing Bot LISTENING capability...")
    result = asyncio.run(test_listening())
    print(f"\n📊 LISTENING test: {'PASSED ✅' if result else 'FAILED ❌'}")