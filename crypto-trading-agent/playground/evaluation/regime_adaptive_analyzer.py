"""
Regime-Adaptive Market Analysis Agent
Improved analysis agent with regime detection and adaptive strategy
"""
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger
import pandas as pd

from playground.evaluation.regime_detector import RegimeDetector, MarketRegime
from playground.evaluation.adaptive_timeframe_selector import AdaptiveTimeframeSelector, TimeframeStrategy
from playground.evaluation.quant_trader_psychology import QuantTraderPsychology, TraderDecision
from playground.evaluation.confluence_scorer import ConfluenceScorer, ConfluenceScore


class RegimeAdaptiveAnalyzer:
    """
    Regime-Adaptive Market Analysis
    
    Professional Quant Trader Workflow:
    1. **Regime Detection**: Classify market (trending/ranging/volatile)
    2. **Timeframe Selection**: Choose optimal TFs based on regime
    3. **Top-Down Analysis**: HTF bias → MTF setup → LTF entry
    4. **Confluence Scoring**: Score setup quality (SMC + ICT + indicators)
    5. **Risk Assessment**: Calculate position size and stops
    6. **Decision Making**: Trade/wait based on professional criteria
    
    This is the "brain" that coordinates all analysis modules.
    """
    
    def __init__(self):
        """Initialize regime-adaptive analyzer"""
        self.regime_detector = RegimeDetector()
        self.timeframe_selector = AdaptiveTimeframeSelector()
        self.trader_psychology = QuantTraderPsychology()
        self.confluence_scorer = ConfluenceScorer()
        
        logger.info("RegimeAdaptiveAnalyzer initialized")
    
    async def analyze(
        self,
        candles: Dict[str, List[Dict]],  # Multi-timeframe candles
        indicators: Dict[str, Dict[str, Any]],  # Indicators per timeframe
        smc_analysis: Dict[str, Any],  # SMC results
        ict_analysis: Dict[str, Any],  # ICT results
        patterns: Dict[str, Any],  # Pattern recognition results
        trading_style: str = 'swing'  # 'swing', 'day_trade', 'scalp'
    ) -> Dict[str, Any]:
        """
        Perform regime-adaptive market analysis
        
        Args:
            candles: Multi-timeframe OHLCV data
            indicators: Technical indicators per timeframe
            smc_analysis: SMC detection results
            ict_analysis: ICT methodology results
            patterns: Chart pattern results
            trading_style: Trading style preference
        
        Returns:
            Complete analysis with trade decision
        """
        logger.info("Starting regime-adaptive analysis...")
        
        # Step 1: Detect Market Regime
        regime = await self._detect_regime(candles, indicators)
        
        # Step 2: Select Optimal Timeframes
        tf_strategy = self.timeframe_selector.select_timeframes(regime, trading_style)
        
        # Step 3: Top-Down Analysis
        htf_bias, mtf_setup, ltf_entry = await self._top_down_analysis(
            candles, indicators, smc_analysis, ict_analysis, tf_strategy
        )
        
        # Step 4: Score Confluences
        confluence_score = await self._score_confluences(
            smc_analysis, ict_analysis, indicators, patterns,
            htf_bias, regime
        )
        
        # Step 5: Make Trading Decision
        decision = self.trader_psychology.make_decision(
            regime=regime,
            htf_bias=htf_bias,
            mtf_setup=mtf_setup,
            ltf_entry=ltf_entry,
            confluence_count=confluence_score.confluence_count,
            risk_reward_ratio=mtf_setup.get('risk_reward', 0.0) if mtf_setup else 0.0
        )
        
        # Step 6: Compile Results
        result = {
            'timestamp': datetime.now().isoformat(),
            'regime': {
                'type': regime.regime,
                'confidence': regime.confidence,
                'trend_strength': regime.trend_strength,
                'volatility_level': regime.volatility_level,
                'reasoning': regime.reasoning
            },
            'timeframe_strategy': {
                'primary': tf_strategy.primary_timeframes,
                'secondary': tf_strategy.secondary_timeframes,
                'reference': tf_strategy.reference_timeframes,
                'avoid': tf_strategy.avoid_timeframes,
                'reasoning': tf_strategy.reasoning
            },
            'top_down_analysis': {
                'htf_bias': htf_bias,
                'mtf_setup': mtf_setup,
                'ltf_entry': ltf_entry
            },
            'confluence': {
                'count': confluence_score.confluence_count,
                'total_score': confluence_score.total_score,
                'quality_rating': confluence_score.quality_rating,
                'meets_minimum': confluence_score.meets_minimum,
                'by_category': confluence_score.by_category,
                'details': [
                    {
                        'factor': c.factor,
                        'category': c.category,
                        'weight': c.weight,
                        'description': c.description,
                        'timeframe': c.timeframe
                    }
                    for c in confluence_score.confluences
                ],
                'reasoning': confluence_score.reasoning
            },
            'decision': {
                'action': decision.action,
                'confidence': decision.confidence,
                'reasoning': decision.reasoning,
                'risk_assessment': decision.risk_assessment,
                'position_size_multiplier': decision.position_size_multiplier,
                'required_confluences': decision.required_confluences,
                'stop_loss_buffer': decision.stop_loss_buffer,
                'take_profit_ratio': decision.take_profit_ratio
            },
            'trading_style': trading_style
        }
        
        logger.success(
            f"Analysis complete: {decision.action} "
            f"({confluence_score.confluence_count} confluences, "
            f"{decision.confidence:.2%} confidence)"
        )
        
        return result
    
    async def _detect_regime(
        self,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict[str, Any]]
    ) -> MarketRegime:
        """Detect market regime from 1H timeframe"""
        
        # Use 1H for regime detection (good balance)
        tf = '1h' if '1h' in candles else list(candles.keys())[0]
        
        # Convert to DataFrame
        df = pd.DataFrame(candles[tf])
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        
        # Get indicators for this timeframe
        tf_indicators = indicators.get(tf, {})
        
        # Detect regime
        regime = self.regime_detector.detect(df, tf_indicators)
        
        logger.info(f"Regime detected: {regime.regime} (confidence: {regime.confidence:.2%})")
        
        return regime
    
    async def _top_down_analysis(
        self,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict[str, Any]],
        smc_analysis: Dict[str, Any],
        ict_analysis: Dict[str, Any],
        tf_strategy: TimeframeStrategy
    ) -> tuple[str, Optional[Dict], Optional[Dict]]:
        """
        Perform top-down analysis
        
        Returns:
            (htf_bias, mtf_setup, ltf_entry)
        """
        
        # HTF Bias (from primary timeframes)
        htf_bias = await self._determine_htf_bias(
            candles, indicators, tf_strategy.primary_timeframes
        )
        
        # MTF Setup (from secondary timeframes)
        mtf_setup = await self._identify_mtf_setup(
            candles, smc_analysis, ict_analysis, tf_strategy.secondary_timeframes
        )
        
        # LTF Entry (from lowest timeframe if available)
        ltf_entry = await self._find_ltf_entry(
            candles, indicators, tf_strategy.secondary_timeframes
        )
        
        return htf_bias, mtf_setup, ltf_entry
    
    async def _determine_htf_bias(
        self,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict[str, Any]],
        htf_timeframes: List[str]
    ) -> str:
        """Determine higher timeframe bias"""
        
        return 'NEUTRAL'
    
    async def _identify_mtf_setup(
        self,
        candles: Dict[str, List[Dict]],
        smc_analysis: Dict[str, Any],
        ict_analysis: Dict[str, Any],
        mtf_timeframes: List[str]
    ) -> Optional[Dict]:
        """Identify medium timeframe setup"""
        
        # Look for SMC/ICT setups
        setup = {
            'type': 'pullback',  # pullback, breakout, reversal
            'entry_zone': None,
            'stop_loss': None,
            'take_profit': None,
            'risk_reward': 0.0
        }
        
        # Check for order blocks
        order_blocks = smc_analysis.get('order_blocks', [])
        if order_blocks:
            # Use most recent order block
            ob = order_blocks[0]
            setup['entry_zone'] = ob.get('price')
            setup['type'] = 'pullback_to_ob'
        
        # Estimate R:R (simplified)
        if setup['entry_zone']:
            # Assume 1.5% stop, 3% target for now
            setup['stop_loss'] = setup['entry_zone'] * 0.985
            setup['take_profit'] = setup['entry_zone'] * 1.03
            setup['risk_reward'] = 2.0
        
        return setup
    
    async def _find_ltf_entry(
        self,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict[str, Any]],
        ltf_timeframes: List[str]
    ) -> Optional[Dict]:
        """Find lower timeframe entry trigger"""
        
        # Look for entry confirmation
        entry = {
            'trigger': 'pending',
            'price': None,
            'confirmation': []
        }
        
        # Use lowest available timeframe
        for tf in reversed(ltf_timeframes):
            if tf in candles:
                entry['price'] = candles[tf][-1]['close']
                break
        
        return entry
    
    async def _score_confluences(
        self,
        smc_analysis: Dict[str, Any],
        ict_analysis: Dict[str, Any],
        indicators: Dict[str, Dict[str, Any]],
        patterns: Dict[str, Any],
        htf_bias: str,
        regime: MarketRegime
    ) -> ConfluenceScore:
        """Score trade confluences"""
        
        # Determine direction from HTF bias
        direction = 'LONG' if htf_bias == 'BULLISH' else 'SHORT' if htf_bias == 'BEARISH' else 'NEUTRAL'
        
        if direction == 'NEUTRAL':
            # No clear direction, return empty score
            return ConfluenceScore(
                total_score=0.0,
                confluence_count=0,
                confluences=[],
                by_category={},
                quality_rating='POOR',
                meets_minimum=False,
                reasoning="No clear HTF bias - waiting for direction"
            )
        
        # Get indicators from primary timeframe
        primary_indicators = indicators.get('1h', indicators.get('4h', {}))
        
        # Build market structure
        market_structure = {
            'htf_trend': htf_bias.lower(),
            'mtf_trend': htf_bias.lower()  # Simplified
        }
        
        # Get minimum confluences based on regime
        recommendations = self.regime_detector.get_strategy_recommendations(regime)
        min_confluences = recommendations['confluences_required']
        
        # Score confluences
        score = self.confluence_scorer.score_setup(
            smc_analysis=smc_analysis,
            ict_analysis=ict_analysis,
            indicators=primary_indicators,
            patterns=patterns,
            market_structure=market_structure,
            direction=direction,
            minimum_required=min_confluences
        )
        
        return score


async def test_regime_adaptive_analyzer():
    """Test the regime-adaptive analyzer"""
    import numpy as np
    import pandas_ta as ta
    
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=200, freq='1H')
    trend = np.linspace(40000, 45000, 200)
    noise = np.random.randn(200) * 100
    close_prices = trend + noise
    
    candles_1h = []
    for i, date in enumerate(dates):
        candles_1h.append({
            'timestamp': date,
            'open': close_prices[i] - 50,
            'high': close_prices[i] + 100,
            'low': close_prices[i] - 100,
            'close': close_prices[i],
            'volume': np.random.randint(1000, 10000)
        })
    
    # Calculate indicators
    df = pd.DataFrame(candles_1h)
    df.set_index('timestamp', inplace=True)
    
    indicators_1h = {}
    indicators_1h['rsi_14'] = ta.rsi(df['close'], length=14).iloc[-1]
    indicators_1h['ema_21'] = ta.ema(df['close'], length=21).iloc[-1]
    indicators_1h['ema_50'] = ta.ema(df['close'], length=50).iloc[-1]
    indicators_1h['ema_200'] = ta.ema(df['close'], length=200).iloc[-1]
    indicators_1h['adx'] = ta.adx(df['high'], df['low'], df['close'], length=14)['ADX_14'].iloc[-1]
    indicators_1h['di_plus'] = ta.adx(df['high'], df['low'], df['close'], length=14)['DMP_14'].iloc[-1]
    indicators_1h['di_minus'] = ta.adx(df['high'], df['low'], df['close'], length=14)['DMN_14'].iloc[-1]
    indicators_1h['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
    
    bb = ta.bbands(df['close'], length=20, std=2)
    indicators_1h['bb_width'] = ((bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']).iloc[-1]
    
    # Mock analysis results
    smc_analysis = {
        'order_blocks': [
            {'type': 'bullish', 'price': 43000, 'timeframe': '4h'}
        ],
        'fair_value_gaps': [],
        'break_of_structure': {'detected': True, 'direction': 'bullish', 'timeframe': '1h'}
    }
    
    ict_analysis = {
        'killzone': {'active': True, 'name': 'London Open'},
        'liquidity_sweeps': [],
        'ote_zones': {'in_zone': False}
    }
    
    patterns = {'patterns': []}
    
    # Run analysis
    analyzer = RegimeAdaptiveAnalyzer()
    
    result = await analyzer.analyze(
        candles={'1h': candles_1h, '4h': candles_1h[::4]},
        indicators={'1h': indicators_1h, '4h': indicators_1h},
        smc_analysis=smc_analysis,
        ict_analysis=ict_analysis,
        patterns=patterns,
        trading_style='swing'
    )
    
    logger.info("\n=== REGIME-ADAPTIVE ANALYSIS RESULT ===")
    logger.info(f"Regime: {result['regime']['type']} ({result['regime']['confidence']:.2%})")
    logger.info(f"HTF Bias: {result['top_down_analysis']['htf_bias']}")
    logger.info(f"Confluences: {result['confluence']['count']} ({result['confluence']['quality_rating']})")
    logger.info(f"Decision: {result['decision']['action']} ({result['decision']['confidence']:.2%})")
    logger.info(f"Position Size: {result['decision']['position_size_multiplier']:.2f}x")


if __name__ == "__main__":
    asyncio.run(test_regime_adaptive_analyzer())
