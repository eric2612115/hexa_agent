import logging
from typing import Dict, Any
from ..data.token_database import HIGH_LIQUIDITY_TOKENS


async def check_liquidity(ctx, token_symbol: str, blockchain: str) -> str:
    """检查代币流动性"""
    logging.info(f"Checking liquidity for {token_symbol} on {blockchain}")

    blockchain = blockchain.lower()
    token_symbol = token_symbol.upper()

    if blockchain in HIGH_LIQUIDITY_TOKENS and token_symbol in HIGH_LIQUIDITY_TOKENS[blockchain]:
        return f"""
        Liquidity Analysis for {token_symbol} on {blockchain}:
        - High liquidity across multiple pools
        - Trading should not cause significant slippage
        - 24h volume is healthy
        - Multiple DEXes available for trading
        """

    # 中等流动性代币
    medium_liquidity_tokens = {
        "ethereum": ["COMP", "MKR", "SNX", "YFI", "CRV", "BAL"],
        "polygon": ["QUICK", "SUSHI", "CRV", "BAL"],
    }

    if blockchain in medium_liquidity_tokens and token_symbol in medium_liquidity_tokens[blockchain]:
        return f"""
        Liquidity Analysis for {token_symbol} on {blockchain}:
        - Moderate liquidity in major pools
        - Some slippage may occur with larger trades
        - Trading volume is sufficient for most trades
        - Available on several DEXes
        """

    # 对于未知代币或链，提供谨慎的响应
    return f"""
    Liquidity Analysis for {token_symbol} on {blockchain}:
    - Limited information available
    - Liquidity may be low
    - Trading could result in significant slippage
    - Exercise caution when trading this token
    """