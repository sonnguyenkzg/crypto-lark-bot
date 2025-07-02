#!/usr/bin/env python3
"""
Basic Lark Bot Connection Test
Test script to verify Lark bot credentials and API connectivity
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
                print("✅ Successfully obtained tenant access token")
                return True
            else:
                print(f"❌ Failed to get token: {result.get('msg', 'Unknown error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return False
    
    def test_bot_info(self):
        """Test bot information API call"""
        if not self.tenant_access_token:
            print("❌ No access token available")
            return False
            
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
                bot_info = result.get('bot', {})
                print(f"✅ Bot Info Retrieved:")
                print(f"   Bot Name: {bot_info.get('app_name', 'N/A')}")
                print(f"   Bot ID: {bot_info.get('open_id', 'N/A')}")
                print(f"   Status: {bot_info.get('status', 'N/A')}")
                return True
            else:
                print(f"❌ Failed to get bot info: {result.get('msg', 'Unknown error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return False

def main():
    print("🤖 Lark Bot Connection Test")
    print("=" * 40)
    
    # Check environment variables
    app_id = os.getenv('LARK_APP_ID')
    app_secret = os.getenv('LARK_APP_SECRET')
    
    if not app_id or not app_secret:
        print("❌ Missing credentials in .env file")
        print("   Please check LARK_APP_ID and LARK_APP_SECRET")
        return
    
    print(f"📱 App ID: {app_id}")
    print(f"🔑 App Secret: {'*' * (len(app_secret) - 4) + app_secret[-4:]}")
    print()
    
    # Initialize bot
    bot = LarkBot()
    
    # Test 1: Get access token
    print("🔑 Testing access token...")
    if not bot.get_tenant_access_token():
        print("❌ Connection test failed at token stage")
        return
    
    print()
    
    # Test 2: Get bot info
    print("🤖 Testing bot info API...")
    if bot.test_bot_info():
        print("\n🎉 All tests passed! Bot is ready for development.")
    else:
        print("\n❌ Bot info test failed")

if __name__ == "__main__":
    main()