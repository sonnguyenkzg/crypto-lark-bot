#!/usr/bin/env python3
"""
Simple Lark Bot Webhook - Walking Skeleton
Minimal implementation to get bot responding in groups
"""

import os
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

APP_ID = os.getenv('LARK_APP_ID')
APP_SECRET = os.getenv('LARK_APP_SECRET')

def get_tenant_access_token():
    """Get tenant access token for API calls"""
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    data = {"app_id": APP_ID, "app_secret": APP_SECRET}
    
    try:
        response = requests.post(url, json=data)
        result = response.json()
        return result.get('tenant_access_token')
    except Exception as e:
        print(f"❌ Token error: {e}")
        return None

def send_message(chat_id, text):
    """Send message to group chat"""
    token = get_tenant_access_token()
    if not token:
        return False
    
    url = "https://open.larksuite.com/open-apis/im/v1/messages"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {
        'receive_id': chat_id,
        'receive_id_type': 'chat_id',
        'msg_type': 'text',
        'content': json.dumps({'text': text})
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if result.get('code') == 0:
            print(f"✅ Message sent: {text}")
            return True
        else:
            print(f"❌ Send failed: {result.get('msg', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Send error: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Lark webhooks"""
    try:
        data = request.json
        print(f"📨 Received: {json.dumps(data, indent=2)}")
        
        # Handle URL verification challenge
        if data.get('type') == 'url_verification':
            challenge = data.get('challenge')
            print(f"🔑 URL verification challenge: {challenge}")
            return jsonify({'challenge': challenge})
        
        # Handle message events
        event_type = data.get('header', {}).get('event_type')
        if event_type == 'im.message.receive_v1':
            event = data.get('event', {})
            sender = event.get('sender', {})
            
            # Skip bot's own messages
            if sender.get('sender_type') == 'app':
                return jsonify({'code': 0})
            
            message = event.get('message', {})
            chat_id = message.get('chat_id')
            content = message.get('content', '{}')
            
            try:
                text_content = json.loads(content).get('text', '')
                print(f"💬 Message: {text_content}")
                
                # Simple response logic
                if '@_user_1' in text_content or text_content.startswith('/'):
                    response = f"🤖 Bot received: {text_content}"
                    send_message(chat_id, response)
                    
            except json.JSONDecodeError:
                print("❌ Failed to parse message content")
        
        return jsonify({'code': 0})
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "bot": "Crypto Wallet Monitor",
        "webhook": "ready"
    })

@app.route('/test-send/<chat_id>', methods=['POST'])
def test_send(chat_id):
    """Test endpoint to send messages manually"""
    message = request.json.get('message', 'Test message from webhook!')
    success = send_message(chat_id, message)
    return jsonify({'success': success})

if __name__ == '__main__':
    print("🚀 Starting Simple Lark Bot Webhook")
    print("=" * 50)
    print(f"App ID: {APP_ID}")
    print("Webhook endpoint: /webhook")
    print("Health check: /health")
    print("Test endpoint: /test-send/<chat_id>")
    print("=" * 50)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)