#!/usr/bin/env python3
"""
Lark Bot Help Handler - Telegram-style UI
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

class HelpHandler:
    def __init__(self):
        self.name = "help"
        self.description = "Show available commands and their descriptions"
        self.usage = "/help [command]"
        self.aliases = ["h", "?"]
        self.enabled = True

    async def handle(self, context: Any) -> bool:
        try:
            if not self.enabled:
                await self._send_disabled_message(context)
                return False

            
            message = self._get_help_text()
            await context.topic_manager.send_command_response(message)

            logger.info(f"✅ Help command completed for user: {context.sender_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error in help command: {e}")
            await context.topic_manager.send_error_message(f"❌ Error: {e}")
            return False

    def _get_help_text(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""📋 __Available Commands:__
        **Wallet Management:**
        • `/start` – Start the bot and check connection  
        • `/help` – Show available commands and their descriptions  
        • `/list` – Show all configured wallets  
        • `/add "company" "wallet" "address"` – Add new wallet  
        • `/remove "wallet_name"` – Remove wallet  
        • `/check` – Check all wallet balances  
        • `/check "wallet_name"` – Check specific wallet balance  
        • `/check "wallet1" "wallet2"` – Check multiple specific wallets  

        **Examples:**
        • `/add "KZP" "KZP WDB2" "TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWY4KS"`  
        • `/remove "KZP WDB2"`  
        • `/list`  
        • `/check`  
        • `/check "KZP 96G1"`  
        • `/check "KZP 96G1" "KZP WDB2"`  

        **Notes:**
        • All arguments must be in quotes  
        • TRC20 addresses start with `T` (34 characters)  
        • Balance reports sent via scheduled messages at midnight GMT+7  
        • Only authorized team members can use commands

        🕒 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """

    async def _send_disabled_message(self, context: Any):
        await context.topic_manager.send_command_response("🚫 This command is currently disabled.")

    async def _send_unauthorized_message(self, context: Any):
        await context.topic_manager.send_command_response(
            "**🚫 Access Denied**\nYou are not authorized to use this bot.\n\n"
            f"Your ID: `{context.sender_id}`"
        )
