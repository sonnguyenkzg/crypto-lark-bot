# Pre-GitHub Push Cleanup Checklist

## ✅ Completed

1. **Updated .gitignore** - Added:
   - `wallets.json` (production data)
   - `wallets.test.json` (test data)
   - `*.pre-erc20.*` (backup files)

2. **Created Template Files:**
   - `wallets.json.example` - Example wallet configuration
   - `.env.example` - Example environment configuration

## 📁 File Organization

### Files to KEEP (add to git):
- ✅ `bot/services/chain_detector.py` - New feature
- ✅ `bot/services/ethereum_validator.py` - New feature
- ✅ `migrations/` - Migration scripts (useful for reference)
- ✅ `test_erc20_support.py` - Test suite (useful for future)
- ✅ `discover_env_ids.py` - Utility script (useful for setup)
- ✅ `ERC20_IMPLEMENTATION_SUMMARY.md` - Documentation
- ✅ `wallets.json.example` - Template
- ✅ `.env.example` - Template

### Files to DELETE (sensitive/temporary):
- ❌ `wallets.json.pre-erc20.20260123_044829` - Backup (ignored by .gitignore)
- ❌ `wallets.json.backup.20260123_044824` - Backup (ignored by .gitignore)
- ❌ `wallets.test.json.pre-erc20.20260123_043950` - Test backup (ignored by .gitignore)

### Files IGNORED (won't be committed):
- 🔒 `wallets.json` - Production wallet data
- 🔒 `wallets.test.json` - Test wallet data
- 🔒 `.env` - Environment secrets

## 🧹 Cleanup Commands

### Remove backup files:
```bash
rm -f wallets.json.pre-erc20.* wallets.json.backup.* wallets.test.json.pre-erc20.*
```

### Stage new files:
```bash
git add .gitignore
git add wallets.json.example
git add .env.example
git add bot/services/chain_detector.py
git add bot/services/ethereum_validator.py
git add migrations/
git add test_erc20_support.py
git add discover_env_ids.py
git add ERC20_IMPLEMENTATION_SUMMARY.md
```

### Stage modified files:
```bash
git add bot/handlers/
git add bot/services/balance_service.py
git add bot/services/wallet_service.py
git add bot/utils/config.py
git add start_lark_bot.sh
git add README/
```

### Verify status:
```bash
git status
```

### Expected output:
- Modified files should be listed
- `wallets.json` should NOT appear (ignored)
- `.env` should NOT appear (ignored)
- Backup files should NOT appear (deleted/ignored)

## ⚠️ Pre-Commit Verification

**CRITICAL: Ensure these are NOT in git:**
- [ ] `wallets.json` (contains real addresses)
- [ ] `.env` (contains API keys and secrets)
- [ ] Any backup files

**Run this check:**
```bash
git status | grep -E "wallets\.json|\.env"
```

If these files appear, they are NOT properly ignored!

## 📝 Suggested Commit Message

```
feat: Add ERC20 (Ethereum) wallet support and enhance company grouping

Features:
- ✨ Add ERC20 (Ethereum) USDT wallet support alongside TRC20
- ✨ Auto-detect chain type from address format
- ✨ Dynamic company grouping in /check command
- 🔧 Fixed ngrok domain support for company subscription

Enhancements:
- 📚 Update help messages to document both TRC20 and ERC20
- 📊 KZDW company now appears in summary totals
- 🔄 New companies automatically show in grouping
- 🌐 Fixed webhook URL: kzg-cryptobalance-{ENV}.ngrok.app

Files:
- New: bot/services/chain_detector.py
- New: bot/services/ethereum_validator.py
- New: migrations/ (add_chain_field.py, rollback_chain_field.py)
- Updated: check_handler.py (dynamic grouping)
- Updated: help_handler.py (ERC20 documentation)
- Updated: start_lark_bot.sh (fixed ngrok domain)
- Updated: README.md, UAT_TEST_CASES.md

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```
