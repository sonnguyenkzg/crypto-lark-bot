#!/usr/bin/env python3
"""
Balance Service - USDT Balance Fetcher (Following Telegram Bot Pattern)
Save as: bot/services/balance_service.py
"""

import requests
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class BalanceService:
    """Service for checking USDT TRC20 wallet balances."""
    
    def __init__(self):
        # Configuration constants (same as your Telegram bot)
        self.API_TIMEOUT = 10  # seconds for API requests
        self.USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # Official USDT TRC20 contract
        self.GMT_OFFSET = 7  # GMT+7 timezone offset
    
    def get_usdt_trc20_balance(self, address: str) -> Optional[Decimal]:
        """
        Fetches the USDT TRC20 balance for a given Tron address using the Tronscan API.
        Handles network errors and unexpected API responses.

        Args:
            address (str): The Tron wallet address to query.

        Returns:
            Optional[Decimal]: The USDT balance as a Decimal object, or None on error.
        """
        url = f"https://apilist.tronscanapi.com/api/account/tokens?address={address}"
        
        # Add API key header if available
        headers = {}
        import os
        api_key = os.getenv('TRON_API_KEY')  # Note: you said TRON_API_KEY, but Tronscan expects TRONSCAN_API_KEY
        if api_key:
            headers['TRON-PRO-API-KEY'] = api_key
        
        try:
            resp = requests.get(url, headers=headers, timeout=self.API_TIMEOUT)  # Add headers parameter
            resp.raise_for_status()

            # Rest of your method remains exactly the same
            data = resp.json().get("data", [])
            if not data:
                logger.warning(f"No token data found for address {address}")
                return Decimal('0.0')

            for token in data:
                if token.get("tokenId") == self.USDT_CONTRACT:
                    raw_balance_str = token.get("balance", "0")
                    try:
                        raw_balance = Decimal(raw_balance_str)
                    except Exception as e:
                        logger.error(f"Error converting balance '{raw_balance_str}' for {address}: {e}")
                        return Decimal('0.0')

                    # USDT TRC20 has 6 decimal places (1,000,000 sun per USDT)
                    return raw_balance / Decimal('1000000')
            
            # USDT token not found for this address
            return Decimal('0.0')

        except requests.exceptions.Timeout:
            logger.error(f"Request timed out for address {address}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for address {address}")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for address {address}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for address {address}: {e}")
        except ValueError as e:
            logger.error(f"Error decoding JSON for address {address}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching balance for address {address}: {e}")
        
        return None
    
    def validate_trc20_address(self, address: str) -> bool:
        """
        Validate if an address is a valid TRC20 address.
        
        Args:
            address: The address to validate
            
        Returns:
            bool: True if valid TRC20 address, False otherwise
        """
        if not address or not isinstance(address, str):
            return False
        
        # TRC20 addresses start with 'T' and are typically 34 characters (but can be 33-35)
        return address.startswith('T') and 33 <= len(address) <= 35
    
    def get_current_gmt_time(self) -> str:
        """
        Get current time formatted in GMT+7.
        
        Returns:
            str: Formatted time string
        """
        gmt_now = datetime.now(timezone(timedelta(hours=self.GMT_OFFSET)))
        return gmt_now.strftime("%Y-%m-%d %H:%M")
    
    def fetch_multiple_balances(self, wallets_to_check: Dict[str, str]) -> Dict[str, Optional[Decimal]]:
        """
        Fetch balances for multiple wallets.
        
        Args:
            wallets_to_check: Dictionary mapping display names to addresses
            
        Returns:
            Dict[str, Optional[Decimal]]: Dictionary mapping display names to balances
        """
        balances = {}
        total_wallets = len(wallets_to_check)
        logger.info(f"Starting to fetch balances for {total_wallets} wallets...")
        
        for i, (display_name, address) in enumerate(wallets_to_check.items(), 1):
            try:
                logger.info(f"Fetching balance {i}/{total_wallets} for {display_name}...")
                balance = self.get_usdt_trc20_balance(address)
                balances[display_name] = balance
                
                if balance is not None:
                    logger.info(f"✅ {display_name}: {balance} USDT")
                else:
                    logger.warning(f"❌ Failed to fetch balance for {display_name}")
                    
            except Exception as e:
                logger.error(f"❌ Error fetching balance for {display_name}: {e}")
                balances[display_name] = None
        
        logger.info(f"Completed fetching balances for {total_wallets} wallets")
        return balances
    
    def extract_wallet_group(self, wallet_name: str) -> str:
        """Extract group code from wallet name (e.g., 'KZP 96G1' -> 'KZP')."""
        parts = wallet_name.split()
        if len(parts) >= 1:
            return parts[0]  # First part (e.g., "KZP")
        
        # Fallback: use first 3 characters
        return wallet_name[:3].upper()