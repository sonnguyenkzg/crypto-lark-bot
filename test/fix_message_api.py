#!/usr/bin/env python3
"""
Fix Lark message API with correct parameters
Try different receive_id_type values and API versions
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LarkBot:
    def __init__(self):
        self.app_id = os.getenv('LARK_APP_ID')
        self.app_secret = os.getenv('LARK_APP_SECRET')
        self.base_url = "https://open.larksuite.com/open-apis"
        self.tenant_access_token = None
        
    def get_tenant_access_token(self):
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                self.tenant_access_token = result.get('tenant_access_token')
                return True
            return False
        except Exception as e:
            print(f"❌ Token error: {e}")
            return False

    def test_different_receive_types(self, chat_id):
        """Test different receive_id_type values"""
        if not self.tenant_access_token:
            return False
            
        url = f"{self.base_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # Different receive_id_type options to try
        receive_types = [
            "chat_id",      # What we've been using
            "group_id",     # Maybe it's called group_id
            "room_id",      # Alternative name
            "conversation_id", # Another possibility
            "channel_id"    # Yet another option
        ]
        
        for receive_type in receive_types:
            data = {
                "receive_id": chat_id,
                "receive_id_type": receive_type,
                "msg_type": "text",
                "content": json.dumps({"text": f"Testing with {receive_type}"})
            }
            
            try:
                print(f"🧪 Testing receive_id_type: {receive_type}")
                response = requests.post(url, headers=headers, json=data)
                result = response.json()
                
                if result.get('code') == 0:
                    print(f"   ✅ SUCCESS with {receive_type}!")
                    return receive_type
                else:
                    print(f"   ❌ Failed: {result.get('msg', 'Unknown error')}")
                    if 'field_violations' in result.get('error', {}):
                        violations = result['error']['field_violations']
                        for violation in violations:
                            print(f"      Field: {violation.get('field')}")
                            print(f"      Error: {violation.get('description')}")
            except Exception as e:
                print(f"   ❌ Exception: {e}")
        
        return None

    def test_webhook_approach(self):
        """Set up webhook to receive messages instead"""
        print("🔗 Alternative: Setting up webhook approach...")
        print("   This would let users send commands TO the bot")
        print("   Then we respond to those messages")
        
        # For now, just show the webhook URL format
        webhook_url = "https://your-server.com/webhook"
        print(f"   Webhook URL needed: {webhook_url}")
        print("   We can set this up if direct messaging doesn't work")

def main():
    print("🔧 Fix Lark Message API")
    print("=" * 50)
    
    bot = LarkBot()
    
    print("🔑 Getting access token...")
    if not bot.get_tenant_access_token():
        print("❌ Failed to get access token")
        return
    
    print("✅ Access token obtained\n")
    
    chat_id = "oc_e5a44326bca3cbe45a2166228fce16a9"
    print(f"📋 Testing with Chat ID: {chat_id}\n")
    
    # Test different receive_id_type values
    working_type = bot.test_different_receive_types(chat_id)
    
    if working_type:
        print(f"\n🎉 Found working receive_id_type: {working_type}")
        print("✅ We can now send messages!")
        
        # Update .env with working configuration
        print(f"\n📝 Add to .env file:")
        print(f"LARK_CHAT_ID={chat_id}")
        print(f"LARK_RECEIVE_TYPE={working_type}")
    else:
        print("\n❌ None of the receive_id_type values worked")
        print("🔄 Let's try the webhook approach instead...")
        bot.test_webhook_approach()
        
        print("\n💡 Alternative: We might need to:")
        print("   1. Add the bot to the group manually first")
        print("   2. Use a different API endpoint")
        print("   3. Set up webhooks for bi-directional communication")

if __name__ == "__main__":
    main()