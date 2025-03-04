import logging
import httpx
from typing import Dict, Any, Optional
from pydantic_ai import RunContext

from ..config.settings import COINGECKO_API_KEY
from ..data.token_database import TOKEN_DATA


async def fetch_token_information(ctx, token_symbol: str, blockchain: str = None) -> Dict[str, Any]:
    """获取代币信息"""
    logging.info(f"Fetching information for {token_symbol} on {blockchain if blockchain else 'any blockchain'}")

    # 使用本地数据库
    result = _check_local_database(token_symbol, blockchain)
    if result:
        return result

    # 尝试从CoinGecko获取
    try:
        result = await _fetch_from_coingecko(token_symbol, blockchain)
        if result:
            return result
    except Exception as e:
        logging.error(f"Error fetching from CoinGecko: {e}")

    # 返回未知结果
    return {
        "token_symbol": token_symbol.upper(),
        "blockchain": blockchain.lower() if blockchain else "Unknown",
        "error": f"No detailed information found for {token_symbol} on {blockchain if blockchain else 'any blockchain'}.",
        "source": "No reliable sources"
    }


def _check_local_database(token_symbol: str, blockchain: str = None) -> Optional[Dict[str, Any]]:
    """从本地数据库检查代币信息"""
    token_symbol = token_symbol.upper()
    blockchain = blockchain.lower() if blockchain else None

    if token_symbol in TOKEN_DATA:
        if blockchain and blockchain in TOKEN_DATA[token_symbol]:
            data = TOKEN_DATA[token_symbol][blockchain]
            return _format_token_data(token_symbol, blockchain, data)
        elif not blockchain:
            # 返回第一个可用的区块链
            first_blockchain = next(iter(TOKEN_DATA[token_symbol]))
            data = TOKEN_DATA[token_symbol][first_blockchain]
            return _format_token_data(token_symbol, first_blockchain, data)

    return None


async def _fetch_from_coingecko(token_symbol: str, blockchain: str = None) -> Optional[Dict[str, Any]]:
    """从CoinGecko获取代币信息"""
    # CoinGecko API实现细节
    # ...

    return None


def _format_token_data(token_symbol: str, blockchain: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化代币数据"""
    return {
        "token_symbol": token_symbol,
        "name": data.get("name"),
        "blockchain": blockchain,
        "contract_address": data.get("contract_address"),
        "project_url": data.get("project_url"),
        "current_price": data.get("current_price"),
        "market_cap": data.get("market_cap"),
        "volume_24h": data.get("volume_24h"),
        "price_change_24h": data.get("price_change_24h"),
        "description": data.get("description"),
        "risks": data.get("risks"),
        "source": "Internal database"
    }