"""Adding the same on-chain address twice must be refused, whatever its casing.

An ERC20 address is the same wallet whether it is written in upper, lower or mixed
case. Two wallet entries pointing at one address would each report its balance, so
every total that includes both counts that money twice.
"""
import asyncio

from bot.services.wallet_service import WalletService


def _service(existing):
    """A WalletService backed by an in-memory dict instead of wallets.json."""
    s = WalletService(wallet_file="/dev/null/not-used")
    saved = {}
    s._load_wallets = lambda: dict(existing)
    s._save_wallets = lambda w: saved.update(w) or True
    s._saved = saved
    return s


ERC20_MIXED = "0xAbC0000000000000000000000000000000000001"
ERC20_LOWER = ERC20_MIXED.lower()
TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def _add(service, company, name, address, chain):
    return asyncio.run(service.add_wallet(company, name, address, chain))


def test_same_erc20_address_in_a_different_casing_is_refused():
    s = _service({"KZO ETH 1": {"company": "KZO", "wallet": "KZO ETH 1",
                                "address": ERC20_MIXED, "chain": "ERC20"}})
    ok, msg = _add(s, "KZP", "KZP ETH 2", ERC20_LOWER, "ERC20")
    assert ok is False
    assert "already used" in msg and "KZO ETH 1" in msg
    assert s._saved == {}                     # nothing was written


def test_identical_erc20_address_is_still_refused():
    s = _service({"KZO ETH 1": {"company": "KZO", "wallet": "KZO ETH 1",
                                "address": ERC20_MIXED, "chain": "ERC20"}})
    ok, _ = _add(s, "KZP", "KZP ETH 2", ERC20_MIXED, "ERC20")
    assert ok is False


def test_trc20_addresses_stay_case_sensitive():
    """TRC20 base58 IS case-sensitive: a different casing is a DIFFERENT address and
    must not be mistaken for a duplicate."""
    s = _service({"KZP 1": {"company": "KZP", "wallet": "KZP 1",
                            "address": TRC20, "chain": "TRC20"}})
    ok, _ = _add(s, "KZP", "KZP 2", TRC20.lower(), "TRC20")
    assert ok is True


def test_a_genuinely_new_address_is_accepted():
    s = _service({"KZO ETH 1": {"company": "KZO", "wallet": "KZO ETH 1",
                                "address": ERC20_MIXED, "chain": "ERC20"}})
    ok, _ = _add(s, "KZP", "KZP TRX 1", TRC20, "TRC20")
    assert ok is True
    assert s._saved["KZP TRX 1"]["address"] == TRC20
