#!/usr/bin/env python3
"""
Remove Handler for Lark Bot - Following Telegram Bot Pattern
Removes wallets with single quoted argument parsing
"""

import logging
import re
from typing import Any, Tuple, Union

from bot.services.wallet_service import WalletService

logger = logging.getLogger(__name__)

class RemoveHandler:
    def __init__(self):
        self.name = "remove"
        self.description = "Remove a wallet (requires 1 quoted wallet name)"
        self.usage = '/remove "wallet_name"'
        self.aliases = ["delete", "del"]
        self.enabled = True
        self.wallet_service = WalletService()

    def extract_quoted_strings(self, text: str) -> list:
        """Extract quoted strings from text."""
        pattern = r'["\']([^"\']*)["\']'
        matches = re.findall(pattern, text)
        return matches

    def parse_single_quoted_argument(self, text: str) -> Tuple[bool, Union[str, str]]:
        """
        Parse text with single quoted argument.
        Expects exactly 1 quoted string: "wallet_name"
        
        Args:
            text: Command text from user
            
        Returns:
            Tuple[bool, Union[str, str]]: (success, wallet_name or error_message)
        """
        if not text or not text.strip():
            return False, "❌ Missing wallet name"
        
        # Extract quoted strings
        matches = self.extract_quoted_strings(text)
        
        if len(matches) != 1:
            return False, f"❌ Expected 1 quoted argument, found {len(matches)}"
        
        wallet_name = matches[0].strip()
        
        # Validate wallet name is not empty
        if not wallet_name:
            return False, "❌ Wallet name cannot be empty"
        
        return True, wallet_name

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            user_id = context.sender_id
            command_args = " ".join(context.args) if context.args else ""
            
            logger.info(f"Remove command received from user ID: {user_id}")
            logger.info(f"Command args: '{command_args}'")

            # If no arguments, show usage
            if not command_args.strip():
                usage_card = self._create_usage_card()
                await context.topic_manager.send_command_response(usage_card, msg_type="interactive")
                return True

            # Parse argument using quoted parsing
            success, result = self.parse_single_quoted_argument(command_args)
            
            if not success:
                error_message = result
                error_card = self._create_error_card(error_message)
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                logger.warning(f"Remove command failed for user {user_id}: {error_message}")
                return False

            wallet_name = result

            # Check if wallet exists before attempting removal
            wallet_exists, wallet_info = self.wallet_service.get_wallet(wallet_name)
            
            if not wallet_exists:
                # Create not found error with suggestions
                not_found_card = self._create_not_found_card(wallet_name)
                await context.topic_manager.send_command_response(not_found_card, msg_type="interactive")
                logger.warning(f"Remove failed - wallet '{wallet_name}' not found for user {user_id}")
                return False

            # Attempt to remove wallet using wallet service
            success, message = self.wallet_service.remove_wallet(wallet_name)
            
            if success:
                # Create success card matching your screenshot
                success_card = self._create_success_card(wallet_name, wallet_info)
                await context.topic_manager.send_command_response(success_card, msg_type="interactive")
                logger.info(f"Wallet '{wallet_name}' removed successfully by user {user_id}")
            else:
                # Send error message from wallet service
                error_card = self._create_error_card(message)
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                logger.warning(f"Remove wallet failed for user {user_id}: {message}")

            return success

        except Exception as e:
            logger.error(f"❌ Error in remove command: {e}")
            # Fallback to text message
            fallback_message = f"❌ **Error removing wallet:** {str(e)}"
            await context.topic_manager.send_command_response(fallback_message)
            return False

    def _create_success_card(self, wallet_name: str, wallet_info: dict) -> dict:
        """Create success card matching your screenshot format."""
        company = wallet_info.get('company', 'Unknown')
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": "✅ Wallet Removed Successfully"
                }
            },
            "elements": [
                # Success message
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "✅ **Wallet Removed Successfully**"
                    }
                },
                
                # Wallet details
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**Wallet:** {wallet_name}\n**Company:** {company}"
                            }
                        }
                    ]
                },
                
                # Confirmation message
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "The wallet has been removed from monitoring."
                    }
                },
                
                # Footer suggestion
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Use **/list** to see remaining wallets."
                    }
                }
            ]
        }

    def _create_not_found_card(self, wallet_name: str) -> dict:
        """Create not found error with helpful suggestions."""
        # Get all wallets to suggest similar names
        try:
            success, wallet_data = self.wallet_service.list_wallets()
            similar_names = []
            
            if success and 'companies' in wallet_data:
                all_wallet_names = []
                for company_wallets in wallet_data['companies'].values():
                    for wallet in company_wallets:
                        all_wallet_names.append(wallet['name'])
                
                # Find similar names
                similar_names = [name for name in all_wallet_names 
                               if wallet_name.lower() in name.lower()][:3]
        except:
            similar_names = []

        # Build error message
        error_content = f"❌ **Wallet '{wallet_name}' not found**"
        
        if similar_names:
            suggestions = "`, `".join(similar_names)
            error_content += f"\n\n💡 **Did you mean:** `{suggestions}`"
        
        error_content += "\n\n📋 Use **/list** to see all available wallets"

        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Wallet Not Found"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": error_content
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
                    "content": "ℹ️ Remove Wallet Usage"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **Missing wallet name**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Usage:** `/remove \"wallet_name\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Example:** `/remove \"KZP TEST1\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "💡 Use **/list** to see available wallets"
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
                    "content": "❌ Remove Wallet Error"
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
                        "content": "**Usage:** `/remove \"wallet_name\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Example:** `/remove \"KZP TEST1\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "💡 Use **/list** to see available wallets"
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
                        "content": "🚫 **Remove command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")