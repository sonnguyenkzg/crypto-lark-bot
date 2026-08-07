# tests/test_group_near_miss.py
"""A near-miss group typo must resolve to the WHOLE group (matching what the correct
spelling gives), never a silent subset, and never over-count by merging one group into
another.

`/check [okz]` used to return 3 of the OKKZ wallets: `okz` misses every literal tier and
lands in the closest-match tier, which caps guesses at 3.

`resolve_group_near_miss` runs only after the literal tiers miss. It matches the typo
against the GROUP CODES (each wallet's group_code = its first token, folded to a family
parent via the explicit GROUP_FAMILY map). A clear winner expands to that whole group; a
tie across groups refuses. The explicit map — not a string rule — is what lets `OKKZ`
mean all 10 (incl the OKKZ1A..5A variant batch) while `S5` never captures the distinct
`S5A` (codex refuted both a raw-prefix and a digit-suffix heuristic).
"""
import pytest

from bot.services.command_args import resolve_group_near_miss, group_code, GROUP_FAMILY

# Faithful fixture: same group structure as the real roster.
ROSTER = [
    "OKKZ 1", "OKKZ 2", "OKKZ 3", "OKKZ 4", "OKKZ 5",
    "OKKZ1A", "OKKZ2A", "OKKZ3A", "OKKZ4A", "OKKZ5A",   # variant batch -> folds into OKKZ
    "KZO COY TRC A 1", "KZO TH OPS TRC 1", "KZO PH SETTLE TRC 1",
    "KZP 96G1", "KZP COY", "KZP TH BM 1",
    "KZG A 1", "KZG B 1",
    "S5 KZWL TRC20", "S5 Tech TRC20",                   # group S5
    "S5A",                                              # distinct group S5A
    "KZDW DPP PH 1", "KZDW FIN OPS TRC 1", "KZDW DPP TH 2", "KZDW DPP PKR 1",
    "DPP COY TRC",
]


def test_group_code_folds_variants_into_the_family_parent():
    assert group_code("OKKZ 3") == "OKKZ"
    assert group_code("OKKZ3A") == "OKKZ"     # variant folded
    assert group_code("S5 KZWL TRC20") == "S5"
    assert group_code("S5A") == "S5A"          # distinct, NOT folded into S5
    assert all(v == "OKKZ" for v in GROUP_FAMILY.values())


def test_okz_confidently_expands_to_all_ten_okkz():
    verdict, anchor, wallets = resolve_group_near_miss("okz", ROSTER)
    assert verdict == "confident"
    assert anchor == "OKKZ"
    assert len(wallets) == 10
    assert "OKKZ 1" in wallets and "OKKZ1A" in wallets


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
        assert set(wallets) == {"S5 KZWL TRC20", "S5 Tech TRC20"}


def test_a_group_code_can_never_swallow_a_digit_suffixed_distinct_group():
    """codex-found: a `<parent><digit>...` group (e.g. S55A) must not merge into S5."""
    injected = ROSTER + ["S55A ALPHA", "S55A BETA"]
    verdict, anchor, wallets = resolve_group_near_miss("s5 ", injected)
    if verdict == "confident" and anchor == "S5":
        assert not any(w.startswith("S55A") for w in wallets)
        assert len({group_code(w) for w in wallets}) == 1


def test_kzdww_confidently_resolves_to_kzdw():
    verdict, anchor, wallets = resolve_group_near_miss("kzdww", ROSTER)
    assert verdict == "confident" and anchor == "KZDW"
    assert len(wallets) == 4 and all(group_code(w) == "KZDW" for w in wallets)


def test_a_short_exact_group_still_resolves_confidently():
    verdict, anchor, wallets = resolve_group_near_miss("dpp", ROSTER)
    assert verdict == "confident" and anchor == "DPP" and wallets == ["DPP COY TRC"]


def test_a_typo_of_an_okkz_variant_still_resolves_to_the_okkz_family():
    verdict, anchor, wallets = resolve_group_near_miss("okz1a", ROSTER)
    assert verdict == "confident" and anchor == "OKKZ" and len(wallets) == 10


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
    for token in ["okz", "kzdww", "dpp", "okz1a", "s5a"]:
        verdict, _, wallets = resolve_group_near_miss(token, ROSTER)
        if verdict == "confident":
            assert len({group_code(w) for w in wallets}) == 1
