"""
Dual-context LLM context builder - creates separate prompts for swing vs scalping
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from loguru import logger
import json


@dataclass
class LLMContextRequest:
    """Request for LLM context generation"""
    symbol: str
    analysis_type: str  # 'swing' or 'scalping'
    swing_results: Optional[Dict[str, Any]] = None
    scalping_results: Optional[Dict[str, Any]] = None
    historical_trades: Optional[List[Dict]] = None


class DualContextLLMBuilder:
    """Generates contextual LLM prompts for different trading strategies"""
    
    SWING_TRADING_SYSTEM_PROMPT = """
You are an expert swing trading analyst specializing in institutional market structure analysis.

Your role:
- Identify high-probability swing setups (4H-1H timeframe structure)
- Confirm entries on 15m-5m timeframes
- Focus on quality over frequency
- Prioritize risk:reward ratios (minimum 1:2)
- Use Smart Money Concepts (SMC) and ICT methodologies

Key Analysis Areas:
1. Market Structure (4H primary, 1H confirmation)
   - Identify trends, reversals, consolidation
   - Locate institutional order blocks
   - Map fair value gaps and liquidity zones

2. Entry Triggers (15m-5m secondary)
   - Use lower timeframe confirmation
   - Look for pullbacks to structure
   - Identify exact entry points with stop placement

3. Risk Management
   - Define clear stop levels below/above structures
   - Calculate position size based on risk:reward
   - Identify key levels for profit taking

Output Format:
ALWAYS respond with ONLY valid JSON (no markdown, no text before/after) with this exact structure:
{
  "market_structure": {
    "1d_trend": "bullish|bearish|neutral",
    "4h_trend": "bullish|bearish|neutral",
    "1h_trend": "bullish|bearish|neutral",
    "alignment": "aligned|conflicted|mixed",
    "overall_bias": "bullish|bearish|neutral"
  },
  "key_levels": {
    "resistance": [level1, level2, level3],
    "support": [level1, level2, level3],
    "most_significant": {
      "level": number,
      "type": "resistance|support",
      "reason": "description"
    }
  },
  "smc_confluences": [
    {
      "type": "order_block|fvg|liquidity_sweep",
      "timeframe": "4h|1h|15m|5m",
      "description": "detailed description",
      "significance": "high|medium|low"
    }
  ],
  "ict_setup": {
    "killzone_active": boolean,
    "liquidity_sweeps": [list of sweep types],
    "order_flow_phase": "description",
    "ote_zone_status": "description"
  },
  "trade_opportunities": [
    {
      "direction": "LONG|SHORT",
      "entry_zone": [level1, level2],
      "confluence_count": number,
      "key_factors": [list of factors],
      "confidence": 0.0-1.0,
      "invalidation_level": number,
      "type": "FVG Retest|Support Bounce|Resistance Break|etc"
    }
  ],
  "reasoning": "comprehensive explanation of the analysis"
}
"""

    SCALPING_SYSTEM_PROMPT = """
You are an expert scalping analyst specializing in rapid price action and momentum.

Your role:
- Identify quick scalping opportunities (5m-1m timeframe action)
- Focus on momentum and liquidity sweeps
- Optimize for entry speed and minimal slippage
- Target 1:1 to 1:1.5 risk:reward (accept higher frequency, lower ratio)
- Use candlestick patterns and order flow analysis

Key Analysis Areas:
1. Immediate Price Action (5m-1m primary)
   - Identify recent patterns and breakouts
   - Spot liquidity sweeps and sudden moves
   - Assess momentum indicators (RSI, MACD divergences)

2. Context Bias (15m-1h reference)
   - Confirm direction aligns with higher timeframe trend
   - Avoid counter-trend trades
   - Use major levels as reference only

3. Entry Timing (Real-time)
   - Immediate entry signals
   - Quick profit targets (20-50 pips)
   - Tight stops (10-20 pips)

Output Format:
ALWAYS respond with ONLY valid JSON (no markdown, no text before/after) with this exact structure:
{
  "market_structure": {
    "1h_trend": "bullish|bearish|neutral",
    "15m_trend": "bullish|bearish|neutral",
    "5m_trend": "bullish|bearish|neutral",
    "1m_trend": "bullish|bearish|neutral",
    "alignment": "aligned|conflicted|mixed",
    "overall_bias": "bullish|bearish|neutral"
  },
  "key_levels": {
    "immediate_resistance": [level1, level2],
    "immediate_support": [level1, level2],
    "most_relevant": {
      "level": number,
      "type": "resistance|support",
      "reason": "description"
    }
  },
  "momentum_analysis": {
    "direction": "up|down|neutral",
    "strength": "strong|moderate|weak",
    "indicators": ["indicator1", "indicator2"],
    "recent_action": "description"
  },
  "entry_signals": [
    {
      "type": "breakout|pullback|reversal|sweep",
      "timeframe": "5m|1m",
      "entry_level": number,
      "description": "detailed description",
      "confidence": 0.0-1.0
    }
  ],
  "scalp_opportunities": [
    {
      "direction": "LONG|SHORT",
      "entry": number,
      "stop_loss": number,
      "take_profit": [profit1, profit2],
      "risk_reward": 1.0,
      "setup_type": "Momentum Scalp|Breakout Scalp|etc",
      "confluence_factors": [list of factors]
    }
  ],
  "reasoning": "rapid analysis of scalping opportunities"
}
"""
    
    def __init__(self):
        self.logger = logger
    
    def build_swing_context(
        self,
        symbol: str,
        swing_results: Dict[str, Any],
        candles: Dict[str, List[Dict]],
        historical_trades: Optional[List[Dict]] = None
    ) -> Dict[str, str]:
        """Build LLM context for swing trading analysis"""
        
        self.logger.info("🎯 Building Swing Trading LLM Context")
        
        # Build the swing analysis message
        swing_analysis = self._build_swing_analysis_message(
            symbol, swing_results, candles
        )
        
        context = {
            'system_prompt': self.SWING_TRADING_SYSTEM_PROMPT,
            'analysis_type': 'swing',
            'symbol': symbol,
            'message': swing_analysis,
            'timeframe_hierarchy': '4H (Structure) → 1H (Confirmation) → 15m (Entry) → 5m (Trigger)',
            'focus': 'High-probability setups with proper structure confirmation'
        }
        
        return context
    
    def build_scalping_context(
        self,
        symbol: str,
        scalping_results: Dict[str, Any],
        candles: Dict[str, List[Dict]],
        historical_trades: Optional[List[Dict]] = None
    ) -> Dict[str, str]:
        """Build LLM context for scalping analysis"""
        
        self.logger.info("⚡ Building Scalping LLM Context")
        
        # Build the scalping analysis message
        scalping_analysis = self._build_scalping_analysis_message(
            symbol, scalping_results, candles
        )
        
        context = {
            'system_prompt': self.SCALPING_SYSTEM_PROMPT,
            'analysis_type': 'scalping',
            'symbol': symbol,
            'message': scalping_analysis,
            'timeframe_hierarchy': '5m (Primary) → 1m (Entry) → 15m (Bias) → 1H (Reference)',
            'focus': 'Rapid opportunities with tight risk:reward'
        }
        
        return context
    
    def _build_swing_analysis_message(
        self,
        symbol: str,
        swing_results: Dict[str, Any],
        candles: Dict[str, List[Dict]]
    ) -> str:
        """Build the message content for swing trading analysis"""
        
        message = f"""
Analyze {symbol} for swing trading opportunities using the following computational results:

## MARKET STRUCTURE ANALYSIS (4H Primary)
{self._format_timeframe_analysis(swing_results, '4h')}

## INTERMEDIATE STRUCTURE (1H Confirmation)
{self._format_timeframe_analysis(swing_results, '1h')}

## ENTRY REFINEMENT (15M Secondary)
{self._format_timeframe_analysis(swing_results, '15m')}

## ENTRY TRIGGER CONFIRMATION (5M Secondary)
{self._format_timeframe_analysis(swing_results, '5m')}

## MACRO CONTEXT (1D Reference)
{self._format_timeframe_analysis(swing_results, '1d')}

## CURRENT MARKET DATA
Last 5 candles (1H):
{self._format_candles_sample(candles.get('1h', [])[-5:] if '1h' in candles else [])}

Last 5 candles (15M):
{self._format_candles_sample(candles.get('15m', [])[-5:] if '15m' in candles else [])}

## YOUR TASK - RESPOND WITH JSON ONLY
1. Assess overall market structure (4H primary bias)
2. Identify institutional levels and order blocks
3. Confirm entry triggers on lower timeframes
4. Rate setup quality (High/Medium/Low based on confluence)
5. Recommend specific trade opportunities with:
   - Entry level
   - Stop loss placement
   - Take profit targets
   - Risk:reward ratio

Return ONLY valid JSON matching the system prompt format. No markdown, no text before or after.
"""
        
        return message
    
    def _build_scalping_analysis_message(
        self,
        symbol: str,
        scalping_results: Dict[str, Any],
        candles: Dict[str, List[Dict]]
    ) -> str:
        """Build the message content for scalping analysis"""
        
        message = f"""
Identify scalping opportunities in {symbol} using the following computational results:

## IMMEDIATE PRICE ACTION (5M Primary)
{self._format_timeframe_analysis(scalping_results, '5m')}

## ENTRY PRECISION (1M Primary)
{self._format_timeframe_analysis(scalping_results, '1m')}

## DIRECTIONAL BIAS (15M Secondary)
{self._format_timeframe_analysis(scalping_results, '15m')}

## REFERENCE LEVELS (1H Reference Only)
{self._format_timeframe_analysis(scalping_results, '1h')}

## CURRENT PRICE ACTION
Last 10 candles (5M):
{self._format_candles_sample(candles.get('5m', [])[-10:] if '5m' in candles else [])}

Last 5 candles (1M):
{self._format_candles_sample(candles.get('1m', [])[-5:] if '1m' in candles else [])}

## YOUR TASK - RESPOND WITH JSON ONLY
1. Assess current momentum direction (5m/1m)
2. Confirm directional bias aligns with 15m trend
3. Identify immediate entry signals
4. Recommend quick scalping opportunities with:
   - Immediate entry level
   - Tight stop loss (10-20 pips)
   - Quick profit target (20-50 pips)
   - Risk:reward ratio (accept 1:1 or better)
5. Prioritize speed and risk management over size

Return ONLY valid JSON matching the system prompt format. No markdown, no text before or after.
"""
        
        return message
    
    def _format_timeframe_analysis(
        self,
        results: Dict[str, Any],
        timeframe: str
    ) -> str:
        """Format analysis results for a specific timeframe"""
        
        tf_data = results.get('timeframes_analyzed', {}).get(timeframe, {})
        
        if not tf_data:
            return f"No data available for {timeframe}"
        
        formatted = f"### {timeframe.upper()} Analysis\n"
        formatted += f"Candles: {tf_data.get('candles', 0)}\n\n"
        
        analyses = tf_data.get('analyses', {})
        
        if 'smc' in analyses:
            smc = analyses['smc']
            formatted += f"**SMC Structures:**\n"
            formatted += f"- Order Blocks: {len(smc.get('order_blocks', []))}\n"
            formatted += f"- Fair Value Gaps: {len(smc.get('fvg_zones', []))}\n"
            formatted += f"- Liquidity Zones: {len(smc.get('liquidity_pools', []))}\n\n"
        
        if 'ict' in analyses:
            ict = analyses['ict']
            formatted += f"**ICT Analysis:**\n"
            if 'liquidity_sweeps' in ict:
                formatted += f"- Recent Sweeps: {len(ict.get('liquidity_sweeps', []))}\n"
            if 'setup_quality' in ict:
                formatted += f"- Setup Quality: {ict.get('setup_quality', 'unknown')}\n\n"
        
        if 'patterns' in analyses:
            patterns = analyses['patterns']
            formatted += f"**Chart Patterns:**\n"
            formatted += f"- Patterns Found: {patterns.get('count', 0)}\n"
            if patterns.get('patterns'):
                formatted += f"- Recent: {patterns['patterns'][0].get('name', 'unknown')}\n\n"
        
        if 'indicators' in analyses:
            formatted += f"- Technical Indicators: Calculated (21 indicators)\n\n"
        
        return formatted
    
    def _format_candles_sample(self, candles: List[Dict]) -> str:
        """Format recent candles for display"""
        
        if not candles:
            return "No candle data available"
        
        formatted = "```\nTime          | Open      | High      | Low       | Close     | Volume\n"
        formatted += "=" * 80 + "\n"
        
        for candle in candles:
            ts = str(candle.get('timestamp', ''))[-16:-6] if 'timestamp' in candle else 'N/A'
            formatted += f"{ts} | "
            formatted += f"{candle.get('open', 0):>9.2f} | "
            formatted += f"{candle.get('high', 0):>9.2f} | "
            formatted += f"{candle.get('low', 0):>9.2f} | "
            formatted += f"{candle.get('close', 0):>9.2f} | "
            formatted += f"{int(candle.get('volume', 0)):>10}\n"
        
        formatted += "```\n"
        return formatted
    
    def estimate_context_size(self, message: str) -> Dict[str, int]:
        """Estimate context size in tokens and bytes"""
        
        chars = len(message)
        # Rough estimate: 4 chars = 1 token (varies by model)
        estimated_tokens = int(chars / 4)
        
        return {
            'characters': chars,
            'estimated_tokens': estimated_tokens,
            'safe_for_claude': estimated_tokens < 100000,  # Claude: 200K window
            'safe_for_deepseek': estimated_tokens < 150000  # DeepSeek: 163K window
        }
