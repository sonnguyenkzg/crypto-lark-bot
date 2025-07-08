#!/usr/bin/env python3
"""
Daily Balance Report Scheduler for Lark Bot
Sends automated daily reports at 12:00 AM GMT+7 (midnight)
Uses the same beautiful table format as /check command

PRODUCTION VERSION: Fixed threading and clean formatting with Lark cards
"""

import asyncio
import logging
import schedule
import time
import threading
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict

from bot.utils.config import Config
from bot.services.lark_api_client import LarkAPIClient
from bot.services.topic_manager import LarkTopicManager, TopicType
from bot.services.wallet_service import WalletService
from bot.services.balance_service import BalanceService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LarkDailyReportScheduler:
    """Scheduler for daily balance reports in Lark."""
    
    def __init__(self):
        self.config = Config
        self.api_client = None
        self.topic_manager = None
        self.wallet_service = WalletService()
        self.balance_service = BalanceService()
        
    async def initialize_lark(self):
        """Initialize Lark API client and topic manager."""
        try:
            self.api_client = LarkAPIClient(self.config.LARK_APP_ID, self.config.LARK_APP_SECRET)
            self.topic_manager = LarkTopicManager(self.api_client, self.config)
            
            # Test connection
            async with self.api_client:
                logger.info("✅ Lark API client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Lark client: {e}")
            return False
    
    def create_daily_report_card(self, balances: Dict[str, Decimal], time_str: str) -> dict:
        """
        Create daily report card using the same beautiful format as CheckHandler.
        Reuses the exact same styling and layout.
        """
        # Calculate totals
        total_wallets = len(balances)
        successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
        grand_total = sum(successful_balances.values())
        
        # Sort wallets by group then by name (same logic as CheckHandler)
        wallet_list = []
        for wallet_name, balance in successful_balances.items():
            group = self.balance_service.extract_wallet_group(wallet_name)
            wallet_list.append((group, wallet_name, balance))
        
        wallet_list.sort(key=lambda x: (x[0], x[1]))
        
        # Build elements with structured table layout (same as CheckHandler)
        elements = [
            # Header info - Modified for daily report
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "💰 **Daily Balance Report**"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"⏰ **Time:** {time_str} GMT+7"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"📊 **Total wallets checked:** {total_wallets}"
                }
            },
            
            # Separator
            {
                "tag": "hr"
            },
            
            # Table header using column layout (exact same as CheckHandler)
            {
                "tag": "column_set",
                "flex_mode": "none",
                "background_style": "grey",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**Group**"
                                }
                            }
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted", 
                        "weight": 2,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**Wallet Name**"
                                }
                            }
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**Amount (USDT)**"
                                }
                            }
                        ]
                    }
                ]
            }
        ]
        
        # Add data rows using column layout (exact same as CheckHandler)
        for group, wallet_name, balance in wallet_list:
            balance_str = f"{balance:,.2f}"
            
            row_element = {
                "tag": "column_set",
                "flex_mode": "none",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "plain_text",
                                    "content": group
                                }
                            }
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 2,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "plain_text",
                                    "content": wallet_name
                                }
                            }
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "plain_text",
                                    "content": balance_str
                                }
                            }
                        ]
                    }
                ]
            }
            elements.append(row_element)
        
        # Add separator and total row (exact same as CheckHandler)
        elements.append({
            "tag": "hr"
        })
        
        # Total row with bold text, no background (exact same as CheckHandler)
        total_row = {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "vertical_align": "center",
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": "**TOTAL**"
                            }
                        }
                    ]
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 2,
                    "vertical_align": "center",
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "plain_text",
                                "content": ""
                            }
                        }
                    ]
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "vertical_align": "center",
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{grand_total:,.2f}**"
                            }
                        }
                    ]
                }
            ]
        }
        elements.append(total_row)

        # Return card with green header for daily report
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "green",  # Green for daily report vs blue for manual check
                "title": {
                    "tag": "plain_text",
                    "content": "💰 Daily Balance Report"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": f"Total: {grand_total:,.2f} USDT"
                }
            },
            "elements": elements
        }
    
    async def send_daily_report(self):
        """Generate and send daily balance report to Lark."""
        try:
            logger.info("🚀 STARTING SCHEDULED DAILY REPORT")
            logger.info(f"🕐 Report time: {datetime.now()}")
            
            # Create fresh API client for this thread
            fresh_api_client = LarkAPIClient(self.config.LARK_APP_ID, self.config.LARK_APP_SECRET)
            fresh_topic_manager = LarkTopicManager(fresh_api_client, self.config)
            
            # Load wallets and fetch balances (same logic as CheckHandler)
            success, wallet_list_data = self.wallet_service.list_wallets()
            if not success or not wallet_list_data.get('companies'):
                logger.warning("No wallets configured for daily report")
                return
            
            # Convert wallet list data to flat dictionary (same as CheckHandler)
            wallet_data = {}
            for company_wallets in wallet_list_data['companies'].values():
                for wallet in company_wallets:
                    wallet_key = f"{wallet['name']}"
                    wallet_data[wallet_key] = {
                        'name': wallet['name'],
                        'address': wallet['address'],
                        'company': wallet.get('company', 'Unknown')
                    }
            
            # Prepare wallets for balance checking
            wallets_to_check = {info['name']: info['address'] for info in wallet_data.values()}
            
            # Fetch all balances (same as CheckHandler but synchronous for scheduler)
            balances = self.balance_service.fetch_multiple_balances(wallets_to_check)
            
            # Filter successful balances
            successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
            
            if not successful_balances:
                logger.warning("No successful balance fetches for daily report")
                return
            
            # Get current GMT+7 time for display
            gmt7_time = datetime.now(timezone(timedelta(hours=7)))
            time_str = gmt7_time.strftime('%Y-%m-%d %H:%M')
            
            # Create daily report card using the same format as CheckHandler
            report_card = self.create_daily_report_card(successful_balances, time_str)
            
            # Send report to daily reports topic
            async with fresh_api_client:
                await fresh_topic_manager.send_to_daily_reports(report_card, msg_type="interactive")
                
            logger.info(f"✅ Daily report sent successfully to Lark daily reports topic")
            logger.info(f"📊 Report summary: {len(successful_balances)} wallets, {sum(successful_balances.values()):,.2f} USDT total")
                
        except Exception as e:
            logger.error(f"❌ Unexpected error in daily report: {e}")
    
    def run_scheduled_report(self):
        """Wrapper to run async report in separate thread."""
        def thread_target():
            try:
                logger.info("📞 SCHEDULED REPORT TRIGGERED!")
                
                # Create completely new event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(self.send_daily_report())
                    logger.info("✅ Scheduled report completed")
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.error(f"❌ Error in scheduled report thread: {e}")
        
        # Run in separate thread to avoid event loop conflicts
        thread = threading.Thread(target=thread_target)
        thread.start()
        thread.join()  # Wait for completion

def main():
    """Main function to run the daily report scheduler."""
    try:
        # Validate configuration
        Config.validate_config()
        logger.info("Configuration validated successfully")
        
        # Create scheduler instance
        scheduler = LarkDailyReportScheduler()
        
        # Initialize Lark
        async def init_lark():
            return await scheduler.initialize_lark()
        
        if not asyncio.run(init_lark()):
            logger.error("Failed to initialize Lark client, exiting")
            return
        
        # Schedule daily report at 17:00 UTC (midnight GMT+7)
        schedule.every().day.at("17:00").do(scheduler.run_scheduled_report)
        
        # Get current time info
        utc_now = datetime.now(timezone.utc)
        gmt7_now = datetime.now(timezone(timedelta(hours=7)))
        
        logger.info("=== Lark Daily Report Scheduler Started ===")
        logger.info(f"Environment: {Config.ENVIRONMENT}")
        logger.info(f"Lark App ID: {Config.LARK_APP_ID}")
        logger.info(f"Current UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Current GMT+7 time: {gmt7_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("📅 Scheduled: Daily reports at 17:00 UTC (00:00 GMT+7)")
        
        # Show next scheduled run
        jobs = schedule.get_jobs()
        if jobs:
            next_run = jobs[0].next_run
            next_run_gmt7 = next_run.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
            logger.info(f"⏰ Next report: {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            logger.info(f"   (Which is: {next_run_gmt7.strftime('%Y-%m-%d %H:%M:%S')} GMT+7)")
        
        logger.info("Press Ctrl+C to stop")
        logger.info("=====================================")
        
        # Run scheduler
        loop_count = 0
        while True:
            loop_count += 1
            
            # Log every 60 loops (60 minutes) to show it's alive
            if loop_count % 60 == 0:
                current_time = datetime.now()
                logger.info(f"🔄 Scheduler alive - Loop #{loop_count}, Time: {current_time}")
                
                # Show next scheduled time
                jobs = schedule.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run
                    logger.info(f"⏰ Next scheduled run: {next_run}")
            
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Lark daily report scheduler stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in daily report scheduler: {e}")
        raise

def test_report():
    """Test function to send a report immediately (for testing)."""
    async def run_test():
        scheduler = LarkDailyReportScheduler()
        if await scheduler.initialize_lark():
            logger.info("Sending test report...")
            await scheduler.send_daily_report()
        else:
            logger.error("Failed to initialize Lark client for test")
    
    asyncio.run(run_test())

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: send report immediately
        print("🧪 Testing daily report...")
        test_report()
    else:
        # Normal mode: run scheduler
        main()