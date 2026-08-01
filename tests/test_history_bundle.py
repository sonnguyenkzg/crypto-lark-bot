# tests/test_history_bundle.py
"""One DAILY_REPORT read must serve the snapshot the dated check needs.

The sheet is ~17,500 rows; reading it twice per command would double the quota cost
for data we already have in memory.
"""
from unittest.mock import patch

from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger


def _row(date, address, balance="10.00", batch="20260101000100"):
    return [batch, date, "00:00:00", "W-" + address, "CO", address, balance, "scheduled"]


ROWS = [
    _row("2026-07-15", "TAAA", "100.00"),
    _row("2026-07-15", "TBBB", "200.00"),
    _row("2026-07-16", "TAAA", "150.00"),
]


def test_bundle_returns_snapshot_from_one_read():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS) as rd:
        b = lg.get_history_bundle("2026-07-15")
    assert rd.call_count == 1, "must read the sheet exactly once"
    assert b["ok"] is True
    assert set(b["snapshot"]) == {"TAAA", "TBBB"}


def test_a_failed_read_reports_not_ok():
    """ok=False means 'I don't know', never 'nothing is saved'."""
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=None):
        b = lg.get_history_bundle("2026-07-15")
    assert b["ok"] is False
    assert b["snapshot"] == {}
    assert b["first_funded"] == {}
    assert b["coverage_start"] is None


def test_first_funded_is_earliest_positive_balance_date():
    """first_funded marks each wallet's on-chain creation -- the earliest date it held a
    positive balance, ignoring earlier zero rows and out-of-order batches."""
    rows = [
        _row("2026-03-01", "TAAA", "0.00"),      # exists on chain but empty -> not creation
        _row("2026-03-05", "TAAA", "100.00"),    # first positive -> creation
        _row("2026-03-02", "TAAA", "50.00"),     # earlier positive, arrives later in list
        _row("2026-04-01", "TBBB", "0"),         # TBBB only ever zero -> absent from map
    ]
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=rows):
        b = lg.get_history_bundle("2026-07-15")
    assert b["first_funded"]["TAAA"] == "2026-03-02"
    assert "TBBB" not in b["first_funded"]
    # rows begin 2026-03-01 (after VAULT_COMPLETE_FROM), so the trust floor is that date
    assert b["coverage_start"] == "2026-03-01"


def test_coverage_start_never_precedes_the_verified_complete_floor():
    """A sparse pre-backfill row must not lower the trust floor below VAULT_COMPLETE_FROM,
    or a pre-backfill date could wrongly claim not_yet_created and hide money."""
    from bot.services.google_sheets_logger import VAULT_COMPLETE_FROM
    rows = [
        _row("2025-09-22", "TAAA", "5.00"),   # sparse pre-backfill row
        _row("2026-04-01", "TBBB", "5.00"),
    ]
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=rows):
        b = lg.get_history_bundle("2026-04-01")
    assert b["coverage_start"] == VAULT_COMPLETE_FROM   # floored, not 2025-09-22


def test_non_padded_sheet_date_still_matches_and_is_not_hidden():
    """A hand-edited non-zero-padded cell ('2026-7-20') must still match its calendar
    date: the saved positive balance is found, not missed and then hidden. Guards the
    exact case Codex flagged -- raw '2026-07-20' < '2026-7-20' would sort it as pre-
    existence."""
    from bot.handlers.check_handler import CheckHandler
    rows = [
        _row("2026-07-01", "TBBB", "1.00"),
        [ "b2", "2026-7-20", "00:00:00", "W-TAAA", "CO", "TAAA", "100.00", "scheduled"],
    ]
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=rows):
        b = lg.get_history_bundle("2026-07-20")
    assert b["snapshot"].get("TAAA", {}).get("balance") == 100.0, "the saved row must be found"
    assert b["first_funded"]["TAAA"] == "2026-07-20", "first_funded is stored canonical"
    roster = [{"wallet": "V", "company": "CO", "address": "TAAA", "chain": "TRC20"}]
    out = CheckHandler().classify_wallets(roster, b["snapshot"], "2026-07-20",
                                          first_funded=b["first_funded"],
                                          coverage_start=b["coverage_start"])
    assert out[0]["status"] == "saved" and out[0]["balance"] == 100.0, \
        "a real balance must never be hidden by a date-format quirk"


def test_first_funded_present_on_nearest_and_exact_paths():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        exact = lg.get_history_bundle("2026-07-15")     # snapshot hit
        nearest = lg.get_history_bundle("2026-07-20")   # falls to nearest
    assert exact["first_funded"] == {"TAAA": "2026-07-15", "TBBB": "2026-07-15"}
    assert nearest["first_funded"] == {"TAAA": "2026-07-15", "TBBB": "2026-07-15"}


def test_legacy_four_tuple_still_works_unchanged():
    """Existing callers and tests must not break."""
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        snapshot, nearest_date, nearest_snapshot, ok = lg.get_snapshot_and_nearest("2026-07-15")
    assert ok is True
    assert set(snapshot) == {"TAAA", "TBBB"}
    assert nearest_date is None


def test_legacy_four_tuple_on_a_date_with_no_rows():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        snapshot, nearest_date, nearest_snapshot, ok = lg.get_snapshot_and_nearest("2026-07-20")
    assert ok is True
    assert snapshot == {}
    assert nearest_date in ("2026-07-15", "2026-07-16")
