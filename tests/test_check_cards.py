import json
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

def blob(c): return json.dumps(c)

ENTRIES = [
    {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
     "status": "saved", "balance": Decimal("19.41")},
    {"name": "Eth One", "company": "KZO", "address": "0xabc", "chain": "ERC20",
     "status": "rebuilt", "balance": Decimal("10.00")},
    {"name": "Cold wallet", "company": "S5", "address": "TOLD", "chain": "TRC20",
     "status": "removed_but_saved", "balance": Decimal("1250.00")},
    {"name": "New Wallet", "company": "KZP", "address": "TNEW", "chain": "TRC20",
     "status": "not_yet_created", "balance": None},
]

def test_summary_counts_only_wallets_with_a_figure():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], "B1"))
    assert "3 wallets counted" in b          # saved + rebuilt + removed_but_saved
    assert "1,279.41" in b                   # 19.41 + 10.00 + 1250.00

def test_added_later_is_listed_but_not_counted():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))
    assert "New Wallet" in b
    assert "added after this date" in b

def test_removed_wallet_is_marked():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))
    assert "no longer in your list" in b

def test_saved_batch_shown_only_when_something_saved():
    assert "B1" in blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], "B1"))
    assert "saved to Google Sheets" not in blob(
        H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))

def test_failed_wallet_reported_not_dropped():
    entries = ENTRIES + [{"name": "Busy", "company": "KZP", "address": "TB", "chain": "TRC20",
                          "status": "failed", "balance": None}]
    b = blob(H._create_historical_card(entries, "2026-07-15", {}, [], None))
    assert "Busy" in b and "could not be worked out" in b

def test_not_found_message_is_plain():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, ["ZZZ QQQ"], None))
    # json.dumps escapes the quotes around the wallet name -- match its actual output.
    assert 'Wallet \\"ZZZ QQQ\\" not found.' in b

def test_header_marks_the_total_partial_when_a_wallet_is_unavailable():
    entries = ENTRIES + [{"name": "Busy", "company": "KZP", "address": "TB", "chain": "TRC20",
                          "status": "failed", "balance": None}]
    card = H._create_historical_card(entries, "2026-07-15", {}, [], None)
    subtitle = card["header"]["subtitle"]["content"]
    assert "Partial total (1 unavailable)" in subtitle
    assert "1,279.41" in subtitle             # still shows what IS known
    assert card["header"]["template"] == "orange"

def test_header_total_is_unmarked_when_every_wallet_has_a_figure():
    card = H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None)
    subtitle = card["header"]["subtitle"]["content"]
    assert "Partial" not in subtitle
    assert subtitle == "2026-07-15 · Total: 1,279.41 USDT"
    assert card["header"]["template"] != "orange"

def test_ack_card_echoes_what_was_understood():
    b = blob(H._create_historical_checking_card("2026-07-20", ["DPP"], [], 1))
    assert "2026-07-20" in b and "DPP" in b and "Matched 1 wallet" in b
