#!/usr/bin/env python3
"""
Enhanced Topic Manager with proper interactive card support
"""

import logging
import json
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

class TopicType(Enum):
    """Enumeration of available topics."""
    QUICKGUIDE = "quickguide"
    COMMANDS = "commands"
    DAILYREPORT = "dailyreport"

class LarkTopicManager:
    """
    Enhanced Topic Manager with proper card message support.
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
        
        # Initialize attributes for direct API calls
        commands_topic = self.topic_config.get("commands", {})
        self.commands_topic_id = commands_topic.get("chat_id", "")
        self.reply_to_message_id = commands_topic.get("message_id", "")
        
        # Log the configuration for debugging
        logger.info(f"🔧 TopicManager initialized:")
        logger.info(f"   Commands topic ID: {self.commands_topic_id}")
        logger.info(f"   Reply message ID: {self.reply_to_message_id}")
        
    def get_topic_info(self, topic_type: TopicType) -> Dict[str, str]:
        """Get topic configuration information."""
        topic_name = topic_type.value
        topic_info = self.topic_config.get(topic_name, {})
        
        if not topic_info.get("thread_id") or not topic_info.get("message_id"):
            logger.warning(f"⚠️ Incomplete configuration for topic: {topic_name}")
            
        return topic_info
    
    async def send_to_topic(self, topic_type: TopicType, message: str, msg_type: str = "text") -> bool:
        """Send a message to a specific topic using reply mechanism."""
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
    
    async def send_to_commands(self, content, msg_type="text"):
        """
        Enhanced send_to_commands with proper card support.
        
        Args:
            content: Message content (str for text, dict for cards)
            msg_type: Message type ("text" or "interactive")
        """
        try:
            if msg_type == "interactive" and isinstance(content, dict):
                # Send interactive card using the API client's reply method
                # Convert card dict to JSON string
                card_json = json.dumps(content)
                
                # Use the API client to send the card
                topic_info = self.get_topic_info(TopicType.COMMANDS)
                message_id = topic_info.get("message_id")
                
                if not message_id:
                    logger.error("❌ No message ID configured for commands topic")
                    return False
                
                response = await self.api_client.reply_to_message(
                    message_id, 
                    card_json, 
                    "interactive"
                )
                
                if response:
                    logger.info("✅ Interactive card sent to commands topic")
                    return True
                else:
                    logger.error("❌ Failed to send interactive card")
                    return False
                    
            else:
                # Handle text messages
                if isinstance(content, dict):
                    # Convert dict to text representation as fallback
                    content = f"📋 **Message Content**\n{str(content)}"
                
                return await self.send_to_topic(TopicType.COMMANDS, str(content), "text")
                
        except Exception as e:
            logger.error(f"❌ Error in send_to_commands: {e}")
            # Fallback to text message
            if isinstance(content, str):
                return await self.send_to_topic(TopicType.COMMANDS, content, "text")
            elif isinstance(content, dict):
                fallback_text = f"📋 **Card Message**\n{json.dumps(content, indent=2)}"
                return await self.send_to_topic(TopicType.COMMANDS, fallback_text, "text")
            return False

    async def send_to_dailyreport(self, message: str) -> bool:
        """Send message to daily report topic."""
        return await self.send_to_topic(TopicType.DAILYREPORT, message)
    
    def is_topic_message(self, message_thread_id: Optional[str], topic_type: TopicType) -> bool:
        """Check if a message belongs to a specific topic."""
        if not message_thread_id:
            return False
            
        topic_info = self.get_topic_info(topic_type)
        expected_thread_id = topic_info.get("thread_id")
        
        return message_thread_id == expected_thread_id
    
    def get_topic_by_thread_id(self, thread_id: str) -> Optional[TopicType]:
        """Get topic type by thread ID."""
        for topic_type in TopicType:
            topic_info = self.get_topic_info(topic_type)
            if topic_info.get("thread_id") == thread_id:
                return topic_type
        
        return None
    
    async def send_startup_message(self) -> bool:
        """Send bot startup message with professional formatting."""
        startup_card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "template": "green",
                "title": {
                    "tag": "plain_text",
                    "content": "🤖 Crypto Wallet Monitor Started"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📅 Started at:** {self._get_current_time()}\n**🎯 Status:** Ready to monitor crypto wallets\n**💡 Next step:** Use `/help` in #commands for available commands"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "content": "📋 View Commands",
                                "tag": "plain_text"
                            },
                            "type": "primary",
                            "value": {
                                "action": "help"
                            }
                        }
                    ]
                }
            ]
        }
        
        try:
            # Send as interactive card to daily report
            success = await self.send_to_dailyreport(json.dumps(startup_card))
            if success:
                logger.info("✅ Startup message sent to daily report topic")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending startup message: {e}")
            return False
    
    async def send_daily_report(self, report_content: str) -> bool:
        """Send daily crypto report to daily report topic."""
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
        Send command response to commands topic with enhanced formatting support.

        Args:
            response: Message content (str, dict for cards)
            msg_type: Message type ("text", "interactive", etc.)

        Returns:
            True if response sent successfully
        """
        try:
            success = await self.send_to_commands(response, msg_type)
            if success:
                logger.info(f"✅ Command response sent (type: {msg_type})")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending command response: {e}")
            return False

    async def send_error_message(self, error_msg: str, topic_type: TopicType = TopicType.COMMANDS) -> bool:
        """Send error message with professional formatting."""
        error_card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": False
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "❌ Error"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Error:** {error_msg}"
                    }
                }
            ]
        }
        
        try:
            if topic_type == TopicType.COMMANDS:
                success = await self.send_to_commands(error_card, "interactive")
            else:
                success = await self.send_to_topic(topic_type, json.dumps(error_card), "interactive")
                
            if success:
                logger.info(f"✅ Error message sent to {topic_type.value}")
            return success
        except Exception as e:
            logger.error(f"❌ Error sending error message: {e}")
            # Fallback to text
            formatted_error = f"❌ **Error**: {error_msg}"
            return await self.send_to_topic(topic_type, formatted_error, "text")
    
    def validate_topic_configuration(self) -> Dict[str, bool]:
        """Validate that all topics are properly configured."""
        validation_results = {}
        
        for topic_type in TopicType:
            topic_name = topic_type.value
            topic_info = self.get_topic_info(topic_type)
            
            has_thread_id = bool(topic_info.get("thread_id"))
            has_message_id = bool(topic_info.get("message_id"))
            has_chat_id = bool(topic_info.get("chat_id"))
            
            is_valid = has_thread_id and has_message_id and has_chat_id
            validation_results[topic_name] = is_valid
            
            if not is_valid:
                missing = []
                if not has_thread_id:
                    missing.append("thread_id")
                if not has_message_id:
                    missing.append("message_id")
                if not has_chat_id:
                    missing.append("chat_id")
                logger.warning(f"⚠️ Topic {topic_name} missing: {', '.join(missing)}")
        
        return validation_results
    
    def get_configuration_summary(self) -> str:
        """Get summary of topic configuration."""
        summary = ["🎯 Topic Manager Configuration:"]
        
        for topic_type in TopicType:
            topic_name = topic_type.value
            topic_info = self.get_topic_info(topic_type)
            
            thread_id = topic_info.get("thread_id", "Not configured")
            message_id = topic_info.get("message_id", "Not configured")
            chat_id = topic_info.get("chat_id", "Not configured")
            
            # Truncate IDs for display
            thread_display = thread_id[:15] + "..." if len(thread_id) > 15 else thread_id
            message_display = message_id[:15] + "..." if len(message_id) > 15 else message_id
            chat_display = chat_id[:15] + "..." if len(chat_id) > 15 else chat_id
            
            summary.append(f"  📌 {topic_name.upper()}:")
            summary.append(f"     Thread ID:  {thread_display}")
            summary.append(f"     Message ID: {message_display}")
            summary.append(f"     Chat ID:    {chat_display}")
        
        return "\n".join(summary)
    
    def _get_current_time(self) -> str:
        """Get current time as formatted string."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")