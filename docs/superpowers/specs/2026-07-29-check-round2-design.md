# Design — `/check [date]` round 2, `/remove` bracket fix, fuzzy matching

**Date:** 2026-07-29
**Status:** Approved (brainstorm), pending spec review
**Driver:** Son's live dev test notes in `DEV_TEST_PLAN.md` (marked `SONNQ`) + updated `request.txt`.

---

## 1. What this fixes

Round 1 shipped `/check [date]` and a `/remove` address fix. Live testing found six issues:

| # | Found in | Problem | Verified |
|---|---|---|---|
| 1 | G1–G3 | `/remove [address]` fails with *"Expected 1 quoted argument, found 0"* — `/remove` never got the bracket parser that `/add` and `/check` got | Yes — `remove_handler` still uses its own quotes-only `extract_quoted_strings` |
| 2 | C1, C2 | Fuzzy too loose: `"DPP COY"` → `DPP COY TRC, KZP COY, KZP COY 2` | Yes — reproduced |
| 3 | D2 | Wallet counts inconsistent and unexplained: `wallets.json` = 71, existed-by-07-15 = 68, saved 07-15 record = 69 | Yes — 3 wallets added after 07-15; `Cold wallet` is in the record but no longer in the list |
| 4 | D1 | The first card doesn't confirm what the bot understood | — |
| 5 | F1 | Historical card lacks the Time / total / logged footer the live card has | — |
| 6 | C3, E1 | Not-found wording; backtick example renders awkwardly | — |

**Also (`request.txt`):** reproduce the original `/remove` bug as a test case, using
`0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071`. `"Cold wallet"` no longer exists, so the
reproduction must **add** a test wallet first — hence `/add` coverage too.

---

## 2. Wallet-level resolution (replaces the date-level branch)

Today the code branches per *date*: "snapshot exists → read it" **or** "no snapshot → rebuild
everything". That binary is why counts differ between dates and why a partial day is awkward.

**New model: resolve each wallet independently.** The wallet set is
**`wallets.json` (the single source of truth)** plus any wallet that has a saved figure for that
date but is no longer listed.

| Wallet's situation on the requested date | Shown as | In total | Saved back |
|---|---|---|---|
| Has a saved figure | the figure | ✅ | — (already saved) |
| No saved figure, existed by then | rebuilt from chain | ✅ | ✅ yes |
| Created after that date | `—  (added 2026-07-24)` | ❌ | no |
| Not in `wallets.json` but has a saved figure | the figure, `(no longer in your list)` | ✅ | — |
| Rebuild failed | `—  (could not be worked out)` | ❌ | no |

**Self-completing history.** Every newly rebuilt figure is appended to `DAILY_REPORT`
(`Check Type = rebuilt`). A partial rebuild is saved as far as it got; the next check of that date
reads what exists and rebuilds **only the still-missing wallets**. A date therefore fills itself in
over time and can never be locked into a permanently understated total.

**Ordering guarantee:** a wallet is only ever rebuilt when no saved figure exists for it, so
rebuilding never overwrites a real measurement.

> **Accepted consequence:** rebuilt rows are written to the **shared** Google Sheet, which dev and
> prod both use. This is intended — it fills real gaps in real history — but it means dev testing
> is no longer read-only. Rows are marked `rebuilt` so they are distinguishable from measured ones.

---

## 3. Fuzzy matching

Order of resolution, with spacing and punctuation ignored throughout
(`KZP96G1` and `KZDW DPP TH2` therefore resolve **exactly**):

1. **Exact** (ignoring case/spacing/punctuation)
2. **Starts with** → return **all** matches
3. **Contains** → return **all** matches
4. **All words present** (any order) → return **all** matches
5. **Closest match** — similarity ≥ 0.6, ranked best-first, **max 3**, labelled as a guess
6. Nothing → `Wallet "X" not found.`

Steps 2–4 return every match because each is a genuine hit — truncating could hide a wallet.
Only step 5 is capped, because those are inferences.

Similarity is the best of four measures: the query vs the name, and the query vs the name's
same-length start, each computed on both the spaced and the squashed form. The head comparison is
what rescues short typo'd queries (`DPY CYO`), and the squashed form is what makes spacing
irrelevant.

**Measured** over 483 generated typos across all 71 real wallet names:

| Typo type | Right one first | Right one found |
|---|--:|--:|
| Missing spaces | 100% | 100% |
| Wrong case | 100% | 100% |
| Swapped letters | 95.6% | 100% |
| Dropped letter | 95.8% | 98.6% |
| Wrong letter | 94.4% | 98.6% |
| Half a name | 57%¹ | 100% |
| Dropped last word | 80% | 98.5% |
| **Overall** | **89.0%** | **99.4%** |
| Nonsense (`ZZZ QQQ`, `12345`, …) wrongly matched | — | **0** |

¹ Typing `OKKZ` legitimately matches ten wallets; "first" is not meaningful, and all ten are shown.

---

## 4. Cards

### 4.1 Acknowledgement (sent immediately)
Echoes what was understood, so a mistyped filter is obvious before any waiting:
```
🔄 Checking Balances...
📅 Date: 2026-07-20
🏢 Company: DPP
🔎 Matched 1 wallet
Reading saved balances; anything missing will be rebuilt.
```
Company/wallet lines appear only when such a filter was given. Error paths (invalid date, future
date, bracket hint) still send exactly one card and no acknowledgement.

### 4.2 Result card
Header unchanged (`🕰️ … | 2026-07-15 · Total: … USDT`). Body, using the real 2026-07-15 figures
(71 in `wallets.json`, 3 of them created after that date, plus `Cold wallet` which has a balance
that day but is no longer listed):
```
📊 69 wallets counted — 68 saved, 1 no longer in your list
   3 more were added after this date, so they have no balance yet
⏰ Time: 2026-07-29 15:39 GMT+7
```
And on a date where some wallets had to be rebuilt:
```
📊 71 wallets counted — 69 saved, 2 rebuilt
⏰ Time: 2026-07-29 15:39 GMT+7
📈 2 rebuilt balances saved to Google Sheets (Batch ID: 20260729153923)
```

**Counting rule (explicit):** the headline number counts only wallets that have a figure and are
therefore in the total. Wallets shown as `—` (created later, or could not be worked out) are listed
in the table but counted separately on the second line, never folded into the headline number. The
`📈` line appears only when something was actually saved. Existing notes (missing / closest-match /
could-not-work-out) are unchanged in behaviour.

### 4.3 Wording
- Not found: `Wallet "ZZZ QQQ" not found.`
- Bracket hint: bold the example (**`/check [2026-07-15]`** → **/check [2026-07-15]**) rather than
  backticks, which render awkwardly in Lark.

---

## 5. `/remove` and `/add`

`/remove` switches to the shared `parse_arguments` (brackets **and** quotes), matching `/add` and
`/check`. Its usage/error text updates to bracket form. This alone fixes G1–G3.

**Reproduction tests** (the `request.txt` bug, end to end):

| Step | Command | Expected |
|---|---|---|
| 1 | `/add [TEST] [KZG TEST WALLET] [0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]` | added, chain detected ERC20 |
| 2 | `/remove [KZG TEST WALLET]` | removed by name (the case that always worked) |
| 3 | repeat step 1 | added again |
| 4 | `/remove [0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]` | **removed by address — the original bug** |
| 5 | `/list` | test wallet absent; the other 71 intact |

Automated equivalents go in `tests/`, using that exact address, so the bug can never silently
return. Quote syntax is tested alongside brackets for backward compatibility.

> **Accepted consequence:** these steps modify `wallets.json` (dev-local — the sheet sync process is
> not running). Step 5 confirms the file returns to its starting state.

---

## 6. Code changes

| File | Change |
|---|---|
| `bot/services/command_args.py` | Rewrite `resolve_fuzzy` per §3 (normalisation, tiered matching, uncapped literal matches, capped guesses). Return the match tier so the card can label a guess. |
| `bot/handlers/remove_handler.py` | Use shared `parse_arguments`; update usage/error text to brackets. |
| `bot/services/google_sheets_logger.py` | Add `save_rebuilt_balances(date_str, rows)` → appends to `DAILY_REPORT` with `Check Type = rebuilt`, reusing the existing retry logic. |
| `bot/handlers/check_handler.py` | Replace the date-level branch with per-wallet resolution (§2); acknowledgement card (§4.1); result card summary + footer (§4.2); wording (§4.3). |
| `tests/` | Fuzzy tiers + nonsense rejection; per-wallet resolution incl. removed/not-yet-created/failed; partial-save then top-up; `/remove` + `/add` bracket & quote parsing with the request.txt address. |

Keeps the existing shape: pure, testable cores (matching, resolution, card assembly) with thin I/O
around them.

---

## 7. Testing

- **Fuzzy:** each tier; nonsense returns nothing; literal matches uncapped; guesses capped at 3 and
  labelled; the benchmark cases from §3 as fixed regression cases.
- **Per-wallet resolution:** saved-only date; gap date; mixed (some saved, some rebuilt); wallet
  created after the date; wallet removed since but present in the record; rebuild failure.
- **Self-completion:** partial rebuild saves what it got → next check rebuilds only the remainder →
  date becomes complete; a saved figure is never overwritten.
- **Cards:** acknowledgement echoes filters and match count; error paths send exactly one card;
  count line matches rows shown (including when filtered).
- **`/remove` / `/add`:** brackets and quotes; by name; by address (TRC20 exact-case, ERC20
  case-insensitive) using the request.txt address; unknown address; wrong argument count.
- **Live verification** in dev against the real sheet, then the `DEV_TEST_PLAN.md` re-run.

---

## 8. Out of scope

USDC / multi-token (still Spec 2), and any change to the live `/check` computation.
