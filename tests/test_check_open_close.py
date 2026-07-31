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


# --- the existence boundary: a row dated D is the balance at 00:00 GMT+7 on D ---

def test_a_wallet_created_during_D_is_not_expected_to_have_a_figure_for_D():
    """THE boundary. A wallet created at any time during D did not exist at 00:00 GMT+7
    on D, which is the only instant a row dated D describes. Reporting it as missing
    made the bot reconstruct and SAVE a balance for a moment when nobody was monitoring
    the wallet -- 40 wallet-days across 18 dates in the live record. Its first real
    figure is the row dated D+1, which is where its first saved row already sits."""
    h = CheckHandler()
    roster = [{"wallet": "KZDW FIN OPS TRC 1", "address": "TAAA", "company": "KZDW",
               "created_at": "2026-07-16"}]
    out = h.classify_wallets(roster, {}, "2026-07-16", {"TAAA": "2026-07-16"})
    assert out[0]["status"] == "not_yet_created"


def test_a_wallet_created_the_day_before_D_is_expected_to_have_a_figure_for_D():
    """The other side of the same boundary: it was there through all of D's 00:00."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-07-15"}]
    out = h.classify_wallets(roster, {}, "2026-07-16", {"TAAA": "2026-07-15"})
    assert out[0]["status"] == "needs_rebuild"


def test_a_saved_row_still_wins_when_first_seen_equals_the_date():
    """The guarantee, at the exact point a careless `<` would do real damage.

    first_seen == D says "did not exist at D's 00:00", but a row for D is sitting right
    there. A saved figure is evidence and must always beat a judgement about existence,
    so this must classify as `saved` and keep its balance -- never `not_yet_created`,
    which would silently drop a real recorded figure out of the reported total."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-07-16"}]
    snapshot = {"TAAA": {"wallet_name": "W1", "company": "CO", "address": "TAAA",
                         "balance": 1234, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets(roster, snapshot, "2026-07-16", {"TAAA": "2026-07-16"})
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 1234


def test_the_legacy_created_at_fallback_uses_the_same_boundary():
    """No first_seen map -> created_at alone, but the same reasoning must apply, or the
    two paths disagree about the same wallet on the same day."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO",
               "created_at": "2026-07-16 15:15:55"}]
    assert h.classify_wallets(roster, {}, "2026-07-16")[0]["status"] == "not_yet_created"
    assert h.classify_wallets(roster, {}, "2026-07-17")[0]["status"] == "needs_rebuild"


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

    def fake_bundle(date_str, roster=None):
        seen["date"] = date_str
        return {"ok": True, "snapshot": {}, "nearest_date": None,
                "nearest_snapshot": {}, "first_seen": {}}

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


# --- classify_wallets is addressed by target_date in the historical handler, not date_str ---

def test_wallet_added_on_dplus1_needs_rebuild_for_closing_of_d():
    """Fence for the ONE vault-addressing site with no direct test: `classify_wallets` in
    `_handle_historical` must be called with `target_date`, not `date_str`. Reverting
    that one call leaves the rest of the suite green, so this test exists solely to
    catch the revert.

    A wallet first seen on D itself did not exist at D's own 00:00 GMT+7 boundary, but
    it certainly existed by D+1's. Closing-of-D reads the row dated D+1, so the wallet
    must classify as needs_rebuild. Addressed by date_str (D) instead, the same wallet
    reads as not_yet_created and silently vanishes from the report.

    That straddle is deliberate: the fixture sits exactly one day either side of the
    strict existence boundary, so this test fails if the handler passes the wrong date
    AND stays honest about which date it is really exercising.
    """
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, {"companies": {
        "CO": [{"name": "W1", "address": "TAAA", "chain": "TRC20", "created_at": None}]}})

    def fake_bundle(date_str, roster=None):
        return {"ok": True, "snapshot": {}, "nearest_date": None,
                "nearest_snapshot": {}, "first_seen": {"TAAA": "2026-07-15"}}

    with patch.object(h.sheets_logger, "get_history_bundle", side_effect=fake_bundle), \
            patch.object(CheckHandler, "_rebuild_entries", return_value=None):
        cards = run(h, ["[2026-07-15]"])   # default mode = closing -> target_date 2026-07-16

    assert "Rebuilding" in titles(cards), (
        "the wallet existed by 2026-07-16 (the closing target date), so it must need "
        "rebuilding for 2026-07-15's closing figure, not be dropped as not_yet_created")


# --- Task 6: cards state the basis and the date they read ---

def _entries(n_saved=2, n_later=0):
    out = [{"name": f"W{i}", "company": "CO", "address": f"T{i}", "chain": "TRC20",
            "status": "saved", "balance": 100} for i in range(n_saved)]
    out += [{"name": f"L{i}", "company": "CO", "address": f"L{i}", "chain": "TRC20",
             "status": "not_yet_created", "balance": None} for i in range(n_later)]
    return out


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


def test_added_later_wallets_are_named_when_there_are_five_or_fewer():
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(2, 3), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "L0" in b and "L1" in b and "L2" in b


def test_added_later_wallets_are_counted_when_there_are_more_than_five():
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(2, 41), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "41" in b
    assert "L40" not in b, "must not list forty-one wallet names"


def test_help_teaches_the_new_grammar():
    from bot.handlers.help_handler import HelpHandler
    cards = run(HelpHandler(), [])
    b = blob(cards)
    assert "[o]" in b and "[c]" in b
    assert "closing" in b.lower() and "opening" in b.lower()
