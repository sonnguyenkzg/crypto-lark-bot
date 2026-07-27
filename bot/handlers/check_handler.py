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
    RECON_CONCURRENCY = 8
    RECON_TOTAL_BUDGET = 90.0

    def __init__(self):
        self.name = "check"
        self.description = "Check wallet balances (all wallets or specific ones)"
        self.usage = '/check [optional: "wallet1" "wallet2"]'
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
                success, batch_id = self.sheets_logger.log_balance_check(balances, wallets_to_check, check_type="manual")
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

    def _filter_roster(self, items, groups, names, name_key="wallet"):
        """Group + exact/fuzzy name filter, SHARED by both historical paths:
        - build_historical_view calls it against snapshot entries (name_key='wallet_name')
        - the reconstruction gap-path calls it against the current roster (name_key='wallet',
          the default)
        A token that matches a company name selects that whole group; a name token is
        matched exactly first, then falls back to a fuzzy match (recorded in `fuzzy`) so a
        near-miss still resolves instead of silently returning nothing; a name with no
        match at all -> `not_found`, never silently dropped.

        Returns (selected_items, fuzzy_map, not_found_list).
        """
        selected = list(items)
        if groups:
            gl = {g.lower() for g in groups}
            selected = [v for v in selected if v.get("company", "").lower() in gl]
        fuzzy = {}
        not_found = []
        if names:
            picked = {}
            base = selected if groups else list(items)
            base_names = [v[name_key] for v in base]
            for want in names:
                exact = [v for v in base if v[name_key].lower() == want.lower()]
                if exact:
                    for v in exact:
                        picked[v["address"]] = v
                    continue
                close = resolve_fuzzy(want, base_names)
                if close:
                    fuzzy[want] = close
                    for v in base:
                        if v[name_key] in close:
                            picked[v["address"]] = v
                else:
                    not_found.append(want)
            selected = list(picked.values())
        return selected, fuzzy, not_found

    def build_historical_view(self, snapshot, current_roster, groups, names, date_str):
        """Pure: turn a snapshot + filters into rows + warnings. See interface block."""
        # 1. choose which snapshot entries to show
        selected, fuzzy, not_found = self._filter_roster(
            list(snapshot.values()), groups, names, name_key="wallet_name")
        rows = [{"name": v["wallet_name"], "company": v["company"],
                 "address": v["address"], "balance": v["balance"], "source": "snapshot"}
                for v in selected]
        # 2. completeness guard vs CURRENT roster (only when unfiltered)
        missing = []
        if not groups and not names:
            snap_addrs = {canonical_address(v["address"]) for v in snapshot.values()}
            for w in current_roster:
                if not self._existed_by(w.get("created_at"), date_str):
                    continue
                if canonical_address(w.get("address", "")) not in snap_addrs:
                    missing.append(w.get("wallet"))
        return {"rows": rows, "missing": missing, "not_found": not_found, "fuzzy": fuzzy}

    async def _handle_historical(self, context: Any, date_str: str, other_tokens: List[str],
                                  wallet_data: Dict) -> bool:
        """Route for `/check [date] ...`.

        Validates the date, classifies the remaining tokens into group/name filters,
        then either renders the DAILY_REPORT snapshot for that date (if one was logged)
        or -- on a gap day with no snapshot -- reconstructs the current roster's
        balances as of {date_str} 00:01 GMT+7 from on-chain transfer history.
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

        # Acknowledge immediately (same courtesy as the live /check path): reading the
        # sheet takes a moment and a gap date can take up to ~90s to rebuild, so the user
        # should never be left staring at silence.
        await context.topic_manager.send_command_response(
            self._create_historical_checking_card(date_str), msg_type="interactive")

        companies = sorted({info["company"] for info in wallet_data.values()})
        names_all = [info["wallet"] for info in wallet_data.values()]
        groups, names = classify_tokens(other_tokens, companies, names_all)

        # current roster (wallet_service already loaded into wallet_data)
        roster = [{"wallet": i["wallet"], "company": i["company"], "address": i["address"],
                   "chain": i.get("chain", "TRC20"), "created_at": i.get("created_at")}
                  for i in wallet_data.values()]

        # get_snapshot_for_date already catches its own errors and returns {} on failure.
        snapshot = self.sheets_logger.get_snapshot_for_date(date_str)

        if snapshot:
            view = self.build_historical_view(snapshot, roster, groups, names, date_str)
            source = f"Daily snapshot (DAILY_REPORT) — {date_str} · {len(snapshot)} wallets"
            card = self._create_historical_card(view, date_str, source, reconstructed=False)
        else:
            # Gap: no snapshot logged for this date -- reconstruct the current roster's
            # balances as of date_str 00:01 GMT+7 from on-chain transfer history.
            cutoff_ms = int(datetime.strptime(date_str + " 00:01:00", "%Y-%m-%d %H:%M:%S")
                            .replace(tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
            # Same "did this wallet exist yet" guard as the snapshot path's completeness
            # check (_existed_by): a wallet added AFTER date_str has nothing meaningful to
            # reconstruct for that date, so it's excluded here rather than fabricated.
            existing_roster = [w for w in roster if self._existed_by(w.get("created_at"), date_str)]
            targets, fuzzy, not_found = self._filter_roster(existing_roster, groups, names)
            rows, unavailable = [], []
            if targets:
                # This is the genuinely slow path (chain history per wallet) -- tell the
                # user what is happening and roughly how long it will take.
                await context.topic_manager.send_command_response(
                    self._create_rebuilding_card(date_str, len(targets)), msg_type="interactive")
                # PROD SAFETY: run reconstruction on a DEDICATED bounded thread pool -- never the
                # default executor the LIVE /check path uses -- so stale/slow gap-date threads can
                # never saturate it and starve live checks. One outer budget caps total lock-hold;
                # each transfer fetch is itself page/time-capped in balance_service so a single
                # thread can't run unbounded. Completion is tracked by task identity, so every
                # wallet lands in rows XOR unavailable exactly once.
                loop = asyncio.get_event_loop()
                recon_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.RECON_CONCURRENCY, thread_name_prefix="recon")
                try:
                    fut_to_w = {}
                    for w in targets:
                        f = loop.run_in_executor(
                            recon_pool, self.balance_service.get_balance_at,
                            w["address"], w.get("chain", "TRC20"), cutoff_ms)
                        fut_to_w[f] = w
                    done, pending = await asyncio.wait(
                        list(fut_to_w.keys()), timeout=self.RECON_TOTAL_BUDGET)
                    for f in pending:
                        f.cancel()                       # queued futures never run
                        unavailable.append(fut_to_w[f]["wallet"])
                    for f in done:
                        w = fut_to_w[f]
                        try:
                            bal = f.result()
                        except Exception as e:
                            logger.error(f"Reconstruction failed for {w['wallet']} "
                                         f"({w.get('chain', 'TRC20')}): {e}")
                            bal = None
                        if bal is None:
                            unavailable.append(w["wallet"])
                        else:
                            rows.append({"name": w["wallet"], "company": w["company"],
                                         "address": w["address"], "balance": bal,
                                         "source": "reconstructed"})
                finally:
                    recon_pool.shutdown(wait=False)      # never block the event loop
            view = {"rows": rows, "missing": [], "not_found": not_found, "fuzzy": fuzzy,
                    "unavailable": unavailable}
            source = f"Reconstructed from chain — no snapshot for {date_str}"
            card = self._create_historical_card(view, date_str, source, reconstructed=True)

        await context.topic_manager.send_command_response(card, msg_type="interactive")
        return True

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

    def _create_historical_card(self, view: Dict, date_str: str, source: str, reconstructed: bool = False) -> dict:
        """Card for `/check [date]`. REUSES the group-subtotal + grand-total table layout
        from _create_balance_table_card_with_sheets_info (built by feeding it the
        historical rows as a name->balance dict), then swaps that builder's LIVE header
        (title/time/wallet-count) for a historical one and adds completeness/fuzzy/
        unavailable notes. The "not found" note is inherited for free since we pass
        view["not_found"] straight through to the reused builder.
        """
        rows = view.get("rows", [])
        # A display name can legitimately map to TWO different addresses in a historical
        # snapshot (a wallet renamed/rotated over time -- see
        # test_same_name_different_address_both_kept in tests/test_snapshot.py), unlike the
        # live path where wallets.json keys wallets by name so this can't happen. The reused
        # builder below is keyed by display name, so a bare name->row dict would let one
        # collide-and-drop the other, silently under-reporting the total.
        #
        # Guarantee a globally UNIQUE key per row by checking against what's actually been
        # assigned so far (`key in balances`), not by reasoning about what "should" be
        # unique -- an assumption-based disambiguator (e.g. a truncated address suffix, or
        # even the full canonical address) can itself coincide with some other row's literal
        # name. Escalating against the real, growing dict is correct by construction for any
        # input: it can never silently overwrite, because a used key always gets pushed to a
        # longer, still-checked alternative. The common (unique-name) case is untouched.
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
            not_found=view.get("not_found", []), sheets_logged=False, batch_id=None)

        # The reused builder's first 3 elements are its own live-check header
        # (title/time/wallet-count); element[3] is the "hr" right after them, which we
        # keep as the separator between OUR header and its grouped-totals/detail table.
        table_elements = base_card["elements"][3:]

        header_elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "🕰️ **Historical Wallet Balance Check**"}
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"📅 **Date:** {date_str}"}
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"ℹ️ **Source:** {source}"}
            },
        ]

        if view.get("missing"):
            header_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "⚠️ **Completeness warning — expected but missing from this "
                                f"snapshot:** {', '.join(view['missing'])}"
                }
            })

        if view.get("fuzzy"):
            fuzzy_lines = "\n".join(
                f'🔍 "{want}" ≈ closest to "{", ".join(matches)}"'
                for want, matches in view["fuzzy"].items()
            )
            header_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": fuzzy_lines}
            })

        if view.get("unavailable"):
            header_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "🚫 **Unavailable (reconstruction failed, excluded from "
                                f"total):** {', '.join(view['unavailable'])}"
                }
            })

        base_card["elements"] = header_elements + table_elements
        grand_total = sum(balances.values()) if balances else Decimal("0")
        base_card["header"] = {
            "template": "purple" if reconstructed else "blue",
            "title": {
                "tag": "plain_text",
                "content": "🕰️ Historical Wallet Balance Check"
            },
            "subtitle": {
                "tag": "plain_text",
                "content": f"{date_str} · Total: {grand_total:,.2f} USDT"
            }
        }
        return base_card

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
                                   f"Wrap the date (and any filter) in brackets, e.g. `/check [{date_str}]` "
                                   f"for a date on its own, or `/check [{date_str}] [KZP]` to also filter "
                                   "by company or wallet name."
                    }
                }
            ]
        }

    def _create_historical_checking_card(self, date_str: str) -> dict:
        """Acknowledge a `/check [date]` right away, before the sheet/chain lookup."""
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
                        "content": f"🔄 **Looking up balances for {date_str}...**\n\n"
                                   "Reading the daily record for that date. This may take a few seconds."
                    }
                }
            ]
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
                        "content": f"🔄 **No daily record was saved for {date_str}, so I'm working the "
                                   f"balances out from the blockchain for {wallet_count} {wallet_word}.**\n\n"
                                   "This is slower than reading a saved record — it can take up to about "
                                   "90 seconds. Any wallet that can't be worked out in time will be listed "
                                   "as \"unavailable\" rather than left out."
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