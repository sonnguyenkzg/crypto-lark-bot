from bot.services.command_args import classify_tokens, resolve_fuzzy

COMPANIES = ["KZP", "KZO", "KZG", "S5"]
NAMES = ["KZP 96G1", "KZP WDB2", "KZO A 1", "S5 Tech ERC20"]

def test_classify_group_vs_wallet():
    groups, names = classify_tokens(["KZP", "KZP 96G1"], COMPANIES, NAMES)
    assert groups == ["KZP"]
    assert names == ["KZP 96G1"]

def test_classify_case_insensitive_and_group_wins_on_tie():
    # a token that is also a company name is treated as a group
    groups, names = classify_tokens(["kzp"], COMPANIES, NAMES)
    assert groups == ["kzp"] and names == []

def test_resolve_fuzzy_near_miss():
    # typo / prefix -> closest wallet name
    assert "KZP 96G1" in resolve_fuzzy("KZP 96", NAMES)

def test_resolve_fuzzy_total_miss():
    assert resolve_fuzzy("ZZZ QQQ", NAMES) == []
