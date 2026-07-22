from bot.services.command_args import parse_arguments, is_valid_iso_date, split_date

def test_parse_brackets_and_quotes():
    assert parse_arguments('[2026-07-15] [KZP 96G1]') == (["2026-07-15", "KZP 96G1"], False)
    assert parse_arguments('"KZP 96G1"') == (["KZP 96G1"], False)
    assert parse_arguments("[KZP]  [KZO]") == (["KZP", "KZO"], False)

def test_parse_flags_bare_words():
    # bare (undelimited) word must be flagged so the handler can hint "wrap in [ ]"
    assert parse_arguments("2026-07-15 KZP") == ([], True)
    assert parse_arguments("[2026-07-15] KZP") == (["2026-07-15"], True)

def test_parse_empty():
    assert parse_arguments("") == ([], False)
    assert parse_arguments("   ") == ([], False)

def test_is_valid_iso_date():
    assert is_valid_iso_date("2026-07-15")
    assert not is_valid_iso_date("2026-13-40")   # impossible calendar date
    assert not is_valid_iso_date("15/07/2026")
    assert not is_valid_iso_date("2026-7-5")

def test_split_date_first_iso_token_wins():
    assert split_date(["2026-07-15", "KZP", "KZP 96G1"]) == ("2026-07-15", ["KZP", "KZP 96G1"])
    assert split_date(["KZP 96G1"]) == (None, ["KZP 96G1"])

def test_mixed_delimiters_flagged_not_corrupted():
    # a token wrapped in BOTH styles must not silently corrupt; the leftover
    # delimiter must raise the bare-word flag so the handler can hint the user
    assert parse_arguments('["KZP"]') == (["KZP"], True)
    assert parse_arguments('"[KZP]"') == (["KZP"], True)
