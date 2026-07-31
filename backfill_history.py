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
from bot.services.balance_history import balances_by_date, day_boundary_ms, signed_net
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


def _fmt_gmt7(ms):
    """ms epoch -> HH:MM:SS in GMT+7, for reporting an inferred fetch instant."""
    return datetime.fromtimestamp(ms / 1000, tz=GMT7).strftime("%H:%M:%S")


def disagreement_explained(transfers, address, date_str, time_str, saved, derived,
                           allow_partial=True):
    """Is a derived-vs-measured disagreement fully explained by WHEN the balance was
    actually read, rather than a real derivation error?

    `allow_partial` gates the one degree of freedom this check has. With it True, ANY
    prefix of the window's transfers may supply the inferred read instant. That freedom
    is what an independent review flagged: a genuinely WRONG derived value could be
    reconciled by a coincidental intermediate prefix whose net happens to equal the
    error. So callers pass allow_partial=False for any wallet that WRITES rows -- there,
    only the FULL window (the complete, fixed net up to the stamped Time; zero degrees of
    freedom, the exact check that cannot mask an error) may explain a disagreement.
    allow_partial=True is used ONLY for wallets that write nothing, where a false explain
    can corrupt no written data -- it can only mis-label a confidence signal on a row
    that already exists and is never touched.

    The daily report's row Time is the WRITE instant, not the READ instant: it reads 71
    wallets sequentially with rate-limit pacing and writes the whole batch afterwards, so
    each wallet's balance was actually captured at its own moment, somewhat BEFORE the
    stamped Time. A transfer landing between that true (unknown) read instant and the
    stamped Time sits inside (00:00:00, Time] but was never seen by the read that
    produced `saved` -- so summing the WHOLE window can overshoot or undershoot by
    exactly that transfer's amount, even though the derivation itself is correct.

    The true read instant is unknown, but it must fall at or just after one of this
    wallet's own transfer timestamps in the window (or the window's very start). So walk
    the window's successful transfers in chronological order, accumulating a running net,
    and after each one test whether

        derived + running_net == saved

    EXACTLY -- to the cent, the SAME 0.01 tolerance used everywhere else in this file,
    never a looser one. The first transfer whose running net satisfies this is taken as
    the inferred read instant: everything up to and including it was captured by the
    read; everything after it was not.

    This is NOT a loosened tolerance and must never become one: the equality check stays
    exact; only the WINDOW END being searched for is uncertain, and only a prefix of this
    wallet's own real transfers can supply it -- never an arbitrary allowance. A genuine
    derivation error, one that no prefix of the wallet's own transfers reconciles to the
    cent, is NOT explained by this and still blocks the write.

    balance_at(00:00:00) = balance_at(read_instant) - net(transfers in (00:00:00, read_instant]).

    Returns (explained: bool, net: Decimal | None, fetch_instant_ms: int | None).
    """
    me = canonical_address(address)
    start = day_boundary_ms(date_str)
    try:
        end = int(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                  .replace(tzinfo=GMT7).timestamp() * 1000)
    except ValueError:
        return (False, None, None)   # malformed/missing time -> nothing to explain it with

    window = [t for t in (transfers or [])
              if t.get("success", True) and start < int(t["ts"]) <= end]
    window.sort(key=lambda t: int(t["ts"]))     # chronological -- earliest prefix first

    target = Decimal(saved) - Decimal(derived)
    running = Decimal(0)
    for i, t in enumerate(window):
        amount = t["amount"]
        if canonical_address(t.get("to", "")) == me:
            running += amount
        if canonical_address(t.get("from", "")) == me:
            running -= amount
        is_full_window = (i == len(window) - 1)
        if abs(running - target) <= Decimal("0.01") and (allow_partial or is_full_window):
            return (True, running, int(t["ts"]))
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
    unverifiable_writers = []             # writers with no scheduled row to validate against
    excluded_rebuilt = 0
    rebuilt_mismatches = []                # informational only -- never blocks the write
    unfilled_from_unavailable = 0

    for n, wallet in enumerate(roster, 1):
        name = wallet.get("wallet")
        addr = wallet.get("address", "")
        chain = wallet.get("chain", "TRC20")
        key = canonical_address(addr)

        # T anchors this ENTIRE wallet's derivation to one explicit instant. The old
        # code read the current balance, then separately fetched transfers "up to now"
        # -- two DIFFERENT instants, sometimes minutes apart (a slow/chunked transfer
        # fetch, or simply queueing behind other wallets in a ~50-minute run). Any
        # transfer landing in that gap was counted on one side but not the other,
        # silently offsetting EVERY derived date for that wallet by the same constant
        # amount. Proven: "KZO PH SETTLE TRC 1" was off by exactly -4,049.00 on 20+
        # dates spanning January to April -- exactly its own +4,049.00 transfer that
        # landed mid-run. The fix is to pin the transfer fetch to an explicit T, read
        # the balance AFTER that fetch (b2), and correct b2 back to T with a small
        # "tail" fetch covering whatever landed in (T, now]. Both sides then describe
        # the same instant T, instead of two instants that merely happen to be close.
        T = int(time.time() * 1000)

        transfers = svc._fetch_transfers_after(addr, chain, day_boundary_ms(args.start))
        if transfers is None:
            # A very high-volume wallet blows through Tronscan's 10,000-per-query cap in
            # one shot. Fall back to chunked windowed fetching, which slices the window
            # into (by default) day-sized pieces, each far under the cap, and is provably
            # complete per chunk. This path costs minutes instead of seconds, which is why
            # it is only tried after the fast path has already refused -- the other ~69
            # wallets never pay for it.
            #
            # CRITICAL: end_ms is T -- the SAME instant captured above, not a freshly
            # captured "now". The whole point of T is that every path (fast or chunked)
            # anchors to one identical instant, so the later tail correction only has to
            # cover (T, now], never a second, independently-drifting boundary.
            transfers = svc.fetch_transfers_between(
                addr, chain, day_boundary_ms(args.start), T,
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

        # Bound the derivation window to T. The chunked fallback already ends exactly at T,
        # but the fast path (_fetch_transfers_after) fetches to its OWN internal "now",
        # which is strictly after T, so it can include transfers in (T, now]. Those belong
        # ONLY in the tail correction below (current_at_T = b2 - tail_net). Left in the
        # derivation list they would be subtracted a SECOND time inside balances_by_date --
        # they fall after every gap date, so net(after D) would include them even though
        # current_at_T already excludes them -- offsetting every derived date by their net
        # and writing wrong gap rows with no measured row to catch it. Filter to (start, T]
        # (tail is strictly ts > T, so a transfer exactly at T stays here, never double).
        transfers = [t for t in transfers if int(t["ts"]) <= T]

        # b2: the balance, read AFTER the (possibly slow) transfer fetch above -- never
        # before it. Reading it first and reusing that value would reopen exactly the
        # race this whole block exists to close.
        #
        # t_b2 is captured immediately BEFORE the balance read, as a conservative LOWER
        # bound on the instant the returned balance reflects (the node processes the query
        # at or after we send it). The tail correction below is bounded to (T, t_b2], so
        # it only ever removes transfers that unambiguously predate the balance read. The
        # tail fetch itself runs later and would otherwise cover (T, tail_now] with
        # tail_now > t_b2 -- subtracting transfers that landed AFTER b2 was read and were
        # therefore never in b2, offsetting every derived date. Bounding to t_b2 closes
        # that second race to at most the sub-second duration of this one get_balance call.
        t_b2 = int(time.time() * 1000)
        b2 = svc.get_balance(addr, chain)
        if b2 is None:
            missing_days = sum(1 for d in dates if key not in existing.get(d, {}))
            unfilled_from_unavailable += missing_days
            unavailable.append((name, "current balance unavailable", missing_days))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - current balance unavailable "
                  f"({missing_days} wallet-days left unfilled)")
            continue

        # tail: whatever landed in (T, now] -- normally empty or tiny, since T was
        # captured only moments to minutes ago and this query costs one extra small
        # fetch per wallet. A FAILED tail fetch must NOT be treated as "no tail": silently
        # assuming zero would reopen the exact race this fix exists to close and corrupt
        # every date for the wallet the same way the original bug did, so a failure here
        # means the wallet is unavailable, not zero.
        tail = svc._fetch_transfers_after(addr, chain, T)
        if tail is None:
            missing_days = sum(1 for d in dates if key not in existing.get(d, {}))
            unfilled_from_unavailable += missing_days
            unavailable.append((name, "post-fetch tail-correction transfers unavailable "
                                      "-- refusing to guess", missing_days))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - tail-correction fetch "
                  f"unavailable ({missing_days} wallet-days left unfilled)")
            continue

        # Bound the tail to (T, t_b2]: transfers that landed after T but no later than the
        # balance read. _fetch_transfers_after returns (T, tail_now] with tail_now > t_b2,
        # so anything in (t_b2, tail_now] happened AFTER b2 was read, was never in b2, and
        # must NOT be subtracted from it. tail is strictly ts > T already.
        tail = [t for t in tail if int(t["ts"]) <= t_b2]

        # Same signed-net convention balances_by_date uses internally (+received,
        # -sent, canonical_address on both sides) -- imported from balance_history.py
        # rather than reimplemented here, so there is exactly one implementation of it.
        tail_net = signed_net(tail, addr)
        if tail:
            log.info(f"{name}: tail correction, {len(tail)} transfer(s) after T, "
                     f"net={tail_net:+,.2f}")
            print(f"[{n:>3}/{len(roster)}] {name:<28} tail correction: {len(tail)} "
                  f"transfer(s) after T, net={tail_net:+,.2f}")
        current_at_T = b2 - tail_net

        series = balances_by_date(current_at_T, transfers, addr, dates)

        # Does this wallet WRITE any row (a date with no existing row and a usable derived
        # value)? And how many SCHEDULED (measured, non-rebuilt) rows does it have to be
        # validated against? These decide how strictly its disagreements are judged.
        #
        # A wallet that writes gap rows is held to the strictest bar: its derivation must
        # reproduce EVERY scheduled measured row it has, EXACTLY (within 0.01), with no
        # jitter/prefix explanation at all. Gap rows have no measured row to catch an
        # error, so the only thing that earns trust in them is the derivation nailing all
        # the ground-truth rows the wallet does have. Any disagreement -- from a residual
        # sub-second race, an ERC20 second-granular boundary, a constant offset, anything
        # -- means refuse the whole run. The prefix-walk read-instant inference is used
        # ONLY for wallets that write nothing, where a false explain can corrupt no data.
        wallet_writes = any(existing.get(d, {}).get(key) is None and series[d] is not None
                            for d in dates)
        wallet_scheduled = 0
        for d in dates:
            snap_d = existing.get(d, {}).get(key)
            if snap_d is not None:
                rr = row_index.get((d, snap_d["batch_id"], key))
                if rr and len(rr) > 7 and rr[7] == "scheduled":
                    wallet_scheduled += 1
        if wallet_writes and wallet_scheduled == 0:
            # A writer with no scheduled row cannot be validated at all: nothing catches a
            # bad derivation. Refuse rather than write unvalidated gap rows.
            n_gap = sum(1 for d in dates
                        if existing.get(d, {}).get(key) is None and series[d] is not None)
            unverifiable_writers.append((name, n_gap))
            print(f"[{n:>3}/{len(roster)}] {name:<28} SKIPPED - writes rows but has no "
                  f"scheduled measured row to validate against")
            continue

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
                elif derived is not None and wallet_writes:
                    # STRICT bar for writers: this scheduled row is ground truth and the
                    # derivation did not reproduce it exactly. Because this wallet writes
                    # gap rows that have no measured row to catch an error, we do NOT try
                    # to explain the disagreement away -- any mismatch on a ground-truth
                    # row means the derivation is off, so refuse the whole run. This closes
                    # every residual-timing / boundary / offset path in one rule: an offset
                    # that reached the gap rows would necessarily show up here too.
                    disagree.append((name, d, saved, derived))
                elif derived is not None:
                    # Non-writing wallet: this disagreement is only a confidence signal on
                    # a row that already exists and is never touched. The daily report's
                    # row Time is the WRITE instant, not the READ instant, so a transfer in
                    # that read->write gap sits inside (00:00:00, Time] but was not in the
                    # read that produced `saved`. Search for the wallet's own true read
                    # instant -- the prefix of its transfers whose running net reconciles
                    # derived and saved EXACTLY. A false explain here can corrupt no written
                    # data, so the prefix relaxation is safe.
                    time_str = snap.get("time") or "00:00:00"
                    ok_expl, window_net, fetch_ms = disagreement_explained(
                        transfers, addr, d, time_str, saved, derived, allow_partial=True)
                    if ok_expl:
                        explained.append((name, d, saved, derived, time_str, window_net, fetch_ms))
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
    print(f"explained       : {len(explained):,} disagreements explained by the wallet's "
          f"own true read instant, inferred from its transfers (report only, does not "
          f"block the write)")
    for name, d, saved, derived, time_str, window_net, fetch_ms in explained[:20]:
        fetch_str = _fmt_gmt7(fetch_ms) if fetch_ms is not None else "?"
        print(f"    {name:<26} {d}  saved={saved:,.2f}  derived={derived:,.2f}  "
              f"row_time={time_str}  inferred_fetch={fetch_str}  window_net={window_net:+,.2f}")
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
    print(f"unverifiable    : {len(unverifiable_writers)} writers had gap rows but no "
          f"scheduled measured row to validate against (their gaps are NOT written)")
    for name, n_gap in unverifiable_writers[:20]:
        print(f"    {name:<26} {n_gap} gap rows withheld")
    print(f"rows to write   : {total:,} across {len(to_write)} dates")

    if disagree:
        sys.exit("\nREFUSING TO WRITE: the derivation disagrees with a scheduled row that "
                 "was measured on the day. Investigate before backfilling.")

    if unverifiable_writers:
        sys.exit("\nREFUSING TO WRITE: one or more wallets would write gap rows but have "
                 "no scheduled measured row to validate the derivation against. Refusing "
                 "to write unvalidated data.")

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
