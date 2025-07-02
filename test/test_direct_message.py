#!/usr/bin/env python3
"""
Test sending direct messages to yourself
Try different methods to reach your user
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

    def send_test_message_to_email(self, email, message):
        """Try sending message using email as receive_id"""
        if not self.tenant_access_token:
            return False
            
        url = f"{self.base_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "receive_id": email,
            "receive_id_type": "email",
            "content": json.dumps({"text": message}),
            "msg_type": "text"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                print(f"✅ Message sent via email!")
                return True
            else:
                print(f"❌ Email method failed: {result.get('msg', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Email request failed: {e}")
            return False

    def create_group_and_get_id(self, group_name="Test Crypto Bot"):
        """Create a group and return its chat_id"""
        if not self.tenant_access_token:
            return None
            
        url = f"{self.base_url}/im/v1/chats"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "name": group_name,
            "chat_mode": "group",
            "chat_type": "private"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                chat_id = result.get('data', {}).get('chat_id')
                print(f"✅ Group created with ID: {chat_id}")
                return chat_id
            else:
                print(f"❌ Group creation failed: {result.get('msg', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"❌ Group creation error: {e}")
            return None

    def send_message_to_chat(self, chat_id, message):
        """Send message to a specific chat/group"""
        if not self.tenant_access_token:
            return False
            
        url = f"{self.base_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "receive_id": chat_id,
            "receive_id_type": "chat_id",
            "content": json.dumps({
                "text": message
            }),
            "msg_type": "text"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                print(f"✅ Message sent to chat!")
                return True
            else:
                print(f"❌ Chat message failed: {result.get('msg', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Chat message error: {e}")
            return False

def main():
    print("🧪 Lark Bot Direct Message Test")
    print("=" * 50)
    
    bot = LarkBot()
    
    print("🔑 Getting access token...")
    if not bot.get_tenant_access_token():
        print("❌ Failed to get access token")
        return
    
    print("✅ Access token obtained\n")
    
    # Test 1: Try sending via email
    print("📧 Test 1: Sending message via email...")
    email = "quangson3591@gmail.com"
    test_message = "🤖 Hello! This is a test message from your Crypto Wallet Monitor bot!"
    
    if bot.send_test_message_to_email(email, test_message):
        print("✅ Email method worked!")
    else:
        print("❌ Email method failed")
    
    print("\n" + "="*50)
    
    # Test 2: Create a group and send message there
    print("👥 Test 2: Creating test group...")
    chat_id = bot.create_group_and_get_id("Crypto Bot API Test")
    
    if chat_id:
        print(f"📝 Group created! Chat ID: {chat_id}")
        print("💬 Sending test message to group...")
        
        group_message = "🎉 Success! Bot can send messages to groups.\n\nNext steps:\n• Add crypto wallet monitoring\n• Set up daily reports\n• Handle commands"
        
        if bot.send_message_to_chat(chat_id, group_message):
            print("✅ Group message sent!")
            print(f"\n📋 Save this Chat ID for testing: {chat_id}")
            print("💡 Check your Lark app - you should see the new group and message!")
        else:
            print("❌ Group message failed")
    
    print("\n🎯 Next: Check your Lark app for the test group and messages!")

if __name__ == "__main__":
    main()