#!/usr/bin/env python3
"""
Test sending messages via Lark Bot API
Send a test message to verify bot functionality
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
        """Get tenant access token for API calls"""
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 0:
                self.tenant_access_token = result.get('tenant_access_token')
                return True
            else:
                print(f"❌ Failed to get token: {result.get('msg', 'Unknown error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return False
    
    def get_bot_info(self):
        """Get bot information including open_id"""
        if not self.tenant_access_token:
            return None
            
        url = f"{self.base_url}/bot/v3/info"
        
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('bot', {})
            else:
                print(f"❌ Failed to get bot info: {result.get('msg', 'Unknown error')}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None

    def send_message_to_user(self, user_id, message):
        """Send a direct message to a specific user"""
        if not self.tenant_access_token:
            print("❌ No access token available")
            return False
            
        url = f"{self.base_url}/im/v1/messages"
        
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "receive_id": user_id,
            "receive_id_type": "open_id",
            "content": json.dumps({
                "text": message
            }),
            "msg_type": "text"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 0:
                print(f"✅ Message sent successfully!")
                print(f"   Message ID: {result.get('data', {}).get('message_id', 'N/A')}")
                return True
            else:
                print(f"❌ Failed to send message: {result.get('msg', 'Unknown error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return False

def main():
    print("🤖 Lark Bot Message Test")
    print("=" * 40)
    
    # Initialize bot
    bot = LarkBot()
    
    # Get access token
    print("🔑 Getting access token...")
    if not bot.get_tenant_access_token():
        print("❌ Failed to get access token")
        return
    
    # Get bot info to confirm it's working
    print("🤖 Getting bot info...")
    bot_info = bot.get_bot_info()
    if not bot_info:
        print("❌ Failed to get bot info")
        return
    
    print(f"✅ Bot ready: {bot_info.get('app_name', 'N/A')}")
    print(f"   Bot Open ID: {bot_info.get('open_id', 'N/A')}")
    print()
    
    # For testing, we'll need your user open_id
    # This is a placeholder - we'll get this from Lark
    print("📝 To test messaging, we need your Lark user Open ID")
    print("   We can get this by having you send a message to the bot first")
    print("   Or by using Lark's user search API")
    print()
    print("🎯 Next step: Set up webhook to receive messages and get your user ID")

if __name__ == "__main__":
    main()