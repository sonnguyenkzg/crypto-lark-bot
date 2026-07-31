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


# --- guards ---

def test_modifier_without_a_date_is_rejected():
    """Without this, [o] would fall through to the filter and match OKKZ wallets.

    The error card now legitimately names OKKZ/KZO COY as *example group names* a
    filtering user could type instead (Finding 3), so a blunt "OKKZ not in the card"
    check would fail on that intentional text. Assert the real guarantee instead: this
    must be the error card, not an actual wallet-balance result -- no total, no USDT
    figure, none of the balance-table card's own header.
    """
    h = CheckHandler()
    cards = run(h, ["[o]"])
    assert len(cards) == 1
    b = blob(cards)
    assert "date" in b.lower()
    assert "USDT" not in b, "must be an error card, not real wallet balances"
    assert "Wallet Balance Check" not in b


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

    def fake_bundle(date_str):
        seen["date"] = date_str
        return {"ok": True, "snapshot": {}, "nearest_date": None,
                "nearest_snapshot": {}}

    # An empty snapshot marks every real wallet in wallets.json "needs_rebuild", so
    # without this second patch the handler would issue a live provider request per
    # wallet. A unit test must never reach the network: on a machine holding working
    # API keys that would hammer a live provider and could write to the sheet.
    with patch.object(h.sheets_logger, "get_history_bundle", side_effect=fake_bundle), \
            patch.object(CheckHandler, "_rebuild_entries", return_value=None):
        run(h, args)
    assert seen["date"] == expected_target


def test_closing_of_D_reads_the_same_date_as_opening_of_D_plus_one():
    assert target_date_for("2026-07-15", "closing") == target_date_for("2026-07-16", "opening")


# --- Task 6: cards state the basis and the date they read ---

def _entries(n_saved=2):
    return [{"name": f"W{i}", "company": "CO", "address": f"T{i}", "chain": "TRC20",
             "status": "saved", "balance": 100} for i in range(n_saved)]


def _header(card):
    return card["header"]["title"]["content"]


def test_card_header_states_the_basis():
    h = CheckHandler()
    closing = h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")
    opening = h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "opening", "2026-07-15")
    assert "Closing" in _header(closing)
    assert "Opening" in _header(opening)
    assert "Opening" not in _header(closing)
    assert "Closing" not in _header(opening)


def test_closing_card_names_the_date_it_read():
    """Without this the figure cannot be reconciled against the sheet."""
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "2026-07-15" in b, "the day the user asked about"
    assert "2026-07-16" in b, "the vault date the figure came from"


def test_opening_card_does_not_mention_a_second_date():
    """For an opening query the target IS the requested date, so there is no second
    date to explain. Mentioning 2026-07-16 there would be nonsense."""
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "opening", "2026-07-15")])
    assert "2026-07-16" not in b
    assert "2026-07-14" not in b


def test_help_teaches_the_new_grammar():
    from bot.handlers.help_handler import HelpHandler
    cards = run(HelpHandler(), [])
    b = blob(cards)
    assert "[o]" in b and "[c]" in b
    assert "closing" in b.lower() and "opening" in b.lower()
