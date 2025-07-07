#!/usr/bin/env python3
"""
Add Handler for Lark Bot - Following Telegram Bot Pattern
Adds new wallets with quoted argument parsing
"""

import logging
import re
from typing import Any, Tuple, List, Union

from bot.services.wallet_service import WalletService

logger = logging.getLogger(__name__)

class AddHandler:
    def __init__(self):
        self.name = "add"
        self.description = "Add a new wallet (requires 3 quoted arguments)"
        self.usage = '/add "company" "wallet_name" "address"'
        self.aliases = ["create", "new"]
        self.enabled = True
        self.wallet_service = WalletService()

    def extract_quoted_strings(self, text: str) -> List[str]:
        """
        Extract quoted strings from text.
        Supports both single and double quotes.
        """
        # Pattern to match quoted strings (either single or double quotes)
        pattern = r'["\']([^"\']*)["\']'
        matches = re.findall(pattern, text)
        return matches

    def parse_quoted_arguments(self, text: str) -> Tuple[bool, Union[List[str], str]]:
        """
        Parse text with quoted arguments.
        Expects exactly 3 quoted strings: "company" "wallet" "address"
        
        Args:
            text: Command text from user
            
        Returns:
            Tuple[bool, Union[List[str], str]]: (success, [company, wallet, address] or error_message)
        """
        if not text or not text.strip():
            return False, "❌ Missing arguments"
        
        # Extract quoted strings
        matches = self.extract_quoted_strings(text)
        
        if len(matches) != 3:
            return False, f"❌ Expected 3 quoted arguments, found {len(matches)}"
        
        company, wallet, address = matches
        
        # Validate none are empty
        if not company.strip():
            return False, "❌ Company cannot be empty"
        if not wallet.strip():
            return False, "❌ Wallet name cannot be empty"  
        if not address.strip():
            return False, "❌ Address cannot be empty"
        
        return True, [company.strip(), wallet.strip(), address.strip()]

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            user_id = context.sender_id
            command_args = " ".join(context.args) if context.args else ""
            
            logger.info(f"Add command received from user ID: {user_id}")
            logger.info(f"Command args: '{command_args}'")

            # If no arguments, show usage
            if not command_args.strip():
                usage_card = self._create_usage_card()
                await context.topic_manager.send_command_response(usage_card, msg_type="interactive")
                return True

            # Parse arguments using quoted parsing
            success, result = self.parse_quoted_arguments(command_args)
            
            if not success:
                error_message = result
                error_card = self._create_error_card(error_message)
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                logger.warning(f"Add command failed for user {user_id}: {error_message}")
                return False

            company, wallet, address = result

            # Attempt to add wallet using wallet service (now async)
            success, message = await self.wallet_service.add_wallet(company, wallet, address)
            
            if success:
                # Create success card matching your screenshot
                success_card = self._create_success_card(company, wallet, address)
                await context.topic_manager.send_command_response(success_card, msg_type="interactive")
                logger.info(f"Wallet '{wallet}' added successfully by user {user_id}")
            else:
                # Send error message from wallet service
                error_card = self._create_error_card(message)
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                logger.warning(f"Add wallet failed for user {user_id}: {message}")

            return success

        except Exception as e:
            logger.error(f"❌ Error in add command: {e}")
            # Fallback to text message
            fallback_message = f"❌ **Error adding wallet:** {str(e)}"
            await context.topic_manager.send_command_response(fallback_message)
            return False

    def _create_success_card(self, company: str, wallet: str, address: str) -> dict:
        """Create success card matching your screenshot format."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": "✅ Wallet Added Successfully"
                }
            },
            "elements": [
                # Success message
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "✅ **Wallet Added Successfully**"
                    }
                },
                
                # Details section header
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "📋 **Details:**"
                    }
                },
                
                # Details list
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"• **Company:** {company}\n• **Wallet:** {wallet}\n• **Address:** {address}"
                            }
                        }
                    ]
                },
                
                # Footer suggestion
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Use **/check** to see current balance."
                    }
                }
            ]
        }

    def _create_usage_card(self) -> dict:
        """Create usage instruction card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "ℹ️ Add Wallet Usage"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **Missing arguments**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Usage:** `/add \"company\" \"wallet_name\" \"address\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Example:** `/add \"KZP\" \"KZP WDB2\" \"TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⚠️ **Notes:**\n• All arguments must be in quotes\n• TRC20 addresses start with 'T' (34 characters)"
                    }
                }
            ]
        }

    def _create_error_card(self, error_message: str) -> dict:
        """Create error card with usage information."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Add Wallet Error"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": error_message
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Usage:** `/add \"company\" \"wallet_name\" \"address\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Example:** `/add \"KZP\" \"KZP WDB2\" \"TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS\"`"
                    }
                }
            ]
        }

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
                        "content": "🚫 **Add command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")