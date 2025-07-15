#!/usr/bin/env python3
"""
Lark Bot Handler Registry Module
Routes commands to appropriate handlers and manages command execution
FIXED: Unknown command now shows as rich card instead of plain text
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional, Callable, List
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class CommandContext:
    message: Any
    command: str
    args: List[str]
    sender_id: str
    chat_id: str
    thread_id: Optional[str]
    topic_manager: Any
    api_client: Any
    config: Any

class BaseHandler(ABC):
    def __init__(self, name: str, description: str, usage: str = ""):
        self.name = name
        self.description = description
        self.usage = usage
        self.aliases = []

    @abstractmethod
    async def handle(self, context: CommandContext) -> bool:
        pass

    def add_alias(self, alias: str) -> 'BaseHandler':
        self.aliases.append(alias)
        return self

    def get_help_text(self) -> str:
        help_text = f"**/{self.name}**"
        if self.aliases:
            help_text += f" (aliases: {', '.join(self.aliases)})"
        help_text += f"\n{self.description}"
        if self.usage:
            help_text += f"\n**Usage:** {self.usage}"
        return help_text

class HandlerRegistry:
    def __init__(self, config_class):
        self.config = config_class
        self.handlers: Dict[str, BaseHandler] = {}
        self.aliases: Dict[str, str] = {}
        self.middleware: List[Callable] = []

    def register(self, handler: BaseHandler) -> None:
        command_name = handler.name.lower()
        if command_name in self.handlers:
            logger.warning(f"⚠️ Overwriting existing handler for command: {command_name}")
        self.handlers[command_name] = handler
        for alias in handler.aliases:
            alias_lower = alias.lower()
            if alias_lower in self.aliases:
                logger.warning(f"⚠️ Overwriting existing alias: {alias_lower}")
            self.aliases[alias_lower] = command_name
        logger.info(f"✅ Registered handler: {command_name}")

    def unregister(self, command_name: str) -> bool:
        command_name = command_name.lower()
        if command_name not in self.handlers:
            return False
        handler = self.handlers[command_name]
        del self.handlers[command_name]
        for alias in handler.aliases:
            alias_lower = alias.lower()
            if alias_lower in self.aliases:
                del self.aliases[alias_lower]
        logger.info(f"✅ Unregistered handler: {command_name}")
        return True

    def get_handler(self, command_name: str) -> Optional[BaseHandler]:
        command_name = command_name.lower()
        if command_name in self.handlers:
            return self.handlers[command_name]
        if command_name in self.aliases:
            actual_command = self.aliases[command_name]
            return self.handlers.get(actual_command)
        return None

    def list_commands(self) -> List[str]:
        return list(self.handlers.keys())

    def add_middleware(self, middleware_func: Callable) -> None:
        self.middleware.append(middleware_func)
        logger.info(f"✅ Added middleware: {middleware_func.__name__}")

    async def execute_command(self, context: CommandContext) -> bool:
        try:
            for middleware in self.middleware:
                try:
                    should_continue = await middleware(context)
                    if not should_continue:
                        logger.info(f"🚫 Middleware blocked command: {context.command}")
                        return False
                except Exception as e:
                    logger.error(f"❌ Middleware error: {e}")
                    return False
            handler = self.get_handler(context.command)
            if not handler:
                await self._send_unknown_command_message(context)
                return False
            logger.info(f"🎯 Executing command: {context.command} (user: {context.sender_id})")
            start_time = datetime.now()
            success = await handler.handle(context)
            execution_time = (datetime.now() - start_time).total_seconds()
            if success:
                logger.info(f"✅ Command completed: {context.command} ({execution_time:.2f}s)")
            else:
                logger.warning(f"⚠️ Command failed: {context.command}")
            return success
        except Exception as e:
            logger.error(f"❌ Error executing command {context.command}: {e}")
            await self._send_error_message(context, str(e))
            return False

    def _create_unknown_command_card(self, command: str, available_commands: List[str]) -> dict:
        """Create rich card for unknown command error."""
        commands_list = ", ".join([f"/{cmd}" for cmd in sorted(available_commands)])
        
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "❓ Unknown Command"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"❓ **Unknown command: /{command}**"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Available commands:** {commands_list}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Use **/help** for detailed information."
                    }
                }
            ]
        }

    def _create_error_card(self, command: str, error: str) -> dict:
        """Create rich card for command execution errors."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "💥 Command Error"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "💥 **Command Error**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Command:** /{command}\n**Error:** {error}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Please try again or contact support if the issue persists."
                    }
                }
            ]
        }

    def _create_authorization_error_card(self) -> dict:
        """Create rich card for authorization errors."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "🚫 Access Denied"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "🚫 **Access Denied**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "You are not authorized to use this bot."
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Please contact an administrator for access."
                    }
                }
            ]
        }

    def _create_rate_limit_card(self, max_commands: int, time_window: int) -> dict:
        """Create rich card for rate limit errors."""
        return {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "orange",
                "title": {
                    "tag": "plain_text",
                    "content": "⏰ Rate Limit Exceeded"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⏰ **Rate Limit Exceeded**"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"Maximum {max_commands} commands per {time_window} seconds."
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Please wait before sending more commands."
                    }
                }
            ]
        }

    async def _send_unknown_command_message(self, context: CommandContext) -> None:
        """FIXED: Send unknown command message as rich card instead of plain text."""
        try:
            available_commands = self.list_commands()
            unknown_card = self._create_unknown_command_card(context.command, available_commands)
            await context.topic_manager.send_command_response(unknown_card, msg_type="interactive")
        except Exception as e:
            logger.error(f"❌ Error sending unknown command message: {e}")
            # Fallback to plain text if card fails
            try:
                available_commands = ", ".join([f"/{cmd}" for cmd in sorted(self.list_commands())])
                error_msg = (
                    f"❓ **Unknown command: /{context.command}**\n\n"
                    f"Available commands: {available_commands}\n\n"
                    f"Use `/help` for detailed information."
                )
                await context.topic_manager.send_command_response(error_msg)
            except Exception as fallback_error:
                logger.error(f"❌ Error sending fallback message: {fallback_error}")

    async def _send_error_message(self, context: CommandContext, error: str) -> None:
        """FIXED: Send error message as rich card instead of plain text."""
        try:
            error_card = self._create_error_card(context.command, error)
            await context.topic_manager.send_command_response(error_card, msg_type="interactive")
        except Exception as e:
            logger.error(f"❌ Error sending error card: {e}")
            # Fallback to plain text if card fails
            try:
                error_msg = f"💥 **Command Error**\nCommand: /{context.command}\nError: {error}"
                await context.topic_manager.send_command_response(error_msg)
            except Exception as fallback_error:
                logger.error(f"❌ Error sending fallback error message: {fallback_error}")

    def get_help_text(self, command_name: Optional[str] = None) -> str:
        if command_name:
            handler = self.get_handler(command_name)
            if handler:
                return handler.get_help_text()
            else:
                return f"❓ Unknown command: /{command_name}"
        help_sections = ["🤖 **Available Commands:**\n"]
        for command_name in sorted(self.list_commands()):
            handler = self.handlers[command_name]
            help_sections.append(handler.get_help_text())
            help_sections.append("")
        return "\n".join(help_sections)

# FIXED: Authorization middleware now uses rich cards
async def authorization_middleware(context: CommandContext) -> bool:
    # NEW: Use LARK_AUTHORIZED_USERS instead of ALLOWED_USERS
    allowed_ids = os.getenv("LARK_AUTHORIZED_USERS", "")
    allowed_set = set(uid.strip() for uid in allowed_ids.split(",") if uid.strip())
    
    # NEW: If no users configured, allow all (development mode)
    if not allowed_set:
        logger.info(f"🔓 No authorization configured - allowing user {context.sender_id}")
        return True
    
    if context.sender_id not in allowed_set:
        logger.warning(f"🚫 Unauthorized command attempt: {context.command} by {context.sender_id}")
        try:
            # Create authorization error card with Open ID shown
            auth_error_card = {
                "config": {
                    "wide_screen_mode": True,
                    "enable_forward": False
                },
                "header": {
                    "template": "red",
                    "title": {
                        "tag": "plain_text",
                        "content": "🚫 Access Denied"
                    }
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "🚫 **Access Denied**"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"🆔 **Your Open ID:** `{context.sender_id}`"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "📞 **Contact your administrator with your Open ID to request access.**"
                        }
                    }
                ]
            }
            await context.topic_manager.send_command_response(auth_error_card, msg_type="interactive")
        except Exception as e:
            logger.error(f"❌ Error sending authorization error: {e}")
        return False
    
    logger.info(f"✅ User {context.sender_id} authorized for /{context.command}")
    return True

# Optional: Rate limiter middleware with rich cards
class RateLimiter:
    def __init__(self, max_commands: int = 10, time_window: int = 60):
        self.max_commands = max_commands
        self.time_window = time_window
        self.user_commands: Dict[str, List[datetime]] = {}

    async def rate_limit_middleware(self, context: CommandContext) -> bool:
        user_id = context.sender_id
        now = datetime.now()
        if user_id not in self.user_commands:
            self.user_commands[user_id] = []
        cutoff_time = now.timestamp() - self.time_window
        self.user_commands[user_id] = [
            cmd_time for cmd_time in self.user_commands[user_id]
            if cmd_time.timestamp() > cutoff_time
        ]
        if len(self.user_commands[user_id]) >= self.max_commands:
            logger.warning(f"🚫 Rate limit exceeded: {context.command} by {user_id}")
            try:
                # FIXED: Rate limit error as rich card
                rate_limit_card = {
                    "config": {
                        "wide_screen_mode": True,
                        "enable_forward": False
                    },
                    "header": {
                        "template": "orange",
                        "title": {
                            "tag": "plain_text",
                            "content": "⏰ Rate Limit Exceeded"
                        }
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": "⏰ **Rate Limit Exceeded**"
                            }
                        },
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"Maximum {self.max_commands} commands per {self.time_window} seconds."
                            }
                        },
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": "Please wait before sending more commands."
                            }
                        }
                    ]
                }
                await context.topic_manager.send_command_response(rate_limit_card, msg_type="interactive")
            except Exception as e:
                logger.error(f"❌ Error sending rate limit error: {e}")
            return False
        self.user_commands[user_id].append(now)
        return True