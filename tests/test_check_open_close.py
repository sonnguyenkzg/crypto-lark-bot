# tests/test_check_open_close.py
"""/check [D] resolves to a vault DATE, then runs the existing pipeline against it."""
import asyncio
from unittest.mock import patch

import pytest

from bot.handlers.check_handler import CheckHandler
from bot.services.vault_calendar import target_date_for


class Topic:
    def __init__(self):
        self.cards = []

    async def send_command_response(self, card, msg_type=None):
        self.cards.append(card)


class Ctx:
    def __init__(self, args):
        self.args = args
        self.sender_id = "ou_test"
        self.topic_manager = Topic()


def run(handler, args):
    ctx = Ctx(args)
    asyncio.run(handler.handle(ctx))
    return ctx.topic_manager.cards


def titles(cards):
    return " | ".join(c["header"]["title"]["content"] for c in cards if isinstance(c, dict))


def blob(cards):
    import json
    return json.dumps(cards)


# --- classify_wallets now decides existence from first_seen ---

def test_classify_uses_first_seen_not_created_at():
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-01-15"}]
    # created_at says January, but we hold a measured row from December
    first_seen = {"TAAA": "2025-12-17"}
    out = h.classify_wallets(roster, {}, "2025-12-20", first_seen)
    assert out[0]["status"] == "needs_rebuild", "existed by then, so we should expect a figure"


def test_classify_excludes_a_wallet_created_after_the_date():
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-03-01"}]
    out = h.classify_wallets(roster, {}, "2026-01-01", {"TAAA": "2026-03-01"})
    assert out[0]["status"] == "not_yet_created"


def test_classify_never_excludes_a_wallet_that_has_a_saved_row():
    """The guarantee: a saved figure always wins over any existence judgement."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2099-01-01"}]
    snapshot = {"TAAA": {"wallet_name": "W1", "company": "CO", "address": "TAAA",
                         "balance": 42, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets(roster, snapshot, "2026-07-15", {"TAAA": "2026-07-15"})
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 42


def test_classify_falls_back_when_first_seen_is_unknown():
    """No signal either way -> assume it existed, the safe direction, as before."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": None}]
    out = h.classify_wallets(roster, {}, "2026-01-01", {"TAAA": None})
    assert out[0]["status"] == "needs_rebuild"


def test_classify_still_works_without_a_first_seen_map():
    """Backward compatibility: the 3-argument call keeps the old created_at behaviour."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-03-01"}]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert out[0]["status"] == "not_yet_created"


# --- guards ---

def test_modifier_without_a_date_is_rejected():
    """Without this, [o] would fall through to the filter and match OKKZ wallets."""
    h = CheckHandler()
    cards = run(h, ["[o]"])
    assert len(cards) == 1
    assert "date" in blob(cards).lower()
    assert "OKKZ" not in blob(cards)


def test_opening_and_closing_together_is_rejected():
    h = CheckHandler()
    cards = run(h, ["[2026-07-15]", "[o]", "[c]"])
    assert len(cards) == 1
    b = blob(cards).lower()
    assert "opening" in b and "closing" in b


def test_closing_of_today_is_refused_and_points_at_the_opening():
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    h = CheckHandler()
    cards = run(h, [f"[{today}]"])
    b = blob(cards)
    assert len(cards) == 1
    assert "[o]" in b, "must tell the user how to get the figure that does exist"


def test_opening_of_today_is_allowed():
    """Opening of today is the row written at ~00:01 this morning -- it exists."""
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    h = CheckHandler()
    with patch.object(CheckHandler, "_handle_historical", return_value=True) as hh:
        run(h, [f"[{today}]", "[o]"])
    assert hh.called, "opening of today must reach the historical path, not a guard"
    assert hh.call_args[0][1] == today


# --- date translation reaches the pipeline ---

@pytest.mark.parametrize("args,expected_target", [
    (["[2026-07-15]"],          "2026-07-16"),   # default = closing
    (["[2026-07-15]", "[c]"],   "2026-07-16"),
    (["[2026-07-15]", "[o]"],   "2026-07-15"),
])
def test_target_date_passed_to_the_pipeline(args, expected_target):
    h = CheckHandler()
    seen = {}

    def fake_bundle(date_str, roster=None):
        seen["date"] = date_str
        return {"ok": True, "snapshot": {}, "nearest_date": None,
                "nearest_snapshot": {}, "first_seen": {}}

    with patch.object(h.sheets_logger, "get_history_bundle", side_effect=fake_bundle):
        run(h, args)
    assert seen["date"] == expected_target


def test_closing_of_D_reads_the_same_date_as_opening_of_D_plus_one():
    assert target_date_for("2026-07-15", "closing") == target_date_for("2026-07-16", "opening")
