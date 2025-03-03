import os
import asyncio
import aiohttp
from langchain.tools.render import render_text_description
from langchain_community.utilities.serpapi import SerpAPIWrapper
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder #改用PromptTemplate
from langchain_google_vertexai import ChatVertexAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.messages import AIMessage, HumanMessage
from dotenv import load_dotenv, find_dotenv
from langchain.output_parsers import StructuredOutputParser, ResponseSchema


# from langchain.output_parsers import StructuredOutputParser, ResponseSchema #不再需要

async def get_link_contract_address(query: str) -> str:
    """Queries Etherscan for the Chainlink (LINK) contract address using aiohttp."""
    etherscan_api_key = os.getenv("ETHERSCAN_API_KEY")
    if not etherscan_api_key:
        return "Error: Etherscan API key not found in environment variables."

    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://api.etherscan.io/api?module=contract&action=getabi&address={query}&apikey={etherscan_api_key}"
        ) as response:
            await response.raise_for_status()
            data = await response.json()

            if data["status"] == "1" and data["message"] == "OK":
                # 這裡需要根據實際情況修改，以正確返回合約地址
                return query  # 簡化, 假設輸入就是地址
            else:
                return f"Error fetching data from Etherscan: {data['message']}"


async def create_agent_executor():
    """Creates and returns a configured AgentExecutor."""

    load_dotenv()

    llm = ChatVertexAI(
        model_name="gemini-1.5-pro-002",
        project=os.getenv("GOOGLE_PROJECT_ID"),
        location="asia-east1",
    )

    search = SerpAPIWrapper()
    search_tool = Tool(
        name="Search",
        description="Use this tool to search the internet.",
        func=search.run,
        coroutine=search.arun,
    )

    chain_data_tool = Tool(
        name="ChainDataTool",
        func=lambda query: asyncio.run(get_link_contract_address(query)),
        description="Use this tool to verify the contract address of an Ethereum token. Input should be the token's contract address.",
        coroutine=get_link_contract_address
    )

    tools = [search_tool, chain_data_tool]

    # 使用 PromptTemplate 建構 ReAct Prompt
    template = """
You are a cryptocurrency research assistant. Your role is to help users safely research and find information about cryptocurrencies. You MUST ALWAYS follow these rules:

**RULES:**

*   **ONLY use the provided tools.** Do NOT attempt to make up information or use your internal knowledge.
*   **ALWAYS verify contract addresses** using the `ChainDataTool`.
*   **Prioritize safety and accuracy.** If you are unsure about something, state that you are unsure.
*   **ONLY search cryptocurrency exchanges and blockchain explorers, and news from reputable sources.**

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
{token_name} ({token_symbol}) - Research Report: [Your final answer, including the Safety Check, Project Description, Purchase Options, and Verified Contract Address]

Begin!

Question: {input}
{agent_scratchpad}
"""

    prompt = PromptTemplate.from_template(template)  # 使用 PromptTemplate

    agent = create_react_agent(llm, tools, prompt)

    # 不需要 output_parser, 因為輸出格式在 prompt 中已經定義
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8,
    )

    return agent_executor  # 不再返回 output_parser


async def main():
    """Main function to interact with the agent."""

    agent_executor = await create_agent_executor()
    chat_history = []  # 不再需要, 因為我們沒有使用 ChatPromptTemplate

    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break

        # 直接傳入 input，以及 token_name 和 token_symbol
        result = await agent_executor.ainvoke(
            {
                "input": user_input,
                "token_name": "ExampleToken",  # 替換成實際值
                "token_symbol": "ETN",  # 替換成實際值
                # 不再需要 chat_history 或 format_instructions
            }
        )

        print(f"AI: {result['output']}")  # 直接輸出結果

        # chat_history 不再需要,除非你要用其他的 agent


if __name__ == "__main__":
    asyncio.run(main())
