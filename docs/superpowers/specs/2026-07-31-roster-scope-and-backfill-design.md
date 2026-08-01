# Design — `wallets.json` is the only scope, plus a one-time backfill

**Date:** 2026-07-31
**Status:** approved in brainstorming, pending spec review
**Baseline:** prod and `origin/main` at `c1afc8f`

---

## 1. The problem, in one line

`/check [date]` hides money that existed.

A wallet added to `wallets.json` after a given date is currently reported as *"added on or after this
date, so no balance yet"* — even when the address demonstrably held USDT on that date. Measured
against the live chain:

| | |
|---|---|
| Wallets that joined monitoring later | 52 |
| **Of those, holding USDT the day before they joined** | **31** |
| Combined hidden balance at their join dates | **20,184,069.03 USDT** |

Largest cases: `OKKZ5A` held 2,350,006.97 the day before it joined on 2026-05-18; `S5 KZWL TRC20`
held 1,718,009.94 before joining on 2025-10-11.

The bot was answering *"what was our monitored set worth?"*. It should answer *"what did the company
hold?"*.

---

## 2. The rule

```
scope       = every wallet in wallets.json that EXISTED on the date.
saved row?  -> use it
no row, and it existed?      -> reconstruct from the chain, show it, save it "rebuilt"
no row, and it did not exist -> "added on or after this date", not counted
```

**Existence is on-chain creation, not the wallets.json add-date and not `created_at`.** A wallet is
counted from the first date it ever held a POSITIVE balance in the vault (`first_funded`). That keeps
both truths:

- **Money held before monitoring is still shown.** `OKKZ5A` held ~2.35M before it was added; hiding
  it understated the total. It has a positive balance from its real funding date, so it counts.
- **A wallet has no balance before it was funded.** A wallet created on day T genuinely had nothing on
  T−1, so a date before its `first_funded` is reported "added on or after this date" — not a fictitious
  `0.00` for a day it did not exist.

> **Amendment (2026-08-01).** An earlier draft of this rule said "when a wallet was added is never
> consulted; a non-existent wallet reconstructs to `0.00`." That hid the opposite error — inventing a
> zero for a day a wallet did not exist. The rule above supersedes it. Existence uses `first_funded`
> (earliest positive vault balance), never `created_at` (unreliable in both directions). It is trusted
> only on/after `coverage_start` = `max(earliest vault row, VAULT_COMPLETE_FROM)`, the date the vault
> is verified-complete. `VAULT_COMPLETE_FROM = 2026-01-01` is the backfill floor; the vault also holds
> *sparse* scheduled rows back to ~2025-09-22, where a funded wallet may simply be unrecorded, so its
> `first_funded` would read later than its true creation. Claiming "added on or after" there would hide
> money — so below `coverage_start` we reconstruct instead (showing the true balance, or an honest
> `0.00` for a genuine pre-monitoring date). All date comparisons go through `normalize_iso_date`, so a
> non-zero-padded cell can never sort a real balance as "before it existed" and hide it.

---

## 3. One-time backfill

Reconstructing on demand would make the first check of an old date slow. Instead the history is
filled in once, up front.

**Window: 2026-01-01 → 2026-07-30** (the last date before today; today's own row is written by the
daily report at 00:01 GMT+7 and needs no backfill). Earlier dates are left alone; they still work,
they are just slower on first use.

| | |
|---|---|
| Calendar days in window | 212 |
| Wallets | 71 |
| Wallet-days in window | 15,052 |
| Already present | 11,973 |
| **To backfill** | **3,079** |

### The method matters more than the scope

Reconstructing each wallet-day independently means re-fetching the same transfer history 212 times
per wallet — about 2.2 hours at the measured rate of ~2.6s per wallet-day.

Instead, fetch each wallet's history **once** and derive every date from it:

```
for each wallet:
    B    = current balance                          (1 request)
    T    = all transfers since 2026-01-01           (1 paginated fetch)
    then, walking backwards from today:
        balance_at(D) = B - net(transfers after D)   pure arithmetic, no further requests
```

**71 fetches instead of 3,079 reconstructions.** Minutes rather than hours, and far gentler on the
provider rate limits.

This requires one small addition: `_fetch_transfers_after` currently discards each transfer's
timestamp during normalisation. It must keep it (`ts`), so transfers can be bucketed by date. The
change is additive — existing consumers ignore the extra key.

### Execution

- Runs as a **standalone script**, not through the bot, so it cannot hold the command lock or delay a
  `/check`.
- Runs **locally**, writing to the shared Google Sheet — the only data store. Local execution means
  it can be watched and stopped instantly.
- **Must not overlap the 17:00 UTC daily report.** The script stops cleanly if it approaches that
  time, and resumes later.
- **Dry run first**: prints exactly what it would write, writes nothing, and is reviewed before any
  real run.
- Rows are written with `Check Type = "rebuilt"`, so a reconstructed figure is always
  distinguishable from one measured on the day.
- **Idempotent**: a wallet-day that already has a row is skipped, never duplicated.

---

### Order of work: backfill first, deploy second

`classify_wallets` consults the snapshot **before** it asks whether a wallet existed:

```python
entry = snapshot.get(key)
if entry:                       # a saved row always wins
    status = "saved"
elif self._existed_on(...):     # existence is only consulted when there is NO row
```

So **a backfilled row displays correctly on the code already running in production.** That makes the
safe order:

1. **Backfill** — data only, no deploy, no code risk. Verify in Lark against the current prod bot.
2. **Then the code change** — which matters for dates outside the backfill window, and for wallets
   added to `wallets.json` in future.

If the backfill turns out to be wrong, nothing has been deployed and the fix is a data correction.
If it is right, the code change ships against a vault that is already complete.

---

## 4. How existence is decided

Existence is derived from the vault itself, not from a stored per-wallet field, so nothing has to be
kept in sync:

| Signal | Source |
|---|---|
| `first_funded[addr]` — earliest positive vault balance (a wallet's creation) | `_first_funded_from_rows`, computed in `get_history_bundle` from the one DAILY_REPORT read |
| `coverage_start` — earliest date `first_funded` may be trusted = `max(earliest row, VAULT_COMPLETE_FROM)` | `get_history_bundle`, same read |
| `not_yet_created` status + "added on or after this date" card line | `classify_wallets`, only when `coverage_start <= date < first_funded[addr]` |

`created_at` in `wallets.json` is never consulted (unreliable: sometimes stamped after real funding,
which would hide money; sometimes before, which would invent a zero). `first_seen` / `build_first_seen`
from earlier drafts stay removed — existence is now `first_funded`, recomputed each read.

`target_date_for`, the `[o]`/`[c]` grammar, the filters and the bracket parsing are all untouched.

Every wallet ends in one of four states: `saved`, `rebuilt`, `unavailable` (reconstruction failed, no
figure claimed), or `not_yet_created` (did not exist on the date; shown but not counted).

---

## 5. The card

```
📊 Total wallets in monitoring: 71
• 39 have a balance recorded for this date
• 1 was calculated from blockchain records
• 31 wallets were added on or after this date, so they had no balance yet
➡️ 40 wallets counted in the total below
```

(Real figures for `/check [2026-01-01]`.) Every line adds up to the roster: `saved + rebuilt +
not_yet_created + failed = 71`, so the counted total is never a number the reader has to work
backwards to. A wallet that genuinely reconstructs to `0.00` (existed, held nothing) still appears
in the list and counts; only wallets that did not yet exist are set aside as "added on or after".

If a reconstruction fails, that wallet is listed as **unavailable** and excluded from the total, with
the count saying so — never silently counted as zero.

---

## 6. Risks, stated plainly

**Historical totals will rise, materially.** That is the point of the change, but it means a figure
quoted from an old `/check` will no longer match a new one. The daily report that actually went out
on an old date covered fewer wallets; after backfill the sheet shows the full roster. Rebuilt rows
are labelled, so the difference stays visible to anyone auditing.

**Some wallets may come back "unavailable".** Reconstruction needs every transfer since the cutoff.
For a long window a busy wallet can exceed the page cap or the deadline. The existing code already
fails safe — it returns `None` and the wallet is reported as unavailable rather than guessed. The
pre-monitoring audit hit this once in 52 wallets (`KZDW DPP TH 2`).

**The backfill and the bot share provider rate limits.** They run on different machines, so the
process-wide rate gate does not span both. Mitigated by running outside the daily-report window and
by keeping the backfill's own concurrency low.

**A wrong reconstruction would be saved permanently.** Mitigated by the dry run, by the existing
negative-balance guard (a negative result is rejected, never saved), and by spot-checking backfilled
figures against dates that already have measured rows — a backfilled value for a date that also has
a measured row must match it.

---

## 7. Verification

- **Agreement check**: for wallet-days that already have a measured row, the backfill's computed
  value must equal it. Any disagreement stops the run.
- **Coverage check**: after the run, every date from 2026-01-01 to 2026-07-30 holds exactly 71
  wallets. (A wallet added to `wallets.json` later would make this 72 and reopen a gap; that is
  correct and self-healing — `/check` reconstructs the newcomer on demand and saves it.)
- **No duplicates**: row count rises by exactly the number of gaps filled, 3,079.
- **Spot check in Lark**: `/check` on a backfilled date returns 71 wallets and reconciles.
- The full unit suite (211 tests) must still pass, minus the tests deleted with `build_first_seen`.

---

## 8. Out of scope

Dates before 2026-01-01 (they still work, just slower on first use), the live `/check`, the daily
report itself, `/add`, `/remove`, `/list`, and USDC / multi-token support.
