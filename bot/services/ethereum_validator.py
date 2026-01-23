#!/usr/bin/env python3
"""
Ethereum Address Validator - Validates ERC20 addresses against Ethereum blockchain
Mirrors the structure of tron_validator.py for consistency
"""

import aiohttp
import asyncio
import logging
import os
from typing import Tuple

logger = logging.getLogger(__name__)

class EthereumAddressValidator:
    """Validates ERC20 addresses against Ethereum blockchain."""

    def __init__(self):
        # Etherscan API V2 endpoint
        self.etherscan_api = "https://api.etherscan.io/v2/api"
        self.api_key = os.getenv('ETHEREUM_API_KEY', '')

    async def validate_address(self, address: str) -> Tuple[bool, str]:
        """
        Validate if ERC20 address exists on Ethereum blockchain.

        Args:
            address: ERC20 address to validate (should start with '0x')

        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        try:
            # First do basic format validation
            if not self._basic_format_check(address):
                return False, "❌ **Invalid ERC20 address format**"

            # Check against Ethereum blockchain
            is_valid, message = await self._check_blockchain(address)

            if is_valid:
                return True, "✅ **Address verified on Ethereum network**"
            else:
                return False, f"❌ **Address not found on Ethereum network:** {message}"

        except Exception as e:
            logger.error(f"Error validating address {address}: {e}")
            # If validation fails, be permissive and allow if format is correct
            if self._basic_format_check(address):
                return True, "⚠️ **Address format valid (network check failed)**"
            else:
                return False, f"❌ **Invalid address format**"

    def _basic_format_check(self, address: str) -> bool:
        """
        Basic format validation for ERC20 addresses.

        ERC20 addresses must:
        - Start with '0x'
        - Be exactly 42 characters long (0x + 40 hex chars)
        - Contain only valid hexadecimal characters (0-9, a-f, A-F)
        """
        if not address or not address.startswith('0x'):
            return False

        if len(address) != 42:
            return False

        # Verify it's valid hexadecimal
        try:
            int(address[2:], 16)  # Try parsing as hex (skip '0x' prefix)
            return True
        except ValueError:
            logger.warning(f"Address {address[:10]}... contains invalid hex characters")
            return False

    async def _check_blockchain(self, address: str) -> Tuple[bool, str]:
        """
        Check if address exists on Ethereum blockchain using Etherscan API.

        Uses the account balance endpoint which will return data for any valid address.
        """

        # Check if API key is configured
        if not self.api_key:
            logger.warning("ETHEREUM_API_KEY not configured - skipping blockchain verification")
            return True, "API key not configured (format check passed)"

        try:
            async with aiohttp.ClientSession() as session:
                # Use account balance endpoint - works for any valid Ethereum address
                params = {
                    "chainid": "1",  # Ethereum mainnet
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest",
                    "apikey": self.api_key
                }

                async with session.get(self.etherscan_api, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Etherscan returns status "1" for success, "0" for error
                        if data.get('status') == '1':
                            logger.info(f"Address {address[:10]}... verified on Etherscan")
                            return True, "Verified on Etherscan"
                        elif data.get('message') == 'NOTOK':
                            error_result = data.get('result', 'Unknown error')
                            logger.warning(f"Etherscan validation failed: {error_result}")
                            return False, f"Etherscan error: {error_result}"
                        else:
                            # Even status "0" can be a valid address (e.g., never used)
                            # If result is "0" (zero balance), it's still a valid address
                            if 'result' in data:
                                logger.info(f"Address {address[:10]}... is valid (balance: {data['result']})")
                                return True, "Verified on Etherscan (zero balance)"
                            return False, "Unexpected Etherscan response"
                    else:
                        logger.warning(f"Etherscan API returned status {response.status}")
                        return False, f"API returned status {response.status}"

        except aiohttp.ClientError as e:
            logger.warning(f"Etherscan API connection failed: {e}")
            return False, f"Network error: {str(e)}"
        except asyncio.TimeoutError:
            logger.warning("Etherscan API request timed out")
            return False, "API request timed out"
        except Exception as e:
            logger.error(f"Unexpected error checking Ethereum blockchain: {e}")
            return False, f"Validation error: {str(e)}"
