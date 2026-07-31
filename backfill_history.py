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
import time
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


JITTER_GRACE_S = 5   # read->write gap: the row's Time is WRITE-time; the balance was
                     # read up to a few seconds earlier (API call, then datetime.now()).


def _net_up_to(transfers, me, start, end):
    """Signed net of successful transfers in (start, end]. +received, -sent."""
    net = Decimal(0)
    for t in transfers or []:
        if not t.get("success", True):
            continue
        ts = int(t["ts"])
        if not (start < ts <= end):
            continue
        amount = t["amount"]
        if canonical_address(t.get("to", "")) == me:
            net += amount
        if canonical_address(t.get("from", "")) == me:
            net -= amount
    return net


def disagreement_explained(transfers, address, date_str, time_str, saved, derived):
    """Is a derived-vs-measured disagreement fully explained by the measurement's
    read->write timing, rather than a real error?

    The daily report does not land at exactly 00:00:00 GMT+7 -- it lands
    00:00:31..00:01:35 -- and its row Time is the WRITE instant, while the balance was
    READ up to a few seconds earlier. A transfer in that read->write gap sits in the
    measured row but not in a derivation anchored at the true 00:00:00 boundary (or the
    reverse). So the effective read instant is somewhere in [Time - JITTER_GRACE_S, Time].

    We try every plausible read instant (the stamped Time, and just-before each transfer
    in that grace window) and return the first whose window net reconciles `derived` and
    `saved` to the cent: derived == saved - net(00:00:00, read_instant].

    The MONEY tolerance stays 0.01 -- only the boundary SECOND is fuzzy, never the
    amount. A genuine derivation error (wrong by an amount that does not correspond to a
    transfer within a few seconds of the row's Time) is NOT explained by this and still
    blocks the write. Returns (explained, net, effective_time_ms).
    """
    me = canonical_address(address)
    start = day_boundary_ms(date_str)
    try:
        end = int(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                  .replace(tzinfo=GMT7).timestamp() * 1000)
    except ValueError:
        return (False, None, None)     # malformed time -> nothing to explain it with
    lo = end - JITTER_GRACE_S * 1000
    candidates = {end}
    for t in transfers or []:
        ts = int(t["ts"])
        if lo < ts <= end:
            candidates.add(ts - 1)      # a read that landed just before this transfer
    for c in sorted(candidates, reverse=True):
        net = _net_up_to(transfers, me, start, c)
        if abs(Decimal(derived) - (Decimal(saved) - net)) <= Decimal("0.01"):
            return (True, net, c)
    return (False, None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-07-30")
    ap.add_argument("--write", action="store_true", help="actually save (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N wallets")
    ap.add_argument("--wallet", action="append", default=None,
                     help="only process this wallet, by its exact name in wallets.json "
                          "(repeatable, e.g. --wallet 'OKKZ1A' --wallet 'OKKZ 2')")
    ap.add_argument("--chunk-days", type=float, default=1,
                     help="chunk size in days for the chunked fallback fetch used when a "
                          "wallet's transfer history is too long for a single query "
                          "(default: 1). Only affects wallets that hit that fallback.")
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
    #
    # A date can carry more than one intraday batch (e.g. 2026-01-27 has a 00:00:31
    # scheduled run and an unrelated 13:45:13 one). The vault's rule -- implemented in
    # GoogleSheetsBalanceLogger._build_snapshot_from_rows and confirmed 2026-07-30 -- is
    # that the EARLIEST batch_id wins, because a row dated D means the balance at ~00:00
    # GMT+7 on day D, not whatever an unrelated afternoon run happened to see. Reuse that
    # method rather than reimplementing the tie-break by hand, and index every row by
    # (date, batch_id, address) so the winning row's own Check Type and Time columns can
    # be looked up afterwards -- both matter for the comparison below.
    rows_by_date = defaultdict(list)
    row_index = {}                        # (date, batch_id, canonical_address) -> row
    for r in rows:
        if len(r) < 7 or not r[1]:
            continue
        rows_by_date[r[1]].append(r)
        key = canonical_address(r[5]) if len(r) > 5 else ""
        if key:
            row_index[(r[1], r[0], key)] = r

    existing = {}                          # date -> {canonical_address: snapshot dict}
    for d in dates:
        existing[d] = logger._build_snapshot_from_rows(rows_by_date.get(d, []), d)

    print(f"window {args.start} .. {args.end}  ({len(dates)} days)")
    print(f"wallets: {len(roster)}   mode: {'WRITE' if args.write else 'DRY RUN'}\n")

    to_write = defaultdict(list)          # date -> [row dicts]
    unavailable, agree, disagree, explained = [], 0, [], []
    excluded_rebuilt = 0
    rebuilt_mismatches = []                # informational only -- never blocks the write
    unfilled_from_unavailable = 0

    for n, wallet in enumerate(roster, 1):
        name = wallet.get("wallet")
        addr = wallet.get("address", "")
        chain = wallet.get("chain", "TRC20")
        key = canonical_address(addr)

        current = svc.get_balance(addr, chain)
        if current is None:
            missing_days = sum(1 for d in dates if key not in existing.get(d, {}))
            unfilled_from_unavailable += missing_days
            unavailable.append((name, "current balance unavailable", missing_days))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - current balance unavailable "
                  f"({missing_days} wallet-days left unfilled)")
            continue

        transfers = svc._fetch_transfers_after(addr, chain, day_boundary_ms(args.start))
        if transfers is None:
            # A very high-volume wallet blows through Tronscan's 10,000-per-query cap in
            # one shot. Fall back to chunked windowed fetching, which slices the window
            # into (by default) day-sized pieces, each far under the cap, and is provably
            # complete per chunk. This path costs minutes instead of seconds, which is why
            # it is only tried after the fast path has already refused -- the other ~69
            # wallets never pay for it.
            #
            # CRITICAL: end_ms MUST be "now" (int(time.time() * 1000)), NOT the end of the
            # --start/--end backfill window. balances_by_date() computes
            # balance_at(D) = current_balance - net(transfers strictly after D), and
            # `current` (fetched above via get_balance) is the balance AS OF NOW. Fetching
            # only up to the window end would silently omit every transfer between the
            # window end and now, understating every single derived date by that same
            # missing net amount -- a constant offset that still looks plausible row by
            # row. (Hit exactly this while verifying: passing day_boundary_ms(args.end)
            # here made every derived value for "KZDW DPP TH 2" too high by +16,032.07,
            # precisely that wallet's net inflow between --end and now.)
            now_ms = int(time.time() * 1000)
            transfers = svc.fetch_transfers_between(
                addr, chain, day_boundary_ms(args.start), now_ms,
                chunk_days=args.chunk_days)
            if transfers is not None:
                log.info(f"{name}: fast-path transfer fetch unavailable, used chunked "
                         f"fetch instead ({len(transfers):,} transfers)")
                print(f"[{n:>3}/{len(roster)}] {name:<28} chunked fetch: "
                      f"{len(transfers):,} transfers")
        if transfers is None:
            missing_days = sum(1 for d in dates if key not in existing.get(d, {}))
            unfilled_from_unavailable += missing_days
            unavailable.append((name, "transfer history too long to fetch safely "
                                      "(even chunked)", missing_days))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - transfer history "
                  f"unavailable even with chunked fetch "
                  f"({missing_days} wallet-days left unfilled)")
            continue

        series = balances_by_date(current, transfers, addr, dates)

        gaps = 0
        for d in dates:
            derived = series[d]
            snap = existing.get(d, {}).get(key)
            if snap is not None:
                saved = snap["balance"]
                row = row_index.get((d, snap["batch_id"], key))
                check_type = row[7] if row and len(row) > 7 else ""
                if check_type == "rebuilt":
                    # Not ground truth: it is an earlier RECONSTRUCTION, not something
                    # the daily report measured on-chain that day, so comparing our
                    # derivation against it is derivation-vs-derivation, not
                    # derivation-vs-measurement -- it proves nothing either way.
                    # (Investigated 2026-07-31: the 2026-07-20 rebuilt rows' mismatches
                    # are NOT explained by their old pre-standardisation cutoff -- there
                    # are zero transfers in that wallet's (00:00, 00:01] window that day --
                    # so those rows are suspected simply wrong, produced by an earlier
                    # gap-fill before later fail-safes existed. Still excluded either way:
                    # right or wrong, they are not ground truth.)
                    # Still "already has a row" -- never a gap, never overwritten. Any
                    # mismatch is recorded separately, informational only -- it never
                    # blocks the write.
                    excluded_rebuilt += 1
                    if derived is not None and abs(derived - saved) > Decimal("0.01"):
                        rebuilt_mismatches.append((name, d, saved, derived))
                    continue
                if derived is not None and abs(derived - saved) <= Decimal("0.01"):
                    agree += 1
                elif derived is not None:
                    # The daily report does not land at exactly 00:00:00 GMT+7 -- it
                    # lands 00:00:31..00:01:35. A transfer inside that window is
                    # correctly IN the measured row and correctly ABSENT from a
                    # derivation anchored at the true 00:00:00 boundary; that is not a
                    # math error, it is two different (both correct) instants. Explain
                    # it from the wallet's own transfers rather than loosening the
                    # tolerance, which would hide real errors instead of this one
                    # known, understood effect.
                    time_str = snap.get("time") or "00:00:00"
                    ok_expl, window_net, _eff = disagreement_explained(
                        transfers, addr, d, time_str, saved, derived)
                    if ok_expl:
                        explained.append((name, d, saved, derived, time_str, window_net))
                    else:
                        disagree.append((name, d, saved, derived))
                continue
            if derived is None:
                unavailable.append((name, f"{d}: negative reconstruction", None))
                continue
            to_write[d].append({"name": name, "company": wallet.get("company", "Unknown"),
                                "address": addr, "balance": derived})
            gaps += 1
        print(f"[{n:>3}/{len(roster)}] {name:<28} {len(transfers):>5} transfers, "
              f"{gaps:>4} gaps to fill")

    total = sum(len(v) for v in to_write.values())
    print(f"\n{'='*72}")
    print(f"agreement check : {agree:,} existing rows matched the derivation")
    print(f"explained       : {len(explained):,} disagreements explained by a transfer "
          f"inside the snapshot window (report only, does not block the write)")
    for name, d, saved, derived, time_str, window_net in explained[:20]:
        print(f"    {name:<26} {d}  saved={saved:,.2f}  derived={derived:,.2f}  "
              f"time={time_str}  window_net={window_net:+,.2f}")
    print(f"excluded        : {excluded_rebuilt:,} existing rows were themselves "
          f"rebuilt (not ground truth; skipped from the agreement check, still counted "
          f"as 'already has a row')")
    print(f"  of which {len(rebuilt_mismatches):,} mismatch the derivation -- "
          f"informational only, does not block the write:")
    for name, d, saved, derived in rebuilt_mismatches[:20]:
        print(f"    {name:<26} {d}  saved={saved:,.2f}  derived={derived:,.2f}  "
              f"diff={derived-saved:+,.2f}")
    print(f"DISAGREEMENTS   : {len(disagree)}  (unexplained -- blocks the write)")
    for name, d, saved, derived in disagree[:20]:
        print(f"    {name:<26} {d}  saved={saved:,.2f}  derived={derived:,.2f}  "
              f"diff={derived-saved:+,.2f}")
    print(f"unavailable     : {len(unavailable)}  "
          f"({unfilled_from_unavailable:,} wallet-days left unfilled by skipped wallets)")
    for name, why, extra in unavailable[:20]:
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
