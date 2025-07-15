#!/usr/bin/env python3
"""
Enhanced User ID Extractor for Open ID Authorization
This version focuses on extracting Open IDs (ou_xxx) for pre-authorization
"""

import json
import logging
import os
import time
from collections import defaultdict
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

class LarkOpenIDExtractor:
    def __init__(self):
        self.app_id = os.getenv('LARK_APP_ID')
        self.app_secret = os.getenv('LARK_APP_SECRET')
        self.chat_id = os.getenv('LARK_CHAT_ID')
        self.base_url = "https://open.larksuite.com/open-apis"
        self.tenant_access_token = None
        self.token_expires = 0
        
        # Setup basic logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def get_tenant_access_token(self):
        """Get access token"""
        if self.tenant_access_token and time.time() < self.token_expires:
            return self.tenant_access_token
            
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if result.get('code') == 0:
                self.tenant_access_token = result.get('tenant_access_token')
                self.token_expires = time.time() + 5400
                return self.tenant_access_token
            else:
                self.logger.error(f"Token error: {result.get('msg')}")
                return None
        except Exception as e:
            self.logger.error(f"Token exception: {e}")
            return None
    
    def get_chat_members(self):
        """Get chat members directly (more reliable for Open IDs)"""
        token = self.get_tenant_access_token()
        if not token:
            return []
        
        url = f"{self.base_url}/im/v1/chats/{self.chat_id}/members"
        headers = {'Authorization': f'Bearer {token}'}
        params = {
            'member_id_type': 'open_id',  # Request Open IDs specifically
            'page_size': 100
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('items', [])
            else:
                self.logger.error(f"Get chat members failed: {result.get('msg')}")
                return []
        except Exception as e:
            self.logger.error(f"Get chat members error: {e}")
            return []
    
    def get_user_info(self, open_id):
        """Get detailed user information"""
        token = self.get_tenant_access_token()
        if not token:
            return None
        
        url = f"{self.base_url}/contact/v3/users/{open_id}"
        headers = {'Authorization': f'Bearer {token}'}
        params = {'user_id_type': 'open_id'}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('user', {})
            else:
                self.logger.debug(f"Get user info failed for {open_id}: {result.get('msg')}")
                return None
        except Exception as e:
            self.logger.debug(f"Get user info error for {open_id}: {e}")
            return None
    
    def extract_open_ids_from_chat(self):
        """Extract Open IDs from chat members (most reliable method)"""
        print("👥 Extracting Open IDs from Chat Members...")
        print(f"📋 Chat ID: {self.chat_id}")
        print("=" * 70)
        
        members = self.get_chat_members()
        if not members:
            print("❌ No chat members found!")
            return []
        
        print(f"👫 Found {len(members)} chat members")
        print("=" * 70)
        
        open_ids = []
        human_users = []
        
        for i, member in enumerate(members):
            member_id = member.get('member_id', '')
            member_type = member.get('member_type', '')
            
            print(f"Member {i+1}:")
            print(f"  ID: {member_id}")
            print(f"  Type: {member_type}")
            
            # Skip bots and apps
            if member_type != 'user':
                print(f"  ⏭️ Skipping (not a user)")
                print()
                continue
            
            # Get user details
            user_info = self.get_user_info(member_id)
            if user_info:
                name = user_info.get('name', 'Unknown')
                email = user_info.get('enterprise_email', 'No email')
                status = user_info.get('status', {}).get('is_activated', False)
                
                print(f"  👤 Name: {name}")
                print(f"  📧 Email: {email}")
                print(f"  ✅ Active: {status}")
                
                if status:  # Only include active users
                    open_ids.append(member_id)
                    human_users.append({
                        'open_id': member_id,
                        'name': name,
                        'email': email
                    })
                else:
                    print(f"  ⏭️ Skipping (inactive user)")
            else:
                print(f"  ⚠️ Could not get user details")
                # Still include if it looks like a valid Open ID
                if member_id.startswith('ou_'):
                    open_ids.append(member_id)
                    human_users.append({
                        'open_id': member_id,
                        'name': 'Unknown',
                        'email': 'Unknown'
                    })
            
            print()
        
        return human_users
    
    def generate_authorization_config(self):
        """Generate complete authorization configuration"""
        print("🔐 GENERATING OPEN ID AUTHORIZATION CONFIG")
        print("=" * 70)
        
        # Method 1: Get from chat members (most reliable)
        human_users = self.extract_open_ids_from_chat()
        
        if not human_users:
            print("❌ No users found for authorization!")
            return
        
        print("👥 FOUND USERS FOR AUTHORIZATION:")
        print("-" * 70)
        
        for i, user in enumerate(human_users, 1):
            print(f"{i}. {user['name']} ({user['email']})")
            print(f"   Open ID: {user['open_id']}")
            print()
        
        print("=" * 70)
        print("📋 ENVIRONMENT VARIABLE CONFIGURATION")
        print("=" * 70)
        
        open_ids = [user['open_id'] for user in human_users]
        
        print("Add this to your .env file:")
        print()
        
        if len(open_ids) == 1:
            print(f"# Single user authorization")
            print(f"LARK_AUTHORIZED_USERS={open_ids[0]}")
        else:
            print(f"# Multiple users authorization ({len(open_ids)} users)")
            print(f"LARK_AUTHORIZED_USERS={','.join(open_ids)}")
            
            print()
            print("# Or for individual testing:")
            for i, user in enumerate(human_users, 1):
                print(f"# User {i} ({user['name']}): LARK_AUTHORIZED_USERS={user['open_id']}")
        
        print()
        print("=" * 70)
        print("🎯 AUTHORIZATION MODES:")
        print("=" * 70)
        print("1. DEVELOPMENT MODE:")
        print("   Leave LARK_AUTHORIZED_USERS empty or unset")
        print("   → Allows ALL users (no restrictions)")
        print()
        print("2. PRODUCTION MODE:")
        print("   Set LARK_AUTHORIZED_USERS to specific Open IDs")
        print("   → Only allows specified users")
        print()
        print("3. TESTING MODE:")
        print("   Set to single Open ID for testing")
        print("   → Allows only that specific user")
        
        print()
        print("=" * 70)
        print("💡 NEXT STEPS:")
        print("=" * 70)
        print("1. Copy the LARK_AUTHORIZED_USERS line to your .env file")
        print("2. Restart your bot")
        print("3. Users can now be authorized WITHOUT needing to send commands first!")
        print("4. Add new users by getting their Open ID and adding to the list")
        print()
        print("🔍 To get Open ID for new users:")
        print("   - Add them to the chat")
        print("   - Run this script again")
        print("   - Their Open ID will appear in the list")

def main():
    """Main function"""
    try:
        if not os.getenv('LARK_APP_ID') or not os.getenv('LARK_APP_SECRET') or not os.getenv('LARK_CHAT_ID'):
            print("❌ Error: Missing required environment variables!")
            print("   Make sure you have set:")
            print("   - LARK_APP_ID")
            print("   - LARK_APP_SECRET") 
            print("   - LARK_CHAT_ID")
            return
        
        extractor = LarkOpenIDExtractor()
        extractor.generate_authorization_config()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()