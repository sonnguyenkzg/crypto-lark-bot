#!/usr/bin/env python3
"""
Final Lark Crypto Bot - Walking Skeleton Complete
Topic-aware bot with command handling and daily reports
"""

import os
import json
import requests
import asyncio
import logging
import time
import signal
import sys
from dotenv import load_dotenv

load_dotenv()

# Topic Message IDs (from your topic headers)
TOPIC_MESSAGE_IDS = {
    'dailyreport': 'om_x100b490ea8b938bc0ef22c9cbabf87f',
    'commands': 'om_x100b490ea9f6c0840d00a4878d54ee6',
    'quickguide': 'om_x100b497f22eb68880d61cd8f61a55c8'
}

# Commands topic thread ID (only listen here)
COMMANDS_THREAD_ID = "omt_1b0626ba92cd577c"

class LarkBotConfig:
    LARK_APP_ID = os.getenv('LARK_APP_ID')
    LARK_APP_SECRET = os.getenv('LARK_APP_SECRET')
    LARK_CHAT_ID = os.getenv('LARK_CHAT_ID')
    AUTHORIZED_USERS = os.getenv('LARK_AUTHORIZED_USERS', '').split(',')
    AUTHORIZED_USERS = [user.strip() for user in AUTHORIZED_USERS if user.strip()]
    
    @classmethod
    def setup_logging(cls):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

class LarkAPI:
    def __init__(self):
        self.app_id = LarkBotConfig.LARK_APP_ID
        self.app_secret = LarkBotConfig.LARK_APP_SECRET
        self.base_url = "https://open.larksuite.com/open-apis"
        self.tenant_access_token = None
        self.token_expires = 0
        self.logger = logging.getLogger(__name__)
    
    def get_tenant_access_token(self):
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
        except Exception as e:
            self.logger.error(f"Token error: {e}")
        return None
    
    def reply_to_topic(self, topic_name, message):
        """Reply to a topic (dailyreport, commands, quickguide)"""
        if topic_name not in TOPIC_MESSAGE_IDS:
            return False
            
        token = self.get_tenant_access_token()
        if not token:
            return False
            
        message_id = TOPIC_MESSAGE_IDS[topic_name]
        url = f"{self.base_url}/im/v1/messages/{message_id}/reply"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        data = {
            'msg_type': 'text',
            'content': json.dumps({'text': message})
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            return result.get('code') == 0
        except Exception as e:
            self.logger.error(f"Reply error: {e}")
            return False
    
    def get_chat_messages(self, chat_id):
        token = self.get_tenant_access_token()
        if not token:
            return []
        
        url = f"{self.base_url}/im/v1/messages"
        headers = {'Authorization': f'Bearer {token}'}
        params = {
            'container_id_type': 'chat',
            'container_id': chat_id,
            'page_size': 20
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data', {}).get('items', [])
        except Exception as e:
            self.logger.error(f"Get messages error: {e}")
        return []

class LarkMessage:
    def __init__(self, message_data, api):
        self.data = message_data
        self.api = api
        
    @property
    def text(self):
        try:
            body = self.data.get('body', {})
            content_str = body.get('content', '{}')
            content = json.loads(content_str)
            return content.get('text', '')
        except:
            return ''
    
    @property
    def thread_id(self):
        return self.data.get('thread_id', '')
    
    @property
    def user_id(self):
        return self.data.get('sender', {}).get('id', '')
    
    @property
    def user_name(self):
        return self.data.get('sender', {}).get('id', 'User')
    
    def is_bot_message(self):
        return self.data.get('sender', {}).get('sender_type') == 'app'
    
    def is_in_commands_topic(self):
        return self.thread_id == COMMANDS_THREAD_ID
    
    def is_command(self):
        if not self.is_in_commands_topic():
            return False
        text = self.text.strip()
        return text.startswith('/') or '@_user_1' in text

class CommandHandler:
    def __init__(self, api):
        self.api = api
        self.logger = logging.getLogger(__name__)
    
    def check_authorization(self, message):
        user_id = message.user_id
        authorized_users = LarkBotConfig.AUTHORIZED_USERS
        
        if not authorized_users or user_id in authorized_users:
            return True
        
        self.api.reply_to_topic('commands', "❌ You are not authorized to use this bot.")
        return False
    
    def parse_command(self, text):
        text = text.strip()
        if '@_user_1' in text:
            text = text.replace('@_user_1', '').strip()
        
        if text.startswith('/'):
            parts = text.split()
            command = parts[0][1:]
            args = parts[1:] if len(parts) > 1 else []
            return command, args
        return None, []
    
    async def handle_command(self, message):
        if not self.check_authorization(message):
            return
        
        command, args = self.parse_command(message.text)
        
        if command == 'help':
            response = """📖 **Available Commands**

**Wallet Management:**
• /help - Show this help message
• /check - Check wallet balances
• /list - Show configured wallets

**Examples:**
• /check - Check all wallets
• @Crypto Wallet Monitor Test /help

💰 **Daily Reports:** Sent automatically to #dailyreport at 12:00 AM GMT+7"""
            
            self.api.reply_to_topic('commands', response)
            
        elif command == 'check':
            response = """💰 **Wallet Balance Check**

⏰ **Time:** 2025-07-02 12:00 GMT+7

• **KZP Store 1:** 50,000.00 USDT
• **KZP Store 2:** 25,000.00 USDT  
• **KZP Office:** 10,000.00 USDT

📊 **Total:** 125,000.00 USDT

*Note: This is test data. Real wallet integration coming next.*"""
            
            self.api.reply_to_topic('commands', response)
            
        elif command == 'list':
            response = """📋 **Configured Wallets**

Currently no wallets configured.

Use /add "company" "wallet_name" "TRC20_address" to add wallets.

**Coming soon:** Full wallet management like Telegram bot."""
            
            self.api.reply_to_topic('commands', response)
            
        else:
            response = f"""❌ Unknown command: `/{command}`

💡 **Available commands:**
• /help - Show all commands
• /check - Check balances  
• /list - Show wallets

Use /help for detailed information."""
            
            self.api.reply_to_topic('commands', response)

class LarkBot:
    def __init__(self):
        self.api = LarkAPI()
        self.handler = CommandHandler(self.api)
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.last_message_time = int(time.time() * 1000)
    
    async def handle_message(self, message):
        if message.is_bot_message():
            return
        
        if message.is_command():
            try:
                await self.handler.handle_command(message)
            except Exception as e:
                self.logger.error(f"Command error: {e}")
    
    def send_daily_report(self):
        """Send daily report to #dailyreport topic"""
        report = """💰 **Daily Crypto Balance Report**

⏰ **Time:** 2025-07-02 00:00 GMT+7

• **KZP Store 1:** 50,000.00 USDT
• **KZP Store 2:** 25,000.00 USDT
• **KZP Office:** 10,000.00 USDT

📊 **Total:** 125,000.00 USDT

*Automated daily report - Walking skeleton complete!*"""
        
        success = self.api.reply_to_topic('dailyreport', report)
        if success:
            self.logger.info("✅ Daily report sent to #dailyreport")
        else:
            self.logger.error("❌ Failed to send daily report")
    
    async def poll_messages(self, chat_id):
        self.logger.info(f"Starting polling for commands in #commands topic")
        
        while self.running:
            try:
                messages = self.api.get_chat_messages(chat_id)
                
                for msg_data in messages:
                    msg_time = int(msg_data.get('create_time', 0))
                    if msg_time > self.last_message_time:
                        self.last_message_time = msg_time
                        
                        message = LarkMessage(msg_data, self.api)
                        if message.is_in_commands_topic():
                            self.logger.info(f"📨 Command message: '{message.text}'")
                            await self.handle_message(message)
                
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Polling error: {e}")
                await asyncio.sleep(10)
    
    def run_polling(self, chat_id=None):
        chat_id = chat_id or LarkBotConfig.LARK_CHAT_ID
        self.running = True
        
        def signal_handler(signum, frame):
            self.logger.info("Shutting down...")
            self.running = False
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        asyncio.run(self.poll_messages(chat_id))

def main():
    print("🤖 Starting Lark Crypto Wallet Monitor Bot - FINAL")
    
    LarkBotConfig.validate_config = lambda: None  # Skip validation for now
    logger = LarkBotConfig.setup_logging()
    
    bot = LarkBot()
    
    logger.info("=== Walking Skeleton Complete ===")
    logger.info("✅ Topic-aware messaging")
    logger.info("✅ Command handling in #commands")
    logger.info("✅ Daily reports to #dailyreport")
    logger.info("✅ Ready for crypto wallet integration")
    logger.info("===================================")
    
    # Send startup test message to #dailyreport
    bot.send_daily_report()
    
    # Start polling for commands
    bot.run_polling()

if __name__ == '__main__':
    main()