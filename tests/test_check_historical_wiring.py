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


def test_unrebuildable_wallet_falls_back_to_nearest_record_not_dropped():
    """A wallet that can't be rebuilt must still show a number (from the closest saved
    record) and be INCLUDED in the total -- never silently dropped or left blank."""
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
    assert "KZP 96G1" in blob                    # present, not dropped
    assert "2026-07-19" in blob                  # says where the figure came from
    assert "510.00" in blob                      # 500 (fallback) + 10 (rebuilt) => in the total
    assert "No figure available" not in blob     # nothing left unavailable


def test_no_nearest_record_still_reports_wallet_as_unavailable():
    """If there is no saved record anywhere for a wallet, be honest rather than invent."""
    h = _handler(monkeysnapshot={},
                 monkeybalances={"TAAA": None,
                                 "0xabc0000000000000000000000000000000000001": Decimal("10.00")},
                 nearest=(None, {}))
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert "No figure available" in blob
    assert "KZP 96G1" in blob
