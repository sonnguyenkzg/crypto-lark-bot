# tests/test_vault_calendar.py
"""The vault stores one figure per date: the balance at 00:00 GMT+7 that morning.

So the OPENING of D is the row dated D, and the CLOSING of D -- the balance at the end
of D -- is the same instant as 00:00 GMT+7 on D+1, which is the row dated D+1.
"""
import pytest

from bot.services.vault_calendar import target_date_for


@pytest.mark.parametrize("date_str", ["2026-07-15", "2025-09-22", "2026-02-28"])
def test_opening_is_the_same_date(date_str):
    assert target_date_for(date_str, "opening") == date_str


@pytest.mark.parametrize("date_str,expected", [
    ("2026-07-15", "2026-07-16"),
    ("2026-07-30", "2026-07-31"),
    ("2026-07-31", "2026-08-01"),   # month boundary
    ("2026-12-31", "2027-01-01"),   # year boundary
    ("2028-02-28", "2028-02-29"),   # leap year
    ("2026-02-28", "2026-03-01"),   # non-leap year
])
def test_closing_is_the_next_date(date_str, expected):
    assert target_date_for(date_str, "closing") == expected


def test_closing_of_D_equals_opening_of_D_plus_one():
    """The property the whole feature rests on."""
    assert target_date_for("2026-07-15", "closing") == target_date_for("2026-07-16", "opening")


def test_unknown_mode_is_rejected_loudly():
    """A typo must not silently fall through to one of the two real answers."""
    with pytest.raises(ValueError):
        target_date_for("2026-07-15", "sideways")


from bot.services.vault_calendar import build_first_seen


def _row(date, address):
    """A DAILY_REPORT row: batch, date, time, wallet, company, address, balance, type."""
    return ["20260101000100", date, "00:00:00", "W", "CO", address, "1.00", "scheduled"]


def test_uses_created_at_when_there_are_no_rows():
    roster = [{"address": "TAAA", "created_at": "2026-03-01T09:00:00"}]
    assert build_first_seen(roster, []) == {"TAAA": "2026-03-01"}


def test_uses_the_earliest_row_when_created_at_is_missing():
    """27 of 71 real wallets have no created_at; every one has vault rows."""
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [_row("2025-10-11", "TAAA"), _row("2025-09-22", "TAAA"), _row("2026-01-05", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2025-09-22"}


def test_takes_the_minimum_when_created_at_is_later_than_real_data():
    """Real case: KZDW DPP TH 2 records created_at 2026-01-15 but has a row from 2025-12-17."""
    roster = [{"address": "TAAA", "created_at": "2026-01-15"}]
    rows = [_row("2025-12-17", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2025-12-17"}


def test_takes_the_minimum_when_created_at_is_earlier():
    """Normal case: created one evening, first snapshot the next morning."""
    roster = [{"address": "TAAA", "created_at": "2026-03-31"}]
    rows = [_row("2026-04-01", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-03-31"}


def test_none_when_neither_signal_exists():
    assert build_first_seen([{"address": "TAAA"}], []) == {"TAAA": None}


def test_erc20_addresses_match_case_insensitively():
    """0x addresses are hex, so case must not create two separate wallets."""
    roster = [{"address": "0xAbCdEf", "created_at": None}]
    rows = [_row("2026-02-02", "0xabcdef")]
    assert build_first_seen(roster, rows) == {"0xabcdef": "2026-02-02"}


def test_rows_for_other_wallets_are_ignored():
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [_row("2025-01-01", "TBBB"), _row("2026-05-05", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-05-05"}


def test_unparseable_created_at_is_ignored_rather_than_trusted():
    roster = [{"address": "TAAA", "created_at": "not-a-date"}]
    rows = [_row("2026-06-06", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-06-06"}


def test_malformed_rows_do_not_crash():
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [[], ["only-one"], _row("", "TAAA"), _row("2026-07-07", ""), _row("2026-07-08", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-07-08"}


def test_the_guarantee_a_wallet_with_a_row_on_D_is_never_excluded_on_D():
    """first_seen includes the row's own date, so first_seen <= D always holds."""
    roster = [{"address": "TAAA", "created_at": "2099-01-01"}]   # absurdly late created_at
    rows = [_row("2026-07-15", "TAAA")]
    fs = build_first_seen(roster, rows)
    assert fs["TAAA"] <= "2026-07-15"
