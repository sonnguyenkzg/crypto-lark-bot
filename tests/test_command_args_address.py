"""Unit coverage for address-token detection in command_args.

`/check [date] [<wallet address>]` lets an Account Executive name a monitored wallet by
its on-chain address instead of its name. The first step is telling an *address token*
apart from a group/name token purely by content, so `classify_tokens` can route it. These
tests pin that detection (`looks_like_address`) and the three-way split it feeds.

Detection is deliberately consistent with detect_chain_from_address (the same validator
/add and /remove use): an ERC20 address starts with a literal lowercase `0x`; a TRC20
address starts with `T`. `looks_like_address` recognises the *intent* to give an address
(so a malformed one is flagged, not silently treated as a wallet name); the strict format
check that decides valid/invalid stays with detect_chain_from_address downstream.
"""
from bot.services.command_args import looks_like_address, classify_tokens

# Valid, well-formed addresses (detect_chain_from_address returns a chain for each).
ERC20 = "0xabc0000000000000000000000000000000000001"          # 42 chars, hex
ERC20_UPPER = "0xABC0000000000000000000000000000000000001"    # same address, upper hex
TRC20 = "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"                  # 35 chars, starts 'T'

COMPANIES = ["KZP", "KZO", "KZG", "S5"]
NAMES = ["KZP 96G1", "KZP WDB2", "KZO A 1", "S5 Tech ERC20"]


# --- looks_like_address ----------------------------------------------------------------

def test_erc20_address_is_recognised():
    assert looks_like_address(ERC20) is True
    assert looks_like_address(ERC20_UPPER) is True


def test_trc20_address_is_recognised():
    assert looks_like_address(TRC20) is True


def test_malformed_address_still_reads_as_an_address_attempt():
    # Short/garbled but clearly meant as an address -> recognised as address INTENT, so it
    # is flagged "invalid" downstream rather than misfiled as a wallet name.
    assert looks_like_address("0x123") is True                 # starts 0x, too short
    assert looks_like_address("0xZZZ0000000000000000000000000000000000001") is True  # not hex


def test_wallet_names_and_groups_are_not_addresses():
    # Names contain spaces and are short; group codes are short. None looks like an address.
    for tok in ["KZP 96G1", "KZO A 1", "S5 Tech ERC20", "KZP", "S5", "OKKZ5A"]:
        assert looks_like_address(tok) is False, tok


def test_short_t_token_is_a_name_not_an_address():
    # A short token that merely starts with 'T' (e.g. a code) must NOT be taken as a TRC20
    # address, or a real group/name could be swallowed. The length floor prevents that.
    assert looks_like_address("Tech") is False
    assert looks_like_address("T") is False


def test_blank_token_is_not_an_address():
    assert looks_like_address("") is False
    assert looks_like_address("   ") is False


# --- classify_tokens three-way split ---------------------------------------------------

def test_classify_splits_group_name_and_address():
    groups, names, addresses = classify_tokens(
        ["KZP", "KZP 96G1", ERC20, TRC20], COMPANIES, NAMES)
    assert groups == ["KZP"]
    assert names == ["KZP 96G1"]
    assert addresses == [ERC20, TRC20]


def test_classify_address_only():
    groups, names, addresses = classify_tokens([ERC20], COMPANIES, NAMES)
    assert groups == []
    assert names == []
    assert addresses == [ERC20]


def test_classify_preserves_order_within_addresses():
    groups, names, addresses = classify_tokens([TRC20, ERC20], COMPANIES, NAMES)
    assert addresses == [TRC20, ERC20]


def test_classify_group_still_wins_over_name():
    # unchanged behaviour: a token equal to a company is a group, case-insensitive
    groups, names, addresses = classify_tokens(["kzp"], COMPANIES, NAMES)
    assert groups == ["kzp"] and names == [] and addresses == []
