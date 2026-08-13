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
                                "content": "• **/start** - Start the bot and check connection\n• **/help** - Show available commands and their descriptions\n• **/list** - Show all configured wallets\n• **/add [company] [wallet name] [address]** - Add a new wallet\n• **/remove [wallet name or address]** - Remove a wallet\n• **/check** - Check all wallet balances right now"
                            }
                        }
                    ]
                },
                
                # Divider
                {
                    "tag": "hr"
                },

                # Check a balance on a date (dedicated guide)
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**📅 Check a balance on any date:**"
                    }
                },
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": "• **/check** — everyone's balance right now\n• **/check [2026-07-15]** — that day's **closing** balance (end of day)\n• **/check [2026-07-15] [o]** — that day's **opening** balance (start of day)\n• **/check [2026-07-15] [c]** — closing, said explicitly\n• Narrow it to a group or wallet: **/check [2026-07-15] [KZDW]** or **/check [2026-07-15] [KZP 96G1]**\n• Or by wallet **address**: **/check [2026-07-15] [TVbEfiMhs7c94u6SeAY65vZR9C5eLQRMSD]** — an address is matched **exactly**, so you get that wallet or a clear error, never the wrong wallet by a typo (a mistyped *name* can be guessed wrong; an address can't). Give several to add them up; only the monitored wallets can be looked up, and a bad or unmonitored address is flagged (✅/❌/⚠️), never silently skipped\n• Dates go in [ ] and spacing doesn't matter — **[2026-07-15][o]** works too\n• Every dated figure is the balance at **midnight (00:00) GMT+7**"
                            }
                        }
                    ]
                },
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
                                "content": "• **/add [KZP] [KZP WDB2] [TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS]**\n• **/remove [KZP WDB2]**\n• **/check [2026-07-15]**\n• **/check [2026-07-15] [KZP]**\n• **/check [2026-07-15] [KZP 96G1]**\n• **/check [2026-07-15] [TVbEfiMhs7c94u6SeAY65vZR9C5eLQRMSD]**\n• **/list**\n• **/check**"
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
                                "content": "• Wrap each argument in [ ]; quotes also work\n• Dates are YYYY-MM-DD\n• **TRC20** addresses start with 'T' (34 characters)\n• **ERC20** addresses start with '0x' (42 characters)\n• Chain type auto-detected from address format\n• Balance reports sent via scheduled messages at midnight GMT+7\n• Only authorized team members can use commands"
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
• **/add [company] [wallet name] [address]** - Add a new wallet
• **/remove [wallet name or address]** - Remove a wallet
• **/check** - Check all wallet balances
• **/check [2026-07-15]** - balance at the END of that day (closing)
• **/check [2026-07-15] [o]** - balance at the START of that day (opening)
• **/check [2026-07-15] [c]** - balance at the end of that day, said explicitly
• **/check [2026-07-15] [KZDW]** - one group, that day's closing balance
• **/check [2026-07-15] [o] [KZDW]** - one group, that day's opening balance
• **/check [2026-07-15] [KZP 96G1]** - one wallet on that date (typo-tolerant)
• **/check [2026-07-15] [TVbEfiMhs7c94u6SeAY65vZR9C5eLQRMSD]** - one wallet by its address (matched exactly — you get that wallet or a clear error, never the wrong wallet by a typo; give several to add them up; a bad or unmonitored address is flagged, never silently skipped)

Spacing does not matter: **[2026-07-15][KZDW]** works the same.

---

**📝 Examples:**
• **/add [KZP] [KZP WDB2] [TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS]**
• **/remove [KZP WDB2]**
• **/check [2026-07-15]**
• **/check [2026-07-15] [KZP]**
• **/check [2026-07-15] [KZP 96G1]**
• **/check [2026-07-15] [TVbEfiMhs7c94u6SeAY65vZR9C5eLQRMSD]**
• **/list**
• **/check**

---

**⚠️ Notes:**
• Wrap each argument in [ ]; quotes also work
• Dates are YYYY-MM-DD
• **TRC20** addresses start with 'T' (34 characters)
• **ERC20** addresses start with '0x' (42 characters)
• Chain type auto-detected from address format
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