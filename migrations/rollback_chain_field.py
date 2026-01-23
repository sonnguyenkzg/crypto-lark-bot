#!/usr/bin/env python3
"""
Rollback Script: Restore Wallets from Backup

This script restores wallets.json from the most recent backup file.
Used to rollback the chain field migration if issues occur.

Features:
- Finds most recent .pre-erc20.* backup file
- Validates backup before restoration
- Creates additional safety backup before rollback
- Logs detailed rollback summary
"""

import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def find_latest_backup(wallets_file: str) -> str | None:
    """
    Find the most recent backup file.

    Args:
        wallets_file: Path to wallets.json

    Returns:
        Path to most recent backup file, or None if not found
    """
    # Look for .pre-erc20.* backup files
    backup_pattern = f"{wallets_file}.pre-erc20.*"
    backup_files = glob.glob(backup_pattern)

    if not backup_files:
        return None

    # Sort by modification time (most recent first)
    backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    return backup_files[0]


def validate_backup(backup_file: str) -> bool:
    """
    Validate that backup file contains valid JSON and wallets.

    Args:
        backup_file: Path to backup file

    Returns:
        True if backup is valid
    """
    try:
        with open(backup_file, 'r') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print(f"❌ Backup file is not a valid wallet dictionary")
            return False

        # Check if it looks like wallet data
        if len(data) == 0:
            print(f"⚠️  Warning: Backup file is empty")
            return True  # Empty is still technically valid

        # Validate structure of first wallet
        first_wallet = next(iter(data.values()))
        required_fields = ['address']  # At minimum, must have address
        if not all(field in first_wallet for field in required_fields):
            print(f"⚠️  Warning: Backup may not contain valid wallet data")

        return True

    except json.JSONDecodeError as e:
        print(f"❌ Backup file contains invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating backup: {e}")
        return False


def rollback_wallets(wallets_file: str, backup_file: str | None = None) -> bool:
    """
    Restore wallets from backup file.

    Args:
        wallets_file: Path to wallets.json
        backup_file: Optional specific backup file to restore from.
                     If None, finds most recent backup.

    Returns:
        True if rollback successful
    """
    print("\n🔄 Starting rollback: Restore wallets from backup")
    print("=" * 60)

    # Find backup file if not specified
    if backup_file is None:
        backup_file = find_latest_backup(wallets_file)
        if not backup_file:
            print(f"❌ Error: No backup files found")
            print(f"   Searched for: {wallets_file}.pre-erc20.*")
            return False

    print(f"📂 Using backup file: {backup_file}")

    # Validate backup exists
    if not os.path.exists(backup_file):
        print(f"❌ Error: Backup file not found: {backup_file}")
        return False

    # Validate backup content
    print(f"\n🔍 Validating backup...")
    if not validate_backup(backup_file):
        print(f"❌ Backup validation failed")
        return False

    # Load backup data
    try:
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        print(f"✅ Backup contains {len(backup_data)} wallets")
    except Exception as e:
        print(f"❌ Error loading backup: {e}")
        return False

    # Create safety backup of current file (if exists)
    if os.path.exists(wallets_file):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup = f"{wallets_file}.pre-rollback.{timestamp}"

            with open(wallets_file, 'r') as f:
                current_data = f.read()

            with open(safety_backup, 'w') as f:
                f.write(current_data)

            print(f"✅ Safety backup created: {safety_backup}")
        except Exception as e:
            print(f"⚠️  Warning: Could not create safety backup: {e}")
            response = input("Continue with rollback anyway? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Rollback cancelled")
                return False

    # Restore from backup
    try:
        with open(wallets_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        print(f"\n✅ Wallets restored from backup")
    except Exception as e:
        print(f"❌ Error restoring wallets: {e}")
        return False

    # Verify restoration
    try:
        with open(wallets_file, 'r') as f:
            restored_data = json.load(f)

        if len(restored_data) != len(backup_data):
            print(f"⚠️  Warning: Wallet count mismatch after restore")
            print(f"   Backup: {len(backup_data)}, Restored: {len(restored_data)}")
        else:
            print(f"✅ Verification passed: {len(restored_data)} wallets restored")

    except Exception as e:
        print(f"⚠️  Warning: Could not verify restoration: {e}")

    # Print summary
    print("\n" + "=" * 60)
    print("📊 Rollback Summary:")
    print(f"   Source backup: {backup_file}")
    print(f"   Wallets restored: {len(backup_data)}")
    print(f"   Target file: {wallets_file}")

    # Check if chain field was removed
    sample_wallet = next(iter(backup_data.values()))
    if 'chain' in sample_wallet:
        print(f"   ⚠️  Note: Backup still contains chain field")
    else:
        print(f"   ✅ Chain field removed (pre-migration state)")

    print(f"\n✅ Rollback completed successfully!")
    print("=" * 60)

    return True


def list_available_backups(wallets_file: str):
    """List all available backup files."""
    backup_pattern = f"{wallets_file}.pre-erc20.*"
    backup_files = glob.glob(backup_pattern)

    if not backup_files:
        print(f"No backup files found matching: {backup_pattern}")
        return

    print(f"\n📋 Available backup files:")
    print("=" * 60)

    # Sort by modification time (most recent first)
    backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    for i, backup_file in enumerate(backup_files, 1):
        mtime = os.path.getmtime(backup_file)
        timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        size = os.path.getsize(backup_file)

        # Try to load and count wallets
        try:
            with open(backup_file, 'r') as f:
                data = json.load(f)
            wallet_count = len(data)
            print(f"{i}. {backup_file}")
            print(f"   Created: {timestamp}, Size: {size} bytes, Wallets: {wallet_count}")
        except:
            print(f"{i}. {backup_file}")
            print(f"   Created: {timestamp}, Size: {size} bytes, Wallets: Error reading")

    print("=" * 60)


def main():
    """Main rollback entry point."""
    # Determine wallets file path
    wallets_file = os.getenv('WALLETS_FILE', 'wallets.json')

    # If running from migrations directory, adjust path
    if not os.path.exists(wallets_file) and not os.path.exists(f"{wallets_file}.pre-erc20.*"):
        wallets_file = f"../{wallets_file}"

    print(f"📂 Wallets file: {wallets_file}")

    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            list_available_backups(wallets_file)
            sys.exit(0)
        elif sys.argv[1] == "help":
            print("\nUsage:")
            print("  python rollback_chain_field.py           # Rollback from latest backup")
            print("  python rollback_chain_field.py list      # List available backups")
            print("  python rollback_chain_field.py <file>    # Rollback from specific backup")
            print("  python rollback_chain_field.py help      # Show this help")
            sys.exit(0)
        else:
            # Use specified backup file
            backup_file = sys.argv[1]
            if not os.path.exists(backup_file):
                print(f"❌ Error: Backup file not found: {backup_file}")
                sys.exit(1)

            success = rollback_wallets(wallets_file, backup_file)
            sys.exit(0 if success else 1)

    # Interactive confirmation
    print("\n⚠️  WARNING: This will restore wallets.json from backup!")
    print("   Any changes since the backup was created will be lost.")

    # Show what backup will be used
    latest_backup = find_latest_backup(wallets_file)
    if latest_backup:
        mtime = os.path.getmtime(latest_backup)
        timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n📁 Latest backup found:")
        print(f"   File: {latest_backup}")
        print(f"   Created: {timestamp}")
    else:
        print(f"\n❌ No backup files found")
        print(f"   Use 'python rollback_chain_field.py list' to see available backups")
        sys.exit(1)

    response = input("\nProceed with rollback? (yes/no): ")

    if response.lower() != 'yes':
        print("❌ Rollback cancelled")
        sys.exit(0)

    # Run rollback
    success = rollback_wallets(wallets_file)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
