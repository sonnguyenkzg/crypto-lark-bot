from bot.services.command_args import classify_tokens, resolve_fuzzy

COMPANIES = ["KZP", "KZO", "KZG", "S5"]
NAMES = ["KZP 96G1", "KZP WDB2", "KZO A 1", "S5 Tech ERC20"]

def test_classify_group_vs_wallet():
    groups, names, addresses = classify_tokens(["KZP", "KZP 96G1"], COMPANIES, NAMES)
    assert groups == ["KZP"]
    assert names == ["KZP 96G1"]
    assert addresses == []

def test_classify_case_insensitive_and_group_wins_on_tie():
    # a token that is also a company name is treated as a group
    groups, names, addresses = classify_tokens(["kzp"], COMPANIES, NAMES)
    assert groups == ["kzp"] and names == [] and addresses == []

def test_resolve_fuzzy_near_miss():
    # typo / prefix -> closest wallet name
    got, _ = resolve_fuzzy("KZP 96", NAMES)
    assert "KZP 96G1" in got

def test_resolve_fuzzy_total_miss():
    assert resolve_fuzzy("ZZZ QQQ", NAMES) == ([], "none")

def test_resolve_fuzzy_case_insensitive():
    # a near-miss typed in a DIFFERENT case than the stored name still resolves
    got, _ = resolve_fuzzy("kzp 96g2", NAMES)
    assert "KZP 96G1" in got
