#!/usr/bin/env python3
"""
Lark API Client Module
Handles all Lark API interactions: authentication, messaging, polling
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LarkAPIClient:
    """
    Lark API client for bot operations.
    Handles authentication, messaging, and polling.
    """
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.token_expires_at = None
        self.base_url = "https://open.larksuite.com/open-apis"
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        await self.get_access_token()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def get_access_token(self) -> str:
        """
        Get or refresh access token for Lark API.
        Returns the current valid access token.
        """
        # Check if current token is still valid
        if self.access_token and self.token_expires_at:
            if datetime.now() < self.token_expires_at - timedelta(minutes=5):
                return self.access_token
        
        # Get new token
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        self.access_token = data["tenant_access_token"]
                        # Token expires in 2 hours, store expiry time
                        self.token_expires_at = datetime.now() + timedelta(seconds=data["expire"])
                        logger.info("✅ Lark access token obtained successfully")
                        return self.access_token
                    else:
                        raise Exception(f"Lark API error: {data.get('msg', 'Unknown error')}")
                else:
                    raise Exception(f"HTTP error: {response.status}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to get Lark access token: {e}")
            raise
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make authenticated request to Lark API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for aiohttp request
            
        Returns:
            Response data as dictionary
        """
        # Ensure we have a valid token
        await self.get_access_token()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Merge headers if provided
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        try:
            async with self.session.request(method, url, headers=headers, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data
                    else:
                        logger.error(f"❌ Lark API error: {data.get('msg', 'Unknown error')}")
                        raise Exception(f"Lark API error: {data.get('msg', 'Unknown error')}")
                else:
                    text = await response.text()
                    logger.error(f"❌ HTTP error {response.status}: {text}")
                    raise Exception(f"HTTP error {response.status}: {text}")
                    
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            raise
    
    async def send_message(self, chat_id: str, content: str, msg_type: str = "text") -> Dict[str, Any]:
        """
        Send a message to a chat.
        
        Args:
            chat_id: Target chat ID
            content: Message content
            msg_type: Message type (text, rich_text, etc.)
            
        Returns:
            Response data from API
        """
        endpoint = "/im/v1/messages"
        payload = {
            "receive_id": chat_id,
            "receive_id_type": "chat_id",
            "msg_type": msg_type,
            "content": json.dumps({"text": content}) if msg_type == "text" else content
        }
        
        logger.info(f"📤 Sending message to chat {chat_id}")
        return await self._make_request("POST", endpoint, json=payload)
    
    async def reply_to_message(self, message_id: str, content: str, msg_type: str = "text") -> Dict[str, Any]:
        """
        Reply to a specific message (used for topic messaging).
        
        Args:
            message_id: ID of message to reply to
            content: Reply content
            msg_type: Message type
            
        Returns:
            Response data from API
        """
        endpoint = f"/im/v1/messages/{message_id}/reply"
        payload = {
            "msg_type": msg_type,
            "content": json.dumps({"text": content}) if msg_type == "text" else content
        }
        
        logger.info(f"💬 Replying to message {message_id}")
        return await self._make_request("POST", endpoint, json=payload)
    
    async def get_chat_messages(self, chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent messages from a chat.
        
        Args:
            chat_id: Chat ID to get messages from
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message objects
        """
        # Try different API endpoints for message retrieval
        endpoints_to_try = [
            # Method 1: Standard messages endpoint
            {
                "path": "/im/v1/messages",
                "params": {
                    "container_id": chat_id,
                    "container_id_type": "chat_id",
                    "page_size": min(limit, 100)
                }
            },
            # Method 2: Chat history endpoint
            {
                "path": f"/im/v1/chats/{chat_id}/messages",
                "params": {
                    "page_size": min(limit, 100)
                }
            }
        ]
        
        for method in endpoints_to_try:
            try:
                response = await self._make_request("GET", method["path"], params=method["params"])
                messages = response.get("data", {}).get("items", [])
                logger.info(f"📬 Retrieved {len(messages)} messages from chat {chat_id}")
                return messages
            except Exception as e:
                logger.warning(f"⚠️ Message retrieval method failed: {e}")
                continue
        
        logger.warning(f"⚠️ All message retrieval methods failed for chat {chat_id}")
        return []
    
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """
        Get information about a chat.
        
        Args:
            chat_id: Chat ID to get info for
            
        Returns:
            Chat information
        """
        endpoint = f"/im/v1/chats/{chat_id}"
        
        try:
            response = await self._make_request("GET", endpoint)
            chat_info = response.get("data", {})
            logger.info(f"ℹ️ Retrieved chat info for {chat_id}")
            return chat_info
        except Exception as e:
            logger.error(f"❌ Failed to get chat info: {e}")
            return {}
    
    async def test_connection(self) -> bool:
        """
        Test the connection to Lark API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get access token
            token = await self.get_access_token()
            if token:
                logger.info("✅ Lark API connection test successful")
                return True
            else:
                logger.error("❌ Lark API connection test failed: No token received")
                return False
        except Exception as e:
            logger.error(f"❌ Lark API connection test failed: {e}")
            return False

class LarkMessagePoller:
    """
    Polls Lark for new messages in specific chats/topics.
    Alternative to webhook-based approach.
    """
    
    def __init__(self, api_client: LarkAPIClient, chat_id: str, poll_interval: int = 30):
        self.api_client = api_client
        self.chat_id = chat_id
        self.poll_interval = poll_interval
        self.last_message_time = None
        self.is_running = False
        
    async def start_polling(self, message_handler=None, topic_filter: str = None):
        """
        Start polling for new messages.
        
        Args:
            message_handler: Async function to handle new messages
            topic_filter: Only process messages from this topic thread_id
        """
        self.is_running = True
        logger.info(f"🔄 Starting message polling for chat {self.chat_id}")
        
        if topic_filter:
            logger.info(f"🎯 Filtering for topic: {topic_filter}")
        
        while self.is_running:
            try:
                # Get recent messages
                messages = await self.api_client.get_chat_messages(self.chat_id, limit=10)
                
                # Filter new messages
                new_messages = []
                for msg in messages:
                    msg_time = datetime.fromtimestamp(int(msg.get("create_time", 0)) / 1000)
                    
                    # Skip if we've seen this message before
                    if self.last_message_time and msg_time <= self.last_message_time:
                        continue
                    
                    # Filter by topic if specified
                    if topic_filter and msg.get("thread_id") != topic_filter:
                        continue
                    
                    new_messages.append(msg)
                
                # Update last seen time
                if messages:
                    latest_time = max(
                        datetime.fromtimestamp(int(msg.get("create_time", 0)) / 1000)
                        for msg in messages
                    )
                    self.last_message_time = latest_time
                
                # Process new messages
                if new_messages and message_handler:
                    for msg in reversed(new_messages):  # Process oldest first
                        try:
                            await message_handler(msg)
                        except Exception as e:
                            logger.error(f"❌ Error handling message: {e}")
                
                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"❌ Polling error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    def stop_polling(self):
        """Stop the polling loop."""
        self.is_running = False
        logger.info("⏹️ Stopping message polling")

# Example usage and testing
async def test_lark_client():
    """Test function for the Lark API client."""
    import os
    
    # Test credentials (replace with actual values)
    app_id = os.getenv("LARK_APP_ID", "your_app_id")
    app_secret = os.getenv("LARK_APP_SECRET", "your_app_secret")
    chat_id = os.getenv("LARK_CHAT_ID", "your_chat_id")
    
    async with LarkAPIClient(app_id, app_secret) as client:
        # Test connection
        if await client.test_connection():
            print("✅ Connection successful")
            
            # Test sending a message
            try:
                response = await client.send_message(chat_id, "🤖 Test message from Lark API client")
                print(f"✅ Message sent: {response}")
            except Exception as e:
                print(f"❌ Failed to send message: {e}")
        else:
            print("❌ Connection failed")

import httpx
import os

LARK_BOT_URL = "https://open.larksuite.com/open-apis/im/v1/messages"

import httpx
import uuid
from bot.utils import config
async def send_text_message(chat_id: str, root_id: str, text: str):
    url = "https://open.larksuite.com/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {config.LARK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
        "uuid": str(uuid.uuid4()),
        "root_id": root_id,
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, json=payload)

async def send_message_card(chat_id: str, root_id: str, card: dict):
    headers = {
        "Authorization": f"Bearer {os.getenv('LARK_BOT_TOKEN')}",
        "Content-Type": "application/json"
    }

    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": card,
        "root_id": root_id
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LARK_BOT_URL}?receive_id_type=chat_id",
            json=payload,
            headers=headers
        )
        response.raise_for_status()


if __name__ == "__main__":
    # Run test
    asyncio.run(test_lark_client())