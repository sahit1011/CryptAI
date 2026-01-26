"""
Data Models for Market Analysis
Defines strict data contracts using Pydantic for validation.
"""
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime

class IndicatorData(BaseModel):
    """Validator for technical indicator data"""
    rsi_14: Optional[float] = None
    macd_histogram: Optional[float] = None
    volume: Optional[float] = None
    volume_sma: Optional[float] = None
    adx: Optional[float] = None
    atr_14: Optional[float] = None
    
    class Config:
        extra = "allow" # Allow other indicators

class OrderBlock(BaseModel):
    """Validator for Order Block data"""
    type: str # 'bullish' or 'bearish'
    price: float
    timeframe: str
    strength: Optional[float] = 0.5
    zone: Optional[List[float]] = None

class SMCAnalysis(BaseModel):
    """Validator for SMC Analysis results"""
    order_blocks: List[OrderBlock] = []
    fair_value_gaps: List[Dict[str, Any]] = []
    break_of_structure: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    liquidity_zones: List[Dict[str, Any]] = []

class MarketStructure(BaseModel):
    """Validator for Market Structure data"""
    htf_trend: str
    mtf_trend: str
    structure_break: Optional[bool] = False

class AnalysisResult(BaseModel):
    """Validator for final Analysis Result payload"""
    symbol: str
    timestamp: str
    market_regime: Dict[str, Any]
    smc_analysis: Dict[str, Any] # Can be validated further with SMCAnalysis
    ict_analysis: Dict[str, Any]
    mtf_analysis: Dict[str, Any]
    trade_opportunities: List[Dict[str, Any]]

    class Config:
        extra = "allow"  # Allow additional fields for flexibility

    @validator('trade_opportunities')
    def validate_opportunities(cls, v):
        for opp in v:
            if 'direction' not in opp:
                raise ValueError("Trade opportunity missing 'direction'")
            if 'confidence' not in opp:
                raise ValueError("Trade opportunity missing 'confidence'")
        return v
