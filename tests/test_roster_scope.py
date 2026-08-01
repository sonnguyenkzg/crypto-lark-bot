# tests/test_roster_scope.py
"""wallets.json is the scope; on-chain creation is existence.

Two rules act together:

1. Every wallet in wallets.json that EXISTED on the date is shown -- including a wallet
   that already held money before it entered monitoring. Excluding those hid
   20,184,069.03 USDT across 31 wallets that were funded before being added.

2. A wallet had no balance before it was first funded. `first_funded[address]` is the
   earliest date it ever held a positive balance (its on-chain creation), and for any
   date before that the wallet is reported "added on or after this date" -- NOT
   reconstructed to a fictitious 0.00 for a day it did not yet exist.

Creation is the first on-chain balance, never the wallets.json `created_at` field, which
is unreliable in both directions.
"""
from bot.handlers.check_handler import CheckHandler


def w(name, addr, created_at=None):
    return {"wallet": name, "address": addr, "company": "CO",
            "chain": "TRC20", "created_at": created_at}


START = "2026-01-01"   # vault coverage_start (verified-complete floor) in these fixtures


def test_before_first_funded_is_not_yet_created():
    """A date before the wallet's first positive balance -> added on/after, no rebuild."""
    h = CheckHandler()
    out = h.classify_wallets([w("Late", "TAAA")], {}, "2026-01-01",
                             first_funded={"TAAA": "2026-05-18"}, coverage_start=START)
    assert len(out) == 1
    assert out[0]["status"] == "not_yet_created"
    assert out[0]["balance"] is None


def test_on_or_after_first_funded_is_rebuilt():
    """From its creation date onward, a gap wallet is reconstructed as usual."""
    h = CheckHandler()
    on = h.classify_wallets([w("A", "TAAA")], {}, "2026-05-18",
                            first_funded={"TAAA": "2026-05-18"}, coverage_start=START)
    after = h.classify_wallets([w("A", "TAAA")], {}, "2026-06-01",
                               first_funded={"TAAA": "2026-05-18"}, coverage_start=START)
    assert on[0]["status"] == "needs_rebuild"
    assert after[0]["status"] == "needs_rebuild"


def test_money_held_before_monitoring_is_still_shown():
    """A wallet funded (first_funded) BEFORE the queried date is expected, not hidden --
    this is the 20M-USDT protection. It reconstructs; it is never not_yet_created."""
    h = CheckHandler()
    out = h.classify_wallets([w("Early", "TEEE")], {}, "2026-05-17",
                             first_funded={"TEEE": "2026-05-16"}, coverage_start=START)
    assert out[0]["status"] == "needs_rebuild"


def test_a_date_before_coverage_start_is_never_not_yet_created():
    """Below the verified-complete floor the vault is sparse: a wallet funded in 2025 can
    have no row until 2026, so its first_funded reads later than reality. Claiming
    not_yet_created for a pre-floor date would hide real money -- reconstruct instead."""
    h = CheckHandler()
    out = h.classify_wallets([w("A", "TAAA")], {}, "2025-12-01",
                             first_funded={"TAAA": "2026-02-01"}, coverage_start=START)
    assert out[0]["status"] == "needs_rebuild"


def test_no_coverage_start_falls_back_to_rebuild():
    """Without a coverage floor we cannot trust first_funded, so we reconstruct."""
    h = CheckHandler()
    out = h.classify_wallets([w("A", "TAAA")], {}, "2026-01-01",
                             first_funded={"TAAA": "2026-05-18"})
    assert out[0]["status"] == "needs_rebuild"


def test_unknown_creation_falls_back_to_rebuild():
    """A wallet absent from first_funded (no recorded positive balance) has unknown
    creation, so we reconstruct rather than risk hiding a genuinely-funded wallet."""
    h = CheckHandler()
    out = h.classify_wallets([w("A", "TAAA")], {}, "2026-01-01",
                             first_funded={}, coverage_start=START)
    assert out[0]["status"] == "needs_rebuild"


def test_missing_first_funded_arg_falls_back_to_rebuild():
    """With no first_funded passed at all, behaviour is the safe fallback: rebuild."""
    h = CheckHandler()
    out = h.classify_wallets([w("A", "TAAA")], {}, "2026-01-01")
    assert out[0]["status"] == "needs_rebuild"


def test_a_saved_row_is_still_used_regardless_of_creation():
    """A recorded figure always wins, even for a date before first_funded."""
    h = CheckHandler()
    snap = {"TAAA": {"wallet_name": "A", "company": "CO", "address": "TAAA",
                     "balance": 42, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets([w("A", "TAAA")], snap, "2026-01-01",
                             first_funded={"TAAA": "2026-05-18"}, coverage_start=START)
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 42


def test_every_roster_wallet_appears_exactly_once():
    h = CheckHandler()
    roster = [w(f"W{i}", f"T{i}") for i in range(71)]
    out = h.classify_wallets(roster, {}, "2026-01-01", first_funded={}, coverage_start=START)
    assert len(out) == 71
    assert len({e["name"] for e in out}) == 71


def test_created_at_is_never_consulted():
    """Existence is first_funded, not created_at. Identical wallets differing only in
    created_at must classify identically; only first_funded changes the outcome."""
    h = CheckHandler()
    a = h.classify_wallets([w("A", "TAAA", "2099-01-01")], {}, "2026-01-01",
                           first_funded={"TAAA": "2026-01-01"}, coverage_start=START)
    b = h.classify_wallets([w("A", "TAAA", None)], {}, "2026-01-01",
                           first_funded={"TAAA": "2026-01-01"}, coverage_start=START)
    assert a[0]["status"] == b[0]["status"] == "needs_rebuild"


# --- card behaviour ---

import json


def _entries(saved=2, rebuilt=1, failed=0, not_yet=0):
    out = [{"name": f"S{i}", "company": "CO", "address": f"TS{i}", "chain": "TRC20",
            "status": "saved", "balance": 100} for i in range(saved)]
    out += [{"name": f"R{i}", "company": "CO", "address": f"TR{i}", "chain": "TRC20",
             "status": "rebuilt", "balance": 0} for i in range(rebuilt)]
    out += [{"name": f"U{i}", "company": "CO", "address": f"TU{i}", "chain": "TRC20",
             "status": "failed", "balance": None} for i in range(failed)]
    out += [{"name": f"N{i}", "company": "CO", "address": f"TN{i}", "chain": "TRC20",
             "status": "not_yet_created", "balance": None} for i in range(not_yet)]
    return out


def _card(entries, roster_total):
    return json.dumps(CheckHandler()._create_historical_card(
        entries, "2026-05-17", [], [], None,
        mode="closing", target_date="2026-05-18", roster_total=roster_total)).replace("**", "")


def test_card_omits_not_yet_line_when_none():
    b = _card(_entries(), roster_total=3)
    assert "added on or after" not in b
    assert "no balance yet" not in b


def test_card_names_a_few_not_yet_created_wallets():
    b = _card(_entries(saved=2, rebuilt=0, not_yet=2), roster_total=4)
    assert "added on or after this date" in b
    assert "N0" in b and "N1" in b


def test_card_summarises_many_not_yet_created_wallets_by_count():
    b = _card(_entries(saved=1, rebuilt=0, not_yet=10), roster_total=11)
    assert "10 wallets were added on or after this date" in b
    assert "N7" not in b, "with many, individual names are not listed"


def test_not_yet_created_is_not_counted_in_the_total():
    b = _card(_entries(saved=2, rebuilt=1, not_yet=3), roster_total=6)
    assert "3 wallets counted" in b


def test_a_zero_balance_wallet_is_listed_not_hidden():
    """A zero is a real balance. Hiding it breaks the reconciliation to the roster size."""
    b = _card(_entries(2, 1), roster_total=3)
    assert "R0" in b, "the rebuilt 0.00 wallet must appear in the card"


def test_summary_counts_the_full_roster():
    b = _card(_entries(68, 3), roster_total=71)
    assert "Total wallets in monitoring: 71" in b


def test_an_unavailable_wallet_is_named_and_not_silently_counted():
    b = _card(_entries(68, 2, failed=1), roster_total=71)
    assert "U0" in b, "the unavailable wallet must be named"
    assert "could not be calculated" in b
    assert "Total wallets in monitoring: 71" in b
