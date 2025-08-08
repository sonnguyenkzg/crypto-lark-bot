import json
import os
import time
import logging
import schedule
import threading
from datetime import datetime
import pytz
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleSheetsSync:
    def __init__(self, credentials_file, spreadsheet_id, sheet_name):
        """
        Initialize the Google Sheets sync client
        
        Args:
            credentials_file (str): Path to service account JSON file
            spreadsheet_id (str): Google Sheet ID from URL
            sheet_name (str): Name of the sheet tab
        """
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        
        # Set up credentials and build service
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        self.creds = Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES)
        self.service = build('sheets', 'v4', credentials=self.creds)
        self.sheet = self.service.spreadsheets()
    
    def clear_sheet(self):
        """Clear all data from the specified sheet"""
        try:
            range_name = f"{self.sheet_name}!A:Z"  # Adjust range as needed
            self.sheet.values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            logger.info(f"Cleared data from {self.sheet_name}")
        except HttpError as error:
            logger.error(f"An error occurred while clearing: {error}")
    
    def json_to_rows(self, json_data):
        """
        Convert JSON data to rows for Google Sheets
        
        Args:
            json_data (dict): The wallet data JSON
            
        Returns:
            list: List of rows with headers
        """
        # Get current time in GMT+7 (Asia/Bangkok timezone) but format without timezone suffix
        gmt7_tz = pytz.timezone('Asia/Bangkok')
        current_time = datetime.now(gmt7_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        # Create headers
        headers = ['Wallet Name', 'Company', 'Address', 'Created At', 'Refreshed Time']
        rows = [headers]
        
        # Convert each wallet entry to a row
        for wallet_name, wallet_data in json_data.items():
            row = [
                wallet_data.get('wallet', wallet_data.get('name', wallet_name)),
                wallet_data.get('company', ''),
                wallet_data.get('address', ''),
                wallet_data.get('created_at', ''),
                current_time  # Add refreshed time to each row (same format as created_at)
            ]
            rows.append(row)
        
        return rows
    
    def upload_data(self, data_rows):
        """
        Upload data rows to Google Sheets
        
        Args:
            data_rows (list): List of rows to upload
        """
        try:
            range_name = f"{self.sheet_name}!A1"
            body = {
                'values': data_rows
            }
            
            result = self.sheet.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Updated {result.get('updatedCells')} cells in {self.sheet_name}")
            return result
            
        except HttpError as error:
            logger.error(f"An error occurred while uploading: {error}")
    
    def sync_json_data(self, json_file_path):
        """
        Complete sync process: clear sheet and upload new data
        
        Args:
            json_file_path (str): Path to JSON file containing wallet data
        """
        try:
            # Load JSON data
            with open(json_file_path, 'r') as file:
                json_data = json.load(file)
            
            logger.info(f"Loaded {len(json_data)} wallet entries from {json_file_path}")
            
            # Clear existing data
            self.clear_sheet()
            
            # Convert to rows
            data_rows = self.json_to_rows(json_data)
            
            # Upload new data
            self.upload_data(data_rows)
            
            logger.info("✅ Sync completed successfully!")
            
        except FileNotFoundError:
            logger.error(f"❌ JSON file not found: {json_file_path}")
        except json.JSONDecodeError:
            logger.error(f"❌ Invalid JSON format in: {json_file_path}")
        except Exception as error:
            logger.error(f"❌ Unexpected error: {error}")

def validate_environment():
    """Validate required environment variables and files exist"""
    CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE')
    SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID') 
    JSON_FILE_PATH = os.getenv('JSON_FILE_PATH')
    
    # Validate required environment variables
    if not CREDENTIALS_FILE:
        logger.error("❌ Error: GOOGLE_CREDENTIALS_FILE environment variable not set")
        logger.error("Please add GOOGLE_CREDENTIALS_FILE=path/to/your/file.json to your .env file")
        return None, None, None
    
    if not SPREADSHEET_ID:
        logger.error("❌ Error: GOOGLE_SHEET_ID environment variable not set") 
        logger.error("Please add GOOGLE_SHEET_ID=your-sheet-id to your .env file")
        return None, None, None
        
    if not JSON_FILE_PATH:
        logger.error("❌ Error: JSON_FILE_PATH environment variable not set")
        logger.error("Please add JSON_FILE_PATH=path/to/your/json/file to your .env file")
        return None, None, None
        
    if not os.path.exists(CREDENTIALS_FILE):
        logger.error(f"❌ Error: Credentials file not found at: {CREDENTIALS_FILE}")
        logger.error("Please check the path in your .env file")
        return None, None, None
        
    if not os.path.exists(JSON_FILE_PATH):
        logger.error(f"❌ Error: JSON file not found at: {JSON_FILE_PATH}")
        logger.error("Please check the path in your .env file")
        return None, None, None
    
    return CREDENTIALS_FILE, SPREADSHEET_ID, JSON_FILE_PATH

class GoogleSheetsSyncScheduler:
    """Scheduler for daily Google Sheets sync."""
    
    def __init__(self):
        self.credentials_file = None
        self.spreadsheet_id = None
        self.json_file_path = None
        self.sheet_name = "WALLET_LIST"
        self.sync_client = None
        
    def initialize(self):
        """Initialize the sync client with environment variables."""
        self.credentials_file, self.spreadsheet_id, self.json_file_path = validate_environment()
        
        if not all([self.credentials_file, self.spreadsheet_id, self.json_file_path]):
            return False
            
        # Don't create the sync client immediately - only validate the config
        logger.info("✅ Google Sheets sync configuration validated successfully")
        logger.info(f"   Credentials: {self.credentials_file}")
        logger.info(f"   Sheet ID: {self.spreadsheet_id}")
        logger.info(f"   JSON file: {self.json_file_path}")
        return True
    
    def run_scheduled_sync(self):
        """Wrapper to run sync in separate thread."""
        def thread_target():
            try:
                logger.info("📞 SCHEDULED GOOGLE SHEETS SYNC TRIGGERED!")
                logger.info(f"🕐 Sync time: {datetime.now()}")
                
                # Create sync client only when actually running the sync
                sync_client = GoogleSheetsSync(
                    self.credentials_file, 
                    self.spreadsheet_id, 
                    self.sheet_name
                )
                
                sync_client.sync_json_data(self.json_file_path)
                logger.info("✅ Scheduled Google Sheets sync completed")
                    
            except Exception as e:
                logger.error(f"❌ Error in scheduled sync thread: {e}")
        
        # Run in separate thread to avoid blocking
        thread = threading.Thread(target=thread_target)
        thread.start()
        thread.join()  # Wait for completion

def main():
    """Main function to run the daily Google Sheets sync scheduler."""
    try:
        # Create scheduler instance
        scheduler = GoogleSheetsSyncScheduler()
        
        # Initialize
        if not scheduler.initialize():
            logger.error("Failed to initialize Google Sheets sync, exiting")
            return
        
        # Schedule daily sync at 17:00 UTC (midnight GMT+7) - same as daily reports
        schedule.every().day.at("17:00").do(scheduler.run_scheduled_sync)
        
        # Get current time info
        utc_now = datetime.now()
        gmt7_tz = pytz.timezone('Asia/Bangkok')
        gmt7_now = datetime.now(gmt7_tz)
        
        logger.info("=== Google Sheets Sync Scheduler Started ===")
        logger.info(f"Credentials: {scheduler.credentials_file}")
        logger.info(f"Sheet ID: {scheduler.spreadsheet_id}")
        logger.info(f"JSON file: {scheduler.json_file_path}")
        logger.info(f"Current UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Current GMT+7 time: {gmt7_now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("📅 Scheduled: Daily sync at 17:00 UTC (00:00 GMT+7)")
        logger.info("⚠️  Scheduler started - NO immediate sync will occur")
        
        # Show next scheduled run
        jobs = schedule.get_jobs()
        if jobs:
            next_run = jobs[0].next_run
            next_run_gmt7 = next_run.replace(tzinfo=pytz.UTC).astimezone(gmt7_tz)
            logger.info(f"⏰ Next sync: {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")
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
                logger.info(f"🔄 Sheets sync scheduler alive - Loop #{loop_count}, Time: {current_time}")
                
                # Show next scheduled time
                jobs = schedule.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run
                    logger.info(f"⏰ Next scheduled sync: {next_run}")
            
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Google Sheets sync scheduler stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in Google Sheets sync scheduler: {e}")
        raise

def test_sync():
    """Test function to run sync immediately (for testing)."""
    logger.info("🧪 Testing Google Sheets sync...")
    
    # Configuration from .env file
    CREDENTIALS_FILE, SPREADSHEET_ID, JSON_FILE_PATH = validate_environment()
    
    if not all([CREDENTIALS_FILE, SPREADSHEET_ID, JSON_FILE_PATH]):
        logger.error("❌ Test failed: Environment validation failed")
        return
    
    SHEET_NAME = "WALLET_LIST"  # Hardcoded as requested
    
    logger.info(f"🔧 Test configuration:")
    logger.info(f"   Credentials: {CREDENTIALS_FILE}")
    logger.info(f"   Sheet ID: {SPREADSHEET_ID}")
    logger.info(f"   Sheet name: {SHEET_NAME}")
    logger.info(f"   JSON file: {JSON_FILE_PATH}")
    
    try:
        # Create sync client and run test
        sync_client = GoogleSheetsSync(CREDENTIALS_FILE, SPREADSHEET_ID, SHEET_NAME)
        sync_client.sync_json_data(JSON_FILE_PATH)
        logger.info("✅ Test sync completed successfully!")
        
    except Exception as error:
        logger.error(f"❌ Test failed: {error}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: run sync immediately for testing
        test_sync()
    else:
        # Normal mode: run continuous scheduler
        main()