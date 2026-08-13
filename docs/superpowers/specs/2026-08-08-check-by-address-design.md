# Design — filter `/check [date]` by wallet address

**Date:** 2026-08-08
**Status:** approved in brainstorming, going to TDD implementation
**Requested by:** Fly0076 (FIN RECON, Account Executive)
**Prod baseline:** `9493633` (== `origin/main`)

---

## 1. What the AE asked for

Filter a dated `/check` by wallet **address** instead of (or alongside) name/group:

```
/check [date] [address]                 -> that wallet's closing balance
/check [date] [address] [address]       -> multiple wallets (union)
/check [date] [o] [address] ...         -> opening
/check [date] [c] [address] ...         -> closing, explicit
```

An address is a **precise way to name a monitored wallet by exact match** (no fuzzy guessing, so
never the wrong wallet) — reconciliation-friendly.

## 2. Two decisions made with Son

1. **Monitored wallets only.** An address is a lookup key into the 71 wallets in `wallets.json`.
   A valid address that isn't monitored is an error, not an on-chain reconstruction. No new
   blockchain scope.
2. **Validate first, then check the valid ones and flag the rest.** Never a silent partial total.

## 3. What it reuses (low risk)

- `detect_chain_from_address(addr)` — returns `"TRC20"` / `"ERC20"` for a well-formed address,
  `None` otherwise (the exact format check `/remove` uses).
- `canonical_address(addr)` — ERC20 lowercased (hex, case-insensitive), TRC20 exact (base58,
  case-sensitive). The single source of address identity, already used across the bot.
- `/check [date]` already sends an acknowledgement card **before** the balance lookup — validation
  slots into it, no new card.

## 4. Token detection — by content

A bracketed token is treated as an **address token** when, stripped, it has no spaces AND either:

- starts with `0x`, or
- starts with `T` and is at least 30 characters.

Everything else stays a name/group via the existing `classify_tokens`. Wallet names contain spaces
and are short, and no group code is a 30-char `T…` string, so there is no collision. `classify_tokens`
gains a third return value: `(groups, names, addresses)`.

Addresses, names, and groups may be **mixed** in one command; each token is handled by its own type
and the results are unioned.

## 5. Validation — three outcomes per address token

Evaluated against the 71 monitored wallet entries (each carries its `address`):

| Outcome | Condition | Shown as |
|---|---|---|
| ✅ **matched** | `detect_chain_from_address` valid AND `canonical_address` equals a monitored wallet's | `✅ TR7NH…j6t → KZP 96G1` |
| ❌ **invalid** | `detect_chain_from_address` returns `None` (malformed) | `❌ 0x123 — invalid address` |
| ⚠️ **unmonitored** | valid format, but no monitored wallet has it | `⚠️ Tabc…xyz — valid, but not monitored` |

The acknowledgement card (sent before the lookup) lists these. Then the check proceeds with the
matched wallets only.

## 6. Result

- The result card reconciles: **"checked N of M addresses"**, and repeats any invalid / unmonitored
  so the skip is never silent.
- A matched wallet shows its **name** (with its address available for reconciliation).
- **Deduplication:** the same address twice, or an address plus that wallet's name, collapse to one
  wallet (the existing per-entry dedup in `_filter_entries` already does this by identity).
- `[o]` / `[c]` and multiple addresses (union) behave exactly as they do for name filters today —
  this is a new *token type*, not a new code path for opening/closing or dating.

**Combining semantics.** An address is an **exact** wallet identifier, so it is treated as
**additive**: a named address always resolves against the full 71-wallet roster and is included in the
result, regardless of any group filter present. This differs deliberately from a **name**, which is a
fuzzy filter and still resolves *within* a group's narrowed scope (unchanged from today). Rationale:
naming an exact wallet and then having an unrelated `[KZP]` group silently drop it would produce a
confusing empty result — additive matches intent ("show me this exact wallet, and also the KZP
group"). Multiple addresses union among themselves. All selectors are de-duplicated by wallet identity,
so `[KZP] [<address of a KZP wallet>]` still yields the six KZP wallets, not seven. The intended,
common use is address-only (with optional `[o]`/`[c]`). Because addresses judge against the full
roster, monitored-vs-unmonitored is always accurate — a valid address is "unmonitored" only when no
wallet in the roster holds it.

## 7. Error handling (the AE's core ask)

- Every flag is explicit and up front; a partial result always states how many of how many were
  checked.
- If **nothing** resolves to a monitored wallet (all tokens invalid / unmonitored / not-found), the
  bot shows the validation errors and **runs no balance lookup** — same as the existing "wallet not
  found" behaviour, extended to addresses.
- Case handling is delegated to `canonical_address`: `0xABC…` matches `0xabc…`; a TRC20 address must
  match exactly.
- An empty or whitespace token is ignored by the parser, as today.

## 8. Where it lives

- `bot/services/command_args.py` — `classify_tokens` returns `(groups, names, addresses)`; a small
  `looks_like_address(token)` helper for the content detection. Pure, unit-testable.
- `bot/handlers/check_handler.py` — `_filter_entries` gains address handling: match each address token
  against the entries, collect matched wallets, and return the invalid / unmonitored lists for the
  cards. The acknowledgement and result cards render the validation lines.
- No change to reconstruction, the daily report, `/add`, `/remove`, or the live `/check`.

## 9. Testing (TDD)

- **Unit** (`command_args`): `looks_like_address` for `0x…`, long `T…`, malformed (`0x123`, short
  `T…`), names with spaces; `classify_tokens` three-way split; case-insensitive ERC20, exact TRC20.
- **Handler**: `/check [date] [addr]` → the one wallet; two addresses → union; `[o]`/`[c]`; a
  malformed address → flagged invalid, valid ones still checked; a valid-but-unmonitored address →
  flagged, others checked; all-bad → validation card, no lookup; address + name mixed → union, deduped.
- **Real-data self-test**: run against actual monitored addresses from `wallets.json` (read-only),
  confirming `/check [date] [<real address>]` returns exactly that wallet and matches the name-filtered
  figure.
- **Codex critical review** before deploy; full existing suite must stay green (272 baseline).

## 10. Out of scope

Reconstructing non-monitored / arbitrary addresses (decided against — monitored only); any change to
how opening/closing, dating, or reconstruction work; the live no-date `/check`.
