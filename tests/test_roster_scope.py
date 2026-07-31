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


# --- card behaviour: every wallet counted, nothing hidden ---

import json


def _card_entries(saved=2, rebuilt=1, failed=0):
    out = [{"name": f"S{i}", "company": "CO", "address": f"TS{i}", "chain": "TRC20",
            "status": "saved", "balance": 100} for i in range(saved)]
    out += [{"name": f"R{i}", "company": "CO", "address": f"TR{i}", "chain": "TRC20",
             "status": "rebuilt", "balance": 0} for i in range(rebuilt)]
    out += [{"name": f"U{i}", "company": "CO", "address": f"TU{i}", "chain": "TRC20",
             "status": "failed", "balance": None} for i in range(failed)]
    return out


def _card(entries, roster_total):
    return json.dumps(CheckHandler()._create_historical_card(
        entries, "2026-05-17", [], [], None,
        mode="closing", target_date="2026-05-18", roster_total=roster_total)).replace("**", "")


def test_card_no_longer_says_added_after_this_date():
    b = _card(_card_entries(), roster_total=3)
    assert "added on or after" not in b
    assert "added after" not in b
    assert "no balance yet" not in b


def test_a_zero_balance_wallet_is_listed_not_hidden():
    """A zero is a real balance. Hiding it breaks the reconciliation to the roster size."""
    b = _card(_card_entries(2, 1), roster_total=3)
    assert "R0" in b, "the rebuilt 0.00 wallet must appear in the card"


def test_summary_counts_the_full_roster():
    b = _card(_card_entries(68, 3), roster_total=71)
    assert "Total wallets in monitoring: 71" in b


def test_an_unavailable_wallet_is_named_and_not_silently_counted():
    """A failed reconstruction must be named and excluded from the counted total,
    never quietly counted as zero."""
    b = _card(_card_entries(68, 2, failed=1), roster_total=71)
    assert "U0" in b, "the unavailable wallet must be named"
    assert "could not be calculated" in b
    assert "Total wallets in monitoring: 71" in b
