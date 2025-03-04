import logging
import httpx
from typing import Dict, Any
from ..config.settings import GOOGLE_SEARCH_API_KEY, GOOGLE_CSE_ID, SERPAPI_KEY


async def search_web(ctx, search_query: str) -> str:
    """搜索网络获取加密货币和代币信息"""
    logging.info(f"Searching web for: {search_query}")

    # 尝试使用Google Custom Search
    if GOOGLE_SEARCH_API_KEY and GOOGLE_CSE_ID:
        result = await _search_with_google(search_query)
        if result:
            return result

    # 备选：尝试使用SerpAPI
    if SERPAPI_KEY:
        result = await _search_with_serpapi(search_query)
        if result:
            return result

    # 如果搜索不可用，返回信息
    return "Search functionality is not configured. Using internal knowledge only."


async def _search_with_google(search_query: str) -> str:
    """使用Google Custom Search API搜索"""
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_SEARCH_API_KEY}&cx={GOOGLE_CSE_ID}&q={search_query}"

    try:
        async with httpx.AsyncClient() as client:
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

            return None
    except Exception as e:
        logging.exception("Error using Google Search API")
        return None


async def _search_with_serpapi(search_query: str) -> str:
    """使用SerpAPI搜索"""
    url = "https://serpapi.com/search"
    params = {
        "api_key": SERPAPI_KEY,
        "q": search_query,
        "gl": "us",
        "hl": "en",
        "num": 5
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)

            if response.status_code == 200:
                data = response.json()

                results = []
                if "organic_results" in data:
                    for result in data["organic_results"][:3]:
                        results.append({
                            "title": result.get("title", ""),
                            "snippet": result.get("snippet", ""),
                            "link": result.get("link", "")
                        })

                if results:
                    formatted_results = "Search Results:\n\n"
                    for i, result in enumerate(results, 1):
                        formatted_results += f"{i}. {result['title']}\n"
                        formatted_results += f"   {result['snippet']}\n"
                        formatted_results += f"   Link: {result['link']}\n\n"
                    return formatted_results

            return None
    except Exception as e:
        logging.exception("Error using SerpAPI")
        return None