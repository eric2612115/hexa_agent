#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
import hmac
import base64
import httpx
import aiohttp
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.vertexai import VertexAIModel

# --- 基本設定 ---
load_dotenv(find_dotenv())
USER_AGENT = "TradingAssistant/1.0"
RETRIES = 3
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
sys.excepthook = lambda *args: None

# --- Google Cloud 設定 ---
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
# SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

import os

SERVICE_ACCOUNT_FILE = os.path.abspath("../gemini_defi_agent.json")
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"

# --- API Keys ---
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# OKX Web3 credentials
OKX_WEB3_PROJECT_ID = os.getenv("OKX_WEB3_PROJECT_ID")
OKX_WEB3_PROJECT_KEY = os.getenv("OKX_WEB3_PROJECT_KEY")
OKX_WEB3_PROJECT_SECRET = os.getenv("OKX_WEB3_PROJECT_SECRET")
OKX_WEB3_PROJECT_PASSWRD = os.getenv("OKX_WEB3_PROJECT_PASSWRD")


# --- 環境變數檢查 ---
if not PROJECT_ID or not SERVICE_ACCOUNT_FILE:
    logging.error("GOOGLE_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS must be set.")
    sys.exit(1)  # 退出程式

if not SERPAPI_API_KEY:
    logging.warning("SERPAPI_API_KEY not set. SerpApi searches will be skipped.")

if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
    logging.warning("GOOGLE_SEARCH_API_KEY or GOOGLE_CSE_ID not set. Google searches will be skipped.")

# --- 搜尋引擎優先級 ---
SEARCH_ENGINE_PRIORITY = ["serpapi", "google", "none"]  # 可自行調整

print(f"Using model: {MODEL} in {LOCATION}")


# --- Client Classes ---
class OkxWeb3Client:
    BASE_URL = "https://www.okx.com"
    ENDPOINTS = {
        "v5": {
            "token_price": "/api/v5/wallet/token/current-price",  # 获取当前币价
            "historical_price": "/api/v5/wallet/token/historical-price",  # 获取历史币价
            "token_detail": "/api/v5/wallet/token/token-detail",  # 获取代币详情
            "supported_chains": "/api/v5/wallet/chain/supported-chains",  # 获取支持的区块链
            "total_value": "/api/v5/wallet/asset/total-value",  # 获取钱包总估值
            "total_value_by_address": "/api/v5/wallet/asset/total-value-by-address",  # 获取钱包总估值
            "token_balances": "/api/v5/wallet/asset/all-token-balances-by-address",  # 获取钱包资产明细
            "transactions_by_address": "/api/v5/wallet/post-transaction/transactions-by-address",  # 地址维度交易历史
            "transactions_by_account": "/api/v5/wallet/post-transaction/transactions",  # 账户维度交易历史
            "explore_token_list": "/api/v5/defi/explore/token/list",  # 探索代币列表
        }
    }

    def __init__(self, project_id: str, api_key: str, api_secret: str, api_passphrase: str):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing OkxWeb3Client...")

        self.project_id = project_id
        self.api_key = api_key
        self.api_secret = api_secret.encode('utf-8')  # HMAC 需要 bytes
        self.api_passphrase = api_passphrase
        self.session = None
        self.logger.info("OkxWeb3Client initialized.")

    async def initialize(self):
        """异步初始化 ClientSession"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self.logger.info("OkxWeb3Client session initialized.")

    async def close(self):
        """关闭 ClientSession"""
        if self.session:
            await self.session.close()
            self.session = None
            self.logger.info("OkxWeb3Client session closed.")

    def _get_timestamp(self) -> str:
        """ 获取当前 UTC 时间戳，格式符合 OKX 要求 """
        return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

    def _sign_request(self, method: str, request_path: str, body: str = "") -> tuple:
        """
        计算 OKX API 签名
        :param method: HTTP 方法 ('GET', 'POST')
        :param request_path: 请求路径，例如 `/api/v5/account/balance`
        :param body: 请求体字符串，`GET` 请求时应为空
        :return: (timestamp, signature)
        """
        timestamp = self._get_timestamp()
        prehash_string = f"{timestamp}{method}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret, prehash_string.encode('utf-8'), digestmod='sha256').digest()
        ).decode()
        return timestamp, signature

    async def _send_request(self, method: str, endpoint: str, params: dict = None, body: dict = None):
        """
        发送 HTTP 请求
        :param method: 'GET' or 'POST'
        :param endpoint: API 端点，例如 `/api/v5/account/balance`
        :param params: 仅用于 `GET` 请求，传入 URL 查询参数
        :param body: 仅用于 `POST` 请求，传入 JSON 数据
        :return: 响应 JSON 数据
        """
        if self.session is None:
            await self.initialize()

        request_path = endpoint
        if params:
            query_string = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
            if query_string:
                request_path = f"{endpoint}?{query_string}"

        body_str = json.dumps(body) if (body and method == "POST") else ""  # 仅 `POST` 需要 body
        print(f"Request URL: {self.BASE_URL}{request_path}")
        print(f"Request Body: {body_str}" if body else "No Body for GET Request")

        timestamp, signature = self._sign_request(method, request_path, body_str)

        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-PROJECT": self.project_id,
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "OK-ACCESS-TIMESTAMP": timestamp
        }

        url = f"{self.BASE_URL}{request_path}"

        try:
            async with self.session.request(
                    method, url, headers=headers, json=body if (body and method == "POST") else None
            ) as response:
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error in _send_request: {e}")
            return {"error": str(e)}

    # Add other methods here...
    async def get_token_price(self, token_address: str, chain_id: str):
        """ 查询代币价格 (模拟实现) """
        self.logger.info(f"Getting token price for {token_address} on chain {chain_id}")
        try:
            data = [
                {"chainIndex": chain_id, "tokenAddress": token_address}
            ]
            return await self._send_request("POST", self.ENDPOINTS["v5"]["token_price"], body=data)
        except Exception as e:
            self.logger.error(f"Error getting token price: {e}")
            return {"error": str(e), "message": "Failed to get token price"}

    async def get_historical_price(self, chain_index: str, token_address: str, limit: int = 5, period: str = "5m"):
        """ 查询代币历史价格 (模拟实现) """
        try:
            params = {
                "chainIndex": chain_index,
                "tokenAddress": token_address,
                "limit": limit,
                "period": period
            }
            return await self._send_request("GET", self.ENDPOINTS["v5"]["historical_price"], params=params)
        except Exception as e:
            self.logger.error(f"Error getting historical price: {e}")
            return {"error": str(e), "message": "Failed to get historical price"}

    async def get_token_detail(self, chain_index: str, token_address: str):
        """ 获取代币详细信息 (模拟实现) """
        try:
            params = {
                "chainIndex": chain_index,
                "tokenAddress": token_address
            }
            return await self._send_request("GET", self.ENDPOINTS["v5"]["token_detail"], params=params)
        except Exception as e:
            self.logger.error(f"Error getting token detail: {e}")
            return {"error": str(e), "message": "Failed to get token detail"}

    async def get_total_value_by_address(self, address: str, chains: str):
        """ 获取钱包总估值 (模拟实现) """
        try:
            params = {"address": address, "chains": chains}
            return await self._send_request("GET", self.ENDPOINTS["v5"]["total_value_by_address"], params=params)
        except Exception as e:
            self.logger.error(f"Error getting total value: {e}")
            return {"error": str(e), "message": "Failed to get total value"}

    async def get_transactions_by_address(self, address: str, chains: list = None):
        """ 获取地址维度的交易历史 (模拟实现) """
        try:
            if not chains:
                chains = ["1", "56"]  # 默认以太坊和BSC
            chains_str = ",".join(chains)
            params = {"address": address, "chains": chains_str, "limit": 20}
            return await self._send_request("GET", self.ENDPOINTS["v5"]["transactions_by_address"], params=params)
        except Exception as e:
            self.logger.error(f"Error getting transactions: {e}")
            return {"error": str(e), "message": "Failed to get transactions"}


class ThirdPartyClient:
    BASE_URL = "https://hexa-guard-backend.onrender.com"

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ThirdPartyClient...")
        self.session = None
        self.logger.info("ThirdPartyClient initialized.")

    async def initialize(self):
        """异步初始化 ClientSession"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self.logger.info("ThirdPartyClient session initialized.")

    async def close(self):
        """关闭 ClientSession"""
        if self.session:
            await self.session.close()
            self.session = None
            self.logger.info("ThirdPartyClient session closed.")

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """发送GET请求"""
        if self.session is None:
            await self.initialize()

        url = f"{self.BASE_URL}/{path}"
        try:
            async with self.session.get(url, params=params) as response:
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error in GET request: {e}")
            return {"error": str(e)}

    async def _post_request(self, path: str, data: dict) -> dict:
        """发送POST请求"""
        if self.session is None:
            await self.initialize()

        url = f"{self.BASE_URL}/{path}"
        try:
            async with self.session.post(url, json=data) as response:
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error in POST request: {e}")
            return {"error": str(e)}

    async def get_security(self, input_text: str):
        """获取文本安全性"""
        try:
            data = {
                "input_text": input_text
            }
            return await self._post_request("get-security", data)
        except Exception as e:
            self.logger.error(f"Error getting security: {e}")
            return {"error": str(e), "message": "Failed to get security information"}



# Initialize clients as None
okx_client: OkxWeb3Client = None
third_party_client: ThirdPartyClient = None

# --- MODELS ---
class TokenInfo(BaseModel):
    """Information about a token."""
    symbol: str = Field(description="The token symbol (e.g. ETH, USDC)")
    blockchain: str = Field(description="The blockchain the token is on (e.g. Ethereum, Polygon)")
    contract_address: Optional[str] = Field(default=None, description="The token's contract address")
    project_url: Optional[str] = Field(default=None, description="The project's website URL")


class ThinkingStep(BaseModel):
    """Represents a step in the AI's thought process."""
    question: str = Field(description="The question asked by the AI.")
    answer: str = Field(description="The AI's answer to its own question.")


class TradingAnalysis(BaseModel):
    """Results of a trading analysis."""
    source_token: TokenInfo = Field(description="Information about the source token")
    target_token: TokenInfo = Field(description="Information about the target token")
    security_analysis: str = Field(description="Analysis of the security aspects of this trade")
    contract_risk: str = Field(description="Assessment of contract risks")
    recommendation: str = Field(description="Trading recommendation")
    safe_to_execute: bool = Field(description="Whether the trade is considered safe to execute")
    thinking_steps: List[ThinkingStep] = Field(default_factory=list, description="AI's thinking steps")


class PortfolioItem(BaseModel):
    """Represents a single token in the portfolio, with allocation."""
    token_info: TokenInfo
    allocation_percentage: float = Field(description="Percentage of the total investment allocated to this token.")
    reasoning: str = Field(description="Rationale for including this token and its allocation.")

    @field_validator("allocation_percentage")
    @classmethod
    def allocation_must_be_positive(cls, value: float, info: ValidationInfo) -> float:
        if value <= 0:
            raise ValueError("Allocation percentage must be positive.")
        return value


class PortfolioRecommendation(BaseModel):
    """Represents a recommended investment portfolio."""
    items: List[PortfolioItem]
    overall_risk_assessment: str = Field(
        description="Overall risk level of the portfolio (e.g., Low, Medium, High).")
    justification: str = Field(description="Overall reasoning for the portfolio composition.")
    total_investment_amount: Optional[float] = Field(None, description="Total investment amount in USD (optional).")


class QueryRequest(BaseModel):
    """Request model for user queries."""
    query: str


@dataclass
class TradingAssistantDeps:
    """Dependencies for the Trading Assistant Agent."""
    request: Optional[Any] = None
    update_status_func: Optional[Callable] = None
    send_message_func: Optional[Callable] = None
    agent_name: str = "trading_agent"  # 默認為 trading_agent

# Add blockchain data
chains_data = [
    {'name': 'BTC', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/BTC.png', 'shortName': 'btc',
     'chainIndex': '0'},
    {'name': 'Litecoin', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/LTC.png', 'shortName': 'LTC',
     'chainIndex': '2'},
    {'name': 'Ethereum', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/ETH-20220328.png', 'shortName': 'eth',
     'chainIndex': '1'},
    {'name': 'Ethereum Classic', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/ETC.png', 'shortName': 'ETC',
     'chainIndex': '61'},
    {'name': 'Bitcoin Cash', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/BCH.png', 'shortName': 'BCH',
     'chainIndex': '145'},
    {'name': 'Dash', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/dash.png', 'shortName': 'DASH',
     'chainIndex': '5'},
    {'name': 'OKTC', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/okt.png', 'shortName': 'okt',
     'chainIndex': '66'},
    {'name': 'BNB Smart Chain', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/BNB-20220308.png',
     'shortName': 'bsc', 'chainIndex': '56'},
    {'name': 'Avalanche C', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/AVAX.png', 'shortName': 'avax',
     'chainIndex': '43114'},
    {'name': 'Polygon', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/MATIC-20220415.png',
     'shortName': 'matic', 'chainIndex': '137'},
    {'name': 'Fantom', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/FTM-20220328.png', 'shortName': 'ftm',
     'chainIndex': '250'},
    {'name': 'Cronos', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/cro.png', 'shortName': 'Cronos',
     'chainIndex': '25'},
    {'name': 'Kaia Network', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/klay.png', 'shortName': 'Kaia',
     'chainIndex': '8217'},
    {'name': 'KCC', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/kcc.png', 'shortName': 'KCC',
     'chainIndex': '321'},
    {'name': 'Metis', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/metis.png', 'shortName': 'METIS',
     'chainIndex': '1088'},
    {'name': 'Boba', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/boba.png', 'shortName': 'BOBA',
     'chainIndex': '288'},
    {'name': 'Arbitrum One', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/arb_9000.png',
     'shortName': 'Arbitrum', 'chainIndex': '42161'},
    {'name': 'Optimism', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/op_10000.png', 'shortName': 'Optimism',
     'chainIndex': '10'},
    {'name': 'Gnosis', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/xdai_11300.png', 'shortName': 'XDAI',
     'chainIndex': '100'},
    {'name': 'Aurora', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/auroa_11500.png', 'shortName': 'AURORA',
     'chainIndex': '1313161554'},
    {'name': 'Ronin', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/ronin_11800.png', 'shortName': 'RONIN',
     'chainIndex': '2020'},
    {'name': 'Moonbeam', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/moonbeam_12100.png',
     'shortName': 'GLMR', 'chainIndex': '1284'},
    {'name': 'Moonriver', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/movr_12800.png', 'shortName': 'MOVR',
     'chainIndex': '1285'},
    {'name': 'Harmony', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/one_13100.png', 'shortName': 'one',
     'chainIndex': '1666600000'},
    {'name': 'EthereumPoW', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/ETHW.png', 'shortName': 'ETHW',
     'chainIndex': '10001'}, {'name': 'DIS CHAIN',
                              'logoUrl': 'https://static.coinall.ltd/cdn/web3/currency/token/1707026506326.png/type=png_350_0',
                              'shortName': 'DIS', 'chainIndex': '513100'},
    {'name': 'Celo', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/celo_16600.png', 'shortName': 'Celo',
     'chainIndex': '42220'},
    {'name': 'zkSync Era', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/zk_17000.png', 'shortName': 'ZKSync2',
     'chainIndex': '324'},
    {'name': 'Flare', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/flr_17300.png', 'shortName': 'Flr',
     'chainIndex': '14'},
    {'name': 'Core', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/core_18300.png', 'shortName': 'core',
     'chainIndex': '1116'},
    {'name': 'Dogecoin', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/18000_doge.png', 'shortName': 'DOGE',
     'chainIndex': '3'},
    {'name': 'Arbitrum Nova', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/nova_18500.png',
     'shortName': 'Nova', 'chainIndex': '42170'},
    {'name': 'Conflux', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/cfx_19200.png', 'shortName': 'cfx',
     'chainIndex': '1030'},
    {'name': 'Polygon zkEVM', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/POLYGON_ETH_19300.png',
     'shortName': 'PolygonZK', 'chainIndex': '1101'},
    {'name': 'Endurance', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/ace_19800.png', 'shortName': 'ACE',
     'chainIndex': '648'},
    {'name': 'Kava EVM', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/evm_kava_19900.png',
     'shortName': 'EVM_KAVA', 'chainIndex': '2222'},
    {'name': 'PulseChain', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/pls_20000.png', 'shortName': 'PLS',
     'chainIndex': '369'},
    {'name': 'Mantle', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/mnt_20100.png', 'shortName': 'Mantle',
     'chainIndex': '5000'},
    {'name': 'Linea', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/linea_eth_20700.png',
     'shortName': 'linea_eth', 'chainIndex': '59144'},
    {'name': 'Base', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/base_20900.png', 'shortName': 'base_eth',
     'chainIndex': '8453'},
    {'name': 'opBNB', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/opbnb_20900.png', 'shortName': 'op_bnb',
     'chainIndex': '204'},
    {'name': 'Sepolia', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/sepolia_eth_21100.png',
     'shortName': 'SEPOLIA_ETH', 'chainIndex': '11155111'},
    {'name': 'HAQQ Network', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/islm_21200.png',
     'shortName': 'HAQQ', 'chainIndex': '11235'},
    {'name': 'Scroll', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/scroll_eth_21400.png',
     'shortName': 'Scroll_eth', 'chainIndex': '534352'},
    {'name': 'Manta Pacific', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/manta_22000.png',
     'shortName': 'Manta', 'chainIndex': '169'},
    {'name': 'Wemix 3.0', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/wemix_22200.png', 'shortName': 'wemix',
     'chainIndex': '1111'},
    {'name': 'Merlin Chain', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/merlin_btc_23400.png',
     'shortName': 'Merlin_Chain', 'chainIndex': '4200'},
    {'name': 'Blast', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/blast_eth_23800.png', 'shortName': 'Blast',
     'chainIndex': '81457'},
    {'name': 'Immutable zkEVM', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/imx_24100.png',
     'shortName': 'Immutable_zkEVM', 'chainIndex': '13371'},
    {'name': 'TRON', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/TRX.png', 'shortName': 'trx',
     'chainIndex': '195'},
    {'name': 'Kroma', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/kroma_28800.png', 'shortName': 'Kroma',
     'chainIndex': '255'},
    {'name': 'X Layer', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/okb_22400.png', 'shortName': 'okb',
     'chainIndex': '196'},
    {'name': 'Taiko Mainnet', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/taiko_26600.png',
     'shortName': 'Taiko', 'chainIndex': '167000'},
    {'name': 'BOB Mainnet', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/bob_26400.png', 'shortName': 'Bob',
     'chainIndex': '60808'},
    {'name': 'Rangers', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/rpg_22600.png', 'shortName': 'rpg',
     'chainIndex': '2025'},
    {'name': 'Mode Network', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/mode_23200.png',
     'shortName': 'Mode_Network', 'chainIndex': '34443'},
    {'name': 'B² Network', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/b2_btc_25500.png',
     'shortName': 'B² Network', 'chainIndex': '223'},
    {'name': 'Bitlayer', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/bitlayer_btc_25600.png',
     'shortName': 'Bitlayer_BTC', 'chainIndex': '200901'}, {'name': 'Fractal Bitcoin',
                                                            'logoUrl': 'https://static.coinall.ltd/cdn/web3/currency/token/1725692491055.png/type=png_350_0',
                                                            'shortName': 'FB', 'chainIndex': '70000061'},
    {'name': 'Sui', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/sui_17700.png', 'shortName': 'Sui',
     'chainIndex': '784'},
    {'name': 'Solana', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/SOL-20220525.png', 'shortName': 'sol',
     'chainIndex': '501'},
    {'name': 'Gravity Alpha', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/g_29600.png',
     'shortName': 'Gravity', 'chainIndex': '1625'},
    {'name': 'Lumi Layer3', 'logoUrl': 'https://static.coinall.ltd/cdn/wallet/logo/lumi_eth_24000.png',
     'shortName': 'Lumi Finance', 'chainIndex': '94168'}]

# Create mapping of blockchain names to chain indices
chain_index_map = {chain['shortName'].lower(): chain['chainIndex'] for chain in chains_data}
chain_name_map = {chain['chainIndex']: chain['name'] for chain in chains_data}

# --- AGENT DEFINITION ---
trading_agent = Agent(
    model=VertexAIModel(
        model_name=MODEL,
        service_account_file=SERVICE_ACCOUNT_FILE,
        project_id=PROJECT_ID,
        region=LOCATION,
    ),
    deps_type=TradingAssistantDeps,
    result_type=TradingAnalysis,
    system_prompt="""
You are an AI Trading Assistant specialized in cryptocurrency trading analysis.
Your role is to help users understand and safely execute cryptocurrency trades.

You *MUST* follow these instructions *exactly*:

1. **Understand the User's Request:**
    - Identify the source token, target token, and amount.
    - Determine if the user specified a blockchain.
    - Before confirm all the information, ask the user for any missing details and *MUST* not make any assumptions and call any tools to get the missing information, but able to search web for 2 times at this point. 
    - you *MUST* not search over 2 times for the missing information, once over 2 times, you *MUST* ask the user for more information.
    - Unless user going to trade and you verify the security and info is fine, you *MUST* not use any transaction tools.
    - if there is any info relate to chain data, use 'get_chain_data' tool to get the chain data.
    - Unless user mention about the chain and the underlying they want to swap with, otherwise you *MUST* search only for chain id = "1" and "8453" (Ethereum and Base chain) for the token information only, if not found it, ask the user for more information.
    - you *MUST* not use ['fetch_transactions_by_address', 'fetch_total_value_by_address'] tool at this point.
    - you *MUST* get at least the underlying token name, target token name, chain name, and the amount that user want to swap with, and you good to go to next step.
2. **Document Thinking Steps (JSON Format):**
    - You *MUST* record your thinking process in a JSON format *exactly* like this:

    ```json
    {
      "thinking_steps": [
        {
          "question": "What are the source and target tokens, and the amount?",
          "answer": "The user wants to trade 1000 USDC for ADA."
        },
        {
          "question": "Did the user specify a blockchain?",
          "answer": "No, the user did not specify a blockchain."
        },
        {
          "question": "What specific information is missing that I need to proceed?",
          "answer": "The blockchain is missing."
        },
        {
          "question": "What question should I ask the user to get the missing information?",
          "answer": "I should ask the user: 'Which blockchain do you want to use for this trade?'"
        },
        {
          "question": "What tool should I use to get information about the USDC token?",
          "answer": "I should use the fetch_token_information tool."
        },
        {
          "question": "What tool should I use to get information about the ADA token?",
          "answer": "I should use the fetch_token_information tool."
        }
      ]
    }
    ```
    *Do not deviate from this JSON format in any way*. Each step *must* have a "question" and an "answer".

3. **Gather Token Information (Mandatory):**
    - You *MUST* use the `fetch_token_information` tool to get details about *both* the source and target tokens.
    - *Do not proceed* until you have attempted to fetch information for *both* tokens.
    - If fetch_token_information fails, use `search_web`

4. **Handle Missing Blockchain:**
    - If the user did *not* specify a blockchain, your `thinking_steps` *must* include a question about the missing blockchain (as shown in the example above). *Do not* attempt to guess the blockchain. *Ask the user*.

5. **Provide a Recommendation:**
    - Based on your analysis (using the information gathered from tools), provide a clear recommendation:
        - Should the trade be executed? Why or why not?
        - What are the potential risks? (Even if you don't have detailed security/liquidity info yet, mention general risks like volatility.)
        - Are there any safer alternatives?

6. **Safety Check:**
    - Set the `safe_to_execute` field to `True` only if you are confident that the trade is safe, based on *all* available information. If you are *unsure*, or if you don't have enough information, set it to `False`.

** This is sample code for using okx web3 api to get data (replace placeholders with actual data). Do *NOT* output anything other than a single JSON object.**
    # 1. 查询 ETH 代币历史价格 (GET 请求)
    history_eth = await client.get_historical_price(
        chain_index="1",
        token_address="0xc18360217d8f7ab5e7c516566761ea12ce7f9d72",
        limit=5,
        period="5m"
    )
    print("ETH Historical Prices:", history_eth)

    # 3. 查询支持的区块链 (GET 请求)
    chains = await client.get_supported_chains()
    print("Supported Chains:", chains)
    chain_data = {}

    # 4. 查询 ETH 代币详情 (GET 请求)
    token_detail = await client.get_token_detail("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
    print("Token Detail:", token_detail)

    # 5. 查询钱包总估值 (GET 请求)
    total_value_by_address = await client.get_total_value_by_address("0xefef7863efc158ed32dc3a39dade38a8979011cd", "1")
    print("Total Value by address:", total_value_by_address)
    #
    # 6. 查询地址交易历史 (GET 请求)
    transactions = await client.get_transactions_by_address("0xefef7863efc158ed32dc3a39dade38a8...", chains=["1", "56", "137"], limit=5)
    print("Transactions:", transactions)

    token_lists = await client.get_token_list("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", '1')
    print(token_lists)


**Final Output Format:**

Your final output *MUST* be a JSON object that *strictly* adheres to the following structure (replace placeholders with actual data). Do *NOT* output anything other than a single JSON object.

```json
{
  "source_token": {
    "symbol": "USDC",
    "blockchain": "Ethereum",
    "contract_address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "project_url": "https://www.centre.io/"
  },
  "target_token": {
    "symbol": "ADA",
    "blockchain": "Cardano",
    "contract_address": null,
    "project_url": "https://cardano.org/"
  },
  "security_analysis": "Placeholder - detailed analysis not yet implemented",
  "contract_risk": "Placeholder - risk assessment not yet implemented",
  "recommendation": "The trade can be considered, but the user did not specify the blockchain. More information is needed.",
  "safe_to_execute": false,
  "thinking_steps": [
      { "question": "What are the source and target tokens, and the amount?", "answer": "The user wants to trade 1000 USDC for ADA." },
      { "question": "Did the user specify a blockchain?", "answer": "No." },
      { "question": "What specific information is missing that I need to proceed?", "answer": "The blockchain is missing." },
      { "question": "What question should I ask the user to get the missing information?", "answer": "I should ask the user: 'Which blockchain do you want to use for this trade?'" }
    ]
}
""",
    retries=RETRIES
)
@trading_agent.result_validator
def validate_analysis(_ctx: RunContext[TradingAssistantDeps], value: TradingAnalysis) -> TradingAnalysis:
    """Validates the trading analysis for completeness."""
    issues = []
    if not value.source_token.symbol:
        issues.append("Source token symbol is missing.")
    if not value.target_token.symbol:
        issues.append("Target token symbol is missing.")
    if not value.source_token.blockchain:
        issues.append("Source token blockchain is missing.")
    if not value.target_token.blockchain:
        issues.append("Target token blockchain is missing.")
    if not value.security_analysis or len(value.security_analysis) < 50:
        issues.append("Security analysis is missing or too brief.")
    if not value.recommendation or len(value.recommendation) < 30:
        issues.append("Recommendation is missing or too brief.")
    if not value.thinking_steps or len(value.thinking_steps) < 2:
        issues.append("Thinking steps are missing or insufficient. Please show your reasoning process.")

    if issues:
        logging.info(f"Validation issues: {issues}")
        raise ModelRetry("\n".join(issues))

    return value



# --- Initialize Clients ---
async def initialize_clients():
    global okx_client, third_party_client

    # Initialize OKX Web3 client if credentials exist
    if all([OKX_WEB3_PROJECT_ID, OKX_WEB3_PROJECT_KEY, OKX_WEB3_PROJECT_SECRET, OKX_WEB3_PROJECT_PASSWRD]):
        logging.info("Initializing OKX Web3 client...")
        okx_client = OkxWeb3Client(
            OKX_WEB3_PROJECT_ID,
            OKX_WEB3_PROJECT_KEY,
            OKX_WEB3_PROJECT_SECRET,
            OKX_WEB3_PROJECT_PASSWRD
        )
        await okx_client.initialize()
        logging.info("OKX Web3 client initialized successfully")
        # try:
        token_detail = await okx_client.get_token_detail("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
        print("Token Detail:", token_detail)
    else:
        logging.warning("OKX Web3 client credentials not set, client will not be available")

    # Initialize Third Party client
    logging.info("Initializing Third Party client...")
    third_party_client = ThirdPartyClient()
    await third_party_client.initialize()
    logging.info("Third Party client initialized successfully")


# --- TOOLS ---
# General tool usage reporting function
async def report_tool_usage(_ctx: RunContext[TradingAssistantDeps], tool_name: str, **params):
    """Reports tool usage to the user."""
    if _ctx.deps.send_message_func:
        # Build description
        param_str = ", ".join([f"{k}={v}" for k, v in params.items() if v])
        message = f"Using tool ({_ctx.deps.agent_name}): {tool_name}" + (f" ({param_str})" if param_str else "")

        # Check if the function is awaitable (a coroutine function)
        if _ctx.deps.send_message_func:
            try:
                # Try to call it as an awaitable
                await _ctx.deps.send_message_func(
                    _ctx.deps.request,
                    {
                        "id": f"tool-{_ctx.deps.agent_name}-{tool_name}-{uuid4()}",
                        "sender": "agent",
                        "text": message,
                        "message_type": "tool_call",
                    }
                )
            except TypeError:
                # If it's not awaitable, call it directly
                _ctx.deps.send_message_func(
                    _ctx.deps.request,
                    {
                        "id": f"tool-{_ctx.deps.agent_name}-{tool_name}-{uuid4()}",
                        "sender": "agent",
                        "text": message,
                        "message_type": "tool_call",
                    }
                )
    else:
        # Just log the tool usage if there's no message function
        logging.info(f"Tool Usage: {tool_name} - {params}")

@trading_agent.tool()
def get_chain_data(ctx: RunContext[TradingAssistantDeps]):
    logging.info("Fetching chain data...")
    return chains_data



@trading_agent.tool()
async def fetch_token_information(
        ctx: RunContext[TradingAssistantDeps], token_address: str, blockchain: str
) -> str:
    """Fetches information about a specific token on a specific blockchain.

    Args:
        token_address: The contract address of the token.
        blockchain: The name of the blockchain (e.g., 'Ethereum', 'Polygon', 'BSC').
    """
    await report_tool_usage(ctx, "fetch_token_information", token_address=token_address, blockchain=blockchain)
    logging.info(f"Fetching information for token {token_address} on {blockchain}")

    # 從映射中獲取 chain_index
    chain_index = chain_index_map.get(blockchain.lower())
    if chain_index is None:
        error_message = f"Unsupported blockchain: {blockchain}. Supported blockchains are: {', '.join(chain_index_map.keys())}"
        logging.error(error_message)
        return error_message  # 返回錯誤信息

    try:
        token_info = await okx_client.get_token_detail(
            chain_index=chain_index, token_address=token_address
        )
        if token_info and "data" in token_info:
            if isinstance(token_info['data'], list) and token_info['data']:
                return json.dumps(token_info['data'][0]) #okx 回傳的是 list
            else:
                return "Unexpected data structure in token info"
        else:
            logging.warning(f"Could not fetch token information from Okx for: {token_address} on {blockchain}")
            return f"Could not fetch information for {token_address} on {blockchain}."

    except Exception as e:
        logging.error(f"Error fetching token information from Okx: {e}")
        return f"Error fetching token information: {str(e)}"


@trading_agent.tool()
async def analyze_contract_security(
        ctx: RunContext[TradingAssistantDeps], contract_address: str, blockchain: str
) -> str:
    """Analyzes the security of a smart contract on a specific blockchain."""
    await report_tool_usage(ctx, "analyze_contract_security", contract_address=contract_address, blockchain=blockchain)
    logging.info(f"Analyzing contract security for {contract_address} on {blockchain}")

    # Try to use the third-party client if available
    if third_party_client:
        try:
            result = await third_party_client.get_security(f"{contract_address} on {blockchain}")
            if result:
                return result
        except Exception as e:
            logging.error(f"Error using third-party client for security analysis: {e}")
    else:
        logging.warning("Third-party client not available. Using mock data.")
        return "Risk analysis not available. Agent has some error, should restart the agent."


@trading_agent.tool()
async def search_web(ctx: RunContext[TradingAssistantDeps], query: str) -> str:
    """Uses Google Search to find information."""
    print(f"Searching web for: {query}")
    print(f"Gemini API Key: {GEMINI_API_KEY}")
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )
    model_id = "gemini-2.0-flash"  # 或您的模型 ID
    google_search_tool = Tool(google_search=GoogleSearch())

    response = client.models.generate_content(
        model=model_id,
        contents=query, #直接把query丟進去, 這是官方文件的用法
        config=GenerateContentConfig(
            tools=[google_search_tool],
            response_modalities=["TEXT"],
        ))

    # 提取文本结果 (您可能需要根据实际响应格式进行调整)
    results = []
    print(response)
    for part in response.candidates[0].content.parts:
        results.append(part.text)
        # 檢查是否有資料  沒有的話或是443的話  換一個工具查：
        """使用 Google Custom Search 搜尋"""
        logging.info(f"Searching web with Google Custom Search for: {query}")
        if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
            return "Google Custom Search is not configured."

        url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_API_KEY}&cx={GOOGLE_CSE_ID}&q={query}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                results = [{"title": item["title"], "link": item["link"], "snippet": item["snippet"]}
                           for item in data.get("items", [])[:3]]
                return json.dumps(results)
            except httpx.TimeoutException:  # 捕獲超時異常
                logging.error("Google Custom Search timed out.")
                return "Google Custom Search timed out."
            except Exception as e:
                logging.error(f"Google search failed: {e}")
                return f"Google search failed: {e}"
    return "\n".join(results)


# --- Integration with OKX Web3 client tools ---
@trading_agent.tool()
async def fetch_token_price(ctx: RunContext[TradingAssistantDeps], token_address: str, chain_id: str) -> str:
    """Fetches the current price of a token using OKX Web3 API."""
    await report_tool_usage(ctx, "fetch_token_price", token_address=token_address, chain_id=chain_id)

    if okx_client:
        try:
            result = await okx_client.get_token_price(token_address, chain_id)
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error fetching token price: {e}")
            return json.dumps({"error": str(e), "message": "Failed to get token price"})
    else:
        return json.dumps({"error": "OKX Web3 client not initialized", "message": "Client not available"})


@trading_agent.tool()
async def fetch_token_detail(ctx: RunContext[TradingAssistantDeps], token_address: str, chain_id: str) -> str:
    """Fetches detailed information about a token using OKX Web3 API."""
    await report_tool_usage(ctx, "fetch_token_detail", token_address=token_address, chain_id=chain_id)

    if okx_client:
        try:
            result = await okx_client.get_token_detail(chain_id, token_address)
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error fetching token detail: {e}")
            return json.dumps({"error": str(e), "message": "Failed to get token detail"})
    else:
        return json.dumps({"error": "OKX Web3 client not initialized", "message": "Client not available"})


@trading_agent.tool()
async def fetch_total_value_by_address(
        ctx: RunContext[TradingAssistantDeps], wallet_address: str, chain_id: str
) -> str:
    """Fetches the total value of tokens held by a wallet address using OKX Web3 API."""
    await report_tool_usage(ctx, "fetch_total_value_by_address", wallet_address=wallet_address, chain_id=chain_id)

    if okx_client:
        try:
            result = await okx_client.get_total_value_by_address(wallet_address, chain_id)
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error fetching total value: {e}")
            return json.dumps({"error": str(e), "message": "Failed to get total value"})
    else:
        return json.dumps({"error": "OKX Web3 client not initialized", "message": "Client not available"})


@trading_agent.tool()
async def fetch_transactions_by_address(
    ctx: RunContext[TradingAssistantDeps],
    wallet_address: str,
    chain_id_list: List[str] = ['1', '8453']  # Specify this is a List[str]
) -> str:
    """Fetches transaction history for a wallet address using OKX Web3 API."""
    if chain_id_list is None:
        chain_id_list = ['1', '56']  # Default to Ethereum and BSC

    await report_tool_usage(ctx, "fetch_transactions_by_address", wallet_address=wallet_address,
                            chain_id_list=chain_id_list)

    if okx_client:
        try:
            result = await okx_client.get_transactions_by_address(wallet_address, chain_id_list)
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error fetching transactions: {e}")
            return json.dumps({"error": str(e), "message": "Failed to get transactions"})
    else:
        return json.dumps({"error": "OKX Web3 client not initialized", "message": "Client not available"})


@trading_agent.tool()
async def fetch_token_historical_price(
        ctx: RunContext[TradingAssistantDeps], token_address: str, chain_id: str
) -> str:
    """Fetches the historical price of a token using OKX Web3 API."""
    await report_tool_usage(ctx, "fetch_token_historical_price", token_address=token_address, chain_id=chain_id)

    if okx_client:
        try:
            result = await okx_client.get_historical_price(chain_id, token_address, limit=120, period="1d")
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error fetching historical price: {e}")
            return json.dumps({"error": str(e), "message": "Failed to get historical price"})
    else:
        return json.dumps({"error": "OKX Web3 client not initialized", "message": "Client not available"})


@trading_agent.tool()
async def analyze_contract_security_with_api(
        ctx: RunContext[TradingAssistantDeps], prompt_test_content: str
) -> str:
    """Analyzes the security of a smart contract using a third-party API."""
    await report_tool_usage(ctx, "analyze_contract_security_with_api", prompt=prompt_test_content)

    if third_party_client:
        try:
            result = await third_party_client.get_security(prompt_test_content)
            return json.dumps(result)
        except Exception as e:
            logging.error(f"Error analyzing contract security: {e}")
            return json.dumps({"error": str(e), "message": "Failed to analyze contract security"})
    else:
        return json.dumps({"error": "Third Party client not initialized", "message": "Client not available"})


# --- Transaction simulation tools ---
@trading_agent.tool()
async def update_whitelist(ctx: RunContext[TradingAssistantDeps], address: str, add: bool = True) -> str:
    """Simulates adding or removing an address from a whitelist."""
    await report_tool_usage(ctx, "update_whitelist", address=address, add=add)
    logging.info(f"Simulating {'adding' if add else 'removing'} address {address} to/from whitelist.")
    if add:
        return f"Address {address} has been added to the whitelist."
    else:
        return f"Address {address} has been removed from the whitelist."


@trading_agent.tool()
async def approve(ctx: RunContext[TradingAssistantDeps], token: str, amount: float, spender: str) -> str:
    """Simulates approving a token transfer."""
    await report_tool_usage(ctx, "approve", token=token, amount=amount, spender=spender)
    logging.info(f"Simulating approval of {amount} {token} to spender {spender}.")
    return f"Approval of {amount} {token} to spender {spender} has been simulated."


@trading_agent.tool()
async def swap(ctx: RunContext[TradingAssistantDeps], from_token: str, to_token: str, amount: float,
               slippage: float = 0.01) -> str:
    """Simulates a token swap."""
    await report_tool_usage(ctx, "swap", from_token=from_token, to_token=to_token, amount=amount, slippage=slippage)
    logging.info(f"Simulating swap of {amount} {from_token} to {to_token} with slippage {slippage}.")
    return f"Swap of {amount} {from_token} to {to_token} with slippage {slippage} has been simulated."

# --- API Handlers ---
async def handle_analyze_trade_request(query: str):
    logging.info(f"Handling analyze_trade request with query: {query}")
    deps = TradingAssistantDeps(
        request=None,
        update_status_func=lambda *args: print("Status Update:", *args),
        send_message_func=lambda *args: print("Message:", *args),
        agent_name="trading_agent"
    )
    logging.info("Calling trading_agent.run()...")
    result = await trading_agent.run(query, deps=deps)
    logging.info("trading_agent.run() returned.")

    print("RAW RESULT:", result)  # 打印原始结果, 方便调试

    if isinstance(result, Exception):
        logging.error(f"Analysis failed: {result}")
        return {"error": str(result)}  # 返回一个表示错误的字典
    else:
        return result.data  # 返回 TradingAnalysis 对象

# --- Interactive Mode ---
async def main():
    logging.info("Starting trading assistant in interactive mode...")

    # Initialize clients
    await initialize_clients()
    print(SERVICE_ACCOUNT_FILE)

    while True:
        try:
            query = input("User: ")  # 获取用户输入
            if query.lower() in ("exit", "quit", "q"):
                break
            logging.info(f"Using Trading Analysis agent for query: {query}")
            result = await handle_analyze_trade_request(query)

            if isinstance(result, dict) and "error" in result:
                print(f"Error: {result['error']}")
            elif isinstance(result, TradingAnalysis):
                if result.thinking_steps:
                    print("Agent (Thinking Steps):")
                    for step in result.thinking_steps:
                        print(f"  Question: {step.question}")
                        print(f"  Answer: {step.answer}")

                print("\nFinal Analysis:")
                print(f"Source Token: {result.source_token.symbol} on {result.source_token.blockchain}")
                print(f"Target Token: {result.target_token.symbol} on {result.target_token.blockchain}")
                print(f"Security Analysis: {result.security_analysis}")
                print(f"Contract Risk: {result.contract_risk}")
                print(f"Recommendation: {result.recommendation}")
                print(f"Safe to Execute: {result.safe_to_execute}")

        except (KeyboardInterrupt, EOFError):
            # 处理 Ctrl+C 或 Ctrl+D
            break
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            print(f"Error: {e}")

    # Close clients
    if okx_client:
        await okx_client.close()
    if third_party_client:
        await third_party_client.close()

    logging.info("Exiting trading assistant.")


if __name__ == "__main__":
    asyncio.run(main())