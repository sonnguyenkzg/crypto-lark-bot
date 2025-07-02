#!/usr/bin/env python3
"""
Topic Reply Test
Reply to original topic messages to post in topics
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Original topic message IDs
TOPIC_MESSAGE_IDS = {
    'dailyreport': 'om_x100b490ea8b938bc0ef22c9cbabf87f',
    'commands': 'om_x100b490ea9f6c0840d00a4878d54ee6',
    'quickguide': 'om_x100b497f22eb68880d61cd8f61a55c8'
}

def get_token():
    """Get access token"""
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    data = {
        "app_id": os.getenv('LARK_APP_ID'),
        "app_secret": os.getenv('LARK_APP_SECRET')
    }
    response = requests.post(url, json=data)
    return response.json().get('tenant_access_token')

def reply_to_topic(message_id, reply_text):
    """Reply to a specific message (topic)"""
    token = get_token()
    if not token:
        print("❌ Failed to get token")
        return False
        
    url = f"https://open.larksuite.com/open-apis/im/v1/messages/{message_id}/reply"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    data = {
        'msg_type': 'text',
        'content': json.dumps({'text': reply_text})
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
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
    print("🧪 Topic Reply Test")
    print("Testing replies to original topic messages")
    print()
    
    while True:
        command = input("Enter command (test1/test2/test3/quit): ").strip()
        
        if command == 'quit':
            break
        elif command == 'test1':
            success = reply_to_topic(TOPIC_MESSAGE_IDS['quickguide'], "📖 Test reply to #quickguide topic")
            print(f"Quickguide: {'✅ Sent' if success else '❌ Failed'}")
        elif command == 'test2':
            success = reply_to_topic(TOPIC_MESSAGE_IDS['commands'], "⚡ Test reply to #commands topic")
            print(f"Commands: {'✅ Sent' if success else '❌ Failed'}")
        elif command == 'test3':
            success = reply_to_topic(TOPIC_MESSAGE_IDS['dailyreport'], "📊 Test reply to #dailyreport topic")
            print(f"Daily report: {'✅ Sent' if success else '❌ Failed'}")
        else:
            print("Unknown command. Use: test1, test2, test3, or quit")

if __name__ == '__main__':
    main()