import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

async def check_market_sentiment(ctx, token_symbol: str = None) -> Dict[str, Any]:
    """检查市场情绪"""
    logging.info(f"Analyzing market sentiment{' for '+token_symbol if token_symbol else ''}")

    # 模拟从外部API获取市场数据
    # 这里使用示例数据
    market_data = {
        "total_market_cap": 2158000000000,  # 2.158万亿美元
        "total_volume_24h": 58700000000,    # 587亿美元
        "btc_dominance": 51.2,              # 比特币占比51.2%
        "volume_change_24h": 3.2,           # 交易量上升3.2%
        "market_cap_change_24h": 1.8,       # 市值上升1.8%
        "fear_greed_index": 65,             # 恐惧与贪婪指数(0-100)
        "major_tokens": [
            {"symbol": "BTC", "price_change_24h": 1.5},
            {"symbol": "ETH", "price_change_24h": 2.3},
            {"symbol": "BNB", "price_change_24h": 0.8},
            {"symbol": "SOL", "price_change_24h": 4.1},
            {"symbol": "ADA", "price_change_24h": -1.2}
        ]
    }

    # 如果指定了代币，查找该代币信息
    token_data = None
    if token_symbol:
        token_match = next((t for t in market_data["major_tokens"] if t["symbol"] == token_symbol.upper()), None)
        if token_match:
            token_data = token_match

    # 分析看涨信号
    bullish_signals = []
    if market_data["market_cap_change_24h"] > 0:
        bullish_signals.append(f"Total market cap increased by {market_data['market_cap_change_24h']}%")
    if market_data["volume_change_24h"] > 0:
        bullish_signals.append(f"24-hour trading volume increased by {market_data['volume_change_24h']}%")
    if market_data["fear_greed_index"] > 50:
        bullish_signals.append(f"Fear & Greed Index at {market_data['fear_greed_index']} (Greed)")

    # 分析看跌信号
    bearish_signals = []
    if market_data["market_cap_change_24h"] < 0:
        bearish_signals.append(f"Total market cap decreased by {abs(market_data['market_cap_change_24h'])}%")
    if market_data["volume_change_24h"] < 0:
        bearish_signals.append(f"24-hour trading volume decreased by {abs(market_data['volume_change_24h'])}%")
    if market_data["fear_greed_index"] < 50:
        bearish_signals.append(f"Fear & Greed Index at {market_data['fear_greed_index']} (Fear)")

    # 根据信号判断整体市场情绪
    if len(bullish_signals) > len(bearish_signals):
        overall_sentiment = "Bullish"
    elif len(bearish_signals) > len(bullish_signals):
        overall_sentiment = "Bearish"
    else:
        overall_sentiment = "Neutral"

    # 如果指定了代币，分析该代币的情绪
    token_sentiment = None
    if token_data:
        price_change = token_data["price_change_24h"]
        if price_change > 2:
            token_sentiment = "Strongly Bullish"
        elif price_change > 0:
            token_sentiment = "Mildly Bullish"
        elif price_change < -2:
            token_sentiment = "Strongly Bearish"
        elif price_change < 0:
            token_sentiment = "Mildly Bearish"
        else:
            token_sentiment = "Neutral"

    # 返回分析结果
    return {
        "overall_sentiment": overall_sentiment,
        "token_sentiment": token_sentiment,
        "bullish_signals": bullish_signals,
        "bearish_signals": bearish_signals,
        "trading_volume_change": f"{'Increased' if market_data['volume_change_24h'] > 0 else 'Decreased'} by {abs(market_data['volume_change_24h'])}%",
        "fear_greed_index": market_data['fear_greed_index'],
        "fear_greed_interpretation": "Greed" if market_data["fear_greed_index"] > 50 else "Fear",
        "raw_data": market_data
    }