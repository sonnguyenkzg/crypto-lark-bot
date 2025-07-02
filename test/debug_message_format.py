#!/usr/bin/env python3
"""
Debug Lark message formatting
Test different message formats to find what works
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

    def test_message_format(self, chat_id, format_name, data):
        """Test different message formats"""
        if not self.tenant_access_token:
            return False
            
        url = f"{self.base_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            print(f"🧪 Testing {format_name}...")
            print(f"   Data: {json.dumps(data, indent=2)}")
            
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            print(f"   Response: {json.dumps(result, indent=2)}")
            
            if result.get('code') == 0:
                print(f"   ✅ {format_name} SUCCESS!")
                return True
            else:
                print(f"   ❌ {format_name} FAILED: {result.get('msg', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"   ❌ {format_name} ERROR: {e}")
            return False

    def get_chat_info(self, chat_id):
        """Get information about the chat"""
        if not self.tenant_access_token:
            return None
            
        url = f"{self.base_url}/im/v1/chats/{chat_id}"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            response = requests.get(url, headers=headers)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {})
            else:
                print(f"❌ Failed to get chat info: {result.get('msg', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"❌ Chat info error: {e}")
            return None

def main():
    print("🔍 Debug Lark Message Formats")
    print("=" * 50)
    
    bot = LarkBot()
    
    print("🔑 Getting access token...")
    if not bot.get_tenant_access_token():
        print("❌ Failed to get access token")
        return
    
    print("✅ Access token obtained\n")
    
    # Use the chat ID from previous test
    chat_id = "oc_e5a44326bca3cbe45a2166228fce16a9"
    
    print(f"📋 Using Chat ID: {chat_id}")
    
    # Check if chat exists
    print("\n🔍 Getting chat information...")
    chat_info = bot.get_chat_info(chat_id)
    if chat_info:
        print(f"✅ Chat exists: {chat_info.get('name', 'Unnamed')}")
        print(f"   Type: {chat_info.get('chat_mode', 'Unknown')}")
        print(f"   Members: {len(chat_info.get('members', []))}")
    else:
        print("❌ Chat not found or accessible")
        return
    
    print("\n" + "="*50)
    print("🧪 Testing Different Message Formats")
    print("="*50)
    
    # Test 1: Simple text format
    format1_data = {
        "receive_id": chat_id,
        "receive_id_type": "chat_id",
        "content": json.dumps({"text": "Test message 1"}),
        "msg_type": "text"
    }
    bot.test_message_format(chat_id, "Simple Text", format1_data)
    
    print("\n" + "-"*30)
    
    # Test 2: Even simpler format
    format2_data = {
        "receive_id": chat_id,
        "receive_id_type": "chat_id",
        "content": json.dumps({"text": "Hello"}),
        "msg_type": "text"
    }
    bot.test_message_format(chat_id, "Ultra Simple", format2_data)
    
    print("\n" + "-"*30)
    
    # Test 3: Different content structure
    format3_data = {
        "receive_id": chat_id,
        "receive_id_type": "chat_id",
        "msg_type": "text",
        "content": json.dumps({
            "text": "Test 3"
        })
    }
    bot.test_message_format(chat_id, "Reordered Fields", format3_data)
    
    print("\n" + "-"*30)
    
    # Test 4: Rich text format
    format4_data = {
        "receive_id": chat_id,
        "receive_id_type": "chat_id",
        "msg_type": "post",
        "content": json.dumps({
            "post": {
                "en_us": {
                    "title": "Test Title",
                    "content": [
                        [{"tag": "text", "text": "This is a test message"}]
                    ]
                }
            }
        })
    }
    bot.test_message_format(chat_id, "Rich Text Post", format4_data)

if __name__ == "__main__":
    main()