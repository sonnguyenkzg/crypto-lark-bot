"""End-to-end wiring for `/check [date] [<wallet address>]`.

Drives CheckHandler.handle with a fake context (no network, no Lark), mirroring
tests/test_check_historical_wiring.py. Confirms that an address token routes through the
historical path, that validation is surfaced (✅ / ❌ / ⚠️) and that the result reconciles
("checked N of M") -- never a silent partial.
"""
import asyncio
import json
from decimal import Decimal

from bot.handlers.check_handler import CheckHandler
from bot.services.chain_detector import canonical_address

KZP_ADDR = "0xabc0000000000000000000000000000000000001"   # ERC20
KZO_ADDR = "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"          # TRC20
UNMONITORED = "0x9999999999999999999999999999999999999999"  # valid ERC20, not in roster

ROSTER = {"companies": {
    "KZP": [{"name": "KZP 96G1", "address": KZP_ADDR, "chain": "ERC20",
             "created_at": "2026-01-01 00:00:00"}],
    "KZO": [{"name": "KZO A 1", "address": KZO_ADDR, "chain": "TRC20",
             "created_at": "2026-01-01 00:00:00"}],
}}


class _FakeTopic:
    def __init__(self):
        self.cards = []

    async def send_command_response(self, card, msg_type=None):
        self.cards.append(card)


class _FakeCtx:
    def __init__(self, args):
        self.args = args
        self.sender_id = "ou_test"
        self.topic_manager = _FakeTopic()


def _bundle(snapshot):
    return {"ok": True, "snapshot": snapshot, "nearest_date": None, "nearest_snapshot": {}}


def _snapshot():
    """Both wallets already saved for the date, so no rebuild / network is needed."""
    return {
        canonical_address(KZP_ADDR): {
            "wallet_name": "KZP 96G1", "company": "KZP", "address": KZP_ADDR,
            "balance": Decimal("10.00"), "batch_id": "b", "time": "00:01:12"},
        canonical_address(KZO_ADDR): {
            "wallet_name": "KZO A 1", "company": "KZO", "address": KZO_ADDR,
            "balance": Decimal("20.00"), "batch_id": "b", "time": "00:01:12"},
    }


def _handler():
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_history_bundle = lambda d: _bundle(_snapshot())
    return h


def _run(h, args):
    import bot.handlers.check_handler as ch
    ch._CHECK_EXECUTION_LOCK = False
    ctx = _FakeCtx(args)
    asyncio.run(h.handle(ctx))
    return ctx.topic_manager.cards


def _all(cards):
    return " ".join(json.dumps(c) for c in cards)


def test_address_selects_only_that_wallet():
    cards = _run(_handler(), ["[2026-07-15]", f"[{KZP_ADDR}]"])
    result = json.dumps(cards[-1])
    assert "KZP 96G1" in result
    assert "10.00" in result
    # the other monitored wallet must NOT be in the total
    assert "KZO A 1" not in result
    assert "20.00" not in result


def test_two_addresses_union():
    cards = _run(_handler(), ["[2026-07-15]", f"[{KZP_ADDR}]", f"[{KZO_ADDR}]"])
    result = json.dumps(cards[-1])
    assert "KZP 96G1" in result and "KZO A 1" in result
    assert "30.00" in result                     # 10 + 20


def test_opening_modifier_with_address_is_accepted():
    # [o] must be stripped as a mode, not mistaken for a filter; the address still resolves.
    cards = _run(_handler(), ["[2026-07-15]", "[o]", f"[{KZP_ADDR}]"])
    result = json.dumps(cards[-1])
    assert "KZP 96G1" in result
    assert "Opening" in result


def test_malformed_address_flagged_but_good_one_still_checked():
    cards = _run(_handler(), ["[2026-07-15]", f"[{KZP_ADDR}]", "[0x123]"])
    blob = _all(cards)
    assert "KZP 96G1" in blob                     # the good one is checked
    assert "0x123" in blob                        # the bad one is echoed, not swallowed
    assert "not a valid" in blob.lower()          # and flagged as invalid


def test_unmonitored_address_flagged_but_good_one_still_checked():
    cards = _run(_handler(), ["[2026-07-15]", f"[{KZP_ADDR}]", f"[{UNMONITORED}]"])
    blob = _all(cards)
    assert "KZP 96G1" in blob
    assert "not monitored" in blob.lower() or "not in the monitored" in blob.lower()


def test_all_bad_addresses_run_no_lookup_and_explain():
    # Nothing resolves -> the bot explains and reconstructs nothing (no rebuild call).
    called = []
    h = _handler()
    h.balance_service.get_balance_at = lambda *a, **k: called.append(a) or Decimal("1.00")
    cards = _run(h, ["[2026-07-15]", "[0x123]", f"[{UNMONITORED}]"])
    blob = _all(cards).lower()
    assert called == []                           # no reconstruction attempted
    assert "not a valid" in blob
    assert ("not monitored" in blob or "not in the monitored" in blob)


def test_validation_is_shown_before_the_lookup():
    # The acknowledgement card (sent before the balance read) already carries the verdict,
    # so the AE sees what was understood before any waiting.
    cards = _run(_handler(), ["[2026-07-15]", f"[{KZP_ADDR}]", "[0x123]"])
    # find the "Checking Balances" acknowledgement card
    ack = next((c for c in cards if "Checking Balances" in json.dumps(c)), None)
    assert ack is not None
    ack_blob = json.dumps(ack)
    assert "0x123" in ack_blob                    # the bad address is called out up front
