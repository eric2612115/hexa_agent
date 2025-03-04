from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from .token import TokenInfo

class ThinkingStep(BaseModel):
    """AI思考过程中的一个步骤"""
    step_type: str = Field(description="Category of this thinking step (token_analysis, security, liquidity, etc.)")
    question: str = Field(description="Question the AI is asking itself")
    answer: str = Field(description="AI's answer to the question")
    evidence: Optional[str] = Field(description="Evidence or sources supporting this conclusion", default=None)
    confidence: str = Field(description="Confidence level (high, medium, low)")

class SecurityRating(BaseModel):
    """代币安全性评分"""
    risk_score: int = Field(description="Risk score from 1-10 (1 being least risky, 10 being most risky)")
    risk_level: str = Field(description="Risk level (Low, Medium, High, Critical)")
    security_issues: List[str] = Field(description="List of identified security issues")
    positive_signals: List[str] = Field(description="List of positive security signals")
    audit_status: Optional[str] = Field(description="Audit status if available", default=None)
    sources: List[str] = Field(description="Sources used for this assessment")

class MarketSentiment(BaseModel):
    """市场情绪分析"""
    overall_sentiment: str = Field(description="Overall market sentiment (Bullish, Bearish, Neutral)")
    bullish_signals: List[str] = Field(description="Bullish signals observed in the market")
    bearish_signals: List[str] = Field(description="Bearish signals observed in the market")
    trading_volume_change: str = Field(description="Description of 24h trading volume change")

class TradingAnalysis(BaseModel):
    """交易分析结果"""
    source_token: TokenInfo = Field(description="Information about the source token")
    target_token: TokenInfo = Field(description="Information about the target token")
    security_analysis: str = Field(description="Analysis of the security aspects of this trade")
    market_sentiment: Optional[MarketSentiment] = Field(description="Market sentiment analysis", default=None)
    contract_risk: str = Field(description="Assessment of contract risks")
    recommendation: str = Field(description="Trading recommendation")
    safe_to_execute: bool = Field(description="Whether the trade is considered safe to execute")
    thinking_steps: List[ThinkingStep] = Field(description="AI's thinking steps", default_factory=list)
    security_rating: Optional[SecurityRating] = Field(description="Security rating for the target token", default=None)
    sources_consulted: List[Dict[str, str]] = Field(description="Sources consulted during analysis", default_factory=list)