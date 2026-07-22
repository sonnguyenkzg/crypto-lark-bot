from decimal import Decimal
from bot.services.balance_service import BalanceService

B = BalanceService()
ME = "TAAA"

def tx(frm, to, amt, success=True):
    return {"from": frm, "to": to, "amount": Decimal(amt), "success": success}

def test_net_credits_minus_debits():
    transfers = [
        tx("TXXX", ME, "100.00"),   # +100 in
        tx(ME, "TYYY", "30.00"),    # -30 out
    ]
    assert B._net_from_transfers(transfers, ME) == Decimal("70.00")

def test_net_skips_failed_transfers():
    transfers = [tx("TXXX", ME, "100.00", success=False), tx("TXXX", ME, "5.00")]
    assert B._net_from_transfers(transfers, ME) == Decimal("5.00")

def test_net_erc20_casing():
    me = "0xABC0000000000000000000000000000000000001"
    lower = me.lower()
    transfers = [tx("0xdead", lower, "10.00"), tx(me, "0xbeef", "4.00")]
    # credit matched despite case diff; debit matched despite case diff
    assert B._net_from_transfers(transfers, me) == Decimal("6.00")

def test_reconstruct_equals_current_minus_net(monkeypatch):
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut: [tx("TXXX", ME, "58003.76")])
    # balance_on_date = current(500) - net_after(+58003.76) = -57503.76
    assert B.get_balance_at(ME, "TRC20", 1) == Decimal("-57503.76")

def test_reconstruct_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after", lambda a, c, cut: None)
    assert B.get_balance_at(ME, "TRC20", 1) is None

def test_net_self_transfer_is_zero():
    # wallet sending USDT to itself: credit + debit must cancel to 0
    assert B._net_from_transfers([tx(ME, ME, "50.00")], ME) == Decimal("0")

def test_fetch_transfers_page_cap_returns_none(monkeypatch):
    b = BalanceService()
    b.TRANSFER_MAX_PAGES = 3
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            # always a FULL page (len==50, never <50) so the loop never self-terminates
            return {"token_transfers": [{"from_address": "X", "to_address": "TAAA",
                    "quant": "1000000", "finalResult": "SUCCESS", "contractRet": "SUCCESS"}] * 50}
    monkeypatch.setattr("bot.services.balance_service.requests.get", lambda *a, **k: _Resp())
    # incomplete window (more than the cap) -> None, and it must NOT hang
    assert b._fetch_transfers_after("TAAA", "TRC20", 0) is None
