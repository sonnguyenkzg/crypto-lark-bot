# Production Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy `feature/check-date-and-remove-fix` (`feacdfe`, 49 commits) to the production Lark crypto bot on `47.129.129.241`, verify the daily finance report still works, and close the one missing day in 309 days of history.

**Architecture:** Code-only deploy. Prod already tracks `origin/main`, so the change ships by merging the branch into `main` and running `git pull` + `./start_lark_bot.sh restart` on the box. No config, dependency, or data migration. Rollback is `git reset --hard b6c7722` + restart.

**Tech Stack:** Python 3.12.3 in `.venv` on prod, `start_lark_bot.sh` process manager, ngrok tunnel, Google Sheets as the balance record, Lark for the UI.

Spec: `docs/superpowers/specs/2026-07-30-prod-migration-design.md`

## Global Constraints

- **NEVER copy `credentials/prd_env.txt` onto prod.** 21 of its 22 values already match prod's live `.env`; the only difference is `LARK_AUTHORIZED_USERS`, where **prod has 11 users and the file has 8**. Copying it would silently remove 3 authorised people. Prod's `.env` must not be modified at all.
- **Prod host:** `ubuntu@47.129.129.241`, key `credentials/OA-C-Finance.pem` (copy to a scratch path and `chmod 600` before use). App dir: `/home/ubuntu/crypto-lark-bot`.
- **Rollback commit:** `b6c7722`. **Deploy target:** `feacdfe` (or later branch head).
- **Prod runs FOUR processes** via `./start_lark_bot.sh`: `lark_bot.py` (commands), `main.py` (daily report scheduler), `wallets_to_gg_sheet.py` (wallet sync), `cleanup.py` (log rotation), plus ngrok. A restart cycles all of them, including ngrok — so the webhook blinks for a few seconds.
- **The daily report shares the rewritten code** (`balance_service`, `google_sheets_logger`) and will run **~40s slower** because outbound calls are paced 0.6s apart. There is no timeout on that path.
- **Dev and prod share ONE Google Sheet.** The dev bot must be stopped before prod goes live, or two bots can write to `DAILY_REPORT`.
- `.env` and `wallets.json` are gitignored on prod (verified), so `git pull` cannot modify them.
- **Daily report fires at 17:00 UTC** (= 00:01 GMT+7 next day). Do not deploy inside the few minutes around it.
- Never claim a step succeeded without pasting the command output that proves it.

---

### Task 1: Stop the dev bot so only prod writes to the shared sheet

**Files:** none (process management only)

**Interfaces:**
- Produces: a quiet dev environment — no dev process may write to `DAILY_REPORT` after this task.

- [ ] **Step 1: Record what is running in dev**

```bash
pgrep -af "lark_bot.py" | grep -v pgrep
pgrep -af "bin/ngrok" | grep -v pgrep
```
Note the PIDs. If nothing matches, dev is already down — record that and skip to Step 3.

- [ ] **Step 2: Stop the dev bot and dev tunnel**

Do **not** use `pkill -f "lark_bot.py"`. The pattern matches the invoking shell's own command line, so `pkill` kills that shell before it reports, returning a misleading exit code while leaving ngrok alive. Kill by PID instead, and trust only the `pgrep` re-check in Step 3 — never the exit code:

```bash
ME=$$
for pat in "python lark_bot.py" "ngrok http 8080"; do
  for p in $(pgrep -f "$pat"); do
    [ "$p" = "$ME" ] || [ "$p" = "$PPID" ] && continue
    cmd=$(ps -o args= -p "$p" 2>/dev/null | cut -c1-60)
    case "$cmd" in *pgrep*|*"for pat in"*) continue;; esac
    kill "$p" 2>/dev/null && echo "killed pid $p -> $cmd"
  done
done
```

Uvicorn shuts down gracefully and can take a few seconds. Wait for the process to actually exit rather than assuming, and escalate to `kill -9` only if it outlives the wait:

```bash
for p in $(pgrep -f "python lark_bot.py"); do
  timeout 45 tail --pid=$p -f /dev/null 2>/dev/null
  kill -0 $p 2>/dev/null && kill -9 $p
done
```

- [ ] **Step 3: Verify dev is silent**

```bash
pgrep -af "lark_bot.py" | grep -v pgrep || echo "dev bot: STOPPED"
curl -s --max-time 8 https://kzg-cryptobalance-dev.ngrok.app/ | head -c 80
```
Expected: `dev bot: STOPPED`, and the curl returns an ngrok offline page (`ERR_NGROK_3200`) rather than `{"status":"Bot is running"}`.

- [ ] **Step 4: Record the dev sheet row count as a baseline**

```bash
cd /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/crypto-lark-bot
.venv/bin/python - <<'PY'
import os
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
c=Credentials.from_service_account_file(os.environ['GOOGLE_CREDENTIALS_FILE'],
  scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
sh=build('sheets','v4',credentials=c).spreadsheets()
rows=sh.values().get(spreadsheetId=os.environ['GOOGLE_SHEET_ID'],range='DAILY_REPORT!A:H').execute().get('values',[])
print("DAILY_REPORT data rows before deploy:", len(rows)-1)
PY
```
Write the number down — later tasks compare against it.

---

### Task 2: Publish the code to GitHub `main`

**Files:**
- Modify: remote `origin/main` (currently `b6c7722`)

**Interfaces:**
- Consumes: local branch `feature/check-date-and-remove-fix` @ `feacdfe`.
- Produces: `origin/main` fast-forwarded to the branch head — this is what prod pulls in Task 3.

- [ ] **Step 1: Confirm the local branch is clean and tests pass**

```bash
cd /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/crypto-lark-bot
git status --short          # expect no output
git rev-parse --short HEAD  # expect feacdfe (or later)
.venv/bin/python -m pytest tests/ -q | tail -2
```
Expected: clean tree, `129 passed` (or more). **If anything fails, stop — do not deploy.**

- [ ] **Step 2: Confirm `main` has not moved underneath us**

```bash
git ls-remote --heads origin main
```
Expected: `b6c77223a22f...` — the same baseline prod runs. If it differs, someone else pushed; stop and reconcile before continuing.

- [ ] **Step 3: Push the feature branch**

```bash
git push -u origin feature/check-date-and-remove-fix
```

- [ ] **Step 4: Fast-forward `main` to the branch**

```bash
git checkout main
git pull --ff-only origin main
git merge --ff-only feature/check-date-and-remove-fix
git push origin main
git rev-parse --short HEAD
```
Expected: the merge is a fast-forward (no merge commit) and `main` now equals the branch head. If git refuses the fast-forward, stop — `main` has diverged and needs a decision.

- [ ] **Step 5: Return to the feature branch and verify the remote**

```bash
git checkout feature/check-date-and-remove-fix
git ls-remote --heads origin main
```
Expected: `origin/main` now points at the deploy target.

---

### Task 3: Deploy on prod and restart

**Files:**
- Modify (on prod): the git working tree at `/home/ubuntu/crypto-lark-bot`

**Interfaces:**
- Consumes: `origin/main` at the deploy target (Task 2).
- Produces: prod running the new code, all four processes plus ngrok back up.

- [ ] **Step 1: Set up the SSH key and confirm the pre-deploy state**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
mkdir -p "$SCRATCH"
cp /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/OA-C-Finance.pem "$SCRATCH/k.pem"
chmod 600 "$SCRATCH/k.pem"
ssh -i "$SCRATCH/k.pem" -o StrictHostKeyChecking=accept-new ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
echo "HEAD    : $(git rev-parse --short HEAD)"
echo "branch  : $(git branch --show-current)"
echo "dirty   : $(git status --short | wc -l) file(s)"
echo "time    : $(date -u) UTC"
'
```
Expected: `b6c7722`, branch `main`, 0 dirty files. **Check the clock — if it is within 10 minutes of 17:00 UTC, wait until the daily run has finished before continuing.**

- [ ] **Step 2: Back up the two gitignored files**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
cp .env .env.bak.$(date +%Y%m%d%H%M%S)
cp wallets.json wallets.json.bak.$(date +%Y%m%d%H%M%S)
ls -la .env.bak.* wallets.json.bak.* | tail -2
'
```
These are insurance only — `git pull` cannot touch gitignored files. **Do not modify `.env` itself.**

- [ ] **Step 3: Pull the new code**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
git pull --ff-only
echo "--- now at ---"
git rev-parse --short HEAD
git log --oneline -3
echo "--- .env untouched? ---"
git status --short
'
```
Expected: fast-forward to the deploy target, and `git status --short` shows nothing (the `.bak` files are gitignored patterns or untracked — if they appear as untracked that is fine, just confirm `.env` and `wallets.json` are NOT listed as modified).

- [ ] **Step 4: Confirm no new dependencies are needed**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
git diff b6c7722..HEAD --stat -- requirements.txt requirements_google.txt
.venv/bin/python -c "import bot.handlers.check_handler, bot.services.balance_service, bot.services.google_sheets_logger; print(\"imports OK on prod interpreter\")"
'
```
Expected: no diff in either requirements file, and `imports OK on prod interpreter`. **If the import fails, stop and roll back (Task 6).**

- [ ] **Step 5: Restart all services**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
./start_lark_bot.sh restart 2>&1 | tail -20
'
sleep 20
```

- [ ] **Step 6: Verify every process came back**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
./start_lark_bot.sh status 2>&1 | tail -20
echo "--- processes ---"
pgrep -af "python.*(lark_bot|main|wallets_to_gg_sheet|cleanup)\.py" | cut -c1-70
echo "--- ngrok ---"
pgrep -af ngrok | head -1 | cut -c1-60
echo "--- local health ---"
curl -s --max-time 5 http://127.0.0.1:8080/ || echo "LOCAL HEALTH FAILED"
'
```
Expected: `lark_bot.py` and `main.py` both running, ngrok running, and `{"status":"Bot is running","webhook":"/webhook"}`.
**If ngrok did not return, re-run `./start_lark_bot.sh restart`. If the local health check fails, roll back (Task 6).**

- [ ] **Step 7: Verify the code actually loaded (not a stale process)**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
PID=$(pgrep -f "python lark_bot.py" | head -1)
BOT=$(ps -o lstart= -p $PID | xargs -I{} date -d "{}" +%s)
CM=$(git log -1 --format=%ct)
echo "bot started : $(ps -o lstart= -p $PID)"
echo "commit made : $(git log -1 --format=%cd)"
[ "$BOT" -gt "$CM" ] && echo ">>> bot is running the NEW code" || echo ">>> STALE PROCESS - restart again"
'
```
Expected: `>>> bot is running the NEW code`. A Python process does not hot-reload, so this check is what proves the deploy took effect.

---

### Task 4: Smoke test in Lark, then the Pareto 5

**Files:** none (verification only)

**Interfaces:**
- Consumes: prod running the new code (Task 3).
- Produces: confidence that the command surface works before touching the finance report.

- [ ] **Step 1: Son runs the smoke test in the prod Lark chat**

Ask Son to send, in order:
1. `/start` — bot responds
2. `/help` — the card shows the bracket grammar (`/check [YYYY-MM-DD]`, `/remove [name or address]`) and contains no "must be in quotes" text

**Stop here and roll back if the bot does not answer.**

- [ ] **Step 2: Pareto case 1 — a recorded day**

`/check [2026-07-15]`
Expected: **13,766,045.97 USDT**; summary opens `Total wallets in monitoring: 71`; 68 have a balance recorded; the 3 wallets added later are named in bold; `68 wallets counted`.

- [ ] **Step 3: Pareto case 2 — name matching**

`/check [2026-07-15] [DPP COY]`
Expected: **only `DPP COY TRC`**. `KZP COY` must NOT appear.

- [ ] **Step 4: Pareto case 3 — self-completion**

`/check [2026-07-20] [KZP TH BM 1]` twice.
Expected: **10.09 USDT** both times, and the second reply is fast (~1s) with no "saved to Google Sheets" line. (The figure was rebuilt and saved during dev testing, so even the first run should be quick.)

- [ ] **Step 5: Pareto case 4 — the reported bug**

```
/add [TEST] [KZG TEST WALLET] [0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]
/remove [0x6391f743E1cb0FCF9Fd3e602b43e548B4c1a8071]
/list
```
Expected: added with chain **🔷 ERC20**; removed successfully, card says identified **by address**, chain shown as **🔷 ERC20** (not TRC20); `/list` back to 71 wallets.

- [ ] **Step 6: Pareto case 5 — the routing guard**

`/check 2026-07-15` (no brackets)
Expected: **⚠️ Wrap Dates and Filters in [ ]** — one card, and it must NOT return today's live balances.

- [ ] **Step 7: Record the results**

Note each case's actual figure. Any case returning a materially different number than above is a rollback trigger (Task 6).

---

### Task 5: Verify the daily finance report, then close the gap

**Files:** none (verification + intended data writes)

**Interfaces:**
- Consumes: a verified command surface (Task 4).
- Produces: proof the daily-report write path works on prod, and a complete `DAILY_REPORT` history.

- [ ] **Step 1: Note the sheet row count before the forced run**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
tail -3 logs/daily_reports.log
'
```
Also keep the baseline row count from Task 1 Step 4 to hand.

- [ ] **Step 2: Force a daily report run**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
source .venv/bin/activate
timeout 400 python main.py test 2>&1 | tail -25
'
```
This is the step that proves the write path a single HTTP 503 silently broke before. Expect it to take **~2 minutes** (about 40s longer than it used to, because of request pacing).

Expected in the output: `Report summary: 71 wallets, <total> USDT total`, `Logged 71 balance records to DAILY_REPORT`, and `Daily report sent successfully`.
**Accepted cost:** today already has one batch, so this appends a second batch of ~71 rows for today. Reads are unaffected — the earliest batch per wallet wins.

- [ ] **Step 3: Confirm the rows actually landed and the card posted**

Check the Lark daily-report topic for the card, then:
```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
grep -E "Logged .* balance records|Report summary|Google Sheets API error|FAILED to log" logs/daily_reports.log | tail -5
'
```
Expected: a `Logged 71 balance records` line and **no** `Google Sheets API error` / `FAILED to log` line.
**If the write failed, that is a rollback trigger** — the pre-existing 503 handling is exactly what this change was meant to make safe.

- [ ] **Step 4: Close the 2026-07-20 gap**

Ask Son to send `/check [2026-07-20]` in Lark (no filter).
Expected: acknowledgement, then a "Rebuilding From Blockchain" card naming ~69 wallets, then after ~3 minutes a total of ≈ **14,430,032.60 USDT** with a `📈 … saved to Google Sheets` line and **no** "could not be calculated" note.

- [ ] **Step 5: Prove the gap is closed**

```bash
cd /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/crypto-lark-bot
.venv/bin/python - <<'PY'
import os
from collections import Counter
for l in open("/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/credentials/dev_env.txt"):
    l=l.strip()
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); os.environ[k.strip()]=v.strip().strip('"').strip("'").split("#")[0].strip()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
c=Credentials.from_service_account_file(os.environ['GOOGLE_CREDENTIALS_FILE'],
  scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
sh=build('sheets','v4',credentials=c).spreadsheets()
rows=sh.values().get(spreadsheetId=os.environ['GOOGLE_SHEET_ID'],range='DAILY_REPORT!A:H').execute().get('values',[])[1:]
r=[x for x in rows if len(x)>7 and x[1]=="2026-07-20"]
print(f"2026-07-20 rows: {len(r)}  types: {dict(Counter(x[7] for x in r))}")
dates=sorted({x[1] for x in rows if len(x)>1})
from datetime import date, timedelta
d0,d1=date.fromisoformat(dates[0]),date.fromisoformat(dates[-1])
have=set(dates); gaps=[]
d=d0
while d<=d1:
    if d.isoformat() not in have: gaps.append(d.isoformat())
    d+=timedelta(days=1)
print(f"calendar {d0} .. {d1}: {len(gaps)} gap(s) remaining -> {gaps}")
PY
```
Expected: ~70 rows for 2026-07-20 and **0 gaps remaining**.

- [ ] **Step 6: Watch the natural 17:00 UTC run**

After 17:00 UTC:
```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
grep -E "SCHEDULED REPORT TRIGGERED|Report time|Report summary|Logged .* balance records|error|Error" logs/daily_reports.log | tail -8
'
```
Expected: one triggered run, a `Report summary: 71 wallets`, a `Logged 71 balance records` line, and no errors. **This is the real proof** — the forced run in Step 2 exercises the same path but this is the scheduled one the finance team depends on.

---

### Task 6: Rollback (only if a trigger fires)

**Files:**
- Modify (on prod): the git working tree at `/home/ubuntu/crypto-lark-bot`

**Rollback triggers** — any one of these:
- `/start` or `/help` does not respond after the restart (Task 4 Step 1)
- The prod interpreter cannot import the new modules (Task 3 Step 4)
- The local health check fails (Task 3 Step 6)
- The forced daily report errors or writes nothing (Task 5 Step 3)
- Any Pareto case returns a materially different figure than the expected value

- [ ] **Step 1: Reset prod to the previous commit and restart**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
git reset --hard b6c7722
git rev-parse --short HEAD
./start_lark_bot.sh restart 2>&1 | tail -10
'
sleep 20
```

- [ ] **Step 2: Verify the rollback**

```bash
SCRATCH=/tmp/claude-1000/-home-son-workspaces-kzg/a3a4f4b2-c18c-405d-a097-8265004f9d1c/scratchpad
ssh -i "$SCRATCH/k.pem" ubuntu@47.129.129.241 '
cd /home/ubuntu/crypto-lark-bot
echo "HEAD: $(git rev-parse --short HEAD)"
./start_lark_bot.sh status 2>&1 | tail -10
curl -s --max-time 5 http://127.0.0.1:8080/ || echo "LOCAL HEALTH FAILED"
'
```
Expected: `b6c7722` and a healthy bot. Then ask Son to confirm `/check` works in Lark.

- [ ] **Step 3: Note what rows the new code left behind**

Rows written while the new code was live remain in `DAILY_REPORT`. They are valid rows the old code reads normally — rebuilt ones carry `Check Type = rebuilt`, so they stay distinguishable from measured figures. No cleanup is required, but record what was written so the failure can be diagnosed.

---

### Task 7: Record the outcome

**Files:**
- Modify: `/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/DEV_TEST_RESULTS.md`
- Create: `/home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/PROD_MIGRATION_LOG.md`

- [ ] **Step 1: Write the migration log**

Create `PROD_MIGRATION_LOG.md` capturing, with real values (not placeholders): the date and time of the deploy, the commit deployed and the previous commit, the output of the process/status checks, each Pareto case's actual figure, the forced daily-report totals, the 2026-07-20 gap-fill total and the remaining-gap count, and the 17:00 UTC run result.

- [ ] **Step 2: Note that prod's `.env` was not modified**

State explicitly in the log that `credentials/prd_env.txt` was **not** applied, and why: 21 of 22 values already matched, and its `LARK_AUTHORIZED_USERS` has 8 entries against prod's 11 — applying it would have removed 3 people.

- [ ] **Step 3: Commit the log**

```bash
cd /home/son/workspaces/kzg/tasks/20260721_Crypto_Bot_Improvement/crypto-lark-bot
git add ../PROD_MIGRATION_LOG.md 2>/dev/null || true
git commit -m "docs: production migration log" || echo "(log lives outside the repo — fine)"
```
The task folder is not the bot repo; if the log sits outside it, leave it as a local file and say so.

---

## Self-Review

**Spec coverage:** §2 do-not-touch `.env` → Global Constraints + Task 7 Step 2. §3 blast radius → Task 3 Steps 4/6/7 and Task 5. §4 Step 1 retire dev → Task 1. §4 Step 2 ship → Tasks 2–3. §4 Step 3 `/start` → Task 4 Step 1. §4 Step 4 verification → Tasks 4–5. §5 rollback → Task 6. §6 risks: ngrok blink → Task 3 Step 6; pacing → Task 5 Step 2; extra rows → Task 5 Step 2 note; lock → covered by the "Another Check Is Running" card already shipped.

**Placeholders:** none — every step carries the exact command and the expected output.

**Consistency:** `b6c7722` is the rollback commit throughout; `feacdfe` is the deploy target throughout; the SSH key is copied to the same scratch path in every task that uses it; `./start_lark_bot.sh restart|status` is the only process-control mechanism used.

**Note for the executor:** Tasks 4 and 5 need Son in Lark — they cannot be completed head-down. Stop and ask at Task 4 Step 1, and again at Task 5 Step 4.
