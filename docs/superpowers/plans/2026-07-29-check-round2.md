# `/check` Round 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the six issues found in live dev testing — `/remove` bracket parsing, loose fuzzy matching, unexplained wallet counts — by resolving each wallet independently against the date, saving rebuilt figures back so history self-completes.

**Architecture:** Pure, testable cores (name matching, wallet classification, card assembly) with thin I/O around them. The date-level "snapshot or rebuild" branch is replaced by per-wallet resolution: each wallet is either already saved, rebuilt-and-saved, or shown as a dash with the reason.

**Tech Stack:** Python 3.12, `requests`, Google Sheets API, stdlib `difflib`/`re`/`decimal`, `pytest`. Run tests with `.venv/bin/python -m pytest`.

Spec: `docs/superpowers/specs/2026-07-29-check-round2-design.md`

## Global Constraints

- **No new dependencies.** Matching uses stdlib `difflib` + `re`. No LLM.
- **`wallets.json` is the single source of truth** for which wallets exist; `created_at` decides whether a wallet existed on a given date (missing/unparseable → treat as existing, the safe direction).
- **Never silently understate a total.** A wallet with a real balance is always counted, even if it is no longer in `wallets.json`. A wallet with no figure is listed with a reason and excluded from the total, never dropped.
- **A saved figure is never overwritten.** Rebuilding only ever happens for a wallet with no saved figure for that date.
- **Rebuilt rows are written to `DAILY_REPORT`** with `Check Type = "rebuilt"`, so the date self-completes. Partial saves are fine; the next check fills in only what is still missing.
- **Balances stored with commas** (`"351,432.18"`); strip before `Decimal`. Sheet columns `A:H` = `Batch ID, Date, Time, Wallet Name, Company, Address, Balance (USDT), Check Type`.
- **`canonical_address(addr)`** (ERC20 lowercased, TRC20 exact) for every address key/compare.
- **Dates** ISO `YYYY-MM-DD`, GMT+7. Batch IDs `YYYYMMDDHHMMSS` in GMT+7.
- **Grammar:** every argument in `[ ]`; quotes still accepted. Applies to `/check`, `/add`, **and `/remove`**.
- **Live `/check` (no date) stays behaviourally unchanged.**
- **Plain user-facing language.** No internal names (`DAILY_REPORT`), no shouting caps.

---

### Task 1: Tiered name matching

**Files:**
- Modify: `bot/services/command_args.py`
- Modify: `tests/test_command_args_classify.py`
- Test: `tests/test_fuzzy_matching.py` (create)

**Interfaces:**
- Produces: `normalize_name(s) -> str`; `squash_name(s) -> str`;
  `resolve_fuzzy(token, candidates, n=3, cutoff=0.6) -> tuple[list[str], str]`
  where the second element is the tier: `"exact" | "starts with" | "contains" | "all words" | "closest match" | "none"`.
  **Breaking change:** it previously returned a bare list; Task 4 is the only other consumer.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fuzzy_matching.py
from bot.services.command_args import resolve_fuzzy, normalize_name, squash_name

NAMES = ["DPP COY TRC", "KZDW DPP COY TRC 1", "KZP COY", "KZP COY 2", "KZP 96G1",
         "KZP BLG1", "KZDW DPP TH 2", "OKKZ 1", "OKKZ 2", "OKKZ 3", "S5 Cold TRC20"]

def test_normalizers():
    assert normalize_name("  KZDW  DPP-TH 2 ") == "kzdw dpp th 2"
    assert squash_name("KZDW DPP-TH 2") == "kzdwdppth2"

def test_exact_ignores_case_and_spacing():
    assert resolve_fuzzy("kzp 96g1", NAMES) == (["KZP 96G1"], "exact")
    assert resolve_fuzzy("KZP96G1", NAMES) == (["KZP 96G1"], "exact")
    assert resolve_fuzzy("KZDW DPP TH2", NAMES) == (["KZDW DPP TH 2"], "exact")

def test_starts_with_wins_over_noise():
    # the C1/C2 bug: KZP COY must NOT come back for "DPP COY"
    got, tier = resolve_fuzzy("DPP COY", NAMES)
    assert got == ["DPP COY TRC"] and tier == "starts with"
    got, tier = resolve_fuzzy("kzp 96", NAMES)
    assert got == ["KZP 96G1"] and tier == "starts with"

def test_literal_matches_are_not_capped():
    # all three OKKZ wallets, even though n=3 caps only guesses
    got, tier = resolve_fuzzy("OKKZ", NAMES)
    assert got == ["OKKZ 1", "OKKZ 2", "OKKZ 3"] and tier == "starts with"

def test_contains_when_not_a_prefix():
    got, tier = resolve_fuzzy("COY TRC 1", NAMES)
    assert got == ["KZDW DPP COY TRC 1"] and tier == "contains"

def test_all_words_any_order():
    got, tier = resolve_fuzzy("TRC DPP COY", NAMES)
    assert "DPP COY TRC" in got and tier == "all words"

def test_typo_short_query():
    got, tier = resolve_fuzzy("DPY CYO", NAMES)
    assert got[0] == "DPP COY TRC" and tier == "closest match"

def test_typo_multiple():
    got, tier = resolve_fuzzy("DYP CYO TCR", NAMES)
    assert "DPP COY TRC" in got and tier == "closest match"

def test_guesses_are_capped():
    got, _ = resolve_fuzzy("KZP 96G2", NAMES)
    assert len(got) <= 3

def test_nonsense_matches_nothing():
    for junk in ["ZZZ QQQ", "XYZ ABC", "12345", "hello world"]:
        assert resolve_fuzzy(junk, NAMES) == ([], "none")

def test_empty_input():
    assert resolve_fuzzy("", NAMES) == ([], "none")
    assert resolve_fuzzy("KZP", []) == ([], "none")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_fuzzy_matching.py -v`
Expected: FAIL with `ImportError: cannot import name 'normalize_name'`

- [ ] **Step 3: Implement the tiered matcher**

Replace the whole existing `resolve_fuzzy` in `bot/services/command_args.py` with:

```python
def normalize_name(s):
    """lowercase; every run of non-alphanumerics becomes one space; trimmed."""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def squash_name(s):
    """lowercase with every non-alphanumeric removed, so 'TH 2' == 'TH2'."""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def resolve_fuzzy(token, candidates, n=3, cutoff=0.6):
    """Find the wallet name(s) the user meant.

    Tries progressively looser rules and stops at the first that hits, so a query
    that matches literally never gets guesses mixed in:
        exact -> starts with -> contains -> all words -> closest match

    Spacing, punctuation and case are ignored throughout.
    Literal tiers return EVERY match (truncating could hide a real wallet);
    only the closest-match tier is capped at `n`, because those are guesses.

    Returns (matches, tier). tier is "none" when nothing matched.
    """
    if not token or not candidates:
        return [], "none"
    qn, qs = normalize_name(token), squash_name(token)
    if not qs:
        return [], "none"

    exact = [c for c in candidates if squash_name(c) == qs]
    if exact:
        return exact, "exact"

    starts = [c for c in candidates if squash_name(c).startswith(qs)]
    if starts:
        return starts, "starts with"

    contains = [c for c in candidates if qs in squash_name(c)]
    if contains:
        return contains, "contains"

    words = qn.split()
    if len(words) > 1:
        all_words = [c for c in candidates
                     if all(w in normalize_name(c) for w in words)]
        if all_words:
            return all_words, "all words"

    def score(c):
        cn, cs = normalize_name(c), squash_name(c)
        # compare against the whole name AND its same-length start, in both the
        # spaced and squashed forms -- the head comparison is what lets a short
        # typo'd query ("DPY CYO") still find a longer name.
        return max(SequenceMatcher(None, qn, cn).ratio(),
                   SequenceMatcher(None, qn, cn[:len(qn)]).ratio(),
                   SequenceMatcher(None, qs, cs).ratio(),
                   SequenceMatcher(None, qs, cs[:len(qs)]).ratio())

    ranked = sorted(((score(c), c) for c in candidates), key=lambda x: -x[0])
    close = [c for s, c in ranked if s >= cutoff][:n]
    return (close, "closest match") if close else ([], "none")
```

Ensure the file imports `SequenceMatcher`: change `from difflib import get_close_matches` to
`from difflib import SequenceMatcher` (the old helper is no longer used).

- [ ] **Step 4: Update the existing classify tests for the new return type**

In `tests/test_command_args_classify.py`, the two fuzzy tests now unpack a tuple:

```python
def test_resolve_fuzzy_near_miss():
    got, _ = resolve_fuzzy("KZP 96", NAMES)
    assert "KZP 96G1" in got

def test_resolve_fuzzy_total_miss():
    assert resolve_fuzzy("ZZZ QQQ", NAMES) == ([], "none")

def test_resolve_fuzzy_case_insensitive():
    got, _ = resolve_fuzzy("kzp 96g2", NAMES)
    assert "KZP 96G1" in got
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fuzzy_matching.py tests/test_command_args_classify.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add bot/services/command_args.py tests/test_fuzzy_matching.py tests/test_command_args_classify.py
git commit -m "feat(args): tiered name matching (exact/starts-with/contains/all-words/closest)"
```

---

### Task 2: `/remove` accepts brackets

**Files:**
- Modify: `bot/handlers/remove_handler.py`
- Test: `tests/test_remove_parse.py` (create)

**Interfaces:**
- Consumes: `parse_arguments(text) -> (tokens, had_bare)` from `bot.services.command_args`.
- Produces: `RemoveHandler.parse_single_quoted_argument(text) -> tuple[bool, str]` (unchanged signature, now bracket-aware).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_remove_parse.py
from bot.handlers.remove_handler import RemoveHandler

H = RemoveHandler()

def test_accepts_brackets():
    ok, val = H.parse_single_quoted_argument('[KZG TEST WALLET]')
    assert ok and val == "KZG TEST WALLET"

def test_accepts_bracketed_address():
    # the exact address from request.txt that used to fail
    ok, val = H.parse_single_quoted_argument('[0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]')
    assert ok and val == "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071"

def test_still_accepts_quotes():
    ok, val = H.parse_single_quoted_argument('"Cold wallet"')
    assert ok and val == "Cold wallet"

def test_missing_argument():
    ok, msg = H.parse_single_quoted_argument("")
    assert not ok and "wallet name or address" in msg.lower()

def test_too_many_arguments():
    ok, msg = H.parse_single_quoted_argument('[A] [B]')
    assert not ok and "found 2" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_remove_parse.py -v`
Expected: FAIL — `test_accepts_brackets` returns `(False, "❌ Expected 1 quoted argument, found 0")`

- [ ] **Step 3: Point the parser at the shared tokenizer**

In `bot/handlers/remove_handler.py`, add the import near the other bot imports:

```python
from bot.services.command_args import parse_arguments
```

Delete the `extract_quoted_strings` method entirely, and replace `parse_single_quoted_argument` with:

```python
    def parse_single_quoted_argument(self, text: str) -> Tuple[bool, Union[str, str]]:
        """Parse the single [wallet name or address] argument.

        Accepts [brackets] (preferred) or "quotes" (still supported).
        Returns (success, wallet_identifier) or (False, error_message).
        """
        if not text or not text.strip():
            return False, "❌ Missing wallet name or address"

        matches, _ = parse_arguments(text)

        if len(matches) != 1:
            return False, f"❌ Expected 1 argument in [ ] (or quotes), found {len(matches)}"

        return True, matches[0].strip()
```

- [ ] **Step 4: Update the user-facing text to bracket form**

In the same file, replace every `/remove "..."` example and usage string with bracket form:
- `self.usage` → `'/remove [wallet_name_or_address]'`
- In `_create_usage_card` and `_create_error_card`, the `**Usage:**` line → `**Usage:** /remove [wallet name or address]`
- Their `**Examples:**` lines → `• /remove [KZP TEST1] (by name)` and
  `• /remove [TDgWVGJKktTMaGt9fLJhTr7PHY3hEfk6BU] (by address)`

Verify none remain: `grep -n '/remove "' bot/handlers/remove_handler.py` returns nothing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_remove_parse.py tests/test_remove_address.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/remove_handler.py tests/test_remove_parse.py
git commit -m "fix(remove): accept [brackets] via the shared parser (fixes G1-G3)"
```

---

### Task 3: Save rebuilt balances back to the sheet

**Files:**
- Modify: `bot/services/google_sheets_logger.py`
- Test: `tests/test_save_rebuilt.py` (create)

**Interfaces:**
- Consumes: existing `_generate_batch_id()`, `_ensure_headers(sheet_name)`, `WRITE_RETRIES`.
- Produces: `GoogleSheetsBalanceLogger._append_rows_with_retry(sheet_name, data_rows) -> dict | None`;
  `GoogleSheetsBalanceLogger.save_rebuilt_balances(date_str, rows) -> tuple[bool, str | None]`
  where `rows` is `[{"name": str, "company": str, "address": str, "balance": Decimal}]`
  and the return is `(success, batch_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_save_rebuilt.py
from decimal import Decimal
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

def _logger(monkeypatch, captured):
    L = GoogleSheetsBalanceLogger()
    L.credentials_file = "x"; L.spreadsheet_id = "y"
    monkeypatch.setattr(L, "_initialize_service", lambda: True)
    monkeypatch.setattr(L, "_ensure_headers", lambda name: None)
    monkeypatch.setattr(L, "_append_rows_with_retry",
                        lambda sheet, rows: captured.update(sheet=sheet, rows=rows)
                        or {"updates": {"updatedCells": len(rows) * 8}})
    return L

def test_saves_rows_with_rebuilt_marker(monkeypatch):
    cap = {}
    L = _logger(monkeypatch, cap)
    ok, batch = L.save_rebuilt_balances("2026-07-20", [
        {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "balance": Decimal("19.41")},
    ])
    assert ok is True and batch
    assert cap["sheet"] == "DAILY_REPORT"
    row = cap["rows"][0]
    # cols: batch, date, time, wallet, company, address, balance, check type
    assert row[1] == "2026-07-20"          # the DATE ASKED FOR, not today
    assert row[3] == "KZP 96G1"
    assert row[5] == "TAAA"
    assert row[6] == "19.41"
    assert row[7] == "rebuilt"             # distinguishable from a measured row

def test_no_rows_is_not_an_error(monkeypatch):
    cap = {}
    L = _logger(monkeypatch, cap)
    assert L.save_rebuilt_balances("2026-07-20", []) == (False, None)
    assert cap == {}                        # nothing written

def test_write_failure_reports_false(monkeypatch):
    L = GoogleSheetsBalanceLogger()
    L.credentials_file = "x"; L.spreadsheet_id = "y"
    monkeypatch.setattr(L, "_initialize_service", lambda: True)
    monkeypatch.setattr(L, "_ensure_headers", lambda name: None)
    monkeypatch.setattr(L, "_append_rows_with_retry", lambda sheet, rows: None)
    ok, batch = L.save_rebuilt_balances("2026-07-20", [
        {"name": "W", "company": "C", "address": "TAAA", "balance": Decimal("1")}])
    assert ok is False and batch is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_save_rebuilt.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'save_rebuilt_balances'`

- [ ] **Step 3: Extract the retry-append helper**

In `log_balance_check`, the append currently sits inline in a retry loop. Replace that whole
retry block (from `result = None` through the `if result is None:` guard) with a call:

```python
            result = self._append_rows_with_retry(sheet_name, data_rows)
            if result is None:
                return False, None
```

Then add the helper as a new method:

```python
    def _append_rows_with_retry(self, sheet_name, data_rows):
        """Append rows, retrying transient Sheets failures (5xx/429/timeout).

        A single HTTP 503 here once silently lost a whole day of history, so a
        transient failure must never be treated as final. Returns the API result,
        or None if it kept failing.
        """
        body = {"values": data_rows, "majorDimension": "ROWS"}
        delay = self.WRITE_RETRY_BACKOFF
        last_error = None
        for attempt in range(self.WRITE_RETRIES + 1):
            try:
                return self.sheet.values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A:H",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                ).execute()
            except HttpError as e:
                status = getattr(getattr(e, "resp", None), "status", None)
                last_error = e
                if status not in (429, 500, 502, 503, 504) or attempt >= self.WRITE_RETRIES:
                    raise
                logger.warning(f"Sheets append failed (HTTP {status}); retrying in "
                               f"{delay:.1f}s ({attempt + 1}/{self.WRITE_RETRIES})")
            except (TimeoutError, OSError) as e:
                last_error = e
                if attempt >= self.WRITE_RETRIES:
                    raise
                logger.warning(f"Sheets append failed ({e}); retrying in "
                               f"{delay:.1f}s ({attempt + 1}/{self.WRITE_RETRIES})")
            time.sleep(delay)
            delay *= 2
        logger.error(f"Sheets append gave up after {self.WRITE_RETRIES} retries: {last_error}")
        return None
```

- [ ] **Step 4: Implement `save_rebuilt_balances`**

```python
    def save_rebuilt_balances(self, date_str, rows):
        """Write rebuilt balances into the daily record for `date_str`.

        These fill a hole in the history so the date never needs rebuilding again.
        They are marked "rebuilt" so they stay distinguishable from figures that
        were actually measured on the day.

        rows: [{"name", "company", "address", "balance"}]
        Returns (success, batch_id).
        """
        if not rows:
            return False, None
        if not self.credentials_file or not self.spreadsheet_id:
            logger.warning("Google Sheets not configured; rebuilt balances not saved")
            return False, None
        try:
            if not self._initialize_service():
                return False, None
            batch_id = self._generate_batch_id()
            now = datetime.now(timezone(timedelta(hours=7)))
            data_rows = [[
                batch_id,
                date_str,                       # the date these balances describe
                now.strftime("%H:%M:%S"),       # when we worked them out
                r["name"],
                r.get("company", "Unknown"),
                r.get("address", ""),
                f"{r['balance']:.2f}",
                "rebuilt",
            ] for r in rows]
            self._ensure_headers("DAILY_REPORT")
            if self._append_rows_with_retry("DAILY_REPORT", data_rows) is None:
                return False, None
            logger.info(f"✅ Saved {len(data_rows)} rebuilt balances for {date_str} "
                        f"(batch {batch_id})")
            return True, batch_id
        except Exception as e:
            logger.error(f"Failed to save rebuilt balances for {date_str}: {e}")
            return False, None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_save_rebuilt.py tests/test_snapshot.py -v`
Expected: PASS (all — `test_snapshot.py` proves the extraction didn't break the retry behaviour)

- [ ] **Step 6: Commit**

```bash
git add bot/services/google_sheets_logger.py tests/test_save_rebuilt.py
git commit -m "feat(vault): save_rebuilt_balances so a rebuilt date fills itself in"
```

---

### Task 4: Per-wallet resolution core

**Files:**
- Modify: `bot/handlers/check_handler.py`
- Test: `tests/test_wallet_resolution.py` (create)

**Interfaces:**
- Consumes: `canonical_address` (chain_detector); `resolve_fuzzy` returning `(matches, tier)` (Task 1).
- Produces: `CheckHandler.classify_wallets(roster, snapshot, date_str) -> list[dict]`.
  Each dict: `{"name", "company", "address", "chain", "status", "balance"}` with
  `status` ∈ `"saved" | "removed_but_saved" | "needs_rebuild" | "not_yet_created"`
  and `balance` a `Decimal` for the saved statuses, else `None`.
  `roster` items: `{"wallet", "company", "address", "chain", "created_at"}`.
  `snapshot`: `{canonical_address: {"wallet_name", "company", "address", "balance", ...}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wallet_resolution.py
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

ROSTER = [
    {"wallet": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
     "created_at": "2026-01-01 00:00:00"},
    {"wallet": "KZO ERC A 1", "company": "KZO", "address": "0xABC", "chain": "ERC20",
     "created_at": "2026-01-01 00:00:00"},
    {"wallet": "New Wallet", "company": "KZP", "address": "TNEW", "chain": "TRC20",
     "created_at": "2026-07-24 15:15:55"},
]

def snap(*items):   # (canonical_address, name, company, balance)
    return {a: {"wallet_name": n, "company": c, "address": a, "balance": Decimal(b),
                "batch_id": "20260715000112", "time": "00:01:12"} for a, n, c, b in items}

def by_name(rows):
    return {r["name"]: r for r in rows}

def test_saved_wallet_uses_its_figure():
    rows = H.classify_wallets(ROSTER, snap(("TAAA", "KZP 96G1", "KZP", "19.41")), "2026-07-15")
    r = by_name(rows)["KZP 96G1"]
    assert r["status"] == "saved" and r["balance"] == Decimal("19.41")

def test_missing_wallet_needs_rebuild():
    rows = H.classify_wallets(ROSTER, snap(("TAAA", "KZP 96G1", "KZP", "19.41")), "2026-07-15")
    r = by_name(rows)["KZO ERC A 1"]
    assert r["status"] == "needs_rebuild" and r["balance"] is None
    assert r["chain"] == "ERC20"          # carried through for the rebuild call

def test_wallet_created_after_the_date():
    rows = H.classify_wallets(ROSTER, snap(("TAAA", "KZP 96G1", "KZP", "19.41")), "2026-07-15")
    assert by_name(rows)["New Wallet"]["status"] == "not_yet_created"

def test_wallet_created_before_the_date_is_expected():
    rows = H.classify_wallets(ROSTER, {}, "2026-07-25")     # after New Wallet was added
    assert by_name(rows)["New Wallet"]["status"] == "needs_rebuild"

def test_removed_wallet_with_a_balance_is_kept():
    # 'Cold wallet' is in the saved record but no longer in wallets.json
    s = snap(("TAAA", "KZP 96G1", "KZP", "19.41"), ("TOLD", "Cold wallet", "S5", "1250.00"))
    r = by_name(H.classify_wallets(ROSTER, s, "2026-07-15"))["Cold wallet"]
    assert r["status"] == "removed_but_saved" and r["balance"] == Decimal("1250.00")

def test_unparseable_created_at_is_treated_as_existing():
    roster = [{"wallet": "Odd", "company": "KZP", "address": "TODD", "chain": "TRC20",
               "created_at": "TBD"}]
    assert H.classify_wallets(roster, {}, "2026-07-15")[0]["status"] == "needs_rebuild"

def test_erc20_address_case_is_ignored():
    s = snap(("0xabc", "KZO ERC A 1", "KZO", "29629.90"))    # snapshot key lowercased
    r = by_name(H.classify_wallets(ROSTER, s, "2026-07-15"))["KZO ERC A 1"]
    assert r["status"] == "saved"          # matched despite roster having 0xABC
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_wallet_resolution.py -v`
Expected: FAIL with `AttributeError: 'CheckHandler' object has no attribute 'classify_wallets'`

- [ ] **Step 3: Implement `classify_wallets`**

Add to `CheckHandler` in `bot/handlers/check_handler.py`:

```python
    def classify_wallets(self, roster, snapshot, date_str):
        """Decide, per wallet, what we can show for `date_str`. Pure - no network.

        wallets.json is the source of truth for which wallets exist, but a wallet
        that was removed since can still hold a real balance on a past date, so it
        is kept (otherwise that day's total would silently shrink).

        status: saved              - a figure was recorded that day
                removed_but_saved  - as above, but no longer in wallets.json
                needs_rebuild      - existed then, no figure recorded -> work it out
                not_yet_created    - added after this date, so it has no balance
        """
        out = []
        seen = set()
        for w in roster:
            key = canonical_address(w.get("address", ""))
            seen.add(key)
            entry = snapshot.get(key)
            if entry:
                status, balance = "saved", entry["balance"]
            elif self._existed_by(w.get("created_at"), date_str):
                status, balance = "needs_rebuild", None
            else:
                status, balance = "not_yet_created", None
            out.append({"name": w.get("wallet"), "company": w.get("company", "Unknown"),
                        "address": w.get("address", ""), "chain": w.get("chain", "TRC20"),
                        "status": status, "balance": balance})

        # figures recorded that day for wallets that are no longer on the list
        for key, entry in snapshot.items():
            if key in seen:
                continue
            out.append({"name": entry["wallet_name"], "company": entry.get("company", "Unknown"),
                        "address": entry.get("address", ""), "chain": "TRC20",
                        "status": "removed_but_saved", "balance": entry["balance"]})
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_wallet_resolution.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/check_handler.py tests/test_wallet_resolution.py
git commit -m "feat(check): per-wallet resolution against a date"
```

---

### Task 5: Wire the handler — rebuild only what's missing, save it back

**Files:**
- Modify: `bot/handlers/check_handler.py`
- Test: `tests/test_check_historical_wiring.py`

**Interfaces:**
- Consumes: `classify_wallets` (Task 4), `save_rebuilt_balances` (Task 3),
  `get_snapshot_and_nearest` (existing), `resolve_fuzzy -> (matches, tier)` (Task 1),
  `balance_service.get_balance_at(address, chain, cutoff_ms)` (existing).
- Produces: `_handle_historical` behaviour per the spec; `view` dict gains
  `"counted"`, `"rebuilt"`, `"removed"`, `"not_yet"`, `"failed"`, `"saved_batch"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_check_historical_wiring.py`:

```python
def test_only_missing_wallets_are_rebuilt_and_saved():
    """A wallet with a saved figure must not be rebuilt; the missing one is
    rebuilt AND written back so the date fills itself in."""
    saved = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                      "balance": Decimal("19.41"), "batch_id": "20260720000112",
                      "time": "00:01:12"}}
    rebuilt_for, saved_rows = [], {}
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_snapshot_and_nearest = lambda d: (saved, None, {})

    def fake_rebuild(addr, chain, cutoff):
        rebuilt_for.append(addr)
        return Decimal("10.00")
    h.balance_service.get_balance_at = fake_rebuild
    h.sheets_logger.save_rebuilt_balances = (
        lambda date_str, rows: saved_rows.update(date=date_str, rows=rows) or (True, "B123"))

    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert rebuilt_for == ["0xabc0000000000000000000000000000000000001"]  # ONLY the missing one
    assert [r["name"] for r in saved_rows["rows"]] == ["Eth One"]
    assert saved_rows["date"] == "2026-07-20"
    assert "29.41" in blob                       # 19.41 saved + 10.00 rebuilt
    assert "B123" in blob                        # batch id shown on the card


def test_nothing_saved_when_nothing_was_rebuilt():
    saved = {"TAAA": {"wallet_name": "KZP 96G1", "company": "KZP", "address": "TAAA",
                      "balance": Decimal("19.41"), "batch_id": "b", "time": "t"},
             "0xabc0000000000000000000000000000000000001": {
                 "wallet_name": "Eth One", "company": "KZO",
                 "address": "0xabc0000000000000000000000000000000000001",
                 "balance": Decimal("5.00"), "batch_id": "b", "time": "t"}}
    calls = []
    h = CheckHandler()
    h.wallet_service.list_wallets = lambda: (True, ROSTER)
    h.sheets_logger.get_snapshot_and_nearest = lambda d: (saved, None, {})
    h.sheets_logger.save_rebuilt_balances = lambda d, r: calls.append(r) or (True, "X")
    blob = _blob(_run(h, ["[2026-07-20]"])[-1])
    assert calls == []                           # nothing to save -> no write
    assert "saved to Google Sheets" not in blob  # and no footer line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_check_historical_wiring.py -v`
Expected: FAIL — the handler still uses the old snapshot-or-rebuild branch

- [ ] **Step 3: Replace the body of `_handle_historical`**

Keep the date validation and the acknowledgement send at the top. Replace everything from
`snapshot, nearest_date, nearest_snapshot = ...` down to (but not including) the final
`await context.topic_manager.send_command_response(card, ...)` with:

```python
        snapshot, _nearest_date, _nearest_snapshot = \
            self.sheets_logger.get_snapshot_and_nearest(date_str)

        roster = [{"wallet": i["wallet"], "company": i["company"], "address": i["address"],
                   "chain": i.get("chain", "TRC20"), "created_at": i.get("created_at")}
                  for i in wallet_data.values()]

        entries = self.classify_wallets(roster, snapshot, date_str)
        entries, fuzzy, not_found = self._filter_entries(entries, groups, names)

        todo = [e for e in entries if e["status"] == "needs_rebuild"]
        if todo:
            await context.topic_manager.send_command_response(
                self._create_rebuilding_card(date_str, len(todo)), msg_type="interactive")
            cutoff_ms = int(datetime.strptime(date_str + " 00:01:00", "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
            await self._rebuild_entries(todo, cutoff_ms)

        # Persist whatever we worked out, so this date never needs rebuilding again.
        # Partial is fine: a later check rebuilds only what is still missing.
        fresh = [e for e in entries if e["status"] == "rebuilt"]
        saved_batch = None
        if fresh:
            ok, batch = self.sheets_logger.save_rebuilt_balances(date_str, [
                {"name": e["name"], "company": e["company"],
                 "address": e["address"], "balance": e["balance"]} for e in fresh])
            saved_batch = batch if ok else None

        card = self._create_historical_card(entries, date_str, fuzzy, not_found, saved_batch)
```

- [ ] **Step 4: Add the rebuild executor and the entry filter**

```python
    async def _rebuild_entries(self, entries, cutoff_ms):
        """Work out each entry's balance from chain history, in place.

        Runs on a dedicated pool so slow lookups can never occupy the executor the
        live /check path uses, and is bounded overall so the command lock is never
        held indefinitely. Anything unfinished is marked failed, never dropped.
        """
        loop = asyncio.get_event_loop()
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.RECON_CONCURRENCY, thread_name_prefix="recon")
        try:
            fut_to_entry = {}
            for e in entries:
                f = loop.run_in_executor(pool, self.balance_service.get_balance_at,
                                         e["address"], e.get("chain", "TRC20"), cutoff_ms)
                fut_to_entry[f] = e
            done, pending = await asyncio.wait(list(fut_to_entry.keys()),
                                               timeout=self.RECON_TOTAL_BUDGET)
            for f in pending:
                f.cancel()
                fut_to_entry[f]["status"] = "failed"
            for f in done:
                e = fut_to_entry[f]
                try:
                    bal = f.result()
                except Exception as exc:
                    logger.error(f"Rebuild failed for {e['name']}: {exc}")
                    bal = None
                if bal is None:
                    e["status"] = "failed"
                else:
                    e["status"], e["balance"] = "rebuilt", bal
        finally:
            pool.shutdown(wait=False)

    def _filter_entries(self, entries, groups, names):
        """Apply company/wallet-name filters. Returns (entries, fuzzy, not_found)."""
        if groups:
            wanted = {g.lower() for g in groups}
            entries = [e for e in entries if e["company"].lower() in wanted]
        fuzzy, not_found = {}, []
        if names:
            all_names = [e["name"] for e in entries]
            picked, seen = [], set()
            for want in names:
                matches, tier = resolve_fuzzy(want, all_names)
                if not matches:
                    not_found.append(want)
                    continue
                if tier == "closest match":
                    fuzzy[want] = matches
                for e in entries:
                    if e["name"] in matches and id(e) not in seen:
                        seen.add(id(e))
                        picked.append(e)
            entries = picked
        return entries, fuzzy, not_found
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_check_historical_wiring.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/check_handler.py tests/test_check_historical_wiring.py
git commit -m "feat(check): rebuild only missing wallets and save them back"
```

---

### Task 6: Cards — acknowledgement, summary, footer, wording

**Files:**
- Modify: `bot/handlers/check_handler.py`
- Test: `tests/test_check_cards.py` (create)

**Interfaces:**
- Consumes: entries from Task 4/5.
- Produces: `_create_historical_card(entries, date_str, fuzzy, not_found, saved_batch) -> dict`;
  `_create_historical_checking_card(date_str, groups, names, matched) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_cards.py
import json
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

def blob(c): return json.dumps(c)

ENTRIES = [
    {"name": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20",
     "status": "saved", "balance": Decimal("19.41")},
    {"name": "Eth One", "company": "KZO", "address": "0xabc", "chain": "ERC20",
     "status": "rebuilt", "balance": Decimal("10.00")},
    {"name": "Cold wallet", "company": "S5", "address": "TOLD", "chain": "TRC20",
     "status": "removed_but_saved", "balance": Decimal("1250.00")},
    {"name": "New Wallet", "company": "KZP", "address": "TNEW", "chain": "TRC20",
     "status": "not_yet_created", "balance": None},
]

def test_summary_counts_only_wallets_with_a_figure():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], "B1"))
    assert "3 wallets counted" in b          # saved + rebuilt + removed_but_saved
    assert "1,279.41" in b                   # 19.41 + 10.00 + 1250.00

def test_added_later_is_listed_but_not_counted():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))
    assert "New Wallet" in b
    assert "added after this date" in b

def test_removed_wallet_is_marked():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))
    assert "no longer in your list" in b

def test_saved_batch_shown_only_when_something_saved():
    assert "B1" in blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, [], "B1"))
    assert "saved to Google Sheets" not in blob(
        H._create_historical_card(ENTRIES, "2026-07-15", {}, [], None))

def test_failed_wallet_reported_not_dropped():
    entries = ENTRIES + [{"name": "Busy", "company": "KZP", "address": "TB", "chain": "TRC20",
                          "status": "failed", "balance": None}]
    b = blob(H._create_historical_card(entries, "2026-07-15", {}, [], None))
    assert "Busy" in b and "could not be worked out" in b

def test_not_found_message_is_plain():
    b = blob(H._create_historical_card(ENTRIES, "2026-07-15", {}, ["ZZZ QQQ"], None))
    assert 'Wallet "ZZZ QQQ" not found.' in b

def test_ack_card_echoes_what_was_understood():
    b = blob(H._create_historical_checking_card("2026-07-20", ["DPP"], [], 1))
    assert "2026-07-20" in b and "DPP" in b and "Matched 1 wallet" in b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_check_cards.py -v`
Expected: FAIL — `_create_historical_card` still takes the old `(view, date_str, reconstructed)` signature

- [ ] **Step 3: Rewrite the acknowledgement card**

```python
    def _create_historical_checking_card(self, date_str, groups=None, names=None, matched=None):
        """Confirm what the bot understood, before any waiting begins."""
        lines = [f"📅 **Date:** {date_str}"]
        if groups:
            lines.append(f"🏢 **Company:** {', '.join(groups)}")
        if names:
            lines.append(f"👛 **Wallets:** {', '.join(names)}")
        if matched is not None:
            lines.append(f"🔎 **Matched {matched} {'wallet' if matched == 1 else 'wallets'}**")
        lines.append("\nReading saved balances; anything missing will be rebuilt.")
        return {
            "config": {"wide_screen_mode": True, "enable_forward": False},
            "header": {"template": "blue",
                       "title": {"tag": "plain_text", "content": "🔄 Checking Balances..."}},
            "elements": [{"tag": "div",
                          "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
        }
```

- [ ] **Step 4: Rewrite the result card**

Replace `_create_historical_card` with:

```python
    def _create_historical_card(self, entries, date_str, fuzzy, not_found, saved_batch):
        """Balance table for a past date, plus a plain account of where each figure came from."""
        counted = [e for e in entries if e["balance"] is not None]
        rows = [{"name": e["name"], "company": e["company"], "address": e["address"],
                 "balance": e["balance"], "source": e["status"]} for e in counted]

        balances, wallets_to_check = {}, {}
        for r in rows:
            key = r["name"]
            if key in balances:
                key = f'{r["name"]} [{canonical_address(r["address"])}]'
                n = 2
                while key in balances:
                    key = f'{r["name"]} [{canonical_address(r["address"])}] #{n}'
                    n += 1
            balances[key] = r["balance"]
            wallets_to_check[key] = {"company": r["company"]}

        base_card = self._create_balance_table_card_with_sheets_info(
            balances, wallets_to_check, time_str=date_str,
            not_found=[], sheets_logged=False, batch_id=None)
        table_elements = base_card["elements"][3:]

        n_saved = sum(1 for e in counted if e["status"] == "saved")
        n_rebuilt = sum(1 for e in counted if e["status"] == "rebuilt")
        n_removed = sum(1 for e in counted if e["status"] == "removed_but_saved")
        parts = []
        if n_saved:
            parts.append(f"{n_saved} saved")
        if n_rebuilt:
            parts.append(f"{n_rebuilt} rebuilt")
        if n_removed:
            parts.append(f"{n_removed} no longer in your list")
        summary = (f"📊 **{len(counted)} {'wallet' if len(counted) == 1 else 'wallets'} counted**"
                   + (" — " + ", ".join(parts) if parts else ""))

        header_elements = [{"tag": "div", "text": {"tag": "lark_md", "content": summary}}]

        later = [e["name"] for e in entries if e["status"] == "not_yet_created"]
        if later:
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f"➕ **{len(later)} more were added after this date**, so they have no balance "
                f"yet: {', '.join(later)}"}})

        failed = [e["name"] for e in entries if e["status"] == "failed"]
        if failed:
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f"🚫 **Could not be worked out** (not counted): {', '.join(failed)}"}})

        removed = [e["name"] for e in counted if e["status"] == "removed_but_saved"]
        if removed:
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f"📌 **No longer in your list** but held a balance that day, so still "
                f"counted: {', '.join(removed)}"}})

        for want, matches in (fuzzy or {}).items():
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f'🔍 Showing **{", ".join(matches)}** — closest match to "{want}".'}})

        for want in (not_found or []):
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f'❌ Wallet "{want}" not found.'}})

        header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
            f"⏰ **Time:** {self.balance_service.get_current_gmt_time()} GMT+7"}})

        if saved_batch:
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f"📈 **{n_rebuilt} rebuilt {'balance' if n_rebuilt == 1 else 'balances'} "
                f"saved to Google Sheets** (Batch ID: {saved_batch})"}})

        base_card["elements"] = header_elements + table_elements
        grand_total = sum(balances.values()) if balances else Decimal("0")
        base_card["header"] = {
            "template": "purple" if n_rebuilt else "blue",
            "title": {"tag": "plain_text", "content": "🕰️ Historical Wallet Balance Check"},
            "subtitle": {"tag": "plain_text",
                         "content": f"{date_str} · Total: {grand_total:,.2f} USDT"},
        }
        return base_card
```

- [ ] **Step 5: Update the acknowledgement call site**

In `_handle_historical`, the acknowledgement is currently sent before filters are known. Move it to
just after `entries, fuzzy, not_found = self._filter_entries(...)` so it can report the match count:

```python
        await context.topic_manager.send_command_response(
            self._create_historical_checking_card(date_str, groups, names, len(entries)),
            msg_type="interactive")
```

- [ ] **Step 6: Bold the example in the bracket hint**

In `_create_bracket_hint_card`, replace the backticked examples with bold:

```python
                        "content": "⚠️ **Part of your command wasn't recognized and was ignored.**\n\n"
                                   f"Wrap the date (and any filter) in brackets, like "
                                   f"**/check [{date_str}]** for a date on its own, or "
                                   f"**/check [{date_str}] [KZP]** to also filter by company "
                                   "or wallet name."
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all)

- [ ] **Step 8: Commit**

```bash
git add bot/handlers/check_handler.py tests/test_check_cards.py
git commit -m "feat(check): clearer cards - ack echoes filters, summary counts, saved footer"
```

---

### Task 7: `/add` + `/remove` reproduction tests and live verification

**Files:**
- Test: `tests/test_add_remove_repro.py` (create)
- Modify: `bot/handlers/help_handler.py`

**Interfaces:**
- Consumes: `RemoveHandler._match_address` (existing), `AddHandler.parse_quoted_arguments` (existing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_add_remove_repro.py
"""Reproduces the bug reported in request.txt:
     /remove "Cold wallet"                          -> worked
     /remove "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071" -> did NOT work
"""
from bot.handlers.remove_handler import RemoveHandler
from bot.handlers.add_handler import AddHandler

BUG_ADDRESS = "0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071"
WALLETS = [{"name": "KZG TEST WALLET", "address": BUG_ADDRESS, "company": "TEST"},
           {"name": "Cold wallet", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "company": "S5"}]

R, A = RemoveHandler(), AddHandler()

def test_remove_by_name_brackets():
    ok, val = R.parse_single_quoted_argument("[Cold wallet]")
    assert ok and val == "Cold wallet"

def test_remove_by_name_quotes():
    ok, val = R.parse_single_quoted_argument('"Cold wallet"')
    assert ok and val == "Cold wallet"

def test_remove_by_the_reported_address_brackets():
    ok, val = R.parse_single_quoted_argument(f"[{BUG_ADDRESS}]")
    assert ok and val == BUG_ADDRESS
    assert R._match_address(val, WALLETS)["name"] == "KZG TEST WALLET"

def test_remove_by_the_reported_address_quotes():
    ok, val = R.parse_single_quoted_argument(f'"{BUG_ADDRESS}"')
    assert ok and val == BUG_ADDRESS
    assert R._match_address(val, WALLETS)["name"] == "KZG TEST WALLET"

def test_reported_address_matches_case_insensitively():
    assert R._match_address(BUG_ADDRESS.lower(), WALLETS)["name"] == "KZG TEST WALLET"

def test_add_accepts_the_reported_address_in_brackets():
    ok, res = A.parse_quoted_arguments(f"[TEST] [KZG TEST WALLET] [{BUG_ADDRESS}]")
    assert ok and res == ["TEST", "KZG TEST WALLET", BUG_ADDRESS]

def test_add_still_accepts_quotes():
    ok, res = A.parse_quoted_arguments(f'"TEST" "KZG TEST WALLET" "{BUG_ADDRESS}"')
    assert ok and res[2] == BUG_ADDRESS
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_add_remove_repro.py -v`
Expected: PASS — Task 2 already fixed the parsing; these lock the reported bug shut.
If any fail, the fix is incomplete — return to Task 2.

- [ ] **Step 3: Update the help card to bracket form**

In `bot/handlers/help_handler.py`, both `_create_help_card` and `_get_help_text_fallback`:
change the `/remove` line to `• **/remove [wallet name or address]** - Remove a wallet` and the
`/add` line to `• **/add [company] [wallet name] [address]** - Add a new wallet`.
Verify: `grep -n 'remove "' bot/handlers/help_handler.py` returns nothing.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all)

- [ ] **Step 5: Live verification against the dev bot**

Restart the dev bot, then run these and confirm against `DEV_TEST_PLAN.md`:

```bash
pkill -f lark_bot.py; sleep 2
cd /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/crypto-lark-bot
.venv/bin/python lark_bot.py &
```

Check in Lark: `/check [2026-07-15]` (69 counted + 3 added later), `/check [2026-07-15] [DPP COY]`
(only `DPP COY TRC`), `/remove [0xdac17f958d2ee523a2206206994597c13d831ec7]` (not-found, not a
parse error), and section H of the test plan.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/help_handler.py tests/test_add_remove_repro.py
git commit -m "test: reproduce the request.txt /remove address bug; help card brackets"
```

---

## Self-Review

**Spec coverage:** §2 wallet-level resolution → Tasks 4, 5. §2 self-completing save → Tasks 3, 5.
§3 fuzzy → Task 1. §4.1 ack → Task 6. §4.2 result card → Task 6. §4.3 wording → Tasks 2, 6.
§5 `/remove` + reproduction → Tasks 2, 7. §6 code changes → all tasks. §7 testing → each task's
tests plus Task 7 step 5.

**Placeholders:** none — every step carries the code or the exact command.

**Type consistency:** `resolve_fuzzy -> (list, tier)` defined in Task 1, consumed in Task 5's
`_filter_entries`. `classify_wallets -> list[dict]` with `status`/`balance` defined in Task 4,
consumed in Tasks 5 and 6. `save_rebuilt_balances(date_str, rows) -> (ok, batch_id)` defined in
Task 3, called in Task 5, its batch shown in Task 6. `_create_historical_card(entries, date_str,
fuzzy, not_found, saved_batch)` defined in Task 6, called in Task 5 — same argument order.

**Note for the implementer:** Task 5 changes `_create_historical_card`'s signature and Task 6
implements it. If Task 5 is run alone the suite will be red until Task 6 lands; run them back to
back, or implement Task 6's card first if working out of order.
