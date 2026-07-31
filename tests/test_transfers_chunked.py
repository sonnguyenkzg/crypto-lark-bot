# tests/test_transfers_chunked.py
"""fetch_transfers_between: chunked/windowed transfer fetching for offline backfill.

Two production wallets (KZP TH BM 1, KZDW DPP TH 2) do enough monthly USDT volume that
a single 7-month query blows through Tronscan's hard 10,000-transfers-per-query cap.
`_fetch_transfers_after` correctly refuses rather than return a partial list -- this
method instead slices the window into small chunks (default: 1 day), each provably
complete on its own, and concatenates them.

All HTTP is mocked at `_get_with_retry` -- never touches the real network.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bot.services.balance_service import BalanceService

DAY_MS = 86400 * 1000
TRC20_URL = "https://apilist.tronscanapi.com/api/token_trc20/transfers"


def _trc20_resp(rows):
    r = MagicMock()
    r.json.return_value = {"token_transfers": rows}
    return r


def _trc20_row(ts_ms, quant="1000000", frm="TAAA", to="TBBB"):
    return {"from_address": frm, "to_address": to, "quant": quant,
            "finalResult": "SUCCESS", "contractRet": "SUCCESS", "block_ts": ts_ms}


def _erc20_resp(status, message, result):
    r = MagicMock()
    r.json.return_value = {"status": status, "message": message, "result": result}
    return r


def _erc20_row(ts_s, value="2000000", frm="0xaaa", to="0xbbb"):
    return {"from": frm, "to": to, "value": value, "timeStamp": str(ts_s)}


def _require_trc20(params):
    assert "start_timestamp" in params and "end_timestamp" in params
    return params["start_timestamp"], params["end_timestamp"], params["start"]


# ---------------------------------------------------------------------------
# 1. Window split into the expected number of chunks; results concatenated in full.
# ---------------------------------------------------------------------------

def test_window_splits_into_expected_chunk_count_and_concatenates():
    svc = BalanceService()
    start_ms, end_ms = 0, 3 * DAY_MS   # 3 days -> 3 one-day chunks
    calls = []

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        calls.append((s, e, offset))
        # one small (exhausted) row per chunk, timestamped inside that chunk's window
        return _trc20_resp([_trc20_row(s)])

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", start_ms, end_ms, chunk_days=1)

    assert out is not None
    assert len(out) == 3, "one transfer per chunk, three chunks, none lost or merged away"
    assert len(calls) == 3, "exactly one page fetched per chunk -- each chunk exhausted immediately"
    # the three chunk windows must tile the whole range with no gap/overlap
    starts_ends = sorted((s, e) for s, e, _ in calls)
    assert starts_ends == [(1, DAY_MS), (DAY_MS + 1, 2 * DAY_MS), (2 * DAY_MS + 1, 3 * DAY_MS)]


# ---------------------------------------------------------------------------
# 2. A transfer landing exactly on a chunk boundary is neither lost nor duplicated.
# ---------------------------------------------------------------------------

def test_transfer_exactly_on_chunk_boundary_counted_once():
    svc = BalanceService()
    boundary = DAY_MS   # exactly the boundary between chunk 1 and chunk 2

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        if offset != 0:
            return _trc20_resp([])
        if s == 1 and e == DAY_MS:
            # chunk 1 is (0, DAY_MS] -- inclusive of the boundary itself
            return _trc20_resp([_trc20_row(boundary)])
        if s == DAY_MS + 1:
            # chunk 2 is (DAY_MS, 2*DAY_MS] -- must NOT also see the boundary transfer
            return _trc20_resp([])
        raise AssertionError(f"unexpected window ({s}, {e}]")

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, 2 * DAY_MS, chunk_days=1)

    assert out is not None
    matching = [t for t in out if t["ts"] == boundary]
    assert len(matching) == 1, f"boundary transfer must appear exactly once, got {len(matching)}"


# ---------------------------------------------------------------------------
# 3. A saturated chunk (returns exactly the cap) triggers subdivision.
# ---------------------------------------------------------------------------

def test_saturated_chunk_is_subdivided_and_recovers_everything():
    svc = BalanceService()
    svc.TRANSFER_MAX_PAGES = 2   # scaled-down cap: 2 pages * 50 = 100 "transfers"
    calls = []

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        calls.append((s, e, offset))
        width = e - s   # the un-subdivided day has a distinctly larger width than its halves
        if width == DAY_MS - 1:
            # the whole day: always a FULL page -> never proves exhaustion -> saturates
            return _trc20_resp([_trc20_row(s + i) for i in range(50)])
        # a subdivided half: small, exhausted immediately
        if offset != 0:
            return _trc20_resp([])
        return _trc20_resp([_trc20_row(s), _trc20_row(s + 1)])

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=1)

    assert out is not None, "subdivision must recover a full (non-None) list, not give up"
    assert len(out) == 4, "two halves x two transfers each -- the saturated 100-row " \
                          "attempt is discarded, not double-counted"
    # 2 pages exhausting the cap on the whole day, then 1 page per half = 4 calls
    assert len(calls) == 4


def test_saturated_even_at_one_hour_resolution_returns_none():
    """If subdividing all the way down to an hour still saturates, give up -- a partial
    list would silently understate the balance, which is worse than admitting failure."""
    svc = BalanceService()
    svc.TRANSFER_MAX_PAGES = 1   # 1 page * 50 = cap of 50, trivial to saturate

    def fake(url, params=None, headers=None, deadline=None):
        # ALWAYS a full page, at every resolution -> can never prove exhaustion
        return _trc20_resp([_trc20_row(1)] * 50)

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=1)

    assert out is None


# ---------------------------------------------------------------------------
# 4. A chunk that fails -> the whole call returns None, never a partial list.
# ---------------------------------------------------------------------------

def test_one_failed_chunk_fails_the_whole_fetch():
    svc = BalanceService()

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        if s == 1:                       # chunk 1 succeeds
            return _trc20_resp([_trc20_row(s)])
        return None                      # chunk 2's request fails outright

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, 2 * DAY_MS, chunk_days=1)

    assert out is None, "chunk 1's successfully-fetched transfer must not leak out " \
                        "as a silently-partial result"


def test_malformed_row_fails_safe_instead_of_raising():
    """A non-numeric `quant` raises decimal.InvalidOperation deep inside the
    normaliser. _fetch_transfers_after survives this via its own outer try/except;
    fetch_transfers_between must fail exactly the same way -- return None, never let
    the exception escape uncaught."""
    svc = BalanceService()

    def fake(url, params=None, headers=None, deadline=None):
        row = _trc20_row(1, quant="not-a-number")
        return _trc20_resp([row])

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=1)

    assert out is None


def test_bad_response_body_fails_the_whole_fetch():
    """Same fail-safe as _fetch_transfers_after: a body without token_transfers must
    not be read as an empty page."""
    svc = BalanceService()

    def fake(url, params=None, headers=None, deadline=None):
        r = MagicMock()
        r.json.return_value = {"code": 401, "message": "forbidden"}
        return r

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=1)

    assert out is None


def test_null_token_transfers_fails_safe_not_treated_as_empty_page():
    """A present-but-null `token_transfers` (e.g. {"token_transfers": null}) must NOT
    be silently coerced into an empty/exhausted page -- that would let a malformed
    response for one chunk masquerade as "nothing happened here" while an earlier
    chunk's real transfers are reported as a successful (but partial) result."""
    svc = BalanceService()

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        if s == 1:                                   # chunk 1: one real transfer
            return _trc20_resp([_trc20_row(s)])
        r = MagicMock()
        r.json.return_value = {"token_transfers": None}   # chunk 2: malformed body
        return r

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, 2 * DAY_MS, chunk_days=1)

    assert out is None, "chunk 1's real transfer must not leak out as a partial result"


# ---------------------------------------------------------------------------
# 5. chunk_days larger than the window -> one chunk covers everything.
# ---------------------------------------------------------------------------

def test_chunk_days_larger_than_window_is_a_single_chunk():
    svc = BalanceService()
    calls = []

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        calls.append((s, e, offset))
        return _trc20_resp([_trc20_row(100), _trc20_row(200), _trc20_row(300)])

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, 50_000, chunk_days=1)

    assert out is not None
    assert len(out) == 3
    assert len(calls) == 1
    assert calls[0] == (1, 50_000, 0)


# ---------------------------------------------------------------------------
# 6. Normalisation identical to _fetch_transfers_after: ts in epoch ms, amount a
#    Decimal in USDT units. Checked for both chains.
# ---------------------------------------------------------------------------

def test_trc20_normalisation_matches_fetch_transfers_after():
    svc = BalanceService()
    row = _trc20_row(1785416487000, quant="5000000", frm="TAAA", to="TBBB")

    def fake(url, params=None, headers=None, deadline=None):
        s, e, offset = _require_trc20(params)
        return _trc20_resp([row] if offset == 0 else [])

    with patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=1)

    assert out is not None and len(out) == 1
    t = out[0]
    assert t["ts"] == 1785416487000
    assert isinstance(t["ts"], int)
    assert t["amount"] == Decimal("5")
    assert isinstance(t["amount"], Decimal)
    assert t["from"] == "TAAA" and t["to"] == "TBBB"
    assert t["success"] is True


def test_erc20_normalisation_matches_fetch_transfers_after():
    svc = BalanceService()
    # window (0, DAY_MS]; one transfer at ts_s inside it
    ts_s = 500

    def fake(url, params=None, headers=None, deadline=None):
        assert params.get("module") == "account" and params.get("action") == "tokentx"
        page = params["page"]
        if page == 1:
            return _erc20_resp("1", "OK", [_erc20_row(ts_s, value="7000000")])
        return _erc20_resp("0", "No transactions found", [])

    with patch.dict("os.environ", {"ETHEREUM_API_KEY": "k"}), \
         patch.object(svc, "_get_with_retry", side_effect=fake):
        out = svc.fetch_transfers_between("0xbbb", "ERC20", 0, DAY_MS, chunk_days=1)

    assert out is not None and len(out) == 1
    t = out[0]
    assert t["ts"] == ts_s * 1000, "Etherscan reports seconds -- must be converted to ms"
    assert isinstance(t["ts"], int)
    assert t["amount"] == Decimal("7")
    assert isinstance(t["amount"], Decimal)
    assert t["success"] is True


# ---------------------------------------------------------------------------
# Guardrails: invalid inputs are rejected without ever touching the network.
# ---------------------------------------------------------------------------

def test_invalid_chain_returns_none_without_network_call():
    svc = BalanceService()
    with patch.object(svc, "_get_with_retry", side_effect=AssertionError("must not be called")):
        assert svc.fetch_transfers_between("TBBB", "BTC", 0, DAY_MS) is None


def test_non_positive_chunk_days_returns_none_without_network_call():
    svc = BalanceService()
    with patch.object(svc, "_get_with_retry", side_effect=AssertionError("must not be called")):
        assert svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=0) is None
        assert svc.fetch_transfers_between("TBBB", "TRC20", 0, DAY_MS, chunk_days=-1) is None


def test_vanishingly_small_chunk_days_rejected_instead_of_hanging():
    """A tiny positive chunk_days (e.g. 1e-15) multiplied out in floating point can
    underflow to a chunk width smaller than float64 precision at epoch-ms magnitudes,
    so `cur + chunk_ms == cur` and the main loop would never advance -- an infinite
    loop re-fetching the same zero-width slice forever. Must be rejected up front,
    not hang. Uses a realistic large epoch-ms start (representative of a real 2026
    date) where the underflow actually bites."""
    svc = BalanceService()
    start_ms = 10**15
    with patch.object(svc, "_get_with_retry", side_effect=AssertionError("must not be called")):
        out = svc.fetch_transfers_between("TBBB", "TRC20", start_ms, start_ms + 1,
                                          chunk_days=1e-15)
    assert out is None


def test_end_before_start_returns_none_without_network_call():
    svc = BalanceService()
    with patch.object(svc, "_get_with_retry", side_effect=AssertionError("must not be called")):
        assert svc.fetch_transfers_between("TBBB", "TRC20", DAY_MS, 0) is None


def test_empty_window_returns_empty_list():
    """start_ms == end_ms: zero-width window, nothing to fetch, not a failure."""
    svc = BalanceService()
    with patch.object(svc, "_get_with_retry", side_effect=AssertionError("must not be called")):
        out = svc.fetch_transfers_between("TBBB", "TRC20", DAY_MS, DAY_MS)
    assert out == []
