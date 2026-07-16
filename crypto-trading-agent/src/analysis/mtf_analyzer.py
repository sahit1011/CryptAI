"""
Multi-Timeframe Analyzer
Analyzes trend alignment and bias across multiple timeframes
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from loguru import logger

class MultiTimeframeAnalyzer:
    """
    Analyzes market structure across multiple timeframes
    to determine overall bias and alignment
    """

    TIMEFRAME_HIERARCHY = {
        '1d': 5,   # Highest weight
        '4h': 4,
        '1h': 3,
        '15m': 2,
        '5m': 1    # Lowest weight
    }

    def __init__(self):
        pass

    def analyze(
        self,
        candles: Dict[str, pd.DataFrame],
        indicators: Dict[str, Dict[str, pd.Series]]
    ) -> Dict[str, Any]:
        """
        Complete multi-timeframe analysis

        Returns:
            {
                'overall_bias': 'bullish/bearish/neutral',
                'bias_strength': 0-1,
                'alignment': 'aligned/conflicting',
                'timeframe_trends': {...},
                'entry_timing': 'excellent/good/fair/poor',
                'recommendation': str
            }
        """

        try:
            logger.info("Running multi-timeframe analysis...")

            # Analyze each timeframe
            tf_trends = {}
            for tf in ['1d', '4h', '1h', '15m', '5m']:
                if tf in candles and tf in indicators:
                    tf_trends[tf] = self._analyze_timeframe(
                        candles[tf],
                        indicators[tf]
                    )

            # Determine overall bias
            overall_bias, bias_strength = self._determine_overall_bias(tf_trends)

            # Check alignment
            alignment = self._check_alignment(tf_trends)

            # Determine entry timing
            entry_timing = self._evaluate_entry_timing(tf_trends, overall_bias)

            # Generate recommendation
            recommendation = self._generate_recommendation(
                overall_bias, bias_strength, alignment, entry_timing
            )

            return {
                'overall_bias': overall_bias,
                'bias_strength': round(bias_strength, 3),
                'alignment': alignment,
                'timeframe_trends': tf_trends,
                'entry_timing': entry_timing,
                'recommendation': recommendation,
                'confluence_score': self._calculate_confluence_score(tf_trends)
            }

        except Exception as e:
            logger.error(f"Error in MTF analysis: {e}", exc_info=True)
            return self._empty_result()

    def _analyze_timeframe(
        self,
        df: pd.DataFrame,
        indicators: Dict[str, pd.Series]
    ) -> Dict[str, Any]:
        """Analyze single timeframe"""

        if len(df) < 20:
            return {'trend': 'unknown', 'strength': 0}

        # Trend from EMAs
        ema_trend = self._get_ema_trend(indicators)

        # Trend from price action
        price_trend = self._get_price_trend(df)

        # Momentum from MACD
        momentum = self._get_momentum(indicators)

        # Volume trend
        volume_trend = self._get_volume_trend(df)

        # RSI position
        rsi_position = self._get_rsi_position(indicators)

        # Combine signals
        trend_score = self._calculate_trend_score(
            ema_trend, price_trend, momentum, volume_trend, rsi_position
        )

        if trend_score > 0.6:
            trend = 'bullish'
        elif trend_score < -0.6:
            trend = 'bearish'
        else:
            trend = 'neutral'

        strength = abs(trend_score)

        return {
            'trend': trend,
            'strength': round(strength, 3),
            'ema_alignment': ema_trend,
            'price_action': price_trend,
            'momentum': momentum,
            'volume': volume_trend,
            'rsi': rsi_position
        }

    def _get_ema_trend(self, indicators: Dict) -> str:
        """Determine trend from EMA alignment"""
        try:
            ema_9 = indicators.get('ema_9', pd.Series([0])).iloc[-1]
            ema_21 = indicators.get('ema_21', pd.Series([0])).iloc[-1]
            ema_50 = indicators.get('ema_50', pd.Series([0])).iloc[-1]
            ema_200 = indicators.get('ema_200', pd.Series([0])).iloc[-1]

            if ema_9 > ema_21 > ema_50 > ema_200:
                return 'bullish'
            elif ema_9 < ema_21 < ema_50 < ema_200:
                return 'bearish'
            return 'neutral'
        except Exception:
            return 'neutral'

    def _get_price_trend(self, df: pd.DataFrame) -> str:
        """Determine trend from price action"""
        if len(df) < 20:
            return 'neutral'

        close = df['close'].values

        # Simple linear regression slope (price change per period)
        y = close[-20:]
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]

        # Normalize the slope by the mean close so the threshold is price-agnostic.
        # Absolute thresholds (e.g. slope > 10) only work for high-priced assets:
        # a $0.05 alt could be ripping +40%/window and still read 'neutral' because
        # its raw slope is tiny. Dividing by mean(close) converts the slope into a
        # per-period fractional change so the same threshold applies to BTC and a
        # sub-dollar alt alike.
        mean_close = float(np.mean(y))
        if mean_close <= 0:
            return 'neutral'

        # Fractional price change per period. ~0.001 (=0.1% per bar) over a 20-bar
        # window is a meaningful directional drift; this mirrors the old behaviour
        # (slope 10 on a ~10k-priced asset -> 0.1% per bar).
        normalized_slope = slope / mean_close
        threshold = 0.001

        if normalized_slope > threshold:
            return 'bullish'
        elif normalized_slope < -threshold:
            return 'bearish'
        return 'neutral'

    def _get_momentum(self, indicators: Dict) -> str:
        """Get momentum from MACD"""
        try:
            histogram = indicators.get('macd_histogram', pd.Series([0])).iloc[-1]
            if histogram > 0:
                return 'bullish'
            elif histogram < 0:
                return 'bearish'
            return 'neutral'
        except Exception:
            return 'neutral'

    def _get_volume_trend(self, df: pd.DataFrame) -> str:
        """Determine volume trend"""
        if len(df) < 20:
            return 'neutral'

        recent_volume = df['volume'].iloc[-10:].mean()
        older_volume = df['volume'].iloc[-20:-10].mean()

        if recent_volume > older_volume * 1.2:
            return 'increasing'
        elif recent_volume < older_volume * 0.8:
            return 'decreasing'
        return 'stable'

    def _get_rsi_position(self, indicators: Dict) -> str:
        """Get RSI position"""
        try:
            rsi = indicators.get('rsi_14', pd.Series([50])).iloc[-1]
            if rsi < 30:
                return 'oversold'
            elif rsi > 70:
                return 'overbought'
            elif rsi > 50:
                return 'bullish'
            elif rsi < 50:
                return 'bearish'
            return 'neutral'
        except Exception:
            return 'neutral'

    def _calculate_trend_score(
        self,
        ema_trend: str,
        price_trend: str,
        momentum: str,
        volume_trend: str,
        rsi_position: str
    ) -> float:
        """Calculate combined trend score"""

        score = 0.0

        # EMA trend (weight: 0.3)
        if ema_trend == 'bullish':
            score += 0.3
        elif ema_trend == 'bearish':
            score -= 0.3

        # Price trend (weight: 0.3)
        if price_trend == 'bullish':
            score += 0.3
        elif price_trend == 'bearish':
            score -= 0.3

        # Momentum (weight: 0.2)
        if momentum == 'bullish':
            score += 0.2
        elif momentum == 'bearish':
            score -= 0.2

        # Volume (weight: 0.1)
        if volume_trend == 'increasing':
            score += 0.1
        elif volume_trend == 'decreasing':
            score -= 0.1

        # RSI (weight: 0.1)
        if rsi_position == 'bullish':
            score += 0.1
        elif rsi_position == 'bearish':
            score -= 0.1
        elif rsi_position == 'oversold':
            score += 0.15  # Bonus for oversold
        elif rsi_position == 'overbought':
            score -= 0.15

        return score

    def _determine_overall_bias(
        self,
        tf_trends: Dict[str, Dict]
    ) -> Tuple[str, float]:
        """Determine overall bias with weighted voting"""

        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0

        for tf, trend_data in tf_trends.items():
            weight = self.TIMEFRAME_HIERARCHY.get(tf, 1)
            strength = trend_data.get('strength', 0)
            trend = trend_data.get('trend', 'neutral')

            weighted_strength = weight * strength
            total_weight += weight

            if trend == 'bullish':
                bullish_score += weighted_strength
            elif trend == 'bearish':
                bearish_score += weighted_strength

        if total_weight == 0:
            return 'neutral', 0.0

        # Normalize scores
        bullish_score /= total_weight
        bearish_score /= total_weight

        # Determine bias
        if bullish_score > bearish_score and bullish_score > 0.5:
            return 'bullish', bullish_score
        elif bearish_score > bullish_score and bearish_score > 0.5:
            return 'bearish', bearish_score
        else:
            return 'neutral', max(bullish_score, bearish_score)

    def _check_alignment(self, tf_trends: Dict[str, Dict]) -> str:
        """Check if timeframes are aligned"""

        trends = [data.get('trend', 'neutral') for data in tf_trends.values()]

        # Count trends
        bullish_count = trends.count('bullish')
        bearish_count = trends.count('bearish')
        total_count = len(trends)

        # Strong alignment: 80%+ same direction
        if bullish_count >= total_count * 0.8:
            return 'strongly_aligned_bullish'
        elif bearish_count >= total_count * 0.8:
            return 'strongly_aligned_bearish'
        elif bullish_count >= total_count * 0.6:
            return 'moderately_aligned_bullish'
        elif bearish_count >= total_count * 0.6:
            return 'moderately_aligned_bearish'
        else:
            return 'conflicting'

    def _evaluate_entry_timing(
        self,
        tf_trends: Dict[str, Dict],
        overall_bias: str
    ) -> str:
        """Evaluate entry timing quality"""

        if overall_bias == 'neutral':
            return 'poor'

        # Check if lower timeframes align with higher
        htf_bias = tf_trends.get('1d', {}).get('trend', 'neutral')
        mtf_bias = tf_trends.get('4h', {}).get('trend', 'neutral')
        ltf_bias = tf_trends.get('15m', {}).get('trend', 'neutral')

        # Excellent: HTF trend, MTF pullback, LTF reversal
        if htf_bias == overall_bias:
            if mtf_bias != overall_bias and ltf_bias == overall_bias:
                return 'excellent'  # Pullback completed
            elif mtf_bias == overall_bias and ltf_bias == overall_bias:
                return 'good'  # Strong alignment
            elif mtf_bias == overall_bias:
                return 'fair'

        return 'poor'

    def _generate_recommendation(
        self,
        bias: str,
        strength: float,
        alignment: str,
        timing: str
    ) -> str:
        """Generate trading recommendation"""

        if bias == 'neutral':
            return "No clear directional bias. Wait for better setup."

        direction = bias.upper()

        if 'strongly_aligned' in alignment and timing in ['excellent', 'good']:
            return f"STRONG {direction} SETUP - High confluence, enter on pullback"
        elif 'moderately_aligned' in alignment and timing == 'excellent':
            return f"GOOD {direction} SETUP - Wait for confirmation"
        elif strength > 0.7 and timing in ['good', 'fair']:
            return f"MODERATE {direction} SETUP - Use smaller position size"
        else:
            return f"WEAK {direction} SETUP - Wait for better timing"

    def _calculate_confluence_score(self, tf_trends: Dict[str, Dict]) -> float:
        """Calculate overall confluence score"""

        if not tf_trends:
            return 0.0

        # Average strength across timeframes (weighted)
        total_score = 0.0
        total_weight = 0.0

        for tf, data in tf_trends.items():
            weight = self.TIMEFRAME_HIERARCHY.get(tf, 1)
            strength = data.get('strength', 0)
            total_score += strength * weight
            total_weight += weight

        return total_score / total_weight if total_weight > 0 else 0.0

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result"""
        return {
            'overall_bias': 'unknown',
            'bias_strength': 0.0,
            'alignment': 'unknown',
            'timeframe_trends': {},
            'entry_timing': 'poor',
            'recommendation': 'Insufficient data for MTF analysis',
            'confluence_score': 0.0
        }