from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.vertexai import VertexAIModel
from ..config.settings import MODEL, PROJECT_ID, SERVICE_ACCOUNT_FILE, LOCATION, RETRIES


@dataclass
class AgentDependencies:
    """Agent依赖项"""
    request: Optional[Any] = None
    update_status_func: Optional[Callable] = None
    send_message_func: Optional[Callable] = None


class BaseAgent:
    """基础Agent类"""

    def __init__(self, system_prompt: str, result_type: Any):
        """初始化Agent"""
        self.agent = Agent(
            model=VertexAIModel(
                model_name=MODEL,
                service_account_file=SERVICE_ACCOUNT_FILE,
                project_id=PROJECT_ID,
                region=LOCATION,
            ),
            deps_type=AgentDependencies,
            result_type=result_type,
            system_prompt=system_prompt,
            retries=RETRIES,
        )

    async def report_tool_usage(self, ctx, tool_name: str, **params):
        """报告工具使用情况"""
        if ctx.deps.send_message_func:
            param_str = ", ".join([f"{k}={v}" for k, v in params.items() if v])
            message = f"Using tool: {tool_name}" + (f" ({param_str})" if param_str else "")

            from uuid import uuid4
            await ctx.deps.send_message_func(
                ctx.deps.request,
                {
                    "id": f"tool-{uuid4()}",
                    "sender": "agent",
                    "text": message,
                    "message_type": "tool_call",
                }
            )

    async def run(self, query: str, deps: AgentDependencies):
        """运行Agent"""
        try:
            if deps.update_status_func:
                await deps.update_status_func(deps.request, "Starting analysis...")

            result = await self.agent.run(query, deps=deps)

            if deps.update_status_func:
                await deps.update_status_func(deps.request, "Analysis Complete")

            return result.data
        except Exception as e:
            import logging
            logging.exception(f"Error during agent run: {e}")

            if deps.update_status_func:
                await deps.update_status_func(deps.request, f"Error: {e}")

            return e