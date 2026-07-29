from bot.handlers.remove_handler import RemoveHandler

H = RemoveHandler()

def test_accepts_brackets():
    ok, val = H.parse_single_quoted_argument('[KZG TEST WALLET]')
    assert ok and val == "KZG TEST WALLET"

def test_accepts_bracketed_address():
    # the exact address from request.txt that used to fail
    ok, val = H.parse_single_quoted_argument('[0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]')
    assert ok and val == "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071"

def test_still_accepts_quotes():
    ok, val = H.parse_single_quoted_argument('"Cold wallet"')
    assert ok and val == "Cold wallet"

def test_missing_argument():
    ok, msg = H.parse_single_quoted_argument("")
    assert not ok and "wallet name or address" in msg.lower()

def test_too_many_arguments():
    ok, msg = H.parse_single_quoted_argument('[A] [B]')
    assert not ok and "found 2" in msg
