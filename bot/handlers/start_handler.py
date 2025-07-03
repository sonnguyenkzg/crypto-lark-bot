#!/usr/bin/env python3
"""
Lark Bot Start Handler
Handles the /start command - sends welcome and onboarding info
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class StartHandler:
    def __init__(self):
        self.name = "start"
        self.description = "Start the bot and show welcome message"
        self.usage = "/start"
        self.aliases = ["begin", "init"]
        self.enabled = True
        self.call_count = 0
        self.error_count = 0
        self.last_used = None

    def add_alias(self, alias: str):
        self.aliases.append(alias.lower())
        return self

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        return self

    def get_help_text(self) -> str:
        alias_str = ", ".join([f"/{a}" for a in self.aliases])
        return (
            f"**/{self.name}** (aliases: {alias_str})\n"
            f"{self.description}\n"
            f"**Usage:** {self.usage}"
        )

    async def handle(self, context):
        try:
            if not self.enabled:
                await context.topic_manager.send_command_response("🚫 This command is currently disabled.")
                return False

            self.call_count += 1
            self.last_used = datetime.now()

            logger.info(f"🚀 Running /start command for user {context.sender_id}")

            welcome_message = "\n".join([
                "👋 **Welcome to Crypto Wallet Monitor Bot (Lark Edition)**",
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "This bot helps you monitor TRON-based wallets in real-time.",
                "",
                "📚 Use `/help` to see all commands.",
                "➕ Try `/add` to register a wallet.",
                "📊 Try `/check` to see balances.",
                "",
                "💡 Commands must be sent in the #commands topic."
            ])

            await context.topic_manager.send_command_response(welcome_message)
            return True

        except Exception as e:
            self.error_count += 1
            logger.error(f"❌ Error in /start command: {e}")
            await context.topic_manager.send_error_message(
                f"❌ Failed to run /start\nError: {str(e)}"
            )
            return False
