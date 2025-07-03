#!/usr/bin/env python3
"""
Lark Bot Wallet Service Module
Handles crypto wallet operations: balance checking, wallet management, and API integration
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

@dataclass
class WalletBalance:
    """Represents wallet balance information."""
    wallet_name: str
    address: str
    balance_trx: float
    balance_usd: float
    token_balances: Dict[str, float]
    last_updated: datetime
    error: Optional[str] = None

@dataclass
class WalletInfo:
    """Represents wallet configuration."""
    name: str
    company: str
    address: str

class TronAPIClient:
    """
    Client for interacting with TRON blockchain APIs.
    Supports multiple API providers for redundancy.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = None
        
        # API endpoints (in order of preference)
        self.api_endpoints = [
            "https://api.trongrid.io",
            "https://api.tronstack.io", 
            "https://api.tronscan.org",
        ]
        
        # Rate limiting
        self.last_request_time = None
        self.min_request_interval = 0.2  # 200ms between requests
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Implement basic rate limiting."""
        if self.last_request_time:
            elapsed = datetime.now().timestamp() - self.last_request_time
            if elapsed < self.min_request_interval:
                await asyncio.sleep(self.min_request_interval - elapsed)
        
        self.last_request_time = datetime.now().timestamp()
    
    async def _make_request(self, endpoint: str, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make API request with error handling and retries.
        
        Args:
            endpoint: API endpoint base URL
            path: API path
            params: Query parameters
            
        Returns:
            API response data
        """
        await self._rate_limit()
        
        url = f"{endpoint}{path}"
        headers = {}
        
        if self.api_key and "trongrid" in endpoint:
            headers["TRON-PRO-API-KEY"] = self.api_key
        
        try:
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except asyncio.TimeoutError:
            raise Exception("Request timeout")
        except Exception as e:
            raise Exception(f"Request failed: {e}")
    
    async def get_account_info(self, address: str) -> Dict[str, Any]:
        """
        Get account information for a TRON address.
        
        Args:
            address: TRON wallet address
            
        Returns:
            Account information
        """
        for endpoint in self.api_endpoints:
            try:
                if "trongrid" in endpoint:
                    path = f"/v1/accounts/{address}"
                    data = await self._make_request(endpoint, path)
                    
                    if data.get("success"):
                        return data.get("data", [{}])[0] if data.get("data") else {}
                    
                elif "tronscan" in endpoint:
                    path = f"/api/account"
                    params = {"address": address}
                    data = await self._make_request(endpoint, path, params)
                    return data
                
                else:
                    # Try generic format
                    path = f"/v1/accounts/{address}"
                    data = await self._make_request(endpoint, path)
                    return data
                    
            except Exception as e:
                logger.warning(f"⚠️ API endpoint {endpoint} failed: {e}")
                continue
        
        raise Exception("All API endpoints failed")
    
    async def get_account_balance(self, address: str) -> Tuple[float, Dict[str, float]]:
        """
        Get TRX balance and token balances for an address.
        
        Args:
            address: TRON wallet address
            
        Returns:
            Tuple of (TRX balance, token balances dict)
        """
        try:
            account_info = await self.get_account_info(address)
            
            # Extract TRX balance (in SUN, convert to TRX)
            trx_balance = 0.0
            if account_info.get("balance"):
                trx_balance = account_info["balance"] / 1_000_000  # Convert SUN to TRX
            
            # Extract token balances
            token_balances = {}
            
            # TRC20 tokens
            if account_info.get("trc20"):
                for token_addr, token_info in account_info["trc20"].items():
                    if isinstance(token_info, dict):
                        symbol = token_info.get("symbol", token_addr[:8])
                        balance = float(token_info.get("balance", 0))
                        decimals = int(token_info.get("decimals", 6))
                        
                        # Convert based on decimals
                        actual_balance = balance / (10 ** decimals)
                        if actual_balance > 0:
                            token_balances[symbol] = actual_balance
            
            # Alternative token format
            if account_info.get("tokens"):
                for token in account_info["tokens"]:
                    if isinstance(token, dict):
                        symbol = token.get("tokenAbbr", token.get("symbol", "UNKNOWN"))
                        balance = float(token.get("balance", 0))
                        decimals = int(token.get("tokenDecimal", 6))
                        
                        actual_balance = balance / (10 ** decimals)
                        if actual_balance > 0:
                            token_balances[symbol] = actual_balance
            
            return trx_balance, token_balances
            
        except Exception as e:
            logger.error(f"❌ Error getting balance for {address}: {e}")
            raise

class WalletService:
    """
    Main wallet service for managing crypto wallets and balances.
    """
    
    def __init__(self, config_class):
        self.config = config_class
        self.tron_client = None
        self.balance_cache = {}
        self.cache_ttl = 300  # 5 minutes cache
        
    async def __aenter__(self):
        """Async context manager entry."""
        api_key = getattr(self.config, 'TRON_API_KEY', None)
        self.tron_client = TronAPIClient(api_key)
        await self.tron_client.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.tron_client:
            await self.tron_client.__aexit__(exc_type, exc_val, exc_tb)
    
    def load_wallets(self) -> Dict[str, WalletInfo]:
        """
        Load wallet configurations.
        
        Returns:
            Dictionary of wallet configurations
        """
        try:
            raw_wallets = self.config.load_wallets()
            wallets = {}
            
            for wallet_id, wallet_data in raw_wallets.items():
                wallets[wallet_id] = WalletInfo(
                    name=wallet_data.get("wallet", wallet_id),
                    company=wallet_data.get("company", "Unknown"),
                    address=wallet_data["address"]
                )
            
            logger.info(f"✅ Loaded {len(wallets)} wallet configurations")
            return wallets
            
        except Exception as e:
            logger.error(f"❌ Error loading wallets: {e}")
            return {}
    
    def save_wallets(self, wallets: Dict[str, WalletInfo]) -> bool:
        """
        Save wallet configurations.
        
        Args:
            wallets: Dictionary of wallet configurations
            
        Returns:
            True if saved successfully
        """
        try:
            raw_wallets = {}
            
            for wallet_id, wallet_info in wallets.items():
                raw_wallets[wallet_id] = {
                    "wallet": wallet_info.name,
                    "company": wallet_info.company,
                    "address": wallet_info.address
                }
            
            return self.config.save_wallets(raw_wallets)
            
        except Exception as e:
            logger.error(f"❌ Error saving wallets: {e}")
            return False
    
    async def get_wallet_balance(self, wallet_info: WalletInfo, use_cache: bool = True) -> WalletBalance:
        """
        Get balance for a specific wallet.
        
        Args:
            wallet_info: Wallet information
            use_cache: Whether to use cached results
            
        Returns:
            Wallet balance information
        """
        address = wallet_info.address
        cache_key = f"balance_{address}"
        
        # Check cache
        if use_cache and cache_key in self.balance_cache:
            cached_balance, cached_time = self.balance_cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                logger.info(f"📋 Using cached balance for {wallet_info.name}")
                return cached_balance
        
        # Fetch fresh balance
        try:
            logger.info(f"🔍 Fetching balance for {wallet_info.name} ({address[:10]}...)")
            
            trx_balance, token_balances = await self.tron_client.get_account_balance(address)
            
            # Calculate USD value (simplified - would need price API in production)
            # For now, using approximate values
            trx_usd_price = 0.08  # Approximate TRX price
            balance_usd = trx_balance * trx_usd_price
            
            # Add major token USD values
            token_prices = {"USDT": 1.0, "USDC": 1.0, "BTC": 45000, "ETH": 2500}
            for token, balance in token_balances.items():
                if token in token_prices:
                    balance_usd += balance * token_prices[token]
            
            wallet_balance = WalletBalance(
                wallet_name=wallet_info.name,
                address=address,
                balance_trx=trx_balance,
                balance_usd=balance_usd,
                token_balances=token_balances,
                last_updated=datetime.now()
            )
            
            # Cache the result
            self.balance_cache[cache_key] = (wallet_balance, datetime.now())
            
            logger.info(f"✅ Balance fetched for {wallet_info.name}: {trx_balance:.2f} TRX (${balance_usd:.2f})")
            return wallet_balance
            
        except Exception as e:
            logger.error(f"❌ Error fetching balance for {wallet_info.name}: {e}")
            
            # Return error balance
            return WalletBalance(
                wallet_name=wallet_info.name,
                address=address,
                balance_trx=0.0,
                balance_usd=0.0,
                token_balances={},
                last_updated=datetime.now(),
                error=str(e)
            )
    
    async def get_all_balances(self, use_cache: bool = True) -> List[WalletBalance]:
        """
        Get balances for all configured wallets.
        
        Args:
            use_cache: Whether to use cached results
            
        Returns:
            List of wallet balances
        """
        wallets = self.load_wallets()
        if not wallets:
            logger.warning("⚠️ No wallets configured")
            return []
        
        logger.info(f"🔍 Fetching balances for {len(wallets)} wallets...")
        
        # Fetch balances concurrently (with limit to avoid rate limiting)
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
        
        async def fetch_with_semaphore(wallet_info):
            async with semaphore:
                return await self.get_wallet_balance(wallet_info, use_cache)
        
        tasks = [fetch_with_semaphore(wallet_info) for wallet_info in wallets.values()]
        balances = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        valid_balances = []
        for i, result in enumerate(balances):
            if isinstance(result, Exception):
                wallet_name = list(wallets.values())[i].name
                logger.error(f"❌ Failed to fetch balance for {wallet_name}: {result}")
            else:
                valid_balances.append(result)
        
        logger.info(f"✅ Successfully fetched {len(valid_balances)}/{len(wallets)} wallet balances")
        return valid_balances
    
    def add_wallet(self, wallet_id: str, name: str, company: str, address: str) -> bool:
        """
        Add a new wallet configuration.
        
        Args:
            wallet_id: Unique wallet identifier
            name: Wallet display name
            company: Company/owner name
            address: Wallet address
            
        Returns:
            True if added successfully
        """
        try:
            wallets = self.load_wallets()
            
            if wallet_id in wallets:
                logger.warning(f"⚠️ Wallet {wallet_id} already exists")
                return False
            
            wallets[wallet_id] = WalletInfo(name=name, company=company, address=address)
            
            if self.save_wallets(wallets):
                logger.info(f"✅ Added wallet: {wallet_id} ({name})")
                return True
            else:
                logger.error(f"❌ Failed to save wallet: {wallet_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error adding wallet {wallet_id}: {e}")
            return False
    
    def remove_wallet(self, wallet_id: str) -> bool:
        """
        Remove a wallet configuration.
        
        Args:
            wallet_id: Wallet identifier to remove
            
        Returns:
            True if removed successfully
        """
        try:
            wallets = self.load_wallets()
            
            if wallet_id not in wallets:
                logger.warning(f"⚠️ Wallet {wallet_id} not found")
                return False
            
            removed_wallet = wallets.pop(wallet_id)
            
            if self.save_wallets(wallets):
                logger.info(f"✅ Removed wallet: {wallet_id} ({removed_wallet.name})")
                # Clear cache for removed wallet
                cache_key = f"balance_{removed_wallet.address}"
                self.balance_cache.pop(cache_key, None)
                return True
            else:
                logger.error(f"❌ Failed to save after removing wallet: {wallet_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error removing wallet {wallet_id}: {e}")
            return False
    
    def clear_cache(self):
        """Clear all cached balances."""
        self.balance_cache.clear()
        logger.info("🗑️ Balance cache cleared")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache information."""
        return {
            "cached_items": len(self.balance_cache),
            "cache_ttl": self.cache_ttl,
            "cached_addresses": [key.replace("balance_", "")[:10] + "..." for key in self.balance_cache.keys()]
        }

# Mock classes for testing
class MockConfig:
    """Mock config for testing."""
    
    TRON_API_KEY = "test_api_key"
    
    @classmethod
    def load_wallets(cls):
        return {
            "TEST_WALLET": {
                "wallet": "Test Wallet",
                "company": "Test Company", 
                "address": "TTest123Address"
            }
        }
    
    @classmethod
    def save_wallets(cls, wallets):
        return True

# Testing functions
async def test_wallet_loading():
    """Test wallet loading functionality."""
    print("🧪 Testing Wallet Loading...")
    
    try:
        service = WalletService(MockConfig)
        wallets = service.load_wallets()
        
        assert len(wallets) == 1
        assert "TEST_WALLET" in wallets
        
        wallet = wallets["TEST_WALLET"]
        assert wallet.name == "Test Wallet"
        assert wallet.company == "Test Company"
        assert wallet.address == "TTest123Address"
        
        print("✅ Wallet loading test passed")
        return True
        
    except Exception as e:
        print(f"❌ Wallet loading test failed: {e}")
        return False

async def test_wallet_management():
    """Test wallet add/remove functionality."""
    print("🧪 Testing Wallet Management...")
    
    try:
        service = WalletService(MockConfig)
        
        # Test adding wallet
        success = service.add_wallet("NEW_WALLET", "New Wallet", "New Company", "TNewAddress123")
        assert success
        
        # Test removing wallet  
        success = service.remove_wallet("TEST_WALLET")
        assert success
        
        # Test removing non-existent wallet
        success = service.remove_wallet("NON_EXISTENT")
        assert not success
        
        print("✅ Wallet management test passed")
        return True
        
    except Exception as e:
        print(f"❌ Wallet management test failed: {e}")
        return False

async def test_cache_functionality():
    """Test balance caching."""
    print("🧪 Testing Cache Functionality...")
    
    try:
        service = WalletService(MockConfig)
        
        # Test cache info
        cache_info = service.get_cache_info()
        assert cache_info["cached_items"] == 0
        assert cache_info["cache_ttl"] == 300
        
        # Test cache clearing
        service.clear_cache()
        
        print("✅ Cache functionality test passed")
        return True
        
    except Exception as e:
        print(f"❌ Cache functionality test failed: {e}")
        return False

def test_wallet_info_dataclass():
    """Test WalletInfo dataclass."""
    print("🧪 Testing WalletInfo Dataclass...")
    
    try:
        wallet = WalletInfo(
            name="Test Wallet",
            company="Test Company",
            address="TTestAddress123"
        )
        
        assert wallet.name == "Test Wallet"
        assert wallet.company == "Test Company"
        assert wallet.address == "TTestAddress123"
        
        print("✅ WalletInfo dataclass test passed")
        return True
        
    except Exception as e:
        print(f"❌ WalletInfo dataclass test failed: {e}")
        return False

def test_wallet_balance_dataclass():
    """Test WalletBalance dataclass."""
    print("🧪 Testing WalletBalance Dataclass...")
    
    try:
        balance = WalletBalance(
            wallet_name="Test Wallet",
            address="TTestAddress123",
            balance_trx=100.5,
            balance_usd=8.04,
            token_balances={"USDT": 50.0},
            last_updated=datetime.now()
        )
        
        assert balance.wallet_name == "Test Wallet"
        assert balance.balance_trx == 100.5
        assert balance.balance_usd == 8.04
        assert balance.token_balances["USDT"] == 50.0
        assert balance.error is None
        
        print("✅ WalletBalance dataclass test passed")
        return True
        
    except Exception as e:
        print(f"❌ WalletBalance dataclass test failed: {e}")
        return False

async def run_all_tests():
    """Run all wallet service tests."""
    print("🚀 Running Wallet Service Tests...")
    print("=" * 50)
    
    async_tests = [
        test_wallet_loading,
        test_wallet_management,
        test_cache_functionality
    ]
    
    sync_tests = [
        test_wallet_info_dataclass,
        test_wallet_balance_dataclass
    ]
    
    results = []
    
    # Run async tests
    for test in async_tests:
        result = await test()
        results.append(result)
        print()
    
    # Run sync tests
    for test in sync_tests:
        result = test()
        results.append(result)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Wallet Service is ready.")
        print("\n💡 Wallet Service features:")
        print("- TRON blockchain balance checking")
        print("- Multiple API endpoint support with failover")
        print("- TRX and TRC20 token balance detection")
        print("- Wallet configuration management")
        print("- Balance caching with TTL")
        print("- Concurrent balance fetching with rate limiting")
        print("- USD value estimation")
    else:
        print("❌ Some tests failed. Please check implementation.")
    
    return passed == total

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())