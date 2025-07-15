#!/usr/bin/env python3
"""
Simple script to find your Chat ID
"""

import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_access_token():
    """Get access token"""
    app_id = os.getenv('LARK_APP_ID')
    app_secret = os.getenv('LARK_APP_SECRET')
    
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": app_id, "app_secret": app_secret}
    
    response = requests.post(url, json=data)
    result = response.json()
    
    if result.get('code') == 0:
        return result.get('tenant_access_token')
    else:
        print(f"❌ Token error: {result.get('msg')}")
        return None

def list_chats():
    """List all chats the bot is in"""
    token = get_access_token()
    if not token:
        return
    
    url = "https://open.larksuite.com/open-apis/im/v1/chats"
    headers = {'Authorization': f'Bearer {token}'}
    params = {'page_size': 100}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result.get('code') == 0:
            chats = result.get('data', {}).get('items', [])
            
            print("🔍 FINDING YOUR CHAT ID")
            print("=" * 70)
            print(f"Found {len(chats)} chats that your bot is in:")
            print()
            
            for i, chat in enumerate(chats, 1):
                chat_id = chat.get('chat_id', '')
                name = chat.get('name', 'Unnamed Chat')
                chat_type = chat.get('chat_type', '')
                member_count = chat.get('member_count', 0)
                
                print(f"{i}. Chat: {name}")
                print(f"   Chat ID: {chat_id}")
                print(f"   Type: {chat_type}")
                print(f"   Members: {member_count}")
                print()
            
            print("=" * 70)
            print("📋 Copy the Chat ID of your production group to .env:")
            print("LARK_CHAT_ID=oc_your_chat_id_here")
            
        else:
            print(f"❌ API error: {result.get('msg')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    if not os.getenv('LARK_APP_ID') or not os.getenv('LARK_APP_SECRET'):
        print("❌ Error: Make sure LARK_APP_ID and LARK_APP_SECRET are set in .env")
        return
    
    list_chats()

if __name__ == '__main__':
    main()