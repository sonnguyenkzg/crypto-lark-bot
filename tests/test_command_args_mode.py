# tests/test_command_args_mode.py
"""Basis modifiers ([o]/[c]) are pulled out of the token list before filtering.

`open` and `close` are deliberately NOT modifiers: both resolve to real wallets today
via fuzzy matching (`open` -> KZO PEN SETTLE TRC 1 by "contains", `close` -> KZO SETTLE
OPS TRC 1 by closest match), so treating them as modifiers would shadow real filters.
"""
import pytest

from bot.services.command_args import extract_mode, parse_arguments


@pytest.mark.parametrize("tokens,expected", [
    ([],                      None),
    (["o"],                   "opening"),
    (["O"],                   "opening"),
    (["opening"],             "opening"),
    (["OPENING"],             "opening"),
    (["  o  "],               "opening"),
    (["c"],                   "closing"),
    (["C"],                   "closing"),
    (["closing"],             "closing"),
    (["CLOSING"],             "closing"),
])
def test_recognised_spellings(tokens, expected):
    mode, rest, conflict = extract_mode(tokens)
    assert mode == expected
    assert rest == []
    assert conflict is False


@pytest.mark.parametrize("token", ["open", "close", "OPEN", "Close", "opened", "closes"])
def test_open_and_close_are_not_modifiers(token):
    """These must fall through to the filter -- they match real wallets."""
    mode, rest, conflict = extract_mode([token])
    assert mode is None
    assert rest == [token]
    assert conflict is False


def test_position_independent():
    assert extract_mode(["KZP", "c"]) == ("closing", ["KZP"], False)
    assert extract_mode(["c", "KZP"]) == ("closing", ["KZP"], False)
    assert extract_mode(["KZDW", "o", "KZP TH BM 1"]) == (
        "opening", ["KZDW", "KZP TH BM 1"], False)


def test_repeating_the_same_modifier_is_not_a_conflict():
    assert extract_mode(["o", "o"]) == ("opening", [], False)
    assert extract_mode(["o", "opening"]) == ("opening", [], False)
    assert extract_mode(["c", "CLOSING", "c"]) == ("closing", [], False)


def test_opening_and_closing_together_is_a_conflict():
    mode, rest, conflict = extract_mode(["o", "c"])
    assert conflict is True
    assert mode is None


def test_conflict_still_returns_the_remaining_filters():
    """The caller shows an error, but rest must be intact for any diagnostics."""
    mode, rest, conflict = extract_mode(["KZP", "o", "c"])
    assert conflict is True
    assert rest == ["KZP"]


def test_filters_are_untouched_when_no_modifier_present():
    toks = ["KZDW", "KZP TH BM 1", "OKKZ"]
    assert extract_mode(toks) == (None, toks, False)


# --- bracket spacing: already works, locked in so it cannot regress ---

@pytest.mark.parametrize("raw", [
    "[2026-07-15] [DPP COY]",
    "[2026-07-15][DPP COY]",
    "[2026-07-15]  [DPP COY]",
    "  [2026-07-15]   [DPP COY]  ",
])
def test_bracket_spacing_is_irrelevant(raw):
    tokens, had_bare = parse_arguments(raw)
    assert tokens == ["2026-07-15", "DPP COY"]
    assert had_bare is False


def test_three_adjacent_brackets():
    tokens, had_bare = parse_arguments("[2026-07-15][c][KZDW]")
    assert tokens == ["2026-07-15", "c", "KZDW"]
    assert had_bare is False
