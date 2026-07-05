"""
Market Regime Detector
Classifies market conditions for adaptive trading
"""
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import numpy as np

class MarketRegime(Enum):
    """Market regime types"""
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"

@dataclass
class RegimeDetection:
    """Regime detection result"""
    regime: MarketRegime
    confidence: float  # 0-1
    indicators: Dict[str, float]
    detected_at: datetime
    
    def to_dict(self) -> Dict:
        return {
            'regime': self.regime.value,
            'confidence': round(self.confidence, 3),
            'indicators': {k: round(v, 2) for k, v in self.indicators.items()},
            'detected_at': self.detected_at.isoformat()
        }

class MarketRegimeDetector:
    """
    Market regime detection
    
    Uses technical indicators to classify market state:
    - Trending: Strong directional move (ADX > 25)
    - Ranging: Sideways movement (ADX < 20)
    - Volatile: High ATR (> 80th percentile)
    - Calm: Low ATR (< 20th percentile)
    """
    
    def __init__(self):
        # Historical normalized volatility (ATR/price) for percentile calculation,
        # keyed PER SYMBOL. Using ATR% (a fraction of price) instead of absolute
        # ATR makes the volatility percentile comparable across symbols with very
        # different price scales (e.g. BTC vs a sub-dollar alt). Keying per symbol
        # prevents one symbol's ATR distribution from polluting another's.
        self.atr_pct_history: Dict[str, List[float]] = {}
        self.max_history = 100

        # Current regime
        self.current_regime: Optional[RegimeDetection] = None

        logger.info("Market regime detector initialized")

    def load_history(self, symbol: str, history: List[float]) -> None:
        """Seed the per-symbol ATR% history (e.g. from persisted Redis state).

        Called by the memory agent before ``detect_regime`` so the volatility
        percentile is meaningful immediately after a restart instead of falling
        back to the neutral 0.5 default for the first ~100 cycles.
        """
        if not symbol:
            return
        # Keep only the most recent ``max_history`` samples.
        self.atr_pct_history[symbol] = list(history)[-self.max_history:]

    def get_history(self, symbol: str) -> List[float]:
        """Return the current per-symbol ATR% history for persistence."""
        return list(self.atr_pct_history.get(symbol, []))

    def detect_regime(
        self,
        adx: float,
        atr: float,
        trend_direction: str,  # 'up', 'down', 'sideways'
        volume_ratio: float = 1.0,
        atr_pct: Optional[float] = None,
        symbol: str = "_global",
    ) -> RegimeDetection:
        """
        Detect current market regime

        Args:
            adx: Average Directional Index (trend strength)
            atr: Average True Range (absolute volatility, kept for reporting)
            trend_direction: Overall trend direction
            volume_ratio: Volume vs average
            atr_pct: ATR normalized by price (ATR/price). This is what drives
                the volatility percentile so it is comparable across symbols.
                If not supplied, falls back to absolute ``atr`` (legacy behavior).
            symbol: Symbol the ATR% history is tracked under.

        Returns:
            RegimeDetection
        """
        # Prefer normalized ATR% for cross-symbol-comparable volatility ranking.
        # Fall back to absolute ATR only if a caller doesn't provide atr_pct.
        vol_measure = atr_pct if atr_pct is not None else atr

        # Update this symbol's normalized-volatility history.
        history = self.atr_pct_history.setdefault(symbol, [])
        history.append(vol_measure)
        if len(history) > self.max_history:
            history.pop(0)

        # Calculate volatility percentile within this symbol's own history.
        atr_percentile = self._calculate_percentile(vol_measure, history)

        # Detect regime
        regime, confidence = self._classify_regime(
            adx=adx,
            atr=atr,
            atr_percentile=atr_percentile,
            trend_direction=trend_direction,
            volume_ratio=volume_ratio
        )

        detection = RegimeDetection(
            regime=regime,
            confidence=confidence,
            indicators={
                'adx': adx,
                'atr': atr,
                'atr_pct': vol_measure,
                'atr_percentile': atr_percentile,
                'volume_ratio': volume_ratio
            },
            detected_at=datetime.now()
        )
        
        # Update current regime
        self.current_regime = detection
        
        logger.info(f"Regime detected: {regime.value} (confidence: {confidence:.2f})")
        
        return detection
    
    def _classify_regime(
        self,
        adx: float,
        atr: float,
        atr_percentile: float,
        trend_direction: str,
        volume_ratio: float
    ) -> Tuple[MarketRegime, float]:
        """
        Classify market regime based on indicators
        
        Returns:
            (regime, confidence)
        """
        
        # High volatility check
        if atr_percentile > 0.8:
            return MarketRegime.VOLATILE, 0.8
        
        # Low volatility check
        if atr_percentile < 0.2:
            return MarketRegime.CALM, 0.7
        
        # Strong trend
        if adx > 25:
            if trend_direction == 'up':
                confidence = min(adx / 50, 1.0)
                return MarketRegime.TRENDING_BULLISH, confidence
            elif trend_direction == 'down':
                confidence = min(adx / 50, 1.0)
                return MarketRegime.TRENDING_BEARISH, confidence
        
        # Ranging market
        if adx < 20:
            confidence = 1.0 - (adx / 20)
            return MarketRegime.RANGING, confidence
        
        # Default to ranging with lower confidence
        return MarketRegime.RANGING, 0.5
    
    def _calculate_percentile(
        self,
        value: float,
        history: List[float]
    ) -> float:
        """Calculate percentile of value in history"""
        
        if not history:
            return 0.5
        
        sorted_history = sorted(history)
        position = sum(1 for h in sorted_history if h < value)
        
        percentile = position / len(sorted_history)
        
        return percentile
    
    def get_strategy_recommendations(
        self,
        regime: Optional[MarketRegime] = None
    ) -> Dict[str, Any]:
        """
        Get trading strategy recommendations for regime
        
        Args:
            regime: Market regime (uses current if None)
            
        Returns:
            Strategy recommendations
        """
        
        if regime is None:
            if self.current_regime:
                regime = self.current_regime.regime
            else:
                return {}
        
        recommendations = {
            MarketRegime.TRENDING_BULLISH: {
                'preferred_strategies': ['breakout_retest', 'pullback_entry'],
                'avoid_strategies': ['mean_reversion'],
                'position_sizing': 'standard',
                'risk_adjustment': 1.0,
                'notes': 'Favor trend-following setups'
            },
            MarketRegime.TRENDING_BEARISH: {
                'preferred_strategies': ['breakdown_retest', 'rally_short'],
                'avoid_strategies': ['mean_reversion'],
                'position_sizing': 'standard',
                'risk_adjustment': 1.0,
                'notes': 'Favor trend-following short setups'
            },
            MarketRegime.RANGING: {
                'preferred_strategies': ['range_trading', 'mean_reversion'],
                'avoid_strategies': ['breakout', 'trend_following'],
                'position_sizing': 'reduced',
                'risk_adjustment': 0.75,
                'notes': 'Trade range boundaries, avoid breakouts'
            },
            MarketRegime.VOLATILE: {
                'preferred_strategies': ['momentum'],
                'avoid_strategies': ['tight_stops'],
                'position_sizing': 'reduced',
                'risk_adjustment': 0.5,
                'notes': 'Reduce size, widen stops'
            },
            MarketRegime.CALM: {
                'preferred_strategies': ['all'],
                'avoid_strategies': [],
                'position_sizing': 'standard',
                'risk_adjustment': 1.0,
                'notes': 'Ideal conditions for most strategies'
            }
        }
        
        return recommendations.get(regime, {})
