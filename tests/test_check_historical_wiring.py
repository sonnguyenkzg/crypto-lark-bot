"""Integration tests for the /check [date] routing + reconstruction wiring (Task 8).

Uses a fake context (no network, no Lark) and asyncio.run() in plain sync test
functions -- deliberately NOT relying on pytest-asyncio config.
"""
import asyncio
import json
from decimal import Decimal

import pytest

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


def _bundle(snapshot=None, nearest_date=None, nearest_snapshot=None, ok=True, first_seen=None):
    """Build the five-key dict get_history_bundle returns.

    The handler reads the sheet through get_history_bundle (Task 4 made one read yield
    both the snapshot and first_seen; get_snapshot_and_nearest is now only a thin
    4-tuple view OVER it, so stubbing that view cannot influence the handler).

    first_seen defaults to {} -- an empty map means "no evidence either way", which
    classify_wallets treats as "assume the wallet existed". That is exactly what the
    created_at-only rule did for every wallet in ROSTER (created 2026-01-01, well before
    any date under test), so these doubles classify identically to before the refactor.
    """
    return {"ok": ok, "snapshot": snapshot or {}, "nearest_date": nearest_date,
            "nearest_snapshot": nearest_snapshot or {}, "first_seen": first_seen or {}}


def _handler(monkeysnapshot=None, monkeybalances=None, nearest=None):
    """nearest = (date_str, snapshot_dict) used when monkeysnapshot is empty (gap date)."""
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    if monkeysnapshot is not None:
        near_date, near_snap = nearest if nearest else (None, {})
        h.sheets_logger.get_snapshot_for_date = lambda d: monkeysnapshot
        h.sheets_logger.get_history_bundle = (
            lambda d, roster=None: _bundle(snapshot=monkeysnapshot) if monkeysnapshot
            else _bundle(nearest_date=near_date, nearest_snapshot=near_snap))
    if monkeybalances is not None:
        h.balance_service.get_balance_at = (
            lambda addr, chain, cutoff, deadline=None: monkeybalances.get(addr))
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
    def slow(addr, chain, cutoff, deadline=None):
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
    fallback is gone; the bundle's nearest_date/nearest_snapshot are now
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
    assert "could not be calculated" in blob     # honestly reported as failed
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
    assert "could not be calculated" in blob
    assert "KZP 96G1" in blob


@pytest.mark.parametrize("args,expected_save_date", [
    (["[2026-07-20]", "[o]"], "2026-07-20"),   # opening of the 20th IS the row dated the 20th
    (["[2026-07-20]"],        "2026-07-21"),   # default is closing: the end of the 20th is
                                               # 00:00 GMT+7 on the 21st, so the row dated 21st
])
def test_only_missing_wallets_are_rebuilt_and_saved(args, expected_save_date):
    """A wallet with a saved figure must not be rebuilt; the missing one is
    rebuilt AND written back so the date fills itself in.

    Parametrised over both bases because a one-day error in the translation would write
    a real balance onto the WRONG date in the finance record -- silently, and in a way
    that looks entirely plausible afterwards. The save date and the reconstruction cutoff
    are the two places that error would land, so both are pinned here.
    """
    from datetime import datetime, timezone, timedelta
    saved = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                      "balance": Decimal("19.41"), "batch_id": "20260720000112",
                      "time": "00:01:12"}}
    rebuilt_for, rebuilt_cutoffs, saved_rows = [], [], {}
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_history_bundle = lambda d, roster=None: _bundle(snapshot=saved)

    def fake_rebuild(addr, chain, cutoff, deadline=None):
        rebuilt_for.append(addr)
        rebuilt_cutoffs.append(cutoff)
        return Decimal("10.00")
    h.balance_service.get_balance_at = fake_rebuild
    h.sheets_logger.save_rebuilt_balances = (
        lambda date_str, rows: saved_rows.update(date=date_str, rows=rows) or (True, "B123"))

    blob = _blob(_run(h, args)[-1])
    assert rebuilt_for == ["0xabc0000000000000000000000000000000000001"]  # ONLY the missing one
    assert [r["name"] for r in saved_rows["rows"]] == ["Eth One"]
    assert saved_rows["date"] == expected_save_date
    assert "29.41" in blob                       # 19.41 saved + 10.00 rebuilt
    assert "B123" in blob                        # batch id shown on the card

    # The figure must be reconstructed at the instant the row it is written to claims,
    # or the label and the number drift apart by a day.
    expected_cutoff = int(
        datetime.strptime(f"{expected_save_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
    assert rebuilt_cutoffs == [expected_cutoff]


def test_slow_sheets_read_does_not_freeze_the_event_loop():
    """The bot serves every command and its health check on ONE event loop. The Sheets
    calls are blocking (and retry with backoff for up to ~30s), so they must run off
    the loop -- otherwise one slow Sheets call freezes the whole bot."""
    import time
    snapshot = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                         "balance": Decimal("10.00"), "batch_id": "b", "time": "t"}}

    def slow_read(date_str, roster=None):
        time.sleep(0.4)                        # blocking, like the real Sheets client
        return _bundle(snapshot=snapshot)

    h = _handler()
    h.sheets_logger.get_history_bundle = slow_read
    # keep the test off the network: the one unsaved wallet just reports unavailable
    h.balance_service.get_balance_at = lambda addr, chain, cutoff, deadline=None: None

    async def scenario():
        import bot.handlers.check_handler as ch
        ch._CHECK_EXECUTION_LOCK = False
        ticks = 0
        ctx = _FakeCtx(["[2026-07-15]"])
        task = asyncio.ensure_future(h.handle(ctx))
        while not task.done():                 # other work the loop must still get to
            await asyncio.sleep(0.02)
            ticks += 1
        await task
        return ticks

    ticks = asyncio.run(scenario())
    assert ticks > 5, f"event loop was blocked during the Sheets read (only {ticks} ticks)"


def test_rebuild_workers_are_given_the_budget_deadline():
    """Workers must be told when to stop. Without a deadline they keep issuing provider
    requests after the command gave up, and the provider request rate is shared
    process-wide -- which starves the next live /check."""
    import time
    seen = []
    h = _handler(monkeysnapshot={})
    h.RECON_TOTAL_BUDGET = 12.0

    def record(addr, chain, cutoff, deadline=None):
        seen.append(deadline)
        return Decimal("1.00")
    h.balance_service.get_balance_at = record
    h.sheets_logger.save_rebuilt_balances = lambda d, r: (True, "B1")

    _run(h, ["[2026-07-15]"])
    assert seen and all(d is not None for d in seen)      # a deadline was passed
    started = time.monotonic()
    for d in seen:
        assert started < d <= started + h.RECON_TOTAL_BUDGET   # and it is the budget


def test_second_check_while_one_is_running_gets_told_so():
    """The lock can be held for minutes by a rebuild; silence looks like a dead bot."""
    import bot.handlers.check_handler as ch
    h = _handler()
    ctx = _FakeCtx([])
    ch._CHECK_EXECUTION_LOCK = True
    try:
        result = asyncio.run(h.handle(ctx))
    finally:
        ch._CHECK_EXECUTION_LOCK = False
    assert result is False
    assert ctx.topic_manager.cards, "the blocked user must be told something"
    blob = _blob(ctx.topic_manager.cards[-1])
    assert "Another Check Is Running" in blob
    assert "already running" in blob


def test_blocked_check_survives_a_failed_send():
    """A send failure must not break the guard (or raise into the caller)."""
    import bot.handlers.check_handler as ch
    h = _handler()
    ctx = _FakeCtx([])

    async def boom(card, msg_type=None):
        raise RuntimeError("Lark is down")
    ctx.topic_manager.send_command_response = boom
    ch._CHECK_EXECUTION_LOCK = True
    try:
        assert asyncio.run(h.handle(ctx)) is False
    finally:
        ch._CHECK_EXECUTION_LOCK = False


def test_read_failure_sends_unavailable_card_and_triggers_zero_writes():
    """The bug this whole fix targets: /check [2026-07-15] on a date that was ALREADY
    fully saved rebuilt every wallet from the blockchain and wrote duplicate rows,
    because a read failure (ok=False) was silently treated as "nothing is saved".

    With the fix, get_history_bundle reporting ok=False must make the handler
    stop immediately: no classification, no rebuild, no save. Both get_balance_at
    (rebuild) and save_rebuilt_balances (write) are spied and must NEVER be called.
    """
    balance_calls = []
    save_calls = []
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_history_bundle = lambda d, roster=None: _bundle(ok=False)  # read failed

    def spy_get_balance_at(addr, chain, cutoff, deadline=None):
        balance_calls.append(addr)
        return Decimal("999.00")  # would prove a rebuild happened, if ever called

    def spy_save_rebuilt_balances(date_str, rows):
        save_calls.append((date_str, rows))
        return True, "SHOULD-NEVER-HAPPEN"

    h.balance_service.get_balance_at = spy_get_balance_at
    h.sheets_logger.save_rebuilt_balances = spy_save_rebuilt_balances

    cards = _run(h, ["[2026-07-15]"])

    assert cards, "expected at least one card"
    blob = _blob(cards[-1])
    assert "Couldn't Read Saved Balances" in blob
    assert "2026-07-15" in blob

    assert balance_calls == [], f"rebuild must never run on a read failure, got {balance_calls}"
    assert save_calls == [], f"save must never run on a read failure, got {save_calls}"


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
    h.sheets_logger.get_history_bundle = lambda d, roster=None: _bundle(snapshot=saved)
    h.sheets_logger.save_rebuilt_balances = lambda d, r: calls.append(r) or (True, "X")
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert calls == []                           # nothing to save -> no write
    assert "saved to Google Sheets" not in blob  # and no footer line
