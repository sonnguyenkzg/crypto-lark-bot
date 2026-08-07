# Design — group near-miss matching for `/check` filters

**Date:** 2026-08-06
**Status:** approved in brainstorming, going to TDD implementation
**Prod baseline:** `ef675da` (== `origin/main`, prod runs `a40d355` = same handler code)

---

## 1. The bug

`/check [2026-07-15] [okz]` returns only **3** of the 10 OKKZ wallets, silently.

`okz` is a typo — `OKKZ` has two K's, so `okz` is not a prefix or substring of any wallet
name. It misses every literal match tier (exact → starts-with → contains → all-words) and
lands in the **closest-match** tier, which is capped at **3 guesses**. The card shows 3 and
hides 7, so the user under-counts.

For a balance tool, a silently truncated filter is a real hazard: the total looks complete
but isn't.

## 2. What must NOT change

The literal tiers already handle correct spelling correctly and **uncapped**:

- `okkz` → starts-with → all 10 OKKZ wallets
- `kzo` → starts-with → all 29 KZO wallets
- `dpp coy` → all-words → DPP COY TRC

None of these reach the fuzzy tier, so the fix must leave them untouched.

## 3. The fix — a "group near-miss" step

Add one step, reached **only** when a token missed every literal tier (i.e. a genuine
typo). It fuzzy-matches the token against the **group codes** (the distinct leading tokens
of the wallet names: `OKKZ, OKKZ1A…5A, KZO, KZP, KZG, S5, S5A, KZDW, DPP`) — not against
individual wallet names, which is too noisy.

```
group_near_miss(token, wallet_names, floor=0.6, margin=0.15):
    anchors = distinct leading tokens of wallet_names
    score each anchor by difflib ratio to the token (case-insensitive)
    keep anchors with score >= floor, best first
    if none                       -> "none"       (fall through, see §4)
    best = the top anchor
    rivals = other kept anchors within `margin` of best whose FAMILY-EXPANSION is a
             genuinely different wallet set (not a subset/superset of best's)
    if rivals                     -> "ambiguous"  (best + rivals)
    else                          -> "confident"  (best, expand to the group family of best)
```

**Exact first-token group expansion (NOT prefix, NOT a digit heuristic).** A confident hit
expands to wallets whose FIRST token equals the anchor exactly. Every wallet is therefore
in exactly one group, so a short code can NEVER swallow a longer one. Two earlier drafts
were codex-refuted: raw prefix let `S5` swallow `S5A`; a digit-suffix rule let a `S5`+digit
group (`S55A`) merge into `S5`. Exact first-token has no such hole. Consequence: `okz`
resolves to the **OKKZ group = 5** (OKKZ 1..5); the `OKKZ1A..5A` variants are their own
one-wallet groups. A typo between `S5` and `S5A` (`s5b`) is ambiguous, not a silent `S5`.

**Why rivals are compared by result set, not score.** For `okz`, the runner-up anchors
`OKKZ1A…` also score ~0.67, but their expansions are *subsets* of the `OKKZ` expansion, so
they are not competing answers — `okz` stays confident. For `kz0`, `KZP/KZO/KZG` each score
0.67 and expand to three *disjoint* sets, so it is ambiguous.

Verified on the live roster:

| Token | Verdict | Result |
|---|---|---|
| `okz` | confident | OKKZ group → **5** wallets |
| `kzdww` | confident | KZDW → 7 wallets |
| `dpp` | confident | DPP → 1 wallet |
| `s5a` | confident | S5A → 1 wallet |
| `kz0` | ambiguous | could be KZG, KZO, KZP |
| `dpy cyo` | none | falls through (§4) |
| `zzz qqq` | none | falls through (§4) |

## 4. Behaviour on each verdict

- **confident** → filter to the whole expanded set (uncapped), and add a header line so the
  substitution is transparent: `🔍 Closest match to "okz": OKKZ (10 wallets)`. The count
  still reconciles (scope N of 71).
- **ambiguous** → filter matches nothing for that token; show a notice:
  `⚠️ "kz0" could be KZP, KZO or KZG — type the one you mean.` Nothing is counted, so the
  user is never handed a wrong subset.
- **none** → unchanged: the token drops to today's single-wallet closest-match guess, which
  correctly handles a mistyped *wallet* name (`dpy cyo` → `DPP COY TRC`). The existing
  3-cap stays here as a last resort for genuinely scattered guesses — it is no longer the
  thing a *group* typo hits.

## 5. Flexibility & reliability (the two things Son asked for)

- **Flexible:** works for any group without a hardcoded list — anchors are derived from
  `wallets.json` at call time, so new groups/wallets are covered automatically.
- **Reliable:** it never *guesses* a group. A confident hit requires a clear winner; any
  real tie refuses rather than pick. Correct spelling is untouched because the step only
  runs after the literal tiers miss.

## 6. Where it lives

- `bot/services/command_args.py` — new pure function `resolve_group_near_miss(token,
  wallet_names, floor=0.6, margin=0.15) -> (verdict, anchor_or_list, wallets)`. No network,
  no I/O; unit-testable in isolation.
- `bot/handlers/check_handler.py` — the filter path calls it for each unresolved token:
  confident → extend the matched set + record the header; ambiguous → record the notice;
  none → existing behaviour. Card rendering adds the header/notice lines.

## 7. Testing (TDD)

Unit tests on `resolve_group_near_miss` against a fixed roster fixture: `okz`→confident
OKKZ (10), `kz0`→ambiguous {KZG,KZO,KZP}, `kzdww`→confident KZDW, `dpy cyo`/`zzz qqq`→none,
`dpp`→confident (1), and threshold edges. Handler tests: `[okz]` yields scope 5 with the
header; `[kz0]` yields the ambiguity notice and 0 counted; `[okkz]` and `[kzo]` unchanged
(literal tiers). Plus a real-roster self-test and the full suite (253 baseline).

## 8. Out of scope

The single-wallet closest-match 3-cap itself (kept as the last-resort fallback), the
opening/closing logic, the daily report, and the `⏰ Time` line.
