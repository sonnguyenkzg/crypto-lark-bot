#!/bin/bash
#
# Unified Lark Bot Startup Script
# Starts interactive bot, daily reports, Google Sheets sync, and ngrok tunnel together
# FIXED: Forces fresh .env loading on every startup
#

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 ======= LARK CRYPTO BOT STARTUP =======${NC}"
echo "📅 $(date)"
echo "🖥️  Server: $(hostname)"
echo "👤 User: $(whoami)"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "lark_bot.py" ] || [ ! -f "main.py" ] || [ ! -f "wallets_to_gg_sheet.py" ] || [ ! -f "cleanup.py" ]; then
    echo -e "${RED}❌ Error: Must run from crypto-lark-bot directory${NC}"
    echo "📁 Current directory: $(pwd)"
    echo "💡 Expected files: lark_bot.py, main.py, wallets_to_gg_sheet.py, cleanup.py"
    exit 1
fi

# Function to check if process is running
check_process() {
    if pgrep -f "$1" > /dev/null; then
        return 0  # Process running
    else
        return 1  # Process not running
    fi
}

# Function to get ngrok tunnel URL
get_ngrok_url() {
    # Load environment if not already loaded
    if [ -z "$ENVIRONMENT" ]; then
        if [ -f ".env" ]; then
            export $(grep "^ENVIRONMENT=" .env | xargs)
        fi
        ENVIRONMENT=${ENVIRONMENT:-DEV}
    fi

    # Return fixed domain URL
    echo "https://kzg-cryptobalance-${ENVIRONMENT}.ngrok.app"
}

# Stop existing processes
stop_existing() {
    echo -e "${YELLOW}🛑 Stopping existing processes...${NC}"
    
    if check_process "lark_bot.py"; then
        echo "   Stopping lark_bot.py..."
        pkill -f "lark_bot.py"
        sleep 2
    fi
    
    if check_process "python.*main.py"; then
        echo "   Stopping daily reports..."
        pkill -f "python.*main.py"
        sleep 2
    fi
    
    if check_process "python.*wallets_to_gg_sheet.py"; then
        echo "   Stopping Google Sheets sync..."
        pkill -f "python.*wallets_to_gg_sheet.py"
        sleep 2
    fi
    
    if check_process "python.*cleanup.py"; then
        echo "   Stopping log cleanup..."
        pkill -f "python.*cleanup.py"
        sleep 2
    fi
    
    if check_process "ngrok"; then
        echo "   Stopping ngrok..."
        pkill -f "ngrok"
        sleep 2
    fi
    
    echo -e "${GREEN}   ✅ Cleanup completed${NC}"
}

# Clear environment variables to force fresh .env loading
clear_environment() {
    echo -e "${BLUE}🧹 Clearing environment variables for fresh loading...${NC}"
    
    # Clear all LARK-related environment variables
    unset LARK_APP_ID
    unset LARK_APP_SECRET
    unset LARK_CHAT_ID
    unset LARK_TOPIC_QUICKGUIDE
    unset LARK_TOPIC_COMMANDS
    unset LARK_TOPIC_DAILYREPORT
    unset LARK_TOPIC_QUICKGUIDE_MSG
    unset LARK_TOPIC_COMMANDS_MSG
    unset LARK_TOPIC_DAILYREPORT_MSG
    unset LARK_AUTHORIZED_USERS
    unset ENVIRONMENT
    unset POLL_INTERVAL
    unset COMMAND_PREFIX
    unset LOG_LEVEL
    unset WALLETS_FILE
    unset TRON_API_KEY
    unset NGROK_KZG_TOKEN
    
    # Clear Google Sheets related environment variables
    unset GOOGLE_CREDENTIALS_FILE
    unset GOOGLE_SHEET_ID
    unset JSON_FILE_PATH
    
    # Clear log cleanup related environment variables
    unset LOG_RETENTION_DAYS
    unset LOG_DIRECTORY
    
    echo -e "${GREEN}   ✅ Environment variables cleared${NC}"
}

# Activate virtual environment
setup_environment() {
    echo -e "${BLUE}📦 Setting up environment...${NC}"
    
    if [ -d ".venv" ]; then
        echo "   Activating virtual environment..."
        source .venv/bin/activate
        echo -e "${GREEN}   ✅ Virtual environment activated${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Virtual environment not found, using system Python${NC}"
    fi
    
    # Create logs directory
    mkdir -p logs
    echo "   📁 Logs directory created: logs/"
}

# Validate configuration with forced .env reload
validate_config() {
    echo -e "${BLUE}🔍 Validating configuration...${NC}"
    
    # Check .env file
    if [ ! -f ".env" ]; then
        echo -e "${RED}   ❌ .env file not found${NC}"
        exit 1
    fi
    
    # Check wallets.json
    if [ ! -f "wallets.json" ]; then
        echo -e "${RED}   ❌ wallets.json not found${NC}"
        exit 1
    fi
    
    # Check if ngrok is installed
    if ! command -v ngrok &> /dev/null; then
        echo -e "${RED}   ❌ ngrok not found${NC}"
        echo "   💡 Install ngrok: https://ngrok.com/download"
        exit 1
    fi
    
    # Force reload .env and test configuration loading
    if python -c "
import os
from dotenv import load_dotenv

# Clear existing env vars and force reload
for key in list(os.environ.keys()):
    if key.startswith('LARK_') or key in ['ENVIRONMENT', 'POLL_INTERVAL', 'COMMAND_PREFIX', 'LOG_LEVEL', 'WALLETS_FILE', 'TRON_API_KEY', 'GOOGLE_CREDENTIALS_FILE', 'GOOGLE_SHEET_ID', 'JSON_FILE_PATH']:
        del os.environ[key]

# Force load from .env with override
load_dotenv('.env', override=True)

# Test config validation
from bot.utils.config import Config
Config.validate_config()

# Verify LARK_AUTHORIZED_USERS loaded correctly
users = os.getenv('LARK_AUTHORIZED_USERS', '')
user_count = len([u.strip() for u in users.split(',') if u.strip()])
print(f'✅ Loaded {user_count} authorized users')
if user_count > 0:
    print(f'   Users: {users[:60]}...')
else:
    print('   ⚠️  No authorized users found - check LARK_AUTHORIZED_USERS in .env')
" 2>/dev/null; then
        echo -e "${GREEN}   ✅ Configuration valid with fresh .env reload${NC}"
    else
        echo -e "${RED}   ❌ Configuration validation failed${NC}"
        echo "   💡 Check your .env file settings"
        exit 1
    fi
}

# Load environment from .env
load_environment() {
    echo -e "${BLUE}🌍 Loading environment configuration...${NC}"

    if [ -f ".env" ]; then
        export $(grep "^ENVIRONMENT=" .env | xargs)
    fi

    if [ -z "$ENVIRONMENT" ]; then
        echo -e "${YELLOW}   ⚠️  ENVIRONMENT not set in .env, defaulting to DEV${NC}"
        export ENVIRONMENT="DEV"
    else
        echo -e "${GREEN}   ✅ Environment: $ENVIRONMENT${NC}"
    fi
}

# Start ngrok tunnel
start_ngrok() {
    echo -e "${PURPLE}🌐 Starting ngrok tunnel...${NC}"

    # Construct fixed domain based on environment
    local NGROK_DOMAIN="kzg-cryptobalance-${ENVIRONMENT}.ngrok.app"
    local NGROK_PORT=8080

    echo "   🌍 Environment: $ENVIRONMENT"
    echo "   🔗 Domain: $NGROK_DOMAIN"

    # Start ngrok in background with fixed domain
    nohup ngrok http $NGROK_PORT --domain $NGROK_DOMAIN > logs/ngrok.log 2>&1 &
    NGROK_PID=$!

    # Wait for ngrok to start
    echo "   ⏳ Waiting for ngrok to initialize..."
    sleep 3

    if check_process "ngrok"; then
        echo -e "${GREEN}   ✅ ngrok started (PID: $NGROK_PID)${NC}"

        # Construct webhook URL directly (no need to query API)
        WEBHOOK_URL="https://${NGROK_DOMAIN}"

        echo -e "${GREEN}   🔗 Tunnel URL: $WEBHOOK_URL${NC}"
        echo -e "${PURPLE}   📡 Webhook URL: $WEBHOOK_URL/webhook${NC}"

        # Store for later display
        export LARK_WEBHOOK_URL="$WEBHOOK_URL/webhook"
        return 0
    else
        echo -e "${RED}   ❌ Failed to start ngrok${NC}"
        echo "   💡 Check logs: tail -f logs/ngrok.log"
        echo "   💡 Ensure ngrok auth token is configured: ngrok config add-authtoken YOUR_TOKEN"
        return 1
    fi
}

# Start interactive bot with environment isolation
start_interactive_bot() {
    echo -e "${BLUE}🎮 Starting Lark interactive bot...${NC}"
    
    # Start lark_bot.py in background with clean environment
    nohup bash -c "
        cd $(pwd)
        source .venv/bin/activate 2>/dev/null || true
        
        # Clear environment variables in this subprocess
        unset LARK_APP_ID LARK_APP_SECRET LARK_CHAT_ID
        unset LARK_TOPIC_QUICKGUIDE LARK_TOPIC_COMMANDS LARK_TOPIC_DAILYREPORT
        unset LARK_TOPIC_QUICKGUIDE_MSG LARK_TOPIC_COMMANDS_MSG LARK_TOPIC_DAILYREPORT_MSG
        unset LARK_AUTHORIZED_USERS ENVIRONMENT POLL_INTERVAL COMMAND_PREFIX
        unset LOG_LEVEL WALLETS_FILE TRON_API_KEY NGROK_KZG_TOKEN
        unset GOOGLE_CREDENTIALS_FILE GOOGLE_SHEET_ID JSON_FILE_PATH
        unset LOG_RETENTION_DAYS LOG_DIRECTORY
        unset LOG_RETENTION_DAYS LOG_DIRECTORY
        
        python lark_bot.py
    " > logs/startup.log 2>&1 &
    LARK_BOT_PID=$!
    
    # Wait a moment and check if it started successfully
    sleep 3
    
    if check_process "lark_bot.py"; then
        echo -e "${GREEN}   ✅ Lark bot started (PID: $LARK_BOT_PID)${NC}"
        echo "   📄 Logs: logs/lark_bot.log (auto-rotating)"
        echo "   📄 Errors: logs/lark_bot_errors.log"
        echo "   📄 Startup: logs/startup.log"
        return 0
    else
        echo -e "${RED}   ❌ Failed to start Lark bot${NC}"
        echo "   💡 Check logs: tail -f logs/startup.log"
        return 1
    fi
}

# Start daily reports with environment isolation
start_daily_reports() {
    echo -e "${BLUE}📅 Starting daily reports...${NC}"
    
    # Start main.py in background with clean environment
    nohup bash -c "
        cd $(pwd)
        source .venv/bin/activate 2>/dev/null || true
        
        # Clear environment variables in this subprocess
        unset LARK_APP_ID LARK_APP_SECRET LARK_CHAT_ID
        unset LARK_TOPIC_QUICKGUIDE LARK_TOPIC_COMMANDS LARK_TOPIC_DAILYREPORT
        unset LARK_TOPIC_QUICKGUIDE_MSG LARK_TOPIC_COMMANDS_MSG LARK_TOPIC_DAILYREPORT_MSG
        unset LARK_AUTHORIZED_USERS ENVIRONMENT POLL_INTERVAL COMMAND_PREFIX
        unset LOG_LEVEL WALLETS_FILE TRON_API_KEY NGROK_KZG_TOKEN
        unset GOOGLE_CREDENTIALS_FILE GOOGLE_SHEET_ID JSON_FILE_PATH
        
        python main.py
    " > logs/daily_reports.log 2>&1 &
    DAILY_REPORTS_PID=$!
    
    # Wait a moment and check if it started successfully
    sleep 3
    
    if check_process "python.*main.py"; then
        echo -e "${GREEN}   ✅ Daily reports started (PID: $DAILY_REPORTS_PID)${NC}"
        echo "   📄 Logs: logs/daily_reports.log"
        echo "   ⏰ Scheduled: Daily reports at 00:00 GMT+7"
        return 0
    else
        echo -e "${RED}   ❌ Failed to start daily reports${NC}"
        echo "   💡 Check logs: tail -f logs/daily_reports.log"
        return 1
    fi
}

# Start log cleanup scheduler with environment isolation
start_log_cleanup() {
    echo -e "${BLUE}🧹 Starting log cleanup scheduler...${NC}"
    
    # Start cleanup.py in background with clean environment
    nohup bash -c "
        cd $(pwd)
        source .venv/bin/activate 2>/dev/null || true
        
        # Clear environment variables in this subprocess
        unset LARK_APP_ID LARK_APP_SECRET LARK_CHAT_ID
        unset LARK_TOPIC_QUICKGUIDE LARK_TOPIC_COMMANDS LARK_TOPIC_DAILYREPORT
        unset LARK_TOPIC_QUICKGUIDE_MSG LARK_TOPIC_COMMANDS_MSG LARK_TOPIC_DAILYREPORT_MSG
        unset LARK_AUTHORIZED_USERS ENVIRONMENT POLL_INTERVAL COMMAND_PREFIX
        unset LOG_LEVEL WALLETS_FILE TRON_API_KEY NGROK_KZG_TOKEN
        unset GOOGLE_CREDENTIALS_FILE GOOGLE_SHEET_ID JSON_FILE_PATH
        unset LOG_RETENTION_DAYS LOG_DIRECTORY
        
        python cleanup.py
    " > logs/log_cleanup.log 2>&1 &
    LOG_CLEANUP_PID=$!
    
    # Wait a moment and check if it started successfully
    sleep 3
    
    if check_process "python.*cleanup.py"; then
        echo -e "${GREEN}   ✅ Log cleanup started (PID: $LOG_CLEANUP_PID)${NC}"
        echo "   📄 Logs: logs/log_cleanup.log"
        echo "   ⏰ Scheduled: Daily cleanup at 00:30 GMT+7"
        return 0
    else
        echo -e "${RED}   ❌ Failed to start log cleanup${NC}"
        echo "   💡 Check logs: tail -f logs/log_cleanup.log"
        return 1
    fi
}
start_sheets_sync() {
    echo -e "${BLUE}📊 Starting Google Sheets sync...${NC}"
    
    # Start wallets_to_gg_sheet.py in background with clean environment
    nohup bash -c "
        cd $(pwd)
        source .venv/bin/activate 2>/dev/null || true
        
        # Clear environment variables in this subprocess
        unset LARK_APP_ID LARK_APP_SECRET LARK_CHAT_ID
        unset LARK_TOPIC_QUICKGUIDE LARK_TOPIC_COMMANDS LARK_TOPIC_DAILYREPORT
        unset LARK_TOPIC_QUICKGUIDE_MSG LARK_TOPIC_COMMANDS_MSG LARK_TOPIC_DAILYREPORT_MSG
        unset LARK_AUTHORIZED_USERS ENVIRONMENT POLL_INTERVAL COMMAND_PREFIX
        unset LOG_LEVEL WALLETS_FILE TRON_API_KEY NGROK_KZG_TOKEN
        unset GOOGLE_CREDENTIALS_FILE GOOGLE_SHEET_ID JSON_FILE_PATH
        
        python wallets_to_gg_sheet.py
    " > logs/sheets_sync.log 2>&1 &
    SHEETS_SYNC_PID=$!
    
    # Wait a moment and check if it started successfully
    sleep 3
    
    if check_process "python.*wallets_to_gg_sheet.py"; then
        echo -e "${GREEN}   ✅ Google Sheets sync started (PID: $SHEETS_SYNC_PID)${NC}"
        echo "   📄 Logs: logs/sheets_sync.log"
        echo "   ⏰ Scheduled: Daily sync at 00:00 GMT+7"
        return 0
    else
        echo -e "${RED}   ❌ Failed to start Google Sheets sync${NC}"
        echo "   💡 Check logs: tail -f logs/sheets_sync.log"
        return 1
    fi
}

# Show status
show_status() {
    echo ""
    echo -e "${GREEN}🎉 ======= STARTUP COMPLETED =======${NC}"
    echo ""
    echo "📊 Services Status:"
    
    if check_process "ngrok"; then
        echo -e "   ${GREEN}✅ ngrok Tunnel: Running${NC}"
    else
        echo -e "   ${RED}❌ ngrok Tunnel: Not Running${NC}"
    fi
    
    if check_process "lark_bot.py"; then
        echo -e "   ${GREEN}✅ Lark Bot: Running${NC}"
    else
        echo -e "   ${RED}❌ Lark Bot: Not Running${NC}"
    fi
    
    if check_process "python.*main.py"; then
        echo -e "   ${GREEN}✅ Daily Reports: Running${NC}"
    else
        echo -e "   ${RED}❌ Daily Reports: Not Running${NC}"
    fi
    
    if check_process "python.*wallets_to_gg_sheet.py"; then
        echo -e "   ${GREEN}✅ Google Sheets Sync: Running${NC}"
    else
        echo -e "   ${RED}❌ Google Sheets Sync: Not Running${NC}"
    fi
    
    if check_process "python.*cleanup.py"; then
        echo -e "   ${GREEN}✅ Log Cleanup: Running${NC}"
    else
        echo -e "   ${RED}❌ Log Cleanup: Not Running${NC}"
    fi
    
    if [ ! -z "$LARK_WEBHOOK_URL" ]; then
        echo ""
        echo -e "${PURPLE}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐${NC}"
        echo -e "${PURPLE}│                                    🔗 LARK WEBHOOK CONFIGURATION                                    │${NC}"
        echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤${NC}"
        echo -e "${PURPLE}│                                                                                                     │${NC}"
        echo -e "${PURPLE}│  Copy this URL to your Lark Developer Console:                                                     │${NC}"
        echo -e "${PURPLE}│                                                                                                     │${NC}"
        echo -e "${PURPLE}│  ${LARK_WEBHOOK_URL}                                                │${NC}"
        echo -e "${PURPLE}│                                                                                                     │${NC}"
        echo -e "${PURPLE}│  Steps:                                                                                             │${NC}"
        echo -e "${PURPLE}│  1. Go to: https://open.larksuite.com/                                                             │${NC}"
        echo -e "${PURPLE}│  2. Select your app → Features → Bot → Event Configuration                                         │${NC}"
        echo -e "${PURPLE}│  3. Update Request URL with the URL above                                                          │${NC}"
        echo -e "${PURPLE}│  4. Save changes                                                                                   │${NC}"
        echo -e "${PURPLE}│                                                                                                     │${NC}"
        echo -e "${PURPLE}└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘${NC}"
        echo ""
    fi
    
    echo ""
    echo "📋 Management Commands:"
    echo "   View logs:         tail -f logs/lark_bot.log logs/daily_reports.log logs/sheets_sync.log logs/log_cleanup.log"
    echo "   View all logs:     tail -f logs/*.log"
    echo "   Check processes:   ps aux | grep -E 'python|ngrok'"
    echo "   Stop all:          $0 stop"
    echo "   Restart:           $0 restart"
    echo "   Status:            $0 status"
    echo "   Test report:       python main.py test"
    echo "   Test sheets sync:  python wallets_to_gg_sheet.py test"
    echo "   Test log cleanup:  python cleanup.py test"
    echo ""
    echo "🎯 Bot Features Available:"
    echo "   • Interactive commands in Lark topics"
    echo "   • Daily balance reports at midnight GMT+7"
    echo "   • Daily Google Sheets sync at midnight GMT+7"
    echo "   • Daily log cleanup at 00:30 GMT+7"
    echo "   • Real-time wallet monitoring"
    echo "   • Secure ngrok tunnel for webhooks"
    echo "   • Fresh .env loading on every restart"
    echo ""
}

# Test services
test_services() {
    echo -e "${BLUE}🧪 Testing services...${NC}"
    
    # Test imports
    if python -c "import lark_bot" 2>/dev/null; then
        echo -e "${GREEN}   ✅ Lark bot imports successfully${NC}"
    else
        echo -e "${RED}   ❌ Lark bot import failed${NC}"
        return 1
    fi
    
    if python -c "import main" 2>/dev/null; then
        echo -e "${GREEN}   ✅ Daily reports imports successfully${NC}"
    else
        echo -e "${RED}   ❌ Daily reports import failed${NC}"
        return 1
    fi
    
    if python -c "import wallets_to_gg_sheet" 2>/dev/null; then
        echo -e "${GREEN}   ✅ Google Sheets sync imports successfully${NC}"
    else
        echo -e "${RED}   ❌ Google Sheets sync import failed${NC}"
        return 1
    fi
    
    if python -c "import cleanup" 2>/dev/null; then
        echo -e "${GREEN}   ✅ Log cleanup imports successfully${NC}"
    else
        echo -e "${RED}   ❌ Log cleanup import failed${NC}"
        return 1
    fi
    
    echo -e "${GREEN}   ✅ All service tests passed${NC}"
    return 0
}

# Test ngrok connectivity
test_ngrok() {
    echo -e "${BLUE}🔌 Testing ngrok connectivity...${NC}"
    
    if [ ! -z "$LARK_WEBHOOK_URL" ]; then
        echo "   Testing webhook endpoint..."
        
        # Test the webhook endpoint
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$LARK_WEBHOOK_URL" || echo "000")
        
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "405" ]; then
            echo -e "${GREEN}   ✅ Webhook endpoint is reachable${NC}"
        else
            echo -e "${YELLOW}   ⚠️  Webhook endpoint returned HTTP $HTTP_CODE${NC}"
            echo "   💡 This is normal if the bot isn't fully started yet"
        fi
    else
        echo -e "${RED}   ❌ No webhook URL available${NC}"
        return 1
    fi
}

# Main execution
main() {
    # Pre-startup checks with forced environment reload
    stop_existing
    clear_environment
    setup_environment
    load_environment
    validate_config
    test_services
    
    echo ""
    echo -e "${BLUE}🚀 Starting services...${NC}"
    echo ""
    
    # Start services in order
    if start_ngrok; then
        echo ""
        if start_interactive_bot && start_daily_reports && start_sheets_sync && start_log_cleanup; then
            echo ""
            test_ngrok
            show_status
            
            echo -e "${GREEN}✨ All services started successfully!${NC}"
            echo ""
            echo "💡 Next steps:"
            echo "   1. Copy the webhook URL above to Lark Developer Console"
            echo "   2. Test bot in Lark: /start"
            echo "   3. Test daily report: python main.py test"
            echo "   4. Test sheets sync: python wallets_to_gg_sheet.py test"
            echo "   5. Test log cleanup: python cleanup.py test"
            echo "   6. Monitor logs for any issues"
            echo ""
            echo "🔄 Environment reload: Fresh .env loading guaranteed on every start!"
            echo ""
            
            return 0
        else
            echo -e "${RED}❌ Bot service startup failed!${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ ngrok startup failed!${NC}"
        return 1
    fi
}

# Show webhook URL only
show_webhook_url() {
    if check_process "ngrok"; then
        WEBHOOK_URL=$(get_ngrok_url)
        if [ ! -z "$WEBHOOK_URL" ]; then
            echo -e "${PURPLE}🔗 Current webhook URL: $WEBHOOK_URL/webhook${NC}"
        else
            echo -e "${RED}❌ Could not retrieve webhook URL${NC}"
        fi
    else
        echo -e "${RED}❌ ngrok is not running${NC}"
    fi
}

# Handle command line arguments
case "$1" in
    "stop")
        echo -e "${YELLOW}🛑 Stopping all Lark bot services...${NC}"
        stop_existing
        echo -e "${GREEN}✅ All services stopped${NC}"
        ;;
    "status")
        echo -e "${BLUE}📊 Service Status:${NC}"
        if check_process "ngrok"; then
            echo -e "   ${GREEN}✅ ngrok Tunnel: Running${NC}"
        else
            echo -e "   ${RED}❌ ngrok Tunnel: Not Running${NC}"
        fi
        if check_process "lark_bot.py"; then
            echo -e "   ${GREEN}✅ Lark Bot: Running${NC}"
        else
            echo -e "   ${RED}❌ Lark Bot: Not Running${NC}"
        fi
        if check_process "python.*main.py"; then
            echo -e "   ${GREEN}✅ Daily Reports: Running${NC}"
        else
            echo -e "   ${RED}❌ Daily Reports: Not Running${NC}"
        fi
        if check_process "python.*wallets_to_gg_sheet.py"; then
            echo -e "   ${GREEN}✅ Google Sheets Sync: Running${NC}"
        else
            echo -e "   ${RED}❌ Google Sheets Sync: Not Running${NC}"
        fi
        if check_process "python.*cleanup.py"; then
            echo -e "   ${GREEN}✅ Log Cleanup: Running${NC}"
        else
            echo -e "   ${RED}❌ Log Cleanup: Not Running${NC}"
        fi
        echo ""
        show_webhook_url
        ;;
    "restart")
        echo -e "${YELLOW}🔄 Restarting all services...${NC}"
        stop_existing
        sleep 2
        main
        ;;
    "logs")
        echo -e "${BLUE}📄 Showing recent logs...${NC}"
        echo ""
        echo "=== Lark Bot Logs ==="
        tail -20 logs/lark_bot.log 2>/dev/null || echo "No lark_bot.log found"
        echo ""
        echo "=== Daily Reports Logs ==="
        tail -20 logs/daily_reports.log 2>/dev/null || echo "No daily_reports.log found"
        echo ""
        echo "=== Google Sheets Sync Logs ==="
        tail -20 logs/sheets_sync.log 2>/dev/null || echo "No sheets_sync.log found"
        echo ""
        echo "=== Log Cleanup Logs ==="
        tail -20 logs/log_cleanup.log 2>/dev/null || echo "No log_cleanup.log found"
        echo ""
        echo "=== ngrok Logs ==="
        tail -20 logs/ngrok.log 2>/dev/null || echo "No ngrok.log found"
        echo ""
        echo "=== Startup Logs ==="
        tail -20 logs/startup.log 2>/dev/null || echo "No startup.log found"
        ;;
    "webhook")
        show_webhook_url
        ;;
    "url")
        show_webhook_url
        ;;
    "help"|"-h"|"--help")
        echo "Lark Crypto Bot Startup Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "   (no args)    Start all services (ngrok, bot, daily reports, sheets sync, log cleanup)"
        echo "   stop         Stop all services"
        echo "   restart      Restart all services"  
        echo "   status       Show service status"
        echo "   logs         Show recent logs"
        echo "   webhook      Show current webhook URL"
        echo "   url          Show current webhook URL"
        echo "   help         Show this help"
        echo ""
        echo "Features:"
        echo "   • Starts ngrok tunnel automatically"
        echo "   • Displays webhook URL for Lark console"
        echo "   • Auto-rotating logs (prevents disk space issues)"
        echo "   • Process monitoring and management"
        echo "   • Comprehensive error handling"
        echo "   • Forces fresh .env loading on every restart"
        echo "   • Daily Google Sheets wallet sync"
        echo "   • Automatic log cleanup (keeps 7 days)"
        echo ""
        ;;
    "")
        # No arguments - start services
        main
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac