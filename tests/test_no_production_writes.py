"""Proves the test suite cannot reach the production sheet."""
import os
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger


def test_sheet_credentials_are_not_visible_to_tests():
    assert not os.getenv("GOOGLE_SHEET_ID")
    assert not os.getenv("GOOGLE_CREDENTIALS_FILE")


def test_logger_refuses_to_write_without_credentials():
    from decimal import Decimal
    L = GoogleSheetsBalanceLogger()
    ok, batch = L.save_rebuilt_balances("2026-07-15", [
        {"name": "X", "company": "C", "address": "TAAA", "balance": Decimal("1")}])
    assert ok is False and batch is None


def test_logger_read_reports_failure_without_credentials():
    snapshot, nearest_date, nearest_snapshot, ok = \
        GoogleSheetsBalanceLogger().get_snapshot_and_nearest("2026-07-15")
    assert ok is False and snapshot == {}
