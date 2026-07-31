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
from bot.services.vault_calendar import build_first_seen

# The vault's day boundary: a row dated D describes the balance at D 00:00:00 GMT+7.
#
# ONE constant, used in two places that must never disagree:
#   - the Time column written on a rebuilt row (save_rebuilt_balances)
#   - the cutoff CheckHandler reconstructs a missing date at
#
# They used to drift: rebuilt rows carried the time they were COMPUTED (e.g. 14:26:51),
# which read as a mid-afternoon figure when the number was really the day's opening
# balance. Import this rather than writing the literal anywhere.
#
# 00:00:00 rather than the scheduled runs' actual landing times, because those jitter
# (00:00:31, 00:00:59, 00:01:03, 00:01:20, 00:01:35) -- there is no single "real" time to
# match, so a rebuild anchors to the true GMT+7 boundary instead.
VAULT_DAY_BOUNDARY = "00:00:00"
REBUILT_TIME = VAULT_DAY_BOUNDARY   # what lands in the Time column of a rebuilt row


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
            data_rows = [[
                batch_id,                       # WHEN WE WROTE IT (audit trail; also makes
                                                # earliest-batch prefer a real measurement)
                date_str,                       # the date these balances describe
                REBUILT_TIME,                   # the INSTANT the figure describes, GMT+7
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
        EARLIEST batch value per address (a later intraday run only adds wallets).

        DO NOT "fix" this to take the latest batch. Reviewed and confirmed 2026-07-30
        against the live vault; two reasons it must stay earliest:

        1. A row dated D means the balance at ~00:01 GMT+7 on day D -- the opening
           figure. The daily report runs at 00:00 GMT+7 and stamps that day's date, and
           get_balance_at() reconstructs a missing date at exactly `D 00:01:00 GMT+7`.
           Taking the latest batch would label a mid-afternoon figure as day D, so saved
           dates and rebuilt dates would no longer describe the same instant. Real
           example: 2026-01-27 KZO TH OPS TRC 1 holds 1,472,481.02 at 00:00:31 and
           363,735.79 at 13:45:13. Only 4 of 309 dates have same-date duplicates at all,
           but the choice moves 2026-01-27's total by +223,574.35.

        2. batch_id is stamped when a row is WRITTEN, not with the time-of-day on the
           date it describes. Rebuilt rows therefore carry a later batch_id than the
           scheduled measurement they sit beside -- e.g. all 70 rebuilt rows for
           2026-07-20 carry batch ids 202607291720xx / 202607301426xx. "Latest batch"
           would let a reconstruction silently override a genuinely measured snapshot.
        """
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

    def _nearest_from(self, rows, dates, date_str):
        """Find the date (among `dates`) closest to date_str and its snapshot.

        Ties prefer the earlier date (a balance already established). Returns
        (None, {}) when there is no usable date to compare against.
        """
        if not dates:
            return None, {}
        from datetime import date as _date

        def _parse(d):
            try:
                return _date.fromisoformat(d)
            except ValueError:
                return None

        target = _parse(date_str)
        if target is None:
            return None, {}
        candidates = [(d, _parse(d)) for d in dates]
        candidates = [(d, p) for d, p in candidates if p is not None]
        if not candidates:
            return None, {}
        nearest = min(candidates, key=lambda dp: (abs((dp[1] - target).days), dp[1] > target))[0]
        return nearest, self._build_snapshot_from_rows(rows, nearest)

    def get_history_bundle(self, date_str, roster=None):
        """Everything the dated check needs, from ONE DAILY_REPORT read.

        Returns {"ok", "snapshot", "nearest_date", "nearest_snapshot", "first_seen"}.

        `ok` is False whenever the read failed. A caller MUST treat that as "I don't
        know what's saved", never as "nothing is saved" -- confusing the two is what
        once made /check rebuild and duplicate 68 already-saved wallets.

        `first_seen` is {} unless a roster is supplied. The sheet is ~17,500 rows, so
        deriving it here rather than re-reading keeps the command to a single read.
        """
        rows = self._read_daily_report_rows()
        if rows is None:
            return {"ok": False, "snapshot": {}, "nearest_date": None,
                    "nearest_snapshot": {}, "first_seen": {}}

        first_seen = build_first_seen(roster, rows) if roster else {}
        exact = self._build_snapshot_from_rows(rows, date_str)
        if exact:
            return {"ok": True, "snapshot": exact, "nearest_date": None,
                    "nearest_snapshot": {}, "first_seen": first_seen}

        dates = sorted({r[1] for r in rows if len(r) > 1 and r[1]})
        nearest_date, nearest_snapshot = self._nearest_from(rows, dates, date_str)
        return {"ok": True, "snapshot": {}, "nearest_date": nearest_date,
                "nearest_snapshot": nearest_snapshot, "first_seen": first_seen}

    def get_snapshot_and_nearest(self, date_str):
        """Back-compatible 4-tuple view of get_history_bundle: (snapshot, nearest_date,
        nearest_snapshot, ok). Kept so existing callers and tests are untouched."""
        b = self.get_history_bundle(date_str)
        return b["snapshot"], b["nearest_date"], b["nearest_snapshot"], b["ok"]

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