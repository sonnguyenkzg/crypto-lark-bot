"""Regression coverage for CheckHandler._filter_entries -- the company/name/fuzzy
filter used by `/check [date] [...]` (see bot/handlers/check_handler.py).

This replaces the coverage that lived in the now-deleted tests/test_historical_view.py
(test_group_filter, test_group_filter_multiple_or, test_name_filter_exact,
test_name_filter_fuzzy, test_not_found_name), which tested the retired
build_historical_view/_filter_roster pair. The filtering behaviour itself was ported
into _filter_entries when the handler moved to per-wallet resolution (Task 5), but had
no direct test of its own until now.

Entries here are shaped exactly like classify_wallets' output: name, company, address,
chain, status, balance. _filter_entries only reads "name" and "company", so status/
balance/chain are filled with simple placeholders.
"""
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

ENTRIES = [
    {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
     "status": "saved", "balance": Decimal("10.00")},
    {"name": "KZO A 1", "company": "KZO", "address": "TBBB", "chain": "TRC20",
     "status": "saved", "balance": Decimal("20.00")},
    {"name": "Eth One", "company": "KZO", "address": "0xabc", "chain": "ERC20",
     "status": "saved", "balance": Decimal("5.00")},
    {"name": "S5 One", "company": "S5", "address": "TCCC", "chain": "TRC20",
     "status": "saved", "balance": Decimal("30.00")},
]


def test_group_filter_selects_only_that_company():
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, ["KZO"], [])
    assert {e["name"] for e in entries} == {"KZO A 1", "Eth One"}
    assert fuzzy == {}
    assert not_found == []


def test_group_filter_multiple_groups_is_union():
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, ["KZP", "S5"], [])
    assert {e["name"] for e in entries} == {"KZP 96G1", "S5 One"}
    # KZO wallets excluded -- OR across the requested groups only, not all companies
    assert "KZO A 1" not in {e["name"] for e in entries}


def test_name_filter_exact_selects_only_that_wallet():
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, [], ["KZP 96G1"])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert fuzzy == {}                    # exact match -- no guess to flag
    assert not_found == []


def test_name_filter_fuzzy_resolves_a_typo_and_is_recorded():
    """A typo'd name (not a prefix/substring/exact match) must still resolve via the
    closest-match tier, and -- unlike a literal match -- gets recorded in `fuzzy` so
    the card can tell the user it guessed."""
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, [], ["KZP 96G2"])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert fuzzy.get("KZP 96G2") == ["KZP 96G1"]
    assert not_found == []


def test_name_not_found_is_reported_not_silently_dropped_or_guessed():
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, [], ["ZZZ QQQ"])
    assert entries == []
    assert not_found == ["ZZZ QQQ"]
    assert fuzzy == {}


def test_group_and_name_together_is_an_intersection():
    """The name filter is resolved WITHIN the already group-filtered entries, so a
    name that exists but belongs to a company outside the group filter is excluded,
    not silently matched from the wrong company."""
    entries, fuzzy, not_found, _gh, _amb, _addr = H._filter_entries(ENTRIES, ["KZO"], ["Eth One"])
    assert {e["name"] for e in entries} == {"Eth One"}

    # KZP 96G1 is a real wallet name, but it's not in the KZO group being filtered to,
    # so it must be reported not_found rather than pulled in from another company.
    entries2, fuzzy2, not_found2, _gh2, _amb2, _addr2 = H._filter_entries(ENTRIES, ["KZO"], ["KZP 96G1"])
    assert entries2 == []
    assert not_found2 == ["KZP 96G1"]
