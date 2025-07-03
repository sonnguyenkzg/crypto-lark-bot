#!/usr/bin/env python3
"""
Lark Bot Base Handler Module
Provides base handler class with common functionality for all command handlers
"""

import logging
from typing import List, Optional, Any, Dict
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseHandler(ABC):
    """
    Abstract base class for all command handlers.
    Provides common functionality and enforces handler interface.
    """
    
    def __init__(self, name: str, description: str, usage: str = "", min_args: int = 0, max_args: Optional[int] = None):
        """
        Initialize base handler.
        
        Args:
            name: Command name (without prefix)
            description: Command description for help text
            usage: Usage example string
            min_args: Minimum number of arguments required
            max_args: Maximum number of arguments allowed (None = unlimited)
        """
        self.name = name.lower()
        self.description = description
        self.usage = usage
        self.min_args = min_args
        self.max_args = max_args
        self.aliases = []
        self.enabled = True
        
        # Statistics
        self.call_count = 0
        self.last_used = None
        self.error_count = 0
    
    def add_alias(self, alias: str) -> 'BaseHandler':
        """
        Add command alias.
        
        Args:
            alias: Alias name
            
        Returns:
            Self for method chaining
        """
        self.aliases.append(alias.lower())
        return self
    
    def set_enabled(self, enabled: bool) -> 'BaseHandler':
        """
        Enable or disable this handler.
        
        Args:
            enabled: Whether handler should be enabled
            
        Returns:
            Self for method chaining
        """
        self.enabled = enabled
        return self
    
    @abstractmethod
    async def execute(self, context: Any) -> bool:
        """
        Execute the command logic.
        
        Args:
            context: Command execution context
            
        Returns:
            True if command executed successfully, False otherwise
        """
        pass
    
    async def handle(self, context: Any) -> bool:
        """
        Handle command execution with validation and error handling.
        
        Args:
            context: Command execution context
            
        Returns:
            True if command executed successfully, False otherwise
        """
        try:
            # Check if handler is enabled
            if not self.enabled:
                await self._send_disabled_message(context)
                return False
            
            # Validate arguments
            if not self._validate_arguments(context.args):
                await self._send_usage_message(context)
                return False
            
            # Update statistics
            self.call_count += 1
            self.last_used = datetime.now()
            
            # Execute the command
            logger.info(f"🎯 Executing {self.name} command (user: {context.sender_id})")
            success = await self.execute(context)
            
            if not success:
                self.error_count += 1
                logger.warning(f"⚠️ Command {self.name} returned failure")
            
            return success
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"❌ Error in {self.name} command: {e}")
            await self._send_error_message(context, str(e))
            return False
    
    def _validate_arguments(self, args: List[str]) -> bool:
        """
        Validate command arguments.
        
        Args:
            args: List of command arguments
            
        Returns:
            True if arguments are valid, False otherwise
        """
        arg_count = len(args)
        
        # Check minimum arguments
        if arg_count < self.min_args:
            logger.warning(f"⚠️ {self.name}: Too few arguments ({arg_count} < {self.min_args})")
            return False
        
        # Check maximum arguments
        if self.max_args is not None and arg_count > self.max_args:
            logger.warning(f"⚠️ {self.name}: Too many arguments ({arg_count} > {self.max_args})")
            return False
        
        return True
    
    async def _send_usage_message(self, context: Any) -> None:
        """Send usage message to user."""
        try:
            usage_msg = self.get_usage_text()
            await context.topic_manager.send_command_response(usage_msg)
        except Exception as e:
            logger.error(f"❌ Error sending usage message: {e}")
    
    async def _send_error_message(self, context: Any, error: str) -> None:
        """Send error message to user."""
        try:
            error_msg = f"❌ **Command Error**\nCommand: /{self.name}\nError: {error}"
            await context.topic_manager.send_error_message(error_msg)
        except Exception as e:
            logger.error(f"❌ Error sending error message: {e}")
    
    async def _send_disabled_message(self, context: Any) -> None:
        """Send disabled message to user."""
        try:
            disabled_msg = f"🚫 **Command Disabled**\nThe `/{self.name}` command is currently disabled."
            await context.topic_manager.send_command_response(disabled_msg)
        except Exception as e:
            logger.error(f"❌ Error sending disabled message: {e}")
    
    def get_help_text(self) -> str:
        """
        Get formatted help text for this command.
        
        Returns:
            Formatted help text
        """
        help_lines = []
        
        # Command name and aliases
        command_line = f"**/{self.name}**"
        if self.aliases:
            aliases_text = ", ".join([f"/{alias}" for alias in self.aliases])
            command_line += f" (aliases: {aliases_text})"
        
        help_lines.append(command_line)
        
        # Description
        help_lines.append(self.description)
        
        # Usage
        if self.usage:
            help_lines.append(f"**Usage:** {self.usage}")
        elif self.min_args > 0 or self.max_args is not None:
            # Generate basic usage from arg requirements
            if self.max_args == 0:
                usage = f"/{self.name}"
            elif self.min_args == 0:
                usage = f"/{self.name} [optional_args]"
            else:
                required_args = " ".join([f"<arg{i+1}>" for i in range(self.min_args)])
                if self.max_args is None or self.max_args > self.min_args:
                    usage = f"/{self.name} {required_args} [additional_args]"
                else:
                    usage = f"/{self.name} {required_args}"
            help_lines.append(f"**Usage:** {usage}")
        
        # Status
        if not self.enabled:
            help_lines.append("⚠️ *Currently disabled*")
        
        return "\n".join(help_lines)
    
    def get_usage_text(self) -> str:
        """
        Get formatted usage text for argument validation errors.
        
        Returns:
            Formatted usage text
        """
        usage_lines = []
        usage_lines.append(f"❌ **Invalid Usage: /{self.name}**")
        
        if self.usage:
            usage_lines.append(f"**Correct usage:** {self.usage}")
        
        # Argument requirements
        if self.min_args > 0:
            usage_lines.append(f"**Minimum arguments:** {self.min_args}")
        
        if self.max_args is not None:
            usage_lines.append(f"**Maximum arguments:** {self.max_args}")
        
        usage_lines.append(f"Use `/help {self.name}` for more information.")
        
        return "\n".join(usage_lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get handler statistics.
        
        Returns:
            Dictionary with handler statistics
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "success_rate": (self.call_count - self.error_count) / max(self.call_count, 1),
            "aliases": self.aliases
        }

class SimpleResponseHandler(BaseHandler):
    """
    Simple handler that sends a predefined response.
    Useful for static commands like help messages or info.
    """
    
    def __init__(self, name: str, description: str, response: str, **kwargs):
        """
        Initialize simple response handler.
        
        Args:
            name: Command name
            description: Command description
            response: Response message to send
            **kwargs: Additional BaseHandler arguments
        """
        super().__init__(name, description, **kwargs)
        self.response = response
    
    async def execute(self, context: Any) -> bool:
        """Execute by sending the predefined response."""
        try:
            await context.topic_manager.send_command_response(self.response)
            return True
        except Exception as e:
            logger.error(f"❌ Error sending response: {e}")
            return False

class TemplateHandler(BaseHandler):
    """
    Template handler with placeholder implementation.
    Useful for creating handler structure before implementing logic.
    """
    
    def __init__(self, name: str, description: str, **kwargs):
        super().__init__(name, description, **kwargs)
    
    async def execute(self, context: Any) -> bool:
        """Template implementation - sends not implemented message."""
        try:
            message = (
                f"🚧 **Command Under Development**\n"
                f"The `/{self.name}` command is not yet implemented.\n"
                f"Please check back later!"
            )
            await context.topic_manager.send_command_response(message)
            return True
        except Exception as e:
            logger.error(f"❌ Error in template handler: {e}")
            return False

# Mock classes for testing
class MockContext:
    """Mock context for testing."""
    
    def __init__(self, args: List[str] = None, sender_id: str = "test_user"):
        self.args = args or []
        self.sender_id = sender_id
        self.command = "test"
        self.topic_manager = MockTopicManager()

class MockTopicManager:
    """Mock topic manager for testing."""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_command_response(self, message: str):
        self.sent_messages.append(("response", message))
    
    async def send_error_message(self, message: str):
        self.sent_messages.append(("error", message))

# Concrete test handler
class TestHandler(BaseHandler):
    """Test handler implementation."""
    
    def __init__(self, should_succeed: bool = True):
        super().__init__(
            name="test",
            description="Test handler for unit tests",
            usage="/test <arg1> [arg2]",
            min_args=1,
            max_args=2
        )
        self.should_succeed = should_succeed
        self.execution_count = 0
    
    async def execute(self, context: Any) -> bool:
        self.execution_count += 1
        return self.should_succeed

# Testing functions
async def test_basic_handler_functionality():
    """Test basic handler functionality."""
    print("🧪 Testing Basic Handler Functionality...")
    
    try:
        handler = TestHandler()
        context = MockContext(args=["arg1"])
        
        # Test successful execution
        success = await handler.handle(context)
        assert success
        assert handler.execution_count == 1
        assert handler.call_count == 1
        assert handler.error_count == 0
        
        # Test statistics
        stats = handler.get_statistics()
        assert stats["call_count"] == 1
        assert stats["success_rate"] == 1.0
        
        print("✅ Basic handler functionality test passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic handler functionality test failed: {e}")
        return False

async def test_argument_validation():
    """Test argument validation."""
    print("🧪 Testing Argument Validation...")
    
    try:
        handler = TestHandler()
        
        # Test too few arguments
        context1 = MockContext(args=[])  # Need at least 1
        success = await handler.handle(context1)
        assert not success
        assert handler.execution_count == 0  # Should not execute
        
        # Test valid arguments
        context2 = MockContext(args=["arg1"])
        success = await handler.handle(context2)
        assert success
        assert handler.execution_count == 1
        
        # Test too many arguments
        context3 = MockContext(args=["arg1", "arg2", "arg3"])  # Max is 2
        success = await handler.handle(context3)
        assert not success
        assert handler.execution_count == 1  # Should not execute again
        
        # Check that usage messages were sent (each context has its own topic manager)
        usage_message1 = any("Invalid Usage" in msg for msg_type, msg in context1.topic_manager.sent_messages)
        usage_message3 = any("Invalid Usage" in msg for msg_type, msg in context3.topic_manager.sent_messages)
        
        assert usage_message1  # First validation failure
        assert usage_message3  # Second validation failure
        
        print("✅ Argument validation test passed")
        return True
        
    except Exception as e:
        print(f"❌ Argument validation test failed: {e}")
        return False

async def test_handler_states():
    """Test handler enable/disable functionality."""
    print("🧪 Testing Handler States...")
    
    try:
        handler = TestHandler()
        context = MockContext(args=["arg1"])
        
        # Test enabled handler
        assert handler.enabled
        success = await handler.handle(context)
        assert success
        
        # Test disabled handler
        handler.set_enabled(False)
        assert not handler.enabled
        success = await handler.handle(context)
        assert not success
        
        # Check disabled message was sent
        messages = context.topic_manager.sent_messages
        disabled_messages = [msg for msg_type, msg in messages if "Command Disabled" in msg]
        assert len(disabled_messages) == 1
        
        print("✅ Handler states test passed")
        return True
        
    except Exception as e:
        print(f"❌ Handler states test failed: {e}")
        return False

async def test_simple_response_handler():
    """Test simple response handler."""
    print("🧪 Testing Simple Response Handler...")
    
    try:
        response_text = "Hello, this is a test response!"
        handler = SimpleResponseHandler(
            name="hello",
            description="Says hello",
            response=response_text
        )
        
        context = MockContext()
        success = await handler.handle(context)
        
        assert success
        assert handler.call_count == 1
        
        # Check response was sent
        messages = context.topic_manager.sent_messages
        response_messages = [msg for msg_type, msg in messages if msg_type == "response"]
        assert len(response_messages) == 1
        assert response_text in response_messages[0]
        
        print("✅ Simple response handler test passed")
        return True
        
    except Exception as e:
        print(f"❌ Simple response handler test failed: {e}")
        return False

async def test_template_handler():
    """Test template handler."""
    print("🧪 Testing Template Handler...")
    
    try:
        handler = TemplateHandler(
            name="future",
            description="Future command"
        )
        
        context = MockContext()
        success = await handler.handle(context)
        
        assert success
        assert handler.call_count == 1
        
        # Check template message was sent
        messages = context.topic_manager.sent_messages
        response_messages = [msg for msg_type, msg in messages if "Under Development" in msg]
        assert len(response_messages) == 1
        
        print("✅ Template handler test passed")
        return True
        
    except Exception as e:
        print(f"❌ Template handler test failed: {e}")
        return False

def test_help_generation():
    """Test help text generation."""
    print("🧪 Testing Help Generation...")
    
    try:
        # Test basic handler
        handler = TestHandler()
        help_text = handler.get_help_text()
        
        assert "/test" in help_text
        assert "Test handler for unit tests" in help_text
        assert "/test <arg1> [arg2]" in help_text
        
        # Test handler with aliases
        handler.add_alias("t").add_alias("testing")
        help_text = handler.get_help_text()
        
        assert "aliases" in help_text
        assert "/t" in help_text
        assert "/testing" in help_text
        
        # Test disabled handler
        handler.set_enabled(False)
        help_text = handler.get_help_text()
        
        assert "disabled" in help_text.lower()
        
        print("✅ Help generation test passed")
        return True
        
    except Exception as e:
        print(f"❌ Help generation test failed: {e}")
        return False

async def run_all_tests():
    """Run all base handler tests."""
    print("🚀 Running Base Handler Tests...")
    print("=" * 50)
    
    async_tests = [
        test_basic_handler_functionality,
        test_argument_validation,
        test_handler_states,
        test_simple_response_handler,
        test_template_handler
    ]
    
    sync_tests = [
        test_help_generation
    ]
    
    results = []
    
    # Run async tests
    for test in async_tests:
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
        print("🎉 All tests passed! Base Handler module is ready.")
        print("\n💡 Module provides:")
        print("- Abstract base class for all command handlers")
        print("- Argument validation and error handling")
        print("- Handler statistics and state management")
        print("- Help text generation")
        print("- Utility handler classes (SimpleResponse, Template)")
    else:
        print("❌ Some tests failed. Please check implementation.")
    
    return passed == total

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())