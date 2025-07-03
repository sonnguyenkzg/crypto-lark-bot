#!/usr/bin/env python3
"""
Lark Topic Manager Module - FIXED VERSION
Handles topic-specific operations and messaging using reply-based approach
"""

import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from bot.services.lark_api_client import send_message_card, send_text_message

logger = logging.getLogger(__name__)

class TopicType(Enum):
    """Enumeration of available topics."""
    QUICKGUIDE = "quickguide"
    COMMANDS = "commands"
    DAILYREPORT = "dailyreport"

class LarkTopicManager:
    """
    Manages topic-specific operations for Lark bot.
    Uses reply-based messaging to target specific topics.
    """
    
    def __init__(self, api_client, config_class):
        """
        Initialize topic manager.
        
        Args:
            api_client: LarkAPIClient instance
            config_class: Config class with topic configuration
        """
        self.api_client = api_client
        self.config = config_class
        self.topic_config = config_class.get_topic_config()
        
        # Initialize missing attributes that are used in send_to_commands
        commands_topic = self.topic_config.get("commands", {})
        self.commands_topic_id = commands_topic.get("chat_id", "")
        self.reply_to_message_id = commands_topic.get("message_id", "")
        
        # Log the configuration for debugging
        logger.info(f"🔧 TopicManager initialized:")
        logger.info(f"   Commands topic ID: {self.commands_topic_id}")
        logger.info(f"   Reply message ID: {self.reply_to_message_id}")
        
    def get_topic_info(self, topic_type: TopicType) -> Dict[str, str]:
        """
        Get topic configuration information.
        
        Args:
            topic_type: Type of topic to get info for
            
        Returns:
            Dictionary with thread_id and message_id
        """
        topic_name = topic_type.value
        topic_info = self.topic_config.get(topic_name, {})
        
        if not topic_info.get("thread_id") or not topic_info.get("message_id"):
            logger.warning(f"⚠️ Incomplete configuration for topic: {topic_name}")
            
        return topic_info
    
    async def send_to_topic(self, topic_type: TopicType, message: str, msg_type: str = "text") -> bool:
        """
        Send a message to a specific topic using reply mechanism.
        
        Args:
            topic_type: Target topic type
            message: Message content to send
            msg_type: Message type (text, rich_text, etc.)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            topic_info = self.get_topic_info(topic_type)
            message_id = topic_info.get("message_id")
            
            if not message_id:
                logger.error(f"❌ No message ID configured for topic: {topic_type.value}")
                return False
            
            # Use reply API to target the topic
            response = await self.api_client.reply_to_message(message_id, message, msg_type)
            
            if response:
                logger.info(f"✅ Message sent to topic {topic_type.value}")
                return True
            else:
                logger.error(f"❌ Failed to send message to topic {topic_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending to topic {topic_type.value}: {e}")
            return False
    
    async def send_to_quickguide(self, message: str) -> bool:
        """Send message to quickguide topic."""
        return await self.send_to_topic(TopicType.QUICKGUIDE, message)
    
# Replace this method in your LarkTopicManager class

    async def send_to_commands(self, content, msg_type="text"):
        """
        Send message to commands topic - QUICK FIX
        """
        try:
            # Just use the working send_to_topic method for everything
            if isinstance(content, str):
                return await self.send_to_topic(TopicType.COMMANDS, content, msg_type)
            else:
                # Convert non-string content to string
                return await self.send_to_topic(TopicType.COMMANDS, str(content), "text")
                
        except Exception as e:
            logger.error(f"❌ Error in send_to_commands: {e}")
            return False
        
    async def send_to_dailyreport(self, message: str) -> bool:
        """Send message to daily report topic."""
        return await self.send_to_topic(TopicType.DAILYREPORT, message)
    
    def is_topic_message(self, message_thread_id: Optional[str], topic_type: TopicType) -> bool:
        """
        Check if a message belongs to a specific topic.
        
        Args:
            message_thread_id: Thread ID from the message
            topic_type: Topic type to check against
            
        Returns:
            True if message is from the specified topic
        """
        if not message_thread_id:
            return False
            
        topic_info = self.get_topic_info(topic_type)
        expected_thread_id = topic_info.get("thread_id")
        
        return message_thread_id == expected_thread_id
    
    def get_topic_by_thread_id(self, thread_id: str) -> Optional[TopicType]:
        """
        Get topic type by thread ID.
        
        Args:
            thread_id: Thread ID to look up
            
        Returns:
            TopicType if found, None otherwise
        """
        for topic_type in TopicType:
            topic_info = self.get_topic_info(topic_type)
            if topic_info.get("thread_id") == thread_id:
                return topic_type
        
        return None
    
    async def send_startup_message(self) -> bool:
        """
        Send bot startup message to daily report topic.
        
        Returns:
            True if message sent successfully
        """
        startup_message = (
            "🤖 **Lark Crypto Bot Started**\n"
            f"📅 Started at: {self._get_current_time()}\n"
            "🎯 Ready to monitor crypto wallets\n"
            "💡 Use `/help` in #commands for available commands"
        )
        
        try:
            success = await self.send_to_dailyreport(startup_message)
            if success:
                logger.info("✅ Startup message sent to daily report topic")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending startup message: {e}")
            return False
    
    async def send_daily_report(self, report_content: str) -> bool:
        """
        Send daily crypto report to daily report topic.
        
        Args:
            report_content: Formatted report content
            
        Returns:
            True if report sent successfully
        """
        try:
            success = await self.send_to_dailyreport(report_content)
            if success:
                logger.info("✅ Daily report sent to daily report topic")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending daily report: {e}")
            return False
    
    async def send_command_response(self, response: Any, msg_type: str = "text") -> bool:
        """
        Send command response to commands topic.

        Args:
            response: Message content (str or dict)
            msg_type: Message type ("text", "interactive", etc.)

        Returns:
            True if response sent successfully
        """
        try:
            success = await self.send_to_commands(response, msg_type)
            if success:
                logger.info("✅ Command response sent")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending command response: {e}")
            return False

    async def send_error_message(self, error_msg: str, topic_type: TopicType = TopicType.COMMANDS) -> bool:
        """
        Send error message to specified topic.
        
        Args:
            error_msg: Error message content
            topic_type: Target topic (defaults to commands)
            
        Returns:
            True if error message sent successfully
        """
        formatted_error = f"❌ **Error**: {error_msg}"
        
        try:
            success = await self.send_to_topic(topic_type, formatted_error)
            if success:
                logger.info(f"✅ Error message sent to {topic_type.value}")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending error message: {e}")
            return False
    
    def validate_topic_configuration(self) -> Dict[str, bool]:
        """
        Validate that all topics are properly configured.
        
        Returns:
            Dictionary mapping topic names to their configuration status
        """
        validation_results = {}
        
        for topic_type in TopicType:
            topic_name = topic_type.value
            topic_info = self.get_topic_info(topic_type)
            
            has_thread_id = bool(topic_info.get("thread_id"))
            has_message_id = bool(topic_info.get("message_id"))
            
            is_valid = has_thread_id and has_message_id
            validation_results[topic_name] = is_valid
            
            if not is_valid:
                missing = []
                if not has_thread_id:
                    missing.append("thread_id")
                if not has_message_id:
                    missing.append("message_id")
                logger.warning(f"⚠️ Topic {topic_name} missing: {', '.join(missing)}")
        
        return validation_results
    
    def get_configuration_summary(self) -> str:
        """
        Get summary of topic configuration.
        
        Returns:
            Formatted configuration summary
        """
        summary = ["🎯 Topic Manager Configuration:"]
        
        for topic_type in TopicType:
            topic_name = topic_type.value
            topic_info = self.get_topic_info(topic_type)
            
            thread_id = topic_info.get("thread_id", "Not configured")
            message_id = topic_info.get("message_id", "Not configured")
            
            # Truncate IDs for display
            thread_display = thread_id[:15] + "..." if len(thread_id) > 15 else thread_id
            message_display = message_id[:15] + "..." if len(message_id) > 15 else message_id
            
            summary.append(f"  📌 {topic_name.upper()}:")
            summary.append(f"     Thread ID:  {thread_display}")
            summary.append(f"     Message ID: {message_display}")
        
        return "\n".join(summary)
    
    def _get_current_time(self) -> str:
        """Get current time as formatted string."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")