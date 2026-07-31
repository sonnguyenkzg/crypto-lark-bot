# tests/test_roster_scope.py
"""wallets.json is the scope, full stop.

Every wallet gets a figure for every date. When it was added is never consulted --
a wallet that did not exist yet reconstructs to 0.00, which is the truthful answer.
Excluding it hid 20,184,069.03 USDT across 31 wallets that were already funded
before they entered monitoring.
"""
from bot.handlers.check_handler import CheckHandler


def w(name, addr, created_at=None):
    return {"wallet": name, "address": addr, "company": "CO",
            "chain": "TRC20", "created_at": created_at}


def test_a_wallet_added_after_the_date_is_still_expected():
    """Previously not_yet_created -> silently dropped. Now it must be rebuilt."""
    h = CheckHandler()
    out = h.classify_wallets([w("Late", "TAAA", "2026-05-18")], {}, "2026-01-01")
    assert len(out) == 1
    assert out[0]["status"] == "needs_rebuild"


def test_no_wallet_is_ever_reported_as_not_yet_created():
    h = CheckHandler()
    roster = [w("A", "TAAA", "2026-05-18"), w("B", "TBBB", None), w("C", "TCCC", "2020-01-01")]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert {e["status"] for e in out} == {"needs_rebuild"}
    assert all(e["status"] != "not_yet_created" for e in out)


def test_a_saved_row_is_still_used():
    h = CheckHandler()
    snap = {"TAAA": {"wallet_name": "A", "company": "CO", "address": "TAAA",
                     "balance": 42, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets([w("A", "TAAA", "2026-05-18")], snap, "2026-01-01")
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 42


def test_every_roster_wallet_appears_exactly_once():
    h = CheckHandler()
    roster = [w(f"W{i}", f"T{i}") for i in range(71)]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert len(out) == 71
    assert len({e["name"] for e in out}) == 71


def test_created_at_is_no_longer_consulted():
    """Identical wallets differing only in created_at must classify identically."""
    h = CheckHandler()
    a = h.classify_wallets([w("A", "TAAA", "2099-01-01")], {}, "2026-01-01")
    b = h.classify_wallets([w("A", "TAAA", None)], {}, "2026-01-01")
    assert a[0]["status"] == b[0]["status"] == "needs_rebuild"
