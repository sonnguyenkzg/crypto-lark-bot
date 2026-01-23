#!/usr/bin/env python3
"""
Migration Script: Add Chain Field to Wallets

This script adds a "chain" field to all existing wallets in wallets.json.
All existing wallets are TRC20, so they will be tagged with "chain": "TRC20".

Features:
- Creates timestamped backup before migration
- Validates all addresses are TRC20 format
- Adds chain field to each wallet
- Preserves all existing data
- Logs detailed migration summary
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def create_backup(wallets_file: str) -> str:
    """
    Create timestamped backup of wallets file.

    Args:
        wallets_file: Path to wallets.json

    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{wallets_file}.pre-erc20.{timestamp}"

    # Copy original file
    with open(wallets_file, 'r') as f:
        original_data = f.read()

    with open(backup_file, 'w') as f:
        f.write(original_data)

    print(f"✅ Backup created: {backup_file}")
    return backup_file


def validate_trc20_address(address: str) -> bool:
    """
    Validate that address follows TRC20 format.

    Args:
        address: Wallet address to validate

    Returns:
        True if valid TRC20 address
    """
    if not address:
        return False

    # TRC20 addresses: Start with 'T', 33-35 chars, alphanumeric
    return (
        address.startswith('T') and
        33 <= len(address) <= 35 and
        address[1:].isalnum()
    )


def migrate_wallets(wallets_file: str) -> bool:
    """
    Add chain field to all wallets in the JSON file.

    Args:
        wallets_file: Path to wallets.json

    Returns:
        True if migration successful, False otherwise
    """
    print("\n🔄 Starting migration: Add chain field to wallets")
    print("=" * 60)

    # Check if file exists
    if not os.path.exists(wallets_file):
        print(f"❌ Error: Wallets file not found: {wallets_file}")
        return False

    # Create backup
    try:
        backup_file = create_backup(wallets_file)
    except Exception as e:
        print(f"❌ Error creating backup: {e}")
        return False

    # Load wallets
    try:
        with open(wallets_file, 'r') as f:
            wallets = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {wallets_file}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error loading wallets: {e}")
        return False

    print(f"\n📄 Loaded {len(wallets)} wallets from {wallets_file}")

    # Validate and migrate
    migrated_count = 0
    skipped_count = 0
    errors = []

    for wallet_key, wallet_data in wallets.items():
        # Check if chain field already exists
        if 'chain' in wallet_data:
            print(f"⏭️  Skipping {wallet_key}: chain field already exists ({wallet_data['chain']})")
            skipped_count += 1
            continue

        # Get wallet address
        address = wallet_data.get('address', '')

        # Validate it's a TRC20 address
        if not validate_trc20_address(address):
            error_msg = f"Invalid TRC20 address for wallet '{wallet_key}': {address}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            continue

        # Add chain field
        wallet_data['chain'] = 'TRC20'
        migrated_count += 1
        print(f"✅ Migrated {wallet_key}: {address[:10]}... → TRC20")

    # Save updated wallets
    if migrated_count > 0:
        try:
            with open(wallets_file, 'w') as f:
                json.dump(wallets, f, indent=2)
            print(f"\n✅ Saved updated wallets to {wallets_file}")
        except Exception as e:
            print(f"\n❌ Error saving wallets: {e}")
            print(f"💡 You can restore from backup: {backup_file}")
            return False

    # Print summary
    print("\n" + "=" * 60)
    print("📊 Migration Summary:")
    print(f"   Total wallets: {len(wallets)}")
    print(f"   Migrated: {migrated_count}")
    print(f"   Skipped (already migrated): {skipped_count}")
    print(f"   Errors: {len(errors)}")

    if errors:
        print("\n⚠️  Errors encountered:")
        for error in errors:
            print(f"   - {error}")

    if migrated_count > 0:
        print(f"\n✅ Migration completed successfully!")
        print(f"💾 Backup saved at: {backup_file}")
        print(f"💡 To rollback: cp {backup_file} {wallets_file}")
    elif skipped_count > 0:
        print(f"\n✅ All wallets already have chain field - no changes needed")
    else:
        print(f"\n⚠️  No wallets were migrated")

    print("=" * 60)

    return len(errors) == 0


def main():
    """Main migration entry point."""
    # Determine wallets file path
    wallets_file = os.getenv('WALLETS_FILE', 'wallets.json')

    # If running from migrations directory, adjust path
    if not os.path.exists(wallets_file):
        wallets_file = f"../{wallets_file}"

    if not os.path.exists(wallets_file):
        print(f"❌ Error: Cannot find wallets.json")
        print(f"   Tried: WALLETS_FILE env var, ./wallets.json, ../wallets.json")
        sys.exit(1)

    print(f"📂 Using wallets file: {wallets_file}")

    # Run migration
    success = migrate_wallets(wallets_file)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
