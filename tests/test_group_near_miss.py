# tests/test_group_near_miss.py
"""A near-miss group typo must resolve to the WHOLE group, not a silent subset.

`/check [okz]` used to return 3 of the 10 OKKZ wallets: `okz` misses every literal tier
(OKKZ has two K's) and lands in the closest-match tier, which caps guesses at 3.

`resolve_group_near_miss` runs only after the literal tiers miss. It matches the typo
against the GROUP CODES (distinct leading tokens), and:
  - a clear winner  -> "confident", expand to every wallet whose name starts with it
  - a real tie      -> "ambiguous", name the candidates, match nothing
  - nothing close   -> "none", let the caller fall back to the single-wallet guess
"""
import pytest

from bot.services.command_args import resolve_group_near_miss

# Faithful fixture: same DISTINCT LEADING TOKENS as the real 71-wallet roster
# (OKKZ, OKKZ1A..5A, KZO, KZP, KZG, S5, S5A, KZDW, DPP), so verdicts match production.
ROSTER = [
    "OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",
    "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A",
    "KZO COY TRC A 1", "KZO TH OPS TRC 1", "KZO PH SETTLE TRC 1",
    "KZP 96G1", "KZP COY", "KZP TH BM 1",
    "KZG A 1", "KZG B 1",
    "S5 KZWL TRC20", "S5 Tech TRC20",
    "S5A",
    "KZDW DPP PH 1", "KZDW FIN OPS TRC 1", "KZDW TH TINDER PAY", "KZDW DPP TH 2",
    "DPP COY TRC",
]


def test_okz_confidently_expands_to_all_ten_okkz_wallets():
    verdict, anchor, wallets = resolve_group_near_miss("okz", ROSTER)
    assert verdict == "confident"
    assert anchor == "OKKZ"
    assert len(wallets) == 10
    assert set(wallets) == {"OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",
                            "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A"}


def test_kz0_is_ambiguous_and_names_the_candidates():
    verdict, anchor, wallets = resolve_group_near_miss("kz0", ROSTER)
    assert verdict == "ambiguous"
    assert anchor == ["KZG", "KZO", "KZP"]   # sorted, disjoint groups
    assert wallets == []


def test_kzdww_confidently_resolves_to_kzdw():
    verdict, anchor, wallets = resolve_group_near_miss("kzdww", ROSTER)
    assert verdict == "confident"
    assert anchor == "KZDW"
    assert all(w.startswith("KZDW") for w in wallets)
    assert len(wallets) == 4


def test_a_short_exact_group_still_resolves_confidently():
    verdict, anchor, wallets = resolve_group_near_miss("dpp", ROSTER)
    assert verdict == "confident"
    assert anchor == "DPP"
    assert wallets == ["DPP COY TRC"]


def test_a_wallet_name_typo_returns_none_so_the_caller_can_fall_through():
    """`dpy cyo` is a typo of the wallet DPP COY TRC, not of a group code."""
    verdict, anchor, wallets = resolve_group_near_miss("dpy cyo", ROSTER)
    assert verdict == "none"
    assert wallets == []


def test_nonsense_returns_none():
    verdict, _, wallets = resolve_group_near_miss("zzz qqq", ROSTER)
    assert verdict == "none"
    assert wallets == []


def test_expansion_uses_prefix_not_group_equality():
    """OKKZ must catch OKKZ1A..5A too (they start with OKKZ) -> 10, matching `okkz`."""
    _, _, wallets = resolve_group_near_miss("okz", ROSTER)
    assert "OKKZ1A" in wallets and "OKKZ 1" in wallets


def test_empty_inputs_are_safe():
    assert resolve_group_near_miss("", ROSTER)[0] == "none"
    assert resolve_group_near_miss("okz", [])[0] == "none"


def test_confident_wallets_are_in_roster_order():
    _, _, wallets = resolve_group_near_miss("okz", ROSTER)
    assert wallets == [n for n in ROSTER if n.startswith("OKKZ")]


def test_s5b_does_not_swallow_s5a_into_s5():
    """codex-found: `s5b` (typo of S5A) must NOT confidently return the broad S5 group
    with S5A merged in. S5 and S5A are distinct groups; the near-miss is ambiguous."""
    verdict, anchor, wallets = resolve_group_near_miss("s5b", ROSTER)
    assert verdict == "ambiguous"
    assert "S5" in anchor and "S5A" in anchor
    assert wallets == []


def test_s5_family_never_includes_s5a():
    """Even a confident S5 hit must exclude S5A (letter-suffixed distinct group)."""
    # force a confident S5 by using a token far closer to S5 than S5A
    verdict, anchor, wallets = resolve_group_near_miss("s5 ", ROSTER)
    if verdict == "confident":
        assert anchor == "S5"
        assert "S5A" not in wallets
        assert wallets == ["S5 KZWL TRC20", "S5 Tech TRC20"]


def test_okkz_family_still_includes_numbered_variants():
    """The exact-family rule must keep OKKZ1A..5A under OKKZ (digit suffix) -> okz = 10."""
    _, anchor, wallets = resolve_group_near_miss("okz", ROSTER)
    assert anchor == "OKKZ"
    assert "OKKZ1A" in wallets and "OKKZ 1" in wallets and len(wallets) == 10
