from decimal import Decimal
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

L = GoogleSheetsBalanceLogger()
# row = [batch, date, time, wallet, company, address, balance, type]
def row(batch, time, wallet, addr, bal, date="2026-07-15"):
    return [batch, date, time, wallet, "KZP", addr, bal, "scheduled"]

def test_parse_amount_strips_commas():
    assert L._parse_amount("351,432.18") == Decimal("351432.18")
    assert L._parse_amount("") == Decimal("0")

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
