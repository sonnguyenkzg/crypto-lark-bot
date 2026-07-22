from bot.services.chain_detector import canonical_address

def test_erc20_lowercased():
    assert canonical_address("0xAbC17F958d2Ee523A2206206994597C13D831EC7") \
        == "0xabc17f958d2ee523a2206206994597c13d831ec7"

def test_trc20_unchanged_case_sensitive():
    a = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    assert canonical_address(a) == a            # base58 is case-sensitive
    assert canonical_address(a.lower()) != a    # lowercasing would corrupt it

def test_strip_and_empty():
    assert canonical_address("  0xABC...  ".replace("...", "1"*38)) \
        == "0xabc" + "1"*38
    assert canonical_address("") == ""
    assert canonical_address(None) == ""
