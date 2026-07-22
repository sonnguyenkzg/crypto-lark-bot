from bot.handlers.add_handler import AddHandler

H = AddHandler()

def test_add_accepts_brackets():
    ok, res = H.parse_quoted_arguments('[KZP] [KZP WDB2] [TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t]')
    assert ok and res == ["KZP", "KZP WDB2", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"]

def test_add_still_accepts_quotes():
    ok, res = H.parse_quoted_arguments('"KZP" "KZP WDB2" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"')
    assert ok and res[0] == "KZP"

def test_add_wrong_count():
    ok, res = H.parse_quoted_arguments('[KZP] [KZP WDB2]')
    assert not ok
