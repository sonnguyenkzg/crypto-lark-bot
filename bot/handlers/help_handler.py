#!/usr/bin/env python3
"""
Enhanced Lark Bot Help Handler with Professional Formatting
Creates Telegram-style professional help messages using Lark's interactive cards
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

class HelpHandler:
    def __init__(self):
        self.name = "help"
        self.description = "Show available commands and their descriptions"
        self.usage = "/help [command]"
        self.aliases = ["h", "?"]
        self.enabled = True

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            # Create professional interactive card message
            card_message = self._create_help_card()
            
            # Send as interactive card
            await context.topic_manager.send_command_response(card_message, msg_type="interactive")

            logger.info(f"✅ Help command completed for user: {context.sender_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error in help command: {e}")
            # Fallback to text message if card fails
            fallback_message = self._get_help_text_fallback()
            await context.topic_manager.send_command_response(fallback_message)
            return False

    def _create_help_card(self) -> dict:
        """
        Create a professional interactive card for help message.
        This matches the Telegram-style formatting from your screenshot.
        """
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🤖 Crypto Wallet Monitor Bot"
                },
                "subtitle": {
                    "tag": "plain_text", 
                    "content": "Available Commands"
                }
            },
            "elements": [
                # Wallet Management Section
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🔐 Wallet Management:**"
                    }
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": "• **/start** - Start the bot and check connection\n• **/help** - Show available commands and their descriptions\n• **/list** - Show all configured wallets\n• **/add \"company\" \"wallet\" \"address\"** - Add new wallet\n• **/remove \"wallet_name\"** - Remove wallet\n• **/check** - Check all wallet balances\n• **/check \"wallet_name\"** - Check specific wallet balance\n• **/check \"wallet1\" \"wallet2\"** - Check multiple specific wallets"
                            }
                        }
                    ]
                },
                
                # Divider
                {
                    "tag": "hr"
                },
                
                # Examples Section
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**📝 Examples:**"
                    }
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": "• **/add \"KZP\" \"KZP WDB2\" \"TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS\"**\n• **/remove \"KZP WDB2\"**\n• **/list**\n• **/check**\n• **/check \"KZP 96G1\"**\n• **/check \"KZP 96G1\" \"KZP WDB2\"**"
                            }
                        }
                    ]
                },
                
                # Divider
                {
                    "tag": "hr"
                },
                
                # Notes Section
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**⚠️ Notes:**"
                    }
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": "• All arguments must be in quotes\n• TRC20 addresses start with 'T' (34 characters)\n• Balance reports sent via scheduled messages at midnight GMT+7\n• Only authorized team members can use commands"
                            }
                        }
                    ]
                },
                
                # Quick Actions Section (replacing buttons)
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**⚡ Quick Actions:**"
                    }
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": "• Type **/check** to check all wallet balances\n• Type **/list** to see all configured wallets\n• Type **/start** to test bot connection"
                            }
                        }
                    ]
                },
                

            ]
        }

    def _get_help_text_fallback(self) -> str:
        """
        Fallback to rich text message if interactive card fails.
        Uses Lark's markdown formatting for professional appearance.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""🤖 **Crypto Wallet Monitor Bot**

**🔐 Wallet Management:**
• **/start** - Start the bot and check connection
• **/help** - Show available commands and their descriptions  
• **/list** - Show all configured wallets
• **/add "company" "wallet" "address"** - Add new wallet
• **/remove "wallet_name"** - Remove wallet
• **/check** - Check all wallet balances
• **/check "wallet_name"** - Check specific wallet balance
• **/check "wallet1" "wallet2"** - Check multiple specific wallets

---

**📝 Examples:**
• **/add "KZP" "KZP WDB2" "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"**
• **/remove "KZP WDB2"**
• **/list**
• **/check**
• **/check "KZP 96G1"**
• **/check "KZP 96G1" "KZP WDB2"**

---

**⚠️ Notes:**
• All arguments must be in quotes
• TRC20 addresses start with 'T' (34 characters)
• Balance reports sent via scheduled messages at midnight GMT+7
• Only authorized team members can use commands

---

**⚡ Quick Actions:**
• Type **/check** to check all wallet balances
• Type **/list** to see all configured wallets
• Type **/start** to test bot connection"""

    async def _send_disabled_message(self, context: Any):
        """Send a professional disabled message."""
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
                        "content": "🚫 **This command is currently disabled.**\n\nPlease contact an administrator if you need assistance."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")

    async def _send_unauthorized_message(self, context: Any):
        """Send a professional unauthorized message."""
        unauthorized_card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "🚫 Access Denied"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🚫 Access Denied**\n\nYou are not authorized to use this bot.\n\n**Your ID:** **{context.sender_id}**\n\nPlease contact an administrator for access."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(unauthorized_card, msg_type="interactive")