from bot.services.command_args import resolve_fuzzy, normalize_name, squash_name

NAMES = ["DPP COY TRC", "KZDW DPP COY TRC 1", "KZP COY", "KZP COY 2", "KZP 96G1",
         "KZP BLG1", "KZDW DPP TH 2", "OKKZ 1", "OKKZ 2", "OKKZ 3", "S5 Cold TRC20"]

def test_normalizers():
    assert normalize_name("  KZDW  DPP-TH 2 ") == "kzdw dpp th 2"
    assert squash_name("KZDW DPP-TH 2") == "kzdwdppth2"

def test_exact_ignores_case_and_spacing():
    assert resolve_fuzzy("kzp 96g1", NAMES) == (["KZP 96G1"], "exact")
    assert resolve_fuzzy("KZP96G1", NAMES) == (["KZP 96G1"], "exact")
    assert resolve_fuzzy("KZDW DPP TH2", NAMES) == (["KZDW DPP TH 2"], "exact")

def test_starts_with_wins_over_noise():
    # the C1/C2 bug: KZP COY must NOT come back for "DPP COY"
    got, tier = resolve_fuzzy("DPP COY", NAMES)
    assert got == ["DPP COY TRC"] and tier == "starts with"
    got, tier = resolve_fuzzy("kzp 96", NAMES)
    assert got == ["KZP 96G1"] and tier == "starts with"

def test_literal_matches_are_not_capped():
    # all three OKKZ wallets, even though n=3 caps only guesses
    got, tier = resolve_fuzzy("OKKZ", NAMES)
    assert got == ["OKKZ 1", "OKKZ 2", "OKKZ 3"] and tier == "starts with"

def test_contains_when_not_a_prefix():
    got, tier = resolve_fuzzy("COY TRC 1", NAMES)
    assert got == ["KZDW DPP COY TRC 1"] and tier == "contains"

def test_all_words_any_order():
    got, tier = resolve_fuzzy("TRC DPP COY", NAMES)
    assert "DPP COY TRC" in got and tier == "all words"

def test_typo_short_query():
    got, tier = resolve_fuzzy("DPY CYO", NAMES)
    assert got[0] == "DPP COY TRC" and tier == "closest match"

def test_typo_multiple():
    got, tier = resolve_fuzzy("DYP CYO TCR", NAMES)
    assert "DPP COY TRC" in got and tier == "closest match"

def test_guesses_are_capped():
    got, _ = resolve_fuzzy("KZP 96G2", NAMES)
    assert len(got) <= 3

def test_nonsense_matches_nothing():
    for junk in ["ZZZ QQQ", "XYZ ABC", "12345", "hello world"]:
        assert resolve_fuzzy(junk, NAMES) == ([], "none")

def test_empty_input():
    assert resolve_fuzzy("", NAMES) == ([], "none")
    assert resolve_fuzzy("KZP", []) == ([], "none")
