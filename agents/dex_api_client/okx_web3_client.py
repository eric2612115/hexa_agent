import logging
import os
import hmac
import base64
import json
import aiohttp
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

from typing import Optional

import logging
import os
import hmac
import base64
import json
import aiohttp
from dotenv import load_dotenv, find_dotenv
from datetime import datetime
import requests

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

    SUPPORT_CHAINS_IDS = ["1", "56", "137", "8453", "42161", "10", "43114", "250"]

    def __init__(self, project_id: str, api_key: str, api_secret: str, api_passphrase: str):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing OkxWeb3Client...")

        self.project_id = project_id
        self.api_key = api_key
        self.api_secret = api_secret.encode('utf-8')  # HMAC 需要 bytes
        self.api_passphrase = api_passphrase
        self.logger.info("Initializing OkxWeb3Client...")
        self.session = None

        self.logger.info("OkxWeb3Client initialized.")
        self.chain_data = None
        self.chain_id_map_to_name = None
        self.chain_name_map_to_id = None

    async def initialize(self):
        """异步初始化 ClientSession"""
        self.session = aiohttp.ClientSession()
        self.logger.info("OkxWeb3Client initialized.")
        self.chain_data = await self.get_supported_chains()
        # print(self.chain_data)
        if self.chain_data['code'] != '0':
            self.logger.error("Failed to get supported chains.")
            raise ValueError("Failed to get supported chains.")
        else:
            self.chain_data = self.chain_data["data"]
        self.chain_id_map_to_name = {chain["chainIndex"]: chain["name"] for chain in self.chain_data}
        self.chain_name_map_to_id = {chain["name"]: chain["chainIndex"] for chain in self.chain_data}

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

    async def get_all_token_balances_by_address(self, address: str, chains: list[str] = None,
                                                filter_risk_tokens: bool = True):
        """
        获取钱包资产明细
        :param address: 查询地址
        :param chains: 需要查询的链, 逗号分隔
        :param filter_risk_tokens: 是否过滤风险空投币 (默认 True)
        """

        if chains is None:
            chains = self.SUPPORT_CHAINS_IDS
        params = {
            "address": address,
            "chains": ",".join(chains),
            "filter": "0" if filter_risk_tokens else "1"
        }
        print(params)
        return await self._send_request("GET", self.ENDPOINTS["v5"]["token_balances"], params=params)

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

    async def get_total_value_by_address(self, address: str, chains: list[str] = None):
        """ 获取钱包总估值 """
        if chains is None:
            chains = self.SUPPORT_CHAINS_IDS
        if not address:
            raise ValueError("address cannot be empty")
        if not chains:
            raise ValueError("chains cannot be empty")

        params = {"address": address, "chains": ",".join(chains)}
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
        if chains is None:
            chains = self.SUPPORT_CHAINS_IDS

        if not address:
            raise ValueError("`address` cannot be empty")
        if not isinstance(chains, list):
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

    def get_trust_wallet_icon(self, chain, token_address):
        """
        从 Trust Wallet Assets 获取代币图标。
        """
        chain_mapping = {
            "1": "ethereum",
            "56": "smartchain",
            "137": "polygon",
            "8453": "base"
        }

        chain_id = chain_mapping.get(chain)
        if not chain_id:
            return None

        token_address = token_address.lower()
        url = f"https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/{chain_id}/assets/{token_address}/logo.png"
        try:
            response = requests.head(url)
            if response.status_code == 200:
                return url
            else:
                return None
        except requests.exceptions.RequestException:
            return None

    def get_defillama_icon(self, chain, token_address):
        """
        使用 DefiLlama API 获取代币图标。
        """
        chain_mapping_de = {
          "1": "ethereum",
          "56": "bsc",
          "137": "polygon",
          "8453": "base"
        }
        chain_id = chain_mapping_de.get(chain)

        url = f"https://coins.llama.fi/icons/tokens/{chain_id}/{token_address.lower()}"
        # 检查 URL 是否有效 (可选，但建议)
        try:
            response = requests.head(url)  # HEAD 请求只获取头部，不下载图片
            if response.status_code == 200:
                return url
            else:
                return None #找不到
        except requests.exceptions.RequestException:
            return None

    def get_icon_url(self, chain_index, symbol, token_address):
        """
        获取代币图标 URL (组合多种方法)。
        """
        # 1. 尝试 Trust Wallet (如果 token_address 不为空)
        if token_address:
            icon_url = self.get_trust_wallet_icon(chain_index, token_address)
            if icon_url:
                return icon_url

         # 2. 尝试 DefiLlama (如果 token_address 不为空)
        if token_address:
            icon_url = self.get_defillama_icon(chain_index, token_address)
            if icon_url:
                return icon_url

        # 3. 返回默认图标 (如果都没有找到)
        return "https://via.placeholder.com/24x24"  # 一个占位符图片

    async def process_token_data(self, token_data):
        formatted_balances = []
        for item in token_data['data'][0]['tokenAssets']:
            chain_name = self.chain_id_map_to_name.get(item['chainIndex'], item['chainIndex'])  # 获取链名称
            balance = float(item['balance'])
            token_price = float(item['tokenPrice'])
            value = f"{balance * token_price:.2f}"  # 计算美元价值并格式化
            # icon_url = self.get_icon_url(item['chainIndex'], item['symbol'], item['tokenAddress'])
            formatted_balances.append({
                "chain": chain_name,
                "chainIndex": item['chainIndex'],
                "symbol": item['symbol'],
                "balance": f"{balance:.4f}",  # 格式化余额
                "tokenPrice": item['tokenPrice'],
                "value": value,
                "tokenAddress": item['tokenAddress'],
                "tokenType": item['tokenType'],
                "isRiskToken": item['isRiskToken'],
                "icon": None,
                "transferAmount": item['transferAmount'],
                "availableAmount": item['availableAmount']

            })
        return formatted_balances

    async def process_transaction_data(self, transaction_data, my_address: str, if_filter_risk: bool = True):
        formatted_transactions = []
        for item in transaction_data['data'][0]['transactionList']:
            if if_filter_risk and item['hitBlacklist']:
                continue
            chain_name = self.chain_id_map_to_name.get(item['chainIndex'], item['chainIndex'])
            tx_hash = item['txHash']
            # 格式化时间
            tx_time = datetime.fromtimestamp(int(item["txTime"]) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            status = item['txStatus'].capitalize()
            token_address = item['tokenAddress']

            # 确定交易类型和详情
            from_address = item['from'][0]['address']
            to_address = item['to'][0]['address']

            if from_address.lower() == my_address.lower():
                tx_type = "Send"
            elif to_address.lower() == my_address.lower():
                tx_type = "Receive"
            else:
                tx_type = "Other"  # 或 "Swap" (需要更复杂的逻辑来判断)

            details = f"{item.get('symbol', '')}"  # 默认为代币符号
            amount_str = f"{item.get('amount', 'N/A')} {item.get('symbol', '')}"
            # icon_url = self.get_icon_url(item['chainIndex'], item.get('symbol', ''), item.get('tokenAddress', ''))

            formatted_transactions.append({
                "chain": chain_name,
                "chainIndex": item['chainIndex'],
                "txHash": tx_hash,
                "type": tx_type,
                "details": details,
                "amount": amount_str,
                "value": item.get('txFee', "N/A"),  # 这里可能需要根据txFee和当时的币价计算
                "time": tx_time,
                "status": status,
                "icon": None,
                "tokenAddress": token_address,
                "hitBlacklist": item['hitBlacklist'],
                "itype": item['itype'],
                "tag": item['tag']

            })
        return formatted_transactions


def mock_total_token_detail():
    return  {'code': '0', 'msg': 'success', 'data': [{'tokenAssets': [{'chainIndex': '1', 'tokenAddress': '', 'symbol': 'ETH', 'balance': '0.12170524654211874', 'tokenPrice': '2230.74', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '121705246542118738', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '1', 'tokenAddress': '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'symbol': 'USDC', 'balance': '251.211039', 'tokenPrice': '1', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '251211039', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '56', 'tokenAddress': '0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c', 'symbol': 'WBNB', 'balance': '0.15', 'tokenPrice': '597', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '1', 'tokenAddress': '0x8d96b4ab6c741a4c8679ae323a100d74f085ba8f', 'symbol': 'BZR', 'balance': '1', 'tokenPrice': '26.838690987260991', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '56', 'tokenAddress': '0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82', 'symbol': 'Cake', 'balance': '1.9527999620297511', 'tokenPrice': '1.7906309003614109', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '137', 'tokenAddress': '', 'symbol': 'POL', 'balance': '6.8776463325608335', 'tokenPrice': '0.2552', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '1', 'tokenAddress': '0x9813037ee2218799597d83d4a5b6f3b6778218d9', 'symbol': 'BONE', 'balance': '1.2229909071274327', 'tokenPrice': '0.257', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '56', 'tokenAddress': '', 'symbol': 'BNB', 'balance': '0.00039361143', 'tokenPrice': '597', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '8453', 'tokenAddress': '0xcde172dc5ffc46d228838446c57c1227e0b82049', 'symbol': 'BOOMER', 'balance': '0.0168', 'tokenPrice': '0.002284920741051779', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '16800000000000000', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}, {'chainIndex': '56', 'tokenAddress': '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d', 'symbol': 'USDC', 'balance': '0.000003600364646315', 'tokenPrice': '1', 'tokenType': '1', 'isRiskToken': False, 'transferAmount': '0', 'availableAmount': '0', 'rawBalance': '', 'address': '0xefef7863efc158ed32dc3a39dade38a8979011cd'}]}]}


def mock_transaction_data():
    """
    https://www.okx.com/zh-hant/web3/build/docs/waas/walletapi-api-transactions-by-address
    EVM 交易的层级类型
    itype:
        0:外层主链币转移
        1:合约内层主链币转移
        2:token转移
    :return:
    """
    return {
        "code": "0",
        "msg": "success",
        "data": [
            {
                "cursor": "1734870891",
                "transactionList": [
                    {
                        "chainIndex": "8453",
                        "txHash": "0xe5afe2d7a3d625657caa72795729ad8136f0f137cd8dc526b8de3d11ee7254cf",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1740376529000",
                        "from": [
                            {
                                "address": "0x6985884c4392d348587b19cb9eaaf157f13271cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xd05e8d4805f0bdae4216fed3f497e0939e0f427d",
                        "amount": "1",
                        "symbol": "LayerZero - Check: t.ly/AIR",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "8453",
                        "txHash": "0xe8858d83d9e63b17c95eed02c5ec608efeb605017d00b49e5d69638ce4d75ed1",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1740376485000",
                        "from": [
                            {
                                "address": "0xc27468b12ffa6d714b1b5fbc87ef403f38b82ad4",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x38e61dab33b5d9cbd86c4033a4f859cee056aeec",
                        "amount": "1",
                        "symbol": "$TRUMP - Claim: t.ly/TRUMP - #47",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0x27e2678be601ea3a2016e23eafa01c5f000affc92d7f42dbeb560a08c87a23db",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1740376415000",
                        "from": [
                            {
                                "address": "0x220e6fba494b112b19f5c3d64f9773f2a5b8a154",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                        "amount": "138.296737",
                        "symbol": "USDC",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "137",
                        "txHash": "0x8a5f417d7ba57a8cc0820a4ad626fa96151213f0d121a29cf75bd20b35c19481",
                        "methodId": "0xd43a632f",
                        "nonce": "",
                        "txTime": "1739994477000",
                        "from": [
                            {
                                "address": "0x67366782805870060151383f4bbff9dab53e5cd6",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x072eec247ce02eb8fda070416baf7f3de7dee439",
                        "amount": "12865",
                        "symbol": "NC-Eligible (Verify: https:claim.nodepay.info)",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "137",
                        "txHash": "0x59f453a2b81a8cdb51fe9fe59e3cef6ae0582fc1c6fcff1a17e516f701f1c5c6",
                        "methodId": "0x9c96eec5",
                        "nonce": "",
                        "txTime": "1739678274000",
                        "from": [
                            {
                                "address": "0x765312cabf8dda3fc976c5822936248ed2bc7483",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xedf4c1fbaf0d8bb8b95306df6e5f7c58d1ae8758",
                        "amount": "1",
                        "symbol": "$PHA | PHA-EVENT.COM",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0x2e6a4f21f48e63463f76268f53efea3e0eb04a7714d361c0942809277d0469af",
                        "methodId": "0x095ea7b3",
                        "nonce": "36",
                        "txTime": "1739651267000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xb4a81261b16b92af0b9f7c4a83f1e885132d81e4",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0",
                        "symbol": "ETH",
                        "txFee": "0.000033425360308257",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "56",
                        "txHash": "0x82f12774372f5accdd05168307f344546a9b0410bd7cd7b2d22356672a852bb2",
                        "methodId": "0x095ea7b3",
                        "nonce": "9",
                        "txTime": "1739651264000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xe9e7cea3dedca5984780bafc599bd69add087d56",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0",
                        "symbol": "BNB",
                        "txFee": "0.000026910642",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "56",
                        "txHash": "0x26c8898142f6733a9bd9620f40db6918788351f8e0315b6b12d43be5411a475e",
                        "methodId": "0x095ea7b3",
                        "nonce": "8",
                        "txTime": "1739651261000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0",
                        "symbol": "BNB",
                        "txFee": "0.000024564008",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "137",
                        "txHash": "0xb2287c579d8e039424cef502390d77eac28899b9151d2083fb68d62f22225dad",
                        "methodId": "0x095ea7b3",
                        "nonce": "5",
                        "txTime": "1739651258000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0",
                        "symbol": "POL",
                        "txFee": "0.00100503000134004",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "8453",
                        "txHash": "0x198cc14bafbe87c324fd8cb8a50a9d13f12477103f68fac3f86b693403eef9e3",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1739650425000",
                        "from": [
                            {
                                "address": "0x498581ff718922c3f8e6a244956af099b2652b2b",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x91e3bf9057b8be985f0b2619110dc1044d62cd94",
                        "amount": "1",
                        "symbol": "$VINE - Claim: t.ly/vine",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "137",
                        "txHash": "0x852345ef15d28a4451e972b956c7a51ea6bdbdce81b1defbacb27617ecb602e6",
                        "methodId": "0x729ad39e",
                        "nonce": "",
                        "txTime": "1739650374000",
                        "from": [
                            {
                                "address": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x2b7a2927465f29785b867b23cf6f102531df6802",
                        "amount": "1",
                        "symbol": "$weETH - Redeem: t.lyweth",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0xc934f1909c98c42d888248d72943c86f454340063b24fc96cb4fab19e279697f",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1739650151000",
                        "from": [
                            {
                                "address": "0x6d303cee7959f814042d31e0624fb88ec6fbcc1d",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                        "amount": "112.914302",
                        "symbol": "USDC",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "137",
                        "txHash": "0x8211c5c4c03202b4f175cf7742fa2244a9c7764b8fc4f42cae6551ff3256d0a1",
                        "methodId": "0x12514bba",
                        "nonce": "",
                        "txTime": "1739170735000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0x00007aa55b354391ab1aeb0507238e4c61abbe59",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x57d4cc9bfb06c1b3447f517fd3bdde6289267e4b",
                        "amount": "0.02",
                        "symbol": "EТH",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0xd693d2c6c033ed60848f4d06093ed5b32ead0c291dd8b8f598b19a221633aae1",
                        "methodId": "",
                        "nonce": "",
                        "txTime": "1739170379000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0x00064b9e073b8eeb60fb4c61d4ef44682237be59",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0x9d98937a664dc1e7a8ed8ab313f426b681d1e63a",
                        "amount": "0.02",
                        "symbol": "ЕTН",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0xf951e6bda05f44841208c161ae8e1aec52f003e84d727b23341888a16d84b03c",
                        "methodId": "",
                        "nonce": "35",
                        "txTime": "1739170067000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0x00000000000ebccded8ad28e591c96ac3337be59",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0.02",
                        "symbol": "ETH",
                        "txFee": "0.000015468655356",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0x20bb329708cac97031672171dce8a224bcfb4c5c7a36804dc96208fa794743c6",
                        "methodId": "",
                        "nonce": "28",
                        "txTime": "1737745523000",
                        "from": [
                            {
                                "address": "0x96cf35f472b837ea4b743f73f9d06e9d91646af2",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0.032208795857506476",
                        "symbol": "ETH",
                        "txFee": "0.000250795309611",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "1",
                        "txHash": "0x756770b43bb79f2e29aadddb107407c077b41883d58aa57636fb45a5a77cd5d2",
                        "methodId": "",
                        "nonce": "31",
                        "txTime": "1737745487000",
                        "from": [
                            {
                                "address": "0xfb5cd9bf243305a1bee155b4e900b422cc8cc401",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "",
                        "amount": "0.04570296331639978",
                        "symbol": "ETH",
                        "txFee": "0.000230819685747",
                        "txStatus": "success",
                        "hitBlacklist": False,
                        "tag": "",
                        "itype": "0"
                    },
                    {
                        "chainIndex": "56",
                        "txHash": "0x511ebf0c56116f0bdbd533b4dcba47846c6d02a2709bebd801939a98d8b047b2",
                        "methodId": "0x12514bba",
                        "nonce": "",
                        "txTime": "1735578931000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xacc56ade764d70598793565449dd7e173b8a37b9",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xe45ecd651fb0f8c1697ace0871130aa99a7c7855",
                        "amount": "110.384800000000009002",
                        "symbol": " UЅDС ",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "56",
                        "txHash": "0x91eff4c8a39933cb987187012da6405d75b5fa4d7d55f20288590e2a11910a95",
                        "methodId": "0x12514bba",
                        "nonce": "",
                        "txTime": "1735572067000",
                        "from": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xacc56ade764d70598793565449dd7e173b8a37b9",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xe45ecd651fb0f8c1697ace0871130aa99a7c7855",
                        "amount": "110.384800000000009002",
                        "symbol": " UЅDС ",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    },
                    {
                        "chainIndex": "56",
                        "txHash": "0x21677f0ca226b4a282f9ac9c8f598838350441c8c5aff506e414ce91f5bf94a4",
                        "methodId": "0xf8b037d9",
                        "nonce": "",
                        "txTime": "1734870891000",
                        "from": [
                            {
                                "address": "0xa18b59607b7286a6533fd8c7e8c9716eac9a5c73",
                                "amount": ""
                            }
                        ],
                        "to": [
                            {
                                "address": "0xefef7863efc158ed32dc3a39dade38a8979011cd",
                                "amount": ""
                            }
                        ],
                        "tokenAddress": "0xa18b59607b7286a6533fd8c7e8c9716eac9a5c73",
                        "amount": "21500.32",
                        "symbol": "AAV",
                        "txFee": "",
                        "txStatus": "success",
                        "hitBlacklist": True,
                        "tag": "",
                        "itype": "2"
                    }
                ]
            }
        ]
    }





async def main():
    load_dotenv(find_dotenv())
    project_id = os.getenv("OKX_WEB3_PROJECT_ID")
    api_key = os.getenv("OKX_WEB3_PROJECT_KEY")
    api_secret = os.getenv("OKX_WEB3_PROJECT_SECRET")
    api_passphrase = os.getenv("OKX_WEB3_PROJECT_PASSWRD")

    client = OkxWeb3Client(project_id, api_key, api_secret, api_passphrase)
    await client.initialize()

    # 获取支持的链信息
    # chains = await client.get_supported_chains()
    # print("Supported Chains:", chains)

    # 获取代币价格
    # token_price = await client.get_token_price("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
    # print("Token Price:", token_price)

    # 1. 查询 ETH 代币历史价格 (GET 请求)
    # history_eth = await client.get_historical_price(
    #     chain_index="1",
    #     token_address="0xc18360217d8f7ab5e7c516566761ea12ce7f9d72",
    #     limit=5,
    #     period="5m"
    # )
    # print("ETH Historical Prices:", history_eth)

    # 3. 查询支持的区块链 (GET 请求)
    # chains = await client.get_supported_chains()
    # print("Supported Chains:", chains)
    # chain_data = {}

    # 4. 查询 ETH 代币详情 (GET 请求)
    # token_detail = await client.get_token_detail("1", "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72")
    # print("Token Detail:", token_detail)

    # 5. 查询钱包总估值 (GET 请求)
    # total_value_by_address = await client.get_total_value_by_address("0xefef7863efc158ed32dc3a39dade38a8979011cd", ["1", "56", "137", "8453"])
    # print("Total Value by address:", total_value_by_address)

    print(await client.process_token_data(mock_total_token_detail()))

    print(await client.process_transaction_data(mock_transaction_data(), "0xefef7863efc158ed32dc3a39dade38a8979011cd"))
    #

    # total_value_by_address = await client.get_all_token_balances_by_address("0xefef7863efc158ed32dc3a39dade38a8979011cd", ["1", "56", "137", "8453"])
    # print("Total Value by address:", total_value_by_address)
    #
    # 6. 查询地址交易历史 (GET 请求)
    # transactions = await client.get_transactions_by_address("0xefef7863efc158ed32dc3a39dade38a8...", chains=["1", "56", "137"], limit=5)
    # print("Transactions:", transactions)

    # token_lists = await client.get_token_list("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", '1')
    # print(token_lists)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
