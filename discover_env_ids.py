#!/usr/bin/env python3
"""
Environment Discovery Tool
Helps you find missing LARK_* environment variables by listening to test messages
"""

import os
import asyncio
import json
from dotenv import load_dotenv

# Load existing .env
load_dotenv()

from bot.services.lark_api_client import LarkAPIClient

async def discover_chat_ids():
    """Step 1: Find your chat ID"""
    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")

    if not app_id or not app_secret:
        print("❌ Error: LARK_APP_ID and LARK_APP_SECRET must be set in .env")
        return

    print("🔍 Discovering Lark Chat IDs...")
    print("=" * 60)

    async with LarkAPIClient(app_id, app_secret) as client:
        try:
            # Get tenant access token
            token = await client.get_access_token()

            # List all chats the bot is in
            url = "https://open.larksuite.com/open-apis/im/v1/chats"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            async with client.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    chats = data.get('data', {}).get('items', [])

                    if not chats:
                        print("⚠️  No chats found. Make sure the bot is added to your group!")
                        return

                    print(f"\n✅ Found {len(chats)} chat(s):\n")

                    for i, chat in enumerate(chats, 1):
                        chat_id = chat.get('chat_id', 'Unknown')
                        chat_name = chat.get('name', 'Unnamed Chat')
                        print(f"{i}. {chat_name}")
                        print(f"   Chat ID: {chat_id}")
                        print(f"   Add to .env: LARK_CHAT_ID={chat_id}\n")

                    print("=" * 60)
                    print("📝 Next Steps:")
                    print("1. Copy the correct Chat ID to your .env file")
                    print("2. Run this script with --messages to find topic IDs")

                else:
                    error_text = await response.text()
                    print(f"❌ API Error: {response.status}")
                    print(f"Response: {error_text}")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def discover_message_ids():
    """Step 2: Find topic and message IDs from recent messages"""
    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")
    chat_id = os.getenv("LARK_CHAT_ID")

    if not all([app_id, app_secret, chat_id]):
        print("❌ Error: LARK_APP_ID, LARK_APP_SECRET, and LARK_CHAT_ID must be set")
        return

    print("🔍 Discovering Message & Topic IDs...")
    print("=" * 60)
    print("💡 TIP: Send a test message in your Lark group NOW")
    print("   - Send one message in your Quickguide topic (e.g., 'hey bot this is quickguide')")
    print("   - Send one message in your Commands topic (e.g., 'hey bot this is command')")
    print("   - Send one message in your Daily Report topic (e.g., 'hey bot this is report')")
    print("   Then press Enter here...")
    input()

    async with LarkAPIClient(app_id, app_secret) as client:
        try:
            token = await client.get_access_token()

            # Get recent messages from the chat
            url = f"https://open.larksuite.com/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            params = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": 20
            }

            async with client.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    messages = data.get('data', {}).get('items', [])

                    if not messages:
                        print("⚠️  No recent messages found in this chat")
                        return

                    print(f"\n✅ Found {len(messages)} recent message(s):\n")

                    topics_found = {}

                    for i, msg in enumerate(messages, 1):
                        msg_id = msg.get('message_id', 'Unknown')
                        thread_id = msg.get('thread_id', msg.get('root_id', 'No thread'))
                        body = msg.get('body', {})
                        content = body.get('content', '{}')

                        try:
                            content_json = json.loads(content)
                            text = content_json.get('text', '[No text]')
                        except:
                            text = '[Unable to parse]'

                        print(f"{i}. Message: {text[:50]}...")
                        print(f"   Message ID: {msg_id}")
                        print(f"   Thread ID: {thread_id}")

                        # Try to identify which topic this is
                        if 'command' in text.lower() or '/add' in text or '/check' in text:
                            print(f"   🎯 Likely COMMANDS topic!")
                            topics_found['commands'] = (thread_id, msg_id)
                            print(f"   Add to .env:")
                            print(f"   LARK_TOPIC_COMMANDS={thread_id}")
                            print(f"   LARK_TOPIC_COMMANDS_MSG={msg_id}")
                        elif 'report' in text.lower() or 'daily' in text.lower():
                            print(f"   📊 Likely DAILY REPORT topic!")
                            topics_found['dailyreport'] = (thread_id, msg_id)
                            print(f"   Add to .env:")
                            print(f"   LARK_TOPIC_DAILYREPORT={thread_id}")
                            print(f"   LARK_TOPIC_DAILYREPORT_MSG={msg_id}")
                        elif 'quickguide' in text.lower() or 'quick guide' in text.lower() or 'guide' in text.lower():
                            print(f"   📚 Likely QUICKGUIDE topic!")
                            topics_found['quickguide'] = (thread_id, msg_id)
                            print(f"   Add to .env:")
                            print(f"   LARK_TOPIC_QUICKGUIDE={thread_id}")
                            print(f"   LARK_TOPIC_QUICKGUIDE_MSG={msg_id}")

                        print()

                    print("=" * 60)
                    if topics_found:
                        print("✅ Discovery Complete! Copy the IDs above to your .env file")
                    else:
                        print("⚠️  Couldn't auto-identify topics from message content")
                        print("   Manually identify which messages are from which topic")
                        print("   and copy their Thread ID and Message ID to .env")

                else:
                    error_text = await response.text()
                    print(f"❌ API Error: {response.status}")
                    print(f"Response: {error_text}")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--messages':
        await discover_message_ids()
    else:
        await discover_chat_ids()


if __name__ == "__main__":
    asyncio.run(main())
