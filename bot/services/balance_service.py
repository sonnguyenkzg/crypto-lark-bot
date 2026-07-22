#!/usr/bin/env python3
"""
Balance Service - USDT Balance Fetcher (Following Telegram Bot Pattern)
Save as: bot/services/balance_service.py
"""

import requests
import logging
import os
import time as _time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from bot.services.chain_detector import canonical_address

logger = logging.getLogger(__name__)

class BalanceService:
    """Service for checking USDT wallet balances across multiple chains (TRC20, ERC20)."""

    def __init__(self):
        # Configuration constants
        self.API_TIMEOUT = 10  # seconds for API requests
        self.USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # Official USDT TRC20 contract
        self.USDT_ERC20_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"  # Official USDT ERC20 contract
        self.GMT_OFFSET = 7  # GMT+7 timezone offset

        # Maintain backward compatibility
        self.USDT_CONTRACT = self.USDT_TRC20_CONTRACT
    
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

    def get_usdt_erc20_balance(self, address: str) -> Optional[Decimal]:
        """
        Fetches the USDT ERC20 balance for a given Ethereum address using the Etherscan API.
        Handles network errors and unexpected API responses.

        Args:
            address (str): The Ethereum wallet address to query (should start with '0x').

        Returns:
            Optional[Decimal]: The USDT balance as a Decimal object, or None on error.
        """
        import os

        api_key = os.getenv('ETHEREUM_API_KEY')
        if not api_key:
            logger.warning(f"ETHEREUM_API_KEY not configured - cannot fetch ERC20 balance")
            return None

        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": "1",  # Ethereum mainnet
            "module": "account",
            "action": "tokenbalance",
            "contractaddress": self.USDT_ERC20_CONTRACT,
            "address": address,
            "tag": "latest",
            "apikey": api_key
        }

        try:
            resp = requests.get(url, params=params, timeout=self.API_TIMEOUT)
            resp.raise_for_status()

            data = resp.json()

            # Etherscan returns status "1" for success
            if data.get('status') == '1' and data.get('result'):
                raw_balance_str = data['result']
                try:
                    raw_balance = Decimal(raw_balance_str)
                except Exception as e:
                    logger.error(f"Error converting ERC20 balance '{raw_balance_str}' for {address}: {e}")
                    return Decimal('0.0')

                # USDT ERC20 also has 6 decimal places (same as TRC20)
                return raw_balance / Decimal('1000000')

            elif data.get('message') == 'NOTOK':
                error_result = data.get('result', 'Unknown error')
                logger.error(f"Etherscan API error for {address}: {error_result}")
                return None
            else:
                # Status "0" might still be valid (e.g., zero balance)
                logger.info(f"No USDT ERC20 balance found for address {address}")
                return Decimal('0.0')

        except requests.exceptions.Timeout:
            logger.error(f"Request timed out for ERC20 address {address}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for ERC20 address {address}")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for ERC20 address {address}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for ERC20 address {address}: {e}")
        except ValueError as e:
            logger.error(f"Error decoding JSON for ERC20 address {address}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching ERC20 balance for address {address}: {e}")

        return None

    def get_balance(self, address: str, chain: str) -> Optional[Decimal]:
        """
        Unified balance fetching method that routes to appropriate chain handler.

        Args:
            address: Wallet address
            chain: Chain identifier ("TRC20" or "ERC20")

        Returns:
            Optional[Decimal]: Balance or None on error
        """
        if chain == "TRC20":
            return self.get_usdt_trc20_balance(address)
        elif chain == "ERC20":
            return self.get_usdt_erc20_balance(address)
        else:
            logger.error(f"Unsupported chain: {chain}")
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
    
    def fetch_multiple_balances(self, wallets_to_check: Dict[str, Dict]) -> Dict[str, Optional[Decimal]]:
        """
        Fetch balances for multiple wallets across multiple chains.

        Args:
            wallets_to_check: Dictionary mapping display names to wallet info dicts.
                             Can be:
                             - {'display_name': {'address': '...', 'chain': '...'}}  (new format)
                             - {'display_name': 'address_string'}  (legacy format - assumes TRC20)

        Returns:
            Dict[str, Optional[Decimal]]: Dictionary mapping display names to balances
        """
        balances = {}
        total_wallets = len(wallets_to_check)
        logger.info(f"Starting to fetch balances for {total_wallets} wallets...")

        for i, (display_name, wallet_info) in enumerate(wallets_to_check.items(), 1):
            try:
                # Handle both new dict format and legacy string format
                if isinstance(wallet_info, dict):
                    address = wallet_info.get('address')
                    chain = wallet_info.get('chain', 'TRC20')  # Default to TRC20 for backward compatibility
                else:
                    # Legacy format: wallet_info is just the address string
                    address = wallet_info
                    chain = 'TRC20'

                logger.info(f"Fetching {chain} balance {i}/{total_wallets} for {display_name}...")
                balance = self.get_balance(address, chain)
                balances[display_name] = balance

                if balance is not None:
                    logger.info(f"✅ {display_name} ({chain}): {balance} USDT")
                else:
                    logger.warning(f"❌ Failed to fetch {chain} balance for {display_name}")

            except Exception as e:
                logger.error(f"❌ Error fetching balance for {display_name}: {e}")
                balances[display_name] = None

        logger.info(f"Completed fetching balances for {total_wallets} wallets")
        return balances
    
    def _net_from_transfers(self, transfers, address) -> Decimal:
        """Signed net USDT (already in USDT units) over SUCCESS transfers.
        +amount when I'm the recipient, -amount when I'm the sender."""
        me = canonical_address(address)
        net = Decimal(0)
        for t in transfers:
            if not t.get("success", True):
                continue
            amt = t["amount"]
            if canonical_address(t.get("to", "")) == me:
                net += amt
            if canonical_address(t.get("from", "")) == me:
                net -= amt
        return net

    def _fetch_transfers_after(self, address, chain, cutoff_ms):
        """USDT transfers with block time > cutoff_ms, windowed (cutoff, now].
        Returns normalized [{from,to,amount(Decimal USDT),success}] or None on error."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        out = []
        try:
            if chain == "TRC20":
                headers = {}
                key = os.getenv("TRON_API_KEY")
                if key:
                    headers["TRON-PRO-API-KEY"] = key
                start = 0
                while True:
                    params = {"relatedAddress": address, "contract_address": self.USDT_TRC20_CONTRACT,
                              "start_timestamp": cutoff_ms + 1, "end_timestamp": now_ms,
                              "limit": 50, "start": start, "sort": "-timestamp"}
                    r = requests.get("https://apilist.tronscanapi.com/api/token_trc20/transfers",
                                     params=params, headers=headers, timeout=self.API_TIMEOUT)
                    r.raise_for_status()
                    ts = r.json().get("token_transfers", []) or []
                    for t in ts:
                        out.append({
                            "from": t.get("from_address", ""), "to": t.get("to_address", ""),
                            "amount": Decimal(t.get("quant", "0")) / Decimal(1_000_000),
                            "success": t.get("finalResult") == "SUCCESS" and t.get("contractRet") == "SUCCESS",
                        })
                    if len(ts) < 50:
                        break
                    start += 50
                    _time.sleep(0.2)
                return out
            elif chain == "ERC20":
                key = os.getenv("ETHEREUM_API_KEY")
                if not key:
                    return None
                cutoff_s = cutoff_ms // 1000
                page = 1
                while True:
                    params = {"chainid": "1", "module": "account", "action": "tokentx",
                              "contractaddress": self.USDT_ERC20_CONTRACT, "address": address,
                              "page": page, "offset": 100, "sort": "desc", "apikey": key}
                    r = requests.get("https://api.etherscan.io/v2/api", params=params, timeout=self.API_TIMEOUT)
                    r.raise_for_status()
                    d = r.json()
                    txs = d.get("result") or []
                    if d.get("status") != "1" or not txs:
                        break
                    stop = False
                    for t in txs:
                        if int(t["timeStamp"]) <= cutoff_s:
                            stop = True
                            break
                        out.append({"from": t.get("from", ""), "to": t.get("to", ""),
                                    "amount": Decimal(t.get("value", "0")) / Decimal(1_000_000),
                                    "success": True})
                    if stop or len(txs) < 100:
                        break
                    page += 1
                    _time.sleep(0.2)
                return out
            else:
                return None
        except Exception as e:
            logger.error(f"transfer fetch failed for {address[:10]}... ({chain}): {e}")
            return None

    def get_balance_at(self, address, chain, cutoff_ms):
        """Balance at cutoff = current live balance - net transfers after cutoff.
        Returns Decimal, or None if either fetch fails."""
        current = self.get_balance(address, chain)
        if current is None:
            return None
        transfers = self._fetch_transfers_after(address, chain, cutoff_ms)
        if transfers is None:
            return None
        return current - self._net_from_transfers(transfers, address)

    def extract_wallet_group(self, wallet_name: str) -> str:
        """Extract group code from wallet name (e.g., 'KZP 96G1' -> 'KZP')."""
        parts = wallet_name.split()
        if len(parts) >= 1:
            return parts[0]  # First part (e.g., "KZP")

        # Fallback: use first 3 characters
        return wallet_name[:3].upper()