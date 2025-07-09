#!/usr/bin/env python3
"""
Lark Bot Configuration Module - PRODUCTION-SAFE VERSION
Manages environment variables, validation, and production-safe logging setup
"""

import os
import logging
import logging.handlers
import json
import glob
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
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
    
    # Bot Configuration
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))  # seconds
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "/")
    
    # File Paths
    WALLETS_FILE = os.getenv("WALLETS_FILE", "wallets.json")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # API Configuration
    TRON_API_KEY = os.getenv("TRON_API_KEY")  # For wallet balance checking
    
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
        Setup production-safe logging with automatic rotation and cleanup.
        
        Returns:
            Configured logger instance
        """
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Configure logging level
        log_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)
        
        # Create production-safe formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Clear existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # 1. Console handler (only in development)
        environment = cls.ENVIRONMENT.upper()
        if environment in ["DEV", "DEVELOPMENT", "DEBUG"]:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # 2. Main rotating file handler (production-safe)
        log_file = logs_dir / "lark_bot.log"
        
        # Production settings: 5MB per file, 20 backups = max 100MB total
        main_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB per file
            backupCount=20,            # Keep 20 backup files (5MB x 20 = 100MB max)
            encoding='utf-8'
        )
        main_handler.setLevel(log_level)
        main_handler.setFormatter(formatter)
        root_logger.addHandler(main_handler)
        
        # 3. Error-only file handler (for critical issues)
        error_log_file = logs_dir / "lark_bot_errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            filename=error_log_file,
            maxBytes=2 * 1024 * 1024,  # 2MB for errors
            backupCount=5,             # Keep 5 error log backups (2MB x 5 = 10MB max)
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
        
        # 4. Cleanup old log files on startup
        cls._cleanup_old_logs(logs_dir)
        
        # Create bot-specific logger
        logger = logging.getLogger("lark_bot")
        logger.info(f"🔧 Production-safe logging initialized:")
        logger.info(f"   Environment: {environment}")
        logger.info(f"   Log Level: {cls.LOG_LEVEL}")
        logger.info(f"   Main Log: {log_file} (5MB x 20 files = 100MB max)")
        logger.info(f"   Error Log: {error_log_file} (2MB x 5 files = 10MB max)")
        logger.info(f"   Total Limit: ~110MB maximum")
        
        return logger
    
    @classmethod
    def _cleanup_old_logs(cls, logs_dir: Path):
        """
        Clean up old log files to prevent disk space issues.
        
        Args:
            logs_dir: Directory containing log files
        """
        try:
            # Delete files older than 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            old_files_deleted = 0
            
            # Find all log files (including old daily files and backups)
            log_patterns = [
                "lark_bot_*.log*",  # Old daily files
                "*.log.*",          # Rotated backup files
                "*.backup.*"        # Backup files
            ]
            
            for pattern in log_patterns:
                for log_file in logs_dir.glob(pattern):
                    if log_file.is_file():
                        try:
                            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                            if file_time < cutoff_date:
                                log_file.unlink()
                                old_files_deleted += 1
                        except Exception as e:
                            logging.warning(f"⚠️ Could not delete old log file {log_file}: {e}")
            
            if old_files_deleted > 0:
                logging.info(f"🗑️ Cleaned up {old_files_deleted} old log files")
            
            # Check and report current log directory size
            total_size = cls._get_directory_size(logs_dir)
            total_size_mb = total_size / (1024 * 1024)
            logging.info(f"📊 Log directory size: {total_size_mb:.1f}MB")
            
        except Exception as e:
            logging.error(f"❌ Error during log cleanup: {e}")
    
    @classmethod
    def _get_directory_size(cls, directory: Path) -> int:
        """Get total size of directory in bytes."""
        total_size = 0
        try:
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logging.warning(f"⚠️ Error calculating directory size: {e}")
        return total_size
    
    @classmethod
    def get_log_status(cls) -> Dict[str, Any]:
        """Get current logging status and statistics."""
        logs_dir = Path("logs")
        
        if not logs_dir.exists():
            return {"status": "No logs directory found"}
        
        # Count files and calculate sizes
        log_files = list(logs_dir.glob("*.log*"))
        total_files = len(log_files)
        total_size = cls._get_directory_size(logs_dir)
        total_size_mb = total_size / (1024 * 1024)
        
        # Find newest and oldest files
        newest_file = None
        oldest_file = None
        if log_files:
            files_with_time = [(f.stat().st_mtime, f) for f in log_files]
            files_with_time.sort(key=lambda x: x[0])
            oldest_file = files_with_time[0][1].name
            newest_file = files_with_time[-1][1].name
        
        return {
            "status": "Active",
            "total_files": total_files,
            "total_size_mb": round(total_size_mb, 2),
            "oldest_file": oldest_file,
            "newest_file": newest_file,
            "directory": str(logs_dir.absolute()),
            "limit_mb": 110  # 100MB main + 10MB errors
        }
    
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
                "message_id": cls.LARK_TOPIC_QUICKGUIDE_MSG,
                "chat_id": cls.LARK_CHAT_ID
            },
            "commands": {
                "thread_id": cls.LARK_TOPIC_COMMANDS,
                "message_id": cls.LARK_TOPIC_COMMANDS_MSG,
                "chat_id": cls.LARK_CHAT_ID
            },
            "dailyreport": {
                "thread_id": cls.LARK_TOPIC_DAILYREPORT,
                "message_id": cls.LARK_TOPIC_DAILYREPORT_MSG,
                "chat_id": cls.LARK_CHAT_ID
            }
        }
    
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
        
        # Logging info
        log_status = cls.get_log_status()
        summary.append(f"Logging: {log_status.get('total_size_mb', 0):.1f}MB / {log_status.get('limit_mb', 110)}MB limit")
        
        # Topic configuration
        topics = cls.get_topic_config()
        summary.append("Topics:")
        for name, config in topics.items():
            summary.append(f"  - {name}: thread={config.get('thread_id', 'None')[:10]}..., msg={config.get('message_id', 'None')[:10]}..., chat={config.get('chat_id', 'None')[:10]}...")
        
        # Authorization note
        summary.append("Authorization: Handled by handler_registry.py (ALLOWED_USERS)")
        
        return "\n".join(summary)

    @classmethod
    def get_current_time(cls) -> str:
        """Get current time as formatted string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    print("🧪 Testing Production-Safe Logging Setup...")
    
    try:
        logger = Config.setup_logging()
        logger.info("Test log message")
        
        # Test log status
        status = Config.get_log_status()
        print(f"   Log Status: {status.get('status')}")
        print(f"   Total Files: {status.get('total_files')}")
        print(f"   Directory Size: {status.get('total_size_mb')}MB / {status.get('limit_mb')}MB")
        
        print("✅ Production-safe logging setup successful")
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
                if not config.get("thread_id") or not config.get("message_id") or not config.get("chat_id"):
                    print(f"⚠️ Topic '{name}' missing required configuration")
                    print(f"   thread_id: {config.get('thread_id', 'MISSING')}")
                    print(f"   message_id: {config.get('message_id', 'MISSING')}")
                    print(f"   chat_id: {config.get('chat_id', 'MISSING')}")
                    return False
        
        print("✅ All topics properly configured")
        return True
    except Exception as e:
        print(f"❌ Topic configuration failed: {e}")
        return False

def monitor_log_health():
    """Monitor log health and show statistics."""
    status = Config.get_log_status()
    
    print("📊 Log Health Monitor:")
    print(f"   Status: {status.get('status')}")
    print(f"   Total Files: {status.get('total_files')}")
    print(f"   Total Size: {status.get('total_size_mb')}MB / {status.get('limit_mb')}MB")
    print(f"   Oldest File: {status.get('oldest_file')}")
    print(f"   Newest File: {status.get('newest_file')}")
    print(f"   Directory: {status.get('directory')}")
    
    # Health check
    size_mb = status.get('total_size_mb', 0)
    limit_mb = status.get('limit_mb', 110)
    
    if size_mb > limit_mb * 0.9:  # More than 90% of limit
        print("⚠️ WARNING: Log directory is near the limit!")
    elif size_mb > limit_mb * 0.5:  # More than 50% of limit
        print("💡 INFO: Log directory size is moderate")
    else:
        print("✅ Log directory size is healthy")

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
        print("\n💡 Production-Safe Logging Features:")
        print("   • Automatic log rotation (5MB per file)")
        print("   • Maximum 100MB total size (20 backups)")
        print("   • Separate error logs (10MB max)")
        print("   • Auto-cleanup of files older than 30 days")
        print("   • Console logging only in development")
        print("\n🔧 Next steps:")
        print("   1. Set ENVIRONMENT=PRODUCTION for production")
        print("   2. Monitor with: python config.py status")
    else:
        print("❌ Some tests failed. Please check configuration.")
        
    return passed == total

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            monitor_log_health()
        elif sys.argv[1] == "test":
            run_all_tests()
        else:
            print("Usage: python config.py [status|test]")
    else:
        # Show configuration summary
        try:
            print(Config.get_config_summary())
            print()
        except:
            print("⚠️ Could not load configuration summary")
            print()
        
        # Run tests
        run_all_tests()