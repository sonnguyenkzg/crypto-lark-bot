import logging
import time

logger = logging.getLogger(__name__)
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bot.services.chain_detector import canonical_address

class GoogleSheetsBalanceLogger:
    """Logger for balance check results to Google Sheets"""

    WRITE_RETRIES = 4          # retries on transient Sheets failures (5xx/429/timeout)
    WRITE_RETRY_BACKOFF = 2.0  # seconds; doubles per retry (2, 4, 8, 16)
    
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
        date_str = gmt7_time.strftime('%Y-%m-%d')
        time_str = gmt7_time.strftime('%H:%M:%S')
        
        rows = []
        successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
        
        for wallet_name, balance in successful_balances.items():
            wallet_info = wallets_to_check.get(wallet_name, {})
            company = wallet_info.get('company', 'Unknown')
            address = wallet_info.get('address', '')
            
            row = [
                batch_id,
                date_str,
                time_str,
                wallet_name,
                company,
                address,
                f"{balance:.2f}",
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
            return False, None
            
        try:
            if not self._initialize_service():
                return False, None

            # Generate batch ID
            batch_id = self._generate_batch_id()
            
            # Prepare data rows
            data_rows = self._prepare_balance_rows(balances, wallets_to_check, batch_id, check_type)
            
            if not data_rows:
                logger.warning("No successful balance data to log")
                return False, None

            # Determine sheet name based on check type
            sheet_name = "CHECK" if check_type == "manual" else "DAILY_REPORT"

            # Check if headers exist, if not add them
            self._ensure_headers(sheet_name)

            # RELIABILITY: a transient Google Sheets outage must not lose the day's data.
            # On 2026-07-19 a single HTTP 503 here silently dropped a whole daily snapshot,
            # leaving a permanent hole in the history. Retry transient failures (5xx / 429 /
            # timeouts) with exponential backoff before giving up.
            result = self._append_rows_with_retry(sheet_name, data_rows)
            if result is None:
                return False, None

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

    def _append_rows_with_retry(self, sheet_name, data_rows):
        """Append rows, retrying transient Sheets failures (5xx/429/timeout).

        A single HTTP 503 here once silently lost a whole day of history, so a
        transient failure must never be treated as final. Returns the API result on
        success. If the last attempt still fails, the underlying error is raised --
        the caller's try/except turns that into a failure result, so a lost write is
        always reported, never mistaken for a successful one.
        """
        body = {"values": data_rows, "majorDimension": "ROWS"}
        delay = self.WRITE_RETRY_BACKOFF
        for attempt in range(self.WRITE_RETRIES + 1):
            try:
                return self.sheet.values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A:H",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                ).execute()
            except HttpError as e:
                status = getattr(getattr(e, "resp", None), "status", None)
                if status not in (429, 500, 502, 503, 504) or attempt >= self.WRITE_RETRIES:
                    raise
                logger.warning(f"Sheets append failed (HTTP {status}); retrying in "
                               f"{delay:.1f}s ({attempt + 1}/{self.WRITE_RETRIES})")
            except (TimeoutError, OSError) as e:
                if attempt >= self.WRITE_RETRIES:
                    raise
                logger.warning(f"Sheets append failed ({e}); retrying in "
                               f"{delay:.1f}s ({attempt + 1}/{self.WRITE_RETRIES})")
            time.sleep(delay)
            delay *= 2

    def save_rebuilt_balances(self, date_str, rows):
        """Write rebuilt balances into the daily record for `date_str`.

        These fill a hole in the history so the date never needs rebuilding again.
        They are marked "rebuilt" so they stay distinguishable from figures that
        were actually measured on the day.

        rows: [{"name", "company", "address", "balance"}]
        Returns (success, batch_id).
        """
        if not rows:
            return False, None
        if not self.credentials_file or not self.spreadsheet_id:
            logger.warning("Google Sheets not configured; rebuilt balances not saved")
            return False, None
        try:
            if not self._initialize_service():
                return False, None
            batch_id = self._generate_batch_id()
            now = datetime.now(timezone(timedelta(hours=7)))
            data_rows = [[
                batch_id,
                date_str,                       # the date these balances describe
                now.strftime("%H:%M:%S"),       # when we worked them out
                r["name"],
                r.get("company", "Unknown"),
                r.get("address", ""),
                f"{r['balance']:.2f}",
                "rebuilt",
            ] for r in rows]
            self._ensure_headers("DAILY_REPORT")
            if self._append_rows_with_retry("DAILY_REPORT", data_rows) is None:
                return False, None
            logger.info(f"✅ Saved {len(data_rows)} rebuilt balances for {date_str} "
                        f"(batch {batch_id})")
            return True, batch_id
        except Exception as e:
            logger.error(f"Failed to save rebuilt balances for {date_str}: {e}")
            return False, None

    def _ensure_headers(self, sheet_name):
        """Ensure the sheet has proper headers"""
        try:
            headers = [
                'Batch ID',
                'Date',
                'Time', 
                'Wallet Name',
                'Company',
                'Address',
                'Balance (USDT)',
                'Check Type'
            ]
            
            # Check if sheet exists and has data
            range_name = f"{sheet_name}!A1:H1"
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

    def _parse_amount(self, s):
        """Parse a stored balance ('351,432.18') to Decimal. Returns None for an
        empty or non-numeric cell so the caller can EXCLUDE (not silently zero) it."""
        try:
            cleaned = str(s).replace(",", "").strip()
            if not cleaned:
                return None
            return Decimal(cleaned)
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _build_snapshot_from_rows(self, rows, date_str):
        """Union of all that-date batches, keyed by canonical_address, keeping the
        EARLIEST batch value per address (a later intraday run only adds wallets)."""
        snap = {}
        for r in rows:
            # cols: 0 batch,1 date,2 time,3 wallet,4 company,5 address,6 balance,7 type
            if len(r) < 7 or r[1] != date_str:
                continue
            key = canonical_address(r[5])
            if not key:
                continue
            amount = self._parse_amount(r[6])
            if amount is None:
                continue   # corrupted/empty balance -> exclude; completeness guard will surface it
            prev = snap.get(key)
            if prev is None or r[0] < prev["batch_id"]:   # earliest batch_id wins
                snap[key] = {
                    "wallet_name": r[3],
                    "company": r[4],
                    "address": r[5],
                    "balance": amount,
                    "batch_id": r[0],
                    "time": r[2],
                }
        return snap

    def get_snapshot_and_nearest(self, date_str):
        """Return (snapshot_for_date, nearest_date, nearest_snapshot, ok) in ONE sheet read.

        `ok` is False whenever the underlying read failed -- unconfigured credentials,
        service init failure, or an exception from the Sheets API -- in which case the
        first three values are ({}, None, {}). CRITICAL: a caller MUST treat ok=False as
        "I don't know what's saved", never as "nothing is saved". Confusing the two is
        exactly the bug that caused /check [2026-07-15] to rebuild and duplicate 68
        already-saved wallets after a transient read failure returned an empty result.

        When ok is True and date_str has no saved record, nearest_date/nearest_snapshot
        describe the closest date that does, so a caller can always show a number for
        every wallet instead of leaving it blank. Ties prefer the earlier date (a
        balance already established).
        """
        rows = self._read_daily_report_rows()
        if rows is None:
            return {}, None, {}, False
        exact = self._build_snapshot_from_rows(rows, date_str)
        if exact:
            return exact, None, {}, True
        dates = sorted({r[1] for r in rows if len(r) > 1 and r[1]})
        if not dates:
            return {}, None, {}, True
        from datetime import date as _date

        def _parse(d):
            try:
                return _date.fromisoformat(d)
            except ValueError:
                return None

        target = _parse(date_str)
        if target is None:
            return {}, None, {}, True
        candidates = [(d, _parse(d)) for d in dates]
        candidates = [(d, p) for d, p in candidates if p is not None]
        if not candidates:
            return {}, None, {}, True
        nearest = min(candidates, key=lambda dp: (abs((dp[1] - target).days), dp[1] > target))[0]
        return {}, nearest, self._build_snapshot_from_rows(rows, nearest), True

    def _read_daily_report_rows(self):
        """Read DAILY_REPORT data rows (no header).

        Returns None on ANY failure -- unconfigured credentials, service init failure,
        or an exception raised by the Sheets API call -- so a failed read can never be
        confused with a sheet that genuinely has no rows for the date. Returns a list
        (possibly empty, when the sheet truly holds nothing) on success.
        """
        if not self.credentials_file or not self.spreadsheet_id:
            return None
        try:
            if not self._initialize_service():
                return None
            res = self.sheet.values().get(
                spreadsheetId=self.spreadsheet_id, range="DAILY_REPORT!A:H").execute()
            rows = res.get("values", [])
            return rows[1:] if rows else []
        except Exception as e:
            logger.error(f"Failed to read DAILY_REPORT: {e}")
            return None

    def get_snapshot_for_date(self, date_str):
        """Read DAILY_REPORT and return the assembled snapshot for date_str."""
        if not self.credentials_file or not self.spreadsheet_id:
            return {}
        try:
            if not self._initialize_service():
                return {}
            res = self.sheet.values().get(
                spreadsheetId=self.spreadsheet_id, range="DAILY_REPORT!A:H").execute()
            rows = res.get("values", [])
            return self._build_snapshot_from_rows(rows[1:] if rows else [], date_str)
        except Exception as e:
            logger.error(f"Failed to read DAILY_REPORT snapshot for {date_str}: {e}")
            return {}