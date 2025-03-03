import os
import asyncio
import re
import aiohttp

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, render_text_description
from langchain.output_parsers import (
    StructuredOutputParser,
    ResponseSchema,
)
from google import genai
from pydantic import BaseModel, Field
from typing import Optional, List


# --- 引用類別 ---
class Citation(BaseModel):
    title: str = Field(..., description="Title of the source.")
    uri: str = Field(..., description="Full URL of the source.")


# --- Etherscan API 函數 ---
async def get_link_contract_address(query: str) -> str:
    """Queries Etherscan for the contract address using aiohttp."""
    etherscan_api_key = os.getenv("ETHERSCAN_API_KEY")
    if not etherscan_api_key:
        return "Error: Etherscan API key not found."

    #  (簡化範例) 假設 query 是 token symbol (例如 "LINK")
    #  在實際應用中，您可能需要一個映射表或 API 來將 symbol 轉換為地址

    async with aiohttp.ClientSession() as session:
        async with session.get(
             f"https://api.etherscan.io/api?module=contract&action=getabi&address={query}&apikey={etherscan_api_key}"
        ) as response:
            await response.raise_for_status()
            data = await response.json()
            if data["status"] == "1" and data["message"] == "OK":
              return query
            return f"Etherscan: {data['message']}"



# --- 研究報告 Pydantic 模型 ---
class ResearchReport(BaseModel):
    answer: str = Field(..., description="The main answer to the user's question.")
    contract_address: Optional[str] = Field(
        None, description="The verified contract address (if applicable)."
    )
    chain: Optional[str] = Field(
        None, description="The blockchain (if applicable)."
    )
    purchase_currency: Optional[str] = Field(
        None, description="The purchase currency (e.g., USDC)."
    )
    purchase_currency_address: Optional[str] = Field(
        None, description="Purchase currency address (if applicable)."
    )
    project_website: Optional[str] = Field(
        None, description="Project website (if applicable)."
    )
    additional_info: Optional[str] = Field(
        None, description="Other relevant info, e.g., safety analysis."
    )
    citations: list[Citation] = Field(..., description="List of citations.")


async def create_agent_executor():
    load_dotenv()

    # 1. Response Schema 和 Output Parser
    response_schemas = [
        ResponseSchema(name=field.name, description=field.description)
        for field_name, field in ResearchReport.model_fields.items()
    ]
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()

    # 2. Gemini 設定
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    search_tool = genai.types.Tool(
        google_search=genai.types.GoogleSearch()
    )

    # 3. Langchain Tools
    get_contract_tool = Tool.from_function(
        name="ChainDataTool",
        func=lambda query: asyncio.run(get_link_contract_address(query)),
        description="Verify a token's contract address. Input: token symbol.",
    )
    tools = [get_contract_tool]  # No search tool (using genai's)

    # 4. Prompt Template (更智能的指示)
    template = """
You are a cryptocurrency research assistant. Help users research cryptocurrencies safely.

**RULES:**

*   **ONLY use provided tools.** Do NOT make up information.
*   **ALWAYS verify contract addresses** with `ChainDataTool`.
*   **Prioritize safety.** If unsure, say so.
*   **Provide citations** for all info.
*   **Output in JSON**, following this structure:

{format_instructions}

**INSTRUCTIONS:**

1.  **Identify user intent:** Buying, info, address verification?
2.  **If buying:**
    *   Get **token/symbol** and **currency**.
    *   Get **blockchain** (ask if needed).
    *   **Verify contract address** with `ChainDataTool`.
    *   If currency given, get its address.
    *   Find **exchanges** for the token/currency pair.
    *   Get **project safety/purpose info**.
3.  **If finding info:**
    *   Get **token/symbol**.
    *   Get **blockchain** (ask if needed).
    *   **Verify contract address**.
    *   Find info.
4.  **If verifying address:**
    *   Use `ChainDataTool`.
5.  **Always cite sources.**

Begin!

Question: {input}
{agent_scratchpad}
"""

    prompt = PromptTemplate.from_template(template)
    prompt = prompt.partial(
        tools=render_text_description(tools),
        tool_names=", ".join([t.name for t in tools]),
        format_instructions=format_instructions,
    )

    # 5. Agent
    client = genai.Client()
    available_models = []
    for m in client.models.list():
      if 'generateContent' in m.supported_generation_methods:
        available_models.append(m.name)
    print("Available models:", available_models)

    llm = genai.GenerativeModel(model_name="gemini-1.5-pro-002")

    # 6. Agent Executor
    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=8,
    )
    return agent_executor, output_parser


async def process_citations(parsed_output: dict, raw_result: dict) -> dict:
    """Processes citations and adds them to the output."""
    if 'candidates' in raw_result and raw_result['candidates']:
        candidate = raw_result['candidates'][0]
        if 'metadata' in candidate:
            metadata = candidate['metadata']
            if 'citation_metadata' in metadata and 'citations' in metadata['citation_metadata']:
                citations = [
                    Citation(title=c.get('title', 'No title'), uri=c.get('uri', 'No URI'))
                    for c in metadata['citation_metadata']['citations']
                ]
                parsed_output['citations'] = [c.model_dump() for c in citations]
    return parsed_output


async def main():
    """Main function for terminal interaction."""
    agent_executor, output_parser = await create_agent_executor()

    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break

        try:
            result = await agent_executor.ainvoke({"input": user_input})
            try:
                parsed_output = output_parser.parse(result["output"])
                final_output = await process_citations(parsed_output, result)
                print(f"AI (Parsed): {final_output}")
            except Exception as e:
                print(f"AI (Raw): {result['output']}")
                print(f"Parsing Error: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())