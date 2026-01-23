"""
Chain Detector Utility

Automatically detects blockchain type from wallet address format.
Supports TRC20 (Tron) and ERC20 (Ethereum) addresses.
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def detect_chain_from_address(address: str) -> Optional[str]:
    """
    Auto-detect blockchain from address format.

    Args:
        address: Wallet address string

    Returns:
        "TRC20" for Tron addresses (starts with 'T', 33-35 chars)
        "ERC20" for Ethereum addresses (starts with '0x', 42 chars, hexadecimal)
        None if address format is invalid or unknown

    Examples:
        >>> detect_chain_from_address("TEhmKXCPgX6LyjQ3t9skuSyUQBxwaWfY4KS")
        "TRC20"

        >>> detect_chain_from_address("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
        "ERC20"

        >>> detect_chain_from_address("invalid_address")
        None
    """
    if not address or not isinstance(address, str):
        logger.warning(f"Invalid address input: {address}")
        return None

    address = address.strip()

    # TRC20 Detection: Starts with 'T', 33-35 chars, alphanumeric
    if address.startswith('T') and 33 <= len(address) <= 35:
        # Verify it's alphanumeric (basic format check)
        if address[1:].replace('_', '').replace('-', '').isalnum():
            logger.debug(f"Detected TRC20 address: {address[:10]}...")
            return "TRC20"

    # ERC20 Detection: Starts with '0x', exactly 42 chars, hexadecimal
    if address.startswith('0x') and len(address) == 42:
        # Verify it's valid hexadecimal
        try:
            int(address[2:], 16)  # Try parsing as hex
            logger.debug(f"Detected ERC20 address: {address[:10]}...")
            return "ERC20"
        except ValueError:
            logger.warning(f"Address starts with 0x but is not valid hex: {address[:10]}...")
            return None

    logger.warning(f"Unknown address format: {address[:10]}... (length: {len(address)})")
    return None


def get_chain_emoji(chain: str) -> str:
    """
    Get emoji indicator for blockchain type.

    Args:
        chain: Chain identifier ("TRC20" or "ERC20")

    Returns:
        🟢 for TRC20 (Tron)
        🔷 for ERC20 (Ethereum)
        ⚪ for unknown chains
    """
    emoji_map = {
        "TRC20": "🟢",
        "ERC20": "🔷"
    }
    return emoji_map.get(chain, "⚪")


def get_chain_display_name(chain: str) -> str:
    """
    Get human-readable chain name.

    Args:
        chain: Chain identifier ("TRC20" or "ERC20")

    Returns:
        "Tron (TRC20)" or "Ethereum (ERC20)" or original value if unknown
    """
    display_names = {
        "TRC20": "Tron (TRC20)",
        "ERC20": "Ethereum (ERC20)"
    }
    return display_names.get(chain, chain)
