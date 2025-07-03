import asyncio
import sys
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def test_sending():
    """Test if bot can send messages to each topic."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        
        print("🧪 Testing SENDING to all topics...")
        
        # Test 1: Send to commands
        success1 = await topic_manager.send_to_commands("✅ Test 1: Bot can send to #commands")
        print(f"Commands topic: {'✅ SUCCESS' if success1 else '❌ FAILED'}")
        
        # Test 2: Send to daily report  
        success2 = await topic_manager.send_to_dailyreport("✅ Test 2: Bot can send to #dailyreport")
        print(f"Daily report topic: {'✅ SUCCESS' if success2 else '❌ FAILED'}")
        
        # Test 3: Send to quickguide
        success3 = await topic_manager.send_to_quickguide("✅ Test 3: Bot can send to #quickguide")
        print(f"Quickguide topic: {'✅ SUCCESS' if success3 else '❌ FAILED'}")
        
        if success1 and success2 and success3:
            print("\n🎉 SENDING works perfectly!")
            return True
        else:
            print("\n❌ SENDING has issues")
            return False

if __name__ == "__main__":
    print("🧪 Testing Bot SENDING capability...")
    result = asyncio.run(test_sending())
    print(f"\n📊 SENDING test: {'PASSED ✅' if result else 'FAILED ❌'}")