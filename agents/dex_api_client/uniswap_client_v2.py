import time
import aiohttp
from typing import List, Dict, Optional

class UniswapV2Client:
    BASE_URL = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"

    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def _send_request(self, query: str, variables: Dict = None) -> Dict:
        """ 发送 GraphQL 请求 """
        async with self.session.post(self.BASE_URL, json={"query": query, "variables": variables}) as response:
            return await response.json()

    async def get_all_tradable_tokens(self) -> List[str]:
        """ 获取所有 Uniswap V2 可交易代币 """
        query = '''
        query pairs($skip: Int!) {
          pairs(first: 1000, skip: $skip, orderBy: reserveUSD, orderDirection: desc) {
            token0 { id symbol }
            token1 { id symbol }
          }
        }
        '''

        all_tokens = set()
        skip = 0

        while True:
            result = await self._send_request(query, {"skip": skip})
            pairs = result.get("data", {}).get("pairs", [])

            if not pairs:
                break

            for pair in pairs:
                all_tokens.add(pair["token0"]["id"])
                all_tokens.add(pair["token1"]["id"])

            skip += 1000
            time.sleep(1)  # 避免请求过快

        return list(all_tokens)

    async def find_pairs_by_token(self, token_address: str) -> List[Dict]:
        """ 查询包含特定代币的所有交易对 """
        token_address = token_address.lower()
        query = '''
        query tokenPairs($token: String!) {
          pairs(where: { 
            or: [
              { token0: $token },
              { token1: $token }
            ] 
          }) {
            id
            token0 { id symbol }
            token1 { id symbol }
          }
        }
        '''

        result = await self._send_request(query, {"token": token_address})
        return result.get("data", {}).get("pairs", [])

    async def is_token_tradable(self, token_address: str) -> bool:
        """ 检查某个代币是否可以交易 """
        pairs = await self.find_pairs_by_token(token_address)
        return len(pairs) > 0

    async def close(self):
        """ 关闭 session 资源 """
        await self.session.close()

import asyncio

async def main():
    client = UniswapV2Client()

    # 1️⃣ 获取 Uniswap V2 上的所有可交易代币
    all_tokens = await client.get_all_tradable_tokens()
    print(f"✅ 找到 {len(all_tokens)} 个可交易代币，前 5 个：", all_tokens[:5])

    # 2️⃣ 查询特定代币的交易对（例如 DAI）
    token_address = "0x6b175474e89094c44da98b954eedeac495271d0f"  # DAI 合约地址
    pairs = await client.find_pairs_by_token(token_address)
    print(f"✅ DAI 参与的交易对数量: {len(pairs)}")

    # 3️⃣ 检查某个代币是否可以交易
    is_tradable = await client.is_token_tradable(token_address)
    print(f"✅ DAI 是否可交易: {'是' if is_tradable else '否'}")

    await client.close()  # 关闭 HTTP session

asyncio.run(main())
