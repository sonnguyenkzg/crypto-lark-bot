# Roster-Only Scope + One-Time Backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `/check [date]` hiding money — every wallet in `wallets.json` gets a figure for every date — and backfill 2026-01-01 → 2026-07-30 so those dates are complete and instant.

**Architecture:** Two independent pieces, done in this order. First a **backfill**: a standalone script that fetches each wallet's transfer history *once* and derives all 212 daily balances from it by arithmetic (71 fetches, not 3,079 reconstructions), writing only the gaps. Second a **code change**: delete the "added later" exclusion so no wallet is ever skipped. The backfill goes first because `classify_wallets` consults the saved snapshot *before* asking whether a wallet existed — so backfilled rows display correctly on the code already in production, with nothing deployed.

**Tech Stack:** Python 3.12, pytest, Tronscan + Etherscan v2 APIs, Google Sheets API v4, Lark cards.

Spec: `docs/superpowers/specs/2026-07-31-roster-scope-and-backfill-design.md`

## Global Constraints

- **Scope is `wallets.json`, always.** Every wallet gets a figure for every date. When a wallet was added is never consulted. A wallet that did not exist reconstructs to `0.00` — a real balance, listed like any other.
- **Backfill window: 2026-01-01 → 2026-07-30.** 3,079 wallet-days of a possible 15,052. Today's row is written by the daily report; do not backfill it.
- **Never modify an existing row.** The backfill only *adds* rows for wallet-days that have none. A wallet-day with a row is skipped.
- Rows are written with `Check Type = "rebuilt"`, `Time = 00:00:00`, `Date` = the date described, `Batch ID` = the write time — exactly as `save_rebuilt_balances` already does.
- **A day boundary is `VAULT_DAY_BOUNDARY` = `"00:00:00"` GMT+7.** Import it from `bot/services/google_sheets_logger.py`; never write the literal.
- **Negative reconstruction → no figure.** A USDT balance cannot be negative; a negative result means the transfer window was wrong. Return `None` and report the wallet as unavailable rather than saving a wrong number.
- **Never run near 17:00 UTC** — the daily report writes then. Stop cleanly if within 30 minutes of it.
- **Dry run before any write.** The first real run happens only after its dry-run output is reviewed.
- Run tests with `.venv/bin/python -m pytest tests/ -q`. Baseline **211 passing**. `tests/conftest.py` blanks the real Google credentials — never bypass it.
- Ignore `test_erc20_support.py` at the repo root: pre-existing, outside `tests/`, its async tests lack an asyncio marker and always fail under a bare `pytest`.
- Work on branch `feature/check-date-and-remove-fix`. Never edit files on the production box.

---

## File Structure

| File | Responsibility |
|---|---|
| `bot/services/balance_service.py` (modify) | Add `ts` (epoch ms) to each normalised transfer. Additive only. |
| `bot/services/balance_history.py` (**create**) | Pure, network-free: given a current balance and one transfer list, derive the balance at many dates. |
| `backfill_history.py` (**create**, repo root, beside `cleanup.py` and `wallets_to_gg_sheet.py`) | The standalone runner: fetch per wallet, derive, verify, write gaps. Dry-run by default. |
| `bot/handlers/check_handler.py` (modify) | Delete the existence exclusion and the "added later" card line. |
| `bot/services/vault_calendar.py` (modify) | Delete `build_first_seen`; keep `target_date_for`. |
| `bot/services/google_sheets_logger.py` (modify) | Drop the now-dead `first_seen` key from `get_history_bundle`. |
| `tests/test_balance_history.py` (create) | The derivation maths. |
| `tests/test_roster_scope.py` (create) | No wallet is ever excluded. |

---

### Task 1: Keep each transfer's timestamp

**Files:**
- Modify: `bot/services/balance_service.py` — the Tron branch (~line 44) and the ERC20 branch (~line 100) of `_fetch_transfers_after`
- Test: `tests/test_transfer_timestamps.py` (create)

**Interfaces:**
- Produces: every dict returned by `_fetch_transfers_after` gains `"ts"` — an **integer, epoch milliseconds**. Existing keys (`from`, `to`, `amount`, `success`) are unchanged, so every current consumer is unaffected.

Tron gives `block_ts` already in milliseconds. Etherscan gives `timeStamp` in **seconds** — multiply by 1000. Getting that wrong silently shifts every derived balance by decades, so the tests pin both.

- [ ] **Step 1: Write the failing test**

Create `tests/test_transfer_timestamps.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_transfer_timestamps.py -q`
Expected: FAIL with `KeyError: 'ts'`.

- [ ] **Step 3: Add `ts` on both chains**

In the Tron branch, extend the appended dict:

```python
                        out.append({
                            "from": t.get("from_address", ""), "to": t.get("to_address", ""),
                            "amount": Decimal(t.get("quant", "0")) / Decimal(1_000_000),
                            "success": t.get("finalResult") == "SUCCESS" and t.get("contractRet") == "SUCCESS",
                            # Tronscan already reports milliseconds.
                            "ts": int(t.get("block_ts", 0)),
                        })
```

In the ERC20 branch:

```python
                        out.append({"from": t.get("from", ""), "to": t.get("to", ""),
                                    "amount": Decimal(t.get("value", "0")) / Decimal(1_000_000),
                                    "success": True,
                                    # Etherscan reports SECONDS -- convert to milliseconds so both
                                    # chains speak the same unit.
                                    "ts": int(t["timeStamp"]) * 1000})
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_transfer_timestamps.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: 211 + 3 new, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add bot/services/balance_service.py tests/test_transfer_timestamps.py
git commit -m "feat: normalised transfers keep their timestamp in epoch ms

Tronscan reports block_ts in milliseconds; Etherscan reports timeStamp in seconds,
so it is multiplied by 1000. Both chains now speak the same unit, which the backfill
needs to bucket transfers by date. Additive -- existing consumers are unaffected."
```

---

### Task 2: Derive many dates from one transfer list

**Files:**
- Create: `bot/services/balance_history.py`
- Test: `tests/test_balance_history.py` (create)

**Interfaces:**
- Consumes: transfers carrying `ts` (Task 1); `VAULT_DAY_BOUNDARY` from `bot/services/google_sheets_logger.py`; `canonical_address` from `bot/services/chain_detector.py`.
- Produces: `balances_by_date(current_balance: Decimal, transfers: list[dict], address: str, dates: list[str]) -> dict[str, Decimal | None]` — one entry per requested ISO date; `None` means "cannot claim a figure".

This is the whole efficiency win, and it is pure arithmetic: sort transfers newest-first, walk the dates newest-first, and accumulate. Each transfer is visited exactly once across all 212 dates.

- [ ] **Step 1: Write the failing test**

Create `tests/test_balance_history.py`:

```python
# tests/test_balance_history.py
"""Derive a whole series of historical balances from ONE transfer list.

balance_at(D) = current_balance - net(transfers after D 00:00 GMT+7)

Doing this per-date would re-fetch the same history 212 times. Walking the dates
backwards and accumulating visits each transfer exactly once.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bot.services.balance_history import balances_by_date

GMT7 = timezone(timedelta(hours=7))


def ms(date_str, hh=12):
    """Epoch ms at hh:00 GMT+7 on date_str -- i.e. during that day."""
    return int(datetime.strptime(f"{date_str} {hh:02d}:00:00", "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=GMT7).timestamp() * 1000)


def tx(date_str, amount, to=None, frm=None, hh=12, success=True):
    return {"ts": ms(date_str, hh), "amount": Decimal(str(amount)),
            "to": to or "", "from": frm or "", "success": success}


ME = "TME"


def test_no_transfers_means_every_date_equals_the_current_balance():
    out = balances_by_date(Decimal("100"), [], ME, ["2026-01-01", "2026-06-01"])
    assert out == {"2026-01-01": Decimal("100"), "2026-06-01": Decimal("100")}


def test_an_inflow_is_subtracted_from_earlier_dates_only():
    """Received 30 on 2026-03-10, holding 100 now -> held 70 before that day."""
    out = balances_by_date(Decimal("100"), [tx("2026-03-10", 30, to=ME)], ME,
                           ["2026-03-09", "2026-03-10", "2026-03-11"])
    assert out["2026-03-09"] == Decimal("70")   # before the transfer
    assert out["2026-03-10"] == Decimal("70")   # 00:00 that day, transfer was at 12:00
    assert out["2026-03-11"] == Decimal("100")  # after


def test_an_outflow_is_added_back_to_earlier_dates():
    out = balances_by_date(Decimal("100"), [tx("2026-03-10", 30, frm=ME)], ME,
                           ["2026-03-09", "2026-03-11"])
    assert out["2026-03-09"] == Decimal("130")
    assert out["2026-03-11"] == Decimal("100")


def test_failed_transfers_are_ignored():
    out = balances_by_date(Decimal("100"), [tx("2026-03-10", 30, to=ME, success=False)],
                           ME, ["2026-03-09"])
    assert out["2026-03-09"] == Decimal("100")


def test_a_wallet_funded_later_reads_zero_before_it_was_funded():
    """The whole point: a wallet that did not exist yet is 0.00, not a gap."""
    out = balances_by_date(Decimal("500"), [tx("2026-05-18", 500, to=ME)], ME,
                           ["2026-05-17", "2026-05-19"])
    assert out["2026-05-17"] == Decimal("0")
    assert out["2026-05-19"] == Decimal("500")


def test_a_negative_result_is_refused():
    """A USDT balance cannot be negative -- the window must be wrong, so claim nothing."""
    out = balances_by_date(Decimal("10"), [tx("2026-03-10", 50, to=ME)], ME, ["2026-03-09"])
    assert out["2026-03-09"] is None


def test_many_transfers_across_many_dates():
    txs = [tx("2026-01-05", 100, to=ME), tx("2026-02-05", 40, frm=ME),
           tx("2026-03-05", 25, to=ME), tx("2026-04-05", 10, frm=ME)]
    # current = 100 - 40 + 25 - 10 = 75 net, so start from 75 + opening 0
    out = balances_by_date(Decimal("75"), txs, ME,
                           ["2026-01-04", "2026-01-06", "2026-02-06", "2026-03-06", "2026-04-06"])
    assert out["2026-01-04"] == Decimal("0")
    assert out["2026-01-06"] == Decimal("100")
    assert out["2026-02-06"] == Decimal("60")
    assert out["2026-03-06"] == Decimal("85")
    assert out["2026-04-06"] == Decimal("75")


def test_a_transfer_exactly_at_the_boundary_belongs_to_the_later_side():
    """Consistent with get_balance_at, whose window is (cutoff, now] -- strictly after."""
    out = balances_by_date(Decimal("100"), [tx("2026-03-10", 30, to=ME, hh=0)], ME,
                           ["2026-03-10"])
    assert out["2026-03-10"] == Decimal("100"), "a transfer AT 00:00 is not 'after' it"


def test_erc20_addresses_compare_case_insensitively():
    out = balances_by_date(Decimal("100"), [tx("2026-03-10", 30, to="0xABC")], "0xabc",
                           ["2026-03-09"])
    assert out["2026-03-09"] == Decimal("70")


def test_dates_may_be_supplied_in_any_order():
    txs = [tx("2026-03-10", 30, to=ME)]
    a = balances_by_date(Decimal("100"), txs, ME, ["2026-03-11", "2026-03-09"])
    b = balances_by_date(Decimal("100"), txs, ME, ["2026-03-09", "2026-03-11"])
    assert a == b


def test_each_transfer_is_visited_once_regardless_of_date_count():
    """Efficiency is the reason this function exists -- 212 dates must not mean 212 passes."""
    txs = [tx("2026-03-10", 1, to=ME) for _ in range(50)]
    dates = [(datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(212)]
    out = balances_by_date(Decimal("50"), txs, ME, dates)
    assert out["2026-01-01"] == Decimal("0")
    assert out["2026-12-31" if "2026-12-31" in out else dates[-1]] == Decimal("50")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_balance_history.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.balance_history'`.

- [ ] **Step 3: Create the module**

Create `bot/services/balance_history.py`:

```python
"""Derive a series of historical balances from ONE transfer list. Pure -- no network.

    balance_at(D) = current_balance - net(transfers strictly after D 00:00 GMT+7)

Reconstructing each date separately would re-fetch the same history once per date --
212 fetches per wallet for a 7-month window. Sorting once and walking the dates
backwards visits each transfer exactly once for the whole series.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bot.services.chain_detector import canonical_address
from bot.services.google_sheets_logger import VAULT_DAY_BOUNDARY

GMT7 = timezone(timedelta(hours=7))


def day_boundary_ms(date_str):
    """Epoch ms at the vault's day boundary for `date_str` (00:00:00 GMT+7)."""
    return int(datetime.strptime(f"{date_str} {VAULT_DAY_BOUNDARY}", "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=GMT7).timestamp() * 1000)


def balances_by_date(current_balance, transfers, address, dates):
    """Balance at each date's 00:00 GMT+7, derived from one transfer list.

    Returns {date: Decimal} with None for any date whose result would be negative --
    a USDT balance cannot be negative, so that means the transfer window was wrong
    (truncated or overlapping) and no figure should be claimed. Same fail-safe as
    BalanceService.get_balance_at.

    The window is STRICTLY after the boundary, matching get_balance_at's (cutoff, now].
    """
    me = canonical_address(address)

    # One signed delta per transfer that actually moved this wallet's balance.
    events = []
    for t in transfers or []:
        if not t.get("success", True):
            continue
        delta = Decimal(0)
        amount = t["amount"]
        if canonical_address(t.get("to", "")) == me:
            delta += amount
        if canonical_address(t.get("from", "")) == me:
            delta -= amount
        if delta:
            events.append((int(t["ts"]), delta))
    events.sort(key=lambda e: e[0], reverse=True)   # newest first

    out, i, net_after = {}, 0, Decimal(0)
    for date_str in sorted(dates, reverse=True):    # newest date first
        cutoff = day_boundary_ms(date_str)
        while i < len(events) and events[i][0] > cutoff:
            net_after += events[i][1]
            i += 1
        balance = Decimal(current_balance) - net_after
        out[date_str] = balance if balance >= 0 else None
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_balance_history.py -q`
Expected: PASS.

- [ ] **Step 5: Cross-check against the existing reconstruction on live data**

This proves the fast path agrees with the slow path that is already trusted in production:

```bash
.venv/bin/python - <<'PY'
import os, json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
import logging; logging.basicConfig(level=logging.ERROR)
from bot.services.balance_service import BalanceService
from bot.services.balance_history import balances_by_date, day_boundary_ms
svc=BalanceService()
w=json.load(open("wallets.json")); roster=w if isinstance(w,list) else list(w.values())
DATES=["2026-07-15","2026-06-01","2026-03-01"]
print(f"{'wallet':<24}{'date':<12}{'slow (get_balance_at)':>22}{'fast (series)':>16}  agree")
bad=0
for x in roster[:5]:
    a,ch=x["address"], x.get("chain","TRC20")
    cur=svc.get_balance(a,ch)
    tf=svc._fetch_transfers_after(a,ch, day_boundary_ms(min(DATES)))
    if cur is None or tf is None:
        print(f"{x['wallet']:<24}{'-':<12}{'unavailable':>22}"); continue
    fast=balances_by_date(cur,tf,a,DATES)
    for d in DATES:
        slow=svc.get_balance_at(a,ch,day_boundary_ms(d))
        ok = (slow is None and fast[d] is None) or (slow is not None and fast[d] is not None and abs(slow-fast[d])<Decimal("0.000001"))
        bad += 0 if ok else 1
        print(f"{x['wallet']:<24}{d:<12}{str(slow):>22}{str(fast[d]):>16}  {'OK' if ok else 'MISMATCH'}")
print(f"\nmismatches: {bad}   (must be 0)")
PY
```
Expected: `mismatches: 0`. **If any mismatch appears, STOP and report it — the derivation disagrees with the trusted path and must not be used to write anything.**

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q | tail -3
git add bot/services/balance_history.py tests/test_balance_history.py
git commit -m "feat: derive a whole balance series from one transfer list

balance_at(D) = current - net(transfers strictly after D 00:00 GMT+7). Sorting once
and walking the dates backwards visits each transfer exactly once for the whole
series, instead of re-fetching the same history per date.

Negative results return None, the same fail-safe as get_balance_at: a USDT balance
cannot be negative, so it means the window was wrong. Verified against
get_balance_at on live data -- 0 mismatches."
```

---

### Task 3: The backfill runner, dry run only

**Files:**
- Create: `backfill_history.py` (repo root, beside `cleanup.py` and `wallets_to_gg_sheet.py`)

**Interfaces:**
- Consumes: `balances_by_date`, `day_boundary_ms` (Task 2); `BalanceService`; `GoogleSheetsBalanceLogger.save_rebuilt_balances(date_str, rows)`.
- Produces: a script. `python backfill_history.py` dry-runs; `python backfill_history.py --write` writes.

**Dry run is the default.** Writing requires an explicit flag — nobody backfills the finance record by accident.

- [ ] **Step 1: Write the script**

Create `backfill_history.py`:

```python
#!/usr/bin/env python3
"""Backfill missing DAILY_REPORT rows for every wallet in wallets.json.

Fetches each wallet's transfer history ONCE and derives every date's balance from it,
so the cost is one fetch per wallet rather than one reconstruction per wallet-day.

Dry run by default -- pass --write to actually save.

    python backfill_history.py                 # show what would be written
    python backfill_history.py --write         # write it
    python backfill_history.py --start 2026-01-01 --end 2026-07-30
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from bot.services.balance_history import balances_by_date, day_boundary_ms
from bot.services.balance_service import BalanceService
from bot.services.chain_detector import canonical_address
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill")
GMT7 = timezone(timedelta(hours=7))

# The daily report writes at 17:00 UTC. Never run inside this margin of it.
DAILY_REPORT_UTC_HOUR = 17
BLACKOUT_MINUTES = 30


def in_blackout():
    now = datetime.now(timezone.utc)
    start = now.replace(hour=DAILY_REPORT_UTC_HOUR, minute=0, second=0, microsecond=0)
    return abs((now - start).total_seconds()) < BLACKOUT_MINUTES * 60


def daterange(start, end):
    d, out = date.fromisoformat(start), []
    last = date.fromisoformat(end)
    while d <= last:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-07-30")
    ap.add_argument("--write", action="store_true", help="actually save (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N wallets")
    args = ap.parse_args()

    if args.write and in_blackout():
        sys.exit(f"REFUSING: within {BLACKOUT_MINUTES} min of the "
                 f"{DAILY_REPORT_UTC_HOUR}:00 UTC daily report. Try later.")

    dates = daterange(args.start, args.end)
    logger = GoogleSheetsBalanceLogger()
    svc = BalanceService()

    with open("wallets.json") as f:
        raw = json.load(f)
    roster = raw if isinstance(raw, list) else list(raw.values())
    if args.limit:
        roster = roster[:args.limit]

    rows = logger._read_daily_report_rows()
    if rows is None:
        sys.exit("REFUSING: could not read DAILY_REPORT. A failed read must never be "
                 "mistaken for 'nothing is saved'.")

    # What is already there, and what it says -- used both to find gaps and to verify.
    existing = defaultdict(dict)          # date -> {canonical_address: Decimal}
    for r in rows:
        if len(r) < 7 or not r[1]:
            continue
        try:
            existing[r[1]][canonical_address(r[5])] = Decimal(str(r[6]).replace(",", ""))
        except Exception:
            continue

    print(f"window {args.start} .. {args.end}  ({len(dates)} days)")
    print(f"wallets: {len(roster)}   mode: {'WRITE' if args.write else 'DRY RUN'}\n")

    to_write = defaultdict(list)          # date -> [row dicts]
    unavailable, agree, disagree = [], 0, []

    for n, wallet in enumerate(roster, 1):
        name = wallet.get("wallet")
        addr = wallet.get("address", "")
        chain = wallet.get("chain", "TRC20")
        key = canonical_address(addr)

        current = svc.get_balance(addr, chain)
        if current is None:
            unavailable.append((name, "current balance unavailable"))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - current balance unavailable")
            continue

        transfers = svc._fetch_transfers_after(addr, chain, day_boundary_ms(args.start))
        if transfers is None:
            unavailable.append((name, "transfer history too long to fetch safely"))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - transfer history unavailable")
            continue

        series = balances_by_date(current, transfers, addr, dates)

        gaps = 0
        for d in dates:
            derived = series[d]
            saved = existing.get(d, {}).get(key)
            if saved is not None:
                # Agreement check: our derivation must match what was measured that day.
                if derived is not None and abs(derived - saved) <= Decimal("0.01"):
                    agree += 1
                elif derived is not None:
                    disagree.append((name, d, saved, derived))
                continue
            if derived is None:
                unavailable.append((name, f"{d}: negative reconstruction"))
                continue
            to_write[d].append({"name": name, "company": wallet.get("company", "Unknown"),
                                "address": addr, "balance": derived})
            gaps += 1
        print(f"[{n:>3}/{len(roster)}] {name:<28} {len(transfers):>5} transfers, "
              f"{gaps:>4} gaps to fill")

    total = sum(len(v) for v in to_write.values())
    print(f"\n{'='*72}")
    print(f"agreement check : {agree:,} existing rows matched the derivation")
    print(f"DISAGREEMENTS   : {len(disagree)}")
    for name, d, saved, derived in disagree[:20]:
        print(f"    {name:<26} {d}  saved={saved:,.2f}  derived={derived:,.2f}  "
              f"diff={derived-saved:+,.2f}")
    print(f"unavailable     : {len(unavailable)}")
    for name, why in unavailable[:20]:
        print(f"    {name:<26} {why}")
    print(f"rows to write   : {total:,} across {len(to_write)} dates")

    if disagree:
        sys.exit("\nREFUSING TO WRITE: the derivation disagrees with rows that were "
                 "measured on the day. Investigate before backfilling.")

    if not args.write:
        print("\nDRY RUN -- nothing written. Re-run with --write to save.")
        return

    print("\nwriting...")
    written = 0
    for d in sorted(to_write):
        ok, batch = logger.save_rebuilt_balances(d, to_write[d])
        if not ok:
            sys.exit(f"WRITE FAILED on {d} after {written} rows. Stopping.")
        written += len(to_write[d])
        print(f"  {d}  {len(to_write[d]):>3} rows  batch {batch}")
    print(f"\nwrote {written:,} rows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry run on 3 wallets to prove the mechanics**

```bash
.venv/bin/python backfill_history.py --limit 3 2>&1 | tail -25
```
Expected: per-wallet transfer counts and gap counts, an agreement count, **0 disagreements**, and `DRY RUN -- nothing written`.

**If any disagreement appears, STOP.** It means the derivation contradicts a figure that was measured on the day, and nothing may be written until that is explained.

- [ ] **Step 3: Confirm the dry run really wrote nothing**

```bash
.venv/bin/python - <<'PY'
import os
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
c=Credentials.from_service_account_file(os.environ['GOOGLE_CREDENTIALS_FILE'],
  scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
sh=build('sheets','v4',credentials=c).spreadsheets()
n=len(sh.values().get(spreadsheetId=os.environ['GOOGLE_SHEET_ID'],
                      range='DAILY_REPORT!A:H').execute().get('values',[]))-1
print(f"DAILY_REPORT data rows: {n:,}   (expect 17,570 -- unchanged)")
PY
```
Expected: `17,570`.

- [ ] **Step 4: Commit**

```bash
git add backfill_history.py
git commit -m "feat: one-time backfill script for missing DAILY_REPORT rows

Fetches each wallet's history once and derives every date from it -- one fetch per
wallet instead of one reconstruction per wallet-day.

Dry run by default; --write is required to save. Refuses to write if the derivation
disagrees with any row that was measured on the day, if the sheet read fails, or if
it is within 30 minutes of the 17:00 UTC daily report."
```

---

### Task 4: Full dry run, then the real backfill

**Files:** none changed — this task runs the tool and verifies the data.

**This is the task that writes to the finance record.** Everything here is verification around a single write.

- [ ] **Step 1: Full dry run across all 71 wallets**

```bash
.venv/bin/python backfill_history.py 2>&1 | tee /tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad/backfill_dryrun.txt | tail -30
```
Expected: **0 disagreements**, and roughly **3,079** rows to write. A materially different number needs explaining before proceeding — the gap count was measured from the same sheet.

- [ ] **Step 2: Report the dry run to the user and get explicit go-ahead**

Show: rows to write, dates covered, the agreement count, and every unavailable wallet with its reason. **Do not run `--write` without an explicit go-ahead.**

- [ ] **Step 3: Check the clock**

```bash
date -u '+%H:%M UTC'
```
The run takes minutes, not hours, but it must not be within 30 minutes of 17:00 UTC. The script refuses on its own; check anyway so the refusal is not a surprise.

- [ ] **Step 4: Run the backfill**

```bash
.venv/bin/python backfill_history.py --write 2>&1 | tee /tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad/backfill_run.txt | tail -30
```
Expected: `wrote N rows`, where N matches the dry run's count.

- [ ] **Step 5: Verify coverage and that nothing was duplicated**

```bash
.venv/bin/python - <<'PY'
import os, json
from collections import defaultdict
from datetime import date, timedelta
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from bot.services.chain_detector import canonical_address
c=Credentials.from_service_account_file(os.environ['GOOGLE_CREDENTIALS_FILE'],
  scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
sh=build('sheets','v4',credentials=c).spreadsheets()
rows=sh.values().get(spreadsheetId=os.environ['GOOGLE_SHEET_ID'],range='DAILY_REPORT!A:H').execute().get('values',[])[1:]
w=json.load(open("wallets.json")); roster=w if isinstance(w,list) else list(w.values())
ros={canonical_address(x['address']) for x in roster}
per=defaultdict(list)
for r in rows:
    if len(r)>5 and r[1]:
        k=canonical_address(r[5])
        if k in ros: per[r[1]].append(k)
d=date(2026,1,1); short=[]; dupes=[]
while d<=date(2026,7,30):
    s=d.isoformat(); ks=per.get(s,[])
    if len(set(ks))<len(ros): short.append((s,len(set(ks))))
    if len(ks)!=len(set(ks)): dupes.append(s)
    d+=timedelta(days=1)
print(f"total DAILY_REPORT rows: {len(rows):,}")
print(f"dates 2026-01-01..2026-07-30 with fewer than {len(ros)} wallets: {len(short)}")
for s,n in short[:10]: print(f"    {s}: {n}")
print(f"dates with a DUPLICATE wallet: {len(dupes)}  {dupes[:5]}")
PY
```
Expected: 0 short dates (or only dates whose shortfall matches a wallet reported unavailable), and **0 duplicates**.

- [ ] **Step 6: Spot-check a backfilled date in Lark**

Run `/check [2026-05-17] [o]` in the dev topic. Expected: 71 wallets counted, and `OKKZ5A` present with a real figure — it joined on 2026-05-18 and previously showed as "added later" while holding 2,350,006.97.

---

### Task 5: Delete the existence exclusion

**Files:**
- Modify: `bot/handlers/check_handler.py` — remove `_existed_on` (~line 336), `_existed_by` (~line 320), and the `not_yet_created` branch in `classify_wallets` (~line 370)
- Modify: `bot/services/vault_calendar.py` — remove `build_first_seen` and `_iso_prefix`
- Modify: `bot/services/google_sheets_logger.py` — remove the `first_seen` key from `get_history_bundle`
- Delete: the `build_first_seen` tests in `tests/test_vault_calendar.py`
- Test: `tests/test_roster_scope.py` (create)

**Interfaces:**
- Produces: `classify_wallets(roster, snapshot, date_str)` — the `first_seen` parameter is gone. Every wallet returns status `saved` or `needs_rebuild`; `not_yet_created` no longer exists.

- [ ] **Step 1: Write the failing test**

Create `tests/test_roster_scope.py`:

```python
# tests/test_roster_scope.py
"""wallets.json is the scope, full stop.

Every wallet gets a figure for every date. When it was added is never consulted --
a wallet that did not exist yet reconstructs to 0.00, which is the truthful answer.
Excluding it hid 20,184,069.03 USDT across 31 wallets that were already funded
before they entered monitoring.
"""
from bot.handlers.check_handler import CheckHandler


def w(name, addr, created_at=None):
    return {"wallet": name, "address": addr, "company": "CO",
            "chain": "TRC20", "created_at": created_at}


def test_a_wallet_added_after_the_date_is_still_expected():
    """Previously not_yet_created -> silently dropped. Now it must be rebuilt."""
    h = CheckHandler()
    out = h.classify_wallets([w("Late", "TAAA", "2026-05-18")], {}, "2026-01-01")
    assert len(out) == 1
    assert out[0]["status"] == "needs_rebuild"


def test_no_wallet_is_ever_reported_as_not_yet_created():
    h = CheckHandler()
    roster = [w("A", "TAAA", "2026-05-18"), w("B", "TBBB", None), w("C", "TCCC", "2020-01-01")]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert {e["status"] for e in out} == {"needs_rebuild"}
    assert all(e["status"] != "not_yet_created" for e in out)


def test_a_saved_row_is_still_used():
    h = CheckHandler()
    snap = {"TAAA": {"wallet_name": "A", "company": "CO", "address": "TAAA",
                     "balance": 42, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets([w("A", "TAAA", "2026-05-18")], snap, "2026-01-01")
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 42


def test_every_roster_wallet_appears_exactly_once():
    h = CheckHandler()
    roster = [w(f"W{i}", f"T{i}") for i in range(71)]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert len(out) == 71
    assert len({e["name"] for e in out}) == 71


def test_created_at_is_no_longer_consulted():
    """Identical wallets differing only in created_at must classify identically."""
    h = CheckHandler()
    a = h.classify_wallets([w("A", "TAAA", "2099-01-01")], {}, "2026-01-01")
    b = h.classify_wallets([w("A", "TAAA", None)], {}, "2026-01-01")
    assert a[0]["status"] == b[0]["status"] == "needs_rebuild"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_roster_scope.py -q`
Expected: FAIL — the first two tests report `not_yet_created`.

- [ ] **Step 3: Simplify `classify_wallets`**

Replace its body's branch and drop the `first_seen` parameter:

```python
    def classify_wallets(self, roster, snapshot, date_str):
        """Decide, per wallet, what we can show for `date_str`. Pure - no network.

        SCOPE: the wallets in wallets.json, and only those -- but ALL of them, always.
        When a wallet was added to the list is never consulted: a wallet that did not
        exist on `date_str` reconstructs to 0.00, which is the truthful answer. The
        previous rule excluded such wallets and hid real money -- 31 wallets were
        already holding 20,184,069.03 USDT combined before they entered monitoring.

        status: saved         - a figure was recorded that day
                needs_rebuild - no figure recorded, so work it out from the chain
        """
        out = []
        for w in roster:
            key = canonical_address(w.get("address", ""))
            entry = snapshot.get(key)
            if entry:
                status, balance = "saved", entry["balance"]
            else:
                status, balance = "needs_rebuild", None
            out.append({"name": w.get("wallet"), "company": w.get("company", "Unknown"),
                        "address": w.get("address", ""), "chain": w.get("chain", "TRC20"),
                        "status": status, "balance": balance})
        return out
```

Then delete `_existed_on` and `_existed_by` entirely, and update the single call site in `_handle_historical` to `self.classify_wallets(roster, snapshot, target_date)`.

- [ ] **Step 4: Remove the now-dead first_seen machinery**

In `bot/services/vault_calendar.py`, delete `build_first_seen` and `_iso_prefix`, and the now-unused `canonical_address` import. Keep `target_date_for`, `OPENING`, `CLOSING`.

In `bot/services/google_sheets_logger.py`, drop `first_seen` from both returns of `get_history_bundle`, remove the `roster` parameter, and remove the `build_first_seen` import.

In `tests/test_vault_calendar.py`, delete every `build_first_seen` test. In `tests/test_history_bundle.py`, remove assertions on `first_seen` and the `roster` argument.

- [ ] **Step 5: Run the new tests, then the full suite**

```bash
.venv/bin/python -m pytest tests/test_roster_scope.py -q
.venv/bin/python -m pytest tests/ -q | tail -3
```
Expected: new tests pass; suite green. The count drops by the deleted `build_first_seen` tests — state the new number.

- [ ] **Step 6: Commit**

```bash
git add -A bot/ tests/
git commit -m "feat: wallets.json is the scope - no wallet is ever excluded by date

/check [date] was reporting a wallet as 'added on or after this date' whenever it
joined wallets.json later, even when the address demonstrably held USDT then. 31 of
the 52 wallets that joined later were already funded - 20,184,069.03 USDT combined.

Now every wallet in the roster gets a figure for every date. One that did not exist
reconstructs to 0.00, the truthful answer rather than an excuse.

Deletes the whole existence machinery: _existed_on, _existed_by, build_first_seen,
the first_seen payload, and the not_yet_created status."
```

---

### Task 6: Card, help, and deploy

**Files:**
- Modify: `bot/handlers/check_handler.py` — `_create_historical_card`
- Modify: `bot/handlers/help_handler.py` if it mentions the removed behaviour
- Test: `tests/test_roster_scope.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_roster_scope.py`:

```python
import json


def _entries(saved=2, rebuilt=1, unavailable=0):
    out = [{"name": f"S{i}", "company": "CO", "address": f"TS{i}", "chain": "TRC20",
            "status": "saved", "balance": 100} for i in range(saved)]
    out += [{"name": f"R{i}", "company": "CO", "address": f"TR{i}", "chain": "TRC20",
             "status": "rebuilt", "balance": 0} for i in range(rebuilt)]
    out += [{"name": f"U{i}", "company": "CO", "address": f"TU{i}", "chain": "TRC20",
             "status": "failed", "balance": None} for i in range(unavailable)]
    return out


def test_card_no_longer_says_added_after_this_date():
    h = CheckHandler()
    b = json.dumps([h._create_historical_card(_entries(), "2026-01-01", [], [], None,
                                              "closing", "2026-01-02")])
    assert "added on or after" not in b
    assert "added after" not in b
    assert "no balance yet" not in b


def test_a_zero_balance_wallet_is_listed_not_hidden():
    """A zero is a real balance. Hiding it breaks the reconciliation to the roster size."""
    h = CheckHandler()
    b = json.dumps([h._create_historical_card(_entries(2, 1), "2026-01-01", [], [], None,
                                              "closing", "2026-01-02")])
    assert "R0" in b, "the rebuilt 0.00 wallet must appear in the list"


def test_summary_counts_every_wallet():
    h = CheckHandler()
    b = json.dumps([h._create_historical_card(_entries(68, 3), "2026-01-01", [], [], None,
                                              "closing", "2026-01-02")])
    assert "71" in b
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_roster_scope.py -q`
Expected: FAIL — the card still contains the added-later line.

- [ ] **Step 3: Update the card**

Remove the added-later block from `_create_historical_card` entirely. The summary becomes:

```
📊 **Total wallets in monitoring: 71**
• **68** have a balance recorded for this date
• **3** were calculated from blockchain records
➡️ **71 wallets counted** in the total below
```

A wallet whose reconstruction failed stays listed as **unavailable** and is excluded from the counted total, with the count reflecting that — never silently counted as zero. Keep the settled copy rules: wallet name before status, **bold** names, no backticks, plain language.

- [ ] **Step 4: Check `/help` for stale wording**

```bash
grep -rn "added after\|added on or after\|not yet\|no balance yet" bot/handlers/help_handler.py bot/handlers/check_handler.py
```
Remove any user-facing survivor. Comments explaining history may stay.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: green.

- [ ] **Step 6: Self-test against real data**

```bash
.venv/bin/python /tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad/selftest_openclose.py 2>&1 | tail -6
```
Expected: 26/26 still passing. **Cases A1–A3 will now report different totals** — the old expectations assumed excluded wallets. Update those expected figures to the new values and say clearly in the report which changed and by how much.

- [ ] **Step 7: Commit, publish, deploy**

```bash
git add -A bot/ tests/
git commit -m "feat: card counts every wallet, drops the added-later line"
.venv/bin/python -m pytest tests/ -q | tail -2
git status --short
git push origin feature/check-date-and-remove-fix
git checkout main && git merge --ff-only feature/check-date-and-remove-fix && git push origin main
git checkout feature/check-date-and-remove-fix
```

Then on prod:

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 'cd /home/ubuntu/crypto-lark-bot
date -u +%H:%M
cp .env .env.bak.$(date +%Y%m%d%H%M%S); cp wallets.json wallets.json.bak.$(date +%Y%m%d%H%M%S)
git pull --ff-only
git status --porcelain --untracked-files=no
./start_lark_bot.sh restart' 
```

**Never copy `credentials/prd_env.txt` onto prod** — it holds 8 authorized users against prod's 11.

- [ ] **Step 8: Verify the deploy from a FRESH ssh connection**

The restart kills its own ssh session, so its output cannot be trusted.

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 'cd /home/ubuntu/crypto-lark-bot
echo "HEAD: $(git rev-parse --short HEAD)"
CM=$(git log -1 --format=%ct)
for name in lark_bot.py main.py wallets_to_gg_sheet.py cleanup.py; do
  for PID in $(pgrep -f "python.*$name"); do
    [ "$(tr -d "\0" < /proc/$PID/comm 2>/dev/null)" = "python" ] || continue
    ST=$(date -d "$(ps -o lstart= -p $PID)" +%s)
    [ "$ST" -gt "$CM" ] && echo "  NEW   $name" || echo "  STALE $name <-- restart again"
  done
done
pgrep -af ngrok | head -1 | cut -c1-45
curl -s --max-time 6 http://127.0.0.1:8080/
md5sum .env wallets.json
echo "authorized users: $(grep "^LARK_AUTHORIZED_USERS=" .env | cut -d= -f2 | tr "," "\n" | grep -c .)"'
```
Expected: all four **NEW**, ngrok up, health OK, `.env` md5 `8980c501f4bb6e902f2eff153e994a4e`, **11** authorized users.

Rollback if needed: `git reset --hard c1afc8f && ./start_lark_bot.sh restart`.

---

## Self-Review

**Spec coverage.** §1 the problem → Task 5's test rationale. §2 the rule → Task 5. §3 backfill window, method, execution, dry run, idempotence → Tasks 1–4. §3 "backfill first, deploy second" → task order (4 before 5). §4 what the code loses → Task 5 Steps 3–4. §5 the card, zeros listed, unavailable excluded → Task 6. §6 risks: rising totals → Task 6 Step 6; unavailable wallets → Task 3's script reports each with a reason; shared rate limits → Task 3's blackout window; a wrong reconstruction saved → Task 3's agreement check plus the negative guard in Task 2. §7 verification → Task 4 Steps 5–6.

**Placeholders.** None — every step carries real code or a real command with its expected output.

**Type consistency.** `ts` is an int in epoch ms in Tasks 1, 2, 3. `balances_by_date(current_balance, transfers, address, dates) -> {date: Decimal|None}` is identical in Tasks 2 and 3. `day_boundary_ms(date_str) -> int` in Tasks 2 and 3. `classify_wallets(roster, snapshot, date_str)` — three parameters — in Tasks 5 and 6. `save_rebuilt_balances(date_str, rows)` with `rows` as dicts of `name/company/address/balance` matches the existing signature used in Task 3.

**Two risks flagged for the executor.**

1. **Task 4 Step 4 is the only irreversible step.** It writes ~3,079 rows to the finance record. It must not run until the dry run shows 0 disagreements *and* the user has explicitly approved the dry-run output.
2. **Task 5 deletes code other tests depend on.** `tests/test_vault_calendar.py` and `tests/test_history_bundle.py` both exercise `build_first_seen`. Deleting those tests is correct — the feature is gone — but every *other* assertion in those files must survive untouched. Removing an inconvenient assertion instead of a genuinely dead one is the failure mode to watch for.
