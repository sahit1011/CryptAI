"""
Confluence Scorer
Scores trade setups based on confluence of multiple factors
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class Confluence:
    """Single confluence factor"""
    factor: str  # Name of the factor
    category: str  # 'SMC', 'ICT', 'INDICATOR', 'PATTERN', 'STRUCTURE'
    weight: float  # Importance weight (0.0 to 1.0)
    description: str  # Human-readable description
    timeframe: str  # Timeframe where confluence was found


@dataclass
class ConfluenceScore:
    """Complete confluence scoring result"""
    total_score: float  # Weighted total score
    confluence_count: int  # Number of confluences
    confluences: List[Confluence]  # List of all confluences
    by_category: Dict[str, int]  # Count by category
    quality_rating: str  # 'EXCELLENT', 'GOOD', 'FAIR', 'POOR'
    meets_minimum: bool  # Meets minimum confluence requirement
    reasoning: str  # Explanation of the score


class ConfluenceScorer:
    """
    Score trade setups based on confluence of multiple factors
    
    Confluence Categories:
    1. **SMC (Smart Money Concepts)**:
       - Order Blocks (bullish/bearish)
       - Fair Value Gaps (FVG)
       - Break of Structure (BOS)
       - Change of Character (CHoCH)
       - Liquidity Pools
    
    2. **ICT (Inner Circle Trader)**:
       - Killzone timing
       - Liquidity sweeps
       - Order flow (AMD model)
       - Optimal Trade Entry (OTE) zones
    
    3. **Technical Indicators**:
       - RSI divergence
       - MACD crossover
       - Bollinger Band squeeze
       - Volume confirmation
       - EMA alignment
    
    4. **Chart Patterns**:
       - Head & Shoulders
       - Double Top/Bottom
       - Triangles
       - Flags/Pennants
    
    5. **Market Structure**:
       - HTF trend alignment
       - MTF support/resistance
       - LTF entry trigger

    6. **Cross-Timeframe Alignment**:
       - HTF + MTF OB alignment
       - HTF + MTF FVG alignment
       - Full Trend Alignment (HTF + MTF + LTF)
    
    Minimum Requirements:
    - Trending markets: 3 confluences
    - Ranging markets: 4 confluences
    - Volatile markets: 5 confluences
    """
    
    def __init__(self):
        """Initialize confluence scorer"""
        # Define category weights
        self.category_weights = {
            'SMC': 1.0,        # Smart Money Concepts - highest weight
            'ICT': 1.0,        # ICT methodology - highest weight
            'STRUCTURE': 0.9,  # Market structure - very important
            'ALIGNMENT': 1.1,  # Cross-timeframe alignment - CRITICAL
            'INDICATOR': 0.7,  # Technical indicators - supporting
            'PATTERN': 0.8     # Chart patterns - important
        }
        
        logger.info("ConfluenceScorer initialized")
    
    def score_setup(
        self,
        smc_analysis: Dict[str, Any],
        ict_analysis: Dict[str, Any],
        indicators: Dict[str, Any],
        patterns: Dict[str, Any],
        market_structure: Dict[str, Any],
        direction: str,
        minimum_required: int = 3
    ) -> ConfluenceScore:
        """
        Calculate total confluence score
        
        Args:
            smc_analysis: Results from SMC detector
            ict_analysis: Results from ICT detector
            indicators: Technical indicators
            patterns: Chart patterns
            market_structure: Market structure analysis
            direction: 'LONG' or 'SHORT'
            minimum_required: Minimum confluences needed
            
        Returns:
            ConfluenceScore object
        """
        confluences = []
        
        # 1. Score SMC
        confluences.extend(self._score_smc(smc_analysis, direction))
        
        # 2. Score ICT
        confluences.extend(self._score_ict(ict_analysis, direction))
        
        # 3. Score Indicators
        confluences.extend(self._score_indicators(indicators, direction))
        
        # 4. Score Patterns
        confluences.extend(self._score_patterns(patterns, direction))
        
        # 5. Score Market Structure
        confluences.extend(self._score_structure(market_structure, direction))

        # 6. Score Cross-Timeframe Alignment (NEW)
        confluences.extend(self._score_cross_timeframe(smc_analysis, market_structure, direction))
        
        # Calculate total score
        total_score = sum(c.weight for c in confluences)
        confluence_count = len(confluences)
        
        # Count by category
        by_category = {}
        for c in confluences:
            by_category[c.category] = by_category.get(c.category, 0) + 1
        
        # Determine quality rating
        if confluence_count >= 6:
            quality_rating = 'EXCELLENT'
        elif confluence_count >= 4:
            quality_rating = 'GOOD'
        elif confluence_count >= 3:
            quality_rating = 'FAIR'
        else:
            quality_rating = 'POOR'
        
        # Check if meets minimum
        meets_minimum = confluence_count >= minimum_required
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            confluences, confluence_count, minimum_required, quality_rating
        )
        
        score = ConfluenceScore(
            total_score=total_score,
            confluence_count=confluence_count,
            confluences=confluences,
            by_category=by_category,
            quality_rating=quality_rating,
            meets_minimum=meets_minimum,
            reasoning=reasoning
        )
        
        logger.info(
            f"Confluence Score: {confluence_count} confluences "
            f"(total score: {total_score:.2f}, rating: {quality_rating})"
        )
        
        return score
    
    def _score_smc(self, smc_analysis: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score SMC confluences"""
        confluences = []
        
        if not smc_analysis:
            return confluences
            
        logger.debug(f"Scoring SMC: {len(smc_analysis.get('order_blocks', []))} OBs, {len(smc_analysis.get('fair_value_gaps', []))} FVGs")
        
        # Order Blocks
        order_blocks = smc_analysis.get('order_blocks', [])
        for ob in order_blocks:
            if direction == 'LONG' and ob.get('type') == 'bullish':
                confluences.append(Confluence(
                    factor='Bullish Order Block',
                    category='SMC',
                    weight=1.0,
                    description=f"Bullish OB at ${ob.get('price', 0):.2f}",
                    timeframe=ob.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and ob.get('type') == 'bearish':
                confluences.append(Confluence(
                    factor='Bearish Order Block',
                    category='SMC',
                    weight=1.0,
                    description=f"Bearish OB at ${ob.get('price', 0):.2f}",
                    timeframe=ob.get('timeframe', 'unknown')
                ))
        
        # Fair Value Gaps
        fvgs = smc_analysis.get('fair_value_gaps', [])
        for fvg in fvgs:
            if direction == 'LONG' and fvg.get('type') == 'bullish':
                confluences.append(Confluence(
                    factor='Bullish FVG',
                    category='SMC',
                    weight=0.9,
                    description=f"Bullish FVG at ${fvg.get('price', 0):.2f}",
                    timeframe=fvg.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and fvg.get('type') == 'bearish':
                confluences.append(Confluence(
                    factor='Bearish FVG',
                    category='SMC',
                    weight=0.9,
                    description=f"Bearish FVG at ${fvg.get('price', 0):.2f}",
                    timeframe=fvg.get('timeframe', 'unknown')
                ))
        
        # Break of Structure
        bos = smc_analysis.get('break_of_structure', {})
        if bos.get('detected'):
            if direction == 'LONG' and bos.get('direction') == 'bullish':
                confluences.append(Confluence(
                    factor='Bullish BOS',
                    category='SMC',
                    weight=1.0,
                    description="Bullish Break of Structure confirmed",
                    timeframe=bos.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and bos.get('direction') == 'bearish':
                confluences.append(Confluence(
                    factor='Bearish BOS',
                    category='SMC',
                    weight=1.0,
                    description="Bearish Break of Structure confirmed",
                    timeframe=bos.get('timeframe', 'unknown')
                ))
        
        return confluences
    
    def _score_ict(self, ict_analysis: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score ICT confluences"""
        confluences = []
        
        if not ict_analysis:
            return confluences
        
        # Killzone
        killzone = ict_analysis.get('killzone', {})
        if killzone.get('active'):
            confluences.append(Confluence(
                factor='ICT Killzone Active',
                category='ICT',
                weight=0.8,
                description=f"In {killzone.get('name', 'unknown')} killzone",
                timeframe='time-based'
            ))
        
        # Liquidity Sweeps
        sweeps = ict_analysis.get('liquidity_sweeps', [])
        for sweep in sweeps:
            if direction == 'LONG' and sweep.get('type') == 'buy_side':
                confluences.append(Confluence(
                    factor='Liquidity Sweep (Buy Side)',
                    category='ICT',
                    weight=1.0,
                    description=f"Buy-side liquidity swept at ${sweep.get('price', 0):.2f}",
                    timeframe=sweep.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and sweep.get('type') == 'sell_side':
                confluences.append(Confluence(
                    factor='Liquidity Sweep (Sell Side)',
                    category='ICT',
                    weight=1.0,
                    description=f"Sell-side liquidity swept at ${sweep.get('price', 0):.2f}",
                    timeframe=sweep.get('timeframe', 'unknown')
                ))
        
        # OTE Zones
        ote = ict_analysis.get('ote_zones', {})
        if ote.get('in_zone'):
            confluences.append(Confluence(
                factor='OTE Zone',
                category='ICT',
                weight=0.9,
                description=f"Price in OTE zone (0.62-0.79 retracement)",
                timeframe=ote.get('timeframe', 'unknown')
            ))
        
        return confluences
    
    def _get_last_value(self, value: Any) -> Any:
        """
        Get the last value if the input is a pandas Series/DataFrame,
        otherwise return the value itself.
        """
        if hasattr(value, 'iloc'):
            try:
                return value.iloc[-1]
            except Exception:
                return value
        return value

    def _score_indicators(self, indicators: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score indicator confluences"""
        confluences = []
        
        if not indicators:
            return confluences
        
        # Helper to safely get scalar values
        def get_val(key):
            val = indicators.get(key)
            return self._get_last_value(val)
        
        rsi = get_val('rsi_14')
        macd_histogram = get_val('macd_histogram')
        volume_sma = get_val('volume_sma')
        current_volume = get_val('volume')
        
        logger.debug(f"Scoring Indicators: RSI={rsi}, MACD_Hist={macd_histogram}, Vol={current_volume}, Vol_SMA={volume_sma}")
        
        # RSI
        if rsi is not None:
            if direction == 'LONG' and rsi < 35:
                confluences.append(Confluence(
                    factor='RSI Oversold',
                    category='INDICATOR',
                    weight=0.6,
                    description=f"RSI oversold ({rsi:.1f})",
                    timeframe='indicator'
                ))
            elif direction == 'SHORT' and rsi > 65:
                confluences.append(Confluence(
                    factor='RSI Overbought',
                    category='INDICATOR',
                    weight=0.6,
                    description=f"RSI overbought ({rsi:.1f})",
                    timeframe='indicator'
                ))
        
        # MACD
        if macd_histogram is not None:
            if direction == 'LONG' and macd_histogram > 0:
                confluences.append(Confluence(
                    factor='MACD Bullish',
                    category='INDICATOR',
                    weight=0.7,
                    description="MACD histogram positive",
                    timeframe='indicator'
                ))
            elif direction == 'SHORT' and macd_histogram < 0:
                confluences.append(Confluence(
                    factor='MACD Bearish',
                    category='INDICATOR',
                    weight=0.7,
                    description="MACD histogram negative",
                    timeframe='indicator'
                ))
        
        # Volume
        if volume_sma is not None and current_volume is not None:
            # Ensure we're comparing scalars
            try:
                if current_volume > volume_sma * 1.5:
                    confluences.append(Confluence(
                        factor='High Volume',
                        category='INDICATOR',
                        weight=0.5,
                        description=f"Volume {(current_volume/volume_sma):.1f}x average",
                        timeframe='indicator'
                    ))
            except Exception as e:
                logger.warning(f"Error comparing volume: {e}")
        
        return confluences
    
    def _score_patterns(self, patterns: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score chart pattern confluences"""
        confluences = []
        
        if not patterns:
            return confluences
        
        detected_patterns = patterns.get('patterns', [])
        for pattern in detected_patterns:
            pattern_type = pattern.get('type', '')
            pattern_direction = pattern.get('direction', '')
            
            # Match pattern direction with trade direction
            if direction == 'LONG' and pattern_direction == 'bullish':
                confluences.append(Confluence(
                    factor=f'Bullish {pattern_type}',
                    category='PATTERN',
                    weight=0.8,
                    description=f"Bullish {pattern_type} pattern detected",
                    timeframe=pattern.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and pattern_direction == 'bearish':
                confluences.append(Confluence(
                    factor=f'Bearish {pattern_type}',
                    category='PATTERN',
                    weight=0.8,
                    description=f"Bearish {pattern_type} pattern detected",
                    timeframe=pattern.get('timeframe', 'unknown')
                ))
        
        return confluences
    
    def _score_structure(self, market_structure: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score market structure confluences"""
        confluences = []
        
        if not market_structure:
            return confluences
            
        logger.debug(f"Scoring Structure: HTF={market_structure.get('htf_trend')}, MTF={market_structure.get('mtf_trend')}")
        
        # HTF trend
        htf_trend = market_structure.get('htf_trend', '').lower()
        if direction == 'LONG' and htf_trend == 'bullish':
            confluences.append(Confluence(
                factor='HTF Bullish Trend',
                category='STRUCTURE',
                weight=1.0,
                description="Higher timeframe in bullish trend",
                timeframe='HTF'
            ))
        elif direction == 'SHORT' and htf_trend == 'bearish':
            confluences.append(Confluence(
                factor='HTF Bearish Trend',
                category='STRUCTURE',
                weight=1.0,
                description="Higher timeframe in bearish trend",
                timeframe='HTF'
            ))
        
        # MTF alignment
        mtf_trend = market_structure.get('mtf_trend', '').lower()
        if direction == 'LONG' and mtf_trend == 'bullish':
            confluences.append(Confluence(
                factor='MTF Bullish Alignment',
                category='STRUCTURE',
                weight=0.9,
                description="Medium timeframe aligned bullish",
                timeframe='MTF'
            ))
        elif direction == 'SHORT' and mtf_trend == 'bearish':
            confluences.append(Confluence(
                factor='MTF Bearish Alignment',
                category='STRUCTURE',
                weight=0.9,
                description="Medium timeframe aligned bearish",
                timeframe='MTF'
            ))
        
        return confluences

    def _score_cross_timeframe(
        self, 
        smc_analysis: Dict[str, Any], 
        market_structure: Dict[str, Any],
        direction: str
    ) -> List[Confluence]:
        """Score cross-timeframe alignment"""
        confluences = []
        
        # 1. SMC Alignment (e.g. 4H OB + 15M OB)
        obs = smc_analysis.get('order_blocks', [])
        timeframes_with_ob = set()
        
        for ob in obs:
            # Check if OB matches direction
            if (direction == 'LONG' and ob.get('type') == 'bullish') or \
               (direction == 'SHORT' and ob.get('type') == 'bearish'):
                timeframes_with_ob.add(ob.get('timeframe'))
                
        # If we have OBs on multiple distinct timeframes (e.g. 4h and 15m)
        if len(timeframes_with_ob) >= 2:
            confluences.append(Confluence(
                factor='Multi-Timeframe OB Alignment',
                category='ALIGNMENT',
                weight=1.2,
                description=f"Order Blocks aligned on {', '.join(timeframes_with_ob)}",
                timeframe='Multi'
            ))

        # 2. Trend Alignment (HTF + MTF)
        htf = market_structure.get('htf_trend', '').lower()
        mtf = market_structure.get('mtf_trend', '').lower()
        
        if direction == 'LONG' and htf == 'bullish' and mtf == 'bullish':
            confluences.append(Confluence(
                factor='Full Trend Alignment',
                category='ALIGNMENT',
                weight=1.5,
                description="HTF and MTF trends are both Bullish",
                timeframe='Multi'
            ))
        elif direction == 'SHORT' and htf == 'bearish' and mtf == 'bearish':
            confluences.append(Confluence(
                factor='Full Trend Alignment',
                category='ALIGNMENT',
                weight=1.5,
                description="HTF and MTF trends are both Bearish",
                timeframe='Multi'
            ))
            
        return confluences
    
    def _generate_reasoning(
        self,
        confluences: List[Confluence],
        count: int,
        minimum: int,
        quality: str
    ) -> str:
        """Generate human-readable reasoning"""
        
        if count == 0:
            return "No confluences detected - setup does not meet minimum requirements"
        
        # Group by category
        by_category = {}
        for c in confluences:
            if c.category not in by_category:
                by_category[c.category] = []
            by_category[c.category].append(c.factor)
        
        # Build reasoning
        parts = []
        parts.append(f"Found {count} confluences ({quality} quality)")
        
        if count >= minimum:
            parts.append(f"✓ Meets minimum requirement ({minimum})")
        else:
            parts.append(f"✗ Below minimum requirement ({minimum})")
        
        parts.append("\nConfluences by category:")
        for category, factors in by_category.items():
            parts.append(f"  {category}: {', '.join(factors)}")
        
        return "\n".join(parts)


def test_confluence_scorer():
    """Test the confluence scorer"""
    
    # Mock data
    smc_analysis = {
        'order_blocks': [
            {'type': 'bullish', 'price': 43000, 'timeframe': '4h'}
        ],
        'fair_value_gaps': [
            {'type': 'bullish', 'price': 42800, 'timeframe': '1h'}
        ],
        'break_of_structure': {
            'detected': True,
            'direction': 'bullish',
            'timeframe': '1h'
        }
    }
    
    ict_analysis = {
        'killzone': {'active': True, 'name': 'London Open'},
        'liquidity_sweeps': [
            {'type': 'buy_side', 'price': 42500, 'timeframe': '15m'}
        ],
        'ote_zones': {'in_zone': True, 'timeframe': '1h'}
    }
    
    indicators = {
        'rsi_14': 32.5,
        'macd_histogram': 15.2,
        'volume': 50000,
        'volume_sma': 30000
    }
    
    patterns = {
        'patterns': [
            {'type': 'Double Bottom', 'direction': 'bullish', 'timeframe': '4h'}
        ]
    }
    
    market_structure = {
        'htf_trend': 'bullish',
        'mtf_trend': 'bullish'
    }
    
    scorer = ConfluenceScorer()
    
    logger.info("=== Testing Confluence Scorer ===")
    score = scorer.score_setup(
        smc_analysis=smc_analysis,
        ict_analysis=ict_analysis,
        indicators=indicators,
        patterns=patterns,
        market_structure=market_structure,
        direction='LONG',
        minimum_required=3
    )
    
    logger.info(f"\nTotal Score: {score.total_score:.2f}")
    logger.info(f"Confluence Count: {score.confluence_count}")
    logger.info(f"Quality Rating: {score.quality_rating}")
    logger.info(f"Meets Minimum: {score.meets_minimum}")
    logger.info(f"\nBy Category: {score.by_category}")
    logger.info(f"\nReasoning:\n{score.reasoning}")
    
    logger.info("\n=== Individual Confluences ===")
    for conf in score.confluences:
        logger.info(f"{conf.category} | {conf.factor} (weight: {conf.weight}) - {conf.description}")


if __name__ == "__main__":
    test_confluence_scorer()
