"""Calendar semantics of the balance vault. Pure -- no network, no sheet access.

The vault stores exactly one figure per wallet per date: the balance at 00:00 GMT+7
that morning (VAULT_DAY_BOUNDARY in google_sheets_logger). Everything here follows from
that single fact.
"""
from datetime import datetime, timedelta

from bot.services.chain_detector import canonical_address

OPENING = "opening"
CLOSING = "closing"


def target_date_for(date_str, mode):
    """The vault date holding the requested figure for `date_str`.

    opening(D) is the row dated D -- the balance at 00:00 GMT+7 that morning.
    closing(D) is the balance at the END of D. The end of D is the same instant as
    00:00 GMT+7 on D+1, so it is the row dated D+1. No separate figure is stored or
    needed for a closing balance.
    """
    if mode == OPENING:
        return date_str
    if mode != CLOSING:
        raise ValueError(f"unknown balance basis {mode!r}; expected {OPENING!r} or {CLOSING!r}")
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def _iso_prefix(value):
    """The YYYY-MM-DD prefix of `value`, or None if it is absent or not a real date."""
    if not value:
        return None
    prefix = str(value)[:10]
    try:
        datetime.strptime(prefix, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return prefix


def build_first_seen(roster, rows):
    """Earliest date each wallet is known to have existed, keyed by canonical address.

        first_seen = min( created_at when present , earliest vault row for that wallet )

    Why not created_at alone -- both failure modes are real, measured on the live data:

      1. 27 of 71 wallets have no created_at at all. Treating that as "always existed"
         made 44 of 313 dates look gappy and provoked reconstruction of wallets that
         were never monitored then. All 27 have vault rows, so all 27 are inferable.
      2. created_at is sometimes LATER than data already held. KZDW DPP TH 2 records
         2026-01-15 against a measured row from 2025-12-17. Trusting created_at alone
         would hide a wallet on a date whose balance is sitting in the sheet.

    Taking the minimum keeps created_at as the primary signal while never contradicting
    recorded evidence: a wallet holding a row on D necessarily has first_seen <= D,
    because first_seen includes that row's own date.

    Note that this inequality is NOT what protects a saved balance from being excluded.
    Callers apply a STRICT test (first_seen < D), because a row dated D is the balance at
    D 00:00 GMT+7 and a wallet created during D did not exist at that instant. What
    actually guarantees a saved balance is always counted is the ORDER in
    CheckHandler.classify_wallets: it consults the snapshot first and only asks about
    existence when no row was found. Reversing that order would silently drop a wallet
    that has a real recorded balance.

    Returns None for a wallet with neither signal; callers treat that as "assume it
    existed", which is the safe direction and matches the previous behaviour.
    """
    earliest = {}
    for r in rows or []:
        if len(r) < 6:
            continue
        date = _iso_prefix(r[1])
        key = canonical_address(r[5])
        if not date or not key:
            continue
        if key not in earliest or date < earliest[key]:
            earliest[key] = date

    out = {}
    for w in roster:
        key = canonical_address(w.get("address", ""))
        if not key:
            continue
        candidates = [c for c in (_iso_prefix(w.get("created_at")), earliest.get(key)) if c]
        out[key] = min(candidates) if candidates else None
    return out
