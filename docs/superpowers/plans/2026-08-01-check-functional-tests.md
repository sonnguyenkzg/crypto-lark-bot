# /check Functional Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A committed hermetic pytest file that drives the whole `/check [date]` command and asserts on the rendered card, giving the creation-based existence rule reliable regression coverage.

**Architecture:** Reuse the `Topic`/`Ctx`/`run()` pattern from `tests/test_check_open_close.py`. Patch three boundaries — `_read_daily_report_rows` (fixed rows), `BalanceService.get_balance_at` (deterministic), `save_rebuilt_balances` (no-op recorder) — and let the real parse→bundle→classify→rebuild→card chain run. Assert on card text.

**Tech Stack:** Python 3.12, pytest, unittest.mock.

## Global Constraints

- `VAULT_COMPLETE_FROM = "2026-01-01"` (from `bot.services.google_sheets_logger`). Fixtures set `coverage_start = max(earliest row, 2026-01-01)`.
- Row shape: `[batch, date, time, wallet, company, address, balance, check_type]` (8 cols). `check_type` is `"scheduled"` or `"rebuilt"`.
- Hermetic: NO network, NO sheet I/O. Any test that reaches `save_rebuilt_balances` must find the recorder patched.
- Card summary lines are asserted after stripping `**`.

---

### Task 1: Harness + fixture + first scenario (fully-saved opening)

**Files:**
- Create: `tests/test_check_functional.py`

**Interfaces:**
- Produces: `rows(*specs)` row builder; `make_handler(rows_list, balances=None)` → a `CheckHandler` with the three boundaries patched and a `writes` recorder attached; `run(h, args)` → captured cards; `summary(cards)` → the final card's joined summary text (`**` stripped).

- [ ] **Step 1: Write the harness + the first failing assertion**

```python
# tests/test_check_functional.py
"""Functional tests: drive the whole /check [date] command, assert on the rendered card.

Hermetic -- the sheet read, the reconstruction call, and the write-back are patched, so
parse -> get_history_bundle -> classify_wallets -> rebuild -> card all run for real with
no network or I/O. This is the creation-based existence rule's end-to-end safety net.
"""
import asyncio, json
from unittest.mock import patch
import pytest
from bot.handlers.check_handler import CheckHandler
import bot.handlers.check_handler as ch


def _row(date, wallet, address, balance, company="CO", batch="20260101000100", ctype="scheduled"):
    return [batch, date, "00:00:00", wallet, company, address, str(balance), ctype]


class Topic:
    def __init__(self): self.cards = []
    async def send_command_response(self, card, msg_type=None): self.cards.append(card)


class Ctx:
    def __init__(self, args): self.args = args; self.sender_id = "ou_fn"; self.topic_manager = Topic()


def make_handler(rows_list, balances=None):
    """A CheckHandler whose sheet read returns rows_list, whose reconstruction returns
    balances.get(address) (Decimal-friendly), and whose write-back is a no-op recorder
    (handler.writes collects any attempted write)."""
    from decimal import Decimal
    h = CheckHandler()
    h.writes = []
    def _no_write(target_date, entries):
        h.writes.append((target_date, entries)); return (False, None)
    h.sheets_logger.save_rebuilt_balances = _no_write
    h.sheets_logger._read_daily_report_rows = lambda: list(rows_list)
    bals = {k: Decimal(str(v)) for k, v in (balances or {}).items()}
    h.balance_service.get_balance_at = lambda address, chain, cutoff_ms, deadline=None: bals.get(address)
    return h


def run(h, args):
    ch._CHECK_EXECUTION_LOCK = False
    ctx = Ctx(args); asyncio.run(h.handle(ctx)); return ctx.topic_manager.cards


def summary(cards):
    final = cards[-1]
    return " ".join(e.get("text", {}).get("content", "") for e in final.get("elements", [])).replace("**", "")


# 5-wallet roster fixture the handler reads via wallet_data (patched loader below).
ROSTER = [
    {"wallet": "EARLY",   "company": "CO", "address": "TEARLY", "chain": "TRC20"},
    {"wallet": "MIDA",    "company": "CO", "address": "TMIDA",  "chain": "TRC20"},
    {"wallet": "MIDB",    "company": "DAO","address": "TMIDB",  "chain": "TRC20"},
    {"wallet": "LATE1",   "company": "CO", "address": "TLATE1", "chain": "TRC20"},
    {"wallet": "LATE2",   "company": "CO", "address": "TLATE2", "chain": "TRC20"},
]


def _wallet_data():
    # shape check_handler expects: dict keyed by anything, values have wallet/company/address/chain
    return {w["address"]: dict(w) for w in ROSTER}


def with_roster(h):
    """Patch the handler's roster source to ROSTER. check_handler builds `roster` from
    self._load_wallets()/wallet_data; point that at our synthetic roster."""
    return patch.object(h, "_load_wallets", return_value=_wallet_data())
```

> NOTE for implementer: confirm how `_handle_historical` obtains `wallet_data` (grep `wallet_data` / `_load_wallets` in `check_handler.py`). Wire `with_roster` to the real attribute/method name before writing assertions. If the roster comes from a module-level loader, patch that instead.

- [ ] **Step 2: Write scenario 1 (fully-saved opening date)**

```python
def test_fully_saved_opening_lists_saved_and_added_later():
    # EARLY/MIDA/MIDB funded by 2026-05-01 (have rows on the queried date); LATE1/LATE2
    # first funded 2026-06-01 (no row on 2026-05-10) -> "added on or after this date".
    rows = (
        [_row("2026-05-10", "EARLY", "TEARLY", 100)]
        + [_row("2026-05-10", "MIDA", "TMIDA", 200)]
        + [_row("2026-05-10", "MIDB", "TMIDB", 300)]
        + [_row("2026-06-01", "LATE1", "TLATE1", 50)]   # first funding, after query date
        + [_row("2026-06-01", "LATE2", "TLATE2", 60)]
    )
    h = make_handler(rows)
    with with_roster(h):
        cards = run(h, ["[2026-05-10]", "[o]"])
    s = summary(cards)
    assert "Total wallets in monitoring: 5" in s
    assert "3 have a balance recorded" in s
    assert "added on or after this date" in s
    assert "LATE1" in s and "LATE2" in s        # <=6 -> named
    assert "3 wallets counted" in s
    assert h.writes == []                        # opening of a fully-saved date writes nothing
```

- [ ] **Step 3: Run, adjust harness to real handler wiring until green**

Run: `.venv/bin/python -m pytest tests/test_check_functional.py -x -q`
Expected: PASS. If FAIL, the wiring note in Step 1 (roster source) or the card copy is off — fix the harness, not the assertion's intent.

- [ ] **Step 4: Commit**

```bash
git add tests/test_check_functional.py
git commit -m "test: functional harness + fully-saved /check scenario"
```

---

### Task 2: Remaining scenarios (2–9)

**Files:**
- Modify: `tests/test_check_functional.py`

Add one test per scenario, each `with with_roster(h)`. Fixtures and the specific card assertions:

- [ ] **Scenario 2 — not-yet-created naming (>6 summarized).** Use a temporary 8-wallet roster (extend ROSTER inside the test or param) where 7 are first-funded after the query date. Assert `"7 wallets were added on or after this date"` in summary and that individual late-wallet names are NOT listed.

- [ ] **Scenario 3 — money before monitoring is counted, never "added later".** `EARLY` has a positive row on `2026-03-01`; query `2026-05-10`. Assert `EARLY` is in the counted balance table and NOT in the "added on or after" line. Mutation proof target.

- [ ] **Scenario 4 — pre-coverage date reconstructs, hides nothing.** Rows only from `2026-02-01`+ (so `coverage_start = 2026-02-01`). Query `2026-01-15` (below floor). `LATE1` has no row; provide `balances={"TLATE1": 4049}` etc. Assert NO "added on or after this date" line, `LATE1` shows a reconstructed balance ("calculated from blockchain records" count ≥1), and `h.writes` has one entry (rebuilt rows are saved). Mutation proof target.

- [ ] **Scenario 5 — in-window gap wallet reconstructs.** `MIDA` funded `2026-04-01` (row exists there) but NO row on the queried `2026-05-10`; provide `balances={"TMIDA": 222}`. Assert `"calculated from blockchain records"` count ≥1 and `MIDA` shows 222 in the table.

- [ ] **Scenario 6 — malformed non-zero-padded sheet date.** One row dated `"2026-7-05"` (not `2026-07-05`) with a positive balance; query `[2026-07-05]`. Assert that wallet is `saved`/counted (its balance appears), NOT in the "added later" line — the date still matches. Mutation proof target (revert `normalize_iso_date` in snapshot → should go red).

- [ ] **Scenario 7 — filtered query.** All 5 saved on `2026-05-10`; query `["[2026-05-10]", "[DAO]", "[o]"]`. Assert `"Wallets in scope: 1 of 5 monitored"` and only `MIDB` in the table.

- [ ] **Scenario 8 — closing reads D+1.** Put `EARLY`'s row only on `2026-05-11` (not `2026-05-10`). Query `["[2026-05-10]", "[c]"]` → closing(2026-05-10) = row 2026-05-11. Assert `EARLY` is `saved` (found via the D+1 row), and the basis line names `2026-05-11`.

- [ ] **Scenario 9 — sheet read failure.** `make_handler` with `_read_daily_report_rows` patched to `lambda: None`. Query `[2026-05-10]`. Assert exactly ONE card, it is the "unavailable"/error card (no "counted", no USDT table), and `h.writes == []`. Mutation proof target (the `if not bundle["ok"]` guard).

- [ ] **Run the whole file green.** `.venv/bin/python -m pytest tests/test_check_functional.py -q`

- [ ] **Commit.** `git commit -am "test: full /check functional scenario matrix (creation rule)"`

---

### Task 3: Prove the tests can fail (red→green mutation) + full-suite verification

- [ ] **Mutation 1 — reconciliation/existence (#1, #3).** In `check_handler.classify_wallets`, force `status = "needs_rebuild"` for the `not_yet_created` branch (delete the branch). Run scenarios 1–3: they must FAIL (the "added on or after" line disappears / counts change). Restore; confirm green.

- [ ] **Mutation 2 — coverage floor (#4).** Temporarily lower the floor by passing `coverage_start=None`-equivalent (or change `VAULT_COMPLETE_FROM` to `"2020-01-01"`): scenario 4 must FAIL (LATE1 becomes `not_yet_created`, money hidden). Restore; confirm green.

- [ ] **Mutation 3 — date normalization (#6).** Revert the `normalize_iso_date` compare in `_build_snapshot_from_rows` to raw `!=`: scenario 6 must FAIL (saved row missed). Restore; confirm green.

- [ ] **Mutation 4 — read-failure guard (#9).** Delete the `if not bundle["ok"]: ... return False` block: scenario 9 must FAIL (it proceeds to rebuild/None-snapshot instead of the error card). Restore; confirm green.

- [ ] **Full suite.** `.venv/bin/python -m pytest tests/ -q` → all green (existing + new).

- [ ] **Independent Codex review** of `tests/test_check_functional.py`: does any assertion pass vacuously? Can a real regression slip through the fixtures? Loop until SOUND.

- [ ] **Commit + push.** `git commit -am "test: prove functional tests fail on regression (red-green)"` then `git push` (branch + main per release flow if shipping).

## Self-Review

- **Spec coverage:** Tasks map to all 9 spec scenarios (Task 1 = #1; Task 2 = #2–9; Task 3 = mutation proofs + verify). ✓
- **Placeholders:** Harness code is complete; scenario fixtures specify exact rows/assertions. The one open item (roster source wiring) is flagged explicitly for the implementer to resolve against `check_handler.py` before assertions — not a hidden TODO. ✓
- **Type consistency:** `make_handler`/`run`/`summary`/`with_roster` names used consistently across tasks. ✓
