#!/usr/bin/env python3
"""
Simple Topic Test Script
Listen for commands and send test messages to each topic
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def get_token():
    """Get access token"""
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    data = {
        "app_id": os.getenv('LARK_APP_ID'),
        "app_secret": os.getenv('LARK_APP_SECRET')
    }
    response = requests.post(url, json=data)
    return response.json().get('tenant_access_token')

def send_to_topic(chat_id, thread_id, message):
    """Send message to specific topic"""
    token = get_token()
    if not token:
        print("❌ Failed to get token")
        return False
        
    url = "https://open.larksuite.com/open-apis/im/v1/messages"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    params = {'receive_id_type': 'chat_id'}  # Move to URL params
    data = {
        'receive_id': chat_id,
        'msg_type': 'text',
        'content': json.dumps({'text': message}),
        'thread_id': thread_id
    }
    
    try:
        response = requests.post(url, headers=headers, params=params, json=data)
        result = response.json()
        
        if result.get('code') == 0:
            return True
        else:
            print(f"❌ API Error: {result.get('msg', 'Unknown error')}")
            print(f"   Full response: {result}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    print("🧪 Simple Topic Test")
    
    chat_id = os.getenv('LARK_CHAT_ID')
    quickguide_id = os.getenv('LARK_TOPIC_QUICKGUIDE')
    commands_id = os.getenv('LARK_TOPIC_COMMANDS')
    dailyreport_id = os.getenv('LARK_TOPIC_DAILYREPORT')
    
    print(f"Chat ID: {chat_id}")
    print(f"Commands topic: {commands_id}")
    print(f"Daily report topic: {dailyreport_id}")
    
    while True:
        command = input("\nEnter command (test1/test2/test3/quit): ").strip()
        
        if command == 'quit':
            break
        elif command == 'test1':
            success = send_to_topic(chat_id, quickguide_id, "📖 Test message to #quickguide topic")
            print(f"Quickguide: {'✅ Sent' if success else '❌ Failed'}")
        elif command == 'test2':
            success = send_to_topic(chat_id, commands_id, "⚡ Test message to #commands topic")
            print(f"Commands: {'✅ Sent' if success else '❌ Failed'}")
        elif command == 'test3':
            success = send_to_topic(chat_id, dailyreport_id, "📊 Test message to #dailyreport topic")
            print(f"Daily report: {'✅ Sent' if success else '❌ Failed'}")
        else:
            print("Unknown command. Use: test1, test2, test3, or quit")

if __name__ == '__main__':
    main()