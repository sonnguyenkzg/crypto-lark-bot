#!/usr/bin/env python3
"""
Test Script: ERC20 Support Verification
Tests chain detection, validators, and balance fetching for both TRC20 and ERC20
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load test environment
load_dotenv()

# Test addresses
TEST_ADDRESSES = {
    'TRC20_VALID': 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',  # USDT TRC20 contract
    'TRC20_USER': 'TNZJ5wTSMK4oR79CYzy8BGK6LWNmQxcuM8',   # From wallets.json
    'ERC20_VALID': '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT ERC20 contract
    'ERC20_USER': '0x5041ed759Dd4aFc3a72b8192C143F72f4724081A',   # Sample ERC20 address
    'INVALID': 'invalid_address_format'
}

async def test_chain_detection():
    """Test 1: Chain Detection"""
    print("\n" + "=" * 60)
    print("TEST 1: Chain Detection")
    print("=" * 60)

    from bot.services.chain_detector import detect_chain_from_address

    tests = [
        (TEST_ADDRESSES['TRC20_VALID'], 'TRC20'),
        (TEST_ADDRESSES['TRC20_USER'], 'TRC20'),
        (TEST_ADDRESSES['ERC20_VALID'], 'ERC20'),
        (TEST_ADDRESSES['ERC20_USER'], 'ERC20'),
        (TEST_ADDRESSES['INVALID'], None),
    ]

    passed = 0
    for address, expected in tests:
        result = detect_chain_from_address(address)
        status = "✅" if result == expected else "❌"
        print(f"{status} {address[:20]}... → {result} (expected: {expected})")
        if result == expected:
            passed += 1

    print(f"\n📊 Chain Detection: {passed}/{len(tests)} tests passed")
    return passed == len(tests)


async def test_validators():
    """Test 2: Address Validators"""
    print("\n" + "=" * 60)
    print("TEST 2: Address Validators")
    print("=" * 60)

    from bot.services.tron_validator import TronAddressValidator
    from bot.services.ethereum_validator import EthereumAddressValidator

    # Test TRC20 validator
    print("\n🟢 TRC20 Validator:")
    tron_validator = TronAddressValidator()

    trc20_tests = [
        (TEST_ADDRESSES['TRC20_VALID'], True),
        (TEST_ADDRESSES['TRC20_USER'], True),
        (TEST_ADDRESSES['ERC20_VALID'], False),
        (TEST_ADDRESSES['INVALID'], False),
    ]

    trc20_passed = 0
    for address, expected in trc20_tests:
        result = await tron_validator.validate_address(address)
        # Validators return (bool, str), extract bool
        is_valid = result[0] if isinstance(result, tuple) else result
        status = "✅" if is_valid == expected else "❌"
        print(f"  {status} {address[:30]}... → {is_valid} (expected: {expected})")
        if is_valid == expected:
            trc20_passed += 1

    # Test ERC20 validator
    print("\n🔷 ERC20 Validator:")
    eth_validator = EthereumAddressValidator()

    erc20_tests = [
        (TEST_ADDRESSES['ERC20_VALID'], True),
        (TEST_ADDRESSES['ERC20_USER'], True),
        (TEST_ADDRESSES['TRC20_VALID'], False),
        (TEST_ADDRESSES['INVALID'], False),
    ]

    erc20_passed = 0
    for address, expected in erc20_tests:
        result = await eth_validator.validate_address(address)
        # Validators return (bool, str), extract bool
        is_valid = result[0] if isinstance(result, tuple) else result
        status = "✅" if is_valid == expected else "❌"
        print(f"  {status} {address[:30]}... → {is_valid} (expected: {expected})")
        if is_valid == expected:
            erc20_passed += 1

    total_tests = len(trc20_tests) + len(erc20_tests)
    total_passed = trc20_passed + erc20_passed
    print(f"\n📊 Validators: {total_passed}/{total_tests} tests passed")
    return total_passed == total_tests


async def test_balance_fetching():
    """Test 3: Balance Fetching"""
    print("\n" + "=" * 60)
    print("TEST 3: Balance Fetching")
    print("=" * 60)

    from bot.services.balance_service import BalanceService

    balance_service = BalanceService()

    # Test TRC20 balance
    print("\n🟢 TRC20 Balance Fetching:")
    print(f"  Testing: {TEST_ADDRESSES['TRC20_VALID'][:30]}...")
    trc20_balance = balance_service.get_usdt_trc20_balance(TEST_ADDRESSES['TRC20_VALID'])
    if trc20_balance is not None:
        print(f"  ✅ TRC20 Balance: {trc20_balance:,.2f} USDT")
        trc20_success = True
    else:
        print(f"  ❌ TRC20 Balance fetch failed")
        trc20_success = False

    # Test ERC20 balance
    print("\n🔷 ERC20 Balance Fetching:")
    print(f"  Testing: {TEST_ADDRESSES['ERC20_VALID'][:30]}...")
    erc20_balance = balance_service.get_usdt_erc20_balance(TEST_ADDRESSES['ERC20_VALID'])
    if erc20_balance is not None:
        print(f"  ✅ ERC20 Balance: {erc20_balance:,.2f} USDT")
        erc20_success = True
    else:
        print(f"  ❌ ERC20 Balance fetch failed")
        erc20_success = False

    # Test unified get_balance method
    print("\n🔀 Unified Balance Method:")
    unified_trc20 = balance_service.get_balance(TEST_ADDRESSES['TRC20_USER'], 'TRC20')
    unified_erc20 = balance_service.get_balance(TEST_ADDRESSES['ERC20_USER'], 'ERC20')

    unified_success = (unified_trc20 is not None) and (unified_erc20 is not None)
    status = "✅" if unified_success else "❌"
    print(f"  {status} Unified method works for both chains")

    total_success = trc20_success and erc20_success and unified_success
    print(f"\n📊 Balance Fetching: {'✅ All tests passed' if total_success else '❌ Some tests failed'}")
    return total_success


async def test_multi_chain_balance():
    """Test 4: Multi-Chain Balance Fetching"""
    print("\n" + "=" * 60)
    print("TEST 4: Multi-Chain Balance Fetching")
    print("=" * 60)

    from bot.services.balance_service import BalanceService

    balance_service = BalanceService()

    # Test mixed wallet dictionary
    wallets_to_check = {
        'TRC20 USDT Contract': {
            'address': TEST_ADDRESSES['TRC20_VALID'],
            'chain': 'TRC20'
        },
        'ERC20 USDT Contract': {
            'address': TEST_ADDRESSES['ERC20_VALID'],
            'chain': 'ERC20'
        },
        'TRC20 User Wallet': {
            'address': TEST_ADDRESSES['TRC20_USER'],
            'chain': 'TRC20'
        },
        'ERC20 User Wallet': {
            'address': TEST_ADDRESSES['ERC20_USER'],
            'chain': 'ERC20'
        },
    }

    print(f"\nFetching balances for {len(wallets_to_check)} wallets...\n")
    balances = balance_service.fetch_multiple_balances(wallets_to_check)

    success_count = 0
    for name, balance in balances.items():
        if balance is not None:
            print(f"  ✅ {name}: {balance:,.2f} USDT")
            success_count += 1
        else:
            print(f"  ❌ {name}: Failed to fetch")

    print(f"\n📊 Multi-Chain: {success_count}/{len(wallets_to_check)} wallets fetched successfully")
    return success_count == len(wallets_to_check)


async def main():
    """Run all tests"""
    print("\n" + "🧪" * 30)
    print("ERC20 MULTI-CHAIN SUPPORT TEST SUITE")
    print("🧪" * 30)

    # Check environment
    print("\n📋 Environment Check:")
    print(f"  ETHEREUM_API_KEY: {'✅ Set' if os.getenv('ETHEREUM_API_KEY') else '❌ Missing'}")
    print(f"  TRON_API_KEY: {'✅ Set' if os.getenv('TRON_API_KEY') else '❌ Missing'}")

    if not os.getenv('ETHEREUM_API_KEY'):
        print("\n⚠️  WARNING: ETHEREUM_API_KEY not set - ERC20 tests will fail")

    # Run tests
    results = []

    try:
        results.append(("Chain Detection", await test_chain_detection()))
        results.append(("Address Validators", await test_validators()))
        results.append(("Balance Fetching", await test_balance_fetching()))
        results.append(("Multi-Chain Balance", await test_multi_chain_balance()))
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! ERC20 support is ready!")
    else:
        print("⚠️  SOME TESTS FAILED - Review errors above")
    print("=" * 60 + "\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
