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


def test_a_full_212_day_window_is_correct_end_to_end():
    """The real backfill shape: 212 dates, many transfers, one call."""
    txs = [tx("2026-03-10", 1, to=ME) for _ in range(50)]
    dates = [(datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(212)]
    out = balances_by_date(Decimal("50"), txs, ME, dates)
    assert len(out) == 212
    assert out["2026-01-01"] == Decimal("0"), "before the transfers"
    assert out["2026-03-10"] == Decimal("0"), "00:00 that day, transfers land at 12:00"
    assert out["2026-03-11"] == Decimal("50"), "after the transfers"
    assert out[dates[-1]] == Decimal("50"), "the far end of the window"


def test_each_transfer_is_examined_once_across_the_whole_series():
    """Efficiency is the REASON this function exists, so prove it rather than assume it.

    Counts how many times the transfer list is read by making `amount` observable.
    A per-date implementation would touch each transfer once PER DATE.
    """
    class CountingDecimal(Decimal):
        reads = 0
        def __radd__(self, other):
            type(self).reads += 1
            return Decimal(self) + other
        def __rsub__(self, other):
            type(self).reads += 1
            return other - Decimal(self)

    txs = []
    for _ in range(10):
        t = tx("2026-03-10", 1, to=ME)
        t["amount"] = CountingDecimal("1")
        txs.append(t)
    dates = [(datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(212)]
    CountingDecimal.reads = 0
    balances_by_date(Decimal("10"), txs, ME, dates)
    assert CountingDecimal.reads <= 10, (
        f"each of the 10 transfers must be summed once, not once per date; "
        f"got {CountingDecimal.reads} reads across {len(dates)} dates")
