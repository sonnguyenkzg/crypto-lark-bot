from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

ROSTER = [
    {"wallet": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
     "created_at": "2026-01-01 00:00:00"},
    {"wallet": "KZO ERC A 1", "company": "KZO", "address": "0xABC", "chain": "ERC20",
     "created_at": "2026-01-01 00:00:00"},
    {"wallet": "New Wallet", "company": "KZP", "address": "TNEW", "chain": "TRC20",
     "created_at": "2026-07-24 15:15:55"},
]

def snap(*items):   # (canonical_address, name, company, balance)
    return {a: {"wallet_name": n, "company": c, "address": a, "balance": Decimal(b),
                "batch_id": "20260715000112", "time": "00:01:12"} for a, n, c, b in items}

def by_name(rows):
    return {r["name"]: r for r in rows}

def test_saved_wallet_uses_its_figure():
    rows = H.classify_wallets(ROSTER, snap(("TAAA", "KZP 96G1", "KZP", "19.41")), "2026-07-15")
    r = by_name(rows)["KZP 96G1"]
    assert r["status"] == "saved" and r["balance"] == Decimal("19.41")

def test_missing_wallet_needs_rebuild():
    rows = H.classify_wallets(ROSTER, snap(("TAAA", "KZP 96G1", "KZP", "19.41")), "2026-07-15")
    r = by_name(rows)["KZO ERC A 1"]
    assert r["status"] == "needs_rebuild" and r["balance"] is None
    assert r["chain"] == "ERC20"          # carried through for the rebuild call

def test_wallet_created_before_the_date_is_expected():
    rows = H.classify_wallets(ROSTER, {}, "2026-07-25")     # after New Wallet was added
    assert by_name(rows)["New Wallet"]["status"] == "needs_rebuild"

def test_wallet_not_in_wallets_json_is_ignored():
    # 'Cold wallet' is in the saved record but no longer in wallets.json -- scope is
    # wallets.json only, so it must not appear in the output at all. Also check every
    # roster wallet IS still present (by name and by address) -- not just that the
    # count matches, which a bug that drops a real wallet while keeping a ghost one
    # could satisfy by coincidence.
    s = snap(("TAAA", "KZP 96G1", "KZP", "19.41"), ("TOLD", "Cold wallet", "S5", "1250.00"))
    rows = H.classify_wallets(ROSTER, s, "2026-07-15")
    assert len(rows) == len(ROSTER)
    assert {r["name"] for r in rows} == {w["wallet"] for w in ROSTER}
    assert {r["address"] for r in rows} == {w["address"] for w in ROSTER}

def test_entry_count_always_equals_wallets_json_count():
    """The report must always reconcile to the wallet list -- never more, never fewer."""
    s = snap(("TAAA", "KZP 96G1", "KZP", "19.41"), ("TGHOST", "Retired Wallet", "S5", "999.00"))
    rows = H.classify_wallets(ROSTER, s, "2026-07-15")
    assert len(rows) == len(ROSTER)
    assert "Retired Wallet" not in {r["name"] for r in rows}

def test_unparseable_created_at_is_treated_as_existing():
    roster = [{"wallet": "Odd", "company": "KZP", "address": "TODD", "chain": "TRC20",
               "created_at": "TBD"}]
    assert H.classify_wallets(roster, {}, "2026-07-15")[0]["status"] == "needs_rebuild"

def test_erc20_address_case_is_ignored():
    s = snap(("0xabc", "KZO ERC A 1", "KZO", "29629.90"))    # snapshot key lowercased
    r = by_name(H.classify_wallets(ROSTER, s, "2026-07-15"))["KZO ERC A 1"]
    assert r["status"] == "saved"          # matched despite roster having 0xABC

