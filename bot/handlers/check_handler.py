#!/usr/bin/env python3
"""
Check Handler for Lark Bot - Following Telegram Bot Pattern
Checks wallet balances with beautiful table format
FIXED: Group display issue - Now correctly uses company information from wallet data
"""
from bot.services.google_sheets_logger import GoogleSheetsBalanceLogger
import os
import logging
import re
import time
import asyncio
import concurrent.futures
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from bot.services.wallet_service import WalletService
from bot.services.balance_service import BalanceService
from bot.services.chain_detector import detect_chain_from_address, get_chain_emoji, canonical_address
from bot.services.command_args import resolve_fuzzy, parse_arguments, split_date, is_valid_iso_date, classify_tokens
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Global execution lock to prevent continuous calling
_CHECK_EXECUTION_LOCK = False

class CheckHandler:
    RECON_CONCURRENCY = 3          # low: Tronscan rate-limits bursts (HTTP 429)
    # Total lock-hold cap for rebuilding. Applies whenever ANY wallet has no saved
    # figure for the requested date -- not just when the whole date is missing.
    RECON_TOTAL_BUDGET = 240.0

    def __init__(self):
        self.name = "check"
        self.description = "Check wallet balances (all wallets or specific ones)"
        self.usage = '/check [optional: date] [optional: company] [optional: wallet]'
        self.aliases = ["balance", "bal"]
        self.enabled = True
        self.wallet_service = WalletService()
        self.balance_service = BalanceService()
        self.sheets_logger = GoogleSheetsBalanceLogger()

    def resolve_wallets_to_check(self, inputs: List[str], wallet_data: Dict) -> Tuple[Dict[str, Dict], List[str]]:
        """
        Resolve input arguments to {display_name: wallet_info} mapping.
        
        Args:
            inputs: List of wallet names or addresses from user
            wallet_data: All available wallet data from JSON
            
        Returns:
            tuple: (wallets_to_check, not_found_list)
        """
        wallets_to_check = {}
        not_found = []
        
        for input_str in inputs:
            input_str = input_str.strip()
            if not input_str:
                continue
                
            # Detect chain type from address format
            detected_chain = detect_chain_from_address(input_str)

            if detected_chain:
                # It's a valid address (TRC20 or ERC20) - find the wallet name or use address as display
                found_wallet = False
                for wallet_key, wallet_info in wallet_data.items():
                    if wallet_info['address'].lower() == input_str.lower():
                        wallets_to_check[wallet_info['wallet']] = wallet_info
                        found_wallet = True
                        break

                if not found_wallet:
                    # Address not in our list - still check it
                    display_name = f"External: {input_str[:10]}...{input_str[-6:]}"
                    wallets_to_check[display_name] = {
                        'wallet': display_name,
                        'address': input_str,
                        'company': 'External',
                        'chain': detected_chain  # Include detected chain
                    }
            
            else:
                # It's a wallet name - find the address (case-insensitive)
                found_wallet = False
                for wallet_key, wallet_info in wallet_data.items():
                    # FIXED: Use 'wallet' key instead of 'name'
                    wallet_name = wallet_info.get('wallet', wallet_key)
                    if wallet_name.lower() == input_str.lower():
                        wallets_to_check[wallet_name] = wallet_info
                        found_wallet = True
                        break
                
                if not found_wallet:
                    not_found.append(input_str)
        
        return wallets_to_check, not_found

    async def handle(self, context: Any) -> bool:
        global _CHECK_EXECUTION_LOCK
        
        # CRITICAL: Prevent continuous calling
        if _CHECK_EXECUTION_LOCK:
            logger.warning(f"🚫 Check command already executing - BLOCKING duplicate call from user {context.sender_id}")
            # Say so out loud: a rebuild can hold this lock for minutes, and silence
            # makes the bot look dead. A failure to send must not break the guard.
            try:
                await context.topic_manager.send_command_response(
                    self._create_already_running_card(), msg_type="interactive")
            except Exception as e:
                logger.warning(f"Could not tell the user a check is already running: {e}")
            return False
        
        # Lock execution
        _CHECK_EXECUTION_LOCK = True
        logger.info(f"🔒 Check command LOCKED - Starting execution for user {context.sender_id}")
        
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            user_id = context.sender_id
            command_args = " ".join(context.args) if context.args else ""

            logger.info(f"Check command received from user ID: {user_id}")
            logger.info(f"Command args: '{command_args}'")

            # Parse [bracket]/"quote"/'quote' tokens once, up front, and split off a
            # leading ISO date if present -> routes to the LIVE path or the historical path.
            tokens, had_bare = parse_arguments(command_args)
            date_str, other = split_date(tokens)
            # A bare (undelimited) token is silently DROPPED by parse_arguments -- it never
            # reaches `tokens`/`other`, so we can flag THAT it happened (had_bare) but not
            # say what it was. For the LIVE (no-date) path this matches pre-Task-8 behaviour
            # exactly (parse_check_arguments only ever recognized "quoted" strings too, so a
            # bare word already silently fell back to "check all wallets" before this diff)
            # -- unchanged on purpose, handled further down where `inputs = other` is used.
            # For the HISTORICAL path there is no such legacy precedent: silently proceeding
            # with an empty/partial filter could return a materially different, unfiltered
            # result than the user asked for (e.g. `/check [2026-07-15] KZP` would silently
            # show ALL companies, not just KZP), so that combination is handled explicitly
            # right before the historical dispatch below instead of guessing.

            # Load all wallets
            success, wallet_list_data = self.wallet_service.list_wallets()
            if not success or not wallet_list_data.get('companies'):
                no_wallets_card = self._create_no_wallets_card()
                await context.topic_manager.send_command_response(no_wallets_card, msg_type="interactive")
                return True

            # Convert wallet list data to flat dictionary for easier processing
            wallet_data = {}
            for company_name, company_wallets in wallet_list_data['companies'].items():
                for wallet in company_wallets:
                    wallet_key = f"{wallet['name']}"
                    wallet_data[wallet_key] = {
                        'wallet': wallet['name'],  # FIXED: Use 'wallet' key instead of 'name'
                        'address': wallet['address'],
                        'company': company_name,  # Use the actual company name from the data structure
                        'chain': wallet.get('chain', 'TRC20'),  # Include chain information (default to TRC20 for backward compatibility)
                        'created_at': wallet.get('created_at')  # Used by /check [date]'s completeness guard (_existed_by)
                    }

            # Date present -> historical branch (Task 8); wallet_data doubles as the
            # current roster used for the completeness guard / reconstruction fallback.
            if date_str:
                if had_bare:
                    # Some part of the command was un-bracketed and got silently dropped by
                    # parse_arguments; proceeding here could silently show an unfiltered
                    # result instead of what the user actually asked to filter to, so stop
                    # and ask them to re-wrap it rather than guess.
                    await context.topic_manager.send_command_response(
                        self._create_bracket_hint_card(date_str), msg_type="interactive")
                    return False
                return await self._handle_historical(context, date_str, other, wallet_data)

            # A bare, un-bracketed ISO date (e.g. `/check 2026-07-15`) parses to no tokens
            # and would silently run a full LIVE check -- the user could mistake today's
            # balances for that date's. Detect the bare date and ask them to bracket it.
            if not date_str and had_bare:
                m = re.search(r'\b\d{4}-\d{2}-\d{2}\b', command_args)
                if m:
                    await context.topic_manager.send_command_response(
                        self._create_bracket_hint_card(m.group(0)), msg_type="interactive")
                    return False

            # LIVE path (unchanged): inputs now come from the shared token parser
            # (parse_arguments/split_date) instead of parse_check_arguments, so
            # [bracket] wallet/company names work the same as "quoted" ones.
            inputs = other

            if not inputs:
                # Check all wallets - return full wallet info
                # FIXED: Use 'wallet' key instead of 'name'
                wallets_to_check = {info['wallet']: info for info in wallet_data.values()}
                not_found = []
            else:
                # Resolve inputs to wallets
                wallets_to_check, not_found = self.resolve_wallets_to_check(inputs, wallet_data)
                
                # If no valid wallets found but we had inputs, show error
                if not wallets_to_check and not_found:
                    error_card = self._create_not_found_error_card(not_found, wallet_data)
                    await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                    return False

            # Show "checking..." message
            checking_card = self._create_checking_card(len(wallets_to_check))
            await context.topic_manager.send_command_response(checking_card, msg_type="interactive")

            # Create wallet mapping for balance service (includes address and chain)
            wallet_mapping = {
                name: {
                    'address': info['address'],
                    'chain': info.get('chain', 'TRC20')  # Default to TRC20 for backward compatibility
                }
                for name, info in wallets_to_check.items()
            }

            # Fetch balances with timeout to prevent hanging
            logger.info(f"Fetching balances for {len(wallets_to_check)} wallets...")
            
            try:
                # Use asyncio.to_thread with timeout to prevent hanging
                balances = await asyncio.wait_for(
                    asyncio.to_thread(self.balance_service.fetch_multiple_balances, wallet_mapping),
                    timeout=90.0  # 90 second timeout
                )
            except asyncio.TimeoutError:
                logger.error("⏰ Balance fetch timed out after 30 seconds")
                timeout_card = self._create_timeout_error_card()
                await context.topic_manager.send_command_response(timeout_card, msg_type="interactive")
                return False
            
            # Log to Google Sheets and track success
            sheets_logged = False
            batch_id = None
            try:
                # Off the event loop: this is a blocking Sheets call with retries/backoff,
                # and the bot serves every other command on this one loop.
                success, batch_id = await asyncio.to_thread(
                    self.sheets_logger.log_balance_check, balances, wallets_to_check, "manual")
                sheets_logged = success
                logger.info("✅ Successfully logged to Google Sheets")
            except Exception as e:
                logger.warning(f"Failed to log to Google Sheets: {e}")
                sheets_logged = False
                batch_id = None

            # Process results and create table
            successful_checks = sum(1 for balance in balances.values() if balance is not None)
            
            if successful_checks == 0:
                error_card = self._create_fetch_error_card()
                await context.topic_manager.send_command_response(error_card, msg_type="interactive")
                return False

            # Create the beautiful table card matching your screenshot
            time_str = self.balance_service.get_current_gmt_time()
            
            table_card = self._create_balance_table_card_with_sheets_info(balances, wallets_to_check, time_str, not_found, sheets_logged, batch_id)
            await context.topic_manager.send_command_response(table_card, msg_type="interactive")

            logger.info(f"✅ Check command completed for user: {user_id}, {successful_checks}/{len(wallets_to_check)} successful")
            return True

        except Exception as e:
            logger.error(f"❌ Error in check command: {e}")
            # Fallback to text message
            fallback_message = f"❌ **Error checking balances:** {str(e)}"
            await context.topic_manager.send_command_response(fallback_message)
            return False
        
        finally:
            # CRITICAL: Always unlock execution in finally block
            _CHECK_EXECUTION_LOCK = False
            logger.info(f"🔓 Check command UNLOCKED - Execution finished for user {context.sender_id}")

    def _existed_by(self, created_at, date_str):
        """True if a wallet with this created_at existed on/before date_str.
        Missing OR unparseable created_at -> True (safe direction: still expect it,
        so a snapshot-missing wallet still surfaces in the completeness guard)."""
        if not created_at:
            return True
        prefix = str(created_at)[:10]
        try:
            datetime.strptime(prefix, "%Y-%m-%d")   # must be a real ISO date
        except (ValueError, TypeError):
            return True                              # unparseable -> safe direction
        return prefix <= date_str

    def classify_wallets(self, roster, snapshot, date_str):
        """Decide, per wallet, what we can show for `date_str`. Pure - no network.

        SCOPE: the wallets currently in wallets.json, and only those. A wallet that
        has since been removed from monitoring is ignored even if the daily record
        still holds a figure for it that day -- reporting is about the wallets under
        monitoring now, so the count always reconciles to wallets.json.

        status: saved            - a figure was recorded that day
                needs_rebuild    - existed then, no figure recorded -> work it out
                not_yet_created  - added after this date, so it has no balance
        """
        out = []
        for w in roster:
            key = canonical_address(w.get("address", ""))
            entry = snapshot.get(key)
            if entry:
                status, balance = "saved", entry["balance"]
            elif self._existed_by(w.get("created_at"), date_str):
                status, balance = "needs_rebuild", None
            else:
                status, balance = "not_yet_created", None
            out.append({"name": w.get("wallet"), "company": w.get("company", "Unknown"),
                        "address": w.get("address", ""), "chain": w.get("chain", "TRC20"),
                        "status": status, "balance": balance})

        return out

    async def _handle_historical(self, context: Any, date_str: str, other_tokens: List[str],
                                  wallet_data: Dict) -> bool:
        """Route for `/check [date] ...`.

        Validates the date, classifies the remaining tokens into group/name filters,
        then resolves each wallet INDEPENDENTLY for that date (classify_wallets): already
        saved, rebuilt from chain history and saved back, added after the date, or failed.
        Whatever gets rebuilt is written back, so this date is never fully rebuilt twice.
        """
        if not is_valid_iso_date(date_str):
            await context.topic_manager.send_command_response(
                self._create_bad_date_card(date_str), msg_type="interactive")
            return False

        gmt7_today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
        if date_str > gmt7_today:
            await context.topic_manager.send_command_response(
                self._create_future_date_card(date_str), msg_type="interactive")
            return False

        companies = sorted({info["company"] for info in wallet_data.values()})
        names_all = [info["wallet"] for info in wallet_data.values()]
        groups, names = classify_tokens(other_tokens, companies, names_all)

        # Off the event loop: reading the sheet blocks (and retries), and the bot serves
        # every other command plus its health check on this single loop.
        snapshot, _nearest_date, _nearest_snapshot, ok = \
            await asyncio.to_thread(self.sheets_logger.get_snapshot_and_nearest, date_str)

        # CRITICAL: a failed read must NEVER be treated as "nothing is saved for this
        # date". That confusion is exactly what caused /check [2026-07-15] to rebuild and
        # duplicate 68 already-saved wallets after a transient Sheets error. If we can't
        # read the record, stop here -- no classifying, no rebuilding, no saving.
        if not ok:
            await context.topic_manager.send_command_response(
                self._create_sheet_unavailable_card(date_str), msg_type="interactive")
            return False

        roster = [{"wallet": i["wallet"], "company": i["company"], "address": i["address"],
                   "chain": i.get("chain", "TRC20"), "created_at": i.get("created_at")}
                  for i in wallet_data.values()]

        entries = self.classify_wallets(roster, snapshot, date_str)
        entries, fuzzy, not_found = self._filter_entries(entries, groups, names)

        # Acknowledge immediately (same courtesy as the live /check path): reading the
        # sheet takes a moment and a gap date can take up to ~90s to rebuild, so the user
        # should never be left staring at silence. Sent AFTER filters are resolved so it
        # can report the match count, echoing back what was understood.
        await context.topic_manager.send_command_response(
            self._create_historical_checking_card(date_str, groups, names, len(entries),
                                                  roster_total=len(roster)),
            msg_type="interactive")

        todo = [e for e in entries if e["status"] == "needs_rebuild"]
        if todo:
            if len(todo) == len(entries):
                # Legitimate gap-date case (e.g. a date the bot never ran for) still must
                # be allowed to rebuild everything -- this is NOT the bug being guarded
                # against above (that was an empty snapshot caused by a READ FAILURE, now
                # blocked by the `ok` check). Just make it visible in the logs.
                logger.info(f"Rebuilding ALL {len(todo)} wallets in scope for {date_str} "
                            "(no saved balances found)")
            await context.topic_manager.send_command_response(
                self._create_rebuilding_card(date_str, len(todo)), msg_type="interactive")
            cutoff_ms = int(datetime.strptime(date_str + " 00:01:00", "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
            await self._rebuild_entries(todo, cutoff_ms)

        # Persist whatever we worked out, so this date never needs rebuilding again.
        # Partial is fine: a later check rebuilds only what is still missing.
        fresh = [e for e in entries if e["status"] == "rebuilt"]
        saved_batch = None
        if fresh:
            # Off the event loop: the write retries with backoff for up to ~30s.
            ok, batch = await asyncio.to_thread(
                self.sheets_logger.save_rebuilt_balances, date_str, [
                    {"name": e["name"], "company": e["company"],
                     "address": e["address"], "balance": e["balance"]} for e in fresh])
            saved_batch = batch if ok else None

        card = self._create_historical_card(entries, date_str, fuzzy, not_found, saved_batch,
                                           roster_total=len(roster), filtered=bool(groups or names))

        await context.topic_manager.send_command_response(card, msg_type="interactive")
        return True

    async def _rebuild_entries(self, entries, cutoff_ms):
        """Work out each entry's balance from chain history, in place.

        Runs on a dedicated pool, so slow lookups never occupy the executor the live
        /check path uses. The *executor* is separate, but the outbound request rate is
        NOT: the balance service paces every call to a provider process-wide, so a
        worker still running after we stopped waiting would keep taking that shared
        budget and starve the next live /check. That is what the deadline bounds -- it
        is handed to each worker, which stops on its own once the budget expires.
        Anything unfinished is marked failed, never dropped.
        """
        loop = asyncio.get_event_loop()
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.RECON_CONCURRENCY, thread_name_prefix="recon")
        deadline = time.monotonic() + self.RECON_TOTAL_BUDGET
        try:
            fut_to_entry = {}
            for e in entries:
                f = loop.run_in_executor(pool, self.balance_service.get_balance_at,
                                         e["address"], e.get("chain", "TRC20"), cutoff_ms,
                                         deadline)
                fut_to_entry[f] = e
            done, pending = await asyncio.wait(list(fut_to_entry.keys()),
                                               timeout=self.RECON_TOTAL_BUDGET)
            for f in pending:
                f.cancel()
                fut_to_entry[f]["status"] = "failed"
            for f in done:
                e = fut_to_entry[f]
                try:
                    bal = f.result()
                except Exception as exc:
                    logger.error(f"Rebuild failed for {e['name']}: {exc}")
                    bal = None
                if bal is None:
                    e["status"] = "failed"
                else:
                    e["status"], e["balance"] = "rebuilt", bal
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _filter_entries(self, entries, groups, names):
        """Apply company/wallet-name filters. Returns (entries, fuzzy, not_found)."""
        if groups:
            wanted = {g.lower() for g in groups}
            entries = [e for e in entries if e["company"].lower() in wanted]
        fuzzy, not_found = {}, []
        if names:
            all_names = [e["name"] for e in entries]
            picked, seen = [], set()
            for want in names:
                matches, tier = resolve_fuzzy(want, all_names)
                if not matches:
                    not_found.append(want)
                    continue
                if tier == "closest match":
                    fuzzy[want] = matches
                for e in entries:
                    if e["name"] in matches and id(e) not in seen:
                        seen.add(id(e))
                        picked.append(e)
            entries = picked
        return entries, fuzzy, not_found

    def _create_balance_table_card_with_sheets_info(self, balances: Dict[str, Decimal], wallets_to_check: Dict[str, Dict], time_str: str, not_found: List[str], sheets_logged: bool = False, batch_id: str = None) -> dict:        
        """Create table using Lark's column layout for better formatting with Google Sheets info."""
        
        # Calculate totals
        total_wallets = len(balances)
        successful_balances = {name: balance for name, balance in balances.items() if balance is not None}
        grand_total = sum(successful_balances.values())
        
        # Sort wallets by group then by name using the actual wallet data
        wallet_list = []
        for wallet_name, balance in successful_balances.items():
            # Get the company/group from the wallet data
            wallet_info = wallets_to_check.get(wallet_name, {})
            group = wallet_info.get('company', 'Unknown')
            wallet_list.append((group, wallet_name, balance))
        
        wallet_list.sort(key=lambda x: (x[0], x[1]))

        # Calculate grouped totals dynamically
        company_totals = defaultdict(Decimal)

        for group, wallet_name, balance in wallet_list:
            # Preserve KZG+KZO merge logic (existing business requirement)
            if group.startswith('KZG') or group.startswith('KZO'):
                display_group = "KZG + KZO"
            else:
                # For all other companies, use the company name as-is
                display_group = group

            company_totals[display_group] += balance

        # Sort alphabetically
        sorted_companies = sorted(company_totals.keys())
        
        # Build elements with structured table layout
        elements = [
            # Header info
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "🤖 **Wallet Balance Check**"
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
            }
        ]
        
        # Add Google Sheets info if logged successfully
        if sheets_logged and batch_id:
            spreadsheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            if spreadsheet_id:
                sheets_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit?gid=1979323493#gid=1979323493"
                elements.append({
                    "tag": "div", 
                    "text": {
                        "tag": "lark_md",
                        "content": f"📈 **Data logged to:** [Google Sheets CHECK tab]({sheets_url}) (Batch ID: {batch_id})"
                    }
                })
        
        # Continue with existing elements...
        elements.extend([
            # Separator
            {
                "tag": "hr"
            },
            
            # Grouped totals section
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "📈 **Totals by Group**"
                }
            },
            
            # Group totals table header
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
                        "weight": 1,
                        "vertical_align": "center",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**Total (USDT)**"
                                }
                            }
                        ]
                    }
                ]
            },
            
        ])

        # Dynamic company rows
        for company in sorted_companies:
            total = company_totals[company]

            company_row = {
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
                                    "content": company
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
                                    "content": f"{total:,.2f}"
                                }
                            }
                        ]
                    }
                ]
            }
            elements.append(company_row)

        # Continue with separator and detailed breakdown
        elements.extend([
            
            # Separator between grouped totals and detailed table
            {
                "tag": "hr"
            },
            
            # Detailed table section
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "📋 **Detailed Breakdown**"
                }
            },
            
            # Table header using column layout
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
        ])
        
        # Add data rows using column layout with right-aligned amounts
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
        
        # Add separator and total row
        elements.append({
            "tag": "hr"
        })
        
        # Total row with bold text, no background
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
        
        # Add not found notice if any
        if not_found:
            elements.extend([
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"❌ **Not found:** {', '.join(not_found)}"
                    }
                }
            ])

        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🤖 Wallet Balance Check"
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": f"Total: {grand_total:,.2f} USDT"
                }
            },
            "elements": elements
        }

    def _create_historical_card(self, entries, date_str, fuzzy, not_found, saved_batch,
                                roster_total=None, filtered=False):
        """Balance table for a past date, plus a plain account of where each figure came from."""
        counted = [e for e in entries if e["balance"] is not None]
        rows = [{"name": e["name"], "company": e["company"], "address": e["address"],
                 "balance": e["balance"], "source": e["status"]} for e in counted]

        balances, wallets_to_check = {}, {}
        for r in rows:
            key = r["name"]
            if key in balances:
                key = f'{r["name"]} [{canonical_address(r["address"])}]'
                n = 2
                while key in balances:
                    key = f'{r["name"]} [{canonical_address(r["address"])}] #{n}'
                    n += 1
            balances[key] = r["balance"]
            wallets_to_check[key] = {"company": r["company"]}

        base_card = self._create_balance_table_card_with_sheets_info(
            balances, wallets_to_check, time_str=date_str,
            not_found=[], sheets_logged=False, batch_id=None)
        table_elements = base_card["elements"][3:]

        n_saved = sum(1 for e in counted if e["status"] == "saved")
        n_rebuilt = sum(1 for e in counted if e["status"] == "rebuilt")
        later = [e["name"] for e in entries if e["status"] == "not_yet_created"]
        failed = [e["name"] for e in entries if e["status"] == "failed"]

        def names(ns):
            return ", ".join(f"**{n}**" for n in ns)

        # Start from the number of wallets under monitoring and account for every one of
        # them, so the counted figure is never a number the reader has to work backwards to.
        # Exception lines lead with the wallet name, not the reason.
        lines = []
        if filtered:
            lines.append(f"📊 **Wallets in scope: {len(counted)} of {roster_total} "
                         f"monitored** · {date_str}")
        else:
            lines.append(f"📊 **Total wallets in monitoring: {roster_total}** · {date_str}")
        if n_saved:
            lines.append(f"• **{n_saved}** have a balance recorded for this date")
        if n_rebuilt:
            lines.append(f"• **{n_rebuilt}** were calculated from blockchain records")
        if later:
            lines.append(f"• {names(later)} — added after this date, so no balance yet")
        if failed:
            lines.append(f"• {names(failed)} — could not be calculated, so not counted")
        lines.append(f"➡️ **{len(counted)} {'wallet' if len(counted) == 1 else 'wallets'} "
                     f"counted** in the total below")

        header_elements = [{"tag": "div",
                            "text": {"tag": "lark_md", "content": "\n".join(lines)}}]

        # (added-later / removed / could-not-work-out are itemised in the summary above,
        # so they are not repeated as separate notes here.)

        for want, matches in (fuzzy or {}).items():
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f'🔍 Showing **{", ".join(matches)}** — closest match to "{want}".'}})

        for want in (not_found or []):
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f'❌ Wallet "{want}" not found.'}})

        header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
            f"⏰ **Time:** {self.balance_service.get_current_gmt_time()} GMT+7"}})

        if saved_batch:
            header_elements.append({"tag": "div", "text": {"tag": "lark_md", "content":
                f"📈 **{n_rebuilt} rebuilt {'balance' if n_rebuilt == 1 else 'balances'} "
                f"saved to Google Sheets** (Batch ID: {saved_batch})"}})

        base_card["elements"] = header_elements + table_elements
        grand_total = sum(balances.values()) if balances else Decimal("0")
        # If any wallet has no figure, say so in the headline itself -- the reason sits
        # far down a long card, and an unmarked total reads as the full day's money.
        if failed:
            subtitle = (f"{date_str} · Partial total ({len(failed)} unavailable): "
                        f"{grand_total:,.2f} USDT")
            template = "orange"
        else:
            subtitle = f"{date_str} · Total: {grand_total:,.2f} USDT"
            template = "purple" if n_rebuilt else "blue"
        base_card["header"] = {
            "template": template,
            "title": {"tag": "plain_text", "content": "🕰️ Historical Wallet Balance Check"},
            "subtitle": {"tag": "plain_text", "content": subtitle},
        }
        return base_card

    def _create_sheet_unavailable_card(self, date_str: str) -> dict:
        """Saved balances couldn't be read -- never rebuild in this state."""
        return {
            "config": {"wide_screen_mode": True, "enable_forward": False},
            "header": {"template": "red",
                       "title": {"tag": "plain_text", "content": "❌ Couldn't Read Saved Balances"}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content":
                f"I couldn't read the saved balances for **{date_str}** just now, so I've stopped "
                "rather than risk rebuilding figures that are already recorded.\n\n"
                "This is usually temporary — please try again in a minute."}}],
        }

    def _create_bad_date_card(self, date_str: str) -> dict:
        """Create invalid-date error card for `/check [date]`."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Invalid Date"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"❌ **\"{date_str}\" is not a valid date.**\n\n"
                                   "Use ISO format in brackets, e.g. `/check [2026-07-15]`."
                    }
                }
            ]
        }

    def _create_future_date_card(self, date_str: str) -> dict:
        """Create future-date error card for `/check [date]`."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⏳ Future Date"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"⏳ **{date_str} is in the future.**\n\n"
                                   "Historical checks only work for today or earlier (GMT+7)."
                    }
                }
            ]
        }

    def _create_bracket_hint_card(self, date_str: str) -> dict:
        """Create hint card for two un-bracketed cases:
        1. `/check 2026-07-15` (bare date, no brackets at all) -- would otherwise silently
           fall through to a full LIVE check, which the user could mistake for that date's
           balances.
        2. `/check [2026-07-15] KZP` (bracketed date + un-bracketed filter) -- the filter
           word is silently dropped by parse_arguments and could show an unfiltered result
           the user didn't ask for.

        parse_arguments only recognizes [bracket]/"quote"/'quote' tokens; a bare
        (un-delimited) word is silently dropped and we're only told THAT it happened, not
        what it was. Rather than guess in either case, we stop here and ask the user to
        wrap the whole command -- date included -- in brackets.
        """
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ Wrap Dates and Filters in [ ]"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⚠️ **Part of your command wasn't recognized and was ignored.**\n\n"
                                   f"Wrap the date (and any filter) in brackets, like "
                                   f"**/check [{date_str}]** for a date on its own, or "
                                   f"**/check [{date_str}] [KZP]** to also filter by company "
                                   "or wallet name."
                    }
                }
            ]
        }

    def _create_historical_checking_card(self, date_str, groups=None, names=None, matched=None,
                                         roster_total=None) -> dict:
        """Confirm what the bot understood, before any waiting begins.

        States the number of wallets under monitoring rather than an internal "matched"
        count, so the figure always reconciles to the wallet list.
        """
        lines = [f"📅 **Date:** {date_str}"]
        if groups:
            lines.append(f"🏢 **Company:** {', '.join(groups)}")
        if names:
            lines.append(f"👛 **Wallets requested:** {', '.join(f'**{n}**' for n in names)}")
        if matched is not None:
            if groups or names:
                lines.append(f"📊 **Wallets in scope: {matched}"
                             + (f" of {roster_total} monitored" if roster_total else "") + "**")
            else:
                lines.append(f"📊 **Total wallets in monitoring: {matched}**")
        lines.append("\nReading recorded balances; anything not yet recorded will be calculated.")
        return {
            "config": {"wide_screen_mode": True, "enable_forward": False},
            "header": {"template": "blue",
                       "title": {"tag": "plain_text", "content": "🔄 Checking Balances..."}},
            "elements": [{"tag": "div",
                          "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
        }

    def _create_rebuilding_card(self, date_str: str, wallet_count: int) -> dict:
        """Tell the user we fell back to rebuilding from the blockchain (the slow path)."""
        wallet_word = "wallet" if wallet_count == 1 else "wallets"
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🔄 Rebuilding From Blockchain..."
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🔄 **Some balances for {date_str} aren't saved yet, so I'm "
                                   f"rebuilding {wallet_count} {wallet_word} from blockchain records.**\n\n"
                                   "This is slower than reading a saved record — rebuilding can take "
                                   "up to about four minutes. Any wallet that can't be worked out in time "
                                   "will be listed as \"unavailable\" rather than left out."
                    }
                }
            ]
        }

    def _create_already_running_card(self) -> dict:
        """Tell the user their /check was turned away because one is already running."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⏳ Another Check Is Running"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "A balance check is already running. Please wait for it to "
                                   "finish and try again — historical checks can take a few minutes."
                    }
                }
            ]
        }

    def _create_checking_card(self, wallet_count: int) -> dict:
        """Create 'checking...' status card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🔄 Checking Balances..."
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🔄 **Fetching balances for {wallet_count} wallets...**\n\nThis may take a few seconds."
                    }
                }
            ]
        }

    def _create_no_wallets_card(self) -> dict:
        """Create no wallets configured card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ No Wallets Configured"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **No wallets configured**\n\nUse **/add** to add your first wallet."
                    }
                }
            ]
        }

    def _create_not_found_error_card(self, not_found: List[str], wallet_data: Dict) -> dict:
        """Create wallet not found error card."""
        available_names = list(wallet_data.keys())[:5]
        if len(wallet_data) > 5:
            available_names.append("...")
        
        error_content = f"❌ **Wallet name(s) not found:** {', '.join(not_found)}\n\n"
        error_content += f"**Available wallet names:**\n{', '.join(available_names)}\n\n"
        error_content += "Use **/list** to see all wallets or provide TRC20/ERC20 addresses directly."
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Wallets Not Found"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": error_content
                    }
                }
            ]
        }

    def _create_fetch_error_card(self) -> dict:
        """Create balance fetch error card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Balance Fetch Failed"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "❌ **Unable to fetch any wallet balances.**\n\nPlease check your network connection and try again."
                    }
                }
            ]
        }

    def _create_timeout_error_card(self) -> dict:
        """Create timeout error card."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "⏰ Request Timeout"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⏰ **Request timed out after 30 seconds.**\n\nPlease try again. If the issue persists, there may be network connectivity problems."
                    }
                }
            ]
        }

    async def _send_disabled_message(self, context: Any):
        """Send disabled message."""
        disabled_card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ Command Disabled"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "🚫 **Check command is currently disabled.**\n\nPlease contact an administrator."
                    }
                }
            ]
        }
        
        await context.topic_manager.send_command_response(disabled_card, msg_type="interactive")