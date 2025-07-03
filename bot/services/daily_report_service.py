#!/usr/bin/env python3
"""
Lark Bot Daily Report Service
Generates automated daily crypto balance reports
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ReportSummary:
    """Summary information for the daily report."""
    total_wallets: int
    successful_checks: int
    failed_checks: int
    total_trx: float
    total_usd: float
    top_wallets: List[Tuple[str, float]]  # (wallet_name, usd_value)
    report_time: datetime

class DailyReportService:
    """
    Service for generating daily crypto balance reports.
    """
    
    def __init__(self, wallet_service=None, config_class=None):
        """
        Initialize daily report service.
        
        Args:
            wallet_service: WalletService instance (will be created if None)
            config_class: Config class for settings
        """
        self.wallet_service = wallet_service
        self.config = config_class
        
    async def generate_daily_report(self, include_details: bool = True, force_refresh: bool = False) -> str:
        """
        Generate comprehensive daily balance report.
        
        Args:
            include_details: Whether to include individual wallet details
            force_refresh: Whether to force fresh balance checks (bypass cache)
            
        Returns:
            Formatted report string
        """
        try:
            logger.info("🚀 Starting daily report generation...")
            
            # Ensure we have a wallet service
            if not self.wallet_service:
                from bot.services.wallet_service import WalletService
                self.wallet_service = WalletService(self.config)
            
            # Get all wallet balances
            async with self.wallet_service:
                balances = await self.wallet_service.get_all_balances(use_cache=not force_refresh)
            
            if not balances:
                return self._create_no_wallets_report()
            
            # Generate report summary
            summary = self._create_report_summary(balances)
            
            # Create formatted report
            report = self._format_daily_report(summary, balances, include_details)
            
            logger.info(f"✅ Daily report generated successfully ({summary.successful_checks}/{summary.total_wallets} wallets)")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error generating daily report: {e}")
            return self._create_error_report(str(e))
    
    def _create_report_summary(self, balances: List[Any]) -> ReportSummary:
        """Create summary information from balance data."""
        total_wallets = len(balances)
        successful_checks = sum(1 for b in balances if b.error is None)
        failed_checks = total_wallets - successful_checks
        
        total_trx = sum(b.balance_trx for b in balances if b.error is None)
        total_usd = sum(b.balance_usd for b in balances if b.error is None)
        
        # Get top wallets by USD value
        successful_balances = [b for b in balances if b.error is None]
        top_wallets = sorted(
            [(b.wallet_name, b.balance_usd) for b in successful_balances],
            key=lambda x: x[1],
            reverse=True
        )[:5]  # Top 5 wallets
        
        return ReportSummary(
            total_wallets=total_wallets,
            successful_checks=successful_checks,
            failed_checks=failed_checks,
            total_trx=total_trx,
            total_usd=total_usd,
            top_wallets=top_wallets,
            report_time=datetime.now()
        )
    
    def _format_daily_report(self, summary: ReportSummary, balances: List[Any], include_details: bool) -> str:
        """Format the complete daily report."""
        report_lines = []
        
        # Header
        report_lines.append("💰 **Daily Crypto Balance Report**")
        report_lines.append(f"📅 {summary.report_time.strftime('%Y-%m-%d %H:%M:%S')} GMT+7")
        report_lines.append("")
        
        # Summary section
        report_lines.extend(self._format_summary_section(summary))
        report_lines.append("")
        
        # Top wallets section
        if summary.top_wallets:
            report_lines.extend(self._format_top_wallets_section(summary.top_wallets))
            report_lines.append("")
        
        # Detailed balances section
        if include_details:
            report_lines.extend(self._format_detailed_balances_section(balances))
            report_lines.append("")
        
        # Footer
        report_lines.extend(self._format_footer_section(summary))
        
        return "\n".join(report_lines)
    
    def _format_summary_section(self, summary: ReportSummary) -> List[str]:
        """Format the summary section."""
        lines = []
        lines.append("📊 **Portfolio Summary**")
        lines.append(f"• **Total Wallets:** {summary.total_wallets}")
        lines.append(f"• **Successful Checks:** {summary.successful_checks} ✅")
        
        if summary.failed_checks > 0:
            lines.append(f"• **Failed Checks:** {summary.failed_checks} ❌")
        
        lines.append(f"• **Total TRX:** {summary.total_trx:,.2f} TRX")
        lines.append(f"• **Total USD Value:** ${summary.total_usd:,.2f}")
        
        # Calculate success rate
        success_rate = (summary.successful_checks / summary.total_wallets) * 100 if summary.total_wallets > 0 else 0
        lines.append(f"• **Success Rate:** {success_rate:.1f}%")
        
        return lines
    
    def _format_top_wallets_section(self, top_wallets: List[Tuple[str, float]]) -> List[str]:
        """Format the top wallets section."""
        lines = []
        lines.append("🏆 **Top Wallets by Value**")
        
        for i, (wallet_name, usd_value) in enumerate(top_wallets, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💎"
            lines.append(f"{emoji} **{wallet_name}**: ${usd_value:,.2f}")
        
        return lines
    
    def _format_detailed_balances_section(self, balances: List[Any]) -> List[str]:
        """Format the detailed balances section."""
        lines = []
        lines.append("📋 **Detailed Balances**")
        
        # Group by company for better organization
        companies = {}
        for balance in balances:
            # Extract company from wallet name (assuming format like "KZP ...")
            company = balance.wallet_name.split()[0] if balance.wallet_name else "Unknown"
            if company not in companies:
                companies[company] = []
            companies[company].append(balance)
        
        for company, company_balances in companies.items():
            lines.append(f"\n**{company} Wallets:**")
            
            for balance in company_balances:
                if balance.error:
                    lines.append(f"❌ **{balance.wallet_name}**: Error - {balance.error}")
                else:
                    # Format main balance line
                    balance_line = f"• **{balance.wallet_name}**: {balance.balance_trx:,.2f} TRX (${balance.balance_usd:,.2f})"
                    lines.append(balance_line)
                    
                    # Add token balances if any
                    if balance.token_balances:
                        significant_tokens = {k: v for k, v in balance.token_balances.items() if v > 0.01}
                        if significant_tokens:
                            token_strs = [f"{v:,.2f} {k}" for k, v in significant_tokens.items()]
                            lines.append(f"  └─ Tokens: {', '.join(token_strs)}")
        
        return lines
    
    def _format_footer_section(self, summary: ReportSummary) -> List[str]:
        """Format the footer section."""
        lines = []
        lines.append("ℹ️ **Report Information**")
        lines.append(f"• Generated at: {summary.report_time.strftime('%H:%M:%S')} GMT+7")
        lines.append(f"• Next report: Tomorrow at 00:00 GMT+7")
        lines.append("• Use `/check [wallet]` for real-time balance")
        lines.append("• Use `/list` to view all configured wallets")
        
        return lines
    
    def _create_no_wallets_report(self) -> str:
        """Create report when no wallets are configured."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f"""💰 **Daily Crypto Balance Report**
📅 {current_time} GMT+7

⚠️ **No Wallets Configured**

No wallets are currently configured for monitoring.

🚀 **Get Started:**
• Use `/add <name> <company> <address>` to add wallets
• Use `/help` for more information
• Contact administrator for wallet setup

Next report: Tomorrow at 00:00 GMT+7"""
    
    def _create_error_report(self, error: str) -> str:
        """Create report when an error occurs."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return f"""💰 **Daily Crypto Balance Report**
📅 {current_time} GMT+7

❌ **Report Generation Failed**

An error occurred while generating the daily report:
`{error}`

🔧 **Troubleshooting:**
• Check network connectivity
• Verify API endpoints are accessible
• Contact administrator if issue persists

Next attempt: Tomorrow at 00:00 GMT+7"""
    
    async def generate_summary_report(self) -> str:
        """
        Generate a condensed summary report (for quick updates).
        
        Returns:
            Formatted summary report string
        """
        try:
            # Ensure we have a wallet service
            if not self.wallet_service:
                from bot.services.wallet_service import WalletService
                self.wallet_service = WalletService(self.config)
            
            async with self.wallet_service:
                balances = await self.wallet_service.get_all_balances(use_cache=True)
            
            if not balances:
                return "📊 **Quick Summary**: No wallets configured"
            
            summary = self._create_report_summary(balances)
            
            # Create condensed report
            report_lines = []
            report_lines.append("📊 **Portfolio Quick Summary**")
            report_lines.append(f"💰 Total: {summary.total_trx:,.2f} TRX (${summary.total_usd:,.2f})")
            report_lines.append(f"📈 Wallets: {summary.successful_checks}/{summary.total_wallets} ✅")
            
            if summary.top_wallets:
                top_wallet = summary.top_wallets[0]
                report_lines.append(f"🏆 Top: {top_wallet[0]} (${top_wallet[1]:,.2f})")
            
            return "\n".join(report_lines)
            
        except Exception as e:
            logger.error(f"❌ Error generating summary report: {e}")
            return f"📊 **Quick Summary**: Error - {e}"
    
    def get_report_schedule_info(self) -> str:
        """Get information about the report schedule."""
        # Calculate next report time (midnight GMT+7)
        now_utc = datetime.now(timezone.utc)
        gmt7_tz = timezone(timedelta(hours=7))
        now_gmt7 = now_utc.astimezone(gmt7_tz)
        
        # Next midnight GMT+7
        next_midnight = (now_gmt7 + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_midnight_utc = next_midnight.astimezone(timezone.utc)
        
        time_until = next_midnight_utc - now_utc
        hours_until = int(time_until.total_seconds() // 3600)
        minutes_until = int((time_until.total_seconds() % 3600) // 60)
        
        info_lines = []
        info_lines.append("⏰ **Daily Report Schedule**")
        info_lines.append(f"• **Report Time:** Daily at 00:00 GMT+7 (17:00 UTC)")
        info_lines.append(f"• **Current Time:** {now_gmt7.strftime('%H:%M:%S')} GMT+7")
        info_lines.append(f"• **Next Report:** {next_midnight.strftime('%Y-%m-%d %H:%M:%S')} GMT+7")
        info_lines.append(f"• **Time Until:** {hours_until}h {minutes_until}m")
        
        return "\n".join(info_lines)

# Mock classes for testing
class MockWalletBalance:
    """Mock wallet balance for testing."""
    def __init__(self, name: str, trx: float, usd: float, tokens: dict = None, error: str = None):
        self.wallet_name = name
        self.balance_trx = trx
        self.balance_usd = usd
        self.token_balances = tokens or {}
        self.error = error

class MockWalletService:
    """Mock wallet service for testing."""
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def get_all_balances(self, use_cache=True):
        return [
            MockWalletBalance("KZP Wallet 1", 100.0, 8.0, {"USDT": 50.0}),
            MockWalletBalance("KZP Wallet 2", 200.0, 16.0, {"USDC": 25.0}),
            MockWalletBalance("KZP Wallet 3", 0.0, 0.0, {}, "Network error"),
        ]

class MockConfig:
    """Mock config for testing."""
    pass

# Testing functions
async def test_daily_report_generation():
    """Test daily report generation."""
    print("🧪 Testing Daily Report Generation...")
    
    try:
        service = DailyReportService(MockWalletService(), MockConfig)
        
        report = await service.generate_daily_report()
        
        # Debug: Print part of the report to see what's generated
        print(f"📄 Generated report preview: {report[:200]}...")
        
        # Check report content (more flexible assertions)
        assert "Daily Crypto Balance Report" in report, "Missing report title"
        assert "Portfolio Summary" in report, "Missing portfolio summary"
        assert "Total Wallets" in report, "Missing total wallets"
        assert "Successful Checks" in report, "Missing successful checks"
        
        # Check for TRX total (should be 300.00 from mock data)
        assert "300.00 TRX" in report or "300 TRX" in report, "Missing TRX total"
        
        # Check for USD total (should be around $24.00)
        assert "24.00" in report or "$24" in report, "Missing USD total"
        
        # Check sections exist
        assert "Top Wallets" in report, "Missing top wallets section"
        assert "Detailed Balances" in report, "Missing detailed balances"
        
        # Check wallet names appear
        assert "KZP Wallet" in report, "Missing wallet names"
        
        # Check error handling
        assert "Network error" in report, "Missing error handling"
        
        print("✅ Daily report generation test passed")
        return True
        
    except AssertionError as e:
        print(f"❌ Daily report generation test failed: {e}")
        print(f"📄 Full report content:\n{report}")
        return False
    except Exception as e:
        print(f"❌ Daily report generation test failed: {e}")
        return False

async def test_summary_report():
    """Test summary report generation."""
    print("🧪 Testing Summary Report...")
    
    try:
        service = DailyReportService(MockWalletService(), MockConfig)
        
        summary = await service.generate_summary_report()
        
        # Check summary content
        assert "Portfolio Quick Summary" in summary
        assert "Total: 300.00 TRX" in summary
        assert "Wallets: 2/3" in summary
        assert "Top: KZP Wallet 2" in summary  # Highest USD value
        
        print("✅ Summary report test passed")
        return True
        
    except Exception as e:
        print(f"❌ Summary report test failed: {e}")
        return False

async def test_no_wallets_report():
    """Test report when no wallets configured."""
    print("🧪 Testing No Wallets Report...")
    
    try:
        class EmptyWalletService:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            async def get_all_balances(self, use_cache=True):
                return []
        
        service = DailyReportService(EmptyWalletService(), MockConfig)
        
        report = await service.generate_daily_report()
        
        # Check no wallets content
        assert "No Wallets Configured" in report
        assert "Get Started" in report
        assert "/add" in report
        
        print("✅ No wallets report test passed")
        return True
        
    except Exception as e:
        print(f"❌ No wallets report test failed: {e}")
        return False

def test_schedule_info():
    """Test schedule information generation."""
    print("🧪 Testing Schedule Info...")
    
    try:
        service = DailyReportService()
        
        schedule_info = service.get_report_schedule_info()
        
        # Check schedule content
        assert "Daily Report Schedule" in schedule_info
        assert "Report Time" in schedule_info
        assert "00:00 GMT+7" in schedule_info
        assert "17:00 UTC" in schedule_info
        assert "Next Report" in schedule_info
        assert "Time Until" in schedule_info
        
        print("✅ Schedule info test passed")
        return True
        
    except Exception as e:
        print(f"❌ Schedule info test failed: {e}")
        return False

def test_report_summary_creation():
    """Test report summary creation."""
    print("🧪 Testing Report Summary Creation...")
    
    try:
        service = DailyReportService()
        
        balances = [
            MockWalletBalance("Wallet 1", 100.0, 8.0),
            MockWalletBalance("Wallet 2", 200.0, 16.0),
            MockWalletBalance("Wallet 3", 0.0, 0.0, {}, "Error"),
        ]
        
        summary = service._create_report_summary(balances)
        
        assert summary.total_wallets == 3
        assert summary.successful_checks == 2
        assert summary.failed_checks == 1
        assert summary.total_trx == 300.0
        assert summary.total_usd == 24.0
        assert len(summary.top_wallets) == 2
        assert summary.top_wallets[0] == ("Wallet 2", 16.0)  # Highest value first
        
        print("✅ Report summary creation test passed")
        return True
        
    except Exception as e:
        print(f"❌ Report summary creation test failed: {e}")
        return False

async def run_all_tests():
    """Run all daily report service tests."""
    print("🚀 Running Daily Report Service Tests...")
    print("=" * 50)
    
    async_tests = [
        test_daily_report_generation,
        test_summary_report,
        test_no_wallets_report
    ]
    
    sync_tests = [
        test_schedule_info,
        test_report_summary_creation
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
        print("🎉 All tests passed! Daily Report Service is ready.")
        print("\n💡 Daily Report Service features:")
        print("- Comprehensive daily balance reports")
        print("- Portfolio summary with top wallets")
        print("- Detailed balance breakdown by company")
        print("- Error handling and fallback reports")
        print("- Quick summary reports")
        print("- Schedule information display")
        print("- Token balance detection")
        print("- Success rate tracking")
    else:
        print("❌ Some tests failed. Please check implementation.")
    
    return passed == total

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())