# Design — `/check [date]` historical lookup + `/remove [address]` fix

**Date:** 2026-07-22
**Status:** Approved (brainstorm), pending spec review
**Scope:** Spec 1 of 2. USDC / multi-token is deferred to Spec 2.

---

## 1. Context & verified baseline

The crypto Lark bot reports USDT wallet balances to Lark and logs every check to a
shared Google Sheet.

Ground truth was verified directly against **live production** (read-only), because an
outdated server initially caused confusion:

| Fact | Value |
|---|---|
| Live prod host | `47.129.129.241` (`kzg-crypto-bot-ec2`), running `python main.py` since 2026-02-10 |
| Prod code | GitHub `main` **`b6c7722`, clean** — **byte-for-byte identical to our clone** (all target files verified `SAME`) |
| Wallet master | `wallets.json` on prod (**70 wallets**), auto-synced from the `WALLET_LIST` sheet tab (`sheets_sync.log` active) |
| Chain mix | **66 TRC20 + 4 ERC20** (41 wallets have no `chain` field → default TRC20; 25 explicit TRC20; 4 explicit ERC20) |
| `.env` | Has both `TRON_API_KEY` and `ETHEREUM_API_KEY` |
| Vault | Google Sheet `DAILY_REPORT` tab: **303 daily snapshots** (2025-09-22 → 2026-07-22), one batch/day, ~70 wallets. Columns: `Batch ID, Date, Time, Wallet Name, Company, Address, Balance (USDT), Check Type` |

> An old box (`52.221.225.241`) is a **dead deployment** (frozen 2026-01-27, 46 stale
> wallets, no ETH key). It is ignored. Do not deploy there.

Because the clone == prod, development happens on the clone and ships via GitHub → prod
`git pull` + restart.

---

## 2. Goals & non-goals

**Goals (from `request.txt`):**
1. `/check [date]` — balance of all logged wallets on a specific date.
2. `/check [date] [group] [wallet name(s)]` — filtered lookup.
3. `/check [date] [fuzzy]` — return the closest-matching wallets on a name miss.
4. Fix `/remove "[wallet address]"` — works by name, broken by address.

**Non-goals (deferred to Spec 2):** USDC / multi-token, additional chains (Base/Polygon/…),
and the vault sheet schema change those require. `ETHEREUM_API_KEY` is a **hard
prerequisite** for Spec 2 (already present in prod).

---

## 3. Feasibility — proven against real data

"Get a past-date balance" has no easy free endpoint for Tron (Etherscan's historical
endpoint is PRO/paid and Ethereum-only; Covalent/Alchemy skip Tron). Decision:
**vault-first, reconstruct from chain as fallback.** Proof (real prod sheet + live chain):

- **Reconstruction = current balance − (net USDT transfers after the snapshot instant).**
- **TRC20** — 4 wallets on 2026-07-15 reconstructed to the **cent** (diff 0.00), incl. a
  wallet with 210 in-window transfers. Missing date 2026-07-20 gap-filled correctly.
- **ERC20** — 4 wallets reconstructed to the **cent** using the prod Etherscan key.

**Nuances baked into the design:**
- **Windowing is essential** — only fetch transfers *after* the target date, so recent
  dates cost 0–200 calls, not full history. Tronscan caps `total` at 10,000 (irrelevant
  for gap-fills, which are always recent). Note the cap and degrade gracefully.
- **Filter `finalResult == SUCCESS`** (exclude reverted transfers).
- **Strip commas** from logged balances (`"351,432.18"`).
- **Cutoff precision:** for a logged date, use that snapshot's GMT+7 batch timestamp. For
  a gap date `D`, use `D 00:01 GMT+7` (the daily run instant) so spacing matches the vault.

---

## 4. Command grammar

**Every argument is wrapped in `[ ]`** — one uniform rule, no bare words to reason about.
Double quotes `"…"` / `'…'` are still accepted as a silent alias so existing `/remove "…"`
and `/add "…"` commands keep working, but **brackets are THE documented format**. Brackets
also avoid mobile "smart-quote" breakage.

Each bracketed token is classified **by content** (one shared parser for `/check`,
`/remove`, `/add`):
1. matches `YYYY-MM-DD` → the **date** (→ historical mode)
2. else exactly matches a known **company/group** (case-insensitive) → **group** filter
3. else → **wallet name** (exact match, else fuzzy)

If a token matches **both** a company and a wallet name, the **group wins** and the response
says so, so the user can disambiguate. A bare (un-bracketed) token is ignored with a hint to
wrap it in `[ ]`.

The parser returns `(date | None, other_tokens: [str])`; the handler — which has the loaded
wallet/company data — classifies `other_tokens` into `groups` vs `wallet_names` by content.
Live and historical paths apply the same filters; they differ only in data source.

| Command | Mode | Meaning |
|---|---|---|
| `/check` | live | All current wallets, live (unchanged) |
| `/check [KZP 96G1]` | live | That wallet, live |
| `/check [2026-07-15]` | historical | All wallets logged that date |
| `/check [2026-07-15] [KZP]` | historical | Group KZP on that date |
| `/check [2026-07-15] [KZP 96G1] [KZP WDB2]` | historical | Those wallets on that date |
| `/check [2026-07-15] [KZP] [KZP 96G1]` | historical | That wallet within group KZP |
| `/remove [KZP 96G1]` | — | Remove by name |
| `/remove [T… / 0x…]` | — | Remove by address (**fix**) |
| `/add [KZP] [KZP WDB2] [T…]` | — | Add wallet |

---

## 5. Behaviour spec

### 5.1 `/check <date>` (historical)
1. **Validate date** — ISO `YYYY-MM-DD` only (regex + real-calendar check). Otherwise a
   friendly card: "Use format YYYY-MM-DD, e.g. `/check 2026-07-15`."
   - **Reject future dates** (`> today` GMT+7) — a balance for a future date is undefined.
   - Dates before the vault start (2025-09-22) have no snapshot; reconstruction of a very
     old date may exceed the 10,000-transfer cap, so warn and cap gracefully rather than
     silently returning a wrong number.
   > **`canonical_address(addr)` (used everywhere an address is a key or is compared):** ERC20
   > (`0x…`) → `addr.strip().lower()` (hex is case-insensitive — the same address can appear in
   > different casings); TRC20 (`T…`) → `addr.strip()` **unchanged** (base58 is case-sensitive —
   > lowercasing would corrupt/merge distinct addresses). Chain is inferred from the `0x` prefix,
   > so no `chain` column is needed.

2. **Read the vault** — take the **union of ALL batches** for `<date>` from `DAILY_REPORT`,
   **keyed by `canonical_address(address)`** (the on-chain identity), keeping the **EARLIEST
   `Time` value per canonical address** (the value closest to the scheduled ~00:01 daily run).
   Three reasons:
   - **Completeness:** the logger writes rows only for wallets whose fetch *succeeded*, so a
     same-day retry re-logs only what it re-fetched — the earliest batch alone can be partial
     (e.g. a 00:01 batch of 69 + a 00:07 retry of the 1 that failed at 00:01). Unioning restores
     the full set; a wallet missing at 00:01 is picked up from its earliest later appearance.
   - **Earliest, not latest — an intraday run must never overwrite the morning snapshot.** A
     manual test/retry can run *later the same day* (e.g. 14:00) and log a full batch at
     *intraday* balances. "Latest per address" would replace the 00:01 values with 14:00 values
     and report an intraday total as the "date-`D` snapshot". Earliest-per-address keeps the
     canonical 00:01 values; a later batch can only **add** wallets no earlier batch captured.
   - **Key by address, never by name.** Over 300+ days a display name can map to different
     addresses (rename / reuse after removal). Keying by *name* would collapse two distinct
     addresses that share a name → **silent under-count**, or double-count one address logged
     under two names. Address is the true unique balance identity (one USDT balance per address).
   The wallet set is **what was logged** that date (includes since-removed wallets; excludes
   wallets never logged that date).
3. **Completeness guard (prevents a silent under-count) — anchored to the CURRENT roster, NOT
   to neighbouring snapshots.** Neighbouring snapshots can *all* be partial (e.g. ERC20 fetches
   fail for weeks → every day logs only the 66 TRC20 wallets), so a window-based reference is
   itself poison-able. Instead compare the snapshot's **addresses** to the **current roster**
   (`wallets.json`, an independent source): `expected = { addresses of current wallets whose
   created_at <= <date> }` (if `created_at` is missing/unparseable, include the wallet);
   `missing = expected − snapshot_addresses` (both sides mapped through `canonical_address` so an
   ERC20 casing difference never shows a false "missing"; display each missing wallet's name). If `missing` is non-empty, the
   card shows a prominent **⚠️ "This snapshot is missing M wallet(s) that exist today: <list>;
   the total may be understated"** — the number is **never** presented as authoritative.
   *(Optional enhancement: auto-reconstruct the missing wallets as-of `<date>` and merge them
   in, labelled `~reconstructed`, so the total is made whole.)*
   **Documented residual:** a wallet that was BOTH absent from the snapshot AND has since been
   removed cannot be detected (no independent oracle exists for it); this limit is stated in the
   card footnote, not silently hidden.
4. **If union rows exist:** build the table from the union. Source line:
   *"Source: daily snapshot (DAILY_REPORT) — 2026-07-15 · N wallets"*.
5. **If no rows for `<date>` (gap):** reconstruct from chain for the **current** wallet set
   (`wallets.json`). Source line: *"Source: reconstructed from chain — no snapshot for
   2026-07-15"*. Each row tagged `~reconstructed`; any wallet whose reconstruction fails is
   shown as **"unavailable"** and **excluded from the total with a note** — never silently dropped.
6. **Apply filters** (`groups`, `wallet_names`) to the wallet set.
7. **Render** the existing balance card (group subtotals + grand total), plus the source line,
   the wallet count, the completeness/unavailable warnings if any, and `not found` / `~closest`
   notes.

### 5.2 Filters
- **Group:** match `Company` case-insensitively; multiple group tokens = OR.
- **Wallet name:** exact (case-insensitive) match wins.
- **Fuzzy (on a name miss):** `difflib.get_close_matches(token, candidates, n=3, cutoff=0.6)`
  **plus** case-insensitive substring containment. Include matches, each row labelled
  `≈ closest to "<token>"`. If still nothing, add `<token>` to a `not found` list. **No LLM
  — deterministic stdlib only.**

### 5.3 Reconstruction service
`balance_service.get_balance_at(address, chain, cutoff_ms) -> Decimal | None`:
1. `current = get_balance(address, chain)` (existing live method).
2. `net = Σ signed USDT transfers with block_ts > cutoff` (SUCCESS only), windowed
   `(cutoff, now]`, paginated. TRC20 → Tronscan `token_trc20/transfers`; ERC20 → Etherscan
   `tokentx`.
3. `return current - net`. On missing API key / error → `None` (row shows "unavailable",
   never crashes the whole report).

### 5.4 `/remove [address]` fix
Root cause: `remove_handler.find_wallet_by_identifier()` gates address matching behind
`balance_service.validate_trc20_address()` (Tron-only), so ERC20 `0x…` never matches →
"not found". Affects the 4 live ERC20 wallets.

Fix: replace that gate with the chain-agnostic `chain_detector.detect_chain_from_address()`
(already used by `/check`). Also update the `_create_success_card` "removed by
name/address" detection and the not-found card's is-address check to use it. **Address match
uses `canonical_address` per chain — ERC20 case-insensitive, TRC20 case-sensitive (base58) —
never a blanket `.lower()`, which could match and delete the wrong TRC20 wallet on a
case-differing typo.**

---

## 6. Code changes

| File | Change |
|---|---|
| `bot/services/command_args.py` *(new)* | Shared parser: `parse_arguments(text)` → delimited tokens (`[ ]` or quote alias), bare tokens flagged; `split_date(tokens)` → `(date, other_tokens)`; `classify_tokens(other_tokens, companies, wallet_names)` → `(groups, names)` by content, group-wins on tie; `resolve_fuzzy(token, candidates)`. |
| `bot/services/google_sheets_logger.py` | Add `get_snapshot_for_date(date)` → **union of all that-date batches keyed by canonical address, EARLIEST `Time` per address** (closest to the ~00:01 run — a later intraday retry can only add wallets, never overwrite): `{canonical_address: {wallet_name, company, address, balance, batch_id, time}}` (never keyed by name — see §5.1). Read-only; reuses the existing service init. |
| `bot/services/balance_service.py` | Add `get_balance_at(address, chain, cutoff_ms)` + `_net_transfers_after(address, chain, cutoff_ms)` (TRC20 + ERC20, SUCCESS filter, windowed pagination). |
| `bot/services/chain_detector.py` | Add `canonical_address(address)` → ERC20 (`0x…`) lowercased, TRC20 (`T…`) unchanged. Single source of address identity used by the `/check` union, the completeness guard, and `/remove` matching. |
| `bot/handlers/check_handler.py` | Parse via `command_args`; branch date→historical (vault → reconstruct) vs no-date→live (unchanged). Apply group/name/fuzzy filters. **Completeness guard:** compute `missing = expected_addresses − snapshot_addresses` against the current roster (`wallet_service.list_wallets()` + `created_at`) and warn/list. Add source line + row tags to the card. |
| `bot/handlers/remove_handler.py` | Chain-agnostic address matching (`detect_chain_from_address`). |
| `bot/handlers/add_handler.py` | Use the shared parser (accept brackets in addition to quotes). |
| `bot/handlers/help_handler.py` | Document `/check [date]` forms + bracket syntax. |

Design keeps units small: parsing, vault-read, and reconstruction are separate,
independently testable services; the handler orchestrates.

---

## 7. Testing plan

Python-first (Son's convention), against the **real pulled prod data** in scratchpad, then
`difflib`/unit tests, then an independent codex-review before shipping.

- **Parser:** brackets, quote alias, smart-quotes, mixed; content classification
  (date vs group vs wallet); token matching both company + wallet (group wins); bare token
  ignored with hint; ISO-date detection; no-date live path; empty.
- **Date validation:** valid, malformed, impossible (`2026-13-40`), non-ISO (`15/07/2026`).
- **Vault read:** date with a snapshot; a gap date; a date with >1 batch — a full 00:01 batch +
  a 1-wallet 00:07 retry must return the full 70 (union for completeness); AND a full 14:00
  **intraday** re-run must be IGNORED for wallets already in the 00:01 batch
  (earliest-per-address), so `/check [D]` reports the 00:01 total, not the intraday total.
- **Row identity:** two snapshot rows with the **same name but different addresses** are both
  counted (keyed by canonical address, not collapsed); the same address logged under two names
  counts once.
- **Address canonicalization:** the same ERC20 address in two casings across batches counts
  **once** (no double-count) and never shows a false "missing"; a TRC20 address with a changed
  letter-case does **not** match (case-sensitive) in the `/check` union or in `/remove`.
- **Completeness guard (anchored to current roster):** a snapshot missing a current wallet —
  e.g. all 4 ERC20 absent because ERC20 fetches failed for weeks, so *every* ±7-day neighbour is
  equally partial — **still** fires the ⚠️ warning and names the missing wallets; a complete
  snapshot → no warning; a wallet with `created_at` after the date → not expected (no false-miss);
  reconstruction failure → shown "unavailable", excluded from the total.
- **Reconstruction:** re-run the proof (TRC20 incl. big window + ERC20); compare to logged;
  a date with in-window transfers on both chains.
- **Fuzzy:** near-miss returns closest + label; total miss → not-found; case-insensitive.
- **Filters:** group only, names only, group+names intersection, unknown group.
- **`/remove`:** by name; by TRC20 address (exact — a case-changed TRC20 must NOT match); by
  ERC20 address in mixed/checksum case (matches, case-insensitive); by unknown address.
- **Edge/malformed:** commas in balances, missing `chain` field (→ TRC20), reverted
  transfers excluded, missing ETH key → graceful "unavailable".

---

## 8. Deployment

Ship on branch `feature/check-date-and-remove-fix` → push to GitHub `main` → on
`47.129.129.241`: `git pull` + restart the bot. `wallets.json` is local/synced — untouched
by this change.

---

## 9. Open items / prerequisites

- None blocking Spec 1 (all APIs, keys, and data verified live).
- Spec 2 (USDC/multi-token) will need the vault schema to carry a token dimension; the
  `ETHEREUM_API_KEY` prerequisite is already satisfied.
