"""Reproduces the bug reported in request.txt:
     /remove "Cold wallet"                          -> worked
     /remove "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071" -> did NOT work
"""
from bot.handlers.remove_handler import RemoveHandler
from bot.handlers.add_handler import AddHandler

BUG_ADDRESS = "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071"
WALLETS = [{"name": "KZG TEST WALLET", "address": BUG_ADDRESS, "company": "TEST"},
           {"name": "Cold wallet", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "company": "S5"}]

R, A = RemoveHandler(), AddHandler()

def test_remove_by_name_brackets():
    ok, val = R.parse_single_quoted_argument("[Cold wallet]")
    assert ok and val == "Cold wallet"

def test_remove_by_name_quotes():
    ok, val = R.parse_single_quoted_argument('"Cold wallet"')
    assert ok and val == "Cold wallet"

def test_remove_by_the_reported_address_brackets():
    ok, val = R.parse_single_quoted_argument(f"[{BUG_ADDRESS}]")
    assert ok and val == BUG_ADDRESS
    assert R._match_address(val, WALLETS)["name"] == "KZG TEST WALLET"

def test_remove_by_the_reported_address_quotes():
    ok, val = R.parse_single_quoted_argument(f'"{BUG_ADDRESS}"')
    assert ok and val == BUG_ADDRESS
    assert R._match_address(val, WALLETS)["name"] == "KZG TEST WALLET"

def test_reported_address_matches_case_insensitively():
    assert R._match_address(BUG_ADDRESS.lower(), WALLETS)["name"] == "KZG TEST WALLET"

def test_add_accepts_the_reported_address_in_brackets():
    ok, res = A.parse_quoted_arguments(f"[TEST] [KZG TEST WALLET] [{BUG_ADDRESS}]")
    assert ok and res == ["TEST", "KZG TEST WALLET", BUG_ADDRESS]


def _handler_with(wallets):
    """RemoveHandler whose wallet store contains `wallets` (no file, no network)."""
    h = RemoveHandler()
    h.wallet_service.get_wallet = lambda name: (False, {})      # not found by name
    h.wallet_service.list_wallets = lambda: (True, {"companies": {
        w["company"]: [{"name": w["name"], "address": w["address"]}] for w in wallets}})
    return h


def test_find_by_reported_erc20_address_end_to_end():
    """The ACTUAL reported bug: an ERC20 address must be recognised as an address
    and resolved. The old code gated this on a TRC20-only check, so it never matched."""
    h = _handler_with(WALLETS)
    found, info = h.find_wallet_by_identifier(BUG_ADDRESS)
    assert found is True
    assert info["wallet"] == "KZG TEST WALLET"


def test_find_by_erc20_address_is_case_insensitive_end_to_end():
    h = _handler_with(WALLETS)
    found, info = h.find_wallet_by_identifier(BUG_ADDRESS.lower())
    assert found is True and info["wallet"] == "KZG TEST WALLET"


def test_find_by_trc20_address_end_to_end():
    h = _handler_with(WALLETS)
    found, info = h.find_wallet_by_identifier("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert found is True and info["wallet"] == "Cold wallet"


def test_find_by_unknown_address_reports_not_found_end_to_end():
    h = _handler_with(WALLETS)
    found, msg = h.find_wallet_by_identifier("0x0000000000000000000000000000000000000000")
    assert found is False and "not found" in str(msg).lower()
