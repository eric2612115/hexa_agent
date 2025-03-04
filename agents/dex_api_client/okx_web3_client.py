import logging
import os
import hmac
import base64
import json
import aiohttp
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

from typing import Optional


class OkxWeb3Client:
    BASE_URL = "https://www.okx.com"
    ENDPOINTS = {
        "v5": {
            "token_price": "/api/v5/wallet/token/current-price",  # 获取当前币价
            "historical_price": "/api/v5/wallet/token/historical-price",  # 获取历史币价
            "token_detail": "/api/v5/wallet/token/token-detail",  # 获取代币详情
            "supported_chains": "/api/v5/wallet/chain/supported-chains",  # 获取支持的区块链
            "total_value": "/api/v5/wallet/asset/total-value",  # 获取钱包总估值
            "total_value_by_address": "/api/v5/wallet/asset/total-value-by-address",  # 获取钱包总估值
            "token_balances": "/api/v5/wallet/asset/all-token-balances-by-address",  # 获取钱包资产明细
            "transactions_by_address": "/api/v5/wallet/post-transaction/transactions-by-address",  # 地址维度交易历史
            "transactions_by_account": "/api/v5/wallet/post-transaction/transactions",  # 账户维度交易历史
            "explore_token_list": "/api/v5/defi/explore/token/list",  # 探索代币列表
        }
    }

    def __init__(self, project_id: str, api_key: str, api_secret: str, api_passphrase: str):
        self.logger = logging.getLogger(__name__)  # 新增日志
        self.logger.info("Initializing OkxWeb3Client...")  # 新增日志

        self.project_id = project_id
        self.api_key = api_key
        self.api_secret = api_secret.encode('utf-8')  # HMAC 需要 bytes
        self.api_passphrase = api_passphrase
        self.logger.info("Initializing OkxWeb3Client...")
        self.session = None

        self.logger.info("OkxWeb3Client initialized.")  # 新增日志


    async def initialize(self):
        """异步初始化 ClientSession"""
        self.session = aiohttp.ClientSession()
        self.logger.info("OkxWeb3Client initialized.")

    async def close(self):
        """关闭 ClientSession"""
        if self.session:
            await self.session.close()
            self.logger.info("OkxWeb3Client session closed.")

    def _get_timestamp(self) -> str:
        """ 获取当前 UTC 时间戳，格式符合 OKX 要求 """
        return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

    def _sign_request(self, method: str, request_path: str, body: str = "") -> tuple:
        """
        计算 OKX API 签名
        :param method: HTTP 方法 ('GET', 'POST')
        :param request_path: 请求路径，例如 `/api/v5/account/balance`
        :param body: 请求体字符串，`GET` 请求时应为空
        :return: (timestamp, signature)
        """
        timestamp = self._get_timestamp()
        prehash_string = f"{timestamp}{method}{request_path}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret, prehash_string.encode('utf-8'), digestmod='sha256').digest()
        ).decode()
        return timestamp, signature

    async def _send_request(self, method: str, endpoint: str, params: dict = None, body: dict = None):
        """
        发送 HTTP 请求
        :param method: 'GET' or 'POST'
        :param endpoint: API 端点，例如 `/api/v5/account/balance`
        :param params: 仅用于 `GET` 请求，传入 URL 查询参数
        :param body: 仅用于 `POST` 请求，传入 JSON 数据
        :return: 响应 JSON 数据
        """
        request_path = endpoint
        if params:
            query_string = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
            if query_string:
                request_path = f"{endpoint}?{query_string}"

        body_str = json.dumps(body) if (body and method == "POST") else ""  # 仅 `POST` 需要 body
        print(f"Request URL: {self.BASE_URL}{request_path}")
        print(f"Request Body: {body_str}" if body else "No Body for GET Request")

        timestamp, signature = self._sign_request(method, request_path, body_str)

        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-PROJECT": self.project_id,
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
            "OK-ACCESS-TIMESTAMP": timestamp
        }

        url = f"{self.BASE_URL}{request_path}"

        async with self.session.request(
                method, url, headers=headers, json=body if (body and method == "POST") else None
        ) as response:
            return await response.json()

    async def _send_public_request(self, method: str, endpoint: str, params: dict = None):
        """
        发送公共 HTTP 请求
        :param method: 'GET' or 'POST'
        :param endpoint: API 端点，例如 `/api/v5/account/balance`
        :param params: 仅用于 `GET` 请求，传入 URL 查询参数
        :return: 响应 JSON 数据
        """
        request_path = endpoint
        if params:
            query_string = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
            if query_string:
                request_path = f"{endpoint}?{query_string}"

        print(f"Request URL: {self.BASE_URL}{request_path}")

        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase,
        }

        url = f"{self.BASE_URL}{request_path}"

        async with self.session.request(
                method, url, headers=headers
        ) as response:
            return await response.json()

    async def get_supported_chains(self):
        """ 查询支持的链 """
        return await self._send_request("GET", self.ENDPOINTS["v5"]["supported_chains"])

    async def get_token_price(self, chain_index: str, token_address: str):
        """ 查询代币价格 """
        data = [
            {"chainIndex": chain_index, "tokenAddress": token_address}
        ]
        return await self._send_request("POST", self.ENDPOINTS["v5"]["token_price"], data)

    async def get_token_detail(self, chain_index: str, token_address: str):
        """ 获取代币详细信息 """
        params = {
            "chainIndex": chain_index,
            "tokenAddress": token_address
        }
        return await self._send_request("GET", self.ENDPOINTS["v5"]["token_detail"], params=params)

    async def get_all_token_balances_by_address(self, address: str, chains: str, filter_risk_tokens: bool = True):
        """
        获取钱包资产明细
        :param address: 查询地址
        :param chains: 需要查询的链, 逗号分隔
        :param filter_risk_tokens: 是否过滤风险空投币 (默认 True)
        """
        params = {
            "address": address,
            "chains": chains,
            "filter": "0" if filter_risk_tokens else "1"
        }
        return await self._send_request("GET", self.ENDPOINTS["v5"]["token_balances"], body=params)

    async def get_historical_price(self, chain_index: str, token_address: str, limit: int = 5, period: str = "5m",
                                   begin: Optional[int] = None, if_btc: bool = False):
        """ 查询代币历史价格 """
        params = {
            "chainIndex": "0" if if_btc else chain_index,  # 如果是 BTC 代币，则 chainIndex=0
            "tokenAddress": "btc-brc20-ordi" if if_btc else token_address,
            "limit": limit,
            "period": period
        }
        if begin:
            params["begin"] = begin

        return await self._send_request("GET", self.ENDPOINTS["v5"]["historical_price"], params=params)

    async def get_total_value_by_account(self, account_id: str, chains: Optional[str] = None):
        params = {"accountId": account_id}
        if chains:
            params["chains"] = chains
        return await self._send_request("GET", self.ENDPOINTS["v5"]["total_value"], params=params)

    async def get_total_value_by_address(self, address: str, chains: Optional[str] = None):
        """ 获取钱包总估值 """
        if not address:
            raise ValueError("address cannot be empty")
        if not chains:
            raise ValueError("chains cannot be empty")

        params = {"address": address, "chains": chains}
        return await self._send_request("GET", self.ENDPOINTS["v5"]["total_value_by_address"], params=params)

    async def get_transactions_by_address(self, address: str, chains: list, token_address: Optional[str] = None,
                                          begin: Optional[int] = None, end: Optional[int] = None,
                                          cursor: Optional[str] = None, limit: int = 20):
        """
        获取地址维度的交易历史
        :param address: 查询地址
        :param chains: 需要查询的链, 逗号分隔
        :param token_address: 代币地址 (默认查询所有)
        :param begin: 开始时间 (Unix时间戳, 毫秒)
        :param end: 结束时间 (Unix时间戳, 毫秒)
        :param cursor: 游标
        :param limit: 返回条数 (默认 20，最大 100)
        """

        if not address:
            raise ValueError("`address` cannot be empty")
        if not chains or not isinstance(chains, list):
            raise ValueError("`chains` should be a list of chain IDs, like ['1', '56']")
        chains_str = ",".join(chains)

        params = {"address": address, "chains": chains_str, "limit": limit}

        if token_address:
            params["tokenAddress"] = token_address
        if begin:
            params["begin"] = begin
        if end:
            params["end"] = end
        if cursor:
            params["cursor"] = cursor
        return await self._send_request("GET", self.ENDPOINTS["v5"]["transactions_by_address"], params=params)

    async def get_transactions_by_account(self, account_id: str, chain_index: Optional[str] = None,
                                          token_address: Optional[str] = None, begin: Optional[int] = None,
                                          end: Optional[int] = None, cursor: Optional[str] = None, limit: int = 20):
        """
        获取账户维度的交易历史
        :param account_id: 账户唯一标识符
        :param chain_index: 需要查询的链 ID
        :param token_address: 代币地址 (默认查询所有)
        :param begin: 开始时间 (Unix时间戳, 毫秒)
        :param end: 结束时间 (Unix时间戳, 毫秒)
        :param cursor: 游标
        :param limit: 返回条数 (默认 20，最大 20)
        """
        params = {
            "accountId": account_id,
            "chainIndex": chain_index,
            "tokenAddress": token_address,
            "begin": begin,
            "end": end,
            "cursor": cursor,
            "limit": limit
        }
        return await self._send_request("GET", self.ENDPOINTS["v5"]["transactions_by_account"], body=params)


    async def get_token_list(self, tokenAddress: Optional[str] = None, chainId: Optional[str] = None):
        """ 探索代币列表 """
        params = {}
        if tokenAddress:
            params["tokenAddress"] = tokenAddress
        if chainId:
            params["chainId"] = chainId
        return await self._send_request("GET", self.ENDPOINTS["v5"]["explore_token_list"], params=params)


async def main():
    load_dotenv(find_dotenv())
    project_id = os.getenv("OKX_WEB3_PROJECT_ID")
    api_key = os.getenv("OKX_WEB3_PROJECT_KEY")
    api_secret = os.getenv("OKX_WEB3_PROJECT_SECRET")
    api_passphrase = os.getenv("OKX_WEB3_PROJECT_PASSWRD")

    client = OkxWeb3Client(project_id, api_key, api_secret, api_passphrase)

    # 获取支持的链信息
    chains = await client.get_supported_chains()
    print("Supported Chains:", chains)

    # 获取代币价格
    token_price = await client.get_token_price("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
    print("Token Price:", token_price)

    # 1. 查询 ETH 代币历史价格 (GET 请求)
    history_eth = await client.get_historical_price(
        chain_index="1",
        token_address="0xc18360217d8f7ab5e7c516566761ea12ce7f9d72",
        limit=5,
        period="5m"
    )
    print("ETH Historical Prices:", history_eth)

    # 3. 查询支持的区块链 (GET 请求)
    chains = await client.get_supported_chains()
    print("Supported Chains:", chains)
    chain_data = {}

    # 4. 查询 ETH 代币详情 (GET 请求)
    token_detail = await client.get_token_detail("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
    print("Token Detail:", token_detail)

    # 5. 查询钱包总估值 (GET 请求)
    total_value_by_address = await client.get_total_value_by_address("0xefef7863efc158ed32dc3a39dade38a8979011cd", "1")
    print("Total Value by address:", total_value_by_address)
    #
    # 6. 查询地址交易历史 (GET 请求)
    transactions = await client.get_transactions_by_address("0xefef7863efc158ed32dc3a39dade38a8...", chains=["1", "56", "137"], limit=5)
    print("Transactions:", transactions)

    token_lists = await client.get_token_list("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", '1')
    print(token_lists)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
