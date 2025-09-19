import logging

logger = logging.getLogger(__name__)
import os
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleSheetsBalanceLogger:
    """Logger for balance check results to Google Sheets"""
    
    def __init__(self):
        self.credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE')
        self.spreadsheet_id = os.getenv('GOOGLE_SHEET_ID')
        self.service = None
        self.sheet = None
        
    def _initialize_service(self):
        """Initialize Google Sheets service if not already done"""
        if self.service is None:
            try:
                SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
                creds = Credentials.from_service_account_file(
                    self.credentials_file, scopes=SCOPES)
                self.service = build('sheets', 'v4', credentials=creds)
                self.sheet = self.service.spreadsheets()
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Google Sheets service: {e}")
                return False
        return True
    
    def _generate_batch_id(self):
        """Generate batch ID in YYYYMMDDHHMMSS format"""
        gmt7_time = datetime.now(timezone(timedelta(hours=7)))
        return gmt7_time.strftime('%Y%m%d%H%M%S')
    
    def _prepare_balance_rows(self, balances, wallets_to_check, batch_id, check_type):
        """
        Prepare balance data rows for Google Sheets
        
        Args:
            balances: Dict of wallet balances
            wallets_to_check: Dict of wallet info
            batch_id: Batch ID string
            check_type: "manual" or "scheduled"
        """
        gmt7_time = datetime.now(timezone(timedelta(hours=7)))
        timestamp = gmt7_time.strftime('%Y-%m-%d %H:%M:%S')
        
        rows = []
        successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
        
        for wallet_name, balance in successful_balances.items():
            wallet_info = wallets_to_check.get(wallet_name, {})
            company = wallet_info.get('company', 'Unknown')
            address = wallet_info.get('address', '')
            
            row = [
                batch_id,
                timestamp,
                wallet_name,
                company,
                address,
                f"{balance:.2f}",  # Format to 2 decimal places
                check_type
            ]
            rows.append(row)
            
        return rows
    
    def log_balance_check(self, balances, wallets_to_check, check_type="manual"):
        """
        Log balance check results to Google Sheets
        
        Args:
            balances: Dict of wallet balances from balance service
            wallets_to_check: Dict of wallet info
            check_type: "manual" for /check command, "scheduled" for daily reports
            
        Returns:
            bool: Success status
        """
        if not self.credentials_file or not self.spreadsheet_id:
            logger.warning("Google Sheets credentials not configured, skipping logging")
            return False
            
        try:
            if not self._initialize_service():
                return False
                
            # Generate batch ID
            batch_id = self._generate_batch_id()
            
            # Prepare data rows
            data_rows = self._prepare_balance_rows(balances, wallets_to_check, batch_id, check_type)
            
            if not data_rows:
                logger.warning("No successful balance data to log")
                return False
            
            # Determine sheet name based on check type
            sheet_name = "CHECK" if check_type == "manual" else "DAILY_REPORT"
            
            # Check if headers exist, if not add them
            self._ensure_headers(sheet_name)
            
            # Append data to sheet
            range_name = f"{sheet_name}!A:G"
            body = {
                'values': data_rows,
                'majorDimension': 'ROWS'
            }
            
            result = self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            updated_cells = result.get('updates', {}).get('updatedCells', 0)
            logger.info(f"✅ Logged {len(data_rows)} balance records to {sheet_name} sheet ({updated_cells} cells)")
            logger.info(f"📝 Batch ID: {batch_id}")
            return True, batch_id
            
        except HttpError as error:
            logger.error(f"Google Sheets API error: {error}")
            return False, None
        except Exception as e:
            logger.error(f"Failed to log balance check to Google Sheets: {e}")
            return False, None
    
    def _ensure_headers(self, sheet_name):
        """Ensure the sheet has proper headers"""
        try:
            headers = [
                'Batch ID',
                'Timestamp', 
                'Wallet Name',
                'Company',
                'Address',
                'Balance (USDT)',
                'Check Type'
            ]
            
            # Check if sheet exists and has data
            range_name = f"{sheet_name}!A1:G1"
            try:
                result = self.sheet.values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                if not values or values[0] != headers:
                    # Add or update headers
                    body = {
                        'values': [headers]
                    }
                    self.sheet.values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{sheet_name}!A1:G1",
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    logger.info(f"Added headers to {sheet_name} sheet")
                    
            except HttpError:
                # Sheet might not exist, headers will be added with first data
                pass
                
        except Exception as e:
            logger.warning(f"Could not ensure headers for {sheet_name}: {e}")


# Integration code for CheckHandler (add to your check_handler.py)

# Add this to the imports section:
# from .google_sheets_balance_logger import GoogleSheetsBalanceLogger

# Add this to CheckHandler.__init__ method:
# self.sheets_logger = GoogleSheetsBalanceLogger()

# Add this after successful balance fetching in handle() method, 
# right before creating the table card:

# Log to Google Sheets (add this in handle method after balance fetching)
try:
    self.sheets_logger.log_balance_check(balances, wallets_to_check, check_type="manual")
except Exception as e:
    logger.warning(f"Failed to log balance check to Google Sheets: {e}")
    # Continue with normal operation even if sheets logging fails


# Integration code for Daily Report Scheduler (add to your main.py)

# Add this to the imports section:
# from .google_sheets_balance_logger import GoogleSheetsBalanceLogger

# Add this to LarkDailyReportScheduler.__init__ method:
# self.sheets_logger = GoogleSheetsBalanceLogger()

# Add this in send_daily_report() method after successful balance fetching,
# right before creating the report card:

# Log to Google Sheets (add this in send_daily_report method after balance fetching)
try:
    self.sheets_logger.log_balance_check(successful_balances, wallet_data, check_type="scheduled")
except Exception as e:
    logger.warning(f"Failed to log daily report to Google Sheets: {e}")
    # Continue with normal operation even if sheets logging fails