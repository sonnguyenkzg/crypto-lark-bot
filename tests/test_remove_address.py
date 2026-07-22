from bot.handlers.remove_handler import RemoveHandler

H = RemoveHandler()
WALLETS = [
    {"name": "Cold Wallet", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "company": "KZP"},
    {"name": "Eth One",     "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "company": "KZO"},
]

def test_match_trc20_exact():
    assert H._match_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", WALLETS)["name"] == "Cold Wallet"

def test_trc20_case_changed_does_not_match():
    # base58 is case-sensitive: a case-changed TRON address must NOT match
    assert H._match_address("tr7nhqjekqxgtci8q8zy4pl8otszgjlj6t", WALLETS) is None

def test_match_erc20_case_insensitive():
    # ERC20 hex is case-insensitive: checksummed vs lowercase both match
    assert H._match_address("0xdac17f958d2ee523a2206206994597c13d831ec7", WALLETS)["name"] == "Eth One"

def test_unknown_address():
    assert H._match_address("0x0000000000000000000000000000000000000000", WALLETS) is None
