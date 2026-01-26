"""
Multi-context analyzer - runs separate computational analyses for Swing vs Scalping
"""
import asyncio
import pandas as pd
from typing import Dict, Any, List
from dataclasses import dataclass
from loguru import logger

from src.analysis.indicators import TechnicalIndicators
from src.analysis.smc_detector import SMCDetector
from src.analysis.ict_detector import ICTDetector
from src.analysis.pattern_recognition import PatternRecognizer
from src.analysis.mtf_analyzer import MultiTimeframeAnalyzer


@dataclass
class TimeframeAnalysisConfig:
    """Configuration for which timeframes to analyze"""
    name: str  # 'swing' or 'scalping'
    primary_tfs: List[str]  # Main analysis timeframes
    secondary_tfs: List[str]  # Secondary/confirmation timeframes
    reference_tfs: List[str]  # Reference only (major levels)
    min_candles: int  # Minimum candles required
    
    # Analysis settings
    compute_smc: bool = True
    compute_ict: bool = True
    compute_patterns: bool = True
    compute_indicators: bool = True


class MultiContextAnalyzer:
    """Runs computational analysis tailored to swing vs scalping contexts"""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.smc_detector = SMCDetector()
        self.ict_detector = ICTDetector()
        self.pattern_recognizer = PatternRecognizer()
        self.mtf_analyzer = MultiTimeframeAnalyzer()
        
        # Define contexts
        self.swing_config = TimeframeAnalysisConfig(
            name='swing',
            primary_tfs=['4h', '1h'],
            secondary_tfs=['15m', '5m'],
            reference_tfs=['1d'],
            min_candles=100,
            compute_smc=True,
            compute_ict=True,
            compute_patterns=True,
            compute_indicators=True
        )
        
        self.scalping_config = TimeframeAnalysisConfig(
            name='scalping',
            primary_tfs=['5m', '1m'],
            secondary_tfs=['15m'],
            reference_tfs=['1h'],
            min_candles=50,
            compute_smc=True,
            compute_ict=True,
            compute_patterns=True,
            compute_indicators=True
        )
    
    async def analyze_swing_context(
        self,
        dataframes: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """Run swing trading analysis (primary strategy)"""
        logger.info("🎯 Starting Swing Trading Analysis (Multi-Timeframe)")
        
        return await self._run_context_analysis(
            dataframes,
            self.swing_config
        )
    
    async def analyze_scalping_context(
        self,
        dataframes: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """Run scalping analysis (secondary strategy)"""
        logger.info("⚡ Starting Scalping Analysis (Multi-Timeframe)")
        
        return await self._run_context_analysis(
            dataframes,
            self.scalping_config
        )
    
    async def _run_context_analysis(
        self,
        dataframes: Dict[str, pd.DataFrame],
        config: TimeframeAnalysisConfig
    ) -> Dict[str, Any]:
        """Run analysis tailored to a specific context"""
        
        results = {
            'context': config.name,
            'timeframes_analyzed': {},
            'summary': {
                'primary': {},
                'secondary': {},
                'reference': {}
            }
        }
        
        # Analyze PRIMARY timeframes (highest priority)
        logger.info(f"Analyzing PRIMARY timeframes: {config.primary_tfs}")
        for tf in config.primary_tfs:
            if tf in dataframes:
                df = dataframes[tf]
                if len(df) >= config.min_candles:
                    results['timeframes_analyzed'][tf] = await self._analyze_timeframe(
                        df, tf, config
                    )
                    results['summary']['primary'][tf] = self._summarize_results(
                        results['timeframes_analyzed'][tf]
                    )
        
        # Analyze SECONDARY timeframes (confirmation/entry refinement)
        logger.info(f"Analyzing SECONDARY timeframes: {config.secondary_tfs}")
        for tf in config.secondary_tfs:
            if tf in dataframes:
                df = dataframes[tf]
                if len(df) >= config.min_candles:
                    results['timeframes_analyzed'][tf] = await self._analyze_timeframe(
                        df, tf, config
                    )
                    results['summary']['secondary'][tf] = self._summarize_results(
                        results['timeframes_analyzed'][tf]
                    )
        
        # Analyze REFERENCE timeframes (major levels only)
        logger.info(f"Analyzing REFERENCE timeframes: {config.reference_tfs}")
        for tf in config.reference_tfs:
            if tf in dataframes:
                df = dataframes[tf]
                if len(df) >= config.min_candles:
                    # Reference: only major structures, no patterns
                    results['timeframes_analyzed'][tf] = await self._analyze_timeframe(
                        df, tf, config, reference_mode=True
                    )
                    results['summary']['reference'][tf] = self._summarize_results(
                        results['timeframes_analyzed'][tf]
                    )
        
        logger.info(f"✅ {config.name.upper()} analysis complete")
        return results
    
    async def _analyze_timeframe(
        self,
        df: pd.DataFrame,
        timeframe: str,
        config: TimeframeAnalysisConfig,
        reference_mode: bool = False
    ) -> Dict[str, Any]:
        """Analyze a single timeframe"""
        
        loop = asyncio.get_event_loop()
        results = {
            'timeframe': timeframe,
            'candles': len(df),
            'analyses': {}
        }
        
        # Run analyses in parallel
        tasks = {}
        
        if config.compute_indicators:
            tasks['indicators'] = loop.run_in_executor(
                None, self.indicators.calculate_all, df
            )
        
        if config.compute_smc and not reference_mode:
            tasks['smc'] = loop.run_in_executor(
                None, self.smc_detector.analyze, df
            )
        
        if config.compute_ict and not reference_mode:
            tasks['ict'] = loop.run_in_executor(
                None, self.ict_detector.analyze, df
            )
        
        if config.compute_patterns and not reference_mode:
            tasks['patterns'] = loop.run_in_executor(
                None, self.pattern_recognizer.analyze, df
            )
        
        # Collect results
        for analysis_name, task in tasks.items():
            try:
                results['analyses'][analysis_name] = await task
                logger.debug(f"  ✓ {analysis_name} complete for {timeframe}")
            except Exception as e:
                logger.error(f"  ✗ {analysis_name} failed for {timeframe}: {e}")
                results['analyses'][analysis_name] = {}
        
        return results
    
    def _summarize_results(self, tf_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of results for this timeframe"""
        summary = {
            'candles': tf_results.get('candles', 0),
            'analyses_completed': list(tf_results.get('analyses', {}).keys())
        }
        
        # Count structures found
        if 'smc' in tf_results.get('analyses', {}):
            smc = tf_results['analyses']['smc']
            summary['smc_structures'] = {
                'order_blocks': len(smc.get('order_blocks', [])),
                'fvg_zones': len(smc.get('fvg_zones', [])),
                'liquidity_pools': len(smc.get('liquidity_pools', []))
            }
        
        if 'patterns' in tf_results.get('analyses', {}):
            patterns = tf_results['analyses']['patterns']
            summary['patterns_found'] = patterns.get('count', 0)
        
        return summary
