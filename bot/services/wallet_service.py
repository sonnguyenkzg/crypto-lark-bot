#!/usr/bin/env python3
"""
Wallet Service - Manages wallet data from wallets.json
Following the same pattern as your Telegram bot
"""

import json
import logging
import os
from typing import Dict, List, Tuple, Any
from collections import defaultdict

# Import the Tron validator
from bot.services.tron_validator import TronAddressValidator

logger = logging.getLogger(__name__)

class WalletService:
    """Service for managing wallet data from JSON file."""
    
    def __init__(self, wallet_file: str = "wallets.json"):
        self.wallet_file = wallet_file
        self.logger = logger
        self.tron_validator = TronAddressValidator()

    def _load_wallets(self) -> Dict:
        """Load wallets from JSON file."""
        try:
            if not os.path.exists(self.wallet_file):
                # Create empty wallet file if it doesn't exist
                self._save_wallets({})
                return {}
            
            with open(self.wallet_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.logger.info(f"Loaded {len(data)} wallets from {self.wallet_file}")
                return data
        except Exception as e:
            self.logger.error(f"Error loading wallets: {e}")
            return {}

    def _save_wallets(self, wallets: Dict) -> bool:
        """Save wallets to JSON file."""
        try:
            with open(self.wallet_file, 'w', encoding='utf-8') as f:
                json.dump(wallets, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Saved {len(wallets)} wallets to {self.wallet_file}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving wallets: {e}")
            return False

    def list_wallets(self) -> Tuple[bool, Dict]:
        """
        List all wallets organized by company.
        Returns: (success, data)
        Data format: {
            'total_count': int,
            'companies': {
                'company_name': [
                    {'name': 'wallet_name', 'address': 'wallet_address'}, 
                    ...
                ]
            }
        }
        """
        try:
            wallets = self._load_wallets()
            
            if not wallets:
                return True, {
                    'total_count': 0,
                    'companies': {},
                    'message': "📋 **No wallets configured yet.**\n\nUse **/add** to add your first wallet."
                }
            
            # Organize wallets by company
            companies = defaultdict(list)
            total_count = 0
            
            for wallet_key, wallet_data in wallets.items():
                # Assuming wallet_data has company, name, address
                # Based on your screenshot format: "KZP 96G1", "KZP BLG1" etc.
                company = wallet_data.get('company', 'Unknown')
                name = wallet_data.get('name', wallet_key)
                address = wallet_data.get('address', 'Unknown')
                
                companies[company].append({
                    'name': name,
                    'address': address,
                    'key': wallet_key
                })
                total_count += 1
            
            # Sort companies and wallets for consistent display
            sorted_companies = {}
            for company in sorted(companies.keys()):
                sorted_companies[company] = sorted(companies[company], key=lambda x: x['name'])
            
            return True, {
                'total_count': total_count,
                'companies': sorted_companies
            }
            
        except Exception as e:
            self.logger.error(f"Error listing wallets: {e}")
            return False, f"Error loading wallet list: {str(e)}"

    async def add_wallet(self, company: str, name: str, address: str) -> Tuple[bool, str]:
        """Add a new wallet."""
        try:
            wallets = self._load_wallets()
            
            # Create wallet key (you can adjust this format)
            wallet_key = f"{company}_{name}".replace(" ", "_")
            
            # Check if wallet already exists (multiple checks)
            
            # 1. Check if exact wallet key exists
            if wallet_key in wallets:
                return False, f"❌ **Wallet '{name}' already exists for {company}**"
            
            # 2. Check if wallet name already exists (regardless of company)
            for existing_key, existing_data in wallets.items():
                if existing_data.get('name') == name:
                    existing_company = existing_data.get('company', 'Unknown')
                    return False, f"❌ **Wallet name '{name}' already exists in {existing_company}**"
            
            # 3. Check if address already exists
            for existing_key, existing_data in wallets.items():
                if existing_data.get('address') == address:
                    existing_name = existing_data.get('name', 'Unknown')
                    existing_company = existing_data.get('company', 'Unknown')
                    return False, f"❌ **Address already used by '{existing_name}' in {existing_company}**"
            
            # Validate address format and existence on blockchain
            is_valid, validation_message = await self.tron_validator.validate_address(address)
            if not is_valid:
                return False, validation_message
            
            # Add wallet
            wallets[wallet_key] = {
                'company': company,
                'name': name,
                'address': address,
                'created_at': self._get_current_time()
            }
            
            # Save to file
            if self._save_wallets(wallets):
                self.logger.info(f"Added wallet: {company} - {name}")
                return True, f"✅ **Wallet added successfully!**\n\n🏢 **Company:** {company}\n📝 **Name:** {name}\n📍 **Address:** `{address}`"
            else:
                return False, "❌ **Failed to save wallet data.**"
                
        except Exception as e:
            self.logger.error(f"Error adding wallet: {e}")
            return False, f"❌ **Error adding wallet:** {str(e)}"

    def remove_wallet(self, wallet_name: str) -> Tuple[bool, str]:
        """Remove a wallet by name."""
        try:
            wallets = self._load_wallets()
            
            # Find wallet by name (search all wallets)
            wallet_to_remove = None
            for wallet_key, wallet_data in wallets.items():
                if wallet_data.get('name') == wallet_name:
                    wallet_to_remove = wallet_key
                    break
            
            if not wallet_to_remove:
                return False, f"❌ **Wallet '{wallet_name}' not found.**"
            
            # Remove wallet
            removed_wallet = wallets.pop(wallet_to_remove)
            
            # Save to file
            if self._save_wallets(wallets):
                company = removed_wallet.get('company', 'Unknown')
                self.logger.info(f"Removed wallet: {company} - {wallet_name}")
                return True, f"✅ **Wallet removed successfully!**\n\n🏢 **Company:** {company}\n📝 **Name:** {wallet_name}"
            else:
                return False, "❌ **Failed to save wallet data.**"
                
        except Exception as e:
            self.logger.error(f"Error removing wallet: {e}")
            return False, f"❌ **Error removing wallet:** {str(e)}"

    def get_wallet(self, wallet_name: str) -> Tuple[bool, Dict]:
        """Get a specific wallet by name."""
        try:
            wallets = self._load_wallets()
            
            for wallet_key, wallet_data in wallets.items():
                if wallet_data.get('name') == wallet_name:
                    return True, wallet_data
            
            return False, {}
            
        except Exception as e:
            self.logger.error(f"Error getting wallet: {e}")
            return False, {}

    def _get_current_time(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Example wallet.json structure:
"""
{
  "KZP_96G1": {
    "company": "KZP",
    "name": "KZP 96G1", 
    "address": "TNZJSwTSMK4oR79CYzy8BGkGLWNmQxcuM8",
    "created_at": "2024-01-01 12:00:00"
  },
  "KZP_BLG1": {
    "company": "KZP",
    "name": "KZP BLG1",
    "address": "TARvAP993BSFBuQhjc8oGdgv1skNDFtB7Z", 
    "created_at": "2024-01-01 12:01:00"
  }
}
"""