from pprint import pprint

import aiohttp
import asyncio
from dotenv import load_dotenv, find_dotenv



class CaveClient:
    # https://interface.carv.io/ai-agent-backend/news
    BASE_URL = "https://interface.carv.io"
    AGENT_URL = "/ai-agent-backend"
    NEWS_URL = "/news"

    def __init__(self, api_key: str):
        self.session: aiohttp.ClientSession = None
        self.api_key = api_key
        self.header = {
            "Content-Type": "application/json",
            "Authorization" : self.api_key
        }

    async def initialize(self):
        """Initializes the client."""
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Closes the client session."""
        await self.session.close()

    async def fetch_news_data(self):
        """Fetches news data from the Cave API."""
        url = f"{self.BASE_URL}{self.AGENT_URL}{self.NEWS_URL}"
        async with self.session.get(url, headers=self.header) as response:
            return await response.json()


async def main():
    api_key = "22f918f4-1677-4db7-885d-ef657c2683b9"
    client = CaveClient(api_key)
    await client.initialize()
    news_data = await client.fetch_news_data()
    if news_data['code'] == 0:
        data = news_data['data']
        for d in data['infos']:
            pprint(d)


if __name__ == "__main__":
    load_dotenv(find_dotenv())
    asyncio.run(main())