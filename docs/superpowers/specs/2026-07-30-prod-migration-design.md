# Design — migrating `/check [date]` + `/remove` fixes to production

**Date:** 2026-07-30
**Status:** Approved (brainstorm), pending spec review
**Deploying:** `feature/check-date-and-remove-fix` @ `feacdfe` → prod `47.129.129.241`
**Currently on prod:** `b6c7722` (branch `main`, clean tree)

---

## 1. What ships

49 commits, 10 code files (+1241 / −215). Two rounds of work:

- **Round 1** — `/check [YYYY-MM-DD]` historical balances; `/remove` by address; bracket argument grammar.
- **Round 2** — per-wallet resolution with self-completing history; tiered name matching; `/remove` bracket parsing; reporting scoped to `wallets.json`; card rewording.

Plus fixes found by review and live testing: provider error bodies no longer become wrong balances,
negative rebuilds rejected, rebuild workers bounded, Sheets calls off the event loop, a failed sheet
read can no longer trigger writes, tests can no longer reach the production sheet, and `/remove` by
address reports the correct chain.

**129 unit tests pass. 32 live checks pass against the real sheet and chain.**

---

## 2. Key finding: this is a code-only deploy

`credentials/prd_env.txt` was compared against prod's live `.env`, key by key:

| | |
|---|---|
| Keys in each | 22, identical names |
| **Values identical** | **21 of 22** |
| Values differing | 1 — `LARK_AUTHORIZED_USERS` |

Prod holds **11** authorised users; `prd_env.txt` holds **8**. **Prod is more complete.**

> **DO NOT copy `prd_env.txt` onto prod.** It would silently remove 3 authorised people.
> Prod's `.env` is correct as-is and must not be touched.

Therefore: no config change, no new environment variables, no new dependencies, no schema or data
migration. Only application code moves.

---

## 3. Blast radius

Prod runs two Python processes plus ngrok, all managed by `./start_lark_bot.sh`:

| Process | Purpose | Affected |
|---|---|---|
| `lark_bot.py` | `/check`, `/add`, `/remove`, `/list`, `/help` | **Yes** — all new work |
| `main.py` | the 00:01 GMT+7 daily snapshot (17:00 UTC trigger) | **Yes, indirectly** — shares `balance_service` and `google_sheets_logger` |
| `wallets_to_gg_sheet.py` | syncs `wallets.json` ← `WALLET_LIST` | No |
| `cleanup.py` | log rotation | No |

The daily report is the finance record, so it is the highest-value thing to verify. It now runs
through the paced, retrying fetch and will take roughly **40 seconds longer** (0.6s spacing × 67
TRC20 wallets). There is no timeout on that path, so the extra time is safe.

**Environment facts confirmed on prod:** Python 3.12.3, `.venv` present, `wallets.json` = 71 wallets
(same as dev), tree clean at `b6c7722`.

---

## 4. Migration steps

### Step 1 — retire dev first
Dev and prod share one Google Sheet. Leaving dev running would let two bots write to
`DAILY_REPORT`. Stop the dev bot and dev ngrok before prod goes live.

### Step 2 — ship the code
```
push feature/check-date-and-remove-fix  →  merge into GitHub main
prod: cd /home/ubuntu/crypto-lark-bot
      cp .env .env.bak
      cp wallets.json wallets.json.bak
      git pull                        # b6c7722 -> feacdfe (fast-forward)
      ./start_lark_bot.sh restart
      ./start_lark_bot.sh status
```
`.env` and `wallets.json` are gitignored, so `git pull` cannot modify them. The backups are
insurance only.

### Step 3 — smoke test in Lark
Son runs **`/start`**, then **`/help`** (should show the bracket grammar, no "must be in quotes").

### Step 4 — verify, in order
1. **The Pareto 5** from `DEV_TEST_PLAN.md`: `/check [2026-07-15]`; `/check [2026-07-15] [DPP COY]`;
   `/check [2026-07-20] [KZP TH BM 1]` twice; `/add` then `/remove` by address; `/check 2026-07-15`
   with no brackets.
2. **Forced daily report** — `python main.py test`. Proves the write path a single HTTP 503 once
   broke. **Cost:** today already holds one batch, so this appends a second batch of ~71 rows for
   today's date. Reads are unaffected because the earliest batch per wallet wins.
3. **Close the gap** — `/check [2026-07-20]` (~3 minutes, ~69 rows). Fills the only missing day in
   309 and proves the rebuild path on prod.
4. **Watch the natural 17:00 UTC run** and confirm exactly one clean batch.

---

## 5. Rollback

```
prod: git reset --hard b6c7722 && ./start_lark_bot.sh restart
```

Complete and immediate, because only code changed. Rows written by the new code remain, but they are
valid `DAILY_REPORT` rows that the old code reads normally — rebuilt rows are marked
`Check Type = rebuilt`, so they stay distinguishable from measured ones.

**Rollback triggers:** `/start` or `/help` fails after restart; the forced daily report errors or
writes nothing; any Pareto case returns a materially different figure than dev.

---

## 6. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `restart` cycles ngrok, so the webhook blinks | Certain, seconds | `./start_lark_bot.sh status` confirms it returned; re-run `restart` if not |
| Daily report ~40s slower from request pacing | Certain | No timeout on that path; forced test run in step 4.2 proves it end to end |
| Forced test run adds ~71 rows for today | Certain | Accepted. Reads take the earliest batch per wallet, so the original stands |
| Gap-fill writes ~69 rows | Certain | Intended — that is the feature closing a real hole |
| A rebuild holds the command lock up to 240s | Only on a date with missing balances | Bounded by `RECON_TOTAL_BUDGET`; a blocked `/check` now replies "Another Check Is Running" instead of going silent |
| Someone later copies `prd_env.txt` onto prod | Low | Recorded here and in the migration plan: it would drop 3 authorised users |

---

## 7. Out of scope

USDC / multi-token support (a later spec), and any change to how the live `/check` computes current
balances.
