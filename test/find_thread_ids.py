#!/usr/bin/env python3
"""
Find Thread IDs for Topics
Shows all thread IDs and their content to identify topics
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
    print("🔍 Finding Thread IDs for Topics")
    print("=" * 50)
    
    messages = get_messages()
    threads = {}
    
    for msg in messages:
        thread_id = msg.get('thread_id', '')
        if thread_id:
            # Get message content
            body = msg.get('body', {})
            content_str = body.get('content', '{}')
            
            try:
                content = json.loads(content_str)
                # Check for text content
                if 'text' in content:
                    text = content['text']
                elif 'content' in content:
                    # Handle rich text posts
                    rich_content = content['content']
                    if rich_content and len(rich_content) > 0:
                        text = rich_content[0][0].get('text', 'Rich content')
                    else:
                        text = 'Rich post'
                else:
                    text = 'System message'
                
                if thread_id not in threads:
                    threads[thread_id] = []
                threads[thread_id].append(text)
            except:
                pass
    
    print(f"Found {len(threads)} threads:\n")
    
    for i, (thread_id, messages) in enumerate(threads.items(), 1):
        print(f"{i}. Thread ID: {thread_id}")
        print(f"   Sample messages: {messages[:3]}")  # Show first 3 messages
        print()
    
    print("Copy the Thread IDs you need for your .env file")

if __name__ == '__main__':
    main()