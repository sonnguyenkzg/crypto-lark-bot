"""Functional tests: drive the whole /check [date] command, assert on the rendered card.

Hermetic -- the sheet read, the reconstruction call, and the write-back are patched, so
parse -> get_history_bundle -> classify_wallets -> rebuild -> card all run for real with
no network or I/O. This is the creation-based existence rule's end-to-end safety net.

Boundaries patched (and ONLY these):
  - wallet_service.list_wallets        -> a fixed synthetic roster
  - sheets_logger._read_daily_report_rows -> fixed DAILY_REPORT rows
  - balance_service.get_balance_at     -> deterministic per-address balance (no network)
  - sheets_logger.save_rebuilt_balances-> no-op recorder (h.writes); asserts zero writes
"""
import asyncio
import json
from decimal import Decimal

from bot.handlers.check_handler import CheckHandler
import bot.handlers.check_handler as ch


def _row(date, wallet, address, balance, company="CO", batch="20260101000100", ctype="scheduled"):
    # cols: batch, date, time, wallet, company, address, balance, check_type
    return [batch, date, "00:00:00", wallet, company, address, str(balance), ctype]


class _Topic:
    def __init__(self):
        self.cards = []

    async def send_command_response(self, card, msg_type=None):
        self.cards.append(card)


class _Ctx:
    def __init__(self, args):
        self.args = args
        self.sender_id = "ou_fn"
        self.topic_manager = _Topic()


def _wallet_list_data(roster):
    companies = {}
    for w in roster:
        companies.setdefault(w["company"], []).append(
            {"name": w["wallet"], "address": w["address"],
             "chain": w.get("chain", "TRC20"), "created_at": w.get("created_at")})
    return (True, {"companies": companies})


def make_handler(rows_list, roster, balances=None):
    """A CheckHandler with the four external boundaries patched. `roster` is a list of
    {wallet, company, address[, chain]}. `balances` maps address -> reconstructed value
    returned by get_balance_at. `h.writes` collects any attempted sheet write."""
    h = CheckHandler()
    h.writes = []              # (target_date, entries) per save_rebuilt_balances call
    h.balance_at_calls = []    # (address, cutoff_ms) per get_balance_at call

    def _no_write(target_date, entries):
        h.writes.append((target_date, entries))
        return (False, None)

    bals = {k: Decimal(str(v)) for k, v in (balances or {}).items()}

    def _get_balance_at(address, chain, cutoff_ms, deadline=None):
        h.balance_at_calls.append((address, cutoff_ms))
        return bals.get(address)

    h.wallet_service.list_wallets = lambda: _wallet_list_data(roster)
    # rows_list is None to simulate a FAILED read (distinct from an empty sheet).
    h.sheets_logger._read_daily_report_rows = (
        (lambda: None) if rows_list is None else (lambda: list(rows_list)))
    h.sheets_logger.save_rebuilt_balances = _no_write
    h.balance_service.get_balance_at = _get_balance_at
    return h


def cutoff_date_gmt7(cutoff_ms):
    """The GMT+7 calendar date a reconstruction cutoff (epoch ms) falls on -- used to
    prove the rebuild uses the VAULT target_date, not the user's date."""
    from datetime import datetime, timezone, timedelta
    return datetime.fromtimestamp(cutoff_ms / 1000,
                                  tz=timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


def run(h, args):
    ch._CHECK_EXECUTION_LOCK = False
    ctx = _Ctx(args)
    asyncio.run(h.handle(ctx))
    return ctx.topic_manager.cards


def summary(cards):
    """The final card's joined element text, with ** stripped, for substring asserts."""
    final = cards[-1]
    return " ".join(e.get("text", {}).get("content", "")
                    for e in final.get("elements", [])).replace("**", "")


def blob(cards):
    return json.dumps(cards).replace("**", "")


ROSTER5 = [
    {"wallet": "EARLY", "company": "CO",  "address": "TEARLY"},
    {"wallet": "MIDA",  "company": "CO",  "address": "TMIDA"},
    {"wallet": "MIDB",  "company": "DAO", "address": "TMIDB"},
    {"wallet": "LATE1", "company": "CO",  "address": "TLATE1"},
    {"wallet": "LATE2", "company": "CO",  "address": "TLATE2"},
]


# --- Scenario 1: fully-saved opening date lists saved wallets and names the added-later ones ---

def test_fully_saved_opening_lists_saved_and_added_later():
    # EARLY/MIDA/MIDB hold a balance on the queried date; LATE1/LATE2 are first funded
    # 2026-06-01, so on 2026-05-10 they are "added on or after this date".
    rows = [
        _row("2026-05-10", "EARLY", "TEARLY", 100),
        _row("2026-05-10", "MIDA", "TMIDA", 200),
        _row("2026-05-10", "MIDB", "TMIDB", 300, company="DAO"),
        _row("2026-06-01", "LATE1", "TLATE1", 50),
        _row("2026-06-01", "LATE2", "TLATE2", 60),
    ]
    h = make_handler(rows, ROSTER5)
    cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    assert "Total wallets in monitoring: 5" in s
    assert "3 have a balance recorded" in s
    assert "added on or after this date" in s
    assert "LATE1" in s and "LATE2" in s          # <=6 not-yet-created -> named
    assert "3 wallets counted" in s
    assert h.writes == []                          # a fully-saved opening writes nothing


# --- Scenario 2: many not-yet-created wallets are summarised by count, not named ---

def test_many_not_yet_created_are_summarised_by_count():
    roster = [{"wallet": "KEEP", "company": "CO", "address": "TKEEP"}] + [
        {"wallet": f"L{i}", "company": "CO", "address": f"TL{i}"} for i in range(1, 8)]  # 7 late
    rows = [_row("2026-05-10", "KEEP", "TKEEP", 100)] + [
        _row("2026-06-01", f"L{i}", f"TL{i}", 10) for i in range(1, 8)]
    h = make_handler(rows, roster)
    cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    assert "7 wallets were added on or after this date" in s   # >6 -> count, not names
    assert "L3" not in s and "L7" not in s                     # individual names NOT listed
    assert "1 wallets counted" in s or "1 wallet counted" in s
    assert h.writes == []


# --- Scenario 3: money held before the query date is always counted, never "added later" ---

def test_money_before_monitoring_is_counted_never_added_later():
    # EARLY first funded 2026-01-01 (earliest in the sheet) and still holds a balance on
    # the query date; it must appear in the counted table, never in the added-later line.
    rows = [
        _row("2026-01-01", "EARLY", "TEARLY", 999999),
        _row("2026-05-10", "EARLY", "TEARLY", 999999),
        _row("2026-06-01", "LATE1", "TLATE1", 5),          # genuinely later -> added-later
    ]
    roster = [
        {"wallet": "EARLY", "company": "CO", "address": "TEARLY"},
        {"wallet": "LATE1", "company": "CO", "address": "TLATE1"},
    ]
    h = make_handler(rows, roster)
    cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    b = blob(cards)
    assert "EARLY" in b                                     # present in the card
    assert "added on or after this date" in s               # LATE1 is the added-later one
    added_line = [ln for ln in s.split("•") if "added on or after" in ln][0]
    assert "EARLY" not in added_line                        # EARLY is NOT in that line
    assert "1 have a balance recorded" in s                 # EARLY counted


# --- Scenario 4: below coverage_start we reconstruct, never claim "added later" (no hide) ---

def test_below_coverage_start_reconstructs_and_hides_nothing():
    # The sheet has a PRE-2026 anchor row (2025-11-01), so coverage_start =
    # max(2025-11-01, VAULT_COMPLETE_FROM=2026-01-01) = 2026-01-01 -- the constant binds.
    # SPARSE was first RECORDED on 2026-03-01 but is queried at 2025-12-15, which is below
    # the verified-complete floor: the sparse pre-2026 vault cannot prove SPARSE did not
    # exist, so it must reconstruct from chain, NOT be reported "added on or after". If the
    # floor were wrongly lowered to the anchor date, SPARSE would be hidden -- this is the
    # test that catches that. (Guards the VAULT_COMPLETE_FROM constant specifically.)
    rows = [
        _row("2025-11-01", "ANCHOR", "TANCHOR", 50),   # pre-2026 -> makes the constant bind
        _row("2025-12-15", "ANCHOR", "TANCHOR", 50),   # ANCHOR saved on the query date
        _row("2026-03-01", "SPARSE", "TSPARSE", 200),  # SPARSE first recorded here
    ]
    roster = [
        {"wallet": "ANCHOR", "company": "CO", "address": "TANCHOR"},
        {"wallet": "SPARSE", "company": "CO", "address": "TSPARSE"},
    ]
    h = make_handler(rows, roster, balances={"TSPARSE": 1234})
    cards = run(h, ["[2025-12-15]", "[o]"])
    s = summary(cards)
    assert "added on or after this date" not in s          # SPARSE not hidden below the floor
    assert "1 have a balance recorded" in s                # ANCHOR (saved)
    assert "1 were calculated from blockchain records" in s  # SPARSE (reconstructed)
    assert "2 wallets counted" in s
    assert len(h.writes) == 1                              # rebuilt SPARSE saved back


# --- Scenario 5: an in-window gap wallet reconstructs from the chain ---

def test_in_window_gap_wallet_is_reconstructed():
    # MIDA existed since 2026-04-01 but has no row on the queried 2026-05-10 -> it is a real
    # gap (date >= first_funded, >= coverage_start) and must reconstruct, not be hidden.
    rows = [
        _row("2026-05-10", "EARLY", "TEARLY", 100),
        _row("2026-04-01", "MIDA", "TMIDA", 150),          # exists earlier, gap on query date
        _row("2026-05-10", "MIDB", "TMIDB", 300, company="DAO"),
    ]
    roster = [
        {"wallet": "EARLY", "company": "CO", "address": "TEARLY"},
        {"wallet": "MIDA", "company": "CO", "address": "TMIDA"},
        {"wallet": "MIDB", "company": "DAO", "address": "TMIDB"},
    ]
    h = make_handler(rows, roster, balances={"TMIDA": 222})
    cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    assert "added on or after this date" not in s
    assert "1 were calculated from blockchain records" in s
    assert "2 have a balance recorded" in s
    assert "MIDA" in blob(cards)
    assert len(h.writes) == 1


# --- Scenario 6: a non-zero-padded sheet date still matches its calendar date ---

def test_non_padded_sheet_date_is_matched_not_hidden():
    rows = [_row("2026-7-05", "EARLY", "TEARLY", 500)]     # note: 2026-7-05, not 2026-07-05
    roster = [{"wallet": "EARLY", "company": "CO", "address": "TEARLY"}]
    h = make_handler(rows, roster)
    cards = run(h, ["[2026-07-05]", "[o]"])
    s = summary(cards)
    assert "added on or after this date" not in s          # the saved row is found, not hidden
    assert "1 have a balance recorded" in s
    assert "1 wallets counted" in s or "1 wallet counted" in s
    assert h.writes == []


# --- Scenario 7: a company filter narrows scope and reconciles ---

def test_company_filter_narrows_scope():
    rows = [_row("2026-05-10", w["wallet"], w["address"], 100,
                 company=w["company"]) for w in ROSTER5]
    h = make_handler(rows, ROSTER5)
    cards = run(h, ["[2026-05-10]", "[DAO]", "[o]"])
    s = summary(cards)
    assert "Wallets in scope: 1 of 5 monitored" in s
    assert "MIDB" in blob(cards)
    assert "EARLY" not in blob(cards)


# --- Scenario 8: a closing query reads the D+1 vault row ---

def test_closing_reads_the_next_day_row():
    # EARLY has a row only on 2026-05-11. closing(2026-05-10) == the 2026-05-11 row.
    rows = [_row("2026-05-11", "EARLY", "TEARLY", 777)]
    roster = [{"wallet": "EARLY", "company": "CO", "address": "TEARLY"}]
    h = make_handler(rows, roster)
    cards = run(h, ["[2026-05-10]", "[c]"])
    s = summary(cards)
    assert "1 have a balance recorded" in s                # found via the D+1 row
    assert "2026-05-11" in s                               # basis line names the vault date
    assert h.writes == []


# --- Scenario 9: a failed sheet read yields the unavailable card, no rebuild, no write ---

def test_sheet_read_failure_is_an_error_card_no_write():
    h = make_handler(None, ROSTER5)                        # None -> read returns None
    cards = run(h, ["[2026-05-10]"])
    b = blob(cards)
    assert len(cards) == 1                                 # only the error card
    assert "counted" not in b                              # not a balance result
    assert "USDT" not in b                                 # no balance table
    assert h.writes == []                                  # nothing reconstructed or saved


# --- Scenario 10: closing + rebuild uses the D+1 vault date for cutoff AND write-back ---

def test_closing_rebuild_uses_next_day_for_cutoff_and_write():
    # EARLY existed since 2026-05-09 but has NO row on 2026-05-11. A CLOSING query for
    # 2026-05-10 targets the 2026-05-11 vault row, so EARLY is a gap that must reconstruct
    # AT 2026-05-11 00:00 GMT+7 and be written back under date 2026-05-11 -- not 2026-05-10.
    # (Scenario 8 only covered closing READS; this covers the closing REBUILD path, which
    # is where a target_date-vs-date_str mix-up would silently reconstruct the wrong day.)
    rows = [_row("2026-05-09", "EARLY", "TEARLY", 100)]     # exists earlier, gap on 05-11
    roster = [{"wallet": "EARLY", "company": "CO", "address": "TEARLY"}]
    h = make_handler(rows, roster, balances={"TEARLY": 321})
    cards = run(h, ["[2026-05-10]", "[c]"])
    s = summary(cards)
    assert "1 were calculated from blockchain records" in s
    # the reconstruction cutoff is the D+1 vault date, not the user's date
    assert h.balance_at_calls, "closing gap wallet must trigger a reconstruction"
    assert cutoff_date_gmt7(h.balance_at_calls[0][1]) == "2026-05-11"
    # the rebuilt row is saved under the D+1 vault date
    assert len(h.writes) == 1 and h.writes[0][0] == "2026-05-11"


# --- Scenario 11: a zero-balance row before the first positive one is NOT creation ---

def test_zero_balance_row_does_not_count_as_creation():
    # ZEROFIRST has a 0.00 row on 2026-01-01 and its first POSITIVE balance on 2026-03-01.
    # Creation is the first POSITIVE balance, so a query at 2026-02-01 (after the zero row,
    # before the positive one) must report ZEROFIRST as "added on or after this date" -- and
    # must NOT reconstruct it. If _first_funded_from_rows regressed to treat the 0.00 row as
    # creation, ZEROFIRST would instead reconstruct. Guards the "positive balance" rule.
    rows = [
        _row("2026-02-01", "ANCHOR", "TANCHOR", 100),      # saved on the query date
        _row("2026-01-01", "ZEROFIRST", "TZERO", 0),       # zero -> NOT creation
        _row("2026-03-01", "ZEROFIRST", "TZERO", 500),     # first positive -> creation
    ]
    roster = [
        {"wallet": "ANCHOR", "company": "CO", "address": "TANCHOR"},
        {"wallet": "ZEROFIRST", "company": "CO", "address": "TZERO"},
    ]
    h = make_handler(rows, roster, balances={"TZERO": 999})   # provided but must NOT be used
    cards = run(h, ["[2026-02-01]", "[o]"])
    s = summary(cards)
    assert "added on or after this date" in s
    added_line = [ln for ln in s.split("•") if "added on or after" in ln][0]
    assert "ZEROFIRST" in added_line                        # classified not_yet_created
    assert "1 have a balance recorded" in s                 # only ANCHOR counted
    assert h.balance_at_calls == []                         # ZEROFIRST was NOT reconstructed
    assert h.writes == []


# --- Scenario 12: a wallet with NO positive row anywhere (unknown creation) reconstructs ---

def test_unknown_creation_wallet_reconstructs_not_hidden():
    # GHOST is in the roster but has NO row at all in the sheet, so it is absent from
    # first_funded -- its creation is UNKNOWN. Unknown is not evidence of non-existence, so
    # on/after coverage_start it must RECONSTRUCT from chain, never be "added on or after".
    # A regression that treated unknown first_funded as not-yet-created would hide a wallet
    # that may hold money; this scenario is the guard for that branch.
    rows = [_row("2026-05-10", "ANCHOR", "TANCHOR", 100)]   # only ANCHOR has any row
    roster = [
        {"wallet": "ANCHOR", "company": "CO", "address": "TANCHOR"},
        {"wallet": "GHOST", "company": "CO", "address": "TGHOST"},   # no rows anywhere
    ]
    h = make_handler(rows, roster, balances={"TGHOST": 777})
    cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    assert "added on or after this date" not in s          # GHOST is NOT hidden
    assert "1 have a balance recorded" in s                # ANCHOR (saved)
    assert "1 were calculated from blockchain records" in s  # GHOST (reconstructed)
    assert any(addr == "TGHOST" for addr, _ in h.balance_at_calls)  # GHOST WAS reconstructed
    assert len(h.writes) == 1                              # rebuilt GHOST saved back
