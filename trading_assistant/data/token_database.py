# 本地代币数据库

TOKEN_DATA = {
    "ETH": {
        "ethereum": {
            "name": "Ethereum",
            "contract_address": "Native",
            "description": "Native token of the Ethereum blockchain",
            "project_url": "https://ethereum.org",
            "risks": "Low risk, established project",
            "current_price": 3506.42,
            "market_cap": 420912345678,
            "volume_24h": 15789012345,
            "price_change_24h": 2.51
        }
    },
    "USDC": {
        "ethereum": {
            "name": "USD Coin",
            "contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "description": "Stablecoin pegged to the US Dollar",
            "project_url": "https://www.circle.com/en/usdc",
            "risks": "Low risk, established stablecoin",
            "current_price": 1.00,
            "market_cap": 31500000000,
            "volume_24h": 2800000000,
            "price_change_24h": 0.01
        },
        "polygon": {
            "name": "USD Coin",
            "contract_address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "description": "Stablecoin pegged to the US Dollar (Polygon)",
            "project_url": "https://www.circle.com/en/usdc",
            "risks": "Low risk, established stablecoin",
            "current_price": 1.00,
            "market_cap": 31500000000,
            "volume_24h": 780000000,
            "price_change_24h": 0.00
        }
    },
    # 其他代币...
}

# 安全合约列表
SAFE_CONTRACTS = {
    "ethereum": [
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # LINK
        # 其他安全合约...
    ],
    "polygon": [
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
        "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",  # LINK
        # 其他安全合约...
    ],
    # 其他区块链...
}

# 高流动性代币
HIGH_LIQUIDITY_TOKENS = {
    "ethereum": ["ETH", "USDC", "USDT", "WBTC", "LINK", "UNI", "DAI", "AAVE"],
    "polygon": ["MATIC", "USDC", "USDT", "WBTC", "LINK", "AAVE"],
    # 其他区块链...
}