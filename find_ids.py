#!/usr/bin/env python3
"""
Lark Topic ID Extractor - Extract specific IDs for PROD environment
Based on your existing bot code
"""

import json
import logging
import os
import time
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

class LarkTopicExtractor:
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
    
    def get_chat_messages(self):
        """Get messages from chat"""
        token = self.get_tenant_access_token()
        if not token:
            return []
        
        url = f"{self.base_url}/im/v1/messages"
        headers = {'Authorization': f'Bearer {token}'}
        params = {
            'container_id_type': 'chat',
            'container_id': self.chat_id,
            'page_size': 50  # Get more messages to find topics
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('items', [])
            else:
                self.logger.error(f"Get messages failed: {result.get('msg')}")
                return []
        except Exception as e:
            self.logger.error(f"Get messages error: {e}")
            return []
    
    def extract_text_from_message(self, msg_data):
        """Extract text content from message"""
        try:
            # Get content from body.content (as shown in your logs)
            body = msg_data.get('body', {})
            content_str = body.get('content', '{}')
            
            if not content_str or content_str == '{}':
                return ''
            
            content = json.loads(content_str)
            
            msg_type = msg_data.get('msg_type', '')
            
            if msg_type == 'text':
                return content.get('text', '')
            elif msg_type == 'post':
                # Handle rich text posts
                title = content.get('title', '')
                content_blocks = content.get('content', [])
                
                text_parts = []
                if title:
                    text_parts.append(title)
                
                for block in content_blocks:
                    if isinstance(block, list):
                        for item in block:
                            if isinstance(item, dict) and item.get('tag') == 'text':
                                text_parts.append(item.get('text', ''))
                
                return ' '.join(text_parts)
            
            return ''
        except Exception as e:
            self.logger.debug(f"Error extracting text: {e}")
            return ''
    
    def find_topic_ids(self):
        """Find and extract topic IDs"""
        print("🔍 Extracting Lark Topic IDs for PROD environment...")
        print(f"📋 Chat ID: {self.chat_id}")
        print("=" * 70)
        
        messages = self.get_chat_messages()
        if not messages:
            print("❌ No messages found!")
            return
        
        print(f"📨 Analyzing {len(messages)} messages...")
        print("=" * 70)
        
        # Track found topics
        found_topics = {
            'QUICKGUIDE': None,
            'COMMANDS': None, 
            'DAILYREPORT': None
        }
        
        for i, msg_data in enumerate(messages):
            msg_id = msg_data.get('message_id', '')
            thread_id = msg_data.get('thread_id', '')
            parent_id = msg_data.get('parent_id', '')
            root_id = msg_data.get('root_id', '')
            msg_type = msg_data.get('msg_type', '')
            sender_type = msg_data.get('sender', {}).get('sender_type', '')
            
            # Extract text content
            text_content = self.extract_text_from_message(msg_data)
            
            if not text_content:
                continue
                
            text_lower = text_content.lower().strip()
            
            print(f"Message {i+1}: '{text_content}'")
            print(f"  ID: {msg_id}")
            print(f"  Thread ID: {thread_id}")
            print(f"  Parent ID: {parent_id}")
            print(f"  Type: {msg_type}")
            print()
            
            # Look for topic keywords
            if any(keyword in text_lower for keyword in ['#quickguide', '# quickguide', 'quickguide', 'quick guide']):
                if not found_topics['QUICKGUIDE']:
                    found_topics['QUICKGUIDE'] = {
                        'thread_id': thread_id,
                        'message_id': parent_id or root_id or msg_id,
                        'content': text_content,
                        'original_msg_id': msg_id
                    }
                    print(f"✅ Found QUICKGUIDE topic!")
            
            elif any(keyword in text_lower for keyword in ['#commands', '# commands', 'commands']):
                if not found_topics['COMMANDS']:
                    found_topics['COMMANDS'] = {
                        'thread_id': thread_id,
                        'message_id': parent_id or root_id or msg_id,
                        'content': text_content,
                        'original_msg_id': msg_id
                    }
                    print(f"✅ Found COMMANDS topic!")
            
            elif any(keyword in text_lower for keyword in ['#dailyreport', '# dailyreport', '#daily-report', '# daily-report', 'daily report', 'dailyreport']):
                if not found_topics['DAILYREPORT']:
                    found_topics['DAILYREPORT'] = {
                        'thread_id': thread_id,
                        'message_id': parent_id or root_id or msg_id,
                        'content': text_content,
                        'original_msg_id': msg_id
                    }
                    print(f"✅ Found DAILYREPORT topic!")
        
        print("=" * 70)
        print("🎯 EXTRACTION RESULTS")
        print("=" * 70)
        
        # Display results
        all_found = True
        env_vars = []
        
        for topic_name, topic_data in found_topics.items():
            if topic_data:
                print(f"✅ {topic_name}:")
                print(f"   Content: '{topic_data['content']}'")
                print(f"   Thread ID: {topic_data['thread_id']}")
                print(f"   Message ID: {topic_data['message_id']}")
                print()
                
                # Generate .env format
                env_vars.append(f"LARK_TOPIC_{topic_name}={topic_data['thread_id']}")
                env_vars.append(f"LARK_TOPIC_{topic_name}_MSG={topic_data['message_id']}")
            else:
                print(f"❌ {topic_name}: Not found")
                all_found = False
        
        print("=" * 70)
        if all_found:
            print("🎉 SUCCESS! All topic IDs found!")
            print()
            print("📋 Add these to your PROD .env file:")
            print("=" * 70)
            for env_var in env_vars:
                print(env_var)
            print("=" * 70)
        else:
            print("⚠️  Some topics not found. Make sure you have created the topic messages in your PROD chat:")
            print("   - # quickguide")
            print("   - # commands") 
            print("   - # dailyreport")
            print()
            print("📋 Found .env variables:")
            print("=" * 70)
            for env_var in env_vars:
                print(env_var)

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
        
        extractor = LarkTopicExtractor()
        extractor.find_topic_ids()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    main()