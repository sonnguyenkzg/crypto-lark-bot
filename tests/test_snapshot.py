from decimal import Decimal
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

L = GoogleSheetsBalanceLogger()
# row = [batch, date, time, wallet, company, address, balance, type]
def row(batch, time, wallet, addr, bal, date="2026-07-15"):
    return [batch, date, time, wallet, "KZP", addr, bal, "scheduled"]

def test_parse_amount_strips_commas():
    assert L._parse_amount("351,432.18") == Decimal("351432.18")
    assert L._parse_amount("0.00") == Decimal("0.00")
    assert L._parse_amount("") is None          # empty -> excluded, not zeroed
    assert L._parse_amount("N/A") is None        # corrupted -> excluded

def test_union_completes_partial_retry():
    # 00:01 batch has A only; 00:07 retry adds B (B failed at 00:01)
    rows = [
        row("20260715000112", "00:01:12", "A", "TAAA", "10.00"),
        row("20260715000700", "00:07:00", "B", "TBBB", "20.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert set(snap.keys()) == {"TAAA", "TBBB"}
    assert snap["TAAA"]["balance"] == Decimal("10.00")

def test_intraday_rerun_does_not_overwrite_morning():
    # 00:01 A=10 ; 14:00 intraday A=999 -> earliest wins -> 10, not 999
    rows = [
        row("20260715000112", "00:01:12", "A", "TAAA", "10.00"),
        row("20260715140000", "14:00:00", "A", "TAAA", "999.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert snap["TAAA"]["balance"] == Decimal("10.00")

def test_erc20_casing_counts_once():
    rows = [
        row("20260715000112", "00:01:12", "E", "0xABC0000000000000000000000000000000000001", "5.00"),
        row("20260715000700", "00:07:00", "E", "0xabc0000000000000000000000000000000000001", "5.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert list(snap.keys()) == ["0xabc0000000000000000000000000000000000001"]

def test_same_name_different_address_both_kept():
    rows = [
        row("20260715000112", "00:01:12", "DUP", "TAAA", "1.00"),
        row("20260715000112", "00:01:12", "DUP", "TBBB", "2.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert set(snap.keys()) == {"TAAA", "TBBB"}

def test_ignores_other_dates():
    rows = [row("20260714000112", "00:01:12", "A", "TAAA", "10.00", date="2026-07-14")]
    assert L._build_snapshot_from_rows(rows, "2026-07-15") == {}

def test_reversed_batch_order_earliest_still_wins():
    # rows arriving newest-first must still yield the earliest (00:01) value
    rows = [
        row("20260715140000", "14:00:00", "A", "TAAA", "999.00"),
        row("20260715000112", "00:01:12", "A", "TAAA", "10.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert snap["TAAA"]["balance"] == Decimal("10.00")

def test_malformed_rows_excluded_not_crash():
    rows = [
        ["20260715000112", "2026-07-15", "00:01:12", "SHORT"],        # short row
        row("20260715000112", "00:01:12", "NOADDR", "", "5.00"),       # missing address
        row("20260715000112", "00:01:12", "BADBAL", "TCCC", "N/A"),    # non-numeric balance
        row("20260715000112", "00:01:12", "OK", "TAAA", "7.00"),       # good
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert set(snap.keys()) == {"TAAA"}
    assert snap["TAAA"]["balance"] == Decimal("7.00")


def test_write_retries_transient_failure_then_succeeds(monkeypatch):
    """A transient Sheets 503 must NOT lose the day's data (root cause of the 2026-07-20 gap)."""
    from googleapiclient.errors import HttpError
    from decimal import Decimal as D

    logger_obj = GoogleSheetsBalanceLogger()
    logger_obj.credentials_file = "x"; logger_obj.spreadsheet_id = "y"
    logger_obj.WRITE_RETRY_BACKOFF = 0.01          # keep the test fast
    monkeypatch.setattr(logger_obj, "_initialize_service", lambda: True)
    monkeypatch.setattr(logger_obj, "_ensure_headers", lambda name: None)

    class _Resp:  # minimal googleapiclient error shape (real ones carry .reason too)
        status = 503
        reason = "Service Unavailable"
    calls = {"n": 0}

    class _Append:
        def execute(self):
            calls["n"] += 1
            if calls["n"] <= 2:                    # fail twice, then succeed
                raise HttpError(_Resp(), b"service unavailable")
            return {"updates": {"updatedCells": 8}}

    class _Values:
        def append(self, **kw): return _Append()

    monkeypatch.setattr(logger_obj, "sheet", type("S", (), {"values": lambda self: _Values()})())

    ok, batch = logger_obj.log_balance_check(
        {"W": D("1.00")}, {"W": {"company": "C", "address": "TAAA"}}, check_type="scheduled")
    assert ok is True and batch          # data landed instead of being lost
    assert calls["n"] == 3               # proves it retried rather than giving up


# --- read-failure vs genuinely-empty (the /check [2026-07-15] duplicate-write bug) ---
#
# Root cause: _read_daily_report_rows used to return [] on BOTH a transient read
# failure AND a genuinely empty sheet, so callers couldn't tell "I don't know what's
# saved" from "nothing is saved" -- the latter triggered a full rebuild-and-save of
# every wallet in scope, duplicating rows that were already there. These tests pin
# the fixed contract: None means "failed to read", a list (maybe empty) means success.

def _logger_with_fake_sheet(monkeypatch, get_execute):
    """A GoogleSheetsBalanceLogger configured + wired to a fake `sheet.values().get()`."""
    obj = GoogleSheetsBalanceLogger()
    obj.credentials_file = "x"
    obj.spreadsheet_id = "y"
    monkeypatch.setattr(obj, "_initialize_service", lambda: True)

    class _Get:
        def execute(self):
            return get_execute()

    class _Values:
        def get(self, **kw):
            return _Get()

    monkeypatch.setattr(obj, "sheet", type("S", (), {"values": lambda self: _Values()})())
    return obj


def test_read_daily_report_rows_returns_none_when_sheets_call_raises(monkeypatch):
    def boom():
        raise RuntimeError("transient network blip")
    obj = _logger_with_fake_sheet(monkeypatch, boom)
    assert obj._read_daily_report_rows() is None


def test_read_daily_report_rows_returns_empty_list_when_sheet_genuinely_empty(monkeypatch):
    obj = _logger_with_fake_sheet(monkeypatch, lambda: {"values": []})
    assert obj._read_daily_report_rows() == []


def test_read_daily_report_rows_returns_none_when_unconfigured():
    obj = GoogleSheetsBalanceLogger()
    obj.credentials_file = None
    obj.spreadsheet_id = None
    assert obj._read_daily_report_rows() is None


def test_get_snapshot_and_nearest_reports_ok_false_on_read_failure(monkeypatch):
    obj = GoogleSheetsBalanceLogger()
    monkeypatch.setattr(obj, "_read_daily_report_rows", lambda: None)
    snapshot, nearest_date, nearest_snapshot, ok = obj.get_snapshot_and_nearest("2026-07-15")
    assert ok is False
    assert snapshot == {}
    assert nearest_date is None
    assert nearest_snapshot == {}


def test_get_snapshot_and_nearest_reports_ok_true_on_success_with_exact_match(monkeypatch):
    rows = [row("20260715000112", "00:01:12", "A", "TAAA", "10.00")]
    obj = GoogleSheetsBalanceLogger()
    monkeypatch.setattr(obj, "_read_daily_report_rows", lambda: rows)
    snapshot, nearest_date, nearest_snapshot, ok = obj.get_snapshot_and_nearest("2026-07-15")
    assert ok is True
    assert snapshot["TAAA"]["balance"] == Decimal("10.00")


def test_get_snapshot_and_nearest_reports_ok_true_on_genuinely_empty_sheet(monkeypatch):
    obj = GoogleSheetsBalanceLogger()
    monkeypatch.setattr(obj, "_read_daily_report_rows", lambda: [])
    snapshot, nearest_date, nearest_snapshot, ok = obj.get_snapshot_and_nearest("2026-07-15")
    assert ok is True
    assert snapshot == {}
    assert nearest_date is None
    assert nearest_snapshot == {}
