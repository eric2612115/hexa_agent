from pydantic import BaseModel, Field
from typing import Optional

class TokenInfo(BaseModel):
    """代币信息"""
    symbol: str = Field(description="The token symbol (e.g. ETH, USDC)")
    name: Optional[str] = Field(description="The token name (e.g. Ethereum, USD Coin)", default=None)
    blockchain: str = Field(description="The blockchain the token is on (e.g. Ethereum, Polygon)")
    contract_address: Optional[str] = Field(description="The token's contract address", default=None)
    project_url: Optional[str] = Field(description="The project's website URL", default=None)
    current_price: Optional[float] = Field(description="Current token price in USD", default=None)
    market_cap: Optional[float] = Field(description="Market capitalization in USD", default=None)
    volume_24h: Optional[float] = Field(description="24-hour trading volume in USD", default=None)
    price_change_24h: Optional[float] = Field(description="24-hour price change percentage", default=None)