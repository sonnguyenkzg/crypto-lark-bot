"""Coverage for the address branch of CheckHandler._filter_entries.

`/check [date] [<address>]` resolves a wallet by its on-chain address instead of its name.
Design (docs/superpowers/specs/2026-08-08-check-by-address-design.md):

  * Monitored wallets only -- an address is a lookup key into the roster, not new on-chain
    scope. A valid address not in the roster is flagged, never reconstructed.
  * Validate first, then check the valid ones and flag the rest -- never a silent partial.
    Each address token lands in exactly one of matched / invalid / unmonitored, and those
    reconcile against the requested count.
  * An address is an EXACT identifier, so it is additive: it always resolves against the
    full roster and is included regardless of any group filter (unlike a fuzzy name, which
    still resolves within the group scope). Selectors de-duplicate by wallet identity.

_filter_entries now returns a 6-tuple; the 6th element is addr_report:
    {"requested": int, "matched": [{"address","name","chain"}], "invalid": [...],
     "unmonitored": [...]}
"""
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

# Real-format addresses so detect_chain_from_address accepts them.
KZP_ADDR = "0xabc0000000000000000000000000000000000001"   # ERC20
KZO_ADDR = "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"          # TRC20
S5_ADDR = "0xdef0000000000000000000000000000000000002"    # ERC20
UNMONITORED = "0x9999999999999999999999999999999999999999"  # valid ERC20, not in roster

ENTRIES = [
    {"name": "KZP 96G1", "company": "KZP", "address": KZP_ADDR, "chain": "ERC20",
     "status": "saved", "balance": Decimal("10.00")},
    {"name": "KZO A 1", "company": "KZO", "address": KZO_ADDR, "chain": "TRC20",
     "status": "saved", "balance": Decimal("20.00")},
    {"name": "S5 One", "company": "S5", "address": S5_ADDR, "chain": "ERC20",
     "status": "saved", "balance": Decimal("30.00")},
]


def _filter(entries, groups, names, addresses):
    return H._filter_entries(entries, groups, names, addresses)


def test_single_address_selects_only_that_wallet():
    entries, fuzzy, not_found, gh, amb, addr = _filter(ENTRIES, [], [], [KZP_ADDR])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert addr["requested"] == 1
    assert [m["name"] for m in addr["matched"]] == ["KZP 96G1"]
    assert addr["invalid"] == [] and addr["unmonitored"] == []
    assert fuzzy == {} and not_found == []


def test_multiple_addresses_are_a_union():
    entries, *_rest, addr = _filter(ENTRIES, [], [], [KZP_ADDR, S5_ADDR])
    assert {e["name"] for e in entries} == {"KZP 96G1", "S5 One"}
    assert len(addr["matched"]) == 2


def test_erc20_match_is_case_insensitive():
    # ERC20 hex is case-insensitive; the `0x` prefix stays lowercase (codebase convention,
    # enforced by detect_chain_from_address / canonical_address and by /add). Vary the hex
    # body only, as a real checksummed address would.
    mixed_case = "0x" + KZP_ADDR[2:].upper()
    entries, *_rest, addr = _filter(ENTRIES, [], [], [mixed_case])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert len(addr["matched"]) == 1 and not addr["invalid"] and not addr["unmonitored"]


def test_trc20_address_matches_exactly():
    entries, *_rest, addr = _filter(ENTRIES, [], [], [KZO_ADDR])
    assert {e["name"] for e in entries} == {"KZO A 1"}
    assert addr["matched"][0]["chain"] == "TRC20"


def test_malformed_address_is_flagged_invalid_and_not_counted():
    entries, *_rest, addr = _filter(ENTRIES, [], [], ["0x123"])
    assert entries == []
    assert addr["invalid"] == ["0x123"]
    assert addr["matched"] == [] and addr["unmonitored"] == []


def test_valid_but_unmonitored_address_is_flagged_not_reconstructed():
    entries, *_rest, addr = _filter(ENTRIES, [], [], [UNMONITORED])
    assert entries == []
    assert addr["unmonitored"] == [UNMONITORED]
    assert addr["matched"] == [] and addr["invalid"] == []


def test_good_and_bad_addresses_together_check_the_good_flag_the_bad():
    # The AE's core ask: never a silent partial. The one good address is checked; the
    # malformed and the unmonitored ones are flagged; the counts reconcile.
    entries, *_rest, addr = _filter(ENTRIES, [], [], [KZP_ADDR, "0x123", UNMONITORED])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert addr["requested"] == 3
    assert len(addr["matched"]) == 1
    assert addr["invalid"] == ["0x123"]
    assert addr["unmonitored"] == [UNMONITORED]
    # every requested address is accounted for exactly once
    assert len(addr["matched"]) + len(addr["invalid"]) + len(addr["unmonitored"]) == addr["requested"]


def test_address_and_that_wallets_name_dedupe_to_one():
    entries, *_rest, addr = _filter(ENTRIES, [], ["KZP 96G1"], [KZP_ADDR])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert len([e for e in entries]) == 1        # not double-counted


def test_address_is_additive_over_a_group_filter():
    # A group narrows the pool for names, but an address is an exact identifier and is
    # always included. [KZO] + KZP's address -> the KZO wallet AND the addressed KZP wallet.
    entries, *_rest, addr = _filter(ENTRIES, ["KZO"], [], [KZP_ADDR])
    assert {e["name"] for e in entries} == {"KZO A 1", "KZP 96G1"}


def test_address_in_group_scope_is_not_double_counted():
    entries, *_rest, addr = _filter(ENTRIES, ["KZP"], [], [KZP_ADDR])
    assert [e["name"] for e in entries] == ["KZP 96G1"]   # exactly one, not two


def test_repeated_address_dedupes_but_reports_both_requests():
    entries, *_rest, addr = _filter(ENTRIES, [], [], [KZP_ADDR, KZP_ADDR])
    assert [e["name"] for e in entries] == ["KZP 96G1"]   # one wallet
    assert addr["requested"] == 2 and len(addr["matched"]) == 2  # both requests matched


def test_no_addresses_leaves_report_empty_and_behaviour_unchanged():
    entries, fuzzy, not_found, gh, amb, addr = _filter(ENTRIES, ["KZP"], [], [])
    assert {e["name"] for e in entries} == {"KZP 96G1"}
    assert addr == {"requested": 0, "matched": [], "invalid": [], "unmonitored": []}
