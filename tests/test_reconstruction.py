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
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("60000.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut, deadline=None: [tx("TXXX", ME, "58003.76")])
    # balance_on_date = current(60000) - net_after(+58003.76) = 1996.24
    assert B.get_balance_at(ME, "TRC20", 1) == Decimal("1996.24")

def test_reconstruct_negative_result_is_refused(monkeypatch):
    """A USDT balance can never be negative, so a negative reconstruction is proof the
    transfer window was wrong. It must be reported as unavailable, never saved."""
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut, deadline=None: [tx("TXXX", ME, "58003.76")])
    # would be 500 - 58003.76 = -57503.76
    assert B.get_balance_at(ME, "TRC20", 1) is None

def test_reconstruct_zero_is_still_a_valid_balance(monkeypatch):
    """Exactly zero is legitimate (emptied wallet) and must NOT be refused."""
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("100.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut, deadline=None: [tx("TXXX", ME, "100.00")])
    assert B.get_balance_at(ME, "TRC20", 1) == Decimal("0")

def test_reconstruct_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after", lambda a, c, cut, deadline=None: None)
    assert B.get_balance_at(ME, "TRC20", 1) is None

def test_reconstruct_stops_when_deadline_already_passed(monkeypatch):
    """Past the caller's budget we stop instead of spending the shared request rate."""
    import time as _t
    called = []
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut, deadline=None: called.append(1) or [])
    assert B.get_balance_at(ME, "TRC20", 1, deadline=_t.monotonic() - 1) is None
    assert called == []                      # no transfer fetch was even attempted

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


class _Body:
    """Stand-in for a requests Response that carries a given JSON body at HTTP 200."""
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _mock_get(monkeypatch, payload):
    monkeypatch.setattr("bot.services.balance_service.requests.get",
                        lambda *a, **k: _Body(payload))


def test_erc20_error_body_at_http_200_is_not_read_as_no_transfers(monkeypatch):
    """Etherscan sends rate-limit / bad-key errors as HTTP 200 with status "0".
    Reading that as "no transfers" makes the rebuilt figure equal TODAY's balance,
    which then gets written to the sheet as the past date's. Must be None."""
    monkeypatch.setenv("ETHEREUM_API_KEY", "dummy")
    _mock_get(monkeypatch, {"status": "0", "message": "NOTOK",
                            "result": "Max rate limit reached"})
    assert BalanceService()._fetch_transfers_after("0xabc123", "ERC20", 0) is None


def test_erc20_genuinely_empty_window_is_an_empty_list(monkeypatch):
    """The real "nothing happened here" reply must still succeed as [] -- otherwise
    every quiet wallet would be reported unavailable."""
    monkeypatch.setenv("ETHEREUM_API_KEY", "dummy")
    _mock_get(monkeypatch, {"status": "0", "message": "No transactions found",
                            "result": []})
    assert BalanceService()._fetch_transfers_after("0xabc123", "ERC20", 0) == []


def test_trc20_unexpected_body_at_http_200_is_not_read_as_no_transfers(monkeypatch):
    """Tronscan error bodies carry no token_transfers key; treating that as an empty
    page would silently return today's balance for a past date. Must be None."""
    _mock_get(monkeypatch, {"code": 401, "message": "forbidden: invalid API key"})
    assert BalanceService()._fetch_transfers_after("TAAA", "TRC20", 0) is None


def test_trc20_genuinely_empty_window_is_an_empty_list(monkeypatch):
    _mock_get(monkeypatch, {"token_transfers": []})
    assert BalanceService()._fetch_transfers_after("TAAA", "TRC20", 0) == []
