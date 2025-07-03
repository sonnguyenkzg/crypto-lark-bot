#!/usr/bin/env python3
"""
Lark Message Parser Module
Handles parsing and validation of incoming Lark messages
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class LarkMessage:
    def __init__(self, event):
        self.raw = event
        self.message = event.get("message", {})
        self.sender = event.get("sender", {})

    @property
    def sender_id(self) -> str:
        try:
            sid = self.sender.get("sender_id", {})
            resolved_id = sid.get("user_id") or sid.get("open_id") or sid.get("union_id", "")
            if not resolved_id:
                print("⚠️ sender_id not found in:", json.dumps(self.sender, indent=2))
            return resolved_id
        except Exception as e:
            logger.warning(f"⚠️ Failed to extract sender_id: {e}")
            return ""

    @property
    def content(self) -> str:
        try:
            raw = self.message.get("content", "")
            if isinstance(raw, str):
                parsed = json.loads(raw)
                return parsed.get("text", raw)
            return raw
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse content: {e}")
            return str(raw)

    
    @property
    def chat_id(self) -> str:
        return self.message.get("chat_id", "")
    
    @property
    def thread_id(self) -> str:
        return self.message.get("thread_id", "")

    @property
    def is_from_bot(self) -> bool:
        return self.sender.get("sender_type") == "bot"

class LarkMessageParser:
    """
    Parser for Lark messages with command detection and validation.
    """
    
    def __init__(self, command_prefix: str = "/"):
        self.command_prefix = command_prefix
        
    def parse_message(self, event: dict) -> LarkMessage:
        return LarkMessage(event)


    def is_command(self, message: LarkMessage) -> bool:
        """
        Check if a message contains a bot command.
        
        Args:
            message: Parsed LarkMessage object
            
        Returns:
            True if message is a command
        """
        content = message.content.strip()
        
        # Must start with prefix and have at least one character after it
        if not content.startswith(self.command_prefix):
            return False
        
        # Remove prefix and check if there's actual command content
        command_part = content[len(self.command_prefix):].strip()
        return len(command_part) > 0
    
    def parse_command(self, message: LarkMessage) -> Tuple[str, List[str]]:
        """
        Parse command and arguments from message.
        
        Args:
            message: Parsed LarkMessage object
            
        Returns:
            Tuple of (command, arguments_list)
        """
        content = message.content.strip()
        
        if not self.is_command(message):
            return "", []
        
        # Remove command prefix
        command_text = content[len(self.command_prefix):]
        
        # Split into parts
        parts = command_text.split()
        
        if not parts:
            return "", []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    def validate_message_structure(self, raw_message: Dict[str, Any]) -> bool:
        """
        Validate that a message has the expected Lark structure.
        
        Args:
            raw_message: Raw message data to validate
            
        Returns:
            True if structure is valid
        """
        required_fields = ["message_id", "sender", "chat_id", "msg_type", "create_time"]
        
        for field in required_fields:
            if field not in raw_message:
                logger.warning(f"⚠️ Missing required field: {field}")
                return False
        
        # Validate sender structure
        sender = raw_message.get("sender", {})
        if not isinstance(sender, dict) or "sender_id" not in sender:
            logger.warning("⚠️ Invalid sender structure")
            return False
        
        return True
    
    def filter_bot_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out messages from bots (to avoid loops).
        
        Args:
            messages: List of raw message dictionaries
            
        Returns:
            Filtered list without bot messages
        """
        filtered = []
        
        for msg in messages:
            if not self.validate_message_structure(msg):
                continue
                
            sender = msg.get("sender", {})
            sender_type = sender.get("sender_type", "")
            
            if sender_type != "app":  # Keep human messages only
                filtered.append(msg)
        
        return filtered
    
    def filter_by_topic(self, messages: List[Dict[str, Any]], topic_id: str) -> List[Dict[str, Any]]:
        """
        Filter messages by topic/thread ID.
        
        Args:
            messages: List of raw message dictionaries
            topic_id: Topic thread ID to filter by
            
        Returns:
            Messages from the specified topic only
        """
        return [msg for msg in messages if msg.get("thread_id") == topic_id]
    
    def get_recent_commands(self, messages: List[Dict[str, Any]], topic_id: Optional[str] = None) -> List[Tuple[LarkMessage, str, List[str]]]:
        """
        Extract recent commands from a list of messages.
        
        Args:
            messages: List of raw message dictionaries
            topic_id: Optional topic ID to filter by
            
        Returns:
            List of tuples: (LarkMessage, command, args)
        """
        # Filter messages
        filtered_messages = self.filter_bot_messages(messages)
        
        if topic_id:
            filtered_messages = self.filter_by_topic(filtered_messages, topic_id)
        
        # Parse and extract commands
        commands = []
        
        for raw_msg in filtered_messages:
            try:
                message = self.parse_message(raw_msg)
                
                if self.is_command(message):
                    command, args = self.parse_command(message)
                    commands.append((message, command, args))
                    
            except Exception as e:
                logger.error(f"❌ Error parsing message: {e}")
                continue
        
        # Sort by creation time (newest first)
        commands.sort(key=lambda x: x[0].create_time, reverse=True)
        
        return commands

# Testing functions
def test_message_parsing():
    """Test message parsing with sample Lark message."""
    print("🧪 Testing Message Parsing...")
    
    # Sample Lark message (based on typical structure)
    sample_message = {
        "message_id": "om_test123",
        "sender": {
            "sender_id": {"user_id": "ou_user123"},
            "sender_type": "user"
        },
        "chat_id": "oc_chat123",
        "thread_id": "omt_topic123",
        "msg_type": "text",
        "create_time": "1672531200000",  # 2023-01-01 00:00:00
        "body": {
            "content": '{"text": "/start hello world"}'
        }
    }
    
    try:
        parser = LarkMessageParser()
        message = parser.parse_message(sample_message)
        
        # Test basic properties
        assert message.message_id == "om_test123"
        assert message.sender_id == "ou_user123"
        assert message.content == "/start hello world"
        assert message.thread_id == "omt_topic123"
        assert not message.is_from_bot
        assert message.is_in_topic
        
        # Test command parsing
        assert parser.is_command(message)
        command, args = parser.parse_command(message)
        assert command == "start"
        assert args == ["hello", "world"]
        
        print("✅ Message parsing test passed")
        return True
        
    except Exception as e:
        print(f"❌ Message parsing test failed: {e}")
        return False

def test_content_extraction():
    """Test content extraction from different message types."""
    print("🧪 Testing Content Extraction...")
    
    test_cases = [
        # Simple text message
        {
            "msg_type": "text",
            "body": {"content": '{"text": "Hello world"}'},
            "expected": "Hello world"
        },
        # String content (not JSON)
        {
            "msg_type": "text", 
            "body": {"content": "Simple string"},
            "expected": "Simple string"
        },
        # Rich text message
        {
            "msg_type": "rich_text",
            "body": {"content": '{"elements": [{"tag": "text", "text": "Hello "}, {"tag": "text", "text": "world"}]}'},
            "expected": "Hello  world"
        }
    ]
    
    try:
        parser = LarkMessageParser()
        
        for i, test_case in enumerate(test_cases):
            message_data = {
                "message_id": f"test_{i}",
                "sender": {"sender_id": {"user_id": "test"}, "sender_type": "user"},
                "chat_id": "test",
                "msg_type": test_case["msg_type"],
                "create_time": "1672531200000",
                "body": test_case["body"]
            }
            
            message = parser.parse_message(message_data)
            content = message.content
            
            if content != test_case["expected"]:
                print(f"❌ Test case {i}: Expected '{test_case['expected']}', got '{content}'")
                return False
        
        print("✅ Content extraction test passed")
        return True
        
    except Exception as e:
        print(f"❌ Content extraction test failed: {e}")
        return False

def test_command_detection():
    """Test command detection and parsing."""
    print("🧪 Testing Command Detection...")
    
    test_cases = [
        ("/start", True, "start", []),
        ("/help me please", True, "help", ["me", "please"]),
        ("hello world", False, "", []),
        ("/", False, "", []),
        ("/LIST", True, "list", []),
        ("  /check wallet1  ", True, "check", ["wallet1"]),
    ]
    
    try:
        parser = LarkMessageParser()
        
        for content, is_cmd, expected_cmd, expected_args in test_cases:
            message_data = {
                "message_id": "test",
                "sender": {"sender_id": {"user_id": "test"}, "sender_type": "user"},
                "chat_id": "test",
                "msg_type": "text",
                "create_time": "1672531200000",
                "body": {"content": f'{{"text": "{content}"}}'}
            }
            
            message = parser.parse_message(message_data)
            
            # Test command detection
            if parser.is_command(message) != is_cmd:
                print(f"❌ Command detection failed for: '{content}'")
                return False
            
            # Test command parsing
            if is_cmd:
                command, args = parser.parse_command(message)
                if command != expected_cmd or args != expected_args:
                    print(f"❌ Command parsing failed for: '{content}'")
                    print(f"   Expected: {expected_cmd}, {expected_args}")
                    print(f"   Got: {command}, {args}")
                    return False
        
        print("✅ Command detection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Command detection test failed: {e}")
        return False

def test_message_filtering():
    """Test message filtering functionality."""
    print("🧪 Testing Message Filtering...")
    
    sample_messages = [
        # Human message in topic
        {
            "message_id": "msg1",
            "sender": {"sender_id": {"user_id": "user1"}, "sender_type": "user"},
            "chat_id": "chat1",
            "thread_id": "topic1",
            "msg_type": "text",
            "create_time": "1672531200000",
            "body": {"content": '{"text": "/start"}'}
        },
        # Bot message (should be filtered)
        {
            "message_id": "msg2",
            "sender": {"sender_id": {"app_id": "bot1"}, "sender_type": "app"},
            "chat_id": "chat1",
            "thread_id": "topic1", 
            "msg_type": "text",
            "create_time": "1672531300000",
            "body": {"content": '{"text": "Bot response"}'}
        },
        # Human message in different topic
        {
            "message_id": "msg3",
            "sender": {"sender_id": {"user_id": "user1"}, "sender_type": "user"},
            "chat_id": "chat1",
            "thread_id": "topic2",
            "msg_type": "text", 
            "create_time": "1672531400000",
            "body": {"content": '{"text": "/help"}'}
        }
    ]
    
    try:
        parser = LarkMessageParser()
        
        # Test bot message filtering
        filtered = parser.filter_bot_messages(sample_messages)
        assert len(filtered) == 2  # Should remove bot message
        
        # Test topic filtering
        topic_filtered = parser.filter_by_topic(sample_messages, "topic1")
        assert len(topic_filtered) == 2  # Both messages in topic1
        
        # Test command extraction
        commands = parser.get_recent_commands(sample_messages, "topic1")
        assert len(commands) == 1  # Only human command in topic1
        
        message, command, args = commands[0]
        assert command == "start"
        
        print("✅ Message filtering test passed")
        return True
        
    except Exception as e:
        print(f"❌ Message filtering test failed: {e}")
        return False

def run_all_tests():
    """Run all message parser tests."""
    print("🚀 Running Message Parser Tests...")
    print("=" * 50)
    
    tests = [
        test_message_parsing,
        test_content_extraction, 
        test_command_detection,
        test_message_filtering
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Message Parser module is ready.")
        print("\n💡 Module provides:")
        print("- LarkMessage class for easy message property access")
        print("- Command detection and parsing")
        print("- Content extraction from different message types")
        print("- Message filtering (bots, topics)")
        print("- Command extraction from message lists")
    else:
        print("❌ Some tests failed. Please check implementation.")
    
    return passed == total

if __name__ == "__main__":
    run_all_tests()