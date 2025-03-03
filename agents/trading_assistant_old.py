#!/usr/bin/env python3
# Trading Assistant using Google's Gemini API with Chain of Thought

import asyncio
import json
from dataclasses import dataclass, field
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4
from dotenv import load_dotenv, find_dotenv
import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.vertexai import VertexAIModel
from pydantic_ai.tools import ToolDefinition
from google import genai

# --- General Configuration ---
load_dotenv(find_dotenv())
USER_AGENT = "TradingAssistant/1.0"
RETRIES = 3
logging.basicConfig(level=logging.INFO)
sys.excepthook = lambda *args: None

# --- Google Cloud Configuration ---
PROJECT_ID = os.environ.get("GOOGLE_PROJECT_ID")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"

# --- API Keys ---
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")


# --- MODELS ---
class TokenInfo(BaseModel):
    """Information about a token."""
    symbol: str = Field(description="The token symbol (e.g. ETH, USDC)")
    blockchain: str = Field(description="The blockchain the token is on (e.g. Ethereum, Polygon)")
    contract_address: Optional[str] = Field(description="The token's contract address")
    project_url: Optional[str] = Field(description="The project's website URL")


class ThinkingStep(BaseModel):
    """表示AI思考过程中的一个步骤"""
    question: str = Field(description="AI提出的问题")
    answer: str = Field(description="AI对自己问题的回答")


class TradingAnalysis(BaseModel):
    """Results of a trading analysis."""
    source_token: TokenInfo = Field(description="Information about the source token")
    target_token: TokenInfo = Field(description="Information about the target token")
    security_analysis: str = Field(description="Analysis of the security aspects of this trade")
    contract_risk: str = Field(description="Assessment of contract risks")
    recommendation: str = Field(description="Trading recommendation")
    safe_to_execute: bool = Field(description="Whether the trade is considered safe to execute")
    thinking_steps: List[ThinkingStep] = Field(description="AI's thinking steps", default_factory=list)


class QueryRequest(BaseModel):
    """Request model for user queries."""
    query: str


@dataclass
class TradingAssistantDeps:
    """Dependencies for the Trading Assistant Agent."""
    request: Optional[Any] = None
    update_status_func: Optional[Callable] = None
    tool_history: List[str] = field(default_factory=list)

    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    except ValueError as e:
        client = None
        logging.info(
            f"Gemini client not initialized. Please set the GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS environment variables: {e}"
        )


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

        Use a "chain-of-thought" approach for analyzing trading requests:

        1. First, ask yourself questions to understand what the user wants:
           - What tokens does the user want to trade? (source and target)
           - Which blockchain(s) are relevant?
           - What is the purpose of this trade?
           - Do I have enough information to analyze this trade?

        2. Answer each of your own questions based on your knowledge.

        3. If information is missing, identify what you need to clarify with the user.

        4. For the analysis, investigate:
           - Source and target token details
           - Contract security aspects
           - Liquidity information
           - Known risks or issues

        5. Document each step of your thinking as explicit question-answer pairs that will be
           shown to the user. This helps users understand your analytical process.

        6. Provide a final recommendation on whether the trade appears safe to execute.

        Be especially cautious about new or unknown tokens, unusual trading patterns, and 
        potential scams. When unsure, err on the side of caution and suggest further research.
    """,
    retries=RETRIES,
)


@trading_agent.result_validator
def validate_analysis(_ctx: RunContext[TradingAssistantDeps], value: TradingAnalysis) -> TradingAnalysis:
    """Validates the trading analysis for completeness."""
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

    return value


async def report_tool_usage(
        ctx: RunContext[TradingAssistantDeps], tool_def: ToolDefinition
) -> ToolDefinition:
    """Reports tool usage and results to update_status_func."""
    if tool_def.name in ctx.deps.tool_history:
        # Tool has already been used and reported
        return tool_def

    if ctx.deps.update_status_func:
        await ctx.deps.update_status_func(
            ctx.deps.request,
            f"Using tool: {tool_def.name}...",
        )
        ctx.deps.tool_history.append(tool_def.name)

    return tool_def


# --- TOOLS ---
@trading_agent.tool(prepare=report_tool_usage)
async def fetch_token_information(_ctx: RunContext[TradingAssistantDeps], token_symbol: str, blockchain: str) -> str:
    """Fetches information about a specific token on a specific blockchain."""
    logging.info(f"Fetching information for {token_symbol} on {blockchain}")

    # Sample token database
    token_data = {
        "ETH": {
            "ethereum": {
                "name": "Ethereum",
                "contract_address": "Native",
                "description": "Native token of the Ethereum blockchain",
                "project_url": "https://ethereum.org",
                "risks": "Low risk, established project"
            }
        },
        "USDC": {
            "ethereum": {
                "name": "USD Coin",
                "contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "description": "Stablecoin pegged to the US Dollar",
                "project_url": "https://www.circle.com/en/usdc",
                "risks": "Low risk, established stablecoin"
            },
            "polygon": {
                "name": "USD Coin",
                "contract_address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                "description": "Stablecoin pegged to the US Dollar (Polygon)",
                "project_url": "https://www.circle.com/en/usdc",
                "risks": "Low risk, established stablecoin"
            }
        },
        "LINK": {
            "ethereum": {
                "name": "Chainlink",
                "contract_address": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
                "description": "Decentralized oracle network",
                "project_url": "https://chain.link",
                "risks": "Low risk, established project"
            },
            "polygon": {
                "name": "Chainlink",
                "contract_address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
                "description": "Decentralized oracle network (Polygon)",
                "project_url": "https://chain.link",
                "risks": "Low risk, established project"
            }
        },
        "ADA": {
            "cardano": {
                "name": "Cardano",
                "contract_address": "Native",
                "description": "Native token of the Cardano blockchain",
                "project_url": "https://cardano.org",
                "risks": "Low risk, established project"
            },
            "ethereum": {
                "name": "Wrapped Cardano",
                "contract_address": "0x8a6af2b75bb6129961e7c9abd3090d73e1f99df1",  # 这是一个示例地址
                "description": "ERC-20 wrapped version of Cardano's ADA token",
                "project_url": "https://cardano.org",
                "risks": "Medium risk due to wrapped token risks, but based on established project"
            }
        },
        "WBTC": {
            "ethereum": {
                "name": "Wrapped Bitcoin",
                "contract_address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
                "description": "ERC-20 wrapped version of Bitcoin",
                "project_url": "https://wbtc.network",
                "risks": "Low risk, established wrapped token"
            }
        },
        "UNI": {
            "ethereum": {
                "name": "Uniswap",
                "contract_address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                "description": "Governance token for the Uniswap protocol",
                "project_url": "https://uniswap.org",
                "risks": "Low risk, established DeFi project"
            }
        },
        "MATIC": {
            "polygon": {
                "name": "Polygon",
                "contract_address": "Native",
                "description": "Native token of the Polygon network",
                "project_url": "https://polygon.technology",
                "risks": "Low risk, established layer 2 solution"
            },
            "ethereum": {
                "name": "Polygon",
                "contract_address": "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",
                "description": "ERC-20 version of Polygon's MATIC token",
                "project_url": "https://polygon.technology",
                "risks": "Low risk, established project"
            }
        }
    }

    blockchain = blockchain.lower()
    token_symbol = token_symbol.upper()

    if token_symbol in token_data and blockchain in token_data[token_symbol]:
        token_info = token_data[token_symbol][blockchain]
        return f"""
        Token: {token_symbol}
        Name: {token_info['name']}
        Blockchain: {blockchain}
        Contract: {token_info['contract_address']}
        Description: {token_info['description']}
        Project URL: {token_info['project_url']}
        Risk Assessment: {token_info['risks']}
        """
    else:
        return f"No detailed information found for {token_symbol} on {blockchain}. This could be a new token or not available in our database."


@trading_agent.tool(prepare=report_tool_usage)
async def analyze_contract_security(_ctx: RunContext[TradingAssistantDeps], contract_address: str,
                                    blockchain: str) -> str:
    """Analyzes the security of a smart contract on a specific blockchain."""
    logging.info(f"Analyzing contract security for {contract_address} on {blockchain}")

    # Known safe contracts
    safe_contracts = {
        "ethereum": [
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
            "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # LINK
            "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
            "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",  # UNI
            "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",  # MATIC on Ethereum
        ],
        "polygon": [
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
            "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",  # LINK
        ]
    }

    blockchain = blockchain.lower()

    if contract_address == "Native":
        return "This is a native token of the blockchain. No contract security analysis is needed."

    if blockchain in safe_contracts and contract_address.lower() in [c.lower() for c in safe_contracts[blockchain]]:
        return f"""
        Contract Analysis for {contract_address} on {blockchain}:
        - Verified contract
        - Widely used and audited
        - No known vulnerabilities or exploits
        - High security rating
        """

    # For unknown contracts, return a cautious message
    return f"""
    Contract Analysis for {contract_address} on {blockchain}:
    - Contract verification status unknown
    - Audit status unknown
    - Recommend further investigation before interacting with this contract
    - Exercise caution as this is not a widely recognized contract address
    """


@trading_agent.tool(prepare=report_tool_usage)
async def check_liquidity(_ctx: RunContext[TradingAssistantDeps], token_symbol: str, blockchain: str) -> str:
    """Checks the liquidity of a token on a specific blockchain."""
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


@trading_agent.tool(prepare=report_tool_usage)
async def search_web(_ctx: RunContext[TradingAssistantDeps], search_query: str) -> str:
    """Search the web for information about cryptocurrencies and tokens."""
    logging.info(f"Searching web for: {search_query}")

    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
        return "Search functionality is not configured. Please check API keys."

    # 构建URL
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_API_KEY}&cx={GOOGLE_CSE_ID}&q={search_query}"

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


@trading_agent.tool(prepare=report_tool_usage)
async def approve_transaction(_ctx: RunContext[TradingAssistantDeps], token_address: str, spender_address: str,
                              amount: str) -> str:
    """模拟批准交易操作"""
    logging.info(f"模拟批准 {amount} 代币 {token_address} 被 {spender_address} 使用")

    # 生成一个随机交易哈希
    tx_hash = str(uuid4().hex)

    # 在实际实现中，这里会与区块链交互
    # 现在只是模拟结果
    return f"""
    模拟交易批准:
    - 代币: {token_address}
    - 接收者: {spender_address}
    - 数量: {amount}
    - 状态: 已批准
    - 交易哈希: 0x{tx_hash}
    """


@trading_agent.tool(prepare=report_tool_usage)
async def sign_transaction(_ctx: RunContext[TradingAssistantDeps], transaction_data: dict) -> str:
    """模拟签名交易操作"""
    logging.info(f"模拟签名交易: {transaction_data}")

    # 生成一个随机签名
    signature = str(uuid4().hex)

    # 在实际实现中，这里会生成交易签名
    # 现在只是模拟结果
    return f"""
    模拟交易签名:
    - 详情: {json.dumps(transaction_data, indent=2)}
    - 状态: 已签名
    - 签名: 0x{signature}
    """


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
        deps.tool_history = []

        # 发送状态更新
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Starting analysis...")

        result = await trading_agent.run(
            f"Analyze this trading request: {query}",
            deps=deps,
        )
        logging.info(f"Agent result: {result}")

        # 发送完成状态
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Analysis Complete")

        return result.data
    except Exception as e:
        logging.exception(f"Error during agent run: {e}")

        # 发送错误状态
        if deps.update_status_func:
            await deps.update_status_func(deps.request, f"Error: {e}")

        return e