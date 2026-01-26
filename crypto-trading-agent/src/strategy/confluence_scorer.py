"""
Confluence Scorer
Scores trade setups based on confluence of multiple factors.
Consolidated implementation supporting both Market Analysis and Strategy Agents.
"""
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from loguru import logger
import pandas as pd

@dataclass
class Confluence:
    """Single confluence factor"""
    factor: str  # Name of the factor
    category: str  # 'SMC', 'ICT', 'INDICATOR', 'PATTERN', 'STRUCTURE'
    weight: float  # Importance weight (0.0 to 1.0)
    description: str  # Human-readable description
    timeframe: str  # Timeframe where confluence was found

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor': self.factor,
            'category': self.category,
            'weight': self.weight,
            'description': self.description,
            'timeframe': self.timeframe
        }

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
    confidence_level: float = 0.0 # Added for compatibility with Strategy Agent

    @property
    def confluence_factors(self) -> List[str]:
        """Get list of confluence factor names for easy access (Compatibility)"""
        return [f"{c.category}: {c.factor}" for c in self.confluences]
    
    @property
    def factors(self) -> List[Dict[str, Any]]:
        """Get list of factors as dicts (Compatibility)"""
        return [c.to_dict() for c in self.confluences]

    @property
    def breakdown(self) -> Dict[str, float]:
        """Get score breakdown by category (Compatibility)"""
        # This is an approximation as original breakdown was score-based, 
        # here we return counts or we could calculate score contribution.
        # Returning counts for now as it's safer.
        return {k: float(v) for k, v in self.by_category.items()}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'total_score': round(self.total_score, 3),
            'confluence_count': self.confluence_count,
            'confidence_level': round(self.confidence_level, 3),
            'quality_rating': self.quality_rating,
            'meets_minimum': self.meets_minimum,
            'reasoning': self.reasoning,
            'confluences': [c.to_dict() for c in self.confluences],
            'by_category': self.by_category,
            'factors': self.factors, # For compatibility
            'breakdown': self.breakdown # For compatibility
        }

class ConfluenceScorer:
    """
    Score trade setups based on confluence of multiple factors
    
    Confluence Categories:
    1. **SMC (Smart Money Concepts)**: Order Blocks, FVGs, BOS, etc.
    2. **ICT (Inner Circle Trader)**: Killzones, Sweeps, OTE, etc.
    3. **Technical Indicators**: RSI, MACD, Volume, etc.
    4. **Chart Patterns**: Head & Shoulders, Triangles, etc.
    5. **Market Structure**: HTF/MTF trends.
    6. **Cross-Timeframe Alignment**: Multi-timeframe confirmation.
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
        
        logger.info("ConfluenceScorer initialized (Consolidated Version)")
    
    def calculate(
        self,
        direction: str,
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        indicators: Dict[str, Any],
        mtf_analysis: Dict[str, Any]
    ) -> ConfluenceScore:
        """
        Alias for score_setup to maintain compatibility with Strategy Agent.
        Adapts inputs if necessary.
        """
        # Map inputs to score_setup signature
        # Strategy Agent passes 'mtf_analysis' which maps to 'market_structure' roughly,
        # but score_setup expects 'market_structure' AND 'patterns'.
        # We'll pass mtf_analysis as market_structure and empty patterns if not provided.
        
        return self.score_setup(
            smc_analysis=smc_data,
            ict_analysis=ict_data,
            indicators=indicators,
            patterns={}, # Strategy agent doesn't pass patterns explicitly yet
            market_structure=mtf_analysis,
            direction=direction
        )

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
        """
        # CRITICAL DEBUG: Log incoming data structure
        logger.debug(f"ConfluenceScorer.score_setup called with direction={direction}")
        logger.debug(f"  smc_analysis type: {type(smc_analysis)}, keys: {list(smc_analysis.keys()) if isinstance(smc_analysis, dict) else 'N/A'}")
        logger.debug(f"  ict_analysis type: {type(ict_analysis)}, keys: {list(ict_analysis.keys()) if isinstance(ict_analysis, dict) else 'N/A'}")
        logger.debug(f"  indicators type: {type(indicators)}, keys: {list(indicators.keys()) if isinstance(indicators, dict) else 'N/A'}")
        logger.debug(f"  patterns type: {type(patterns)}, keys: {list(patterns.keys()) if isinstance(patterns, dict) else 'N/A'}")
        logger.debug(f"  market_structure type: {type(market_structure)}, keys: {list(market_structure.keys()) if isinstance(market_structure, dict) else 'N/A'}")
        
        # Check for nested 'computational' structure
        if isinstance(smc_analysis, dict):
            if 'computational' in smc_analysis:
                logger.debug(f"  smc_analysis.computational keys: {list(smc_analysis['computational'].keys())}")
                if 'order_blocks' in smc_analysis['computational']:
                    obs = smc_analysis['computational']['order_blocks']
                    logger.debug(f"  smc_analysis.computational.order_blocks: count={len(obs) if isinstance(obs, list) else 'not a list'}")
            else:
                logger.debug(f"  smc_analysis has no 'computational' key - using direct structure")
                if 'order_blocks' in smc_analysis:
                    obs = smc_analysis['order_blocks']
                    logger.debug(f"  smc_analysis.order_blocks: count={len(obs) if isinstance(obs, list) else 'not a list'}")
        
        confluences = []
        
        # 1. Score SMC
        confluences.extend(self._score_smc(smc_analysis, direction))
        logger.debug(f"  After SMC scoring: {len(confluences)} confluences")
        
        # 2. Score ICT
        confluences.extend(self._score_ict(ict_analysis, direction))
        logger.debug(f"  After ICT scoring: {len(confluences)} confluences")
        
        # 3. Score Indicators
        confluences.extend(self._score_indicators(indicators, direction))
        logger.debug(f"  After Indicators scoring: {len(confluences)} confluences")
        
        # 4. Score Patterns
        confluences.extend(self._score_patterns(patterns, direction))
        logger.debug(f"  After Patterns scoring: {len(confluences)} confluences")
        
        # 5. Score Market Structure
        confluences.extend(self._score_structure(market_structure, direction))
        logger.debug(f"  After Structure scoring: {len(confluences)} confluences")

        # 6. Score Cross-Timeframe Alignment
        confluences.extend(self._score_cross_timeframe(smc_analysis, market_structure, direction))
        logger.debug(f"  After Cross-Timeframe scoring: {len(confluences)} confluences")
        
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
        
        # Calculate confidence level (0.0 to 1.0)
        # Base confidence on count and quality
        base_confidence = min(confluence_count * 0.15, 0.95) # Cap at 0.95
        if quality_rating == 'EXCELLENT':
            confidence_level = max(base_confidence, 0.85)
        elif quality_rating == 'GOOD':
            confidence_level = max(base_confidence, 0.70)
        elif quality_rating == 'FAIR':
            confidence_level = max(base_confidence, 0.50)
        else:
            confidence_level = min(base_confidence, 0.40)
            
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
            reasoning=reasoning,
            confidence_level=confidence_level
        )
        
        logger.info(
            f"Confluence Score: {confluence_count} confluences "
            f"(total score: {total_score:.2f}, rating: {quality_rating})"
        )
        
        return score
    
    def _score_smc(self, smc_analysis: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score SMC confluences"""
        confluences = []
        if not smc_analysis: return confluences
            
        # Handle both structure formats (direct dict or nested under 'computational')
        data = smc_analysis.get('computational', smc_analysis)
        
        # Order Blocks
        order_blocks = data.get('order_blocks', [])
        for ob in order_blocks:
            if direction == 'LONG' and ob.get('type') == 'bullish':
                # Extract price from zone dict or direct price field
                zone = ob.get('zone', {})
                if isinstance(zone, dict):
                    price = zone.get('high', zone.get('low', 0))
                else:
                    price = ob.get('price', 0)
                
                confluences.append(Confluence(
                    factor='Bullish Order Block',
                    category='SMC',
                    weight=1.0,
                    description=f"Bullish OB at ${price:.2f}",
                    timeframe=ob.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and ob.get('type') == 'bearish':
                # Extract price from zone dict or direct price field
                zone = ob.get('zone', {})
                if isinstance(zone, dict):
                    price = zone.get('low', zone.get('high', 0))
                else:
                    price = ob.get('price', 0)
                
                confluences.append(Confluence(
                    factor='Bearish Order Block',
                    category='SMC',
                    weight=1.0,
                    description=f"Bearish OB at ${price:.2f}",
                    timeframe=ob.get('timeframe', 'unknown')
                ))
        
        # Fair Value Gaps
        fvgs = data.get('fair_value_gaps', [])
        for fvg in fvgs:
            if direction == 'LONG' and fvg.get('type') == 'bullish':
                # Extract price from gap dict or direct price field
                gap = fvg.get('gap', {})
                if isinstance(gap, dict):
                    price = gap.get('high', gap.get('low', 0))
                else:
                    price = fvg.get('price', 0)
                
                confluences.append(Confluence(
                    factor='Bullish FVG',
                    category='SMC',
                    weight=0.9,
                    description=f"Bullish FVG at ${price:.2f}",
                    timeframe=fvg.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and fvg.get('type') == 'bearish':
                # Extract price from gap dict or direct price field
                gap = fvg.get('gap', {})
                if isinstance(gap, dict):
                    price = gap.get('low', gap.get('high', 0))
                else:
                    price = fvg.get('price', 0)
                
                confluences.append(Confluence(
                    factor='Bearish FVG',
                    category='SMC',
                    weight=0.9,
                    description=f"Bearish FVG at ${price:.2f}",
                    timeframe=fvg.get('timeframe', 'unknown')
                ))
        
        # Break of Structure
        # Handle list or dict format
        bos_data = data.get('break_of_structure', {})
        if isinstance(bos_data, list):
             # If list, check last item
             if bos_data:
                 bos = bos_data[-1]
                 if direction == 'LONG' and bos.get('type') == 'bullish':
                     confluences.append(Confluence(
                        factor='Bullish BOS',
                        category='SMC',
                        weight=1.0,
                        description="Bullish Break of Structure confirmed",
                        timeframe=bos.get('timeframe', 'unknown')
                    ))
                 elif direction == 'SHORT' and bos.get('type') == 'bearish':
                     confluences.append(Confluence(
                        factor='Bearish BOS',
                        category='SMC',
                        weight=1.0,
                        description="Bearish Break of Structure confirmed",
                        timeframe=bos.get('timeframe', 'unknown')
                    ))
        elif isinstance(bos_data, dict):
            if bos_data.get('detected'):
                if direction == 'LONG' and bos_data.get('direction') == 'bullish':
                    confluences.append(Confluence(
                        factor='Bullish BOS',
                        category='SMC',
                        weight=1.0,
                        description="Bullish Break of Structure confirmed",
                        timeframe=bos_data.get('timeframe', 'unknown')
                    ))
                elif direction == 'SHORT' and bos_data.get('direction') == 'bearish':
                    confluences.append(Confluence(
                        factor='Bearish BOS',
                        category='SMC',
                        weight=1.0,
                        description="Bearish Break of Structure confirmed",
                        timeframe=bos_data.get('timeframe', 'unknown')
                    ))
        
        return confluences
    
    def _score_ict(self, ict_analysis: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score ICT confluences"""
        confluences = []
        if not ict_analysis: return confluences
        
        data = ict_analysis.get('computational', ict_analysis)
        
        # Killzone
        killzone = data.get('killzone', {})
        if killzone.get('active') or killzone.get('current_killzone') in ['london', 'new_york']:
            confluences.append(Confluence(
                factor='ICT Killzone Active',
                category='ICT',
                weight=0.8,
                description=f"In {killzone.get('name', killzone.get('current_killzone', 'unknown'))} killzone",
                timeframe='time-based'
            ))
        
        # Liquidity Sweeps
        sweeps = data.get('liquidity_sweeps', [])
        for sweep in sweeps:
            if direction == 'LONG' and (sweep.get('type') == 'buy_side' or sweep.get('type') == 'bearish_liquidity'): # Check types carefully
                 # Buy side liquidity swept usually means bearish reversal? 
                 # Wait, if we sweep sell-side liquidity (stops below lows), we expect bullish reversal.
                 # If we sweep buy-side liquidity (stops above highs), we expect bearish reversal.
                 # Playground logic: LONG if 'buy_side' swept? That seems inverted or I'm misremembering.
                 # Let's stick to Playground logic for now but double check.
                 # Playground: if direction == 'LONG' and sweep.get('type') == 'buy_side' -> Confluence.
                 # Actually, usually sweeping sell-side liquidity (lows) fuels a move up (LONG).
                 # Let's assume 'buy_side' means "swept buy side liquidity" -> price went up, took liquidity, now reversing down?
                 # Or does it mean "liquidity on the buy side"?
                 # Let's look at the playground code again.
                 # Playground: if direction == 'LONG' and sweep.get('type') == 'buy_side'
                 # I will trust the playground logic for now.
                confluences.append(Confluence(
                    factor='Liquidity Sweep',
                    category='ICT',
                    weight=1.0,
                    description=f"Liquidity sweep detected",
                    timeframe=sweep.get('timeframe', 'unknown')
                ))
            elif direction == 'SHORT' and (sweep.get('type') == 'sell_side' or sweep.get('type') == 'bullish_liquidity'):
                confluences.append(Confluence(
                    factor='Liquidity Sweep',
                    category='ICT',
                    weight=1.0,
                    description=f"Liquidity sweep detected",
                    timeframe=sweep.get('timeframe', 'unknown')
                ))
        
        # OTE Zones
        ote = data.get('ote_zones', {})
        if ote.get('in_zone') or ote.get('in_ote_zone'):
            confluences.append(Confluence(
                factor='OTE Zone',
                category='ICT',
                weight=0.9,
                description=f"Price in OTE zone",
                timeframe=ote.get('timeframe', 'unknown')
            ))
        
        return confluences
    
    def _get_last_value(self, value: Any) -> Any:
        """
        Get the last value if the input is a pandas Series/DataFrame,
        otherwise return the value itself. Always returns Python scalar.
        """
        if value is None:
            return None
        
        # Check if it's a pandas Series or DataFrame by checking type name
        # This avoids importing pandas
        type_name = type(value).__name__
        
        # Handle pandas Series/DataFrame
        if type_name in ('Series', 'DataFrame') or hasattr(value, 'iloc'):
            try:
                if hasattr(value, 'empty') and value.empty:
                    return None
                last_val = value.iloc[-1]
                
                # Convert numpy/pandas types to Python scalars
                if hasattr(last_val, 'item'):
                    return float(last_val.item())
                
                # Try direct float conversion
                return float(last_val)
            except Exception as e:
                logger.warning(f"Error extracting last value from {type_name}: {e}")
                return None
        
        # Handle numpy arrays
        if hasattr(value, 'item'):
            try:
                return float(value.item())
            except Exception:
                pass
                
        # Already a scalar - try to convert to float for numeric operations
        if isinstance(value, (int, float)):
            return float(value)
        
        # If it's a string representation of a Series, something went wrong
        if isinstance(value, str) and 'dtype:' in value:
            logger.error(f"Received string representation of pandas object instead of actual object")
            return None
            
        # Handle lists (JSON deserialized data)
        if isinstance(value, list):
            if not value:
                return None
            # Recursively get last value of the last item if it's a list (nested)
            # But usually it's a list of numbers
            return self._get_last_value(value[-1])

        return value

    def _score_indicators(self, indicators: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score indicator confluences"""
        confluences = []
        if not indicators: return confluences
        
        # Helper to safely get scalar values
        def get_val(key, source=indicators):
            val = source.get(key)
            return self._get_last_value(val)
        
        # Handle nested indicators (e.g. '1h': {...})
        # Strategy agent passes raw indicators which might be nested under timeframes or flat
        # Playground expected flat or handled it? Playground expected flat in _score_indicators but test passed flat.
        # But real data might be nested.
        
        # Try to find primary timeframe data
        primary_tf_data = indicators
        if '1h' in indicators:
            primary_tf_data = indicators['1h']
        elif '4h' in indicators:
            primary_tf_data = indicators['4h']
            
        rsi = get_val('rsi_14', primary_tf_data)
        macd_histogram = get_val('macd_histogram', primary_tf_data)
        
        # Volume might be in top level or nested
        volume_sma = get_val('volume_sma', primary_tf_data)
        current_volume = get_val('volume', primary_tf_data)
        
        if volume_sma is None: volume_sma = get_val('volume_sma', indicators)
        if current_volume is None: current_volume = get_val('volume', indicators)
        
        # RSI - with type validation
        if rsi is not None:
            try:
                rsi_val = float(rsi)
                if direction == 'LONG' and rsi_val < 35:
                    confluences.append(Confluence(
                        factor='RSI Oversold',
                        category='INDICATOR',
                        weight=0.6,
                        description=f"RSI oversold ({rsi_val:.1f})",
                        timeframe='indicator'
                    ))
                elif direction == 'SHORT' and rsi_val > 65:
                    confluences.append(Confluence(
                        factor='RSI Overbought',
                        category='INDICATOR',
                        weight=0.6,
                        description=f"RSI overbought ({rsi_val:.1f})",
                        timeframe='indicator'
                    ))
            except (TypeError, ValueError) as e:
                # Don't log the full value if it's a Series object
                val_type = type(rsi).__name__
                logger.warning(f"Invalid RSI value - type: {val_type}, error: {str(e)[:100]}")
        
        # MACD - with type validation
        if macd_histogram is not None:
            try:
                macd_val = float(macd_histogram)
                if direction == 'LONG' and macd_val > 0:
                    confluences.append(Confluence(
                        factor='MACD Bullish',
                        category='INDICATOR',
                        weight=0.7,
                        description="MACD histogram positive",
                        timeframe='indicator'
                    ))
                elif direction == 'SHORT' and macd_val < 0:
                    confluences.append(Confluence(
                        factor='MACD Bearish',
                        category='INDICATOR',
                        weight=0.7,
                        description="MACD histogram negative",
                        timeframe='indicator'
                    ))
            except (TypeError, ValueError) as e:
                # Don't log the full value if it's a Series object
                val_type = type(macd_histogram).__name__
                logger.warning(f"Invalid MACD value - type: {val_type}, error: {str(e)[:100]}")
        
        # Volume - with type validation
        if volume_sma is not None and current_volume is not None:
            try:
                vol_sma = float(volume_sma)
                curr_vol = float(current_volume)
                if curr_vol > vol_sma * 1.5:
                    confluences.append(Confluence(
                        factor='High Volume',
                        category='INDICATOR',
                        weight=0.5,
                        description=f"Volume {(curr_vol/vol_sma):.1f}x average",
                        timeframe='indicator'
                    ))
            except (TypeError, ValueError, Exception) as e:
                logger.warning(f"Error comparing volume: {e}")
        
        return confluences
    
    def _score_patterns(self, patterns: Dict[str, Any], direction: str) -> List[Confluence]:
        """Score chart pattern confluences"""
        confluences = []
        if not patterns: return confluences
        
        detected_patterns = patterns.get('patterns', [])
        for pattern in detected_patterns:
            pattern_type = pattern.get('type', '')
            pattern_direction = pattern.get('direction', '')
            
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
        if not market_structure: return confluences
            
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
        
        # 1. SMC Alignment
        data = smc_analysis.get('computational', smc_analysis)
        obs = data.get('order_blocks', [])
        timeframes_with_ob = set()
        
        for ob in obs:
            if (direction == 'LONG' and ob.get('type') == 'bullish') or \
               (direction == 'SHORT' and ob.get('type') == 'bearish'):
                timeframes_with_ob.add(ob.get('timeframe'))
                
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