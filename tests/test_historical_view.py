from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

def snap(*items):   # items: (canonical_addr, name, company, balance)
    return {a: {"wallet_name": n, "company": c, "address": a, "balance": Decimal(b),
                "batch_id": "20260715000112", "time": "00:01:12"} for a, n, c, b in items}

ROSTER = [
    {"wallet": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20", "created_at": "2026-01-01 00:00:00"},
    {"wallet": "KZO A 1",  "company": "KZO", "address": "TBBB", "chain": "TRC20", "created_at": "2026-01-01 00:00:00"},
    {"wallet": "Eth One",  "company": "KZO", "address": "0xabc", "chain": "ERC20", "created_at": "2026-01-01 00:00:00"},
]

def test_all_wallets_no_filter():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"), ("0xabc","Eth One","KZO","5"))
    v = H.build_historical_view(s, ROSTER, [], [], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1", "KZO A 1", "Eth One"}
    assert v["missing"] == []

def test_group_filter():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, ["KZO"], [], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZO A 1"}

def test_name_filter_exact():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, [], ["KZP 96G1"], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1"}

def test_name_filter_fuzzy():
    s = snap(("TAAA","KZP 96G1","KZP","10"))
    v = H.build_historical_view(s, ROSTER, [], ["KZP 96"], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1"}
    assert v["fuzzy"].get("KZP 96") == ["KZP 96G1"]

def test_completeness_missing_erc20():
    # sustained ERC20 outage: 0xabc absent from snapshot but present in current roster
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, [], [], "2026-07-15")
    assert "Eth One" in v["missing"]

def test_not_found_name():
    s = snap(("TAAA","KZP 96G1","KZP","10"))
    v = H.build_historical_view(s, ROSTER, [], ["ZZZ QQQ"], "2026-07-15")
    assert v["not_found"] == ["ZZZ QQQ"]
