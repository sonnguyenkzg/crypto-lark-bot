# Production Deployment Guide

This guide covers deploying the latest changes to the production environment.

## Prerequisites

- Access to production server
- Git repository access
- Production `.env` file configured
- ngrok company subscription token configured

## Deployment Steps

### 1. Pull Latest Code

In your production environment:

```bash
cd /path/to/crypto-lark-bot
git pull origin main
```

### 2. Verify Production Configuration

Check your `.env` file contains production settings:

```bash
cat .env | grep ENVIRONMENT
```

**Required settings:**
- `ENVIRONMENT=PROD` (not DEV)
- All API keys configured for production
- `WALLETS_FILE=wallets.json` (production wallet file)
- `NGROK_KZG_TOKEN=<your_company_token>`

The ngrok domain will automatically be: `https://kzg-cryptobalance-PROD.ngrok.app`

### 3. Restart Services

```bash
./start_lark_bot.sh restart
```

This will:
- Stop all existing processes
- Clear environment variables
- Load fresh configuration from `.env`
- Start ngrok with fixed PROD domain
- Start Lark bot
- Start daily reports scheduler
- Start Google Sheets sync
- Start log cleanup

### 4. Update Lark Webhook URL

After startup, the script will display the webhook URL in a box:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     🔗 LARK WEBHOOK CONFIGURATION                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  Copy this URL to your Lark Developer Console:                             │
│                                                                             │
│  https://kzg-cryptobalance-PROD.ngrok.app/webhook                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Steps to update:**
1. Go to: https://open.larksuite.com/
2. Select your app → **Features** → **Bot** → **Event Configuration**
3. Update **Request URL** with: `https://kzg-cryptobalance-PROD.ngrok.app/webhook`
4. Save changes

### 5. Verify Deployment

#### Test Daily Report
```bash
python main.py test
```

**Verify:**
- ✅ Report sent to Lark daily reports topic
- ✅ KZDW company appears in totals
- ✅ ERC20 wallets show correct balances
- ✅ Companies sorted alphabetically
- ✅ Google Sheets logged successfully

#### Test Interactive Commands in Lark

In your Lark topic, test:

```
/start
/help
/list
/check
```

**Verify:**
- ✅ Bot responds to commands
- ✅ Help shows both TRC20 and ERC20 formats
- ✅ /check displays dynamic company grouping
- ✅ KZDW appears in company totals
- ✅ ERC20 wallets fetch correctly

#### Monitor Logs

```bash
# View all logs
tail -f logs/*.log

# View specific logs
tail -f logs/lark_bot.log
tail -f logs/daily_reports.log
tail -f logs/sheets_sync.log
```

### 6. Check Service Status

```bash
./start_lark_bot.sh status
```

**Expected output:**
```
✅ ngrok Tunnel: Running
✅ Lark Bot: Running
✅ Daily Reports: Running
✅ Google Sheets Sync: Running
✅ Log Cleanup: Running
```

## Key Features in This Release

### 1. Fixed ngrok Domain
- **DEV**: `https://kzg-cryptobalance-DEV.ngrok.app`
- **PROD**: `https://kzg-cryptobalance-PROD.ngrok.app`
- No more random URLs - fixed domain per environment

### 2. ERC20 Support
- ✅ Both TRC20 and ERC20 USDT wallets supported
- ✅ Automatic chain detection from address format
- ✅ TRC20: Starts with 'T' (33-35 chars)
- ✅ ERC20: Starts with '0x' (42 chars)
- ✅ Backward compatible - wallets without chain default to TRC20

### 3. Dynamic Company Grouping
- ✅ Companies auto-discovered from wallet data
- ✅ KZDW now appears in reports
- ✅ Future companies automatically included
- ✅ Alphabetical sorting (except KZG+KZO merge)
- ✅ Works in both /check command and daily reports

### 4. Updated Documentation
- ✅ Help messages show TRC20 and ERC20 formats
- ✅ README updated with multi-chain support
- ✅ UAT test cases updated

## Scheduled Jobs

All times are **GMT+7** (Thailand timezone):

| Job | Schedule | Description |
|-----|----------|-------------|
| Daily Reports | 00:00 GMT+7 | Balance report to Lark |
| Google Sheets Sync | 00:00 GMT+7 | Sync wallets to spreadsheet |
| Log Cleanup | 00:30 GMT+7 | Remove old logs (3 days) |

## Troubleshooting

### Webhook Not Responding
```bash
# Check ngrok logs
tail -f logs/ngrok.log

# Verify ngrok is running
ps aux | grep ngrok

# Test webhook endpoint
curl https://kzg-cryptobalance-PROD.ngrok.app/webhook
```

### Bot Not Responding to Commands
```bash
# Check bot logs
tail -f logs/lark_bot.log logs/lark_bot_errors.log

# Verify bot is running
ps aux | grep lark_bot.py

# Restart bot
./start_lark_bot.sh restart
```

### Balance Fetching Issues
- **TRC20 errors**: Check `TRON_API_KEY` in `.env`
- **ERC20 errors**: Check `ETHEREUM_API_KEY` in `.env` (Etherscan API key)

### Google Sheets Not Logging
```bash
# Check credentials file exists
ls -la kzg-cryptohash-serviceaccount-key.json

# Check sheets sync logs
tail -f logs/sheets_sync.log

# Test manual sync
python wallets_to_gg_sheet.py test
```

## Rollback Procedure

If issues occur, rollback to previous version:

```bash
# Check recent commits
git log --oneline -5

# Rollback to previous commit
git reset --hard <previous_commit_hash>

# Restart services
./start_lark_bot.sh restart
```

## Environment Differences

| Setting | DEV | PROD |
|---------|-----|------|
| ENVIRONMENT | DEV | PROD |
| ngrok Domain | kzg-cryptobalance-DEV.ngrok.app | kzg-cryptobalance-PROD.ngrok.app |
| Wallets File | wallets.json or wallets.test.json | wallets.json |
| Lark App | DEV app | PROD app |

## Support

If you encounter issues:

1. Check logs: `tail -f logs/*.log`
2. Verify configuration: `.env` file settings
3. Check service status: `./start_lark_bot.sh status`
4. Review GitHub issues: https://github.com/sonnguyenkzg/crypto-lark-bot/issues

## Post-Deployment Checklist

- [ ] Git pull completed successfully
- [ ] `.env` file configured for PROD
- [ ] Services restarted with `./start_lark_bot.sh restart`
- [ ] Lark webhook URL updated in developer console
- [ ] Daily report test passed (`python main.py test`)
- [ ] KZDW appears in report totals
- [ ] ERC20 wallets fetching correctly
- [ ] Bot responding to /check command
- [ ] All services running (`./start_lark_bot.sh status`)
- [ ] Logs monitored for errors
- [ ] Google Sheets sync working

---

**Last Updated**: 2026-01-23
**Latest Commit**: `97610cb` - Fix daily report to support ERC20 and dynamic company grouping
