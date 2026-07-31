# tests/test_transfer_timestamps.py
"""Normalised transfers must carry their timestamp in epoch MILLISECONDS.

The backfill buckets transfers by date, so a unit mix-up (Etherscan reports seconds,
Tronscan milliseconds) would silently shift every derived balance by decades.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bot.services.balance_service import BalanceService


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


def test_tron_transfer_carries_block_ts_unchanged():
    """Tronscan's block_ts is already milliseconds -- pass it straight through."""
    svc = BalanceService()
    payload = {"token_transfers": [{
        "from_address": "TAAA", "to_address": "TBBB", "quant": "5000000",
        "finalResult": "SUCCESS", "contractRet": "SUCCESS", "block_ts": 1785416487000,
    }]}
    with patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("TBBB", "TRC20", 1780000000000)
    assert out is not None and len(out) == 1
    assert out[0]["ts"] == 1785416487000
    assert isinstance(out[0]["ts"], int)
    assert out[0]["amount"] == Decimal("5")


def test_eth_transfer_converts_seconds_to_milliseconds():
    """Etherscan reports SECONDS. Storing them unconverted would date every
    transfer to 1970 and make every derived balance wrong."""
    svc = BalanceService()
    payload = {"status": "1", "message": "OK", "result": [{
        "from": "0xaaa", "to": "0xbbb", "value": "5000000", "timeStamp": "1785416487",
    }]}
    with patch.dict("os.environ", {"ETHEREUM_API_KEY": "k"}), \
         patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("0xbbb", "ERC20", 1780000000000)
    assert out is not None and len(out) == 1
    assert out[0]["ts"] == 1785416487000, "seconds must be multiplied by 1000"


def test_existing_keys_are_unchanged():
    """Additive only -- current consumers must not notice."""
    svc = BalanceService()
    payload = {"token_transfers": [{
        "from_address": "TAAA", "to_address": "TBBB", "quant": "1000000",
        "finalResult": "SUCCESS", "contractRet": "SUCCESS", "block_ts": 1785416487000,
    }]}
    with patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("TBBB", "TRC20", 1780000000000)
    assert set(out[0]) >= {"from", "to", "amount", "success", "ts"}
    assert out[0]["from"] == "TAAA" and out[0]["to"] == "TBBB"
    assert out[0]["success"] is True


def test_tron_transfer_missing_block_ts_fails_safe():
    """A row with no block_ts key at all must not silently default to 1970 --
    that would make the transfer permanently invisible to every future date
    boundary, understating every balance derived from it. Fail the whole fetch
    instead, same as any other malformed Tronscan response."""
    svc = BalanceService()
    payload = {"token_transfers": [{
        "from_address": "TAAA", "to_address": "TBBB", "quant": "5000000",
        "finalResult": "SUCCESS", "contractRet": "SUCCESS",
        # no "block_ts" key
    }]}
    with patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("TBBB", "TRC20", 1780000000000)
    assert out is None


def test_tron_transfer_null_block_ts_fails_safe():
    """A row with block_ts explicitly null must also fail safe, not default to 1970."""
    svc = BalanceService()
    payload = {"token_transfers": [{
        "from_address": "TAAA", "to_address": "TBBB", "quant": "5000000",
        "finalResult": "SUCCESS", "contractRet": "SUCCESS", "block_ts": None,
    }]}
    with patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("TBBB", "TRC20", 1780000000000)
    assert out is None


def test_tron_transfer_boolean_block_ts_fails_safe():
    """bool is a subclass of int in Python, so a stray JSON `false`/`true` in block_ts
    would otherwise silently pass int() as 0/1 (1970-era) instead of being rejected."""
    svc = BalanceService()
    payload = {"token_transfers": [{
        "from_address": "TAAA", "to_address": "TBBB", "quant": "5000000",
        "finalResult": "SUCCESS", "contractRet": "SUCCESS", "block_ts": False,
    }]}
    with patch.object(svc, "_get_with_retry", return_value=_resp(payload)):
        out = svc._fetch_transfers_after("TBBB", "TRC20", 1780000000000)
    assert out is None
