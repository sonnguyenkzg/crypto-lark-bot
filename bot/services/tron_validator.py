#!/usr/bin/env python3
"""
Tron Address Validator - Validates addresses against real Tron blockchain
Save this as: bot/services/tron_validator.py
"""

import aiohttp
import asyncio
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class TronAddressValidator:
    """Validates TRC20 addresses against Tron blockchain."""
    
    def __init__(self):
        # TronScan API endpoints
        self.tronscan_api = "https://apilist.tronscanapi.com/api/account"
        self.trongrid_api = "https://api.trongrid.io/v1/accounts"
    
    async def validate_address(self, address: str) -> Tuple[bool, str]:
        """
        Validate if TRC20 address exists on Tron blockchain.
        
        Args:
            address: TRC20 address to validate
            
        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        try:
            # First do basic format validation
            if not self._basic_format_check(address):
                return False, "❌ **Invalid TRC20 address format**"
            
            # Check against Tron blockchain
            is_valid, message = await self._check_blockchain(address)
            
            if is_valid:
                return True, "✅ **Address verified on Tron network**"
            else:
                return False, f"❌ **Address not found on Tron network:** {message}"
                
        except Exception as e:
            logger.error(f"Error validating address {address}: {e}")
            # If validation fails, we can choose to allow it (assume it's valid if format is correct)
            # For now, let's be permissive and allow it if format is correct
            if self._basic_format_check(address):
                return True, "⚠️ **Address format valid (network check failed)**"
            else:
                return False, f"❌ **Invalid address format**"
    
    def _basic_format_check(self, address: str) -> bool:
        """Basic format validation."""
        return (
            address.startswith('T') and 
            33 <= len(address) <= 35 and
            address.replace('T', '').isalnum()  # Only alphanumeric characters after T
        )
    
    async def _check_blockchain(self, address: str) -> Tuple[bool, str]:
        """Check if address exists on Tron blockchain."""
        
        # Try TronScan API first
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.tronscan_api}?address={address}"
                
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check if account exists
                        if data and 'address' in data:
                            logger.info(f"Address {address} verified on TronScan")
                            return True, "Verified on TronScan"
                        else:
                            return False, "Address not found on TronScan"
                    else:
                        logger.warning(f"TronScan API returned status {response.status}")
                        
        except Exception as e:
            logger.warning(f"TronScan API failed: {e}")
        
        # Try TronGrid API as backup
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.trongrid_api}/{address}"
                
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # TronGrid returns account info if it exists
                        if data and 'data' in data and len(data['data']) > 0:
                            logger.info(f"Address {address} verified on TronGrid")
                            return True, "Verified on TronGrid"
                        else:
                            return False, "Address not found on TronGrid"
                    else:
                        logger.warning(f"TronGrid API returned status {response.status}")
                        
        except Exception as e:
            logger.warning(f"TronGrid API failed: {e}")
        
        # If all APIs fail, return error
        return False, "Unable to connect to Tron APIs"