#!/usr/bin/env python3
"""
Check Handler for Lark Bot - Following Telegram Bot Pattern
Checks wallet balances with beautiful table format
FIXED: Continuous calling issue
"""

import logging
import re
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from bot.services.wallet_service import WalletService
from bot.services.balance_service import BalanceService

logger = logging.getLogger(__name__)

# Global execution lock to prevent continuous calling
_CHECK_EXECUTION_LOCK = False

class CheckHandler:
    def __init__(self):
        self.name = "check"
        self.description = "Check wallet balances (all wallets or specific ones)"
        self.usage = '/check [optional: "wallet1" "wallet2"]'
        self.aliases = ["balance", "bal"]
        self.enabled = True
        self.wallet_service = WalletService()
        self.balance_service = BalanceService()

    def extract_quoted_strings(self, text: str) -> List[str]:
        """Extract quoted strings from text."""
        pattern = r'["\']([^"\']*)["\']'
        matches = re.findall(pattern, text)
        return matches

    def parse_check_arguments(self, text: str) -> List[str]:
        """
        Parse quoted arguments from check command text.
        
        Args:
            text: Command arguments from user
            
        Returns:
            List[str]: List of parsed wallet names/addresses
        """
        if not text or not text.strip():
            return []
        
        # Extract quoted strings
        quoted_inputs = self.extract_quoted_strings(text)
        
        return quoted_inputs

    def resolve_wallets_to_check(self, inputs: List[str], wallet_data: Dict) -> Tuple[Dict[str, str], List[str]]:
        """
        Resolve input arguments to {display_name: address} mapping.
        
        Args:
            inputs: List of wallet names or addresses from user
            wallet_data: All available wallet data from JSON
            
        Returns:
            tuple: (wallets_to_check, not_found_list)
        """
        wallets_to_check = {}
        not_found = []
        
        for input_str in inputs:
            input_str = input_str.strip()
            if not input_str:
                continue
                
            # Check if input is a TRC20 address
            if self.balance_service.validate_trc20_address(input_str):
                # It's an address - find the wallet name or use address as display
                found_wallet = False
                for wallet_key, wallet_info in wallet_data.items():
                    if wallet_info['address'].lower() == input_str.lower():
                        wallet_name = wallet_info.get('name', wallet_key)
                        wallets_to_check[wallet_name] = wallet_info['address']
                        found_wallet = True
                        break
                
                if not found_wallet:
                    # Address not in our list - still check it
                    display_name = f"External: {input_str[:10]}...{input_str[-6:]}"
                    wallets_to_check[display_name] = input_str
            
            else:
                # It's a wallet name - find the address (case-insensitive)
                found_wallet = False
                for wallet_key, wallet_info in wallet_data.items():
                    wallet_name = wallet_info.get('name', wallet_key)
                    if wallet_name.lower() == input_str.lower():
                        wallets_to_check[wallet_name] = wallet_info['address']
                        found_wallet = True
                        break
                
                if not found_wallet:
                    not_found.append(input_str)
        
        return wallets_to_check, not_found

    async def handle(self, context: Any) -> bool:
        global _CHECK_EXECUTION_LOCK
        
        # CRITICAL: Prevent continuous calling
        if _CHECK_EXECUTION_LOCK:
            logger.warning(f"🚫 Check command already executing - BLOCKING duplicate call from user {context.sender_id}")
            return False
        
        # Lock execution
        _CHECK_EXECUTION_LOCK = True
        logger.info(f"🔒 Check command LOCKED - Starting execution for user {context.sender_id}")
        
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            user_id = context.sender_id
            command_args = " ".join(context.args) if context.args else ""
            
            logger.info(f"Check command received from user ID: {user_id}")
            logger.info(f"Command args: '{command_args}'")

            # Load all wallets
            success, wallet_list_data = self.wallet_service.list_wallets()
            if not success or not wallet_list_data.get('companies'):
                no_wallets_card = self._create_no_wallets_card()
                await context.topic_manager.send_command_response(no_wallets_card, msg_type="interactive")
                return True

            # Convert wallet list data to flat dictionary for easier processing
            wallet_data = {}
            for company_wallets in wallet_list_data['companies'].values():
                for wallet in company_wallets:
                    wallet_key = f"{wallet['name']}"
                    wallet_data[wallet_key] = {
                        'name': wallet['name'],
                        'address': wallet['address'],
                        'company': wallet.get('company', 'Unknown')
                    }

            # Parse inputs from command arguments
            inputs = self.parse_check_arguments(command_args)
            
            if not inputs:
                # Check all wallets
                wallets_to_check = {info['name']: info['address'] for info in wallet_data.values()}
                not_found = []
            else:
                # Resolve inputs to wallets
                wallets_to_check, not_found = self.resolve_wallets_to_check(inputs, wallet_data)
                
                # If no valid wallets found but we had inputs, show error
                if not wallets_to_check and not_found:
                    error_card = self._create_not_found_error_card(not_found, wallet_data)
                    await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                    return False

            # Show "checking..." message
            checking_card = self._create_checking_card(len(wallets_to_check))
            await context.topic_manager.send_command_response(checking_card, msg_type="interactive")

            # Fetch balances with timeout to prevent hanging
            logger.info(f"Fetching balances for {len(wallets_to_check)} wallets...")
            
            try:
                # Use asyncio.to_thread with timeout to prevent hanging
                balances = await asyncio.wait_for(
                    asyncio.to_thread(self.balance_service.fetch_multiple_balances, wallets_to_check),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error("⏰ Balance fetch timed out after 30 seconds")
                timeout_card = self._create_timeout_error_card()
                await context.topic_manager.send_command_response(timeout_card, msg_type="interactive")
                return False

            # Process results and create table
            successful_checks = sum(1 for balance in balances.values() if balance is not None)
            
            if successful_checks == 0:
                error_card = self._create_fetch_error_card()
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                return False

            # Create the beautiful table card matching your screenshot
            time_str = self.balance_service.get_current_gmt_time()
            table_card = self._create_balance_table_card(balances, time_str, not_found)
            await context.topic_manager.send_command_response(table_card, msg_type="interactive")

            logger.info(f"✅ Check command completed for user: {user_id}, {successful_checks}/{len(wallets_to_check)} successful")
            return True

        except Exception as e:
            logger.error(f"❌ Error in check command: {e}")
            # Fallback to text message
            fallback_message = f"❌ **Error checking balances:** {str(e)}"
            await context.topic_manager.send_command_response(fallback_message)
            return False
        
        finally:
            # CRITICAL: Always unlock execution in finally block
            _CHECK_EXECUTION_LOCK = False
            logger.info(f"🔓 Check command UNLOCKED - Execution finished for user {context.sender_id}")

    def _create_balance_table_card(self, balances: Dict[str, Decimal], time_str: str, not_found: List[str]) -> dict:
        """Create the beautiful balance table card matching your screenshot."""
        
        # Calculate totals
        total_wallets = len(balances)
        successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
        grand_total = sum(successful_balances.values())
        
        # Build table rows
        table_rows = []
        
        # Sort wallets by group then by name (matching your screenshot)
        wallet_list = []
        for wallet_name, balance in successful_balances.items():
            if balance is not None:
                group = self.balance_service.extract_wallet_group(wallet_name)
                wallet_list.append((group, wallet_name, balance))
        
        # Sort by group, then by wallet name
        wallet_list.sort(key=lambda x: (x[0], x[1]))
        
        # Create table content for the card
        table_content = "| Group | Wallet Name | Amount (USDT) |\n"
        table_content += "|-------|-------------|---------------|\n"
        
        for group, wallet_name, balance in wallet_list:
            # Format balance with commas
            balance_str = f"{balance:,.2f}"
            table_content += f"| {group} | {wallet_name} | {balance_str} |\n"
        
        # Add total row
        table_content += "|-------|-------------|---------------|\n"
        table_content += f"| **TOTAL** | | **{grand_total:,.2f}** |"
        
        # Build the card elements
        elements = [
            # Header info
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "🤖 **Wallet Balance Check**"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"⏰ **Time:** {time_str} GMT+7"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"📊 **Total wallets checked:** {total_wallets}"
                }
            },
            
            # Wallet Balances header
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**Wallet Balances:**"
                }
            },
            
            # The table
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": table_content
                }
            }
        ]
        
        # Add not found notice if any
        if not_found:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"❌ **Not found:** {', '.join(not_found)}"
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
                    "content": "🤖 Wallet Balance Check"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": f"Total: {grand_total:,.2f} USDT"
                }
            },
            "elements": elements
        }

    def _create_checking_card(self, wallet_count: int) -> dict:
        """Create 'checking...' status card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🔄 Checking Balances..."
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🔄 **Fetching balances for {wallet_count} wallets...**\n\nThis may take a few seconds."
                    }
                }
            ]
        }

    def _create_no_wallets_card(self) -> dict:
        """Create no wallets configured card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ No Wallets Configured"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **No wallets configured**\n\nUse **/add** to add your first wallet."
                    }
                }
            ]
        }

    def _create_not_found_error_card(self, not_found: List[str], wallet_data: Dict) -> dict:
        """Create wallet not found error card."""
        available_names = list(wallet_data.keys())[:5]
        if len(wallet_data) > 5:
            available_names.append("...")
        
        error_content = f"❌ **Wallet name(s) not found:** {', '.join(not_found)}\n\n"
        error_content += f"**Available wallet names:**\n{', '.join(available_names)}\n\n"
        error_content += "Use **/list** to see all wallets or provide TRC20 addresses directly."
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Wallets Not Found"
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

    def _create_fetch_error_card(self) -> dict:
        """Create balance fetch error card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Balance Fetch Failed"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **Unable to fetch any wallet balances.**\n\nPlease check your network connection and try again."
                    }
                }
            ]
        }

    def _create_timeout_error_card(self) -> dict:
        """Create timeout error card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "⏰ Request Timeout"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⏰ **Request timed out after 30 seconds.**\n\nPlease try again. If the issue persists, there may be network connectivity problems."
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
                        "content": "🚫 **Check command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")