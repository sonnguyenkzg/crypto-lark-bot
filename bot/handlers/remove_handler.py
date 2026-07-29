#!/usr/bin/env python3
"""
Remove Handler for Lark Bot - Following Telegram Bot Pattern
Removes wallets with single quoted argument parsing
Accepts wallet names and TRC20/ERC20 addresses
"""

import logging
from typing import Any, Tuple, Union

from bot.services.wallet_service import WalletService
from bot.services.chain_detector import get_chain_emoji, detect_chain_from_address, canonical_address
from bot.services.command_args import parse_arguments

logger = logging.getLogger(__name__)

class RemoveHandler:
    def __init__(self):
        self.name = "remove"
        self.description = "Remove a wallet (requires 1 wallet name or address in brackets)"
        self.usage = '/remove [wallet_name_or_address]'
        self.aliases = ["delete", "del"]
        self.enabled = True
        self.wallet_service = WalletService()

    def parse_single_quoted_argument(self, text: str) -> Tuple[bool, Union[str, str]]:
        """Parse the single [wallet name or address] argument.

        Accepts [brackets] (preferred) or "quotes" (still supported).
        Returns (success, wallet_identifier) or (False, error_message).
        """
        if not text or not text.strip():
            return False, "❌ Missing wallet name or address"

        matches, _ = parse_arguments(text)

        if len(matches) != 1:
            return False, f"❌ Expected 1 argument in [ ] (or quotes), found {len(matches)}"

        return True, matches[0].strip()

    def _match_address(self, identifier, wallets_list):
        """Return the wallet dict whose address matches `identifier` by canonical
        address (ERC20 case-insensitive, TRC20 exact), or None."""
        target = canonical_address(identifier)
        if not target:
            return None
        for w in wallets_list:
            if canonical_address(w.get("address", "")) == target:
                return w
        return None

    def find_wallet_by_identifier(self, identifier: str) -> Tuple[bool, Union[dict, str]]:
        """
        Find wallet by name or address.

        Args:
            identifier: Wallet name or address (TRC20 or ERC20)

        Returns:
            Tuple[bool, Union[dict, str]]: (found, wallet_info or error_message)
        """
        try:
            # First, try to get wallet by name (existing functionality)
            wallet_exists, wallet_info = self.wallet_service.get_wallet(identifier)

            if wallet_exists:
                return True, wallet_info

            # Check if identifier is a valid address (TRC20 or ERC20)
            if detect_chain_from_address(identifier):   # valid TRC20 or ERC20 address
                success, wallet_data = self.wallet_service.list_wallets()

                if success and 'companies' in wallet_data:
                    flat = []
                    for company_name, company_wallets in wallet_data['companies'].items():
                        for w in company_wallets:
                            flat.append({"name": w["name"], "address": w["address"], "company": company_name})
                    hit = self._match_address(identifier, flat)
                    if hit:
                        return True, {"name": hit["name"], "wallet": hit["name"],
                                      "address": hit["address"], "company": hit["company"]}

                # Valid address but not found in our wallets
                return False, f"❌ Address '{identifier[:10]}...{identifier[-6:]}' not found in wallet list"

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
        chain = wallet_info.get('chain', 'TRC20')  # Default to TRC20 for backward compatibility
        chain_emoji = get_chain_emoji(chain)

        # Show what identifier was used
        identifier_type = "address" if detect_chain_from_address(original_identifier) else "name"
        
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
                        "content": f"📋 **Details:**\n• **Company:** {company}\n• **Wallet:** {wallet_name}\n• **Chain:** {chain_emoji} {chain}\n• **Address:** {wallet_address[:10]}...{wallet_address[-6:]}"
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
                if not detect_chain_from_address(identifier):
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
        error_content += "\n\n💡 **Tip:** You can remove by wallet name or address (TRC20 or ERC20)"

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
                        "content": "**Usage:** /remove [wallet name or address]"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Examples:**\n• /remove [KZP TEST1] (by name)\n• /remove [TDgWVGJKktTMaGt9fLJhTr7PHY3hEfk6BU] (by address)"
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
                        "content": "**Usage:** /remove [wallet name or address]"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Examples:**\n• /remove [KZP TEST1] (by name)\n• /remove [TDgWVGJKktTMaGt9fLJhTr7PHY3hEfk6BU] (by address)"
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