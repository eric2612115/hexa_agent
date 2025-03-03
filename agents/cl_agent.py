import os
import asyncio
import re  # 導入正則表達式
import aiohttp

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder
from langchain_google_vertexai import ChatVertexAI, HarmCategory, HarmBlockThreshold, FunctionCallingConfig
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, render_text_description
from langchain_core.messages import AIMessage, HumanMessage
# 導入輸出解析器和相關類別
from langchain.output_parsers import (
    StructuredOutputParser,
    ResponseSchema,
)
from google import genai  # 導入 google.genai


async def get_link_contract_address(query: str) -> str:
    """Queries Etherscan for the contract address using aiohttp."""
    etherscan_api_key = os.getenv("ETHERSCAN_API_KEY")
    if not etherscan_api_key:
        return "Error: Etherscan API key not found in environment variables."

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.etherscan.io/api?module=contract&action=getabi&address={query}&apikey={etherscan_api_key}"
        ) as response:
            await response.raise_for_status()  # 更完善的錯誤處理
            data = await response.json()

            if data["status"] == "1" and data["message"] == "OK":
                return query  # 簡化, 假設輸入就是地址
            else:
                # 更詳細的錯誤訊息
                return f"Error fetching data from Etherscan: {data['message']}. Response: {data}"


def extract_token_info(user_input: str) -> dict:
    """Extracts the token name and symbol from the user input.
    For example:
    user_input = "I want to use 1000 USDC to buy LINK"  -> {"token_name": "Chainlink", "token_symbol": "LINK"}
    user_input = "Tell me about ETH" -> {"token_name": "Ethereum", "token_symbol": "ETH"}
    """
    # 使用正則表達式 (這只是一個範例，您可能需要根據實際情況調整)
    match = re.search(r"buy\s+(\w+)", user_input, re.IGNORECASE)
    if match:
        token_symbol = match.group(1)
        # 這裡可以根據 token_symbol 查表或呼叫 API 來獲取 token_name
        # (例如，建立一個字典 {"LINK": "Chainlink", "ETH": "Ethereum", ...})
        token_name = ""
        if token_symbol.upper() == "LINK":
            token_name = "Chainlink"
        elif token_symbol.upper() == "ETH":
            token_name = "Ethereum"
        elif token_symbol.upper() == "AAVE":
            token_name = "Aave"

        return {"token_name": token_name, "token_symbol": token_symbol.upper()}

    match = re.search(r"about\s+(\w+)", user_input, re.IGNORECASE)
    if match:
        token_symbol = match.group(1)
        token_name = ""
        if token_symbol.upper() == "LINK":
            token_name = "Chainlink"
        elif token_symbol.upper() == "ETH":
            token_name = "Ethereum"
        elif token_symbol.upper() == "AAVE":
            token_name = "Aave"

        return {"token_name": token_name, "token_symbol": token_symbol.upper()}

    return {"token_name": "", "token_symbol": ""}


async def create_agent_executor():
    """Creates and returns a configured AgentExecutor."""

    load_dotenv()

    # 定義 Response Schema
    response_schemas = [
        ResponseSchema(
            name="safety_check",
            description="Evaluation of the token's safety based on contract verification, audit reports, and source credibility.",
        ),
        ResponseSchema(
            name="project_description",
            description="A brief description of the cryptocurrency project's purpose.",
        ),
        ResponseSchema(
            name="purchase_options",
            description="A list of reputable exchanges (centralized and decentralized) where the token can be purchased with USDC.",
        ),
        ResponseSchema(
            name="verified_contract_address",
            description="The verified contract address of the token.",
        ),
        ResponseSchema(
            name="citations",
            description="A numbered list of citations, each including a title and a URL, formatted as: [number] title (URL).",
        ),
    ]

    # 創建 StructuredOutputParser
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()

    # Gemini 設定
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    search_tool = genai.types.Tool(
        google_search=genai.types.GoogleSearch()
    )  # 使用 genai 的 GoogleSearch

    llm = ChatVertexAI(
        model_name="gemini-1.5-pro-002",
        project=os.getenv("GOOGLE_PROJECT_ID"),
        location="asia-east1",
    )
    # 現在不用 function calling config

    # Langchain Tools
    get_contract_tool = Tool.from_function(
        name="ChainDataTool",
        func=lambda query: asyncio.run(get_link_contract_address(query)),
        description="Use this tool to verify the contract address of an Ethereum token. Input should be the token's contract address.",
        # coroutine=get_link_contract_address
    )
    # 移除 search tool

    tools = [get_contract_tool]  # 移除 search tool

    # Prompt Template (移除預設的 token_name 和 token_symbol)
    template = """
You are a cryptocurrency research assistant. Your role is to help users safely research and find information about cryptocurrencies. You MUST ALWAYS follow these rules:

**RULES:**

*   **ONLY use the provided tools.** Do NOT attempt to make up information or use your internal knowledge.
*   **ALWAYS verify contract addresses** using the `ChainDataTool`.
*   **Prioritize safety and accuracy.** If you are unsure about something, state that you are unsure.
*   **ONLY search cryptocurrency exchanges and blockchain explorers, and news from reputable sources.**
*   **Provide citations** for all information gathered from web searches.

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
Final Answer: [Your final answer, including the Safety Check, Project Description, Purchase Options, and Verified Contract Address, and citations]

{format_instructions}

Begin!

Question: {input}
{agent_scratchpad}
"""

    prompt = PromptTemplate.from_template(template)

    # 讓 prompt 使用 tools 資訊
    prompt = prompt.partial(
        tools=render_text_description(tools),
        tool_names=", ".join([t.name for t in tools]),
        format_instructions=format_instructions,  # 確保 format_instructions 在這裡
    )

    # Agent and Executor
    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8,
    )

    return agent_executor, output_parser  # 返回 output_parser


async def main():
    """Main function to interact with the agent."""

    agent_executor, output_parser = await create_agent_executor()

    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break

        try:
            result = await agent_executor.ainvoke({"input": user_input})
            # 嘗試解析輸出
            try:
                parsed_output = output_parser.parse(result["output"])
                print(f"AI (Parsed): {parsed_output}")
            except Exception as e:
                print(f"AI (Raw): {result['output']}")
                print(f"Parsing Error: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())