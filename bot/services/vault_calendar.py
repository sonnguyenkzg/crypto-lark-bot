"""Calendar semantics of the balance vault. Pure -- no network, no sheet access.

The vault stores exactly one figure per wallet per date: the balance at 00:00 GMT+7
that morning (VAULT_DAY_BOUNDARY in google_sheets_logger). Everything here follows from
that single fact.
"""
from datetime import datetime, timedelta

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
