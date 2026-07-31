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
