#!/usr/bin/env python3
# Trading Assistant using Google's Gemini API with Chain of Thought

import asyncio
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

import json
from dataclasses import dataclass, field
import logging
import os
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4
from dotenv import load_dotenv, find_dotenv
import httpx
from pydantic import BaseModel, Field
import logging
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.vertexai import VertexAIModel

from agents.dex_api_client.okx_web3_client import OkxWeb3Client
from agents.dex_api_client.third_client import ThirdPartyClient

load_dotenv(find_dotenv())
USER_AGENT = "TradingAssistant/1.0"
RETRIES = 3
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
sys.excepthook = lambda *args: None
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

agent_logger = logging.getLogger("agent")
agent_logger.setLevel(logging.INFO)

# --- Basic Settings ---
logging.basicConfig(level=logging.INFO)
sys.excepthook = lambda *args: None

# --- Google Cloud Settings ---
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"  # Use a valid Gemini 1.5 Pro model ID

# --- API Keys ---
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
# CMC_API_KEY = os.getenv("CMC_API_KEY")

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

logging.info('22222') # Changed to logging.info

project_id = os.getenv("OKX_WEB3_PROJECT_ID")
api_key = os.getenv("OKX_WEB3_PROJECT_KEY")
api_secret = os.getenv("OKX_WEB3_PROJECT_SECRET")
api_passphrase = os.getenv("OKX_WEB3_PROJECT_PASSWRD")
okx_client: OkxWeb3Client = None
third_party_client: ThirdPartyClient = None

logging.info(f"Using model: {MODEL} in {LOCATION}") # Changed to logging.info
logging.info(f"Google Project ID: {PROJECT_ID}") # Changed to logging.info
logging.info(f"Google Service Account File: {GOOGLE_SEARCH_API_KEY}") # Changed to logging.info

# --- Environment Variable Checks ---
if not PROJECT_ID or not SERVICE_ACCOUNT_FILE:
    agent_logger.error("GOOGLE_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS must be set.")
    sys.exit(1)  # Exit the program

# if not SERPAPI_API_KEY:
#     logging.warning("SERPAPI_API_KEY not set. SerpApi searches will be skipped.")

if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
    agent_logger.warning("GOOGLE_SEARCH_API_KEY or GOOGLE_CSE_ID not set. Google searches will be skipped.")


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


# --- MODELS ---
# Using a model definition compatible with the Gemini API (removed schema_extra)
class TokenInfo(BaseModel):
    """Information about a token."""
    symbol: str = Field(description="The token symbol (e.g. ETH, USDC)")
    blockchain: str = Field(description="The blockchain the token is on (e.g. Ethereum, Polygon)")
    contract_address: Optional[str] = Field(default=None, description="The token's contract address")
    project_url: Optional[str] = Field(default=None, description="The project's website URL")


class ThinkingStep(BaseModel):
    """Represents a step in the AI's thought process."""
    question: str = Field(description="AI brings up a question for itself")
    answer: str = Field(description="AI answers its own question")


class TradingAnalysis(BaseModel):
    """Results of a trading analysis."""
    source_token: TokenInfo = Field(description="Information about the source token")
    target_token: TokenInfo = Field(description="Information about the target token")
    security_analysis: str = Field(description="Analysis of the security aspects of this trade")
    contract_risk: str = Field(description="Assessment of contract risks")
    recommendation: str = Field(description="Trading recommendation")
    safe_to_execute: bool = Field(description="Whether the trade is considered safe to execute")
    thinking_steps: List[ThinkingStep] = Field(default_factory=list, description="AI's thinking steps")


class QueryRequest(BaseModel):
    """Request model for user queries."""
    query: str


@dataclass
class TradingAssistantDeps:
    """Dependencies for the Trading Assistant Agent."""
    request: Optional[Any] = None
    update_status_func: Optional[Callable] = None
    send_message_func: Optional[Callable] = None
    agent_name: str = "Trading Assistant"


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
You are an AI Trading Assistant specialized in cryptocurrency trading. Your role is to assist users in making informed and safe trading decisions. You MUST follow a strict chain-of-thought process:

1. **Understand User Request:**
   - Identify the source token, target token, amount, and (if specified) the blockchain.
   - If *any* of this information is missing, you *MUST* ask the user clarifying questions. Do *NOT* proceed until you have *all* necessary information.

2. **Gather Information:**
   - You *MUST* use `fetch_token_information` to get details about *BOTH* the source and target tokens.
   - If `fetch_token_information` fails, you *MAY* use `search_web` as a *last resort*.
     - When using `search_web`, be *extremely specific* in your queries (e.g., "[Token Name] [Blockchain] contract address").
     - You may only use `search_web` a maximum of 3 times per analysis.  Prioritize official project websites and reputable sources (CoinGecko, CoinMarketCap, Etherscan).
     - After *each* search, evaluate if you have enough information to proceed. Add a `thinking_step` like this:
       ```json
       {
         "question": "Have I found enough information about [token name]?",
         "answer": "[Yes/No], because [reason]."
       }
       ```
   - Use `analyze_contract_security` to assess the security of the tokens involved (if applicable, i.e., not native tokens like ETH).
   - Use `check_liquidity` to get an initial assessment of liquidity.

3. **Analyze and Recommend:**
    - Based on the gathered information, provide a clear recommendation:
       - Should the trade be executed?  Why or why not?  Consider:
          - Token information (price, market cap, project details).
          - Contract security.
          - Liquidity.
          - Any potential risks (volatility, scams, etc.).
       - If the trade is *not* recommended, explain why and suggest safer alternatives if possible.
    - Set the `safe_to_execute` field:
        - `true` *only if* you are confident the trade is safe based on the available information.
        - `false` if you have *any* doubts, lack sufficient information, or identify potential risks.

4. **Simulate Trade (if safe):**
   - *Only if* `safe_to_execute` is `true`:
     - You *MAY* simulate the trade using the following tools *if needed*:
        - `update_whitelist`: To simulate adding an address to a whitelist.
        - `approve`: To simulate approving a token transfer.
        - `swap`: To simulate the actual token swap.  Include a reasonable slippage value (default 0.01).

5. **Document Thinking Steps (MANDATORY):**
   - You *MUST* record your *entire* thinking process in `thinking_steps`, using *strictly* the following JSON format:
     ```json
     {
       "question": "[Your question]",
       "answer": "[Your answer or the tool result]"
     }
     ```
   - Include questions about:
     - Understanding the user's request.
     - Identifying missing information.
     - Deciding which tools to use.
     - Evaluating tool results.
     - Justifying your recommendation.
     - Explaining the simulation steps (if any).

**Final Output Format:**

Your final output *MUST* be a JSON object that strictly adheres to the `TradingAnalysis` model structure.  Provide a complete JSON example in every response, replacing placeholders with actual data. Do *NOT* output anything other than a single JSON object.
""",
    retries=RETRIES,
)


@trading_agent.result_validator
def validate_analysis(_ctx: RunContext[TradingAssistantDeps], value: TradingAnalysis) -> TradingAnalysis:
    """Validates the trading analysis for completeness."""
    logging.info(f"Validating analysis: {value}")  # Log the value being validated
    issues = []

    # Ensure both token symbols are provided
    if not value.source_token.symbol:
        issues.append("Source token symbol is missing.")
    if not value.target_token.symbol:
        issues.append("Target token symbol is missing.")

    # Ensure blockchain is identified
    if not value.source_token.blockchain:
        issues.append("Source token blockchain is missing.")
    if not value.target_token.blockchain:
        issues.append("Target token blockchain is missing.")

    # Ensure security analysis and recommendation are provided
    if not value.security_analysis or len(value.security_analysis) < 50:
        issues.append("Security analysis is missing or too brief.")
    if not value.recommendation or len(value.recommendation) < 30:
        issues.append("Recommendation is missing or too brief.")

    # Ensure there are thinking steps
    if not value.thinking_steps or len(value.thinking_steps) < 2:
        issues.append("Thinking steps are missing or insufficient. Please show your reasoning process.")

    if issues:
        logging.info(f"Validation issues: {issues}")
        raise ModelRetry("\n".join(issues))

    logging.info("Analysis validation successful.")  # Log successful validation
    return value


# --- TOOLS ---
# General tool usage reporting function
async def report_tool_usage(_ctx: RunContext[TradingAssistantDeps], tool_name: str, **params):
    """Reports tool usage to the user."""
    logging.info(f"Reporting tool usage: {tool_name} with params: {params}")  # Log tool usage
    if _ctx.deps.send_message_func:
        # Build description
        param_str = ", ".join([f"{k}={v}" for k, v in params.items() if v])
        message = f"Using tool: {tool_name}" + (f" ({param_str})" if param_str else "")

        await _ctx.deps.send_message_func(
            _ctx.deps.request,
            {
                "id": f"tool-{uuid4()}",
                "sender": "agent",
                "text": message,
                "message_type": "tool_call",
            }
        )


# use okx web3 client to fetch the token information
@trading_agent.tool()
async def fetch_token_price(_ctx: RunContext[TradingAssistantDeps], token_address: str, chain_id: str) -> str:
    """Fetches the current price of a token."""
    logging.info(f"Fetching token price for {token_address} on chain {chain_id} using fetch_token_price")  # Add Log
    res = await okx_client.get_token_price(token_address, chain_id)
    logging.info(f"Result: {res}")
    return res


@trading_agent.tool()
async def fetch_token_historical_price(_ctx: RunContext[TradingAssistantDeps], token_address: str,
                                       chain_id: str) -> str:
    """Fetches the historical price of a token."""
    logging.info(
        f"Fetching historical price for {token_address} on chain {chain_id} using fetch_token_historical_price")  # Add Log
    res = await okx_client.get_historical_price(
        chain_index=chain_id,
        token_address=token_address,
        limit=120,
        period="1d"
    )
    logging.info(f"Result: {res}")
    return res


logging.info('111111111111')  # Changed to logging.info


@trading_agent.tool()
async def fetch_token_detail(_ctx: RunContext[TradingAssistantDeps], token_address: str, chain_id: str) -> str:
    """Fetches detailed information about a token."""
    logging.info(f"Fetching token detail for {token_address} on chain {chain_id} using fetch_token_detail")  # Add Log
    res = await okx_client.get_token_detail(
        chain_index=chain_id,
        token_address=token_address
    )
    logging.info(f"Token detail: {res}")
    return res


@trading_agent.tool()
async def fetch_total_value_by_address(_ctx: RunContext[TradingAssistantDeps], wallet_address: str,
                                       chain_id: str) -> str:
    """Fetches the total value of tokens held by a wallet address."""
    logging.info(f"Fetching token price for {wallet_address} on chain {chain_id} using fetch_total_value_by_address")
    res = await okx_client.get_total_value_by_address(
        address=wallet_address,
        chains=chain_id
    )
    logging.info(f"Result: {res}")
    return res


@trading_agent.tool()
async def fetch_transactions_by_address(
        _ctx: RunContext[TradingAssistantDeps],
        wallet_address: str,
        chain_id_list=['1', '8453']
) -> str:
    """Fetches transaction history for a wallet address."""
    logging.info(
        f"Fetching transactions for {wallet_address} on chain {chain_id_list} using fetch_transactions_by_address")  # Add Log
    res = await okx_client.get_transactions_by_address(
        address=wallet_address,
        chains=chain_id_list
    )
    logging.info(f"Result: {res}")
    return res


@trading_agent.tool()
async def analyze_contract_security(_ctx: RunContext[TradingAssistantDeps], prompt_test_content: str) -> str:
    """Analyzes the security of a smart contract.

    Example API call and response (for documentation purposes):

    curl -X 'POST' \
      'https://hexa-guard-backend.onrender.com/get-security' \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -d '{
      "input_text": "Give me KAITO security on BASE"
    }'

    {
      "Market Performance": {
        "Price Trends": "The token has shown a volatile price trend over the past six months, with significant fluctuations ranging from a low of $0.50 to a high of $2.00.",
        "Trading Volume": "Average daily trading volume is approximately $5 million, indicating moderate interest from traders.",
        "Liquidity": "Liquidity is relatively low, with a market depth that can lead to price slippage during large trades.",
        "Historical Data": "Over the past year, the token has experienced a 150% increase in value, but with several sharp corrections."
      },
      "Risks": {
        "Security Vulnerabilities": "The token has not undergone a comprehensive security audit, raising concerns about potential smart contract vulnerabilities.",
        "Regulatory Concerns": "There are ongoing discussions in various jurisdictions regarding the classification of the token, which could lead to regulatory scrutiny.",
        "Market Volatility": "The token is subject to high market volatility, influenced by broader market trends and investor sentiment."
      },
      "Potential Growth": {
        "Future Adoption": "There is potential for increased adoption due to upcoming partnerships with established companies in the fintech sector.",
        "Partnerships": "Recent announcements of collaborations with payment processors could enhance the token's utility and user base.",
        "Competitive Positioning": "The token is positioned well against competitors due to its unique features, but faces challenges from more established tokens."
},
      "Conclusion": {
        "Security Score": 4,
        "Profit Potential": 7,
        "Final Verdict": "While the token presents significant profit potential due to upcoming partnerships and market interest, its security vulnerabilities and regulatory uncertainties pose considerable risks."
      }
    }
    """
    # Use the above API call and response to construct a response to the AI, summarizing the findings.
    logging.info(f"Analyzing contract security for {prompt_test_content}")
    res = await third_party_client.get_security(prompt_test_content)
    logging.info(f"Result: {res}")
    return res


@trading_agent.tool()
async def check_liquidity(_ctx: RunContext[TradingAssistantDeps], token_symbol: str, blockchain: str) -> str:
    """Checks the liquidity of a token on a specific blockchain."""
    await report_tool_usage(_ctx, "check_liquidity", token=token_symbol, blockchain=blockchain)
    logging.info(f"Checking liquidity for {token_symbol} on {blockchain}")

    high_liquidity_tokens = {
        "ethereum": ["ETH", "USDC", "USDT", "WBTC", "LINK", "UNI"],
        "polygon": ["MATIC", "USDC", "USDT", "WBTC", "LINK"],
        "arbitrum": ["ETH", "USDC", "USDT", "LINK"],
    }

    blockchain = blockchain.lower()
    token_symbol = token_symbol.upper()

    if blockchain in high_liquidity_tokens and token_symbol in high_liquidity_tokens[blockchain]:
        return f"""
        Liquidity Analysis for {token_symbol} on {blockchain}:
        - High liquidity across multiple pools
        - Trading should not cause significant slippage
        - 24h volume is healthy
        - Multiple DEXes available for trading
        """

    # For unknown tokens or chains, provide a cautious response
    return f"""
    Liquidity Analysis for {token_symbol} on {blockchain}:
    - Limited information available
    - Liquidity may be low
    - Trading could result in significant slippage
    - Exercise caution when trading this token
    """
@trading_agent.tool()
async def google_search(ctx: RunContext[TradingAssistantDeps], query: str) -> str:
    """Uses Google Search to find information."""
    client = genai.Client()
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
    for part in response.candidates[0].content.parts:
        results.append(part.text)
    return "\n".join(results)



@trading_agent.tool()
async def search_web(_ctx: RunContext[TradingAssistantDeps], search_query: str) -> str:
    """Search the web for information about cryptocurrencies and tokens."""
    agent_logger.info(f"Searching web for: {search_query}")
    await report_tool_usage(_ctx, "search_web", query=search_query)
    logging.info(f"Searching web for: {search_query}")

    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
        return "Search functionality is not configured. Using alternative sources."

    # 构建URL
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_API_KEY}&cx={GOOGLE_CSE_ID}&q={search_query}"
    agent_logger.info(f"Google Search URL: {url}")
    # 发送请求
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)

            if response.status_code == 200:
                data = response.json()

                # 处理结果
                results = []
                for item in data.get("items", [])[:3]:  # 限制结果数量
                    results.append({
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "snippet": item.get("snippet")
                    })

                # 格式化返回结果
                if results:
                    formatted_results = "Search Results:\n\n"
                    for i, result in enumerate(results, 1):
                        formatted_results += f"{i}. {result['title']}\n"
                        formatted_results += f"   {result['snippet']}\n"
                        formatted_results += f"   Link: {result['link']}\n\n"
                    return formatted_results
                else:
                    return "No relevant information found."
            else:
                return f"Search failed with status code: {response.status_code}"
        except Exception as e:
            logging.exception("Error during web search")
            return f"Search failed: {str(e)}"


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

# --- MAIN AGENT FUNCTION ---
async def run_trading_analysis(
        query: str,
        deps: TradingAssistantDeps = TradingAssistantDeps(),
) -> TradingAnalysis | Exception:
    """
    Runs the trading analysis agent.

    Args:
        query: The user's query about trading tokens.
        deps: The dependencies for the agent.

    Returns:
        The trading analysis result or an exception if an error occurred.
    """
    try:
        # Send status update
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Starting analysis...")

        # Run the trading analysis
        result = await trading_agent.run(
            query,  # Pass the query directly (including historical messages)
            deps=deps,
        )
        logging.info(f"Agent result: {result}")

        # Check if the result is an error
        if isinstance(result, Exception):
            if deps.update_status_func:
                await deps.update_status_func(deps.request, f"Error: {result}")
            return result
        # Send completion status
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Analysis Complete")

        # Directly return result.data, it should be a TradingAnalysis object
        return result.data

    except Exception as e:
        logging.exception(f"Error during agent run: {e}")
        if deps.update_status_func:
            await deps.update_status_func(deps.request, f"Error: {e}")
        return e



async def handle_trade_request(query: str, agent_name:str = "trading_agent"):
    logging.info(f"Handling analyze_trade request with query: {query}")
    deps = TradingAssistantDeps(
        request=None,
        update_status_func=lambda *args: print("Status Update:", *args),
        send_message_func=lambda *args: print("Message:", *args),
        agent_name=agent_name
    )

    result = await trading_agent.run(query, deps=deps)
    logging.info(f"trading_agent.run() returned: {result}")

    if isinstance(result, Exception):
        logging.error(f"Analysis failed: {result}")
        return {"error": str(result)}
    else:
        return result.data


# --- 執行範例 (模擬對話) ---
async def main():
    logging.info("Starting trading assistant simulation...")

    # --- 測試案例：複雜的交互，包括澄清、更改意圖 ---
    query = "I want to buy ADA with 1000 USDC"  # 初始查詢
    result = await handle_trade_request(query)

    while True:  # 迴圈
        if isinstance(result, dict) and "error" in result:  # 錯誤就終止
            logging.error(f"Error: {result['error']}")
            break
        if isinstance(result, TradingAnalysis):  # 如果是 TradingAnalysis
            if result.thinking_steps:
                last_step = result.thinking_steps[-1]
                # 檢查最後一步是否為提問，並且是我們可以回答的問題
                if "question" in last_step.model_dump() and "blockchain" in last_step.question.lower():
                    print(f"Agent: {last_step.question}")
                    user_response = "Base"  # 模擬用戶第一次回應
                    print(f"User: {user_response}")
                    query = f"{query} | {user_response}"  # 將回覆附加到查詢中
                    result = await handle_trade_request(query)  # 繼續對話

                    # 模擬用戶第二次改變主意 (改買 LINK)
                    if isinstance(result, TradingAnalysis) and result.thinking_steps:
                        if any("No detailed information" in s.answer for s in result.thinking_steps):
                            print("Agent: It seems I couldn't find ADA on Base. Would you like to consider another token or blockchain?")
                            user_response = "Let's try buying LINK on Ethereum instead."  # 使用者改買LINK
                            print(f"User: {user_response}")
                            query = user_response  # 直接用新的請求覆蓋
                            result = await handle_trade_request(query)  # 重新開始分析
                            if isinstance(result, TradingAnalysis):  #如果成功了
                                logging.info(f"Analysis Result (after changing token/chain):\n{result}")
                                break  # 結束迴圈

                # 如果不是問blockchain, 也沒有錯誤, 也沒有thinking_steps, 但是有最終分析結果
                elif result.recommendation:  # 如果已經有最終的分析結果
                    logging.info(f"Analysis Result:\n{result}")
                    break  # 完成分析，退出循环

            else:  # 如果沒有 thinking_steps，但有最終結果
                logging.info(f"Analysis Result:\n{result}")
                break

        else:  # result 不是 TradingAnalysis 也不是 dict (通常不應該發生)
            logging.info(f"Unexpected result type: {type(result)}")
            break


# --- MAIN ---
if __name__ == "__main__":
    asyncio.run(main())