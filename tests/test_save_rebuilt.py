# tests/test_save_rebuilt.py
from decimal import Decimal
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

def _logger(monkeypatch, captured):
    L = GoogleSheetsBalanceLogger()
    L.credentials_file = "x"; L.spreadsheet_id = "y"
    monkeypatch.setattr(L, "_initialize_service", lambda: True)
    monkeypatch.setattr(L, "_ensure_headers", lambda name: None)
    monkeypatch.setattr(L, "_append_rows_with_retry",
                        lambda sheet, rows: captured.update(sheet=sheet, rows=rows)
                        or {"updates": {"updatedCells": len(rows) * 8}})
    return L

def test_saves_rows_with_rebuilt_marker(monkeypatch):
    cap = {}
    L = _logger(monkeypatch, cap)
    ok, batch = L.save_rebuilt_balances("2026-07-20", [
        {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "balance": Decimal("19.41")},
    ])
    assert ok is True and batch
    assert cap["sheet"] == "DAILY_REPORT"
    row = cap["rows"][0]
    # cols: batch, date, time, wallet, company, address, balance, check type
    assert row[1] == "2026-07-20"          # the DATE ASKED FOR, not today
    assert row[3] == "KZP 96G1"
    assert row[5] == "TAAA"
    assert row[6] == "19.41"
    assert row[7] == "rebuilt"             # distinguishable from a measured row

def test_no_rows_is_not_an_error(monkeypatch):
    cap = {}
    L = _logger(monkeypatch, cap)
    assert L.save_rebuilt_balances("2026-07-20", []) == (False, None)
    assert cap == {}                        # nothing written

def test_write_failure_reports_false(monkeypatch):
    L = GoogleSheetsBalanceLogger()
    L.credentials_file = "x"; L.spreadsheet_id = "y"
    monkeypatch.setattr(L, "_initialize_service", lambda: True)
    monkeypatch.setattr(L, "_ensure_headers", lambda name: None)
    monkeypatch.setattr(L, "_append_rows_with_retry", lambda sheet, rows: None)
    ok, batch = L.save_rebuilt_balances("2026-07-20", [
        {"name": "W", "company": "C", "address": "TAAA", "balance": Decimal("1")}])
    assert ok is False and batch is None
