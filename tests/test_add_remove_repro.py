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

def test_add_still_accepts_quotes():
    ok, res = A.parse_quoted_arguments(f'"TEST" "KZG TEST WALLET" "{BUG_ADDRESS}"')
    assert ok and res[2] == BUG_ADDRESS
