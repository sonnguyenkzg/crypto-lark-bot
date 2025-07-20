# UAT Test Cases - Crypto Wallet Bot

## Overview
This document contains User Acceptance Testing (UAT) test cases for the Crypto Wallet Bot system. The bot manages TRON wallet addresses and provides balance checking functionality through Lark messaging platform.

## Test Environment
- **Platform**: Lark Bot Interface
- **Wallet Storage**: JSON file format
- **Network**: TRON blockchain
- **Address Type**: TRC20 addresses

---

## Test Categories

### 1. Basic Command Functionality

#### TC-001: Display Help Information
**Objective**: Verify help command displays available commands
- **Command**: `/help`
- **Expected Result**: ✅ Display list of all available commands with descriptions
- **Priority**: High

#### TC-002: List All Wallets
**Objective**: Verify list command shows all configured wallets
- **Command**: `/list`
- **Expected Result**: ✅ Display wallets organized by company with addresses
- **Priority**: High

#### TC-003: Bot Status Check
**Objective**: Verify start command shows bot connectivity
- **Command**: `/start`
- **Expected Result**: ✅ Display welcome message and bot status
- **Priority**: Medium

---

### 2. Wallet Management - Add Operations

#### TC-101: Add Valid Wallet
**Objective**: Add new wallet with valid TRON address
- **Command**: `/add "TEST" "TEST WALLET 1" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ✅ Wallet added successfully with confirmation message
- **Priority**: High

#### TC-102: Add Duplicate Wallet Name
**Objective**: Prevent adding wallet with existing name
- **Command**: `/add "KZP" "KZP 96G1" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ❌ Error message: "Wallet name already exists"
- **Priority**: High

#### TC-103: Add Duplicate Address
**Objective**: Prevent adding existing wallet address
- **Command**: `/add "TEST" "NEW WALLET" "TEhmKXCPgX64yJQ3t9skuSyUQBxwaWY4KS"`
- **Expected Result**: ❌ Error message: "Address already used by [wallet] in [company]"
- **Priority**: High

#### TC-104: Add Invalid Address Format
**Objective**: Validate TRON address format
- **Command**: `/add "TEST" "TEST WALLET" "InvalidAddress123"`
- **Expected Result**: ❌ Error message: "Invalid TRC20 address format"
- **Priority**: Medium

#### TC-105: Add Missing Arguments
**Objective**: Ensure all required parameters provided
- **Command**: `/add "COMPANY" "WALLET"`
- **Expected Result**: ❌ Error message: "Expected 3 quoted arguments, found 2"
- **Priority**: Medium

#### TC-106: Add Empty Company Name
**Objective**: Validate company name is not empty
- **Command**: `/add "" "WALLET NAME" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ❌ Error message: "Company cannot be empty"
- **Priority**: Low

---

### 3. Wallet Management - Remove Operations

#### TC-201: Remove by Wallet Name
**Objective**: Remove wallet using exact wallet name
- **Command**: `/remove "KZP 96G1"`
- **Expected Result**: ✅ Wallet removed with confirmation details
- **Priority**: High

#### TC-202: Remove by TRON Address
**Objective**: Remove wallet using TRON address
- **Command**: `/remove "TARvAP993BSFBuQhjc8oG4gviskNDftB7Z"`
- **Expected Result**: ✅ Wallet removed with confirmation details
- **Priority**: High

#### TC-203: Remove Non-Existent Wallet
**Objective**: Handle removal of non-existent wallet
- **Command**: `/remove "FAKE WALLET"`
- **Expected Result**: ❌ Error message with suggested similar wallet names
- **Priority**: Medium

#### TC-204: Remove Case Insensitive
**Objective**: Remove wallet with different case
- **Command**: `/remove "kzp wdb1"`
- **Expected Result**: ✅ Find and remove "KZP WDB1" successfully
- **Priority**: Medium

#### TC-205: Remove Empty Identifier
**Objective**: Handle empty wallet identifier
- **Command**: `/remove ""`
- **Expected Result**: ❌ Error message: "Wallet name or address cannot be empty"
- **Priority**: Low

#### TC-206: Remove Without Quotes
**Objective**: Ensure proper quote usage
- **Command**: `/remove KZP WDB1`
- **Expected Result**: ❌ Error message about missing quotes
- **Priority**: Low

---

### 4. Balance Checking Operations

#### TC-301: Check All Wallets
**Objective**: Display balance table for all wallets
- **Command**: `/check`
- **Expected Result**: ✅ Balance table grouped by company with totals
- **Priority**: High

#### TC-302: Check Specific Wallet by Name
**Objective**: Check balance for single wallet
- **Command**: `/check "KZP WDB1"`
- **Expected Result**: ✅ Balance display for specified wallet only
- **Priority**: High

#### TC-303: Check Multiple Wallets
**Objective**: Check balance for multiple specific wallets
- **Command**: `/check "KZP WDB1" "KZP PH 1"`
- **Expected Result**: ✅ Balance table for specified wallets only
- **Priority**: Medium

#### TC-304: Check by TRON Address
**Objective**: Check balance using wallet address
- **Command**: `/check "TEhmKXCPgX64yJQ3t9skuSyUQBxwaWY4KS"`
- **Expected Result**: ✅ Balance display identifying wallet by address
- **Priority**: Medium

#### TC-305: Check External Address
**Objective**: Check balance for address not in wallet list
- **Command**: `/check "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ✅ Balance display for external address
- **Priority**: Low

#### TC-306: Check Non-Existent Wallet
**Objective**: Handle balance check for invalid wallet
- **Command**: `/check "FAKE WALLET"`
- **Expected Result**: ❌ Error message with available wallet list
- **Priority**: Medium

---

### 5. Data Integrity & Edge Cases

#### TC-401: JSON Structure Validation
**Objective**: Verify wallet data storage format
- **Verification**: Check `wallets.json` file structure
- **Expected Result**: 
  - ✅ Keys are wallet names (e.g., "KZP TH 1")
  - ✅ Each entry contains: company, wallet, address, created_at
  - ❌ No underscore keys (e.g., "KZP_TH_1")
- **Priority**: High

#### TC-402: Quote Type Flexibility
**Objective**: Support both single and double quotes
- **Command**: `/add 'TEST' 'SINGLE QUOTE WALLET' 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'`
- **Expected Result**: ✅ Command processed successfully
- **Priority**: Low

#### TC-403: Long Wallet Names
**Objective**: Handle extended wallet names
- **Command**: `/add "TEST" "TEST WALLET WITH VERY LONG NAME FOR TESTING" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ✅ Wallet added successfully
- **Priority**: Low

#### TC-404: Special Characters in Names
**Objective**: Handle special characters in wallet names
- **Command**: `/add "TEST" "TEST-WALLET_123" "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"`
- **Expected Result**: ✅ Wallet added with special characters preserved
- **Priority**: Low

#### TC-405: Mixed Case Commands
**Objective**: Test case insensitivity in operations
- **Command**: `/CHECK "KzP pH 1"`
- **Expected Result**: ✅ Find and check wallet successfully
- **Priority**: Medium

---

### 6. Error Handling & Security

#### TC-501: Invalid Command
**Objective**: Handle unrecognized commands
- **Command**: `/invalidcommand`
- **Expected Result**: ❌ Unknown command message
- **Priority**: Medium

#### TC-502: Malformed Command Structure
**Objective**: Handle malformed quote structures
- **Command**: `/add "COMPANY "WALLET" "ADDRESS"`
- **Expected Result**: ❌ Graceful error handling for malformed quotes
- **Priority**: Low

#### TC-503: Empty Command
**Objective**: Handle empty command input
- **Command**: `/`
- **Expected Result**: ❌ Graceful error handling
- **Priority**: Low

#### TC-504: Excessive Arguments
**Objective**: Handle commands with too many parameters
- **Command**: `/remove "wallet1" "wallet2" "wallet3"`
- **Expected Result**: ❌ Error: "Expected 1 argument, found 3"
- **Priority**: Low

---

## Test Execution Checklist

### Pre-Test Setup
- [ ] Bot is running and connected to Lark
- [ ] Existing wallet data is backed up
- [ ] Test environment is isolated from production

### Post-Test Validation
- [ ] All wallet operations complete successfully
- [ ] JSON file structure remains consistent
- [ ] No data corruption in wallet storage
- [ ] Error messages are user-friendly and actionable
- [ ] Balance checking integrates properly with TRON network

### Critical Success Criteria
- [ ] ✅ Remove by wallet name works
- [ ] ✅ Remove by TRON address works
- [ ] ✅ Add wallet creates correct JSON structure
- [ ] ✅ Duplicate detection prevents data conflicts
- [ ] ✅ Case-insensitive matching functions properly
- [ ] ✅ Balance checking works for all wallet types

---

## Test Data Cleanup

After testing completion, remove test wallets:
```bash
/remove "TEST WALLET 1"
/remove "TEST WALLET WITH VERY LONG NAME FOR TESTING"
/remove "SINGLE QUOTE WALLET"
/remove "TEST-WALLET_123"
```

---

## Reporting Template

### Test Results Summary
| Test Category | Passed | Failed | Skipped | Total |
|---------------|--------|--------|---------|-------|
| Basic Commands | - | - | - | 3 |
| Add Operations | - | - | - | 6 |
| Remove Operations | - | - | - | 6 |
| Balance Checking | - | - | - | 6 |
| Data Integrity | - | - | - | 5 |
| Error Handling | - | - | - | 4 |
| **Total** | **-** | **-** | **-** | **30** |

### Critical Issues
Document any failed test cases with:
- Test Case ID
- Description of failure
- Expected vs actual result
- Steps to reproduce
- Severity level

---

*Document Version: 1.0*  