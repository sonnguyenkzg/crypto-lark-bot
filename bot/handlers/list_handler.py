#!/usr/bin/env python3
"""
List Handler for Lark Bot - Following Telegram Bot Pattern
Shows all configured wallets from wallets.json
"""

import logging
from datetime import datetime
from typing import Any

# You'll need to create this service following your Telegram bot pattern
from bot.services.wallet_service import WalletService

logger = logging.getLogger(__name__)

class ListHandler:
    def __init__(self):
        self.name = "list"
        self.description = "Show all configured wallets"
        self.usage = "/list"
        self.aliases = ["ls", "show"]
        self.enabled = True
        self.wallet_service = WalletService()

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            user_id = context.sender_id
            logger.info(f"List command received from user ID: {user_id}")

            # Get wallet list from service (same as your Telegram bot)
            success, message_data = self.wallet_service.list_wallets()
            
            if success:
                # Create interactive card with wallet list
                wallets_card = self._create_wallets_card(message_data)
                await context.topic_manager.send_command_response(wallets_card, msg_type="interactive")
            else:
                # Error case - send simple message
                error_card = self._create_error_card(message_data)
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")

            logger.info(f"✅ List command completed for user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error in list command: {e}")
            # Fallback to text message
            fallback_message = self._get_list_text_fallback()
            await context.topic_manager.send_command_response(fallback_message)
            return False

    def _create_wallets_card(self, wallet_data: dict) -> dict:
        """
        Create interactive card showing wallet list.
        Formats exactly like your screenshot.
        """
        # Parse wallet data (assuming wallet_service returns organized data)
        total_count = wallet_data.get('total_count', 0)
        companies = wallet_data.get('companies', {})
        
        elements = []
        
        # Header with count
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md", 
                "content": f"📋 **Configured Wallets ({total_count} total)**"
            }
        })
        
        # Add each company section
        for company_name, wallets in companies.items():
            # Company header
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"🏢 **{company_name}**"
                }
            })
            
            # Wallet list for this company
            wallet_list = []
            for wallet in wallets:
                wallet_name = wallet.get('name', 'Unknown')
                wallet_address = wallet.get('address', 'Unknown')
                wallet_list.append(f"• **{wallet_name}**: {wallet_address}")
            
            elements.append({
                "tag": "div",
                "fields": [
                    {
                        "is_short": False,
                        "text": {
                            "tag": "lark_md",
                            "content": "\n".join(wallet_list)
                        }
                    }
                ]
            })
            
            # Add spacing between companies if there are more
            if company_name != list(companies.keys())[-1]:
                elements.append({"tag": "hr"})
        
        # Footer with check suggestion
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "💡 Use **/check** to see current balances"
            }
        })

        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "📋 Wallet List"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "All Configured Wallets"
                }
            },
            "elements": elements
        }

    def _create_error_card(self, error_message: str) -> dict:
        """Create error card when wallet service fails."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Error"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"❌ **Error loading wallets:**\n\n{error_message}"
                    }
                }
            ]
        }

    def _get_list_text_fallback(self) -> str:
        """Fallback text message if card fails."""
        try:
            success, message_data = self.wallet_service.list_wallets()
            if success:
                # Convert to simple text format
                total_count = message_data.get('total_count', 0)
                companies = message_data.get('companies', {})
                
                text_lines = [f"📋 **Configured Wallets ({total_count} total)**\n"]
                
                for company_name, wallets in companies.items():
                    text_lines.append(f"🏢 **{company_name}**")
                    for wallet in wallets:
                        wallet_name = wallet.get('name', 'Unknown')
                        wallet_address = wallet.get('address', 'Unknown')
                        text_lines.append(f"• **{wallet_name}**: {wallet_address}")
                    text_lines.append("")  # Empty line between companies
                
                text_lines.append("💡 Use **/check** to see current balances")
                return "\n".join(text_lines)
            else:
                return f"❌ **Error loading wallets:** {message_data}"
        except Exception as e:
            return f"❌ **Error loading wallets:** {str(e)}"

    async def _send_disabled_message(self, context: Any):
        """Send disabled message."""
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
                        "content": "🚫 **List command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")