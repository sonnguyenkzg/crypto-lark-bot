#!/usr/bin/env python3
"""
Daily Log Cleanup Scheduler
Cleans up old log files automatically every day
Runs 30 minutes after midnight GMT+7 (17:30 UTC) to avoid conflicts with other jobs

Simple and clean - keeps only recent logs to prevent disk space issues
"""

import os
import glob
import time
import logging
import schedule
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LogCleanupScheduler:
    """Scheduler for daily log cleanup."""
    
    def __init__(self, log_dir="logs", days_to_keep=7):
        self.log_dir = log_dir
        self.days_to_keep = days_to_keep
        
    def cleanup_old_logs(self):
        """Clean up log files older than specified days."""
        try:
            if not os.path.exists(self.log_dir):
                logger.info(f"Log directory {self.log_dir} does not exist, nothing to clean")
                return
            
            cutoff_date = datetime.now() - timedelta(days=self.days_to_keep)
            cutoff_timestamp = cutoff_date.timestamp()
            
            # Find all log files (including rotated ones like .log.1, .log.2, etc.)
            log_patterns = [
                f"{self.log_dir}/*.log",
                f"{self.log_dir}/*.log.*",
                f"{self.log_dir}/*.out",
                f"{self.log_dir}/*.err"
            ]
            
            cleaned_files = []
            total_size_cleaned = 0
            
            for pattern in log_patterns:
                for log_file in glob.glob(pattern):
                    try:
                        file_mtime = os.path.getmtime(log_file)
                        if file_mtime < cutoff_timestamp:
                            file_size = os.path.getsize(log_file)
                            os.remove(log_file)
                            cleaned_files.append(log_file)
                            total_size_cleaned += file_size
                            logger.info(f"Cleaned up old log: {log_file}")
                    except OSError as e:
                        logger.warning(f"Could not remove {log_file}: {e}")
            
            if cleaned_files:
                size_mb = total_size_cleaned / (1024 * 1024)
                logger.info(f"✅ Cleanup completed: {len(cleaned_files)} files removed, {size_mb:.2f} MB freed")
            else:
                logger.info("✅ Cleanup completed: No old log files found to remove")
                
        except Exception as e:
            logger.error(f"❌ Error during log cleanup: {e}")
    
    def run_scheduled_cleanup(self):
        """Wrapper to run cleanup in separate thread."""
        def thread_target():
            try:
                logger.info("📞 SCHEDULED LOG CLEANUP TRIGGERED!")
                logger.info(f"🕐 Cleanup time: {datetime.now()}")
                logger.info(f"🗂️  Cleaning logs older than {self.days_to_keep} days from {self.log_dir}/")
                
                self.cleanup_old_logs()
                logger.info("✅ Scheduled log cleanup completed")
                    
            except Exception as e:
                logger.error(f"❌ Error in scheduled cleanup thread: {e}")
        
        # Run in separate thread to avoid blocking
        thread = threading.Thread(target=thread_target)
        thread.start()
        thread.join()  # Wait for completion

def main():
    """Main function to run the daily log cleanup scheduler."""
    try:
        # Configuration - you can adjust these values
        DAYS_TO_KEEP = int(os.getenv('LOG_RETENTION_DAYS', '7'))  # Keep 7 days by default
        LOG_DIR = os.getenv('LOG_DIRECTORY', 'logs')
        
        # Create scheduler instance
        scheduler = LogCleanupScheduler(log_dir=LOG_DIR, days_to_keep=DAYS_TO_KEEP)
        
        # Schedule daily cleanup at 17:30 UTC (00:30 GMT+7) - 30 minutes after other jobs
        schedule.every().day.at("17:30").do(scheduler.run_scheduled_cleanup)
        
        # Get current time info
        utc_now = datetime.now()
        
        logger.info("=== Log Cleanup Scheduler Started ===")
        logger.info(f"Log directory: {LOG_DIR}")
        logger.info(f"Retention period: {DAYS_TO_KEEP} days")
        logger.info(f"Current UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("📅 Scheduled: Daily cleanup at 17:30 UTC (00:30 GMT+7)")
        logger.info("⚠️  Scheduler started - NO immediate cleanup will occur")
        
        # Show next scheduled run
        jobs = schedule.get_jobs()
        if jobs:
            next_run = jobs[0].next_run
            logger.info(f"⏰ Next cleanup: {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        logger.info("Press Ctrl+C to stop")
        logger.info("=====================================")
        
        # Run scheduler
        loop_count = 0
        while True:
            loop_count += 1
            
            # Log every 60 loops (60 minutes) to show it's alive
            if loop_count % 60 == 0:
                current_time = datetime.now()
                logger.info(f"🔄 Log cleanup scheduler alive - Loop #{loop_count}, Time: {current_time}")
                
                # Show next scheduled time
                jobs = schedule.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run
                    logger.info(f"⏰ Next scheduled cleanup: {next_run}")
            
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Log cleanup scheduler stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in log cleanup scheduler: {e}")
        raise

def test_cleanup():
    """Test function to run cleanup immediately (for testing)."""
    logger.info("🧪 Testing log cleanup...")
    
    DAYS_TO_KEEP = int(os.getenv('LOG_RETENTION_DAYS', '7'))
    LOG_DIR = os.getenv('LOG_DIRECTORY', 'logs')
    
    logger.info(f"🔧 Test configuration:")
    logger.info(f"   Log directory: {LOG_DIR}")
    logger.info(f"   Retention: {DAYS_TO_KEEP} days")
    
    try:
        cleanup_scheduler = LogCleanupScheduler(log_dir=LOG_DIR, days_to_keep=DAYS_TO_KEEP)
        cleanup_scheduler.cleanup_old_logs()
        logger.info("✅ Test cleanup completed successfully!")
        
    except Exception as error:
        logger.error(f"❌ Test failed: {error}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: run cleanup immediately for testing
        test_cleanup()
    else:
        # Normal mode: run continuous scheduler
        main()