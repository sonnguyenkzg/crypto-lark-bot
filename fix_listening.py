import asyncio
import sys
import json
sys.path.append('.')

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager

async def try_different_listening_methods():
    """Try different ways to read messages."""
    config = Config
    
    async with LarkAPIClient(config.LARK_APP_ID, config.LARK_APP_SECRET) as api_client:
        topic_manager = LarkTopicManager(api_client, config)
        
        print("🔧 Trying different LISTENING methods...")
        
        # Send test instruction
        await topic_manager.send_to_commands("🔧 Testing different listening methods...")
        
        # Get access token for manual API calls
        await api_client.get_access_token()
        
        # Try different API endpoints
        methods = [
            {
                "name": "Method 1: No container params",
                "url": f"{api_client.base_url}/im/v1/messages",
                "params": {"page_size": 5}
            },
            {
                "name": "Method 2: Use open_chat_id",
                "url": f"{api_client.base_url}/im/v1/messages", 
                "params": {
                    "container_id": config.LARK_CHAT_ID,
                    "container_id_type": "open_chat_id",
                    "page_size": 5
                }
            },
            {
                "name": "Method 3: Chat history endpoint",
                "url": f"{api_client.base_url}/im/v1/chats/{config.LARK_CHAT_ID}/messages",
                "params": {"page_size": 5}
            },
            {
                "name": "Method 4: Different message endpoint",
                "url": f"{api_client.base_url}/im/v1/messages",
                "params": {
                    "receive_id": config.LARK_CHAT_ID,
                    "receive_id_type": "chat_id",
                    "page_size": 5
                }
            }
        ]
        
        headers = {
            "Authorization": f"Bearer {api_client.access_token}",
            "Content-Type": "application/json"
        }
        
        for method in methods:
            print(f"\n🧪 {method['name']}")
            try:
                async with api_client.session.get(
                    method['url'], 
                    headers=headers, 
                    params=method['params']
                ) as response:
                    
                    print(f"   Status: {response.status}")
                    text = await response.text()
                    
                    if response.status == 200:
                        data = json.loads(text)
                        if data.get("code") == 0:
                            messages = data.get("data", {}).get("items", [])
                            print(f"   ✅ SUCCESS: Got {len(messages)} messages")
                            
                            if messages:
                                # Show first message
                                first_msg = messages[0]
                                content = first_msg.get("body", {}).get("content", "No content")
                                sender = first_msg.get("sender", {})
                                print(f"   📨 Latest: {content[:50]}...")
                                print(f"   👤 From: {sender}")
                                return True
                        else:
                            print(f"   ❌ API Error: {data.get('msg', 'Unknown')}")
                    else:
                        print(f"   ❌ HTTP Error: {text[:100]}...")
                        
            except Exception as e:
                print(f"   💥 Exception: {e}")
        
        print("\n❌ All listening methods failed")
        return False

if __name__ == "__main__":
    print("🔧 Trying to fix LISTENING...")
    result = asyncio.run(try_different_listening_methods())
    
    if result:
        print("\n🎉 Found a working LISTENING method!")
    else:
        print("\n💡 LISTENING needs webhook approach")
        print("   We can still build the bot with manual triggers")