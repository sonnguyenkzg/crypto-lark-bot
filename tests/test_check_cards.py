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
    assert "added on or after this date" in b

def test_summary_opens_with_the_monitoring_total():
    # A `removed_but_saved` status/note can no longer occur -- scope is wallets.json only,
    # so there is nothing left to "mark" as removed. Lock the new headline instead: the
    # summary always opens with how many wallets are under monitoring. Use a fresh entries
    # list (no `removed_but_saved` row) so roster_total coherently equals len(entries), the
    # way the real caller (_handle_historical) always calls it.
    entries = [
        {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
         "status": "saved", "balance": Decimal("19.41")},
        {"name": "Eth One", "company": "KZO", "address": "0xabc", "chain": "ERC20",
         "status": "rebuilt", "balance": Decimal("10.00")},
        {"name": "New Wallet", "company": "KZP", "address": "TNEW", "chain": "TRC20",
         "status": "not_yet_created", "balance": None},
    ]
    b = blob(H._create_historical_card(entries, "2026-07-15", {}, [], None,
                                       roster_total=len(entries)))
    # the date is NOT repeated here -- the card header already carries it
    assert "**Total wallets in monitoring: 3**" in b
    assert "2026-07-15" in b            # present in the header/subtitle, not the summary line

def test_saved_batch_shown_only_when_something_saved():
    assert "B1" in blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], "B1"))
    assert "saved to Google Sheets" not in blob(
        H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))

def test_failed_wallet_reported_not_dropped():
    entries = ENTRIES + [{"name": "Busy", "company": "KZP", "address": "TB", "chain": "TRC20",
                          "status": "failed", "balance": None}]
    b = blob(H._create_historical_card(entries, "2026-07-15", {}, [], None))
    assert "Busy" in b and "could not be calculated" in b

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
    # Filtered: a company was named, so the headline reads "N of ROSTER monitored".
    b = blob(H._create_historical_checking_card("2026-07-20", ["DPP"], [], 1, roster_total=71))
    assert "2026-07-20" in b and "DPP" in b
    assert "Wallets in scope: 1 of 71 monitored" in b
    assert "Matched" not in b       # the old "Matched N wallets" line is gone

    # Unfiltered: no company/name filter, so the headline is just the monitoring total.
    b2 = blob(H._create_historical_checking_card("2026-07-20", [], [], 71, roster_total=71))
    assert "2026-07-20" in b2
    assert "Total wallets in monitoring: 71" in b2
    assert "Matched" not in b2
