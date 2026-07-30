# tests/test_vault_day_boundary.py
"""A rebuilt row's Time column must state the instant the figure describes, and the
reconstruction must compute at that same instant.

These drifted once: rebuilt rows carried the time they were COMPUTED (e.g. 14:26:51 on
2026-07-30 for a 2026-07-20 balance), so the row read as a mid-afternoon figure when the
number was really the day's opening balance. These tests pin them together.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from bot.services.google_sheets_logger import (
    GoogleSheetsBalanceLogger, VAULT_DAY_BOUNDARY, REBUILT_TIME)

GMT7 = timezone(timedelta(hours=7))


def test_rebuilt_time_is_the_day_boundary_not_the_computation_time():
    """The Time column must be the boundary, whatever the wall clock says."""
    lg = GoogleSheetsBalanceLogger()
    lg.credentials_file = "x.json"
    lg.spreadsheet_id = "sheet"
    captured = {}

    def fake_append(sheet_name, data_rows):
        captured["sheet"] = sheet_name
        captured["rows"] = data_rows
        return {"updates": {"updatedRows": len(data_rows)}}

    with patch.object(lg, "_initialize_service", return_value=True), \
         patch.object(lg, "_ensure_headers"), \
         patch.object(lg, "_append_rows_with_retry", side_effect=fake_append), \
         patch.object(lg, "_generate_batch_id", return_value="20260730142651"):
        ok, batch_id = lg.save_rebuilt_balances(
            "2026-07-20",
            [{"name": "KZDW DPP TH 2", "company": "KZDW",
              "address": "THjjvEd1KHUxQgZhGB3AYmoBYAZcBQVy1L", "balance": 108144.34}])

    assert ok is True
    row = captured["rows"][0]
    assert captured["sheet"] == "DAILY_REPORT"
    assert row[0] == "20260730142651", "Batch ID must stay the WRITE time (audit trail)"
    assert row[1] == "2026-07-20", "Date must be the date described"
    assert row[2] == "00:00:00", "Time must be the day boundary, not when we computed it"
    assert row[2] == REBUILT_TIME == VAULT_DAY_BOUNDARY
    assert row[7] == "rebuilt"


def test_rebuilt_time_never_equals_the_wall_clock_by_accident():
    """Guard against a regression that reintroduces datetime.now() for the Time column."""
    import bot.services.google_sheets_logger as mod
    src = open(mod.__file__).read()
    body = src[src.index("def save_rebuilt_balances"):]
    body = body[:body.index("\n    def ", 10)] if "\n    def " in body[10:] else body
    assert "strftime" not in body, (
        "save_rebuilt_balances must not format a wall-clock time into a row; "
        "use REBUILT_TIME so the label matches the reconstructed instant")


def test_reconstruction_cutoff_matches_the_time_written():
    """CheckHandler must reconstruct at exactly the instant the saved row will claim."""
    date_str = "2026-07-20"
    cutoff_ms = int(datetime.strptime(f"{date_str} {VAULT_DAY_BOUNDARY}", "%Y-%m-%d %H:%M:%S")
                    .replace(tzinfo=GMT7).timestamp() * 1000)
    # the instant a reader would infer from the saved row's Date + Time columns
    implied_ms = int(datetime.strptime(f"{date_str} {REBUILT_TIME}", "%Y-%m-%d %H:%M:%S")
                     .replace(tzinfo=GMT7).timestamp() * 1000)
    assert cutoff_ms == implied_ms


def test_boundary_is_gmt7_midnight_not_utc_midnight():
    """A GMT+7 day boundary is 17:00 UTC the previous day. Guards against a UTC slip."""
    cutoff = datetime.strptime(f"2026-07-20 {VAULT_DAY_BOUNDARY}", "%Y-%m-%d %H:%M:%S") \
        .replace(tzinfo=GMT7)
    as_utc = cutoff.astimezone(timezone.utc)
    assert (as_utc.hour, as_utc.minute) == (17, 0)
    assert as_utc.date().isoformat() == "2026-07-19"


def test_check_handler_imports_the_shared_constant():
    """The cutoff must be derived from the constant, not a hardcoded literal."""
    import bot.handlers.check_handler as ch
    src = open(ch.__file__).read()
    assert "VAULT_DAY_BOUNDARY" in src
    assert '" 00:01:00"' not in src, "stale hardcoded cutoff still present"
