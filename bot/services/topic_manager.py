#!/usr/bin/env python3
"""
Lark Topic Manager Module
Handles topic-specific operations and messaging using reply-based approach
"""

import logging
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
    
    async def send_to_commands(self, message: str) -> bool:
        """Send message to commands topic.""" 
        return await self.send_to_topic(TopicType.COMMANDS, message)
    
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
    
    async def send_command_response(self, response: str) -> bool:
        """
        Send command response to commands topic.
        
        Args:
            response: Response message content
            
        Returns:
            True if response sent successfully
        """
        try:
            success = await self.send_to_commands(response)
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

# Mock classes for testing
class MockAPIClient:
    """Mock API client for testing."""
    
    def __init__(self):
        self.sent_messages = []
    
    async def reply_to_message(self, message_id: str, content: str, msg_type: str = "text"):
        """Mock reply to message."""
        self.sent_messages.append({
            "message_id": message_id,
            "content": content,
            "msg_type": msg_type
        })
        return {"code": 0, "msg": "success"}

class MockConfig:
    """Mock config class for testing."""
    
    @classmethod
    def get_topic_config(cls):
        """Mock topic configuration."""
        return {
            "quickguide": {
                "thread_id": "omt_quickguide_123",
                "message_id": "om_quickguide_msg_123"
            },
            "commands": {
                "thread_id": "omt_commands_123", 
                "message_id": "om_commands_msg_123"
            },
            "dailyreport": {
                "thread_id": "omt_dailyreport_123",
                "message_id": "om_dailyreport_msg_123"
            }
        }

# Testing functions
async def test_topic_messaging():
    """Test topic messaging functionality."""
    print("🧪 Testing Topic Messaging...")
    
    try:
        # Setup
        mock_api = MockAPIClient()
        topic_manager = LarkTopicManager(mock_api, MockConfig)
        
        # Test sending to different topics
        await topic_manager.send_to_quickguide("Test quickguide message")
        await topic_manager.send_to_commands("Test command response")
        await topic_manager.send_to_dailyreport("Test daily report")
        
        # Verify messages were sent
        assert len(mock_api.sent_messages) == 3
        
        # Check message targeting
        assert mock_api.sent_messages[0]["message_id"] == "om_quickguide_msg_123"
        assert mock_api.sent_messages[1]["message_id"] == "om_commands_msg_123"
        assert mock_api.sent_messages[2]["message_id"] == "om_dailyreport_msg_123"
        
        print("✅ Topic messaging test passed")
        return True
        
    except Exception as e:
        print(f"❌ Topic messaging test failed: {e}")
        return False

async def test_topic_identification():
    """Test topic identification by thread ID."""
    print("🧪 Testing Topic Identification...")
    
    try:
        topic_manager = LarkTopicManager(None, MockConfig)
        
        # Test topic identification
        assert topic_manager.is_topic_message("omt_commands_123", TopicType.COMMANDS)
        assert not topic_manager.is_topic_message("omt_commands_123", TopicType.DAILYREPORT)
        assert not topic_manager.is_topic_message(None, TopicType.COMMANDS)
        
        # Test reverse lookup
        assert topic_manager.get_topic_by_thread_id("omt_commands_123") == TopicType.COMMANDS
        assert topic_manager.get_topic_by_thread_id("omt_dailyreport_123") == TopicType.DAILYREPORT
        assert topic_manager.get_topic_by_thread_id("unknown_thread") is None
        
        print("✅ Topic identification test passed")
        return True
        
    except Exception as e:
        print(f"❌ Topic identification test failed: {e}")
        return False

def test_configuration_validation():
    """Test configuration validation."""
    print("🧪 Testing Configuration Validation...")
    
    try:
        topic_manager = LarkTopicManager(None, MockConfig)
        
        # Test validation
        validation_results = topic_manager.validate_topic_configuration()
        
        # All topics should be valid in mock config
        assert all(validation_results.values())
        assert len(validation_results) == 3
        
        # Test configuration summary
        summary = topic_manager.get_configuration_summary()
        assert "QUICKGUIDE" in summary
        assert "COMMANDS" in summary
        assert "DAILYREPORT" in summary
        
        print("✅ Configuration validation test passed")
        return True
        
    except Exception as e:
        print(f"❌ Configuration validation test failed: {e}")
        return False

async def test_specialized_messages():
    """Test specialized message functions."""
    print("🧪 Testing Specialized Messages...")
    
    try:
        mock_api = MockAPIClient()
        topic_manager = LarkTopicManager(mock_api, MockConfig)
        
        # Test startup message
        await topic_manager.send_startup_message()
        
        # Test daily report
        await topic_manager.send_daily_report("Test daily report content")
        
        # Test command response
        await topic_manager.send_command_response("Test command response")
        
        # Test error message
        await topic_manager.send_error_message("Test error message")
        
        # Verify all messages sent
        assert len(mock_api.sent_messages) == 4
        
        # Check that error and startup messages went to correct topics
        startup_msg = mock_api.sent_messages[0]
        daily_msg = mock_api.sent_messages[1]
        command_msg = mock_api.sent_messages[2]
        error_msg = mock_api.sent_messages[3]
        
        assert startup_msg["message_id"] == "om_dailyreport_msg_123"
        assert daily_msg["message_id"] == "om_dailyreport_msg_123"
        assert command_msg["message_id"] == "om_commands_msg_123"
        assert error_msg["message_id"] == "om_commands_msg_123"
        
        # Check content formatting
        assert "🤖" in startup_msg["content"]  # Startup message has bot emoji
        assert "❌" in error_msg["content"]    # Error message has error emoji
        
        print("✅ Specialized messages test passed")
        return True
        
    except Exception as e:
        print(f"❌ Specialized messages test failed: {e}")
        return False

async def run_all_tests():
    """Run all topic manager tests."""
    print("🚀 Running Topic Manager Tests...")
    print("=" * 50)
    
    tests = [
        test_topic_messaging,
        test_topic_identification,
        test_specialized_messages
    ]
    
    sync_tests = [
        test_configuration_validation
    ]
    
    results = []
    
    # Run async tests
    for test in tests:
        result = await test()
        results.append(result)
        print()
    
    # Run sync tests
    for test in sync_tests:
        result = test()
        results.append(result)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Topic Manager module is ready.")
        print("\n💡 Module provides:")
        print("- Reply-based topic messaging (solves Lark topic targeting)")
        print("- Topic identification and validation")
        print("- Specialized message functions (startup, daily reports, errors)")
        print("- Configuration validation and summary")
    else:
        print("❌ Some tests failed. Please check implementation.")
    
    return passed == total

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())