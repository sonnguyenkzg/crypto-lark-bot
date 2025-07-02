#!/usr/bin/env python3
"""
Get user information from Lark
Find your user Open ID for testing
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

    def search_user_by_email(self, email):
        """Search for user by email"""
        if not self.tenant_access_token:
            return None
            
        url = f"{self.base_url}/contact/v3/users/batch_get_id"
        
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        data = {
            "emails": [email]
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 0:
                user_list = result.get('data', {}).get('user_list', [])
                if user_list:
                    return user_list[0]
                else:
                    print(f"❌ No user found with email: {email}")
                    return None
            else:
                print(f"❌ Failed to search user: {result.get('msg', 'Unknown error')}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None

    def get_user_info(self, user_id):
        """Get detailed user information"""
        if not self.tenant_access_token:
            return None
            
        url = f"{self.base_url}/contact/v3/users/{user_id}"
        
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('user', {})
            else:
                print(f"❌ Failed to get user info: {result.get('msg', 'Unknown error')}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None

def main():
    print("👤 Get Lark User ID")
    print("=" * 40)
    
    # Initialize bot
    bot = LarkBot()
    
    # Get access token
    print("🔑 Getting access token...")
    if not bot.get_tenant_access_token():
        print("❌ Failed to get access token")
        return
    
    print("✅ Access token obtained")
    print()
    
    # Ask for email
    email = input("📧 Enter your Lark email address: ").strip()
    
    if not email:
        print("❌ Email is required")
        return
    
    print(f"🔍 Searching for user with email: {email}")
    
    # Search for user
    user_basic = bot.search_user_by_email(email)
    
    if not user_basic:
        print("❌ User not found")
        print("💡 Make sure you're using the same email as your Lark account")
        return
    
    user_id = user_basic.get('user_id')
    open_id = user_basic.get('open_id')
    
    print(f"✅ User found!")
    print(f"   User ID: {user_id}")
    print(f"   Open ID: {open_id}")
    
    # Get detailed user info
    print("\n🔍 Getting detailed user info...")
    user_detail = bot.get_user_info(user_id)
    
    if user_detail:
        print(f"   Name: {user_detail.get('name', 'N/A')}")
        print(f"   Email: {user_detail.get('email', 'N/A')}")
        print(f"   Status: {user_detail.get('status', {}).get('is_activated', 'N/A')}")
    
    print("\n📝 Add this to your .env file:")
    print(f"LARK_TEST_USER_ID={open_id}")

if __name__ == "__main__":
    main()