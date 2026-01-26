"""
Data Schemas for Market Analysis Components
Defines strict data contracts using Pydantic for validation.
"""
from typing import Dict, List, Any, Optional, Union, Literal
from pydantic import BaseModel, Field, validator, model_validator
from datetime import datetime
from enum import Enum


class TimeframeEnum(str, Enum):
    """Valid timeframes"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class DirectionEnum(str, Enum):
    """Trade direction"""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class QualityRatingEnum(str, Enum):
    """Quality ratings"""
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


# ============================================================================
# Technical Indicators Schemas
# ============================================================================

class IndicatorData(BaseModel):
    """Validator for technical indicator data"""
    rsi_14: Optional[float] = Field(None, ge=0, le=100, description="RSI 14-period")
    rsi_21: Optional[float] = Field(None, ge=0, le=100, description="RSI 21-period")
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_width: Optional[float] = Field(None, ge=0)
    ema_9: Optional[float] = Field(None, gt=0)
    ema_21: Optional[float] = Field(None, gt=0)
    ema_50: Optional[float] = Field(None, gt=0)
    ema_200: Optional[float] = Field(None, gt=0)
    volume: Optional[float] = Field(None, ge=0)
    volume_sma: Optional[float] = Field(None, ge=0)
    vwap: Optional[float] = Field(None, gt=0)
    atr_14: Optional[float] = Field(None, ge=0)
    adx: Optional[float] = Field(None, ge=0, le=100)
    di_plus: Optional[float] = Field(None, ge=0)
    di_minus: Optional[float] = Field(None, ge=0)
    stoch_k: Optional[float] = Field(None, ge=0, le=100)
    stoch_d: Optional[float] = Field(None, ge=0, le=100)
    
    class Config:
        extra = "allow"  # Allow other indicators
        validate_assignment = True


class MultiTimeframeIndicators(BaseModel):
    """Indicators across multiple timeframes"""
    timeframes: Dict[str, IndicatorData] = Field(default_factory=dict)
    
    @validator('timeframes')
    def validate_timeframes(cls, v):
        """Ensure at least one timeframe"""
        if not v:
            raise ValueError("At least one timeframe required")
        return v


# ============================================================================
# SMC (Smart Money Concepts) Schemas
# ============================================================================

class OrderBlock(BaseModel):
    """Order Block structure"""
    type: Literal["bullish", "bearish"]
    price: float = Field(gt=0)
    zone: List[float] = Field(min_items=2, max_items=2)
    strength: float = Field(ge=0, le=1)
    timeframe: str
    timestamp: Optional[str] = None
    
    @validator('zone')
    def validate_zone(cls, v):
        """Ensure zone is valid [low, high]"""
        if v[0] >= v[1]:
            raise ValueError("Zone must be [low, high] where low < high")
        return v


class FairValueGap(BaseModel):
    """Fair Value Gap structure"""
    type: Literal["bullish", "bearish"]
    gap: List[float] = Field(min_items=2, max_items=2)
    price: Optional[float] = Field(None, gt=0)
    filled: bool = False
    timeframe: str
    timestamp: Optional[str] = None


class BreakOfStructure(BaseModel):
    """Break of Structure"""
    detected: bool
    direction: Optional[Literal["bullish", "bearish"]] = None
    level: Optional[float] = Field(None, gt=0)
    timeframe: str
    timestamp: Optional[str] = None


class SMCAnalysis(BaseModel):
    """Complete SMC Analysis results"""
    order_blocks: List[OrderBlock] = Field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = Field(default_factory=list)
    break_of_structure: Optional[Union[BreakOfStructure, List[BreakOfStructure]]] = None
    liquidity_zones: List[Dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        validate_assignment = True


# ============================================================================
# ICT (Inner Circle Trader) Schemas
# ============================================================================

class Killzone(BaseModel):
    """ICT Killzone data"""
    active: bool
    current_killzone: Optional[Literal["london", "new_york", "asian", "none"]] = None
    name: Optional[str] = None


class LiquiditySweep(BaseModel):
    """Liquidity sweep structure"""
    type: Literal["buy_side", "sell_side", "bullish_liquidity", "bearish_liquidity"]
    level: float = Field(gt=0)
    reversed: bool = False
    significance: Literal["high", "medium", "low"] = "medium"
    timeframe: str


class OTEZone(BaseModel):
    """Optimal Trade Entry zone"""
    in_ote_zone: bool
    in_zone: Optional[bool] = None  # Alias
    bias: Optional[Literal["long", "short"]] = None
    ote_low: Optional[float] = Field(None, gt=0)
    ote_high: Optional[float] = Field(None, gt=0)
    timeframe: Optional[str] = None


class ICTAnalysis(BaseModel):
    """Complete ICT Analysis results"""
    killzone: Optional[Killzone] = None
    liquidity_sweeps: List[LiquiditySweep] = Field(default_factory=list)
    ote_zones: Optional[OTEZone] = None
    order_flow: Optional[Dict[str, Any]] = None
    
    class Config:
        validate_assignment = True


# ============================================================================
# Market Structure Schemas
# ============================================================================

class MarketStructure(BaseModel):
    """Market structure data"""
    htf_trend: Literal["bullish", "bearish", "neutral"]
    mtf_trend: Literal["bullish", "bearish", "neutral"]
    structure_break: bool = False
    overall_bias: Optional[Literal["long", "short", "neutral"]] = None
    alignment: Optional[str] = None
    
    class Config:
        validate_assignment = True


class MarketRegime(BaseModel):
    """Market regime classification"""
    type: Literal["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING_HIGH_VOL", "RANGING_LOW_VOL", "UNKNOWN"]
    regime: Optional[str] = None  # Alias for type
    trend_strength: Literal["strong", "moderate", "weak"]
    volatility: Literal["high", "moderate", "low"]
    adx: float = Field(ge=0, le=100)
    atr: float = Field(ge=0)
    
    @model_validator(mode='after')
    def sync_regime_type(self):
        """Sync regime and type fields"""
        if self.regime and not self.type:
            self.type = self.regime
        elif self.type and not self.regime:
            self.regime = self.type
        return self


# ============================================================================
# Confluence Scoring Schemas
# ============================================================================

class Confluence(BaseModel):
    """Single confluence factor"""
    factor: str
    category: Literal["SMC", "ICT", "INDICATOR", "PATTERN", "STRUCTURE", "ALIGNMENT"]
    weight: float = Field(ge=0, le=2.0)
    description: str
    timeframe: str


class ConfluenceScore(BaseModel):
    """Confluence scoring result"""
    total_score: float = Field(ge=0)
    confluence_count: int = Field(ge=0)
    confluences: List[Confluence] = Field(default_factory=list)
    by_category: Dict[str, int] = Field(default_factory=dict)
    quality_rating: QualityRatingEnum
    meets_minimum: bool
    reasoning: str
    confidence_level: float = Field(ge=0, le=1.0)
    
    # Compatibility properties
    factors: Optional[List[Dict[str, Any]]] = None
    breakdown: Optional[Dict[str, float]] = None
    
    @model_validator(mode='after')
    def populate_compatibility_fields(self):
        """Auto-populate compatibility fields"""
        if self.confluences and not self.factors:
            self.factors = [c.dict() for c in self.confluences]
        if self.by_category and not self.breakdown:
            self.breakdown = {k: float(v) for k, v in self.by_category.items()}
        return self


# ============================================================================
# Trade Opportunity Schemas
# ============================================================================

class TradeOpportunity(BaseModel):
    """Trade opportunity structure"""
    direction: DirectionEnum
    confidence: float = Field(ge=0, le=1.0)
    entry_zone: List[float] = Field(min_items=2, max_items=2)
    stop_loss: float = Field(gt=0)
    take_profit: List[float] = Field(min_items=1)
    risk_reward: float = Field(gt=0)
    confluence_score: Optional[float] = Field(None, ge=0)
    confluence_count: Optional[int] = Field(None, ge=0)
    timeframe: str
    reasoning: Optional[str] = None
    
    @validator('entry_zone')
    def validate_entry_zone(cls, v):
        """Ensure entry zone is valid"""
        if v[0] >= v[1]:
            raise ValueError("Entry zone must be [low, high] where low < high")
        return v
    
    @validator('take_profit')
    def validate_take_profit(cls, v):
        """Ensure take profit levels are sorted"""
        if len(v) > 1 and v != sorted(v):
            raise ValueError("Take profit levels must be in ascending order")
        return v


# ============================================================================
# Analysis Result Schemas
# ============================================================================

class AnalysisResult(BaseModel):
    """Complete analysis result payload"""
    symbol: str
    timestamp: str
    current_price: Optional[float] = Field(None, gt=0)
    market_regime: Dict[str, Any]
    market_structure: Optional[Dict[str, Any]] = None
    smc_analysis: Dict[str, Any]
    ict_analysis: Dict[str, Any]
    mtf_analysis: Dict[str, Any]
    trade_opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    overall_confidence: Optional[float] = Field(None, ge=0, le=1.0)
    
    # Raw computational data (optional)
    _raw_computational: Optional[Dict[str, Any]] = None
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        """Ensure timestamp is valid ISO format"""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}")
        return v
    
    @validator('trade_opportunities')
    def validate_opportunities(cls, v):
        """Validate each trade opportunity"""
        for opp in v:
            if 'direction' not in opp:
                raise ValueError("Trade opportunity missing 'direction'")
            if 'confidence' not in opp:
                raise ValueError("Trade opportunity missing 'confidence'")
            # Validate direction
            if opp['direction'] not in ['LONG', 'SHORT', 'NEUTRAL']:
                raise ValueError(f"Invalid direction: {opp['direction']}")
            # Validate confidence
            if not (0 <= opp['confidence'] <= 1.0):
                raise ValueError(f"Confidence must be between 0 and 1: {opp['confidence']}")
        return v
    
    class Config:
        validate_assignment = True
        extra = "allow"


# ============================================================================
# Validation Decorators
# ============================================================================

def validate_input(schema: type[BaseModel]):
    """Decorator to validate function inputs"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Validate kwargs against schema
            try:
                validated = schema(**kwargs)
                kwargs = validated.dict()
            except Exception as e:
                raise ValueError(f"Input validation failed for {func.__name__}: {e}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_output(schema: type[BaseModel]):
    """Decorator to validate function outputs"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # Validate result against schema
            try:
                if isinstance(result, dict):
                    validated = schema(**result)
                    return validated.dict()
                return result
            except Exception as e:
                raise ValueError(f"Output validation failed for {func.__name__}: {e}")
        return wrapper
    return decorator


# ============================================================================
# Schema Registry
# ============================================================================

SCHEMA_REGISTRY = {
    'indicators': IndicatorData,
    'smc_analysis': SMCAnalysis,
    'ict_analysis': ICTAnalysis,
    'market_structure': MarketStructure,
    'market_regime': MarketRegime,
    'confluence_score': ConfluenceScore,
    'trade_opportunity': TradeOpportunity,
    'analysis_result': AnalysisResult,
}


def get_schema(name: str) -> type[BaseModel]:
    """Get schema by name"""
    if name not in SCHEMA_REGISTRY:
        raise ValueError(f"Unknown schema: {name}")
    return SCHEMA_REGISTRY[name]


def validate_data(data: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
    """Validate data against a named schema"""
    schema = get_schema(schema_name)
    validated = schema(**data)
    return validated.dict()
