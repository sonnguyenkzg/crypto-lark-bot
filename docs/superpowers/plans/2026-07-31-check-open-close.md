# Opening/Closing Balances for `/check [date]` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/check [D]` returns the day's closing balance, `[o]` the opening, `[c]` the closing — implemented as a date translation over the existing pipeline — plus a corrected wallet-existence rule.

**Architecture:** Two new pure functions decide *which vault date* to read (`target_date_for`) and *when each wallet started existing* (`build_first_seen`). The existing dated-check pipeline then runs unchanged against that target date. No new balance logic and no new blockchain calls: `closing(D)` is simply the row dated `D+1`, which the vault already holds.

**Tech Stack:** Python 3.12, pytest, Google Sheets API v4, Lark interactive cards.

Spec: `docs/superpowers/specs/2026-07-31-check-open-close-design.md`

## Global Constraints

- **Modifier tokens** (case-insensitive): `o`, `opening` → opening; `c`, `closing` → closing. **`open` and `close` are NOT modifiers** — they resolve to real wallets today via fuzzy matching (`open` → `KZO PEN SETTLE TRC 1`, `close` → `KZO SETTLE OPS TRC 1`) and must keep filtering.
- **Default mode is `closing`.** A bare `/check [D]` returns closing.
- `closing(D)` = the vault row dated `D + 1 day`. `opening(D)` = the vault row dated `D`.
- **Existence rule:** `first_seen = min(created_at when present, earliest DAILY_REPORT row for that wallet)`; a wallet counts on date X only when `first_seen <= X`. When neither signal exists, fall back to today's behaviour (assume it existed).
- **Never break the guarantee:** a wallet holding a row on X must never be excluded on X.
- Scope is `wallets.json` only — a wallet no longer monitored is ignored even if the vault holds a figure for it.
- Card copy rules, already settled: wallet name before status, **bold** names (never backticks), plain language, no jargon, no duplicated date, "Total wallets in monitoring: 71".
- All existing tests must keep passing. Baseline is **134 passing**.
- Work on branch `feature/check-date-and-remove-fix`. Never edit files on the production box.
- Run tests with `.venv/bin/python -m pytest`. `tests/conftest.py` blanks the real Google credentials — never bypass it, or the suite writes to the production sheet.

---

## File Structure

| File | Responsibility |
|---|---|
| `bot/services/command_args.py` (modify) | Token parsing. Gains `extract_mode` — splitting basis modifiers out of the token list. Already owns `parse_arguments`, `split_date`, `classify_tokens`. |
| `bot/services/vault_calendar.py` (**create**) | Vault calendar semantics, pure and network-free: which date holds a requested figure, and when each wallet started existing. |
| `bot/services/google_sheets_logger.py` (modify) | Gains `get_history_bundle` so one sheet read yields the snapshot *and* the first-seen map. `get_snapshot_and_nearest` becomes a thin wrapper — one read path, no duplication. |
| `bot/handlers/check_handler.py` (modify) | Wiring: extract mode, translate the date, apply the guards, pass `first_seen` into `classify_wallets`, and state the basis on the cards. |
| `bot/handlers/help_handler.py` (modify) | Teach the new grammar. |
| `tests/test_command_args_mode.py` (create) | `extract_mode` + bracket-spacing regression. |
| `tests/test_vault_calendar.py` (create) | `target_date_for` + `build_first_seen`. |
| `tests/test_check_open_close.py` (create) | Handler wiring, guards, and card copy. |

---

### Task 1: `extract_mode` — split basis modifiers out of the tokens

**Files:**
- Modify: `bot/services/command_args.py`
- Test: `tests/test_command_args_mode.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `extract_mode(tokens: list[str]) -> tuple[str | None, list[str], bool]` returning `(mode, rest, conflict)` where `mode` is `"opening" | "closing" | None`, `rest` is the tokens with every modifier removed (order preserved), and `conflict` is `True` when both an opening and a closing modifier were supplied. Also exports the frozensets `OPENING_TOKENS` and `CLOSING_TOKENS`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_command_args_mode.py`:

```python
# tests/test_command_args_mode.py
"""Basis modifiers ([o]/[c]) are pulled out of the token list before filtering.

`open` and `close` are deliberately NOT modifiers: both resolve to real wallets today
via fuzzy matching (`open` -> KZO PEN SETTLE TRC 1 by "contains", `close` -> KZO SETTLE
OPS TRC 1 by closest match), so treating them as modifiers would shadow real filters.
"""
import pytest

from bot.services.command_args import extract_mode, parse_arguments


@pytest.mark.parametrize("tokens,expected", [
    ([],                      None),
    (["o"],                   "opening"),
    (["O"],                   "opening"),
    (["opening"],             "opening"),
    (["OPENING"],             "opening"),
    (["  o  "],               "opening"),
    (["c"],                   "closing"),
    (["C"],                   "closing"),
    (["closing"],             "closing"),
    (["CLOSING"],             "closing"),
])
def test_recognised_spellings(tokens, expected):
    mode, rest, conflict = extract_mode(tokens)
    assert mode == expected
    assert rest == []
    assert conflict is False


@pytest.mark.parametrize("token", ["open", "close", "OPEN", "Close", "opened", "closes"])
def test_open_and_close_are_not_modifiers(token):
    """These must fall through to the filter -- they match real wallets."""
    mode, rest, conflict = extract_mode([token])
    assert mode is None
    assert rest == [token]
    assert conflict is False


def test_position_independent():
    assert extract_mode(["KZP", "c"]) == ("closing", ["KZP"], False)
    assert extract_mode(["c", "KZP"]) == ("closing", ["KZP"], False)
    assert extract_mode(["KZDW", "o", "KZP TH BM 1"]) == (
        "opening", ["KZDW", "KZP TH BM 1"], False)


def test_repeating_the_same_modifier_is_not_a_conflict():
    assert extract_mode(["o", "o"]) == ("opening", [], False)
    assert extract_mode(["o", "opening"]) == ("opening", [], False)
    assert extract_mode(["c", "CLOSING", "c"]) == ("closing", [], False)


def test_opening_and_closing_together_is_a_conflict():
    mode, rest, conflict = extract_mode(["o", "c"])
    assert conflict is True
    assert mode is None


def test_conflict_still_returns_the_remaining_filters():
    """The caller shows an error, but rest must be intact for any diagnostics."""
    mode, rest, conflict = extract_mode(["KZP", "o", "c"])
    assert conflict is True
    assert rest == ["KZP"]


def test_filters_are_untouched_when_no_modifier_present():
    toks = ["KZDW", "KZP TH BM 1", "OKKZ"]
    assert extract_mode(toks) == (None, toks, False)


# --- bracket spacing: already works, locked in so it cannot regress ---

@pytest.mark.parametrize("raw", [
    "[2026-07-15] [DPP COY]",
    "[2026-07-15][DPP COY]",
    "[2026-07-15]  [DPP COY]",
    "  [2026-07-15]   [DPP COY]  ",
])
def test_bracket_spacing_is_irrelevant(raw):
    tokens, had_bare = parse_arguments(raw)
    assert tokens == ["2026-07-15", "DPP COY"]
    assert had_bare is False


def test_three_adjacent_brackets():
    tokens, had_bare = parse_arguments("[2026-07-15][c][KZDW]")
    assert tokens == ["2026-07-15", "c", "KZDW"]
    assert had_bare is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_command_args_mode.py -q`
Expected: FAIL — `ImportError: cannot import name 'extract_mode'`.

- [ ] **Step 3: Implement `extract_mode`**

Append to `bot/services/command_args.py`:

```python
# Balance-basis modifiers for /check [date]. Deliberately NOT "open"/"close": both
# resolve to real wallets through fuzzy matching today ("open" -> KZO PEN SETTLE TRC 1
# by contains, "close" -> KZO SETTLE OPS TRC 1 by closest match), so claiming them as
# modifiers would silently take a working filter away.
OPENING_TOKENS = frozenset({"o", "opening"})
CLOSING_TOKENS = frozenset({"c", "closing"})


def extract_mode(tokens):
    """Split balance-basis modifiers out of a token list.

    Returns (mode, rest, conflict):
      mode      "opening" | "closing" | None   -- None means the caller applies its default
      rest      tokens with every modifier removed, original order preserved
      conflict  True when BOTH an opening and a closing modifier were given

    Position-independent, case-insensitive, and repetition-tolerant: [o][o] and
    [o][opening] both mean opening, because repeating yourself is not a contradiction.
    """
    rest, modes = [], set()
    for t in tokens:
        key = t.strip().lower()
        if key in OPENING_TOKENS:
            modes.add("opening")
        elif key in CLOSING_TOKENS:
            modes.add("closing")
        else:
            rest.append(t)
    if len(modes) > 1:
        return None, rest, True
    return (modes.pop() if modes else None), rest, False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_command_args_mode.py -q`
Expected: PASS, all cases.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: 134 previous + the new ones, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add bot/services/command_args.py tests/test_command_args_mode.py
git commit -m "feat: extract_mode splits [o]/[c] basis modifiers out of the tokens

Case-insensitive, position-independent, repetition-tolerant. Excludes open/close,
which resolve to real wallets via fuzzy matching and must keep filtering.

Also locks in bracket-spacing behaviour with tests -- [a][b] and [a] [b] already
parse identically, and that must not regress."
```

---

### Task 2: `target_date_for` — which vault date holds the requested figure

**Files:**
- Create: `bot/services/vault_calendar.py`
- Test: `tests/test_vault_calendar.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `target_date_for(date_str: str, mode: str) -> str`. `mode` is `"opening"` or `"closing"`. Returns an ISO `YYYY-MM-DD` string.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vault_calendar.py`:

```python
# tests/test_vault_calendar.py
"""The vault stores one figure per date: the balance at 00:00 GMT+7 that morning.

So the OPENING of D is the row dated D, and the CLOSING of D -- the balance at the end
of D -- is the same instant as 00:00 GMT+7 on D+1, which is the row dated D+1.
"""
import pytest

from bot.services.vault_calendar import target_date_for


@pytest.mark.parametrize("date_str", ["2026-07-15", "2025-09-22", "2026-02-28"])
def test_opening_is_the_same_date(date_str):
    assert target_date_for(date_str, "opening") == date_str


@pytest.mark.parametrize("date_str,expected", [
    ("2026-07-15", "2026-07-16"),
    ("2026-07-30", "2026-07-31"),
    ("2026-07-31", "2026-08-01"),   # month boundary
    ("2026-12-31", "2027-01-01"),   # year boundary
    ("2028-02-28", "2028-02-29"),   # leap year
    ("2026-02-28", "2026-03-01"),   # non-leap year
])
def test_closing_is_the_next_date(date_str, expected):
    assert target_date_for(date_str, "closing") == expected


def test_closing_of_D_equals_opening_of_D_plus_one():
    """The property the whole feature rests on."""
    assert target_date_for("2026-07-15", "closing") == target_date_for("2026-07-16", "opening")


def test_unknown_mode_is_rejected_loudly():
    """A typo must not silently fall through to one of the two real answers."""
    with pytest.raises(ValueError):
        target_date_for("2026-07-15", "sideways")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vault_calendar.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.vault_calendar'`.

- [ ] **Step 3: Create the module**

Create `bot/services/vault_calendar.py`:

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vault_calendar.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/services/vault_calendar.py tests/test_vault_calendar.py
git commit -m "feat: target_date_for translates a requested basis to a vault date

closing(D) is the balance at the end of D, which is 00:00 GMT+7 on D+1 -- the row
the vault already holds for D+1. So closing needs no new measurement, only a date
translation. Unknown modes raise rather than silently picking one."
```

---

### Task 3: `build_first_seen` — when each wallet started existing

**Files:**
- Modify: `bot/services/vault_calendar.py`
- Test: `tests/test_vault_calendar.py`

**Interfaces:**
- Consumes: `target_date_for` from Task 2 (same module; no coupling).
- Produces: `build_first_seen(roster: list[dict], rows: list[list]) -> dict[str, str | None]` keyed by `canonical_address`. `roster` entries carry `address` and optionally `created_at`. `rows` are raw `DAILY_REPORT` rows where index 1 is the date and index 5 the address. Value is an ISO date, or `None` when neither signal exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vault_calendar.py`:

```python
from bot.services.vault_calendar import build_first_seen


def _row(date, address):
    """A DAILY_REPORT row: batch, date, time, wallet, company, address, balance, type."""
    return ["20260101000100", date, "00:00:00", "W", "CO", address, "1.00", "scheduled"]


def test_uses_created_at_when_there_are_no_rows():
    roster = [{"address": "TAAA", "created_at": "2026-03-01T09:00:00"}]
    assert build_first_seen(roster, []) == {"TAAA": "2026-03-01"}


def test_uses_the_earliest_row_when_created_at_is_missing():
    """27 of 71 real wallets have no created_at; every one has vault rows."""
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [_row("2025-10-11", "TAAA"), _row("2025-09-22", "TAAA"), _row("2026-01-05", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2025-09-22"}


def test_takes_the_minimum_when_created_at_is_later_than_real_data():
    """Real case: KZDW DPP TH 2 records created_at 2026-01-15 but has a row from 2025-12-17."""
    roster = [{"address": "TAAA", "created_at": "2026-01-15"}]
    rows = [_row("2025-12-17", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2025-12-17"}


def test_takes_the_minimum_when_created_at_is_earlier():
    """Normal case: created one evening, first snapshot the next morning."""
    roster = [{"address": "TAAA", "created_at": "2026-03-31"}]
    rows = [_row("2026-04-01", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-03-31"}


def test_none_when_neither_signal_exists():
    assert build_first_seen([{"address": "TAAA"}], []) == {"TAAA": None}


def test_erc20_addresses_match_case_insensitively():
    """0x addresses are hex, so case must not create two separate wallets."""
    roster = [{"address": "0xAbCdEf", "created_at": None}]
    rows = [_row("2026-02-02", "0xabcdef")]
    assert build_first_seen(roster, rows) == {"0xabcdef": "2026-02-02"}


def test_rows_for_other_wallets_are_ignored():
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [_row("2025-01-01", "TBBB"), _row("2026-05-05", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-05-05"}


def test_unparseable_created_at_is_ignored_rather_than_trusted():
    roster = [{"address": "TAAA", "created_at": "not-a-date"}]
    rows = [_row("2026-06-06", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-06-06"}


def test_malformed_rows_do_not_crash():
    roster = [{"address": "TAAA", "created_at": None}]
    rows = [[], ["only-one"], _row("", "TAAA"), _row("2026-07-07", ""), _row("2026-07-08", "TAAA")]
    assert build_first_seen(roster, rows) == {"TAAA": "2026-07-08"}


def test_the_guarantee_a_wallet_with_a_row_on_D_is_never_excluded_on_D():
    """first_seen includes the row's own date, so first_seen <= D always holds."""
    roster = [{"address": "TAAA", "created_at": "2099-01-01"}]   # absurdly late created_at
    rows = [_row("2026-07-15", "TAAA")]
    fs = build_first_seen(roster, rows)
    assert fs["TAAA"] <= "2026-07-15"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vault_calendar.py -q`
Expected: FAIL — `cannot import name 'build_first_seen'`.

- [ ] **Step 3: Implement it**

Append to `bot/services/vault_calendar.py` (and add the import at the top of the file:
`from bot.services.chain_detector import canonical_address`):

```python
def _iso_prefix(value):
    """The YYYY-MM-DD prefix of `value`, or None if it is absent or not a real date."""
    if not value:
        return None
    prefix = str(value)[:10]
    try:
        datetime.strptime(prefix, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return prefix


def build_first_seen(roster, rows):
    """Earliest date each wallet is known to have existed, keyed by canonical address.

        first_seen = min( created_at when present , earliest vault row for that wallet )

    Why not created_at alone -- both failure modes are real, measured on the live data:

      1. 27 of 71 wallets have no created_at at all. Treating that as "always existed"
         made 44 of 313 dates look gappy and provoked reconstruction of wallets that
         were never monitored then. All 27 have vault rows, so all 27 are inferable.
      2. created_at is sometimes LATER than data already held. KZDW DPP TH 2 records
         2026-01-15 against a measured row from 2025-12-17. Trusting created_at alone
         would hide a wallet on a date whose balance is sitting in the sheet.

    Taking the minimum keeps created_at as the primary signal while never contradicting
    recorded evidence. It also gives the guarantee the callers rely on: a wallet holding
    a row on D necessarily has first_seen <= D, so no saved balance is ever excluded.

    Returns None for a wallet with neither signal; callers treat that as "assume it
    existed", which is the safe direction and matches the previous behaviour.
    """
    earliest = {}
    for r in rows or []:
        if len(r) < 6:
            continue
        date = _iso_prefix(r[1])
        key = canonical_address(r[5])
        if not date or not key:
            continue
        if key not in earliest or date < earliest[key]:
            earliest[key] = date

    out = {}
    for w in roster:
        key = canonical_address(w.get("address", ""))
        if not key:
            continue
        candidates = [c for c in (_iso_prefix(w.get("created_at")), earliest.get(key)) if c]
        out[key] = min(candidates) if candidates else None
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vault_calendar.py -q`
Expected: PASS.

- [ ] **Step 5: Verify against the real vault (read-only, no writes)**

```bash
.venv/bin/python - <<'PY'
import os, json
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from bot.services.vault_calendar import build_first_seen
c=Credentials.from_service_account_file(os.environ['GOOGLE_CREDENTIALS_FILE'],
  scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
sh=build('sheets','v4',credentials=c).spreadsheets()
rows=sh.values().get(spreadsheetId=os.environ['GOOGLE_SHEET_ID'],
                     range='DAILY_REPORT!A:H').execute().get('values',[])[1:]
w=json.load(open("wallets.json"))
roster=w if isinstance(w,list) else list(w.values())
fs=build_first_seen(roster, rows)
print(f"wallets with a first_seen: {sum(1 for v in fs.values() if v)}/{len(fs)}")
print(f"wallets still unknown    : {sum(1 for v in fs.values() if not v)}")
print("expected: 71/71 known, 0 unknown")
PY
```
Expected: `71/71` known, `0` unknown. If any wallet is unknown, stop and report it — the spec's measured effect assumed all 71 resolve.

- [ ] **Step 6: Commit**

```bash
git add bot/services/vault_calendar.py tests/test_vault_calendar.py
git commit -m "feat: build_first_seen derives when each wallet started existing

first_seen = min(created_at when present, earliest vault row). created_at alone is
insufficient twice over: 27 of 71 wallets have none, and 2 record a created_at later
than a measured row already in the sheet.

Guarantees a wallet holding a row on D is never excluded on D, because first_seen
includes that row's own date."
```

---

### Task 4: One sheet read yields the snapshot and the first-seen map

**Files:**
- Modify: `bot/services/google_sheets_logger.py` (`get_snapshot_and_nearest`, around line 380)
- Test: `tests/test_history_bundle.py` (create)

**Interfaces:**
- Consumes: `build_first_seen(roster, rows)` from Task 3.
- Produces: `get_history_bundle(date_str: str, roster: list[dict] | None = None) -> dict` with keys `ok` (bool), `snapshot` (dict), `nearest_date` (str|None), `nearest_snapshot` (dict), `first_seen` (dict). `get_snapshot_and_nearest(date_str)` keeps its existing 4-tuple signature and delegates, so no existing caller changes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_bundle.py`:

```python
# tests/test_history_bundle.py
"""One DAILY_REPORT read must serve both the snapshot and the first-seen map.

The sheet is ~17,500 rows; reading it twice per command would double the quota cost
for data we already have in memory.
"""
from unittest.mock import patch

from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger


def _row(date, address, balance="10.00", batch="20260101000100"):
    return [batch, date, "00:00:00", "W-" + address, "CO", address, balance, "scheduled"]


ROWS = [
    _row("2026-07-15", "TAAA", "100.00"),
    _row("2026-07-15", "TBBB", "200.00"),
    _row("2026-07-16", "TAAA", "150.00"),
]
ROSTER = [{"address": "TAAA", "created_at": None}, {"address": "TBBB", "created_at": "2026-07-01"}]


def test_bundle_returns_snapshot_and_first_seen_from_one_read():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS) as rd:
        b = lg.get_history_bundle("2026-07-15", ROSTER)
    assert rd.call_count == 1, "must read the sheet exactly once"
    assert b["ok"] is True
    assert set(b["snapshot"]) == {"TAAA", "TBBB"}
    assert b["first_seen"] == {"TAAA": "2026-07-15", "TBBB": "2026-07-01"}


def test_a_failed_read_reports_not_ok_and_empty_first_seen():
    """ok=False means 'I don't know', never 'nothing is saved'."""
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=None):
        b = lg.get_history_bundle("2026-07-15", ROSTER)
    assert b["ok"] is False
    assert b["snapshot"] == {}
    assert b["first_seen"] == {}


def test_first_seen_is_empty_when_no_roster_is_supplied():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        b = lg.get_history_bundle("2026-07-15")
    assert b["first_seen"] == {}
    assert set(b["snapshot"]) == {"TAAA", "TBBB"}


def test_legacy_four_tuple_still_works_unchanged():
    """Existing callers and tests must not break."""
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        snapshot, nearest_date, nearest_snapshot, ok = lg.get_snapshot_and_nearest("2026-07-15")
    assert ok is True
    assert set(snapshot) == {"TAAA", "TBBB"}
    assert nearest_date is None


def test_legacy_four_tuple_on_a_date_with_no_rows():
    lg = GoogleSheetsBalanceLogger()
    with patch.object(lg, "_read_daily_report_rows", return_value=ROWS):
        snapshot, nearest_date, nearest_snapshot, ok = lg.get_snapshot_and_nearest("2026-07-20")
    assert ok is True
    assert snapshot == {}
    assert nearest_date in ("2026-07-15", "2026-07-16")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_history_bundle.py -q`
Expected: FAIL — `AttributeError: 'GoogleSheetsBalanceLogger' object has no attribute 'get_history_bundle'`.

- [ ] **Step 3: Refactor `get_snapshot_and_nearest` into a bundle**

In `bot/services/google_sheets_logger.py`, add the import at the top:

```python
from bot.services.vault_calendar import build_first_seen
```

Replace the body of `get_snapshot_and_nearest` with a delegating wrapper and add the new
method immediately above it. Keep the existing docstring on the wrapper — it documents the
`ok=False` contract that a caller must never confuse with "nothing is saved".

```python
    def get_history_bundle(self, date_str, roster=None):
        """Everything the dated check needs, from ONE DAILY_REPORT read.

        Returns {"ok", "snapshot", "nearest_date", "nearest_snapshot", "first_seen"}.

        `ok` is False whenever the read failed. A caller MUST treat that as "I don't
        know what's saved", never as "nothing is saved" -- confusing the two is what
        once made /check rebuild and duplicate 68 already-saved wallets.

        `first_seen` is {} unless a roster is supplied. The sheet is ~17,500 rows, so
        deriving it here rather than re-reading keeps the command to a single read.
        """
        rows = self._read_daily_report_rows()
        if rows is None:
            return {"ok": False, "snapshot": {}, "nearest_date": None,
                    "nearest_snapshot": {}, "first_seen": {}}

        first_seen = build_first_seen(roster, rows) if roster else {}
        exact = self._build_snapshot_from_rows(rows, date_str)
        if exact:
            return {"ok": True, "snapshot": exact, "nearest_date": None,
                    "nearest_snapshot": {}, "first_seen": first_seen}

        dates = sorted({r[1] for r in rows if len(r) > 1 and r[1]})
        nearest_date, nearest_snapshot = self._nearest_from(rows, dates, date_str)
        return {"ok": True, "snapshot": {}, "nearest_date": nearest_date,
                "nearest_snapshot": nearest_snapshot, "first_seen": first_seen}
```

Move the existing "find the nearest date" logic out of `get_snapshot_and_nearest` into a
helper `_nearest_from(self, rows, dates, date_str)` returning `(nearest_date,
nearest_snapshot)`, preserving its current tie-breaking exactly — **ties prefer the
earlier date**. Then:

```python
    def get_snapshot_and_nearest(self, date_str):
        """Back-compatible 4-tuple view of get_history_bundle: (snapshot, nearest_date,
        nearest_snapshot, ok). Kept so existing callers and tests are untouched."""
        b = self.get_history_bundle(date_str)
        return b["snapshot"], b["nearest_date"], b["nearest_snapshot"], b["ok"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_history_bundle.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite — the refactor must break nothing**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: 0 failures. Any failure in existing snapshot tests means the nearest-date
tie-breaking changed during the move — fix it rather than adjusting the old test.

- [ ] **Step 6: Commit**

```bash
git add bot/services/google_sheets_logger.py tests/test_history_bundle.py
git commit -m "refactor: one DAILY_REPORT read yields snapshot + first_seen

Adds get_history_bundle; get_snapshot_and_nearest becomes a thin wrapper so no
existing caller changes. The sheet is ~17,500 rows -- deriving first_seen from the
rows already in memory avoids a second read per command."
```

---

### Task 5: Wire mode and target date through the handler

**Files:**
- Modify: `bot/handlers/check_handler.py` — `handle` (around lines 134-181), `_handle_historical` (line 324), `classify_wallets` (line 296)
- Test: `tests/test_check_open_close.py` (create)

**Interfaces:**
- Consumes: `extract_mode` (Task 1), `target_date_for` (Task 2), `build_first_seen` (Task 3), `get_history_bundle` (Task 4).
- Produces: `classify_wallets(roster, snapshot, date_str, first_seen=None)` — the new optional 4th parameter. `_handle_historical(context, date_str, other_tokens, wallet_data, mode=None)` — the new optional 5th parameter.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_check_open_close.py`:

```python
# tests/test_check_open_close.py
"""/check [D] resolves to a vault DATE, then runs the existing pipeline against it."""
import asyncio
from unittest.mock import patch

import pytest

from bot.handlers.check_handler import CheckHandler
from bot.services.vault_calendar import target_date_for


class Topic:
    def __init__(self):
        self.cards = []

    async def send_command_response(self, card, msg_type=None):
        self.cards.append(card)


class Ctx:
    def __init__(self, args):
        self.args = args
        self.sender_id = "ou_test"
        self.topic_manager = Topic()


def run(handler, args):
    ctx = Ctx(args)
    asyncio.run(handler.handle(ctx))
    return ctx.topic_manager.cards


def titles(cards):
    return " | ".join(c["header"]["title"]["content"] for c in cards if isinstance(c, dict))


def blob(cards):
    import json
    return json.dumps(cards)


# --- classify_wallets now decides existence from first_seen ---

def test_classify_uses_first_seen_not_created_at():
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-01-15"}]
    # created_at says January, but we hold a measured row from December
    first_seen = {"TAAA": "2025-12-17"}
    out = h.classify_wallets(roster, {}, "2025-12-20", first_seen)
    assert out[0]["status"] == "needs_rebuild", "existed by then, so we should expect a figure"


def test_classify_excludes_a_wallet_created_after_the_date():
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-03-01"}]
    out = h.classify_wallets(roster, {}, "2026-01-01", {"TAAA": "2026-03-01"})
    assert out[0]["status"] == "not_yet_created"


def test_classify_never_excludes_a_wallet_that_has_a_saved_row():
    """The guarantee: a saved figure always wins over any existence judgement."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2099-01-01"}]
    snapshot = {"TAAA": {"wallet_name": "W1", "company": "CO", "address": "TAAA",
                         "balance": 42, "batch_id": "b", "time": "00:00:00"}}
    out = h.classify_wallets(roster, snapshot, "2026-07-15", {"TAAA": "2026-07-15"})
    assert out[0]["status"] == "saved"
    assert out[0]["balance"] == 42


def test_classify_falls_back_when_first_seen_is_unknown():
    """No signal either way -> assume it existed, the safe direction, as before."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": None}]
    out = h.classify_wallets(roster, {}, "2026-01-01", {"TAAA": None})
    assert out[0]["status"] == "needs_rebuild"


def test_classify_still_works_without_a_first_seen_map():
    """Backward compatibility: the 3-argument call keeps the old created_at behaviour."""
    h = CheckHandler()
    roster = [{"wallet": "W1", "address": "TAAA", "company": "CO", "created_at": "2026-03-01"}]
    out = h.classify_wallets(roster, {}, "2026-01-01")
    assert out[0]["status"] == "not_yet_created"


# --- guards ---

def test_modifier_without_a_date_is_rejected():
    """Without this, [o] would fall through to the filter and match OKKZ wallets."""
    h = CheckHandler()
    cards = run(h, ["[o]"])
    assert len(cards) == 1
    assert "date" in blob(cards).lower()
    assert "OKKZ" not in blob(cards)


def test_opening_and_closing_together_is_rejected():
    h = CheckHandler()
    cards = run(h, ["[2026-07-15]", "[o]", "[c]"])
    assert len(cards) == 1
    b = blob(cards).lower()
    assert "opening" in b and "closing" in b


def test_closing_of_today_is_refused_and_points_at_the_opening():
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    h = CheckHandler()
    cards = run(h, [f"[{today}]"])
    b = blob(cards)
    assert len(cards) == 1
    assert "[o]" in b, "must tell the user how to get the figure that does exist"


def test_opening_of_today_is_allowed():
    """Opening of today is the row written at ~00:01 this morning -- it exists."""
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    h = CheckHandler()
    with patch.object(CheckHandler, "_handle_historical", return_value=True) as hh:
        run(h, [f"[{today}]", "[o]"])
    assert hh.called, "opening of today must reach the historical path, not a guard"
    assert hh.call_args[0][1] == today


# --- date translation reaches the pipeline ---

@pytest.mark.parametrize("args,expected_target", [
    (["[2026-07-15]"],          "2026-07-16"),   # default = closing
    (["[2026-07-15]", "[c]"],   "2026-07-16"),
    (["[2026-07-15]", "[o]"],   "2026-07-15"),
])
def test_target_date_passed_to_the_pipeline(args, expected_target):
    h = CheckHandler()
    seen = {}

    def fake_bundle(date_str, roster=None):
        seen["date"] = date_str
        return {"ok": True, "snapshot": {}, "nearest_date": None,
                "nearest_snapshot": {}, "first_seen": {}}

    with patch.object(h.sheets_logger, "get_history_bundle", side_effect=fake_bundle):
        run(h, args)
    assert seen["date"] == expected_target


def test_closing_of_D_reads_the_same_date_as_opening_of_D_plus_one():
    assert target_date_for("2026-07-15", "closing") == target_date_for("2026-07-16", "opening")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_check_open_close.py -q`
Expected: FAIL — `classify_wallets() takes 4 positional arguments but 5 were given`, and the guard tests produce the wrong cards.

- [ ] **Step 3: Add the existence helper and extend `classify_wallets`**

In `bot/handlers/check_handler.py`, add after `_existed_by` (line 294):

```python
    def _existed_on(self, first_seen, wallet, date_str):
        """True if `wallet` existed on/before `date_str`.

        Prefers the derived first_seen map (min of created_at and the earliest vault
        row); falls back to created_at alone when no map was supplied. An unknown
        first_seen means no evidence either way -> assume it existed, the safe
        direction, so a missing figure still surfaces instead of being hidden.
        """
        if first_seen is None:
            return self._existed_by(wallet.get("created_at"), date_str)
        fs = first_seen.get(canonical_address(wallet.get("address", "")))
        if not fs:
            return True
        return fs <= date_str
```

Change the `classify_wallets` signature to
`def classify_wallets(self, roster, snapshot, date_str, first_seen=None):`
and replace its existence branch:

```python
            elif self._existed_on(first_seen, w, date_str):
```

Extend its docstring with:

```
        `first_seen` maps canonical address -> the earliest date the wallet is known to
        have existed (see vault_calendar.build_first_seen). When omitted, existence
        falls back to created_at alone, which is the pre-2026-07-31 behaviour.
```

- [ ] **Step 4: Wire mode extraction and the guards into `handle`**

Add to the imports at the top of `check_handler.py`:

```python
from bot.services.command_args import extract_mode
from bot.services.vault_calendar import target_date_for, OPENING, CLOSING
```

In `handle`, immediately after `date_str, other = split_date(tokens)`:

```python
            # Pull [o]/[c] out before anything treats them as filters. Without this an
            # [o] would fall through to fuzzy matching and silently return the ten OKKZ
            # wallets by prefix.
            mode, other, mode_conflict = extract_mode(other)
            if mode_conflict:
                await context.topic_manager.send_command_response(
                    self._create_mode_conflict_card(), msg_type="interactive")
                return False
            if mode and not date_str:
                # Opening and closing are properties of a DAY, so they are meaningless
                # for the live check.
                await context.topic_manager.send_command_response(
                    self._create_mode_without_date_card(mode), msg_type="interactive")
                return False
```

Change the historical dispatch to pass the mode:

```python
                return await self._handle_historical(context, date_str, other, wallet_data, mode)
```

- [ ] **Step 5: Translate the date in `_handle_historical`**

Change the signature to:

```python
    async def _handle_historical(self, context: Any, date_str: str, other_tokens: List[str],
                                  wallet_data: Dict, mode: str = None) -> bool:
```

After the existing future-date guard on `date_str` (line 342), insert:

```python
        # Default basis is CLOSING: the balance at the end of the requested day, which is
        # the same instant as 00:00 GMT+7 the next morning -- i.e. the row dated D+1.
        mode = mode or CLOSING
        target_date = target_date_for(date_str, mode)
        if target_date > gmt7_today:
            # Only reachable for closing-of-today: the day has not ended, so its closing
            # figure does not exist yet. Opening does, so point there.
            await context.topic_manager.send_command_response(
                self._create_day_not_finished_card(date_str), msg_type="interactive")
            return False
```

Then, through the rest of `_handle_historical`, use `target_date` everywhere the vault is
addressed — the bundle read, `classify_wallets`, the reconstruction cutoff, and
`save_rebuilt_balances` — while keeping `date_str` for card copy. Replace the snapshot read
with the bundle so `first_seen` comes from the same read:

```python
        bundle = await asyncio.to_thread(
            self.sheets_logger.get_history_bundle, target_date, list(wallet_data.values()))
        if bundle["ok"] is False:
            await context.topic_manager.send_command_response(
                self._create_sheet_unavailable_card(date_str), msg_type="interactive")
            return False
        snapshot = bundle["snapshot"]
        first_seen = bundle["first_seen"]
        entries = self.classify_wallets(
            list(wallet_data.values()), snapshot, target_date, first_seen)
```

and the cutoff:

```python
            cutoff_ms = int(datetime.strptime(f"{target_date} {VAULT_DAY_BOUNDARY}",
                                              "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
```

and the write-back must save under `target_date`, not `date_str`.

- [ ] **Step 6: Add the three new cards**

Add to `check_handler.py`, following the existing `_create_*_card` style (same colour and
element structure as `_create_future_date_card`):

```python
    def _create_mode_conflict_card(self) -> dict:
        """Both an opening and a closing modifier were given."""
        return self._simple_notice_card(
            "orange", "⚠️ Choose Opening or Closing",
            "You asked for both the opening and the closing balance. Please pick one.\n\n"
            "• **/check [2026-07-15] [o]** — balance at the start of that day\n"
            "• **/check [2026-07-15] [c]** — balance at the end of that day\n"
            "• **/check [2026-07-15]** — closing, the default")

    def _create_mode_without_date_card(self, mode: str) -> dict:
        """A basis modifier with no date. Opening/closing only mean something for a day."""
        word = "opening" if mode == OPENING else "closing"
        return self._simple_notice_card(
            "orange", "⚠️ A Date Is Needed",
            f"The {word} balance is the balance of a particular day, so please say which day.\n\n"
            f"• **/check [2026-07-15] [{'o' if mode == OPENING else 'c'}]** — that day's {word} balance\n"
            "• **/check** — balances right now")

    def _create_day_not_finished_card(self, date_str: str) -> dict:
        """Closing of today: the day has not ended yet."""
        return self._simple_notice_card(
            "orange", "⏳ This Day Has Not Finished",
            f"**{date_str}** has not ended yet, so it has no closing balance. "
            "It will have one after midnight GMT+7.\n\n"
            f"• **/check [{date_str}] [o]** — the balance at the start of today\n"
            "• **/check** — balances right now")
```

Add the shared builder if the file has no equivalent (check first — reuse rather than
duplicate if one exists):

```python
    def _simple_notice_card(self, template: str, title: str, body: str) -> dict:
        """A one-message notice card, matching the existing error cards' shape."""
        return {
            "config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
        }
```

- [ ] **Step 7: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_check_open_close.py -q`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: 0 failures.

- [ ] **Step 9: Commit**

```bash
git add bot/handlers/check_handler.py tests/test_check_open_close.py
git commit -m "feat: /check [date] resolves opening vs closing to a vault date

Default is closing. closing(D) reads the row dated D+1, opening(D) the row dated D,
so the existing pipeline runs unchanged against a translated date.

Guards: a modifier with no date is rejected (it would otherwise fuzzy-match OKKZ
wallets), opening+closing together is rejected, and closing-of-today is refused with
a pointer to the opening.

classify_wallets now takes first_seen and decides existence from it."
```

---

### Task 6: Cards state the basis, the source date, and cap the added-later list

**Files:**
- Modify: `bot/handlers/check_handler.py` — `_create_historical_card` (line 872), `_create_historical_checking_card` (line 1073), `_create_rebuilding_card` (line 1100)
- Modify: `bot/handlers/help_handler.py`
- Test: `tests/test_check_open_close.py`

**Interfaces:**
- Consumes: `mode` and `target_date` from Task 5.
- Produces: `_create_historical_card(entries, date_str, fuzzy, not_found, saved_batch, mode, target_date, ...)` — two new required parameters appended after the existing ones.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_open_close.py`:

```python
def _entries(n_saved=2, n_later=0):
    out = [{"name": f"W{i}", "company": "CO", "address": f"T{i}", "chain": "TRC20",
            "status": "saved", "balance": 100} for i in range(n_saved)]
    out += [{"name": f"L{i}", "company": "CO", "address": f"L{i}", "chain": "TRC20",
             "status": "not_yet_created", "balance": None} for i in range(n_later)]
    return out


def test_card_states_the_basis():
    h = CheckHandler()
    closing = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                              "closing", "2026-07-16")])
    opening = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                              "opening", "2026-07-15")])
    assert "losing" in closing and "pening" not in closing.replace("opening balance", "")
    assert "pening" in opening


def test_closing_card_names_the_date_it_read():
    """Without this the figure cannot be reconciled against the sheet."""
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "2026-07-15" in b and "2026-07-16" in b


def test_opening_card_does_not_repeat_the_date_pointlessly():
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(), "2026-07-15", [], [], None,
                                        "opening", "2026-07-15")])
    assert b.count("2026-07-15") <= 3


def test_added_later_wallets_are_named_when_there_are_five_or_fewer():
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(2, 3), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "L0" in b and "L1" in b and "L2" in b


def test_added_later_wallets_are_counted_when_there_are_more_than_five():
    h = CheckHandler()
    b = blob([h._create_historical_card(_entries(2, 41), "2026-07-15", [], [], None,
                                        "closing", "2026-07-16")])
    assert "41" in b
    assert "L40" not in b, "must not list forty-one wallet names"


def test_help_teaches_the_new_grammar():
    from bot.handlers.help_handler import HelpHandler
    cards = run(HelpHandler(), [])
    b = blob(cards)
    assert "[o]" in b and "[c]" in b
    assert "closing" in b.lower() and "opening" in b.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_check_open_close.py -q -k "card or help"`
Expected: FAIL — `_create_historical_card() takes 6 positional arguments but 8 were given`.

- [ ] **Step 3: Update `_create_historical_card`**

Add `mode` and `target_date` parameters. In the header, use
`"🕰️ Closing Balance"` or `"🕰️ Opening Balance"` in place of the current title.

Immediately under the header, add one basis line — for closing:

```
Closing balance of **2026-07-15** — the balance at 00:00 GMT+7 on **2026-07-16**
```

and for opening:

```
Opening balance of **2026-07-15** — the balance at 00:00 GMT+7 that morning
```

Replace the existing "added after this date" rendering with the capped version:

```python
        later = [e for e in entries if e["status"] == "not_yet_created"]
        if later:
            if len(later) <= 5:
                names = ", ".join(f"**{e['name']}**" for e in later)
                lines.append(f"• {names} — added after this date, so no balance yet")
            else:
                lines.append(f"• **{len(later)} wallets** were added after this date, "
                             "so they have no balance yet")
```

Where the card reports a save, name `target_date` — that is the date rows were written to,
which for a closing query is the day after the one the user typed.

- [ ] **Step 4: Update the acknowledgement and rebuilding cards**

`_create_historical_checking_card` must say which basis is being fetched, so the
acknowledgement and the result agree. `_create_rebuilding_card` must name `target_date`,
because that is the date being reconstructed and saved.

- [ ] **Step 5: Update `/help`**

In `bot/handlers/help_handler.py`, add to the `/check` section:

```
• /check [2026-07-15]            balance at the END of that day (closing)
• /check [2026-07-15] [o]        balance at the START of that day (opening)
• /check [2026-07-15] [c]        balance at the end of that day, said explicitly
• /check [2026-07-15] [KZDW]     one group, that day's closing balance
• /check [2026-07-15] [o] [KZDW] one group, that day's opening balance

Spacing does not matter: [2026-07-15][KZDW] works the same.
```

- [ ] **Step 6: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_check_open_close.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q | tail -3`
Expected: 0 failures.

- [ ] **Step 8: Commit**

```bash
git add bot/handlers/check_handler.py bot/handlers/help_handler.py tests/test_check_open_close.py
git commit -m "feat: cards state the basis and the date they read

A closing figure comes from the row dated D+1, so the card says so -- otherwise the
number cannot be reconciled against the sheet. Rebuild and save messages name the
target date for the same reason.

The added-after-this-date list is capped: five or fewer are named, more than five
shows a count, so an old date no longer lists forty wallet names."
```

---

### Task 7: Verify against real data, then deploy

**Files:** none changed — verification and rollout only.

**Interfaces:**
- Consumes: everything from Tasks 1-6.

- [ ] **Step 1: Verify the headline numbers against the live vault (read-only)**

```bash
.venv/bin/python - <<'PY'
import os, json, asyncio
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from bot.handlers.check_handler import CheckHandler
import bot.handlers.check_handler as ch

class T:
    def __init__(self): self.cards=[]
    async def send_command_response(self, card, msg_type=None): self.cards.append(card)
class C:
    def __init__(self, args): self.args=args; self.sender_id="ou_verify"; self.topic_manager=T()

def sub(cards):
    return cards[-1].get("header",{}).get("subtitle",{}).get("content","")

h = CheckHandler()
for args, expect in [ (["[2026-07-15]","[o]"], "13,766,045.97"),
                      (["[2026-07-15]","[c]"], "13,896,104.81"),
                      (["[2026-07-15]"],       "13,896,104.81") ]:
    ch._CHECK_EXECUTION_LOCK = False
    ctx = C(args); asyncio.run(h.handle(ctx))
    got = sub(ctx.topic_manager.cards)
    print(f"{' '.join(args):28} -> {got}   expect {expect}   {'OK' if expect in got else 'MISMATCH'}")
PY
```
Expected: all three `OK`. `[o]` gives 13,766,045.97, `[c]` and the bare form both give
13,896,104.81. **A mismatch means the date translation is wrong — stop and fix before
deploying.**

- [ ] **Step 2: Verify the guards behave, in the live environment**

Run `/check [<today>]` (expect **This Day Has Not Finished**), `/check [<today>] [o]`
(expect a real figure), `/check [o]` (expect **A Date Is Needed**, and confirm no OKKZ
wallet appears), and `/check [2026-07-15] [o] [c]` (expect **Choose Opening or Closing**).

- [ ] **Step 3: Confirm `[open]` and `[close]` still filter**

Run `/check [2026-07-15] [open]` and confirm it matches `KZO PEN SETTLE TRC 1` rather than
being read as a basis modifier. Same for `[close]` → `KZO SETTLE OPS TRC 1`.

- [ ] **Step 4: Full suite, then publish**

```bash
.venv/bin/python -m pytest tests/ -q | tail -3
git status --short                      # must be empty
git push origin feature/check-date-and-remove-fix
git checkout main && git pull --ff-only origin main
git merge --ff-only feature/check-date-and-remove-fix
git push origin main
git checkout feature/check-date-and-remove-fix
git ls-remote --heads origin main
```
Expected: 0 failures, clean tree, fast-forward with no merge commit.

- [ ] **Step 5: Deploy to production**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
cp /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/OA-C-Finance.pem "$SCRATCH/k.pem"
chmod 600 "$SCRATCH/k.pem"
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 'cd /home/ubuntu/crypto-lark-bot
date -u +%H:%M     # must not be within 10 minutes of 17:00 UTC
cp .env .env.bak.$(date +%Y%m%d%H%M%S)
cp wallets.json wallets.json.bak.$(date +%Y%m%d%H%M%S)
git pull --ff-only
git status --porcelain --untracked-files=no    # must be empty
.venv/bin/python -c "from bot.services.vault_calendar import target_date_for; print(target_date_for(\"2026-07-15\",\"closing\"))"
./start_lark_bot.sh restart'
```
Expected: fast-forward, `.env`/`wallets.json` unmodified, the import prints `2026-07-16`.

**Never copy `credentials/prd_env.txt` onto prod** — it holds 8 authorized users against
prod's 11.

- [ ] **Step 6: Verify the deploy from a FRESH ssh connection**

The restart kills its own ssh session (exit 255), so its output cannot be trusted.

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 'cd /home/ubuntu/crypto-lark-bot
echo "HEAD: $(git rev-parse --short HEAD)"
CM=$(git log -1 --format=%ct)
for name in lark_bot.py main.py wallets_to_gg_sheet.py cleanup.py; do
  for PID in $(pgrep -f "python.*$name"); do
    [ "$(tr -d "\0" < /proc/$PID/comm 2>/dev/null)" = "python" ] || continue
    ST=$(date -d "$(ps -o lstart= -p $PID)" +%s)
    [ "$ST" -gt "$CM" ] && echo "  NEW   $name" || echo "  STALE $name <-- restart again"
  done
done
pgrep -af ngrok | head -1 | cut -c1-50
curl -s --max-time 6 http://127.0.0.1:8080/
md5sum .env wallets.json
echo "authorized users: $(grep "^LARK_AUTHORIZED_USERS=" .env | cut -d= -f2 | tr "," "\n" | grep -c .)"
echo "wallets: $(.venv/bin/python -c "import json;print(len(json.load(open(\"wallets.json\"))))")"'
```
Expected: all four **NEW**, ngrok up, health OK, `.env` md5 `8980c501f4bb6e902f2eff153e994a4e`,
**11** authorized users, **71** wallets.

- [ ] **Step 7: Announce the three breaking changes**

Tell users, because reported figures change:
1. `/check [date]` now gives the **closing** balance. Add `[o]` for the opening.
2. `[o]` and `[c]` no longer work as wallet filters — use `[OKKZ]` and `[KZO COY]`.
3. Totals for older dates may be lower, because wallets that did not exist then are no
   longer counted.

Rollback if needed: `git reset --hard adc6cdc && ./start_lark_bot.sh restart`.

---

## Self-Review

**Spec coverage.** §2 semantics → Task 2. §3 resolution and write-back-lands-on-target →
Tasks 4, 5, 6 Step 3. §4 modifier extraction, excluded words, filters, spacing → Task 1.
§5 existence rule and its guarantee → Tasks 3, 5. §6 all five guard rows → Task 5
(conflict, no-date, day-not-finished) and existing code (invalid date, future date, sheet
failure — covered by regression in Task 5 Step 8). §7 card basis, source date, saved date,
capped list → Task 6. §8 breaking changes announced → Task 7 Step 7. §10 testing → every
task. §11 rollout → Task 7.

**Placeholders.** None. Every code step carries real code; every verification step carries
the command and its expected output.

**Type consistency.** `extract_mode` returns `(mode, rest, conflict)` in Tasks 1 and 5.
`target_date_for(date_str, mode)` returns a string in Tasks 2, 5, 7. `build_first_seen`
returns `{canonical_address: iso_date | None}` in Tasks 3, 4, 5. `get_history_bundle`
returns the same five keys in Tasks 4 and 5. `classify_wallets`'s fourth parameter is named
`first_seen` in Tasks 3, 4 and 5. Mode values are the constants `OPENING`/`CLOSING` from
`vault_calendar`, imported in Task 5 and used in the Task 5 cards.

**One risk flagged for the executor.** Task 5 Step 5 rewrites the middle of
`_handle_historical`, a long method that also holds the rebuild lock, the executor
shutdown, and the save path. Change only the date each call addresses — do not restructure
the surrounding control flow, and re-read the whole method before and after editing.
