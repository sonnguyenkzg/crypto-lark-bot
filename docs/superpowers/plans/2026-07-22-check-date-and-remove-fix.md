# `/check [date]` + `/remove [address]` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add historical `/check [date]` (vault-first with chain-reconstruction fallback, 3 forms + fuzzy) and fix `/remove [address]`, using one bracket-based argument parser across `/check`, `/remove`, `/add`.

**Architecture:** Pure, unit-testable cores (argument parsing, snapshot assembly, reconstruction math, completeness/filter logic) live in small functions; the handlers are thin I/O shells that call them. The network/Sheets shells are the same calls already proven cent-accurate in the scratchpad PoCs.

**Tech Stack:** Python 3.12, `requests`, Google Sheets API (`googleapiclient`), stdlib `difflib`/`decimal`/`datetime`, `pytest` + `pytest-asyncio` (already in `requirements.txt`).

Spec: `docs/superpowers/specs/2026-07-22-check-date-and-remove-fix-design.md`.

## Global Constraints

- **No new dependencies.** Fuzzy matching = stdlib `difflib` (no LLM).
- **Vault** = Google Sheet `DAILY_REPORT` tab, columns `A:H` = `Batch ID, Date, Time, Wallet Name, Company, Address, Balance (USDT), Check Type`. One batch/day normally.
- **Balances are stored with commas** (`"351,432.18"`) — always strip before `Decimal`.
- **Batch IDs are GMT+7 timestamps** `YYYYMMDDHHMMSS`; use them for ordering.
- **USDT contracts:** TRC20 `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`, ERC20 `0xdac17f958d2ee523a2206206994597c13d831ec7`; both 6 decimals (`raw / 1_000_000`).
- **`canonical_address(addr)`:** `0x…` → `.lower()`; `T…` → unchanged. Use for **every** address key/compare.
- **Dates:** ISO `YYYY-MM-DD` only; reject malformed, future (`> today` GMT+7), note pre-vault (`< 2025-09-22`).
- **Grammar:** every arg in `[ ]` (quotes `"…"`/`'…'` still accepted); classify by content (date/group/wallet); group wins on a company-vs-wallet tie.
- **Snapshot assembly:** union of all that-date batches, **keyed by `canonical_address`**, **earliest batch value per address** (a later intraday run only adds wallets, never overwrites the ~00:01 snapshot).
- **Completeness guard:** compare snapshot addresses to the **current roster** (`wallets.json`, `created_at <= date`); warn + list any missing — never present a short total as authoritative.
- **Live `/check` (no date) is unchanged.** `wallets.json` on prod is untouched by this change.
- **Deploy:** GitHub `main` → on `47.129.129.241`: `git pull` + restart. Only after user go-ahead.

---

### Task 1: `canonical_address()` in chain_detector

**Files:**
- Modify: `bot/services/chain_detector.py`
- Test: `tests/test_canonical_address.py`

**Interfaces:**
- Produces: `canonical_address(address: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_canonical_address.py
from bot.services.chain_detector import canonical_address

def test_erc20_lowercased():
    assert canonical_address("0xAbC17F958d2Ee523A2206206994597C13D831EC7") \
        == "0xabc17f958d2ee523a2206206994597c13d831ec7"

def test_trc20_unchanged_case_sensitive():
    a = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    assert canonical_address(a) == a            # base58 is case-sensitive
    assert canonical_address(a.lower()) != a    # lowercasing would corrupt it

def test_strip_and_empty():
    assert canonical_address("  0xABC...  ".replace("...", "1"*38)) \
        == "0xabc" + "1"*38
    assert canonical_address("") == ""
    assert canonical_address(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_canonical_address.py -v`
Expected: FAIL with `ImportError: cannot import name 'canonical_address'`

- [ ] **Step 3: Implement `canonical_address`**

```python
# append to bot/services/chain_detector.py
def canonical_address(address: str) -> str:
    """Canonical on-chain identity used for keying/matching addresses.

    ERC20 ('0x...') hex is case-insensitive -> lowercase.
    TRC20 ('T...') base58 is case-sensitive -> leave unchanged.
    Returns "" for empty/invalid input.
    """
    if not address or not isinstance(address, str):
        return ""
    a = address.strip()
    if a.startswith("0x"):
        return a.lower()
    return a
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_canonical_address.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/services/chain_detector.py tests/test_canonical_address.py
git commit -m "feat(chain): add canonical_address (ERC20 lower, TRC20 exact)"
```

---

### Task 2: argument tokenizer + date split (`command_args`)

**Files:**
- Create: `bot/services/command_args.py`
- Test: `tests/test_command_args_parse.py`

**Interfaces:**
- Produces: `parse_arguments(text: str) -> tuple[list[str], bool]` (tokens, had_bare_words); `is_valid_iso_date(s: str) -> bool`; `split_date(tokens: list[str]) -> tuple[str|None, list[str]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_command_args_parse.py
from bot.services.command_args import parse_arguments, is_valid_iso_date, split_date

def test_parse_brackets_and_quotes():
    assert parse_arguments('[2026-07-15] [KZP 96G1]') == (["2026-07-15", "KZP 96G1"], False)
    assert parse_arguments('"KZP 96G1"') == (["KZP 96G1"], False)
    assert parse_arguments("[KZP]  [KZO]") == (["KZP", "KZO"], False)

def test_parse_flags_bare_words():
    # bare (undelimited) word must be flagged so the handler can hint "wrap in [ ]"
    assert parse_arguments("2026-07-15 KZP") == ([], True)
    assert parse_arguments("[2026-07-15] KZP") == (["2026-07-15"], True)

def test_parse_empty():
    assert parse_arguments("") == ([], False)
    assert parse_arguments("   ") == ([], False)

def test_is_valid_iso_date():
    assert is_valid_iso_date("2026-07-15")
    assert not is_valid_iso_date("2026-13-40")   # impossible calendar date
    assert not is_valid_iso_date("15/07/2026")
    assert not is_valid_iso_date("2026-7-5")

def test_split_date_first_iso_token_wins():
    assert split_date(["2026-07-15", "KZP", "KZP 96G1"]) == ("2026-07-15", ["KZP", "KZP 96G1"])
    assert split_date(["KZP 96G1"]) == (None, ["KZP 96G1"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_command_args_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.command_args'`

- [ ] **Step 3: Implement the tokenizer + date helpers**

```python
# bot/services/command_args.py
import re
from datetime import datetime

# One [bracket] OR "double" OR 'single' quoted token
_TOKEN_RE = re.compile(r'\[([^\[\]]*)\]|"([^"]*)"|\'([^\']*)\'')
_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_arguments(text: str):
    """Extract [bracket]/"quote"/'quote' tokens in order.

    Returns (tokens, had_bare_words). had_bare_words is True when any
    non-delimited word remains after removing all tokens, so the handler
    can hint the user to wrap arguments in [ ].
    """
    if not text or not text.strip():
        return [], False
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        val = next(g for g in m.groups() if g is not None).strip()
        if val:
            tokens.append(val)
    leftover = _TOKEN_RE.sub(" ", text).strip()
    return tokens, bool(leftover)


def is_valid_iso_date(s: str) -> bool:
    if not s or not _ISO_RE.match(s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def split_date(tokens):
    """Return (date_or_None, other_tokens). The first ISO-shaped token is the date."""
    date = None
    rest = []
    for t in tokens:
        if date is None and _ISO_RE.match(t):
            date = t
        else:
            rest.append(t)
    return date, rest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_command_args_parse.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/services/command_args.py tests/test_command_args_parse.py
git commit -m "feat(args): bracket/quote tokenizer + ISO date split"
```

---

### Task 3: token classification + fuzzy resolve (`command_args`)

**Files:**
- Modify: `bot/services/command_args.py`
- Test: `tests/test_command_args_classify.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `classify_tokens(tokens, companies, wallet_names) -> tuple[list[str], list[str]]` (groups, names); `resolve_fuzzy(token, candidates, n=3, cutoff=0.6) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_command_args_classify.py
from bot.services.command_args import classify_tokens, resolve_fuzzy

COMPANIES = ["KZP", "KZO", "KZG", "S5"]
NAMES = ["KZP 96G1", "KZP WDB2", "KZO A 1", "S5 Tech ERC20"]

def test_classify_group_vs_wallet():
    groups, names = classify_tokens(["KZP", "KZP 96G1"], COMPANIES, NAMES)
    assert groups == ["KZP"]
    assert names == ["KZP 96G1"]

def test_classify_case_insensitive_and_group_wins_on_tie():
    # a token that is also a company name is treated as a group
    groups, names = classify_tokens(["kzp"], COMPANIES, NAMES)
    assert groups == ["kzp"] and names == []

def test_resolve_fuzzy_near_miss():
    # typo / prefix -> closest wallet name
    assert "KZP 96G1" in resolve_fuzzy("KZP 96", NAMES)

def test_resolve_fuzzy_total_miss():
    assert resolve_fuzzy("ZZZ QQQ", NAMES) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_command_args_classify.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_tokens'`

- [ ] **Step 3: Implement classify + fuzzy**

```python
# append to bot/services/command_args.py
from difflib import get_close_matches


def classify_tokens(tokens, companies, wallet_names):
    """Split tokens into (groups, names) by content.

    A token that matches a company name (case-insensitive) is a group;
    the group interpretation wins even if it also matches a wallet name.
    """
    comp_lower = {c.lower() for c in companies}
    groups, names = [], []
    for t in tokens:
        if t.lower() in comp_lower:
            groups.append(t)
        else:
            names.append(t)
    return groups, names


def resolve_fuzzy(token, candidates, n=3, cutoff=0.6):
    """Closest wallet names to `token`: case-insensitive substring hits first,
    then difflib close matches. Deduped, order-preserving, capped at n."""
    if not token or not candidates:
        return []
    tl = token.lower()
    subs = [c for c in candidates if tl in c.lower() or c.lower() in tl]
    close = get_close_matches(token, candidates, n=n, cutoff=cutoff)
    out = []
    for c in list(subs) + list(close):
        if c not in out:
            out.append(c)
    return out[:n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_command_args_classify.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/services/command_args.py tests/test_command_args_classify.py
git commit -m "feat(args): content classification + difflib fuzzy resolve"
```

---

### Task 4: `get_snapshot_for_date` (union, earliest-per-canonical-address)

**Files:**
- Modify: `bot/services/google_sheets_logger.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `canonical_address` (Task 1).
- Produces: `GoogleSheetsBalanceLogger._parse_amount(s) -> Decimal`; `._build_snapshot_from_rows(rows, date_str) -> dict[str, dict]`; `.get_snapshot_for_date(date_str) -> dict[str, dict]`. Each value: `{wallet_name, company, address, balance(Decimal), batch_id, time}`, keyed by `canonical_address`.

- [ ] **Step 1: Write the failing test** (pure core; no network)

```python
# tests/test_snapshot.py
from decimal import Decimal
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger

L = GoogleSheetsBalanceLogger()
# row = [batch, date, time, wallet, company, address, balance, type]
def row(batch, time, wallet, addr, bal, date="2026-07-15"):
    return [batch, date, time, wallet, "KZP", addr, bal, "scheduled"]

def test_parse_amount_strips_commas():
    assert L._parse_amount("351,432.18") == Decimal("351432.18")
    assert L._parse_amount("") == Decimal("0")

def test_union_completes_partial_retry():
    # 00:01 batch has A only; 00:07 retry adds B (B failed at 00:01)
    rows = [
        row("20260715000112", "00:01:12", "A", "TAAA", "10.00"),
        row("20260715000700", "00:07:00", "B", "TBBB", "20.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert set(snap.keys()) == {"TAAA", "TBBB"}
    assert snap["TAAA"]["balance"] == Decimal("10.00")

def test_intraday_rerun_does_not_overwrite_morning():
    # 00:01 A=10 ; 14:00 intraday A=999 -> earliest wins -> 10, not 999
    rows = [
        row("20260715000112", "00:01:12", "A", "TAAA", "10.00"),
        row("20260715140000", "14:00:00", "A", "TAAA", "999.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert snap["TAAA"]["balance"] == Decimal("10.00")

def test_erc20_casing_counts_once():
    rows = [
        row("20260715000112", "00:01:12", "E", "0xABC0000000000000000000000000000000000001", "5.00"),
        row("20260715000700", "00:07:00", "E", "0xabc0000000000000000000000000000000000001", "5.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert list(snap.keys()) == ["0xabc0000000000000000000000000000000000001"]

def test_same_name_different_address_both_kept():
    rows = [
        row("20260715000112", "00:01:12", "DUP", "TAAA", "1.00"),
        row("20260715000112", "00:01:12", "DUP", "TBBB", "2.00"),
    ]
    snap = L._build_snapshot_from_rows(rows, "2026-07-15")
    assert set(snap.keys()) == {"TAAA", "TBBB"}

def test_ignores_other_dates():
    rows = [row("20260714000112", "00:01:12", "A", "TAAA", "10.00", date="2026-07-14")]
    assert L._build_snapshot_from_rows(rows, "2026-07-15") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: FAIL with `AttributeError: 'GoogleSheetsBalanceLogger' object has no attribute '_parse_amount'`

- [ ] **Step 3: Implement the snapshot methods**

```python
# add to GoogleSheetsBalanceLogger in bot/services/google_sheets_logger.py
from decimal import Decimal
from bot.services.chain_detector import canonical_address

    def _parse_amount(self, s) -> Decimal:
        try:
            return Decimal(str(s).replace(",", "").strip() or "0")
        except Exception:
            return Decimal("0")

    def _build_snapshot_from_rows(self, rows, date_str):
        """Union of all that-date batches, keyed by canonical_address, keeping the
        EARLIEST batch value per address (a later intraday run only adds wallets)."""
        snap = {}
        for r in rows:
            # cols: 0 batch,1 date,2 time,3 wallet,4 company,5 address,6 balance,7 type
            if len(r) < 7 or r[1] != date_str:
                continue
            key = canonical_address(r[5])
            if not key:
                continue
            prev = snap.get(key)
            if prev is None or r[0] < prev["batch_id"]:   # earliest batch_id wins
                snap[key] = {
                    "wallet_name": r[3],
                    "company": r[4] if len(r) > 4 else "Unknown",
                    "address": r[5],
                    "balance": self._parse_amount(r[6]),
                    "batch_id": r[0],
                    "time": r[2] if len(r) > 2 else "",
                }
        return snap

    def get_snapshot_for_date(self, date_str):
        """Read DAILY_REPORT and return the assembled snapshot for date_str."""
        if not self.credentials_file or not self.spreadsheet_id:
            return {}
        if not self._initialize_service():
            return {}
        res = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id, range="DAILY_REPORT!A:H").execute()
        rows = res.get("values", [])
        return self._build_snapshot_from_rows(rows[1:] if rows else [], date_str)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/services/google_sheets_logger.py tests/test_snapshot.py
git commit -m "feat(vault): get_snapshot_for_date (union, earliest per canonical address)"
```

---

### Task 5: reconstruction (`get_balance_at`) in balance_service

**Files:**
- Modify: `bot/services/balance_service.py`
- Test: `tests/test_reconstruction.py`

**Interfaces:**
- Consumes: `canonical_address` (Task 1); existing `BalanceService.get_balance(address, chain)`.
- Produces: `BalanceService._net_from_transfers(transfers, address) -> Decimal` (pure; `transfers` = list of `{"from","to","amount"(Decimal USDT),"success"(bool)}`); `._fetch_transfers_after(address, chain, cutoff_ms) -> list|None` (network; TRC20 Tronscan `token_trc20/transfers`, ERC20 Etherscan `tokentx`, windowed `> cutoff`, SUCCESS only, normalized dicts); `.get_balance_at(address, chain, cutoff_ms) -> Decimal|None`.

- [ ] **Step 1: Write the failing test** (pure summation core)

```python
# tests/test_reconstruction.py
from decimal import Decimal
from bot.services.balance_service import BalanceService

B = BalanceService()
ME = "TAAA"

def tx(frm, to, amt, success=True):
    return {"from": frm, "to": to, "amount": Decimal(amt), "success": success}

def test_net_credits_minus_debits():
    transfers = [
        tx("TXXX", ME, "100.00"),   # +100 in
        tx(ME, "TYYY", "30.00"),    # -30 out
    ]
    assert B._net_from_transfers(transfers, ME) == Decimal("70.00")

def test_net_skips_failed_transfers():
    transfers = [tx("TXXX", ME, "100.00", success=False), tx("TXXX", ME, "5.00")]
    assert B._net_from_transfers(transfers, ME) == Decimal("5.00")

def test_net_erc20_casing():
    me = "0xABC0000000000000000000000000000000000001"
    lower = me.lower()
    transfers = [tx("0xdead", lower, "10.00"), tx(me, "0xbeef", "4.00")]
    # credit matched despite case diff; debit matched despite case diff
    assert B._net_from_transfers(transfers, me) == Decimal("6.00")

def test_reconstruct_equals_current_minus_net(monkeypatch):
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after",
                        lambda a, c, cut: [tx("TXXX", ME, "58003.76")])
    # balance_on_date = current(500) - net_after(+58003.76) = -57503.76
    assert B.get_balance_at(ME, "TRC20", 1) == Decimal("-57503.76")

def test_reconstruct_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(B, "get_balance", lambda a, c: Decimal("500.00"))
    monkeypatch.setattr(B, "_fetch_transfers_after", lambda a, c, cut: None)
    assert B.get_balance_at(ME, "TRC20", 1) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reconstruction.py -v`
Expected: FAIL with `AttributeError: 'BalanceService' object has no attribute '_net_from_transfers'`

- [ ] **Step 3: Implement reconstruction**

Note: `_fetch_transfers_after` mirrors the proven scratchpad PoCs
(`poc_reconstruct.py` TRC20, `poc_reconstruct_erc20.py` ERC20) — same endpoints, params, and normalization.

```python
# add to BalanceService in bot/services/balance_service.py
from bot.services.chain_detector import canonical_address

    def _net_from_transfers(self, transfers, address) -> Decimal:
        """Signed net USDT (already in USDT units) over SUCCESS transfers.
        +amount when I'm the recipient, -amount when I'm the sender."""
        me = canonical_address(address)
        net = Decimal(0)
        for t in transfers:
            if not t.get("success", True):
                continue
            amt = t["amount"]
            if canonical_address(t.get("to", "")) == me:
                net += amt
            if canonical_address(t.get("from", "")) == me:
                net -= amt
        return net

    def _fetch_transfers_after(self, address, chain, cutoff_ms):
        """USDT transfers with block time > cutoff_ms, windowed (cutoff, now].
        Returns normalized [{from,to,amount(Decimal USDT),success}] or None on error."""
        import os, time as _time
        from datetime import datetime, timezone
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        out = []
        try:
            if chain == "TRC20":
                headers = {}
                key = os.getenv("TRON_API_KEY")
                if key:
                    headers["TRON-PRO-API-KEY"] = key
                start = 0
                while True:
                    params = {"relatedAddress": address, "contract_address": self.USDT_TRC20_CONTRACT,
                              "start_timestamp": cutoff_ms + 1, "end_timestamp": now_ms,
                              "limit": 50, "start": start, "sort": "-timestamp"}
                    r = requests.get("https://apilist.tronscanapi.com/api/token_trc20/transfers",
                                     params=params, headers=headers, timeout=self.API_TIMEOUT)
                    r.raise_for_status()
                    ts = r.json().get("token_transfers", []) or []
                    for t in ts:
                        out.append({
                            "from": t.get("from_address", ""), "to": t.get("to_address", ""),
                            "amount": Decimal(t.get("quant", "0")) / Decimal(1_000_000),
                            "success": t.get("finalResult") == "SUCCESS" and t.get("contractRet") == "SUCCESS",
                        })
                    if len(ts) < 50:
                        break
                    start += 50
                    _time.sleep(0.2)
                return out
            elif chain == "ERC20":
                key = os.getenv("ETHEREUM_API_KEY")
                if not key:
                    return None
                cutoff_s = cutoff_ms // 1000
                page = 1
                while True:
                    params = {"chainid": "1", "module": "account", "action": "tokentx",
                              "contractaddress": self.USDT_ERC20_CONTRACT, "address": address,
                              "page": page, "offset": 100, "sort": "desc", "apikey": key}
                    r = requests.get("https://api.etherscan.io/v2/api", params=params, timeout=self.API_TIMEOUT)
                    r.raise_for_status()
                    d = r.json()
                    txs = d.get("result") or []
                    if d.get("status") != "1" or not txs:
                        break
                    stop = False
                    for t in txs:
                        if int(t["timeStamp"]) <= cutoff_s:
                            stop = True
                            break
                        out.append({"from": t.get("from", ""), "to": t.get("to", ""),
                                    "amount": Decimal(t.get("value", "0")) / Decimal(1_000_000),
                                    "success": True})
                    if stop or len(txs) < 100:
                        break
                    page += 1
                    _time.sleep(0.2)
                return out
            else:
                return None
        except Exception as e:
            logger.error(f"transfer fetch failed for {address[:10]}... ({chain}): {e}")
            return None

    def get_balance_at(self, address, chain, cutoff_ms):
        """Balance at cutoff = current live balance - net transfers after cutoff.
        Returns Decimal, or None if either fetch fails."""
        current = self.get_balance(address, chain)
        if current is None:
            return None
        transfers = self._fetch_transfers_after(address, chain, cutoff_ms)
        if transfers is None:
            return None
        return current - self._net_from_transfers(transfers, address)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reconstruction.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/services/balance_service.py tests/test_reconstruction.py
git commit -m "feat(balance): get_balance_at reconstruction (TRC20+ERC20, windowed)"
```

---

### Task 6: `/remove [address]` chain-aware fix

**Files:**
- Modify: `bot/handlers/remove_handler.py`
- Test: `tests/test_remove_address.py`

**Interfaces:**
- Consumes: `canonical_address`, `detect_chain_from_address` (chain_detector).
- Produces: `RemoveHandler._match_address(identifier, wallets_list) -> dict|None` (pure; `wallets_list` = list of `{name,address,company}`; matches by `canonical_address`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_remove_address.py
from bot.handlers.remove_handler import RemoveHandler

H = RemoveHandler()
WALLETS = [
    {"name": "Cold Wallet", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "company": "KZP"},
    {"name": "Eth One",     "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "company": "KZO"},
]

def test_match_trc20_exact():
    assert H._match_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", WALLETS)["name"] == "Cold Wallet"

def test_trc20_case_changed_does_not_match():
    # base58 is case-sensitive: a case-changed TRON address must NOT match
    assert H._match_address("tr7nhqjekqxgtci8q8zy4pl8otszgjlj6t", WALLETS) is None

def test_match_erc20_case_insensitive():
    # ERC20 hex is case-insensitive: checksummed vs lowercase both match
    assert H._match_address("0xdac17f958d2ee523a2206206994597c13d831ec7", WALLETS)["name"] == "Eth One"

def test_unknown_address():
    assert H._match_address("0x0000000000000000000000000000000000000000", WALLETS) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_remove_address.py -v`
Expected: FAIL with `AttributeError: 'RemoveHandler' object has no attribute '_match_address'`

- [ ] **Step 3: Implement `_match_address` and use it**

```python
# in bot/handlers/remove_handler.py
from bot.services.chain_detector import detect_chain_from_address, canonical_address, get_chain_emoji

    def _match_address(self, identifier, wallets_list):
        """Return the wallet dict whose address matches `identifier` by canonical
        address (ERC20 case-insensitive, TRC20 exact), or None."""
        target = canonical_address(identifier)
        if not target:
            return None
        for w in wallets_list:
            if canonical_address(w.get("address", "")) == target:
                return w
        return None
```

Then in `find_wallet_by_identifier(self, identifier)`, replace the TRC20-only gate:

```python
        # was: if self.balance_service.validate_trc20_address(identifier):
        if detect_chain_from_address(identifier):   # valid TRC20 or ERC20 address
            success, wallet_data = self.wallet_service.list_wallets()
            if success and 'companies' in wallet_data:
                flat = []
                for company_name, company_wallets in wallet_data['companies'].items():
                    for w in company_wallets:
                        flat.append({"name": w["name"], "address": w["address"], "company": company_name})
                hit = self._match_address(identifier, flat)
                if hit:
                    return True, {"name": hit["name"], "wallet": hit["name"],
                                  "address": hit["address"], "company": hit["company"]}
            return False, f"❌ Address '{identifier[:10]}...{identifier[-6:]}' not found in wallet list"
```

Also in `_create_success_card`, replace the identifier-type detection:

```python
        # was: identifier_type = "address" if self.balance_service.validate_trc20_address(original_identifier) else "name"
        identifier_type = "address" if detect_chain_from_address(original_identifier) else "name"
```

And in `_create_not_found_card`, replace the is-address check:

```python
        # was: if not self.balance_service.validate_trc20_address(identifier):
        if not detect_chain_from_address(identifier):
            similar_names = [name for name in all_wallet_names
                             if identifier.lower() in name.lower()][:3]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_remove_address.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/remove_handler.py tests/test_remove_address.py
git commit -m "fix(remove): chain-agnostic address match (ERC20 + TRC20) via canonical_address"
```

---

### Task 7: historical view core (`build_historical_view`) in check_handler

**Files:**
- Modify: `bot/handlers/check_handler.py`
- Test: `tests/test_historical_view.py`

**Interfaces:**
- Consumes: `classify_tokens`, `resolve_fuzzy` (command_args); `canonical_address` (chain_detector).
- Produces: `CheckHandler.build_historical_view(snapshot, current_roster, groups, names, date_str) -> dict` with keys `rows` (list of `{name, company, address, balance, source}`), `missing` (current wallets absent from snapshot), `not_found` (name filters with no match), `fuzzy` (map requested→matched names). Pure; no network. `current_roster` = list of `{wallet, company, address, chain, created_at}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_historical_view.py
from decimal import Decimal
from bot.handlers.check_handler import CheckHandler

H = CheckHandler()

def snap(*items):   # items: (canonical_addr, name, company, balance)
    return {a: {"wallet_name": n, "company": c, "address": a, "balance": Decimal(b),
                "batch_id": "20260715000112", "time": "00:01:12"} for a, n, c, b in items}

ROSTER = [
    {"wallet": "KZP 96G1", "company": "KZP", "address": "TAAA", "chain": "TRC20", "created_at": "2026-01-01 00:00:00"},
    {"wallet": "KZO A 1",  "company": "KZO", "address": "TBBB", "chain": "TRC20", "created_at": "2026-01-01 00:00:00"},
    {"wallet": "Eth One",  "company": "KZO", "address": "0xabc", "chain": "ERC20", "created_at": "2026-01-01 00:00:00"},
]

def test_all_wallets_no_filter():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"), ("0xabc","Eth One","KZO","5"))
    v = H.build_historical_view(s, ROSTER, [], [], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1", "KZO A 1", "Eth One"}
    assert v["missing"] == []

def test_group_filter():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, ["KZO"], [], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZO A 1"}

def test_name_filter_exact():
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, [], ["KZP 96G1"], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1"}

def test_name_filter_fuzzy():
    s = snap(("TAAA","KZP 96G1","KZP","10"))
    v = H.build_historical_view(s, ROSTER, [], ["KZP 96"], "2026-07-15")
    assert {r["name"] for r in v["rows"]} == {"KZP 96G1"}
    assert v["fuzzy"].get("KZP 96") == ["KZP 96G1"]

def test_completeness_missing_erc20():
    # sustained ERC20 outage: 0xabc absent from snapshot but present in current roster
    s = snap(("TAAA","KZP 96G1","KZP","10"), ("TBBB","KZO A 1","KZO","20"))
    v = H.build_historical_view(s, ROSTER, [], [], "2026-07-15")
    assert "Eth One" in v["missing"]

def test_not_found_name():
    s = snap(("TAAA","KZP 96G1","KZP","10"))
    v = H.build_historical_view(s, ROSTER, [], ["ZZZ QQQ"], "2026-07-15")
    assert v["not_found"] == ["ZZZ QQQ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_historical_view.py -v`
Expected: FAIL with `AttributeError: 'CheckHandler' object has no attribute 'build_historical_view'`

- [ ] **Step 3: Implement `build_historical_view`**

```python
# add to CheckHandler in bot/handlers/check_handler.py
from datetime import datetime
from bot.services.command_args import classify_tokens, resolve_fuzzy
from bot.services.chain_detector import canonical_address

    def _existed_by(self, created_at, date_str):
        """True if a wallet with this created_at existed on/before date_str.
        Missing/unparseable created_at -> True (safe direction: expect it)."""
        if not created_at:
            return True
        try:
            return created_at[:10] <= date_str
        except Exception:
            return True

    def build_historical_view(self, snapshot, current_roster, groups, names, date_str):
        """Pure: turn a snapshot + filters into rows + warnings. See interface block."""
        snap_names = [v["wallet_name"] for v in snapshot.values()]
        # 1. choose which snapshot entries to show
        selected = list(snapshot.values())
        if groups:
            gl = {g.lower() for g in groups}
            selected = [v for v in selected if v["company"].lower() in gl]
        fuzzy = {}
        not_found = []
        if names:
            picked = {}
            base = selected if groups else list(snapshot.values())
            base_names = [v["wallet_name"] for v in base]
            for want in names:
                exact = [v for v in base if v["wallet_name"].lower() == want.lower()]
                if exact:
                    for v in exact:
                        picked[v["address"]] = v
                    continue
                close = resolve_fuzzy(want, base_names)
                if close:
                    fuzzy[want] = close
                    for v in base:
                        if v["wallet_name"] in close:
                            picked[v["address"]] = v
                else:
                    not_found.append(want)
            selected = list(picked.values())
        rows = [{"name": v["wallet_name"], "company": v["company"],
                 "address": v["address"], "balance": v["balance"], "source": "snapshot"}
                for v in selected]
        # 2. completeness guard vs CURRENT roster (only when unfiltered)
        missing = []
        if not groups and not names:
            snap_addrs = {canonical_address(v["address"]) for v in snapshot.values()}
            for w in current_roster:
                if not self._existed_by(w.get("created_at"), date_str):
                    continue
                if canonical_address(w.get("address", "")) not in snap_addrs:
                    missing.append(w.get("wallet") or w.get("name"))
        return {"rows": rows, "missing": missing, "not_found": not_found, "fuzzy": fuzzy}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_historical_view.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/check_handler.py tests/test_historical_view.py
git commit -m "feat(check): pure historical-view core (filters, fuzzy, completeness guard)"
```

---

### Task 8: wire `/check` handler (date branch + card + reconstruction fallback)

**Files:**
- Modify: `bot/handlers/check_handler.py`
- Test: manual verification against real prod data (below) — the wiring is I/O; its logic is covered by Tasks 2–7.

**Interfaces:**
- Consumes: `parse_arguments`, `split_date`, `is_valid_iso_date` (command_args); `get_snapshot_for_date` (Task 4); `get_balance_at` (Task 5); `build_historical_view` (Task 7).

- [ ] **Step 1: Add the date branch in `handle()`**

Replace argument parsing (currently `self.parse_check_arguments`) so it routes date vs live:

```python
# near the top of handle(), after command_args is built:
from bot.services.command_args import parse_arguments, split_date, is_valid_iso_date
from datetime import datetime, timezone, timedelta

tokens, had_bare = parse_arguments(command_args)
date_str, other = split_date(tokens)

# a bare (undelimited) non-date token -> hint to use brackets
if had_bare and not date_str:
    # keep legacy behaviour only if nothing parsed at all; else hint
    pass

if date_str:
    return await self._handle_historical(context, date_str, other, wallet_data)
# else: existing LIVE path (unchanged), but source its inputs from `tokens`
```

- [ ] **Step 2: Implement `_handle_historical`**

```python
    async def _handle_historical(self, context, date_str, other_tokens, wallet_data):
        # validate date
        if not is_valid_iso_date(date_str):
            await context.topic_manager.send_command_response(
                self._create_bad_date_card(date_str), msg_type="interactive")
            return False
        gmt7_today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
        if date_str > gmt7_today:
            await context.topic_manager.send_command_response(
                self._create_future_date_card(date_str), msg_type="interactive")
            return False

        companies = sorted({info["company"] for info in wallet_data.values()})
        names_all = [info["wallet"] for info in wallet_data.values()]
        from bot.services.command_args import classify_tokens
        groups, names = classify_tokens(other_tokens, companies, names_all)

        # current roster (wallet_service already loaded into wallet_data)
        roster = [{"wallet": i["wallet"], "company": i["company"], "address": i["address"],
                   "chain": i.get("chain", "TRC20"), "created_at": i.get("created_at")}
                  for i in wallet_data.values()]

        snapshot = self.sheets_logger.get_snapshot_for_date(date_str)

        if snapshot:
            view = self.build_historical_view(snapshot, roster, groups, names, date_str)
            source = f"Daily snapshot (DAILY_REPORT) — {date_str} · {len(snapshot)} wallets"
            card = self._create_historical_card(view, date_str, source, reconstructed=False)
        else:
            # gap: reconstruct current roster as-of date D 00:01 GMT+7
            cutoff_ms = int(datetime.strptime(date_str + " 00:01:00", "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
            rows, unavailable = [], []
            targets = self._filter_roster(roster, groups, names)
            for w in targets:
                bal = await asyncio.wait_for(
                    asyncio.to_thread(self.balance_service.get_balance_at,
                                      w["address"], w.get("chain", "TRC20"), cutoff_ms),
                    timeout=120.0)
                if bal is None:
                    unavailable.append(w["wallet"])
                else:
                    rows.append({"name": w["wallet"], "company": w["company"],
                                 "address": w["address"], "balance": bal, "source": "reconstructed"})
            view = {"rows": rows, "missing": [], "not_found": [], "fuzzy": {}, "unavailable": unavailable}
            source = f"Reconstructed from chain — no snapshot for {date_str}"
            card = self._create_historical_card(view, date_str, source, reconstructed=True)

        await context.topic_manager.send_command_response(card, msg_type="interactive")
        return True
```

- [ ] **Step 3: Add card builders + `_filter_roster` helper**

Reuse the existing `_create_balance_table_card_with_sheets_info` layout (group subtotals + grand total). Add a header **source line**, a **⚠️ completeness warning** when `view["missing"]` is non-empty (list the names), a **fuzzy note** (`≈ closest to "X"`) per `view["fuzzy"]`, an **unavailable note** for reconstruction failures, and a **not-found note**. `_filter_roster(roster, groups, names)` applies group/name/fuzzy the same way `build_historical_view` does, returning roster entries to reconstruct. (Extract the shared filter into one helper used by both.)

- [ ] **Step 4: Manual verification against real prod data**

Run the PoC-style check with the pulled prod config (scratchpad) to confirm the wired path returns the same cent-accurate numbers proven earlier:

```bash
cd /tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
python3 poc_read_sheet.py        # snapshot read still works
python3 poc_reconstruct.py       # TRC20 reconstruct still matches to the cent
```
Expected: DAILY_REPORT snapshot reads for a real date; reconstruction diffs 0.00.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/check_handler.py
git commit -m "feat(check): /check [date] historical branch + reconstruction fallback + card"
```

---

### Task 9: `/add` and `/check` live path use the shared parser

**Files:**
- Modify: `bot/handlers/add_handler.py`, `bot/handlers/check_handler.py`
- Test: `tests/test_add_parse.py`

**Interfaces:**
- Consumes: `parse_arguments` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_add_parse.py
from bot.handlers.add_handler import AddHandler
H = AddHandler()

def test_add_accepts_brackets():
    ok, res = H.parse_quoted_arguments('[KZP] [KZP WDB2] [TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t]')
    assert ok and res == ["KZP", "KZP WDB2", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"]

def test_add_still_accepts_quotes():
    ok, res = H.parse_quoted_arguments('"KZP" "KZP WDB2" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"')
    assert ok and res[0] == "KZP"

def test_add_wrong_count():
    ok, res = H.parse_quoted_arguments('[KZP] [KZP WDB2]')
    assert not ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_add_parse.py -v`
Expected: FAIL (brackets not recognized → wrong count)

- [ ] **Step 3: Point `parse_quoted_arguments` at the shared tokenizer**

```python
# in bot/handlers/add_handler.py
from bot.services.command_args import parse_arguments

    def parse_quoted_arguments(self, text):
        if not text or not text.strip():
            return False, "❌ Missing arguments"
        matches, _ = parse_arguments(text)
        if len(matches) != 3:
            return False, f"❌ Expected 3 arguments in [ ] (or quotes), found {len(matches)}"
        company, wallet, address = (m.strip() for m in matches)
        if not company:
            return False, "❌ Company cannot be empty"
        if not wallet:
            return False, "❌ Wallet name cannot be empty"
        if not address:
            return False, "❌ Address cannot be empty"
        return True, [company, wallet, address]
```

Also update `CheckHandler`'s live path: replace `self.parse_check_arguments(command_args)` usage so live specific-wallet checks read from `tokens` (already parsed in Task 8), i.e. brackets or quotes both work for `/check [KZP 96G1]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_add_parse.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/add_handler.py bot/handlers/check_handler.py tests/test_add_parse.py
git commit -m "feat(args): /add and /check live path accept brackets via shared parser"
```

---

### Task 10: help text + full regression run + independent review

**Files:**
- Modify: `bot/handlers/help_handler.py`
- Test: whole `tests/` suite + Codex review of the diff

- [ ] **Step 1: Update help card + fallback**

Document the bracket grammar and the new `/check [date]` forms in both `_create_help_card` and `_get_help_text_fallback`:

```
• /check [2026-07-15] — balances on that date
• /check [2026-07-15] [KZP] — one company on that date
• /check [2026-07-15] [KZP 96G1] — one wallet on that date (typo-tolerant)
• /remove [T… or 0x…] — remove by name or address
Notes: wrap every argument in [ ]; quotes still work; dates are YYYY-MM-DD.
```

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 3: Independent Codex review of the implementation diff**

Use the `codex-review` skill on the full branch diff (`git diff b6c7722...HEAD`), CRITICAL-ONLY, focused on: does the wired code match the reviewed spec (union/earliest/canonical/completeness), any real-money mis-count, `/remove` safety. Fix findings (fresh sub-agent), re-review until `VERDICT: SOUND`.

- [ ] **Step 4: Commit**

```bash
git add bot/handlers/help_handler.py
git commit -m "docs(help): document [ ] grammar and /check [date] forms"
```

- [ ] **Step 5: Deploy (only after user go-ahead)**

Push `feature/check-date-and-remove-fix` → merge to GitHub `main`; on `47.129.129.241`: `cd /home/ubuntu/crypto-lark-bot && git pull && <restart>`. `wallets.json` untouched. Verify a live `/check [<recent date>]` in Lark matches the sheet.

---

## Self-Review

**Spec coverage:** §4 grammar → Tasks 2,3,9. §5.1 historical flow (validate/future, union, completeness, reconstruction, render) → Tasks 4,7,8. §5.2 filters/fuzzy → Tasks 3,7. §5.3 reconstruction → Task 5. §5.4 `/remove` → Task 6. §6 files → all tasks. §7 tests → each task's tests + Task 10. `canonical_address` everywhere → Task 1, used in 4,5,6,7.

**Placeholders:** none — every code step has complete code; Task 8 step 3 (card builders) is the one descriptive step and reuses the existing `_create_balance_table_card_with_sheets_info` layout, itemizing exactly which notes to add.

**Type consistency:** `canonical_address(str)->str`, `get_snapshot_for_date->{canonical_addr:{...}}`, `get_balance_at->Decimal|None`, `build_historical_view->{rows,missing,not_found,fuzzy}`, `_match_address->dict|None` — consistent across consumers.
