import logging
from typing import Any, Dict, List
from pydantic_ai import ModelRetry, RunContext

from ..config.prompts import TRADING_ANALYSIS_PROMPT
from ..models.analysis import TradingAnalysis
from .base_agent import BaseAgent, AgentDependencies
from ..tools import token_info, security, market_data, search


class TradingAgent(BaseAgent):
    """交易分析Agent"""

    def __init__(self):
        """初始化交易分析Agent"""
        super().__init__(TRADING_ANALYSIS_PROMPT, TradingAnalysis)

        # 注册工具
        self._register_tools()

        # 添加结果验证器
        self.agent.result_validator(self._validate_analysis)

    def _register_tools(self):
        """注册工具"""

        # 获取代币信息工具
        @self.agent.tool()
        async def fetch_token_information(ctx: RunContext[AgentDependencies], token_symbol: str,
                                          blockchain: str) -> str:
            await self.report_tool_usage(ctx, "fetch_token_information", token=token_symbol, blockchain=blockchain)
            return await token_info.fetch_token_information(ctx, token_symbol, blockchain)

        # 分析合约安全性工具
        @self.agent.tool()
        async def analyze_contract_security(ctx: RunContext[AgentDependencies], contract_address: str,
                                            blockchain: str) -> str:
            await self.report_tool_usage(ctx, "analyze_contract_security", contract=contract_address,
                                         blockchain=blockchain)
            return await security.analyze_contract_security(ctx, contract_address, blockchain)

        # 检查流动性工具
        @self.agent.tool()
        async def check_liquidity(ctx: RunContext[AgentDependencies], token_symbol: str, blockchain: str) -> str:
            await self.report_tool_usage(ctx, "check_liquidity", token=token_symbol, blockchain=blockchain)
            return await market_data.check_liquidity(ctx, token_symbol, blockchain)

        # 网络搜索工具
        @self.agent.tool()
        async def search_web(ctx: RunContext[AgentDependencies], search_query: str) -> str:
            await self.report_tool_usage(ctx, "search_web", query=search_query)
            return await search.search_web(ctx, search_query)

    def _validate_analysis(self, ctx: RunContext[AgentDependencies], value: TradingAnalysis) -> TradingAnalysis:
        """验证交易分析结果"""
        issues = []

        # 确保提供了代币符号
        if not value.source_token.symbol:
            issues.append("Source token symbol is missing.")
        if not value.target_token.symbol:
            issues.append("Target token symbol is missing.")

        # 确保提供了区块链
        if not value.source_token.blockchain:
            issues.append("Source token blockchain is missing.")
        if not value.target_token.blockchain:
            issues.append("Target token blockchain is missing.")

        # 确保安全分析和建议足够详细
        if not value.security_analysis or len(value.security_analysis) < 50:
            issues.append("Security analysis is missing or too brief.")
        if not value.recommendation or len(value.recommendation) < 30:
            issues.append("Recommendation is missing or too brief.")

        # 确保有思考步骤
        if not value.thinking_steps or len(value.thinking_steps) < 2:
            issues.append("Thinking steps are missing or insufficient. Please show your reasoning process.")

        if issues:
            logging.info(f"Validation issues: {issues}")
            raise ModelRetry("\n".join(issues))

        return value

    async def analyze_trade(self, query: str,
                            deps: AgentDependencies = AgentDependencies()) -> TradingAnalysis | Exception:
        """运行交易分析"""
        return await self.run(query, deps)