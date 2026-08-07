# tests/test_group_near_miss.py
"""A near-miss group typo must resolve to a WHOLE group, not a silent subset — and must
never over-count by merging one group into another.

`/check [okz]` used to return 3 of the OKKZ wallets: `okz` misses every literal tier and
lands in the closest-match tier, which caps guesses at 3.

`resolve_group_near_miss` runs only after the literal tiers miss. It matches the typo
against the GROUP CODES (distinct FIRST tokens), and expands a confident hit to the EXACT
first-token group — no prefix, no digit heuristic, so a short code can never swallow a
longer one (codex found both a prefix and a digit-suffix over-count). A tie refuses.
"""
import pytest

from bot.services.command_args import resolve_group_near_miss

# Faithful fixture: same distinct FIRST TOKENS as the real roster.
ROSTER = [
    "OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",   # group OKKZ  (5)
    "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A",   # five distinct one-wallet groups
    "KZO COY TRC A 1", "KZO TH OPS TRC 1", "KZO PH SETTLE TRC 1",
    "KZP 96G1", "KZP COY", "KZP TH BM 1",
    "KZG A 1", "KZG B 1",
    "S5 KZWL TRC20", "S5 Tech TRC20",                   # group S5 (2 in fixture)
    "S5A",                                              # distinct group S5A (1)
    "KZDW DPP PH 1", "KZDW FIN OPS TRC 1", "KZDW DPP TH 2", "KZDW DPP PKR 1",
    "DPP COY TRC",
]


def test_okz_confidently_resolves_to_the_okkz_group():
    """okz -> the OKKZ group (OKKZ 1..5). The 1A..5A variants are separate groups."""
    verdict, anchor, wallets = resolve_group_near_miss("okz", ROSTER)
    assert verdict == "confident"
    assert anchor == "OKKZ"
    assert wallets == ["OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5"]


def test_okkz_variant_is_its_own_group_not_folded_into_okkz():
    _, _, okkz = resolve_group_near_miss("okz", ROSTER)
    assert "OKKZ1A" not in okkz
    verdict, anchor, wallets = resolve_group_near_miss("okz1a", ROSTER)
    assert verdict == "confident" and anchor == "OKKZ1A" and wallets == ["OKKZ1A"]


def test_kz0_is_ambiguous_and_names_the_candidates():
    verdict, anchor, wallets = resolve_group_near_miss("kz0", ROSTER)
    assert verdict == "ambiguous"
    assert anchor == ["KZG", "KZO", "KZP"]
    assert wallets == []


def test_s5b_is_ambiguous_between_s5_and_s5a_never_a_silent_broad_s5():
    """codex-found: `s5b` must NOT confidently return S5 with S5A merged in."""
    verdict, anchor, wallets = resolve_group_near_miss("s5b", ROSTER)
    assert verdict == "ambiguous"
    assert anchor == ["S5", "S5A"]
    assert wallets == []


def test_a_confident_s5_hit_never_includes_s5a():
    _, anchor, wallets = resolve_group_near_miss("s5 ", ROSTER)
    if anchor == "S5":
        assert "S5A" not in wallets
        assert wallets == ["S5 KZWL TRC20", "S5 Tech TRC20"]


def test_a_group_code_can_never_swallow_a_digit_suffixed_distinct_group():
    """codex-found: a `<parent><digit>...` group (e.g. S55A) must not merge into S5."""
    injected = ROSTER + ["S55A ALPHA", "S55A BETA"]
    verdict, anchor, wallets = resolve_group_near_miss("s5 ", injected)
    if verdict == "confident" and anchor == "S5":
        assert all(w.split()[0] == "S5" for w in wallets)   # no S55A, no S5A
        assert not any(w.startswith("S55A") for w in wallets)


def test_kzdww_confidently_resolves_to_kzdw():
    verdict, anchor, wallets = resolve_group_near_miss("kzdww", ROSTER)
    assert verdict == "confident" and anchor == "KZDW"
    assert all(w.split()[0] == "KZDW" for w in wallets) and len(wallets) == 4


def test_a_short_exact_group_still_resolves_confidently():
    verdict, anchor, wallets = resolve_group_near_miss("dpp", ROSTER)
    assert verdict == "confident" and anchor == "DPP" and wallets == ["DPP COY TRC"]


def test_a_wallet_name_typo_returns_none_so_the_caller_can_fall_through():
    verdict, _, wallets = resolve_group_near_miss("dpy cyo", ROSTER)
    assert verdict == "none" and wallets == []


def test_nonsense_returns_none():
    verdict, _, wallets = resolve_group_near_miss("zzz qqq", ROSTER)
    assert verdict == "none" and wallets == []


def test_empty_inputs_are_safe():
    assert resolve_group_near_miss("", ROSTER)[0] == "none"
    assert resolve_group_near_miss("okz", [])[0] == "none"


def test_every_confident_hit_is_a_single_group():
    """No confident expansion may ever mix first-token groups."""
    for token in ["okz", "kzdww", "dpp", "okz1a", "s5a"]:
        verdict, _, wallets = resolve_group_near_miss(token, ROSTER)
        if verdict == "confident":
            assert len({w.split()[0] for w in wallets}) == 1
