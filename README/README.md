# Lark Crypto Wallet Monitor Bot

A professional Lark bot that automatically monitors USDT (TRC20) wallet balances and delivers daily reports through interactive cards. Built for enterprise teams managing multiple cryptocurrency wallets across business entities.

## Features

**Real-Time Monitoring**: Instant USDT balance checks with interactive card responses  
**Automated Daily Reports**: Scheduled balance summaries posted to dedicated Lark topics  
**Multi-Company Organization**: Wallet grouping by business entity with consolidated reporting  
**Enterprise Security**: Lark Open ID-based authorization with webhook validation  
**Interactive Interface**: Rich card UI with tables, totals, and actionable responses  

## Quick Start

### Prerequisites
- Python 3.8+
- Lark App credentials (App ID & Secret)
- Lark group chat with configured topics
- Authorized user Open IDs
- Public webhook endpoint

### Installation

1. **Clone and setup environment**
   ```bash
   git clone <repository-url>
   cd lark-crypto-bot
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your Lark app configuration
   ```

3. **Initialize wallet configuration**
   ```bash
   # Edit wallets.json or use /add command after startup
   ```

4. **Start the bot**
   ```bash
   ./start_lark_bot.sh
   ```

## Configuration

Create a `.env` file with your Lark app settings:

```env
# Lark App Configuration
LARK_APP_ID=cli_xxxxxxxxxxxxxxxxxx
LARK_APP_SECRET=xxxxxxxxxxxxxxxxxx
LARK_CHAT_ID=oc_xxxxxxxxxxxxxxxxxx

# Topic Configuration
LARK_TOPIC_COMMANDS=omt_xxxxxxxxxxxxxxxxxx
LARK_TOPIC_DAILYREPORT=omt_xxxxxxxxxxxxxxxxxx
LARK_TOPIC_COMMANDS_MSG=om_xxxxxxxxxxxxxxxxxx
LARK_TOPIC_DAILYREPORT_MSG=om_xxxxxxxxxxxxxxxxxx

# Authorization (comma-separated Open IDs)
LARK_AUTHORIZED_USERS=ou_xxxxxxxxxxxxxxxxxx,ou_yyyyyyyyyyyyyyyyyy

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
TRON_API_KEY=xxxxxxxxxxxxxxxxxx
```

## Commands

### Wallet Management
- `/start` - Initialize bot and verify connection
- `/help` - Display all available commands with usage examples
- `/list` - Show all configured wallets grouped by company
- `/add "company" "wallet_name" "address"` - Add new wallet to monitoring
- `/remove "wallet_name"` - Remove wallet from monitoring (supports names and addresses)

### Balance Operations
- `/check` - Check all wallet balances with formatted table
- `/check "wallet_name"` - Check specific wallet balance
- `/check "TRC20_address"` - Check balance by wallet address
- `/check "wallet1" "wallet2"` - Check multiple specific wallets

### Usage Examples
```bash
/add "KZP Holdings" "Main Treasury" "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"
/remove "Main Treasury"
/check "Main Treasury"
/check "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS"
/check "Treasury" "Operations"
```

## Daily Reports

Automated daily balance reports are sent at **17:00 UTC (00:00 GMT+7)** to the configured daily reports topic.

### Setup Daily Reports
```bash
# Start all services (webhook + daily reports)
./start_lark_bot.sh

# Test immediate report
python lark_bot.py test

# Monitor logs
tail -f logs/daily_reports.log logs/startup.log
```

### Report Format
- Interactive card with company-grouped wallet table
- Individual balance amounts and grand total
- Timestamp and summary statistics
- Consistent formatting with manual `/check` command

## Architecture

### Project Structure
```
lark-crypto-bot/
├── bot/
│   ├── handlers/              # Command handlers (add, check, list, remove, help, start)
│   ├── services/              # Core business logic
│   │   ├── lark_api_client.py     # Lark API communication
│   │   ├── topic_manager.py       # Topic/thread management
│   │   ├── wallet_service.py      # Wallet CRUD operations
│   │   ├── balance_service.py     # Blockchain balance fetching
│   │   ├── message_parser.py      # Message processing and validation
│   │   └── tron_validator.py      # TRON address validation
│   └── utils/
│       ├── config.py              # Configuration management with validation
│       └── handler_registry.py    # Command routing and middleware
├── find_chat_id.py            # Utility to find Lark chat IDs
├── find_ids.py                # Utility to find various Lark IDs
├── find_user_ids.py           # Utility to find user Open IDs
├── lark_bot.py                # Daily report scheduler
├── main.py                    # FastAPI webhook server
├── start_lark_bot.sh          # Service startup script
├── wallets.json              # Wallet configuration storage
├── logs/                     # Production logging with rotation
│   ├── daily_reports.log
│   ├── ngrok.log
│   └── startup.log
└── requirements.txt          # Python dependencies
```

### Key Components

**Webhook Server**: FastAPI-based server handling Lark webhook events with message deduplication and validation

**Handler Registry**: Command routing system with authorization middleware and rich error handling

**Topic Manager**: Manages communication within specific Lark chat topics for organized conversations

**Lark API Client**: Async client with automatic token refresh and comprehensive error handling

**Balance Service**: TRC20 USDT balance fetching with address validation and error recovery

## Security

### Authentication Flow
- Webhook endpoint validation through Lark challenge-response
- Tenant access token management with automatic 2-hour refresh
- Message authenticity verification for all incoming events

### Authorization System
- Lark Open ID-based user authorization
- Configurable authorized user list via environment variables
- Graceful access denial with user ID display for admin reference
- No authentication bypass mechanisms

### Data Security
- Read-only blockchain access (no transaction capabilities)
- Secure credential storage via environment variables
- Production-safe logging with sensitive data filtering
- Automatic wallet configuration backups

## Wallet Configuration

### Supported Format
USDT TRC20 wallets only. Addresses must:
- Start with 'T' character
- Be exactly 34 characters in length
- Pass TRC20 validation checks

### Storage Format
```json
{
  "companies": {
    "Company Name": [
      {
        "name": "Wallet Display Name",
        "address": "TRC20_Address_Here"
      }
    ]
  }
}
```

## Operations

### Service Management
```bash
# Start all services
./start_lark_bot.sh

# Check service status
./start_lark_bot.sh status

# Stop all services
./start_lark_bot.sh stop

# Restart services
./start_lark_bot.sh restart

# View logs
./start_lark_bot.sh logs

# Test webhook endpoint
curl http://localhost:8080/

# Verify configuration
python bot/utils/config.py test
```

### Maintenance Tasks
```bash
# Restart all services
./start_lark_bot.sh restart

# Backup wallet configuration
cp wallets.json wallets.json.backup.$(date +%s)

# Check log file sizes
ls -lah logs/

# Find Lark IDs for setup
python find_chat_id.py      # Get chat ID
python find_user_ids.py     # Get user Open IDs
python find_ids.py          # Get topic/message IDs
```

### Health Monitoring
```bash
# Test bot connectivity
python -c "
import asyncio
from bot.services.lark_api_client import LarkAPIClient
from bot.utils.config import Config

async def test():
    async with LarkAPIClient(Config.LARK_APP_ID, Config.LARK_APP_SECRET) as client:
        return await client.test_connection()

print('Connected:' , asyncio.run(test()))
"
```

## Troubleshooting

### Common Issues

**Webhook not receiving events**
- Verify webhook URL is publicly accessible
- Check Lark app webhook subscription configuration
- Ensure bot is added to the target group chat

**Authorization failures**
- Confirm user Open IDs are correctly formatted (ou_xxxxxxxxxx)
- Verify LARK_AUTHORIZED_USERS environment variable
- Check authorization middleware logs

**Balance fetch errors**
- Validate wallet addresses are proper TRC20 format
- Check TRON_API_KEY configuration and rate limits
- Monitor network connectivity and API response times

**Daily reports not generating**
- Verify lark_bot.py process is running with `./start_lark_bot.sh status`
- Check scheduler logs: `tail -f logs/daily_reports.log`
- Test immediate report: `python lark_bot.py test`
- Confirm topic configuration and message IDs

### Debug Commands
```bash
# Validate all configuration
python bot/utils/config.py test

# Test wallet service
python -c "
from bot.services.wallet_service import WalletService
ws = WalletService()
success, data = ws.list_wallets()
print(f'Wallets loaded: {success}, Count: {len(data.get(\"companies\", {})) if success else 0}')
"

# Test balance service
python -c "
from bot.services.balance_service import BalanceService
bs = BalanceService()
result = bs.fetch_balance('TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS')
print(f'Balance fetch result: {result}')
"
```

## Logging

### Log Files
- `logs/startup.log` - Service startup and general logs
- `logs/daily_reports.log` - Scheduler-specific logs  
- `logs/ngrok.log` - Tunnel service logs (if using ngrok)

### Log Monitoring
```bash
# Follow all logs
tail -f logs/*.log

# Monitor error logs only
tail -f logs/lark_bot_errors.log

# Check log directory size
du -sh logs/
```

## Production Deployment

### Requirements
- Python 3.8+ runtime environment
- Public webhook endpoint with SSL certificate
- Process management (systemd, supervisor, or similar)
- Log rotation and monitoring setup
- Backup strategy for wallet configuration

### Recommended Setup
```bash
# Use process manager for production
# Example systemd service files:

# /etc/systemd/system/lark-bot-webhook.service
[Unit]
Description=Lark Crypto Bot Webhook Server
After=network.target

[Service]
Type=simple
User=larkbot
WorkingDirectory=/opt/lark-crypto-bot
Environment=PATH=/opt/lark-crypto-bot/.venv/bin
ExecStart=/opt/lark-crypto-bot/.venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/lark-bot-scheduler.service
[Unit]
Description=Lark Crypto Bot Daily Reports
After=network.target

[Service]
Type=simple
User=larkbot
WorkingDirectory=/opt/lark-crypto-bot
Environment=PATH=/opt/lark-crypto-bot/.venv/bin
ExecStart=/opt/lark-crypto-bot/.venv/bin/python daily_reports.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Monitoring Setup
- Monitor webhook endpoint availability
- Track daily report delivery success
- Alert on sustained balance fetch failures
- Monitor log file growth and rotation

## Performance Considerations

- Webhook responses typically complete within 3-5 seconds
- Balance fetching supports concurrent requests for multiple wallets
- Daily reports handle unlimited wallet counts with automatic batching
- Memory usage remains stable with built-in garbage collection
- Log rotation prevents disk space exhaustion

---

**Enterprise-grade cryptocurrency wallet monitoring solution with comprehensive Lark integration and production-ready architecture.**