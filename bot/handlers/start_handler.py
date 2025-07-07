#!/usr/bin/env python3
"""
Start Handler - Using Interactive Card Format Like Help Handler
Provides bot introduction and status check with proper rich text formatting
"""

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

class StartHandler:
    def __init__(self):
        self.name = "start"
        self.description = "Start the bot and check connection"
        self.usage = "/start"
        self.aliases = ["begin", "init"]
        self.enabled = True

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            # Create interactive card message (same as help handler)
            card_message = self._create_start_card()
            
            # Send as interactive card (exactly like help handler)
            await context.topic_manager.send_command_response(card_message, msg_type="interactive")

            logger.info(f"✅ Start command completed for user: {context.sender_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error in start command: {e}")
            # Fallback to text message if card fails (same as help handler)
            fallback_message = self._get_start_text_fallback()
            await context.topic_manager.send_command_response(fallback_message)
            return False

    def _create_start_card(self) -> dict:
        """
        Create interactive card for start message.
        Uses same structure as help handler.
        """
        # Get environment from .env
        environment = os.getenv('ENVIRONMENT', 'DEV')
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": "🤖 Crypto Wallet Monitor Bot"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "Bot Status & Welcome"
                }
            },
            "elements": [
                # Main status message
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "🤖 **Crypto Wallet Monitor Bot is running!**"
                    }
                },
                
                # Greeting
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Hello Group! 👋"
                    }
                },
                
                # Purpose
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "This bot helps you monitor USDT wallet balances."
                    }
                },
                
                # Environment and Status
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"Environment: **{environment}**\nStatus: ✅ **Connected and Ready**"
                            }
                        }
                    ]
                },
                
                # Help suggestion
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Try **/help** to see available commands."
                    }
                }
            ]
        }

    def _get_start_text_fallback(self) -> str:
        """
        Fallback to rich text message if interactive card fails.
        Uses same approach as help handler.
        """
        environment = os.getenv('ENVIRONMENT', 'DEV')
        
        return f"""🤖 **Crypto Wallet Monitor Bot is running!**

Hello Group! 👋

This bot helps you monitor USDT wallet balances.

Environment: **{environment}**
Status: ✅ **Connected and Ready**

Try **/help** to see available commands."""

    async def _send_disabled_message(self, context: Any):
        """Send disabled message using interactive card format."""
        disabled_card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ Command Disabled"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "🚫 **Start command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")