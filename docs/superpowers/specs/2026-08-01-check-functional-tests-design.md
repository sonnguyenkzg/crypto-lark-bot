# /check functional test suite — design

**Goal.** A committed, hermetic, functional test suite that drives the *whole* `/check [date]`
command and asserts on the rendered card, so the creation-based existence rule has reliable,
repeatable regression coverage — not one-off scratchpad runs.

**Why it's needed.** Unit tests cover `classify_wallets` and `get_history_bundle` in isolation; the
only end-to-end proof so far lived in throwaway scripts (one of which flaked on a live rate limit).
Nothing in `pytest` exercises parse → bundle → classify → rebuild → card as one flow for the creation
rule.

## Approach

Reuse the existing functional pattern in `tests/test_check_open_close.py` (`Topic` captures cards,
`Ctx` fakes the context, `run(handler, args)` drives `handle()`), and patch only the three external
boundaries so the test is deterministic and does no I/O:

| Boundary | Patched to | Purpose |
|---|---|---|
| `GoogleSheetsBalanceLogger._read_daily_report_rows` | fixed synthetic rows | the REAL `get_history_bundle` computes `first_funded`, `coverage_start`, snapshot from them |
| `BalanceService.get_balance_at` | deterministic per-address value | reconstruction runs without network |
| `GoogleSheetsBalanceLogger.save_rebuilt_balances` | no-op recorder | zero writes (also guarded by `test_no_production_writes.py`) |

Nothing between parse and card is stubbed, so this is a true functional test, not a re-test of
`classify_wallets`.

**Fixture.** One small synthetic roster (~5 TRC20 wallets) with controlled funding dates and a
`_read_daily_report_rows` builder, so every scenario is readable and self-contained. `VAULT_COMPLETE_FROM`
is `2026-01-01`; fixtures place `coverage_start` accordingly.

## Scenarios (each asserts on rendered card text)

1. **Fully-saved opening date** — existing wallets saved, later wallets absent → card shows "N have a
   balance recorded", "M … added on or after this date", and `saved + not_yet == roster`.
2. **not-yet-created naming** — ≤6 such wallets → names listed; >6 → summarized as a count.
3. **Money before monitoring** — a wallet whose `first_funded` precedes the queried date is counted,
   never "added later".
4. **Pre-`coverage_start` date** — a wallet with no row on a date below the floor **reconstructs**
   (needs_rebuild → rebuilt via the stubbed `get_balance_at`), is NOT `not_yet_created`; nothing hidden.
5. **In-window gap wallet** — existed (date ≥ `first_funded`) but no saved row → reconstructs, shown as
   "calculated from blockchain records".
6. **Malformed sheet date** — a non-zero-padded cell (`2026-7-05`) still matches its calendar date; the
   saved balance is found, not hidden.
7. **Filtered query** — `[company]` filter → "Wallets in scope: X of ROSTER" and correct reconciliation.
8. **Closing vs opening** — `[c]` reads the D+1 vault row, `[o]` reads D (both via `target_date_for`).
9. **Sheet read failure** — `_read_daily_report_rows` returns None → "unavailable" card, **no rebuild,
   no write** (recorder stays empty).

## Reliability method (TDD)

Each scenario is written against the real handler and must pass. For the load-bearing invariants
(no money hidden #3/#4, reconciliation #1, no-write #9), prove the test is meaningful with a red→green
mutation: break the relevant code, confirm the test fails, restore, confirm it passes. A test that
cannot fail is not evidence.

## Out of scope

Bad-date / future-date / modifier-without-date rejection (already covered by `test_check_open_close.py`);
live sheet or prod runs (this suite is hermetic by design).

## Verification

`.venv/bin/python -m pytest tests/ -q` green, then an independent Codex review of the test file's logic
(does any assertion pass vacuously? can a real regression slip through?).
