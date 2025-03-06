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
            "Authorization": self.api_key
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

    async def fetch_token_info_price(self, token: str):
        """Fetches token info price from the Cave API."""
        """curl -X GET "https://interface.carv.io/ai-agent-backend/token_info?ticker=aave" \
      -H "Content-Type: application/json" \
      -H "Authorization: <YOUR_AUTH_TOKEN>"""
        url = f"{self.BASE_URL}{self.AGENT_URL}/token_info?ticker={token}"
        async with self.session.get(url, headers=self.header) as response:
            return await response.json()

    async def fetch_token_info_llm(self, question_string: str):
        """
        curl -X POST https://interface.carv.io/ai-agent-backend/sql_query_by_llm \
     -H "Content-Type: application/json" \
     -H "Authorization: <YOUR_AUTH_TOKEN>" \
     -d '{"question":"What's the most active address on Ethereum during the last 24 hours?"}'
        :param token:
        :return:
        """
        url = f"{self.BASE_URL}{self.AGENT_URL}/sql_query_by_llm"
        data = {
            "question": question_string
        }
        async with self.session.post(url, headers=self.header, json=data) as response:
            return await response.json()

    def process_news_data(self, data: list[dict]):
        """Processes the news data."""
        """
        {'card_text': 'A US crypto reserve could offer “cover” to institutional '
              'investors, like pension funds, which have been hesitant to '
              'invest in crypto.',
 'title': 'Reaction to Trump’s crypto reserve: ‘Short-term optimism, long-term '
          'caution’',
 'url': 'https://cointelegraph.com/reaction-trump-crypto-reserve-short-optimism-long-caution'}
 """
        # correct url is: https://cointelegraph.com/news/el-salvador-20-how-kyrgyzstans-blockchain-strategy-stands-apart
        # print(data)
        if "code" in data:
            if data['code'] != 0:
                return data
            else:
                process_data = data['data']['infos']
        else:
            process_data = data
        news_data_set = []
        for d in process_data:
            # split https:// and split the 1st / will give the real url prefix
            real_url_prefix = d['url'].split("https://")[1].split("/")[0]
            # if the url is not from cointelegraph, skip

            if real_url_prefix != "cointelegraph.com":
                real_url = d['url']
                continue
            else:
                sub_url = d['url'].split("https://cointelegraph.com")[1]
                real_url = f"https://cointelegraph.com/news{sub_url}"
            news_data_set.append({
                "title": d['title'],
                "url": real_url,
                "content": d['card_text']
            })

        return news_data_set



async def main():

    mock_news = [

        {'card_text': 'A US crypto reserve could offer “cover” to institutional '
                      'investors, like pension funds, which have been hesitant to '
                      'invest in crypto.',
         'title': 'Reaction to Trump’s crypto reserve: ‘Short-term optimism, long-term '
                  'caution’',
         'url': 'https://cointelegraph.com/reaction-trump-crypto-reserve-short-optimism-long-caution'},
        {'card_text': 'The new crypto reserve could be a way for the US to hedge '
                      'against the rise of China’s digital yuan.',
            'title': 'US crypto reserve could be a hedge against China’s digital yuan',
            'url': 'https://cointelegraph.com/us-crypto-reserve-hedge-against-china-digital-yuan'},
        ]


    api_key = "22f918f4-1677-4db7-885d-ef657c2683b9"
    client = CaveClient(api_key)
    await client.initialize()
    # news_data = client.process_news_data(await client.fetch_news_data())
    # pprint(news_data)
    # print(await client.fetch_token_info_price("SKITTEN"))

    q1="I want to buy ADA on ETH chain"
    q2="What are the news on Base chain today?"
    q3="What's the most active address on Ethereum during the last 24 hours?"
    q4="what is the yield of AAVE?"
    print(await client.fetch_token_info_llm(q2))
    await client.close()


if __name__ == "__main__":
    load_dotenv(find_dotenv())
    asyncio.run(main())
