#!/usr/bin/env python3
"""
Lark Bot Configuration Module
Manages environment variables, validation, and logging setup
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration management for Lark Bot."""
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Lark API Configuration
    LARK_APP_ID = os.getenv("LARK_APP_ID")
    LARK_APP_SECRET = os.getenv("LARK_APP_SECRET")
    LARK_CHAT_ID = os.getenv("LARK_CHAT_ID")
    
    # Topic Configuration
    LARK_TOPIC_QUICKGUIDE = os.getenv("LARK_TOPIC_QUICKGUIDE")
    LARK_TOPIC_COMMANDS = os.getenv("LARK_TOPIC_COMMANDS")
    LARK_TOPIC_DAILYREPORT = os.getenv("LARK_TOPIC_DAILYREPORT")
    
    # Topic Message IDs (for replies)
    LARK_TOPIC_QUICKGUIDE_MSG = os.getenv("LARK_TOPIC_QUICKGUIDE_MSG")
    LARK_TOPIC_COMMANDS_MSG = os.getenv("LARK_TOPIC_COMMANDS_MSG")
    LARK_TOPIC_DAILYREPORT_MSG = os.getenv("LARK_TOPIC_DAILYREPORT_MSG")
    
    # Authorization
    LARK_AUTHORIZED_USERS = os.getenv("LARK_AUTHORIZED_USERS", "").split(",")
    
    # Bot Configuration
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))  # seconds
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "/")
    
    # File Paths
    WALLETS_FILE = os.getenv("WALLETS_FILE", "wallets.json")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def _find_wallets_file(cls) -> str:
        """Find wallets.json file in current directory or project root."""
        possible_paths = [
            cls.WALLETS_FILE,  # Current directory
            f"../../{cls.WALLETS_FILE}",  # Project root from bot/utils
            f"../{cls.WALLETS_FILE}",  # One level up
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # If not found, return the default
        return cls.WALLETS_FILE
    
    # API Configuration
    TRON_API_KEY = os.getenv("TRON_API_KEY")  # For wallet balance checking
    
    @classmethod
    def validate_config(cls) -> bool:
        """
        Validate that all required configuration is present.
        
        Returns:
            True if configuration is valid, raises exception if not
        """
        required_vars = {
            "LARK_APP_ID": cls.LARK_APP_ID,
            "LARK_APP_SECRET": cls.LARK_APP_SECRET,
            "LARK_CHAT_ID": cls.LARK_CHAT_ID,
            "LARK_TOPIC_COMMANDS": cls.LARK_TOPIC_COMMANDS,
            "LARK_TOPIC_DAILYREPORT": cls.LARK_TOPIC_DAILYREPORT,
            "LARK_TOPIC_COMMANDS_MSG": cls.LARK_TOPIC_COMMANDS_MSG,
            "LARK_TOPIC_DAILYREPORT_MSG": cls.LARK_TOPIC_DAILYREPORT_MSG,
        }
        
        missing_vars = []
        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logging.error(f"❌ Configuration Error: {error_msg}")
            raise ValueError(error_msg)
        
        # Validate wallets file exists
        wallets_path = cls._find_wallets_file()
        if not os.path.exists(wallets_path):
            error_msg = f"Wallets file not found: {wallets_path} (searched: {cls.WALLETS_FILE}, ../../{cls.WALLETS_FILE}, ../{cls.WALLETS_FILE})"
            logging.error(f"❌ Configuration Error: {error_msg}")
            raise FileNotFoundError(error_msg)
        
        # Validate authorized users format
        if cls.LARK_AUTHORIZED_USERS == [""]:
            logging.warning("⚠️ No authorized users configured - bot will accept commands from anyone")
        
        logging.info("✅ Configuration validation passed")
        return True
    
    @classmethod
    def load_wallets(cls) -> Dict[str, Any]:
        """
        Load wallet configuration from JSON file.
        
        Returns:
            Dictionary of wallet configurations
        """
        try:
            wallets_path = cls._find_wallets_file()
            with open(wallets_path, 'r') as f:
                wallets = json.load(f)
            
            if not wallets:
                logging.warning("⚠️ No wallets configured in wallets.json")
                return {}
            
            logging.info(f"✅ Loaded {len(wallets)} wallets from {wallets_path}")
            return wallets
            
        except FileNotFoundError:
            logging.error(f"❌ Wallets file not found: {cls._find_wallets_file()}")
            return {}
        except json.JSONDecodeError as e:
            logging.error(f"❌ Invalid JSON in wallets file: {e}")
            return {}
        except Exception as e:
            logging.error(f"❌ Error loading wallets: {e}")
            return {}
    
    @classmethod
    def save_wallets(cls, wallets: Dict[str, Any]) -> bool:
        """
        Save wallet configuration to JSON file.
        
        Args:
            wallets: Dictionary of wallet configurations
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create backup of existing file
            if os.path.exists(cls.WALLETS_FILE):
                backup_file = f"{cls.WALLETS_FILE}.backup.{int(datetime.now().timestamp())}"
                os.rename(cls.WALLETS_FILE, backup_file)
                logging.info(f"📄 Created backup: {backup_file}")
            
            # Save new configuration
            with open(cls.WALLETS_FILE, 'w') as f:
                json.dump(wallets, f, indent=2)
            
            logging.info(f"✅ Saved {len(wallets)} wallets to {cls.WALLETS_FILE}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error saving wallets: {e}")
            return False
    
    @classmethod
    def setup_logging(cls) -> logging.Logger:
        """
        Setup logging configuration.
        
        Returns:
            Configured logger instance
        """
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Configure logging level
        log_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler
        log_file = logs_dir / f"lark_bot_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Create bot-specific logger
        logger = logging.getLogger("lark_bot")
        logger.info(f"🔧 Logging initialized - Level: {cls.LOG_LEVEL}, File: {log_file}")
        
        return logger
    
    @classmethod
    def get_topic_config(cls) -> Dict[str, Dict[str, str]]:
        """
        Get topic configuration mapping.
        
        Returns:
            Dictionary mapping topic names to their IDs and message IDs
        """
        return {
            "quickguide": {
                "thread_id": cls.LARK_TOPIC_QUICKGUIDE,
                "message_id": cls.LARK_TOPIC_QUICKGUIDE_MSG
            },
            "commands": {
                "thread_id": cls.LARK_TOPIC_COMMANDS,
                "message_id": cls.LARK_TOPIC_COMMANDS_MSG
            },
            "dailyreport": {
                "thread_id": cls.LARK_TOPIC_DAILYREPORT,
                "message_id": cls.LARK_TOPIC_DAILYREPORT_MSG
            }
        }
    
    @classmethod
    def is_user_authorized(cls, user_id: str) -> bool:
        """
        Check if a user is authorized to use the bot.
        
        Args:
            user_id: Lark user ID to check
            
        Returns:
            True if user is authorized, False otherwise
        """
        # If no authorized users configured, allow everyone
        if not cls.LARK_AUTHORIZED_USERS or cls.LARK_AUTHORIZED_USERS == [""]:
            return True
        
        return user_id in cls.LARK_AUTHORIZED_USERS
    
    @classmethod
    def get_config_summary(cls) -> str:
        """
        Get a summary of current configuration (for debugging).
        
        Returns:
            Formatted configuration summary
        """
        summary = []
        summary.append("🔧 Lark Bot Configuration Summary")
        summary.append(f"Environment: {cls.ENVIRONMENT}")
        summary.append(f"App ID: {cls.LARK_APP_ID[:10]}..." if cls.LARK_APP_ID else "App ID: Not set")
        summary.append(f"Chat ID: {cls.LARK_CHAT_ID}")
        summary.append(f"Poll Interval: {cls.POLL_INTERVAL}s")
        summary.append(f"Command Prefix: {cls.COMMAND_PREFIX}")
        summary.append(f"Wallets File: {cls.WALLETS_FILE}")
        summary.append(f"Log Level: {cls.LOG_LEVEL}")
        
        # Topic configuration
        topics = cls.get_topic_config()
        summary.append("Topics:")
        for name, config in topics.items():
            summary.append(f"  - {name}: {config['thread_id'][:10]}...")
        
        # Authorization
        if cls.LARK_AUTHORIZED_USERS and cls.LARK_AUTHORIZED_USERS != [""]:
            summary.append(f"Authorized Users: {len(cls.LARK_AUTHORIZED_USERS)} configured")
        else:
            summary.append("Authorized Users: Open access (no restrictions)")
        
        return "\n".join(summary)


# Testing functions
def test_config_validation():
    """Test configuration validation."""
    print("🧪 Testing Configuration Validation...")
    
    try:
        # This will fail if required env vars are missing
        Config.validate_config()
        print("✅ Configuration validation passed")
        return True
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ Configuration validation failed: {e}")
        return False

def test_wallets_loading():
    """Test wallet loading functionality."""
    print("🧪 Testing Wallet Loading...")
    
    try:
        wallets = Config.load_wallets()
        if wallets:
            print(f"✅ Loaded {len(wallets)} wallets successfully")
            
            # Show first wallet as example
            first_wallet = next(iter(wallets.values()))
            print(f"📄 Example wallet: {first_wallet.get('wallet', 'Unknown')} - {first_wallet.get('address', 'No address')[:10]}...")
            return True
        else:
            print("⚠️ No wallets loaded (file might be empty)")
            return False
    except Exception as e:
        print(f"❌ Wallet loading failed: {e}")
        return False

def test_logging_setup():
    """Test logging setup."""
    print("🧪 Testing Logging Setup...")
    
    try:
        logger = Config.setup_logging()
        logger.info("Test log message")
        print("✅ Logging setup successful")
        return True
    except Exception as e:
        print(f"❌ Logging setup failed: {e}")
        return False

def test_topic_config():
    """Test topic configuration."""
    print("🧪 Testing Topic Configuration...")
    
    try:
        topics = Config.get_topic_config()
        print(f"✅ Topic configuration loaded: {list(topics.keys())}")
        
        # Check each topic has required fields
        for name, config in topics.items():
            # Only validate required topics (commands and dailyreport)
            if name in ['commands', 'dailyreport']:
                if not config.get("thread_id") or not config.get("message_id"):
                    print(f"⚠️ Topic '{name}' missing required configuration")
                    return False
        
        print("✅ All topics properly configured")
        return True
    except Exception as e:
        print(f"❌ Topic configuration failed: {e}")
        return False

def run_all_tests():
    """Run all configuration tests."""
    print("🚀 Running Configuration Module Tests...")
    print("=" * 50)
    
    tests = [
        test_logging_setup,
        test_topic_config,
        test_wallets_loading,
        test_config_validation,
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
        print("🎉 All tests passed! Configuration module is ready.")
        print("\n💡 Next steps:")
        print("1. Create .env file with your Lark configuration")
        print("2. Ensure wallets.json is properly formatted")
        print("3. Run this script to validate your setup")
    else:
        print("❌ Some tests failed. Please check configuration.")
        
    return passed == total

if __name__ == "__main__":
    # Show configuration summary
    try:
        print(Config.get_config_summary())
        print()
    except:
        print("⚠️ Could not load configuration summary")
        print()
    
    # Run tests
    run_all_tests()