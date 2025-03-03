import os
import asyncio
import aiohttp

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, render_text_description
# 導入輸出解析器和相關類別
from langchain.output_parsers import (
    StructuredOutputParser,
    ResponseSchema,
)
from google import genai  # 使用新版 google-genai
from pydantic import BaseModel, Field  # 導入 BaseModel


# 定義 Citation 類別 (來自先前的範例)
class Citation(BaseModel):
    title: str = Field(..., description="Title of the source.")
    uri: str = Field(..., description="Full URL of the source.")


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


# ... (extract_token_info 函數保持不變) ...

async def create_agent_executor():
    """Creates and returns a configured AgentExecutor."""

    load_dotenv()

    # 定義 Response Schema (使用 Pydantic BaseModel)
    class ResearchReport(BaseModel):
        safety_check: str = Field(..., description="Evaluation of the token's safety.")
        project_description: str = Field(..., description="A brief description of the project.")
        purchase_options: str = Field(..., description="Reputable exchanges where the token can be purchased.")
        verified_contract_address: str = Field(..., description="The verified contract address.")
        citations: list[Citation] = Field(..., description="List of citations.")

    # 創建 StructuredOutputParser
    output_parser = StructuredOutputParser.from_response_schemas([
        ResponseSchema(name=field.name, description=field.description)
        for field_name, field in ResearchReport.model_fields.items()
    ])

    format_instructions = output_parser.get_format_instructions()

    # Gemini 設定 (使用 google-genai)
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

    # Langchain Tools
    get_contract_tool = Tool.from_function(
        name="ChainDataTool",
        func=lambda query: asyncio.run(get_link_contract_address(query)),
        description="Use this tool to verify the contract address of an Ethereum token. Input should be the token's contract address.",
    )

    tools = [get_contract_tool]

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
        format_instructions=format_instructions,
    )
    # Agent
    client = genai.Client()
    available_models = []
    for m in client.models.list():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
    print("Available models:", available_models)

    llm = genai.GenerativeModel(model_name="gemini-1.5-pro-002")  # 直接使用 genai.GenerativeModel

    # Agent and Executor
    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8,
    )
    return agent_executor, output_parser


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
