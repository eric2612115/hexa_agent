# 环境变量和配置管理
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Google Cloud 配置
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"

# API 密钥
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
CMC_API_KEY = os.getenv("CMC_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# 通用配置
USER_AGENT = "TradingAssistant/1.0"
RETRIES = 3

# 数据来源配置
CRYPTO_DATA_SOURCES = {
    "market_data": [
        {"name": "CoinMarketCap", "url": "https://coinmarketcap.com", "priority": 1, "type": "market_data"},
        {"name": "CoinGecko", "url": "https://coingecko.com", "priority": 1, "type": "market_data"},
        {"name": "TradingView", "url": "https://tradingview.com", "priority": 2, "type": "charts"}
    ],
    "news": [
        {"name": "CoinTelegraph", "url": "https://cointelegraph.com", "priority": 1, "type": "news"},
        {"name": "CryptoSlate", "url": "https://cryptoslate.com", "priority": 1, "type": "news"},
        {"name": "Crypto Daily", "url": "https://cryptodaily.co.uk", "priority": 2, "type": "news"}
    ],
    "security": [
        {"name": "Etherscan", "url": "https://etherscan.io", "priority": 1, "type": "security"},
        {"name": "Certik", "url": "https://certik.com", "priority": 1, "type": "security_audit"},
        {"name": "TokenSniffer", "url": "https://tokensniffer.com", "priority": 1, "type": "security"},
        {"name": "Cyberscope", "url": "https://cyberscope.io", "priority": 2, "type": "security"},
        {"name": "SolidityScan", "url": "https://solidityscan.com", "priority": 2, "type": "security_scanner"}
    ],
    "apis": [
        {"name": "CoinMarketCap API", "url": "https://coinmarketcap.com/api", "priority": 1, "type": "price_api"},
        {"name": "CoinGecko API", "url": "https://api.coingecko.com", "priority": 1, "type": "price_api"},
        {"name": "Uniswap API", "url": "https://api.uniswap.org", "priority": 2, "type": "dex_api"},
        {"name": "PancakeSwap API", "url": "https://api.pancakeswap.com", "priority": 2, "type": "dex_api"},
        {"name": "Moralis Price API", "url": "https://developers.moralis.com", "priority": 3, "type": "price_api"}
    ]
}