"""Integration tests for the /check [date] routing + reconstruction wiring (Task 8).

Uses a fake context (no network, no Lark) and asyncio.run() in plain sync test
functions -- deliberately NOT relying on pytest-asyncio config.
"""
import asyncio
import json
from decimal import Decimal

from bot.handlers.check_handler import CheckHandler


class _FakeTopic:
    def __init__(self):
        self.cards = []

    async def send_command_response(self, card, msg_type=None):
        self.cards.append(card)


class _FakeCtx:
    def __init__(self, args):
        self.args = args
        self.sender_id = "ou_test"
        self.topic_manager = _FakeTopic()


ROSTER = {"companies": {
    "KZP": [{"name": "KZP 96G1", "address": "TAAA", "chain": "TRC20", "created_at": "2026-01-01 00:00:00"}],
    "KZO": [{"name": "Eth One", "address": "0xabc0000000000000000000000000000000000001",
             "chain": "ERC20", "created_at": "2026-01-01 00:00:00"}],
}}


def _handler(monkeysnapshot=None, monkeybalances=None, nearest=None):
    """nearest = (date_str, snapshot_dict) used when monkeysnapshot is empty (gap date)."""
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    if monkeysnapshot is not None:
        near_date, near_snap = nearest if nearest else (None, {})
        h.sheets_logger.get_snapshot_for_date = lambda d: monkeysnapshot
        h.sheets_logger.get_snapshot_and_nearest = (
            lambda d: (monkeysnapshot, None, {}) if monkeysnapshot
            else ({}, near_date, near_snap))
    if monkeybalances is not None:
        h.balance_service.get_balance_at = lambda addr, chain, cutoff: monkeybalances.get(addr)
    return h


def _run(h, args):
    import bot.handlers.check_handler as ch
    ch._CHECK_EXECUTION_LOCK = False
    ctx = _FakeCtx(args)
    asyncio.run(h.handle(ctx))
    return ctx.topic_manager.cards


def _blob(card):  # searchable text of a card
    return json.dumps(card)


def test_bare_unbracketed_date_gives_hint_not_live_check():
    cards = _run(_handler(), ["2026-07-15"])
    assert cards, "expected at least one card"
    last_blob = _blob(cards[-1])
    assert "[" in last_blob
    assert "bracket" in last_blob.lower() or "2026-07-15" in last_blob
    for c in cards:
        assert "checking balances" not in _blob(c).lower()
        assert "Checking Balances" not in _blob(c)


def test_bracketed_date_plus_bare_filter_gives_hint():
    cards = _run(_handler(), ["[2026-07-15]", "KZP"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "[" in blob
    assert "2026-07-15" in blob


def test_invalid_date_gives_bad_date_card():
    cards = _run(_handler(), ["[2026-13-40]"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "2026-13-40" in blob or "YYYY-MM-DD" in blob


def test_future_date_gives_future_card():
    cards = _run(_handler(), ["[9999-01-01]"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1]).lower()
    assert "future" in blob or "9999-01-01" in blob


def test_valid_date_with_snapshot_returns_historical_card_with_total():
    snapshot = {
        "TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                 "balance": Decimal("10.00"), "batch_id": "20260715000112", "time": "00:01:12"}
    }
    h = _handler(monkeysnapshot=snapshot)
    cards = _run(h, ["[2026-07-15]"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "2026-07-15" in blob
    assert "10.00" in blob


def test_valid_date_snapshot_missing_current_wallet_warns():
    # Snapshot only has TAAA; current roster also has the ERC20 wallet "Eth One", which
    # is absent -> should surface as a completeness warning.
    snapshot = {
        "TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                 "balance": Decimal("10.00"), "batch_id": "20260715000112", "time": "00:01:12"}
    }
    h = _handler(monkeysnapshot=snapshot)
    cards = _run(h, ["[2026-07-15]"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "Eth One" in blob


def test_valid_date_no_snapshot_reconstructs_and_marks_unavailable():
    monkeybalances = {
        "TAAA": Decimal("7.00"),
        "0xabc0000000000000000000000000000000000001": None,
    }
    h = _handler(monkeysnapshot={}, monkeybalances=monkeybalances)
    cards = _run(h, ["[2026-07-15]"])
    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "7.00" in blob
    assert "Eth One" in blob


def test_reconstruction_timeout_marks_unavailable_not_dropped():
    import time
    h = _handler(monkeysnapshot={})           # no snapshot -> reconstruction path
    h.RECON_TOTAL_BUDGET = 0.3                 # shrink so the slow lookup can't finish
    def slow(addr, chain, cutoff):
        time.sleep(2)                          # exceeds budget -> task pending -> cancelled
        return Decimal("1.00")
    h.balance_service.get_balance_at = slow
    cards = _run(h, ["[2026-07-15]"])
    blob = _blob(cards[-1])
    # BOTH roster wallets must surface as unavailable, neither silently dropped
    assert "KZP 96G1" in blob
    assert "Eth One" in blob


def test_unrebuildable_wallet_reported_failed_not_borrowed_from_nearest():
    """A wallet that can't be rebuilt must still surface by name -- but the per-wallet
    redesign (Task 5) no longer borrows a number from the nearest saved date (that
    fallback is gone; get_snapshot_and_nearest's nearest_date/nearest_snapshot are now
    discarded). It's honestly reported as failed and excluded from the total; a LATER
    check will retry the rebuild, since the date is still incomplete."""
    nearest_snap = {
        "TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                 "balance": Decimal("500.00"), "batch_id": "20260719000112", "time": "00:01:12"},
    }
    # gap date (no snapshot); TAAA cannot be rebuilt (None), the ERC20 one can
    h = _handler(monkeysnapshot={},
                 monkeybalances={"TAAA": None,
                                 "0xabc0000000000000000000000000000000000001": Decimal("10.00")},
                 nearest=("2026-07-19", nearest_snap))
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert "KZP 96G1" in blob                    # present, not silently dropped
    assert "could not be worked out" in blob     # honestly reported as failed
    assert "10.00" in blob                       # only the rebuilt wallet is counted
    assert "510.00" not in blob                  # NOT borrowed from the nearest record


def test_no_nearest_record_still_reports_wallet_as_unavailable():
    """If a wallet can't be rebuilt, be honest rather than invent a number -- with or
    without a nearby saved date to borrow from (which the new design never does)."""
    h = _handler(monkeysnapshot={},
                 monkeybalances={"TAAA": None,
                                 "0xabc0000000000000000000000000000000000001": Decimal("10.00")},
                 nearest=(None, {}))
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert "could not be worked out" in blob
    assert "KZP 96G1" in blob


def test_only_missing_wallets_are_rebuilt_and_saved():
    """A wallet with a saved figure must not be rebuilt; the missing one is
    rebuilt AND written back so the date fills itself in."""
    saved = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                      "balance": Decimal("19.41"), "batch_id": "20260720000112",
                      "time": "00:01:12"}}
    rebuilt_for, saved_rows = [], {}
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_snapshot_and_nearest = lambda d: (saved, None, {})

    def fake_rebuild(addr, chain, cutoff):
        rebuilt_for.append(addr)
        return Decimal("10.00")
    h.balance_service.get_balance_at = fake_rebuild
    h.sheets_logger.save_rebuilt_balances = (
        lambda date_str, rows: saved_rows.update(date=date_str, rows=rows) or (True, "B123"))

    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert rebuilt_for == ["0xabc0000000000000000000000000000000000001"]  # ONLY the missing one
    assert [r["name"] for r in saved_rows["rows"]] == ["Eth One"]
    assert saved_rows["date"] == "2026-07-20"
    assert "29.41" in blob                       # 19.41 saved + 10.00 rebuilt
    assert "B123" in blob                        # batch id shown on the card


def test_nothing_saved_when_nothing_was_rebuilt():
    saved = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                      "balance": Decimal("19.41"), "batch_id": "b", "time": "t"},
             "0xabc0000000000000000000000000000000000001": {
                 "wallet_name": "Eth One", "company": "KZO",
                 "address": "0xabc0000000000000000000000000000000000001",
                 "balance": Decimal("5.00"), "batch_id": "b", "time": "t"}}
    calls = []
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_snapshot_and_nearest = lambda d: (saved, None, {})
    h.sheets_logger.save_rebuilt_balances = lambda d, r: calls.append(r) or (True, "X")
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert calls == []                           # nothing to save -> no write
    assert "saved to Google Sheets" not in blob  # and no footer line
