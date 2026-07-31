# Design — opening/closing balances for `/check [date]`

**Date:** 2026-07-31
**Status:** approved in brainstorming, pending spec review
**Baseline:** prod runs `adc6cdc`

---

## 1. What ships

Three changes to `/check`:

1. **Opening vs closing selection.** `/check [D]` returns the day's **closing** balance. `[o]`
   returns the opening. `[c]` returns the closing explicitly.
2. **Flexible bracket spacing.** `[a][b]` and `[a]  [b]` behave identically.
3. **A corrected wallet-existence rule.** A wallet counts on date D only if it existed by D, and
   "existed" is now derived from the best evidence available rather than from `created_at` alone.

Items 1 and 3 change numbers that users already see. Item 2 already works.

---

## 2. Semantics

```
opening(D) = the balance at D 00:00 GMT+7        = the vault row dated D
closing(D) = the balance at the end of D
           = the balance at D+1 00:00 GMT+7      = the vault row dated D+1
```

The vault already holds both figures. Nothing new is measured, and no new blockchain call is
introduced by this feature.

This rests on the boundary fixed on 2026-07-30: `VAULT_DAY_BOUNDARY = "00:00:00"` GMT+7, used for
both the reconstruction cutoff and the Time column of a rebuilt row.

**Known imprecision, inherited not introduced:** the scheduled daily report lands at 00:00:31 to
00:01:35 GMT+7, not exactly 00:00:00. A measured row is therefore up to ~95 seconds after the true
boundary. Reconstructed rows are exact. This predates the feature and is unchanged by it.

---

## 3. Resolution — a date translation in front of existing machinery

```
mode        = closing (default) | opening
target_date = D            when mode is opening
              D + 1 day    when mode is closing

then: run the existing dated-check pipeline against target_date, unchanged
```

The existing pipeline already does snapshot lookup, per-wallet classification
(`saved` / `needs_rebuild` / `not_yet_created`), reconstruction at `target_date 00:00:00 GMT+7`, and
write-back of rebuilt figures. None of it changes.

Worked example against live data:

| Command | target_date | Result |
|---|---|---|
| `/check [2026-07-15]` | 2026-07-16 | 13,896,104.81 (closing) |
| `/check [2026-07-15][o]` | 2026-07-15 | 13,766,045.97 (opening) |
| `/check [2026-07-15][c]` | 2026-07-16 | 13,896,104.81 (closing) |

### Write-back lands on target_date, not on D

If `target_date` has missing wallets, the reconstruction saves rows dated `target_date`. For a
closing query that is the day *after* the one the user typed.

Real example: before the hole was filled, 2026-07-20 had no rows. `/check [2026-07-19]` (closing)
would have reconstructed and saved 70 rows dated **2026-07-20**, not 2026-07-19. The figure is
correct; only its location in the sheet is surprising. **The card must therefore name the date it
read and the date it wrote.**

How often this fires, measured against the live vault **under the corrected existence rule of §5**:
18 of 313 dates have a wallet that existed but has no row. Under today's rule it would be 44. The
most recent seven days are complete, so ordinary day-to-day use is a pure read.

---

## 4. Parsing

### Modifier extraction

Modifier tokens are removed from the token list **before** group/name classification.

| Token (case-insensitive) | Meaning |
|---|---|
| `o`, `opening` | opening |
| `c`, `closing` | closing |

Position-independent: `[D][c][KZP]` and `[D][KZP][c]` are equivalent.

**Deliberately excluded:** `open` and `close`. Both currently resolve to real wallets through fuzzy
matching (`open` → `KZO PEN SETTLE TRC 1` by "contains"; `close` → `KZO SETTLE OPS TRC 1` by closest
match). They keep filtering, unchanged.

**Accepted cost:** `[o]` and `[c]` stop working as filters. Today `[o]` returns the ten `OKKZ`
wallets by prefix and `[c]` returns the `KZO COY` wallets by "contains". Users wanting those type
`[OKKZ]` and `[KZO COY]`, which is already the normal usage.

Verified against the live roster: no wallet is named exactly `o`, `c`, `opening` or `closing`, and
none of the 13 group codes (`DPP, KZDW, KZG, KZO, KZP, OKKZ, OKKZ1A-5A, S5, S5A`) collides.

### Filters — unchanged

Everything remaining after modifier extraction goes through `classify_tokens` exactly as today:
group codes and wallet names, any number of them, intersected, with the existing tiered matching
(exact → starts-with → contains → all-words → closest match).

### Spacing — already correct

`parse_arguments` joins `context.args` with spaces and scans for `[...]` with a regex, so adjacency
never mattered. Confirmed working today for `[a][b]`, `[a] [b]`, `[a]  [b]   [c]`. This spec adds
tests to prevent a regression; no code change.

---

## 5. Wallet-existence rule

### The rule

```
existed_on(D) = first_seen < D
first_seen    = min( created_at (when present), earliest vault row for that wallet )
```

**Strictly earlier, not on-or-before.** A row dated D holds the balance at 00:00 GMT+7 on D. A
wallet created *during* D did not exist at that instant — its first real balance is at 00:00 on
D+1, which is exactly where its first vault row already sits. With `<=`, such a wallet is judged
"existed on D but has no row", so the bot reconstructs a 00:00 figure for it and saves it: a number
for a moment when nobody was monitoring the wallet.

Measured on the live vault, **every one** of the 40 remaining rebuild wallet-days, across 18 dates,
is a same-day creation. `<` takes them to zero. Example: `KZDW FIN OPS TRC 1`, `created_at`
2026-07-16 with no row for that date, is today rebuilt and saved for 2026-07-16; it should be
reported as added after that date.

This also makes the data self-consistent: under `<`, closing of 2026-07-15 (which reads 2026-07-16)
resolves to 69 clean saved rows totalling exactly 13,896,104.81, with no rebuild and no write.

The guarantee below is unaffected: a wallet holding a row on D is still always counted, because the
snapshot is consulted before this test is ever reached.

A wallet not yet in existence on `target_date` is excluded from the total and reported as
"added after this date", exactly as today — the change is only in how the date is decided.

### Why not `created_at` alone

- **27 of 71 wallets have no `created_at`.** Today the code treats a missing value as "always
  existed" (the safe direction), which makes old dates look gappy and provokes reconstruction of
  wallets that were not being monitored. All 27 have a first vault row, so all 27 are inferable.
- **`created_at` is sometimes later than data we already hold.** `KZDW DPP TH 2` records
  `created_at = 2026-01-15` but has a measured row from 2025-12-17; `KZDW DPP BDT 1` records
  2026-01-15 against a first row of 2026-01-02. Trusting `created_at` alone would hide a wallet on a
  date where its measured balance is sitting in the sheet.

Taking the minimum uses the created date as the primary signal while never contradicting recorded
evidence.

### Guarantee

A wallet holding a row on D necessarily has `first_seen <= D`, because `first_seen` includes that
row's date. **No saved balance can ever be excluded by this rule.**

### Measured effect

| | Before | After |
|---|---|---|
| Dates where a wallet existed but has no row (triggers rebuild) | 44 of 313 | **0 of 313** |
| Rebuild wallet-days | 40 | **0** |
| Wallets with a usable start date | 44 of 71 | **71 of 71** |
| Wallets becoming visible earlier | — | 2 |

With both refinements — deriving `first_seen`, and requiring it to be strictly earlier than the
date — the vault is effectively complete: no dated check needs to reconstruct anything for the
wallets and dates currently present. Every apparent "gap" was either a wallet with no recorded
start date, or a wallet created on the day itself.

Totals for older dates will fall, because wallets previously reconstructed-and-counted are now
correctly excluded as not-yet-existing. This is the intended effect, and it means an old `/check`
result will not match a new one for those dates.

### Where `first_seen` comes from

The snapshot read already pulls all `DAILY_REPORT` rows, so the earliest date per wallet is computed
from data already in memory. No extra sheet read.

---

## 6. Guards and errors

| Condition | Behaviour |
|---|---|
| `target_date` is in the future — i.e. closing of today | **Day Not Finished Yet** card, pointing the user to `[o]` for the opening, since that is the only figure that exists for today |
| Both an opening and a closing modifier given | Error card: pick one |
| The same modifier repeated, e.g. `[o][o]` or `[o][opening]` | Accepted, treated as one. Repetition is not a contradiction |
| A modifier with **no date**, e.g. `/check [o]` or `/check [c][KZP]` | Error card. Opening and closing are properties of a day, so they are meaningless for the live check. The card says a date is required and shows the correct form. Without this the token would fall through to the filter and match wallets by fuzzy prefix — silently returning OKKZ wallets for `[o]` |
| `D` itself invalid or in the future | Existing guards, unchanged |
| Sheet read fails | Existing abort-with-error-card behaviour, unchanged |

Closing of *yesterday* is always available: its target is today, whose row was written at ~00:01
GMT+7 this morning.

---

## 7. Card

The card must make three things unambiguous:

1. **Which basis** — the header states "Closing balance" or "Opening balance".
2. **Which instant** — one line spelling out the translation, e.g. "Closing of 2026-07-15 = the
   balance at 00:00 GMT+7 on 2026-07-16", so the figure can be reconciled against the sheet.
3. **What was written** — when a reconstruction occurred, the card names `target_date` as the date
   saved.

Everything else keeps the wording settled on 2026-07-30: wallet name before status, bold names, no
backticks, "Total wallets in monitoring: 71", scope limited to `wallets.json`.

**New:** the "added after this date" list is capped. Five or fewer wallets are named as today; more
than five shows a count instead, worded plainly — "**41 wallets** were added after this date, so they
have no balance yet". Without this, an old date would name roughly forty wallets. Either way the
arithmetic must still reconcile: counted + added-later = total wallets in monitoring.

---

## 8. What changes for existing users

| Change | Effect |
|---|---|
| `/check [D]` now means closing | Every bare dated check returns a different number. `/check [2026-07-15]` goes from 13,766,045.97 to 13,896,104.81, +130,058.84 |
| `[o]` and `[c]` stop filtering | `[o]` no longer returns the ten OKKZ wallets; `[c]` no longer returns the KZO COY wallets |
| Existence rule | Totals fall on older dates where non-existent wallets were being reconstructed and counted |

`/help` must be updated to teach the new grammar, and these three changes announced to users.

---

## 9. Out of scope

Live `/check` with no date (still current balances, still writes to the `CHECK` tab), `/add`,
`/remove`, `/list`, the daily report, and USDC / multi-token support.

---

## 10. Testing

- Date translation: opening → D, closing → D+1, across month and year boundaries.
- Modifier extraction: every accepted spelling, both cases, every position, and the both-given error.
- Regression guard: `[open]` and `[close]` still reach the filter and still match their wallets.
- Bracket spacing: `[a][b]`, `[a] [b]`, `[a]  [b]   [c]` all produce identical tokens.
- Closing-of-today refused; closing-of-yesterday allowed.
- Existence rule: `first_seen` from `created_at` only, from vault only, from both (minimum wins),
  and the guarantee that a wallet with a row on D is never excluded.
- End-to-end against real data: `closing(2026-07-15) == opening(2026-07-16) == 13,896,104.81`.
- The full existing suite (134) must still pass.

---

## 11. Rollout

The proven path, unchanged: feature branch → full suite green → fast-forward `main` → prod
`git pull` → `./start_lark_bot.sh restart` → verify from a fresh ssh connection that all four python
processes started after the commit.

No files are edited on the production box; that would put prod out of sync with git.

Rollback is `git reset --hard adc6cdc && ./start_lark_bot.sh restart`.

Because the reported figures change, deploy is followed by a short announcement to users rather than
a silent cutover.
