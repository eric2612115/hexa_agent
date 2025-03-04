#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx
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
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
LOCATION = "us-central1"
MODEL = "gemini-2.0-flash"

# --- API Keys ---
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

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
    agent_name: str = "trading_agent"  # 新增 agent_name 屬性, 預設為 trading_agent


# --- 模擬資料庫 ---
class MockDatabase:
    def __init__(self):
        self.data = {
            ("ETH", "ethereum"): {
                "name": "Ethereum",
                "contract_address": "Native",
                "description": "Native token of the Ethereum blockchain",
                "project_url": "https://ethereum.org",
                "risks": "Low risk, established project"
            },
            ("USDC", "ethereum"): {
                "name": "USD Coin",
                "contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "description": "Stablecoin pegged to the US Dollar",
                "project_url": "https://www.circle.com/en/usdc",
                "risks": "Low risk, established stablecoin"
            },
            ("LINK", "ethereum"): {
                "name": "Chainlink",
                "contract_address": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
                "description": "Decentralized oracle network",
                "project_url": "https://chain.link",
                "risks": "Low risk, established project"
            },
            ("ADA", "cardano"): {
                "name": "Cardano",
                "contract_address": "Native",  # Cardano uses native tokens
                "description": "Proof-of-stake blockchain platform",
                "project_url": "https://cardano.org",
                "risks": "Medium risk, evolving project"
            }
        }

    def get_token_info(self, symbol: str, blockchain: str):
        logging.info(f"MockDB: Getting info for {symbol} on {blockchain}")
        return self.data.get((symbol.upper(), blockchain.lower()))

    def add_or_update_token(self, token_info: dict):
        logging.info(f"MockDB: Adding/Updating {token_info['symbol']} on {token_info['blockchain']}")
        self.data[(token_info["symbol"].upper(), token_info["blockchain"].lower())] = {
            k: v for k, v in token_info.items() if k not in ("symbol", "blockchain")
        }


db = MockDatabase()

"""
4. **Analyze Security (Use Tools):**
    - Use the `analyze_contract_security` tool to check the security of the token contracts.  This is *critical*.

5. **Check Liquidity (Use Tools):**
    - Use the `check_liquidity` tool to assess the liquidity of the tokens on the specified blockchain.
"""

# --- AGENT DEFINITION ---
trading_agent = Agent(  # 原本的Agent
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
    - If fetch_token_information fail, use `search_web`

4. **Handle Missing Blockchain:**
    - If the user did *not* specify a blockchain, your `thinking_steps` *must* include a question about the missing blockchain (as shown in the example above). *Do not* attempt to guess the blockchain. *Ask the user*.

5. **Provide a Recommendation:**
    - Based on your analysis (using the information gathered from tools), provide a clear recommendation:
        - Should the trade be executed? Why or why not?
        - What are the potential risks? (Even if you don't have detailed security/liquidity info yet, mention general risks like volatility.)
        - Are there any safer alternatives?

6. **Safety Check:**
    - Set the `safe_to_execute` field to `True` only if you are confident that the trade is safe, based on *all* available information. If you are *unsure*, or if you don't have enough information, set it to `False`.

**Final Output Format:**

Your final output *MUST* be a JSON object that *strictly* adheres to the following structure (replace placeholders with actual data).  Do *NOT* output anything other than a single JSON object.

```json
{
  "source_token": {
    "symbol": "USDC",
    "blockchain": "Ethereum",
    "contract_address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "project_url": "[https://www.centre.io/](https://www.centre.io/)"
  },
  "target_token": {
    "symbol": "ADA",
    "blockchain": "Cardano",
    "contract_address": null,
    "project_url": "[https://cardano.org/](https://cardano.org/)"
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
    retries=RETRIES,
)

portfolio_advisor_agent = Agent(  # 新的 Agent
    model=VertexAIModel(
        model_name=MODEL,
        service_account_file=SERVICE_ACCOUNT_FILE,
        project_id=PROJECT_ID,
        region=LOCATION,
    ),
    deps_type=TradingAssistantDeps,
    result_type=PortfolioRecommendation,
    system_prompt="""
            You are an AI Portfolio Advisor specialized in creating diversified cryptocurrency portfolios.
            Given a user's investment goals, risk tolerance, and a list of potential tokens (or a request to find trending tokens),
            you should create a recommended portfolio allocation.

            1. **Understand the User's Needs:**  If the user provides an investment amount, note it. Determine if the user
               has specified any preferences (e.g., specific blockchains, types of tokens).  If the user has not specified
               a risk tolerance, assume a "Medium" risk tolerance.

            2. **Token Research:**  If the user specifies tokens, use the available tools to gather information about them
               (price, market cap, security, liquidity, project details). If the user asks for trending tokens, use the
               `get_trending_tokens` tool.

            3. **Diversification:**  Recommend a diversified portfolio.  Do *not* put all funds into a single token. Aim for
               at least 3-5 different tokens, depending on the investment amount.

            4. **Risk Assessment:**  Consider the risk profile of each token.  Include lower-risk, established tokens (e.g.,
               ETH, stablecoins) as a foundation, and allocate smaller percentages to higher-risk, speculative tokens.
            5. Document each step of your thinking as explicit question-answer pairs, *using the following format* :
            
               ```json
               [
                   {
                       "question": "What tokens does the user want to trade?",
                       "answer": "The user wants to trade 1000 USDC for ADA."
                   },
                   {
                       "question": "Which blockchain is relevant?",
                       "answer": "The user did not specify a blockchain."
                   },
                   {
                       "question": "What information do I need to proceed?",
                       "answer": "I need to ask the user which blockchain they want to use."
                   }
               ]
            6. **Allocation Percentages:** Provide clear allocation percentages for *each* token.  Ensure the percentages add up
               to 100%.

            7. **Reasoning:** Explain *why* you chose each token and its allocation percentage.  Consider factors like:
               - Project fundamentals (what problem does it solve?)
               - Market capitalization (larger market cap generally means lower risk)
               - Recent news and developments
               - Potential for growth
               - Risk factors

            8. **Overall Risk:** Provide an overall risk assessment for the *entire* portfolio (Low, Medium, High).

            9. **Justification:** Give a concise summary of the overall strategy and rationale for the portfolio.

            10. **Investment Amount (Optional):** If the user provides an investment amount (e.g., in USDC), you may optionally
               show the amount allocated to each token in both percentage and USD value.

            You *must* use the available tools to gather information.  Do *not* make up token information.
            Refuse to respond to off-topic or malicious requests.
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


@portfolio_advisor_agent.result_validator
def validate_portfolio(_ctx: RunContext[TradingAssistantDeps],
                       value: PortfolioRecommendation) -> PortfolioRecommendation:
    """驗證投資組合建議"""
    issues = []
    total_allocation = 0.0

    for item in value.items:
        if item.allocation_percentage <= 0:
            issues.append(f"Invalid allocation for {item.token_info.symbol}: must be positive.")
        if not item.token_info.symbol or not item.token_info.blockchain:
            issues.append(f"Incomplete token information for an item: {item}")
        if not item.reasoning or len(item.reasoning) < 20:
            issues.append(f"Insufficient reasoning for {item.token_info.symbol}.")
        total_allocation += item.allocation_percentage

    if not abs(total_allocation - 100.0) < 0.01:  # 允許 ചെറിയ 오차
        issues.append(f"Total allocation does not add up to 100% (is {total_allocation}%).")

    if not value.overall_risk_assessment:
        issues.append("Overall risk assessment is missing.")
    if not value.justification or len(value.justification) < 30:
        issues.append("Portfolio justification is missing or too brief.")
    if issues:
        raise ModelRetry("\n".join(issues))
    return value


# --- 模擬 FastAPI Endpoints ---
async def handle_analyze_trade_request(query: str):
    logging.info(f"Handling analyze_trade request with query: {query}")
    deps = TradingAssistantDeps(
        request=None,
        update_status_func=lambda *args: print("Status Update:", *args),
        send_message_func=lambda *args: print("Message:", *args),
        agent_name="trading_agent"  # 确保这里设置了正确的 agent_name
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

async def mock_advise_portfolio(query: str):
    logging.info(f"Mock Endpoint: /advise_portfolio called with query: {query}")
    deps = TradingAssistantDeps(
        request=None,
        update_status_func=lambda *args: print("Status Update:", *args),
        send_message_func=lambda *args: print("Message:", *args),
        agent_name="portfolio_advisor_agent"  # 明确指定 agent_name
    )
    result = await portfolio_advisor_agent.run(query, deps=deps)  # 直接用 agent.run
    if isinstance(result, Exception):
        logging.error(f"Portfolio analysis failed: {result}")
        return {"error": str(result)}
    return result.data


async def mock_approve_transaction(token_address: str, spender_address: str, amount: str):
    logging.info(f"Mock Endpoint: /approve called with {token_address}, {spender_address}, {amount}")
    return {"status": "approved", "tx_hash": "0xmocktxhash"}


async def mock_sign_transaction(transaction_data: dict):
    logging.info(f"Mock Endpoint: /sign called with {transaction_data}")
    return {"status": "signed", "tx_hash": "0xmocktxhash", "signature": "0xmocksignature"}


# --- 通用工具调用报告函数 ---
async def report_tool_usage(_ctx: RunContext[TradingAssistantDeps], tool_name: str, **params):
    """向用户报告工具使用情况"""
    if _ctx.deps.send_message_func:
        # 构建描述
        param_str = ", ".join([f"{k}={v}" for k, v in params.items() if v])
        message = f"Using tool ({_ctx.deps.agent_name}): {tool_name}" + (f" ({param_str})" if param_str else "")

        await _ctx.deps.send_message_func(
            _ctx.deps.request,
            {
                "id": f"tool-{_ctx.deps.agent_name}-{tool_name}-{len(params)}",
                "sender": "agent",
                "text": message,
                "message_type": "tool_call",
            }
        )


# --- TOOLS ---

@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def fetch_token_information(
        ctx: RunContext[TradingAssistantDeps], token_symbol: str, blockchain: str
) -> str:
    """Fetches information about a specific token on a specific blockchain."""
    await report_tool_usage(ctx, "fetch_token_information", token_symbol=token_symbol, blockchain=blockchain)
    logging.info(f"Fetching information for {token_symbol} on {blockchain}")

    token_info = db.get_token_info(token_symbol, blockchain)
    if token_info:
        return json.dumps(token_info)  # 返回 JSON 字符串
    else:
        # 優先使用搜尋引擎
        search_result = await search_web(ctx, f"{token_symbol} token {blockchain} blockchain information")
        return search_result


@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def analyze_contract_security(
        ctx: RunContext[TradingAssistantDeps], contract_address: str, blockchain: str
) -> str:
    """Analyzes the security of a smart contract on a specific blockchain."""
    await report_tool_usage(ctx, "analyze_contract_security", contract_address=contract_address, blockchain=blockchain)
    logging.info(f"Analyzing contract security for {contract_address} on {blockchain}")

    # 模擬安全合約列表
    safe_contracts = {
        "ethereum": ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"]
    }

    if contract_address == "Native":
        return "This is a native token. No contract security analysis needed."
    elif blockchain.lower() in safe_contracts and contract_address.lower() in [c.lower() for c in
                                                                               safe_contracts[blockchain.lower()]]:
        return "Contract is in the safe list."
    else:
        return "Contract security analysis: Unknown. Proceed with caution."


@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def check_liquidity(
        ctx: RunContext[TradingAssistantDeps], token_symbol: str, blockchain: str
) -> str:
    """Checks the liquidity of a token on a specific blockchain."""
    await report_tool_usage(ctx, "check_liquidity", token_symbol=token_symbol, blockchain=blockchain)
    logging.info(f"Checking liquidity for {token_symbol} on {blockchain}")
    # 模擬高流動性代幣列表
    high_liquidity_tokens = {"ethereum": ["ETH", "USDC"]}

    if blockchain.lower() in high_liquidity_tokens and token_symbol.upper() in high_liquidity_tokens[
        blockchain.lower()]:
        return "Liquidity is high."
    else:
        return "Liquidity: Unknown. Proceed with caution."


async def search_web_with_serpapi(ctx: RunContext[TradingAssistantDeps], query: str) -> str:
    """使用 SerpApi 搜尋"""
    logging.info(f"Searching web with SerpApi for: {query}")
    if not SERPAPI_API_KEY:
        return "SerpApi is not configured."
    url = f"https://serpapi.com/search?api_key={SERPAPI_API_KEY}&q={query}&engine=google"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            # 提取 organic_results 中的標題、連結和摘要
            results = []
            for item in data.get("organic_results", [])[:3]:
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet")
                })
            return json.dumps(results)
        except httpx.TimeoutException:  # 捕獲超時異常
            logging.error("SerpApi search timed out.")
            return "SerpApi search timed out."
        except Exception as e:
            logging.error(f"SerpApi search failed: {e}")
            return f"SerpApi search failed: {e}"


async def search_web_with_google(ctx: RunContext[TradingAssistantDeps], query: str) -> str:
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


@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def search_web(ctx: RunContext[TradingAssistantDeps], search_query: str) -> str:
    """Search the web, prioritizing based on SEARCH_ENGINE_PRIORITY."""
    logging.info(f"Searching web for: {search_query}")
    await report_tool_usage(ctx, "search_web", query=search_query)
    for engine in SEARCH_ENGINE_PRIORITY:
        if engine == "serpapi":
            logging.info(f"Using SerpApi to search for: {search_query}")
            result = await search_web_with_serpapi(ctx, search_query)
            logging.info(f"SerpApi search result: {result}")
            if result and result != "SerpApi is not configured.":
                return result
        elif engine == "google":

            logging.info(f"Using Google Custom Search to search for: {search_query}")
            result = await search_web_with_google(ctx, search_query)
            logging.info(f"Google search result: {result}")
            if result and result != "Google Custom Search is not configured.":
                return result
        elif engine == "none":
            return "Web search is disabled."
    return "No search engine available."


# 新增的工具函數
@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def approve_transaction(
        ctx: RunContext[TradingAssistantDeps], token_address: str, spender_address: str, amount: str
) -> dict:  # 返回類型改為 dict
    """模擬批准交易操作"""
    await report_tool_usage(ctx, "approve_transaction", token=token_address, spender=spender_address, amount=amount)
    return await mock_approve_transaction(token_address, spender_address, amount)  # 使用模擬函數


@trading_agent.tool()
@portfolio_advisor_agent.tool()  # 兩個 Agents 共用
async def sign_transaction(ctx: RunContext[TradingAssistantDeps], transaction_data: dict) -> dict:  # 返回類型改為dict
    """模擬簽名交易操作, 接收交易資料"""
    await report_tool_usage(ctx, "sign_transaction", data=transaction_data)
    return await mock_sign_transaction(transaction_data)  # 使用模擬函數


@trading_agent.tool()
@portfolio_advisor_agent.tool()
async def get_trending_tokens(ctx: RunContext[TradingAssistantDeps], limit: int = 5) -> str:
    """獲取熱門代幣列表 (模擬)"""
    await report_tool_usage(ctx, "get_trending_tokens", limit=limit)
    # 模擬數據，您可以根據需要修改
    trending_tokens = [
        {"symbol": "BTC", "name": "Bitcoin", "blockchain": "bitcoin"},
        {"symbol": "ETH", "name": "Ethereum", "blockchain": "ethereum"},
        {"symbol": "SOL", "name": "Solana", "blockchain": "solana"},
        {"symbol": "BNB", "name": "Binance Coin", "blockchain": "binance"},
        {"symbol": "XRP", "name": "XRP", "blockchain": "ripple"},
    ]
    return json.dumps(trending_tokens[:limit])


# --- MAIN AGENT FUNCTION ---
async def run_trading_analysis(
        query: str,
        deps: TradingAssistantDeps = TradingAssistantDeps(),
) -> TradingAnalysis | Exception:
    """
    Runs the trading analysis agent.
    """
    try:
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Starting analysis...")

        result = await trading_agent.run(query, deps=deps)
        logging.info(f"Agent result: {result}")

        if isinstance(result, Exception):
            if deps.update_status_func:
                await deps.update_status_func(deps.request, f"Error: {result}")
            return result
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Analysis Complete")
        return result.data

    except Exception as e:
        logging.exception(f"Error during agent run: {e}")
        if deps.update_status_func:
            await deps.update_status_func(deps.request, f"Error: {e}")
        return e


async def run_portfolio_analysis(  # 新的 portfolio 函數
        query: str,
        deps: TradingAssistantDeps = TradingAssistantDeps(),
) -> PortfolioRecommendation | Exception:
    """Runs the portfolio analysis agent."""
    try:
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Starting portfolio analysis...")

        result = await portfolio_advisor_agent.run(query, deps=deps)
        logging.info(f"Portfolio Agent result: {result}")

        if isinstance(result, Exception):
            if deps.update_status_func:
                await deps.update_status_func(deps.request, f"Error: {result}")
            return result
        if deps.update_status_func:
            await deps.update_status_func(deps.request, "Portfolio analysis complete.")
        return result.data

    except Exception as e:
        logging.exception(f"Error during portfolio agent run: {e}")
        if deps.update_status_func:
            await deps.update_status_func(deps.request, f"Error: {e}")
        return e


# --- MAIN EXECUTION (模擬對話) ---
async def main():
    logging.info("Starting trading assistant in interactive mode...")

    while True:
        try:
            query = input("User: ")  # 获取用户输入
            if query.lower() in ("exit", "quit", "q"):
                break  # 退出循环

            logging.info(f"User query: {query}")

            # 创建 TradingAssistantDeps 实例
            deps = TradingAssistantDeps(
                request=None,
                update_status_func=lambda *args: print("Status Update:", *args),
                send_message_func=lambda *args: print("Message:", *args),
                agent_name="trading_agent"  # 确保设置了 agent_name
            )

            # 调用 trading_agent.run()
            result = await trading_agent.run(query, deps=deps)
            logging.info("trading_agent.run() returned.")

            # 处理结果
            if isinstance(result, Exception):
                logging.error(f"An error occurred: {result}")
            elif isinstance(result.data, TradingAnalysis):
                # 打印 thinking_steps（如果存在）
                if result.data.thinking_steps:
                    print("Agent (Thinking Steps):")
                    for step in result.data.thinking_steps:
                        print(f"  Question: {step.question}")
                        print(f"  Answer: {step.answer}")

                # 打印最终分析结果
                print("Agent (Analysis):")
                print(result.data)

            else: # 正常來說, 除非pydantic-ai有問題, 不然不會跑到這邊, 可能是string
                print("Agent:", result.data)

        except (KeyboardInterrupt, EOFError):
            # 处理 Ctrl+C 或 Ctrl+D
            break
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            break

    logging.info("Exiting trading assistant.")


if __name__ == "__main__":
    asyncio.run(main())