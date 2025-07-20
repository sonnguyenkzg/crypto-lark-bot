#!/usr/bin/env python3
"""
Remove Handler for Lark Bot - Following Telegram Bot Pattern
Removes wallets with single quoted argument parsing
FIXED: Now accepts both wallet names and TRON addresses
"""

import logging
import re
from typing import Any, Tuple, Union

from bot.services.wallet_service import WalletService
from bot.services.balance_service import BalanceService

logger = logging.getLogger(__name__)

class RemoveHandler:
    def __init__(self):
        self.name = "remove"
        self.description = "Remove a wallet (requires 1 quoted wallet name or address)"
        self.usage = '/remove "wallet_name_or_address"'
        self.aliases = ["delete", "del"]
        self.enabled = True
        self.wallet_service = WalletService()
        self.balance_service = BalanceService()  # For address validation

    def extract_quoted_strings(self, text: str) -> list:
        """Extract quoted strings from text."""
        pattern = r'["\']([^"\']*)["\']'
        matches = re.findall(pattern, text)
        return matches

    def parse_single_quoted_argument(self, text: str) -> Tuple[bool, Union[str, str]]:
        """
        Parse text with single quoted argument.
        Expects exactly 1 quoted string: "wallet_name_or_address"
        
        Args:
            text: Command text from user
            
        Returns:
            Tuple[bool, Union[str, str]]: (success, wallet_identifier or error_message)
        """
        if not text or not text.strip():
            return False, "❌ Missing wallet name or address"
        
        # Extract quoted strings
        matches = self.extract_quoted_strings(text)
        
        if len(matches) != 1:
            return False, f"❌ Expected 1 quoted argument, found {len(matches)}"
        
        wallet_identifier = matches[0].strip()
        
        # Validate wallet identifier is not empty
        if not wallet_identifier:
            return False, "❌ Wallet name or address cannot be empty"
        
        return True, wallet_identifier

    def find_wallet_by_identifier(self, identifier: str) -> Tuple[bool, Union[dict, str]]:
        """
        Find wallet by name or address.
        
        Args:
            identifier: Wallet name or TRON address
            
        Returns:
            Tuple[bool, Union[dict, str]]: (found, wallet_info or error_message)
        """
        try:
            # First, try to get wallet by name (existing functionality)
            wallet_exists, wallet_info = self.wallet_service.get_wallet(identifier)
            
            if wallet_exists:
                return True, wallet_info
            
            # Check if identifier is a valid TRON address
            if self.balance_service.validate_trc20_address(identifier):
                # It's a valid address, search through all wallets to find it
                success, wallet_data = self.wallet_service.list_wallets()
                
                if success and 'companies' in wallet_data:
                    for company_name, company_wallets in wallet_data['companies'].items():
                        for wallet in company_wallets:
                            if wallet['address'].lower() == identifier.lower():
                                # Found wallet with matching address
                                # FIXED: Use 'wallet' key instead of 'name' to match JSON structure
                                wallet_info = {
                                    'name': wallet['name'],  # This comes from list_wallets which uses 'name' in output
                                    'wallet': wallet['name'],  # Add wallet key for consistency
                                    'address': wallet['address'],
                                    'company': company_name
                                }
                                return True, wallet_info
                
                # Valid address but not found in our wallets
                return False, f"❌ TRON address '{identifier[:10]}...{identifier[-6:]}' not found in wallet list"
            
            # Not a valid address and not found by name
            return False, f"❌ Wallet '{identifier}' not found"
            
        except Exception as e:
            logger.error(f"Error finding wallet by identifier '{identifier}': {e}")
            return False, f"❌ Error searching for wallet: {str(e)}"

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

            wallet_identifier = result

            # Find wallet by name or address
            found, result = self.find_wallet_by_identifier(wallet_identifier)
            
            if not found:
                error_message = result
                # Create not found error with suggestions
                not_found_card = self._create_not_found_card(wallet_identifier, error_message)
                await context.topic_manager.send_command_response(not_found_card, msg_type="interactive")
                logger.warning(f"Remove failed - {error_message} for user {user_id}")
                return False

            wallet_info = result
            # FIXED: Get wallet name from the correct key
            wallet_name = wallet_info.get('wallet', wallet_info.get('name', 'Unknown'))

            # Attempt to remove wallet using wallet service (by name)
            success, message = self.wallet_service.remove_wallet(wallet_name)
            
            if success:
                # Create success card
                success_card = self._create_success_card(wallet_name, wallet_info, wallet_identifier)
                await context.topic_manager.send_command_response(success_card, msg_type="interactive")
                logger.info(f"Wallet '{wallet_name}' removed successfully by user {user_id} (identifier: '{wallet_identifier}')")
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

    def _create_success_card(self, wallet_name: str, wallet_info: dict, original_identifier: str) -> dict:
        """Create success card with information about what was removed."""
        company = wallet_info.get('company', 'Unknown')
        wallet_address = wallet_info.get('address', 'Unknown')
        
        # Show what identifier was used
        identifier_type = "address" if self.balance_service.validate_trc20_address(original_identifier) else "name"
        
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
                    "text": {
                        "tag": "lark_md",
                        "content": f"📋 **Details:**\n• **Company:** {company}\n• **Wallet:** {wallet_name}\n• **Address:** {wallet_address[:10]}...{wallet_address[-6:]}"
                    }
                },
                
                # Show how it was identified
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🔍 **Removed by:** {identifier_type}"
                    }
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

    def _create_not_found_card(self, identifier: str, error_message: str) -> dict:
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
                
                # Find similar names (only for name searches, not addresses)
                if not self.balance_service.validate_trc20_address(identifier):
                    similar_names = [name for name in all_wallet_names 
                                   if identifier.lower() in name.lower()][:3]
        except:
            similar_names = []

        # Build error message
        error_content = error_message
        
        if similar_names:
            suggestions = "`, `".join(similar_names)
            error_content += f"\n\n💡 **Did you mean:** `{suggestions}`"
        
        error_content += "\n\n📋 Use **/list** to see all available wallets"
        error_content += "\n\n💡 **Tip:** You can remove by wallet name or TRON address"

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
                        "content": "❌ **Missing wallet identifier**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Usage:** `/remove \"wallet_name_or_address\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Examples:**\n• `/remove \"KZP TEST1\"` (by name)\n• `/remove \"TDgWVGJKktTMaGt9fLJhTr7PHY3hEfk6BU\"` (by address)"
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
                        "content": "**Usage:** `/remove \"wallet_name_or_address\"`"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Examples:**\n• `/remove \"KZP TEST1\"` (by name)\n• `/remove \"TDgWVGJKktTMaGt9fLJhTr7PHY3hEfk6BU\"` (by address)"
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