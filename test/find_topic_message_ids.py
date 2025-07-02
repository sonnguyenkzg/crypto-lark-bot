#!/usr/bin/env python3
"""
Find Topic Message IDs
Find the original message IDs for each topic to reply to them
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

def get_messages():
    """Get all messages from chat"""
    token = get_token()
    chat_id = os.getenv('LARK_CHAT_ID')
    
    url = "https://open.larksuite.com/open-apis/im/v1/messages"
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'container_id_type': 'chat',
        'container_id': chat_id,
        'page_size': 50
    }
    
    response = requests.get(url, headers=headers, params=params)
    result = response.json()
    
    if result.get('code') == 0:
        return result.get('data', {}).get('items', [])
    return []

def main():
    print("🔍 Finding Topic Message IDs")
    print("=" * 50)
    
    messages = get_messages()
    topic_messages = {}
    
    for msg in messages:
        message_id = msg.get('message_id', '')
        thread_id = msg.get('thread_id', '')
        
        # Get message content
        body = msg.get('body', {})
        content_str = body.get('content', '{}')
        
        try:
            content = json.loads(content_str)
            text = ''
            
            # Check for text content
            if 'text' in content:
                text = content['text']
            elif 'content' in content:
                # Handle rich text posts (topic headers)
                rich_content = content['content']
                if rich_content and len(rich_content) > 0:
                    text = rich_content[0][0].get('text', '')
            
            # Look for topic headers
            if text.startswith('#'):
                topic_name = text.strip()
                topic_messages[topic_name] = {
                    'message_id': message_id,
                    'thread_id': thread_id,
                    'text': text
                }
                
        except:
            pass
    
    print("Found topic message IDs:\n")
    
    for topic, info in topic_messages.items():
        print(f"Topic: {topic}")
        print(f"  Message ID: {info['message_id']}")
        print(f"  Thread ID: {info['thread_id']}")
        print()
    
    print("Use these Message IDs to reply directly to topics!")

if __name__ == '__main__':
    main()