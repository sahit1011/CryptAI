"""
Regime Detector for Adaptive Market Analysis
Classifies market conditions to adapt analysis strategy
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Literal
from loguru import logger
from dataclasses import dataclass


RegimeType = Literal['TRENDING_BULLISH', 'TRENDING_BEARISH', 'RANGING', 'VOLATILE', 'UNKNOWN']


@dataclass
class MarketRegime:
    """Market regime classification result"""
    regime: RegimeType
    confidence: float
    trend_strength: float  # 0-1
    volatility_level: float  # 0-1
    adx_value: float
    atr_ratio: float
    bb_width: float
    reasoning: str


class RegimeDetector:
    """
    Detect market regime to adapt analysis strategy
    
    Regimes:
    - TRENDING_BULLISH: Strong uptrend (ADX >25, price above EMAs)
    - TRENDING_BEARISH: Strong downtrend (ADX >25, price below EMAs)
    - RANGING: Consolidation (ADX <20, tight BB)
    - VOLATILE: High volatility (ATR >1.5x average, wide BB)
    
    Professional Trader Psychology:
    - Trending: Focus on HTF structure, ride the trend
    - Ranging: Focus on range boundaries, scalp reversals
    - Volatile: Reduce position size, wait for clarity
    """
    
    def __init__(self):
        """Initialize regime detector"""
        self.thresholds = {
            'trending_adx': 25,
            'ranging_adx': 20,
            'high_volatility_atr': 1.5,
            'ranging_bb_width': 0.02
        }
        
        logger.info("RegimeDetector initialized")
    
    def detect(
        self,
        df: pd.DataFrame,
        indicators: Dict[str, pd.Series]
    ) -> MarketRegime:
        """
        Detect current market regime
        
        Args:
            df: OHLCV DataFrame
            indicators: Pre-calculated indicators
        
        Returns:
            MarketRegime classification
        """
        try:
            # Helper function to safely extract scalar from Series or return default
            def safe_extract(series, default=0.0):
                if series is None:
                    return default
                if hasattr(series, 'iloc'):
                    return series.iloc[-1] if len(series) > 0 else default
                return float(series) if series is not None else default
            
            # Extract key indicators safely
            adx = safe_extract(indicators.get('adx'), 0.0)
            di_plus = safe_extract(indicators.get('di_plus'), 0.0)
            di_minus = safe_extract(indicators.get('di_minus'), 0.0)
            
            # ATR analysis
            atr_series = indicators.get('atr_14')
            atr = safe_extract(atr_series, 0.0)
            
            if atr_series is not None and hasattr(atr_series, 'rolling'):
                atr_sma = safe_extract(atr_series.rolling(14).mean(), atr)
            else:
                atr_sma = atr
            
            atr_ratio = atr / atr_sma if atr_sma > 0 else 1.0
            
            # Bollinger Bands width
            bb_width = safe_extract(indicators.get('bb_width'), 0.0)
            
            # EMA alignment
            current_price = df['close'].iloc[-1]
            ema_21 = safe_extract(indicators.get('ema_21'), current_price)
            ema_50 = safe_extract(indicators.get('ema_50'), current_price)
            ema_200 = safe_extract(indicators.get('ema_200'), current_price)
            
            # Classify regime
            regime, confidence, reasoning = self._classify_regime(
                adx=adx,
                di_plus=di_plus,
                di_minus=di_minus,
                atr_ratio=atr_ratio,
                bb_width=bb_width,
                current_price=current_price,
                ema_21=ema_21,
                ema_50=ema_50,
                ema_200=ema_200
            )
            
            # Calculate metrics
            trend_strength = min(adx / 50.0, 1.0)  # Normalize ADX to 0-1
            volatility_level = min(atr_ratio / 2.0, 1.0)  # Normalize ATR ratio
            
            result = MarketRegime(
                regime=regime,
                confidence=confidence,
                trend_strength=trend_strength,
                volatility_level=volatility_level,
                adx_value=adx,
                atr_ratio=atr_ratio,
                bb_width=bb_width,
                reasoning=reasoning
            )
            
            logger.info(
                f"Regime detected: {regime} (confidence: {confidence:.2%}, "
                f"ADX: {adx:.1f}, ATR ratio: {atr_ratio:.2f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting regime: {e}", exc_info=True)
            return MarketRegime(
                regime='UNKNOWN',
                confidence=0.0,
                trend_strength=0.0,
                volatility_level=0.0,
                adx_value=0.0,
                atr_ratio=1.0,
                bb_width=0.0,
                reasoning=f"Error: {str(e)}"
            )
    
    def _classify_regime(
        self,
        adx: float,
        di_plus: float,
        di_minus: float,
        atr_ratio: float,
        bb_width: float,
        current_price: float,
        ema_21: float,
        ema_50: float,
        ema_200: float
    ) -> tuple[RegimeType, float, str]:
        """
        Classify regime based on indicators
        
        Returns:
            (regime, confidence, reasoning)
        """
        reasons = []
        
        # Check for high volatility first
        if atr_ratio > self.thresholds['high_volatility_atr']:
            reasons.append(f"High volatility (ATR {atr_ratio:.2f}x average)")
            confidence = min(0.7 + (atr_ratio - 1.5) * 0.1, 0.95)
            return 'VOLATILE', confidence, "; ".join(reasons)
        
        # Check for trending market
        if adx > self.thresholds['trending_adx']:
            # Determine trend direction
            if di_plus > di_minus and current_price > ema_21 > ema_50:
                reasons.append(f"Strong bullish trend (ADX {adx:.1f})")
                reasons.append(f"Price above EMAs ({current_price:.2f} > {ema_21:.2f} > {ema_50:.2f})")
                confidence = min(0.7 + (adx - 25) / 50, 0.95)
                return 'TRENDING_BULLISH', confidence, "; ".join(reasons)
            
            elif di_minus > di_plus and current_price < ema_21 < ema_50:
                reasons.append(f"Strong bearish trend (ADX {adx:.1f})")
                reasons.append(f"Price below EMAs ({current_price:.2f} < {ema_21:.2f} < {ema_50:.2f})")
                confidence = min(0.7 + (adx - 25) / 50, 0.95)
                return 'TRENDING_BEARISH', confidence, "; ".join(reasons)
            
            else:
                # ADX high but direction unclear
                reasons.append(f"Trend strength high (ADX {adx:.1f}) but direction mixed")
                return 'RANGING', 0.6, "; ".join(reasons)
        
        # Check for ranging market
        if adx < self.thresholds['ranging_adx'] and bb_width < self.thresholds['ranging_bb_width']:
            reasons.append(f"Low trend strength (ADX {adx:.1f})")
            reasons.append(f"Tight Bollinger Bands (width {bb_width:.4f})")
            confidence = 0.7 + (self.thresholds['ranging_adx'] - adx) / 20 * 0.2
            return 'RANGING', min(confidence, 0.9), "; ".join(reasons)
        
        # Default to ranging with lower confidence
        reasons.append(f"Mixed signals (ADX {adx:.1f}, BB width {bb_width:.4f})")
        return 'RANGING', 0.5, "; ".join(reasons)
    
    def get_recommended_timeframes(self, regime: MarketRegime) -> Dict[str, list]:
        """
        Get recommended timeframes based on regime
        
        Professional Trader Approach:
        - Trending: HTF for bias, MTF for entry
        - Ranging: MTF for boundaries, LTF for scalps
        - Volatile: HTF only, avoid LTF noise
        
        Args:
            regime: Detected market regime
        
        Returns:
            Dictionary with primary and secondary timeframes
        """
        if regime.regime == 'TRENDING_BULLISH' or regime.regime == 'TRENDING_BEARISH':
            return {
                'primary': ['4h', '1h'],      # Structure and bias
                'secondary': ['15m', '5m'],    # Entry refinement
                'reference': ['1d'],           # Overall context
                'avoid': ['1m']                # Too much noise in trends
            }
        
        elif regime.regime == 'RANGING':
            return {
                'primary': ['1h', '15m'],      # Range boundaries
                'secondary': ['5m', '1m'],     # Scalping opportunities
                'reference': ['4h'],           # Range context
                'avoid': []                    # All timeframes useful
            }
        
        elif regime.regime == 'VOLATILE':
            return {
                'primary': ['1d', '4h'],       # Big picture only
                'secondary': ['1h'],           # Confirmation
                'reference': [],
                'avoid': ['15m', '5m', '1m']   # Avoid LTF in volatility
            }
        
        else:  # UNKNOWN
            return {
                'primary': ['4h', '1h', '15m'],
                'secondary': ['5m'],
                'reference': ['1d'],
                'avoid': []
            }
    
    def get_strategy_recommendations(self, regime: MarketRegime) -> Dict[str, Any]:
        """
        Get trading strategy recommendations based on regime
        
        Args:
            regime: Detected market regime
        
        Returns:
            Strategy recommendations
        """
        if regime.regime == 'TRENDING_BULLISH':
            return {
                'bias': 'LONG',
                'strategy_types': ['SWING', 'DAY_TRADE'],
                'entry_approach': 'Pullback to demand zones',
                'risk_management': 'Trail stops, let winners run',
                'confluences_required': 3,
                'confidence_threshold': 0.70
            }
        
        elif regime.regime == 'TRENDING_BEARISH':
            return {
                'bias': 'SHORT',
                'strategy_types': ['SWING', 'DAY_TRADE'],
                'entry_approach': 'Pullback to supply zones',
                'risk_management': 'Trail stops, let winners run',
                'confluences_required': 3,
                'confidence_threshold': 0.70
            }
        
        elif regime.regime == 'RANGING':
            return {
                'bias': 'NEUTRAL',
                'strategy_types': ['SCALP', 'DAY_TRADE'],
                'entry_approach': 'Fade extremes, buy support/sell resistance',
                'risk_management': 'Tight stops, quick profits',
                'confluences_required': 4,  # Need more confirmation in ranges
                'confidence_threshold': 0.75
            }
        
        elif regime.regime == 'VOLATILE':
            return {
                'bias': 'WAIT',
                'strategy_types': [],
                'entry_approach': 'Wait for clarity, reduce position size',
                'risk_management': 'Wider stops or stay out',
                'confluences_required': 5,  # Very high bar in volatility
                'confidence_threshold': 0.85
            }
        
        else:  # UNKNOWN
            return {
                'bias': 'NEUTRAL',
                'strategy_types': ['DAY_TRADE'],
                'entry_approach': 'Wait for clear setup',
                'risk_management': 'Standard risk (2%)',
                'confluences_required': 4,
                'confidence_threshold': 0.75
            }


def test_regime_detector():
    """Test the regime detector"""
    import pandas_ta as ta
    
    # Create sample data (trending bullish)
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='1H')
    
    # Simulate trending market
    trend = np.linspace(40000, 45000, 200)
    noise = np.random.randn(200) * 100
    close_prices = trend + noise
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': close_prices - 50,
        'high': close_prices + 100,
        'low': close_prices - 100,
        'close': close_prices,
        'volume': np.random.randint(1000, 10000, 200)
    })
    df.set_index('timestamp', inplace=True)
    
    # Calculate indicators
    indicators = {}
    indicators['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14']
    indicators['di_plus'] = ta.adx(df['high'], df['low'], df['close'], length=14)['DMP_14']
    indicators['di_minus'] = ta.adx(df['high'], df['low'], df['close'], length=14)['DMN_14']
    indicators['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    indicators['ema_21'] = ta.ema(df['close'], length=21)
    indicators['ema_50'] = ta.ema(df['close'], length=50)
    indicators['ema_200'] = ta.ema(df['close'], length=200)
    
    bb = ta.bbands(df['close'], length=20, std=2)
    indicators['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
    
    # Detect regime
    detector = RegimeDetector()
    regime = detector.detect(df, indicators)
    
    logger.info(f"Detected Regime: {regime.regime}")
    logger.info(f"Confidence: {regime.confidence:.2%}")
    logger.info(f"Reasoning: {regime.reasoning}")
    
    # Get recommendations
    timeframes = detector.get_recommended_timeframes(regime)
    strategy = detector.get_strategy_recommendations(regime)
    
    logger.info(f"Recommended Timeframes: {timeframes}")
    logger.info(f"Strategy: {strategy}")


if __name__ == "__main__":
    test_regime_detector()
