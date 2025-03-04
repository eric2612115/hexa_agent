import asyncio
import logging
import os
import hmac
import base64
import json
from pprint import pprint

import aiohttp
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

from typing import Optional


class ThirdPartyClient:
    BASE_URL = "https://hexa-guard-backend.onrender.com"

    def __init__(self):
        self.logger = logging.getLogger(__name__)  # 新增日志
        self.session: aiohttp.ClientSession = None

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """发送GET请求"""
        url = f"{self.BASE_URL}/{path}"
        async with self.session.get(url, params=params) as response:
            return await response.json()

    async def _post_request(self, path: str, data: dict) -> dict:
        """发送POST请求"""
        url = f"{self.BASE_URL}/{path}"
        async with self.session.post(url, json=data) as response:
            return await response.json()

    async def get_security(self, input_text: str):
        """获取文本安全性"""
        data = {
            "input_text": input_text
        }
        return await self._post_request("get-security", data)

    async def get_top5_tokens(self):
        return await self._get("top5_tokens")

    async def initialize(self):
        """异步初始化 ClientSession"""
        self.session = aiohttp.ClientSession()
        self.logger.info("OkxWeb3Client initialized.")

    async def close(self):
        """关闭 ClientSession"""
        if self.session:
            await self.session.close()
            self.logger.info("OkxWeb3Client session closed.")


async def main():
    client = ThirdPartyClient()
    await client.initialize()
    # result = await client.get_security("Give me KAITO security on BASE")
    # pprint(result)

    print(await client.get_top5_tokens())


if __name__ == "__main__":
    load_dotenv(find_dotenv())
    asyncio.run(main())
