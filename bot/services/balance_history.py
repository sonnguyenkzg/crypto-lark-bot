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


def signed_net(transfers, address):
    """Signed net of `address`'s successful transfers: +received, -sent, addresses
    compared through canonical_address. Same delta convention `balances_by_date` uses
    internally (see its per-transfer `delta` below), factored out here so any OTHER
    caller needing a net over a transfer list -- e.g. correcting a balance reading back
    to an earlier instant using a short "tail" of transfers -- does not duplicate it
    with a second, potentially-drifting implementation. Purely additive: does not
    change `balances_by_date` itself.
    """
    me = canonical_address(address)
    net = Decimal(0)
    for t in transfers or []:
        if not t.get("success", True):
            continue
        amount = t["amount"]
        if canonical_address(t.get("to", "")) == me:
            net += amount
        if canonical_address(t.get("from", "")) == me:
            net -= amount
    return net


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
