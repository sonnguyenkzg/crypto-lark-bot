# tests/test_history_bundle.py
"""One DAILY_REPORT read must serve both the snapshot and the first-seen map.

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
ROSTER = [{"address": "TAAA", "created_at": None}, {"address": "TBBB", "created_at": "2026-07-01"}]


def test_bundle_returns_snapshot_and_first_seen_from_one_read():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS) as rd:
        b = lg.get_history_bundle("2026-07-15", ROSTER)
    assert rd.call_count == 1, "must read the sheet exactly once"
    assert b["ok"] is True
    assert set(b["snapshot"]) == {"TAAA", "TBBB"}
    assert b["first_seen"] == {"TAAA": "2026-07-15", "TBBB": "2026-07-01"}


def test_a_failed_read_reports_not_ok_and_empty_first_seen():
    """ok=False means 'I don't know', never 'nothing is saved'."""
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=None):
        b = lg.get_history_bundle("2026-07-15", ROSTER)
    assert b["ok"] is False
    assert b["snapshot"] == {}
    assert b["first_seen"] == {}


def test_first_seen_is_empty_when_no_roster_is_supplied():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        b = lg.get_history_bundle("2026-07-15")
    assert b["first_seen"] == {}
    assert set(b["snapshot"]) == {"TAAA", "TBBB"}


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
