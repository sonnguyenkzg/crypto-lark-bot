# tests/test_filter_group_near_miss.py
"""_filter_entries must expand a confident group typo and refuse an ambiguous one.

This is the integration of resolve_group_near_miss into /check's filtering: a token that
falls to the fuzzy tier now first tries a group near-miss.
"""
from bot.handlers.check_handler import CheckHandler


def _entries(names):
    return [{"name": n, "company": "CO", "address": "T" + n.replace(" ", ""),
             "chain": "TRC20", "status": "saved", "balance": 1} for n in names]


ROSTER = _entries([
    "OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",
    "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A",
    "KZO COY TRC A 1", "KZO TH OPS TRC 1", "KZO PH SETTLE TRC 1",
    "KZP 96G1", "KZP COY", "KZP TH BM 1",
    "KZG A 1", "KZG B 1",
    "KZDW DPP PH 1", "KZDW FIN OPS TRC 1", "KZDW DPP TH 2",
    "DPP COY TRC",
])


def test_okz_filter_returns_all_ten_okkz_not_three():
    h = CheckHandler()
    entries, fuzzy, not_found, group_hits, ambiguous = h._filter_entries(
        list(ROSTER), groups=[], names=["okz"])
    assert len(entries) == 10
    assert {e["name"] for e in entries} == {"OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",
                                            "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A"}
    assert "okz" in group_hits and group_hits["okz"][0] == "OKKZ"
    assert group_hits["okz"][1] == 10
    assert not ambiguous
    assert not not_found


def test_kz0_filter_is_ambiguous_and_counts_nothing():
    h = CheckHandler()
    entries, fuzzy, not_found, group_hits, ambiguous = h._filter_entries(
        list(ROSTER), groups=[], names=["kz0"])
    assert entries == []
    assert "kz0" in ambiguous
    assert ambiguous["kz0"] == ["KZG", "KZO", "KZP"]
    assert "kz0" not in not_found          # not "not found" -- it's ambiguous, a distinct case


def test_a_correct_group_prefix_is_untouched_by_the_near_miss_path():
    """`okkz` hits the literal starts-with tier and must NOT be flagged as a near-miss."""
    h = CheckHandler()
    entries, fuzzy, not_found, group_hits, ambiguous = h._filter_entries(
        list(ROSTER), groups=[], names=["okkz"])
    assert len(entries) == 10
    assert not group_hits            # literal match, no "closest match to" header
    assert not ambiguous


def test_a_wallet_name_typo_still_uses_single_wallet_fuzzy():
    """`dpy cyo` matches no group; it keeps the existing closest-match-to-a-wallet path."""
    h = CheckHandler()
    entries, fuzzy, not_found, group_hits, ambiguous = h._filter_entries(
        list(ROSTER), groups=[], names=["dpy cyo"])
    assert [e["name"] for e in entries] == ["DPP COY TRC"]
    assert "dpy cyo" in fuzzy
    assert not group_hits and not ambiguous


def test_nonsense_is_still_not_found():
    h = CheckHandler()
    entries, fuzzy, not_found, group_hits, ambiguous = h._filter_entries(
        list(ROSTER), groups=[], names=["zzz qqq"])
    assert entries == []
    assert "zzz qqq" in not_found
    assert not group_hits and not ambiguous
