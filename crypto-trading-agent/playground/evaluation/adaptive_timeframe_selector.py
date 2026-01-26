"""
Adaptive Timeframe Selector
Selects optimal timeframes based on market regime and trading style
"""
from typing import Dict, List, Any
from dataclasses import dataclass
from loguru import logger

from playground.evaluation.regime_detector import MarketRegime, RegimeType


@dataclass
class TimeframeStrategy:
    """Timeframe selection strategy for a specific regime"""
    primary_timeframes: List[str]  # Main analysis timeframes
    secondary_timeframes: List[str]  # Supporting/confirmation timeframes
    reference_timeframes: List[str]  # Context/bias timeframes
    avoid_timeframes: List[str]  # Timeframes to avoid (too noisy/slow)
    reasoning: str


class AdaptiveTimeframeSelector:
    """
    Select optimal timeframes based on market regime
    
    Professional Quant Trader Approach:
    - HTF (Higher Timeframe): 1D, 4H - for bias and structure
    - MTF (Medium Timeframe): 1H, 15M - for setup identification
    - LTF (Lower Timeframe): 5M, 1M - for entry refinement
    
    Regime-Specific Selection:
    - TRENDING: HTF for bias, MTF for entry, avoid LTF noise
    - RANGING: MTF for boundaries, LTF for scalps
    - VOLATILE: HTF only, avoid LTF completely
    """
    
    def __init__(self):
        """Initialize adaptive timeframe selector"""
        # Define timeframe hierarchy
        self.timeframe_hierarchy = {
            'HTF': ['1d', '4h'],
            'MTF': ['1h', '15m'],
            'LTF': ['5m', '1m']
        }
        
        logger.info("AdaptiveTimeframeSelector initialized")
    
    def select_timeframes(
        self,
        regime: MarketRegime,
        trading_style: str = 'swing'  # 'swing', 'day_trade', 'scalp'
    ) -> TimeframeStrategy:
        """
        Select optimal timeframes based on regime and trading style
        
        Args:
            regime: Detected market regime
            trading_style: Trading style preference
        
        Returns:
            TimeframeStrategy with selected timeframes
        """
        # Base selection on regime
        if regime.regime == 'TRENDING_BULLISH' or regime.regime == 'TRENDING_BEARISH':
            strategy = self._select_trending_timeframes(regime, trading_style)
        
        elif regime.regime == 'RANGING':
            strategy = self._select_ranging_timeframes(regime, trading_style)
        
        elif regime.regime == 'VOLATILE':
            strategy = self._select_volatile_timeframes(regime, trading_style)
        
        else:  # UNKNOWN
            strategy = self._select_default_timeframes(trading_style)
        
        logger.info(
            f"Selected timeframes for {regime.regime} ({trading_style}): "
            f"Primary={strategy.primary_timeframes}, Secondary={strategy.secondary_timeframes}"
        )
        
        return strategy
    
    def _select_trending_timeframes(
        self,
        regime: MarketRegime,
        trading_style: str
    ) -> TimeframeStrategy:
        """Select timeframes for trending markets"""
        
        if trading_style == 'swing':
            # Swing trading in trends: HTF bias, MTF entry
            return TimeframeStrategy(
                primary_timeframes=['4h', '1h'],
                secondary_timeframes=['15m'],
                reference_timeframes=['1d'],
                avoid_timeframes=['5m', '1m'],
                reasoning=(
                    f"Trending market ({regime.regime}) with swing trading style. "
                    "Using HTF (4H/1H) for structure and bias, MTF (15M) for entry refinement. "
                    "Avoiding LTF (5M/1M) to reduce noise in strong trends."
                )
            )
        
        elif trading_style == 'day_trade':
            # Day trading in trends: MTF bias, LTF entry
            return TimeframeStrategy(
                primary_timeframes=['1h', '15m'],
                secondary_timeframes=['5m'],
                reference_timeframes=['4h'],
                avoid_timeframes=['1m'],
                reasoning=(
                    f"Trending market ({regime.regime}) with day trading style. "
                    "Using MTF (1H/15M) for structure, LTF (5M) for entries. "
                    "Avoiding 1M timeframe to reduce false signals."
                )
            )
        
        else:  # scalp
            # Scalping in trends: MTF bias, LTF execution
            return TimeframeStrategy(
                primary_timeframes=['15m', '5m'],
                secondary_timeframes=['1m'],
                reference_timeframes=['1h'],
                avoid_timeframes=[],
                reasoning=(
                    f"Trending market ({regime.regime}) with scalping style. "
                    "Using MTF (15M/5M) for bias, LTF (1M) for quick entries. "
                    "Trend provides directional bias for scalps."
                )
            )
    
    def _select_ranging_timeframes(
        self,
        regime: MarketRegime,
        trading_style: str
    ) -> TimeframeStrategy:
        """Select timeframes for ranging markets"""
        
        if trading_style == 'swing':
            # Swing trading in ranges: MTF for boundaries
            return TimeframeStrategy(
                primary_timeframes=['4h', '1h'],
                secondary_timeframes=['15m'],
                reference_timeframes=['1d'],
                avoid_timeframes=[],
                reasoning=(
                    "Ranging market - swing trading range boundaries. "
                    "Using HTF/MTF (4H/1H) to identify range limits, "
                    "15M for entry confirmation at support/resistance."
                )
            )
        
        elif trading_style == 'day_trade':
            # Day trading in ranges: MTF boundaries, LTF entries
            return TimeframeStrategy(
                primary_timeframes=['1h', '15m'],
                secondary_timeframes=['5m'],
                reference_timeframes=['4h'],
                avoid_timeframes=[],
                reasoning=(
                    "Ranging market - day trading within range. "
                    "Using MTF (1H/15M) for range boundaries, "
                    "LTF (5M) for entries at extremes."
                )
            )
        
        else:  # scalp
            # Scalping in ranges: LTF mean reversion
            return TimeframeStrategy(
                primary_timeframes=['15m', '5m', '1m'],
                secondary_timeframes=[],
                reference_timeframes=['1h'],
                avoid_timeframes=[],
                reasoning=(
                    "Ranging market - scalping mean reversion. "
                    "Using LTF (15M/5M/1M) for quick reversals at range extremes. "
                    "Range provides clear support/resistance for scalps."
                )
            )
    
    def _select_volatile_timeframes(
        self,
        regime: MarketRegime,
        trading_style: str
    ) -> TimeframeStrategy:
        """Select timeframes for volatile markets"""
        
        # In high volatility, prefer HTF regardless of style
        # Reduce position size and wait for clarity
        
        return TimeframeStrategy(
            primary_timeframes=['1d', '4h'],
            secondary_timeframes=['1h'],
            reference_timeframes=[],
            avoid_timeframes=['15m', '5m', '1m'],
            reasoning=(
                f"High volatility market (ATR ratio: {regime.atr_ratio:.2f}). "
                "Using only HTF (1D/4H) for big picture, avoiding LTF noise. "
                "Recommend reducing position size or waiting for clarity."
            )
        )
    
    def _select_default_timeframes(
        self,
        trading_style: str
    ) -> TimeframeStrategy:
        """Select default timeframes when regime is unknown"""
        
        # Conservative approach: use multiple timeframes
        return TimeframeStrategy(
            primary_timeframes=['4h', '1h', '15m'],
            secondary_timeframes=['5m'],
            reference_timeframes=['1d'],
            avoid_timeframes=[],
            reasoning=(
                "Unknown market regime - using balanced multi-timeframe approach. "
                "Covering HTF (4H), MTF (1H/15M), and LTF (5M) for comprehensive analysis."
            )
        )
    
    def get_analysis_priority(
        self,
        strategy: TimeframeStrategy
    ) -> Dict[str, int]:
        """
        Get analysis priority for each timeframe
        
        Higher priority = analyze first and weight more heavily
        
        Args:
            strategy: Timeframe strategy
        
        Returns:
            Dictionary mapping timeframe to priority (1-10)
        """
        priority = {}
        
        # Primary timeframes: highest priority
        for i, tf in enumerate(strategy.primary_timeframes):
            priority[tf] = 10 - i  # First primary gets 10, second gets 9, etc.
        
        # Secondary timeframes: medium priority
        for i, tf in enumerate(strategy.secondary_timeframes):
            priority[tf] = 7 - i
        
        # Reference timeframes: lower priority
        for i, tf in enumerate(strategy.reference_timeframes):
            priority[tf] = 5 - i
        
        # Avoid timeframes: lowest priority (still analyze but don't weight heavily)
        for tf in strategy.avoid_timeframes:
            priority[tf] = 1
        
        return priority
    
    def should_analyze_timeframe(
        self,
        timeframe: str,
        strategy: TimeframeStrategy
    ) -> bool:
        """
        Check if a timeframe should be analyzed
        
        Args:
            timeframe: Timeframe to check
            strategy: Timeframe strategy
        
        Returns:
            True if should analyze, False otherwise
        """
        # Always analyze primary and secondary
        if timeframe in strategy.primary_timeframes:
            return True
        
        if timeframe in strategy.secondary_timeframes:
            return True
        
        # Analyze reference for context
        if timeframe in strategy.reference_timeframes:
            return True
        
        # Skip avoided timeframes in high-conviction regimes
        if timeframe in strategy.avoid_timeframes:
            return False
        
        # Analyze everything else with lower priority
        return True


def test_adaptive_timeframe_selector():
    """Test the adaptive timeframe selector"""
    from playground.evaluation.regime_detector import MarketRegime
    
    # Test trending market
    trending_regime = MarketRegime(
        regime='TRENDING_BULLISH',
        confidence=0.85,
        trend_strength=0.75,
        volatility_level=0.40,
        adx_value=32.5,
        atr_ratio=1.2,
        bb_width=0.025,
        reasoning="Strong bullish trend with ADX 32.5"
    )
    
    selector = AdaptiveTimeframeSelector()
    
    # Test different trading styles
    for style in ['swing', 'day_trade', 'scalp']:
        logger.info(f"\n=== Testing {style.upper()} in TRENDING market ===")
        strategy = selector.select_timeframes(trending_regime, style)
        
        logger.info(f"Primary: {strategy.primary_timeframes}")
        logger.info(f"Secondary: {strategy.secondary_timeframes}")
        logger.info(f"Reference: {strategy.reference_timeframes}")
        logger.info(f"Avoid: {strategy.avoid_timeframes}")
        logger.info(f"Reasoning: {strategy.reasoning}")
        
        # Get priorities
        priorities = selector.get_analysis_priority(strategy)
        logger.info(f"Priorities: {priorities}")
    
    # Test ranging market
    ranging_regime = MarketRegime(
        regime='RANGING',
        confidence=0.80,
        trend_strength=0.15,
        volatility_level=0.30,
        adx_value=18.0,
        atr_ratio=0.9,
        bb_width=0.015,
        reasoning="Low ADX with tight Bollinger Bands"
    )
    
    logger.info(f"\n=== Testing SCALP in RANGING market ===")
    strategy = selector.select_timeframes(ranging_regime, 'scalp')
    logger.info(f"Primary: {strategy.primary_timeframes}")
    logger.info(f"Reasoning: {strategy.reasoning}")
    
    # Test volatile market
    volatile_regime = MarketRegime(
        regime='VOLATILE',
        confidence=0.90,
        trend_strength=0.50,
        volatility_level=0.85,
        adx_value=25.0,
        atr_ratio=2.1,
        bb_width=0.045,
        reasoning="High volatility with ATR 2.1x average"
    )
    
    logger.info(f"\n=== Testing SWING in VOLATILE market ===")
    strategy = selector.select_timeframes(volatile_regime, 'swing')
    logger.info(f"Primary: {strategy.primary_timeframes}")
    logger.info(f"Avoid: {strategy.avoid_timeframes}")
    logger.info(f"Reasoning: {strategy.reasoning}")


if __name__ == "__main__":
    test_adaptive_timeframe_selector()
