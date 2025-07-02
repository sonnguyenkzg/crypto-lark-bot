#!/usr/bin/env python3
"""
Get Lark Chat ID
Find the chat ID for your Lark groups
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def get_tenant_access_token():
    """Get access token"""
    app_id = os.getenv('LARK_APP_ID')
    app_secret = os.getenv('LARK_APP_SECRET')
    
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": app_id, "app_secret": app_secret}
    
    try:
        response = requests.post(url, json=data)
        result = response.json()
        return result.get('tenant_access_token')
    except Exception as e:
        print(f"❌ Token error: {e}")
        return None

def get_bot_chats():
    """Get all chats the bot is member of"""
    token = get_tenant_access_token()
    if not token:
        return []
    
    url = "https://open.larksuite.com/open-apis/im/v1/chats"
    headers = {'Authorization': f'Bearer {token}'}
    params = {'page_size': 50}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get('code') == 0:
            return result.get('data', {}).get('items', [])
        else:
            print(f"❌ API error: {result.get('msg')}")
            return []
    except Exception as e:
        print(f"❌ Request error: {e}")
        return []

def main():
    print("🔍 Finding Lark Chat IDs")
    print("=" * 40)
    
    chats = get_bot_chats()
    
    if not chats:
        print("❌ No chats found or API error")
        print("\n💡 Make sure:")
        print("   1. Bot is added to your test group")
        print("   2. LARK_APP_ID and LARK_APP_SECRET are correct")
        return
    
    print(f"✅ Found {len(chats)} chat(s) where bot is member:")
    print()
    
    for i, chat in enumerate(chats, 1):
        chat_id = chat.get('chat_id', 'Unknown')
        name = chat.get('name', 'Unnamed Chat')
        chat_mode = chat.get('chat_mode', 'unknown')
        member_count = len(chat.get('members', []))
        
        print(f"{i}. **{name}**")
        print(f"   Chat ID: {chat_id}")
        print(f"   Type: {chat_mode}")
        print(f"   Members: {member_count}")
        print()
    
    print("📝 Copy the Chat ID for your 'Crypto Bot Test' group")
    print("   Add it to .env as: LARK_CHAT_ID=your_chat_id_here")

if __name__ == '__main__':
    main()