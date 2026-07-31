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

# Importing Config runs bot/utils/config.py's module-level load_dotenv(), the same
# mechanism main.py and lark_bot.py rely on -- so GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID,
# TRON_API_KEY and ETHEREUM_API_KEY are picked up from .env automatically. Without this,
# an operator who forgets to export them by hand would silently hit "sheet unconfigured"
# and this script would refuse to run for the wrong reason.
from bot.utils.config import Config
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
    ap.add_argument("--wallet", action="append", default=None,
                     help="only process this wallet, by its exact name in wallets.json "
                          "(repeatable, e.g. --wallet 'OKKZ1A' --wallet 'OKKZ 2')")
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
    if args.wallet:
        wanted = set(args.wallet)
        roster = [w for w in roster if w.get("wallet") in wanted]
        missing = wanted - {w.get("wallet") for w in roster}
        if missing:
            sys.exit(f"REFUSING: unknown wallet name(s) not in wallets.json: "
                     f"{', '.join(sorted(missing))}")
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
