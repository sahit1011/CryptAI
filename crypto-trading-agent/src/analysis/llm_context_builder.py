"""
LLM Context Builder and Optimizer
Prepares optimized contexts for Claude Sonnet 4.5 analysis
"""
import json
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd
from loguru import logger

# How many raw bars each timeframe contributes to the PROMPT (not to the detectors —
# they keep the full window). The indicators/SMC/ICT sections already carry the
# computed meaning of the older bars; re-sending 1,500 raw candles as indented JSON
# was ~35 tokens per candle of pure repetition, and it is exactly what pushed a
# 6-requests-per-cycle pipeline into the free tier's daily request cap (R1.6b).
RECENT_BARS_IN_PROMPT = 20


def _fmt_num(value: Any) -> str:
    """Compact numeric rendering: 64150.0 -> '64150', 0.2500 -> '0.25'.

    10 significant digits so no real price loses a cent — compaction must never
    round away information the model is asked to reason about.
    """
    try:
        return f"{float(value):.10g}"
    except (TypeError, ValueError):
        return str(value)


def _short_ts(value: Any) -> str:
    """'2026-08-24T20:00:00+00:00' -> '2026-08-24T20:00' (candles align to minutes)."""
    s = str(value)
    return s[:16] if len(s) > 16 and s[4:5] == "-" and s[10:11] == "T" else s


def _candle_lines(tf: str, bars: List[Dict]) -> List[str]:
    """One timeframe as: a whole-window stats line + the recent bars as CSV rows."""
    if not bars:
        return [f"### {tf}: no data"]

    def col(key: str) -> List[float]:
        out = []
        for b in bars:
            try:
                out.append(float(b[key]))
            except (KeyError, TypeError, ValueError):
                pass
        return out

    highs, lows, closes, opens = col("h"), col("l"), col("c"), col("o")
    header = f"### {tf} — {len(bars)} bars, {_short_ts(bars[0].get('t'))} → {_short_ts(bars[-1].get('t'))}"
    if highs and lows and closes and opens:
        net = (closes[-1] - opens[0]) / opens[0] * 100 if opens[0] else 0.0
        header += (
            f" | window high {_fmt_num(max(highs))} low {_fmt_num(min(lows))}"
            f" | net {net:+.2f}% | last close {_fmt_num(closes[-1])}"
        )

    lines = [header, f"recent {min(len(bars), RECENT_BARS_IN_PROMPT)} bars (time,open,high,low,close,volume):"]
    for b in bars[-RECENT_BARS_IN_PROMPT:]:
        lines.append(
            f"{_short_ts(b.get('t'))},{_fmt_num(b.get('o'))},{_fmt_num(b.get('h'))},"
            f"{_fmt_num(b.get('l'))},{_fmt_num(b.get('c'))},{_fmt_num(b.get('v'))}"
        )
    return lines


def _safe_default(o: Any) -> Any:
    # Context has already been through _make_serializable upstream; this is the
    # last-resort catch so a stray numpy/pandas scalar can't kill a live cycle.
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, pd.Series):
        return o.tolist()
    if isinstance(o, pd.DataFrame):
        return o.to_dict("records")
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)


def _compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), default=_safe_default)


# Detector sections (SMC/ICT/patterns) emit up to ~10 structures per list per
# timeframe; the most recent few carry the tradeable information. Keep the newest
# LIST_CAP and say how many were dropped — the cost law wants the tokens back, the
# honesty law forbids pretending the omitted structures never existed.
LIST_CAP = 5


def _slim(data: Any) -> Any:
    """Prompt-display copy of a detector section: recent-N lists, rounded floats.

    Rounding is display-only (the engine keeps full precision): 2 decimals for
    price-scale values, 4 for ratios/strengths below 10.
    """
    if isinstance(data, dict):
        return {k: _slim(v) for k, v in data.items()}
    if isinstance(data, list):
        kept = [_slim(v) for v in data[-LIST_CAP:]]
        if len(data) > LIST_CAP:
            kept.insert(0, f"(+{len(data) - LIST_CAP} earlier entries omitted)")
        return kept
    if isinstance(data, float):
        return round(data, 2) if abs(data) >= 10 else round(data, 4)
    if isinstance(data, str):
        return _short_ts(data)  # no-op unless the string is ISO-timestamp shaped
    return data


def render_user_message(context: Dict[str, Any]) -> str:
    """The ONE user-message renderer for analysis LLM calls (all provider tiers).

    Replaces three identical inline builders that dumped the whole context as
    indent=2 JSON (~40k tokens/call, mostly raw candles). Candles render as a
    per-timeframe stats line + recent bars in CSV; every other section keeps its
    full content, just without the indentation tax.
    """
    lines = ["Analyze the following market data:", "", "## Market Data"]
    for tf, bars in (context.get("current_data") or {}).items():
        lines.extend(_candle_lines(tf, bars if isinstance(bars, list) else []))
        lines.append("")

    for title, key, slim in (
        ("## Technical Indicators", "indicators", False),
        ("## Smart Money Concepts Analysis", "smc_analysis", True),
        ("## ICT Methodology Analysis", "ict_analysis", True),
        ("## Chart Patterns", "patterns", True),
        ("## Historical Context", "historical_context", False),
    ):
        section = context.get(key, {})
        lines.append(title)
        lines.append(_compact(_slim(section) if slim else section))
        lines.append("")

    lines.append(str(context.get("task_instructions", "")))
    return "\n".join(lines)


class LLMContextBuilder:
    """
    Builds and optimizes context for LLM analysis
    Manages token budget and prioritizes information
    """

    # Token estimation (approximate)
    TOKENS_PER_CHAR = 0.25
    MAX_TOKENS = 150000  # Leave 50K for response

    # Priority weights for sections
    SECTION_PRIORITIES = {
        'system_prompt': 10,
        'current_data': 9,
        'indicators': 8,
        'smc_analysis': 9,
        'ict_analysis': 9,
        'patterns': 7,
        'historical_context': 6,
        'task_instructions': 10
    }

    def __init__(self):
        self.context_cache = {}
        self.previous_context_hash = None

    def build_analysis_context(
        self,
        symbol: str,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict],
        smc_results: Dict[str, Any],
        ict_results: Dict[str, Any],
        patterns: Dict[str, Any],
        historical_trades: Optional[List[Dict]] = None,
        market_regime: Optional[str] = None,
        timeframe_strategy: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build complete context for market analysis

        Args:
            symbol: Trading symbol
            candles: Multi-timeframe candle data
            indicators: Calculated indicators per timeframe
            smc_results: SMC detector results
            ict_results: ICT detector results
            patterns: Pattern recognition results
            historical_trades: Recent trade history
            market_regime: Current market regime classification

        Returns:
            Optimized context dictionary ready for LLM
        """
        try:
            logger.info(f"Building analysis context for {symbol}")

            # Filter data based on timeframe strategy if provided
            active_timeframes = None
            if timeframe_strategy:
                # Combine primary and secondary timeframes
                active_timeframes = (
                    timeframe_strategy.get('primary', []) + 
                    timeframe_strategy.get('secondary', [])
                )
                logger.info(f"Filtering context for active timeframes: {active_timeframes}")

            # Build full context
            full_context = {
                'system_prompt': self._build_system_prompt(market_regime),
                'current_data': self._prepare_candle_data(candles, active_timeframes),
                'indicators': self._compress_indicators(indicators, active_timeframes),
                'smc_analysis': self._filter_by_timeframe(smc_results, active_timeframes),
                'ict_analysis': self._filter_by_timeframe(ict_results, active_timeframes),
                'patterns': self._filter_by_timeframe(patterns, active_timeframes),
                'historical_context': self._prepare_historical_context(
                    historical_trades, market_regime
                ),
                'task_instructions': self._build_task_instructions(active_timeframes)
            }

            # Estimate tokens
            estimated_tokens = self._estimate_tokens(full_context)
            logger.info(f"Initial context size: ~{estimated_tokens:,} tokens")

            # Optimize if needed
            if estimated_tokens > self.MAX_TOKENS:
                logger.warning(f"Context too large, optimizing...")
                full_context = self._optimize_context(full_context, estimated_tokens)

            # Generate context hash for caching
            context_hash = self._generate_hash(full_context)
            full_context['_context_hash'] = context_hash
            full_context['_timestamp'] = datetime.utcnow().isoformat()
            full_context['_symbol'] = symbol

            final_tokens = self._estimate_tokens(full_context)
            logger.info(f"✅ Final context: ~{final_tokens:,} tokens")

            return full_context

        except Exception as e:
            logger.error(f"Error building context: {e}", exc_info=True)
            raise

    def _build_system_prompt(self, market_regime: Optional[str] = None) -> str:
        """Build system prompt for analysis agent"""
        
        base_prompt = """You are an expert cryptocurrency technical analyst specializing in Smart Money Concepts (SMC) and Inner Circle Trader (ICT) methodology.

Your expertise includes:
- Multi-timeframe analysis (1D → 4H → 1H → 15M → 5M)
- Order Block identification and mitigation
- Fair Value Gap (imbalance) detection
- Break of Structure and Change of Character
- Liquidity mapping and sweep detection
- ICT killzones and order flow
- Optimal Trade Entry (OTE) zones
- Classical chart patterns
- Technical indicator confluence

Your role is to:
1. Analyze provided market data across all timeframes
2. Identify high-probability trading opportunities
3. Assess confluence of multiple factors
4. Provide clear, actionable reasoning
5. Quantify confidence levels

Always think step-by-step and provide detailed reasoning for your analysis."""

        # Inject regime-specific rules
        if market_regime:
            regime_upper = market_regime.upper()
            if 'TRENDING' in regime_upper:
                base_prompt += """

MARKET REGIME: TRENDING
- Focus on trend continuation setups (pullbacks to OB/FVG).
- Ignore counter-trend signals unless there is a clear HTF reversal structure.
- Use HTF for bias and LTF for entry."""
            elif 'RANGING' in regime_upper:
                base_prompt += """

MARKET REGIME: RANGING
- Focus on mean reversion (buy low, sell high).
- Look for liquidity sweeps at range boundaries.
- Ignore breakouts until confirmed by a retest."""
            elif 'VOLATILE' in regime_upper:
                base_prompt += """

MARKET REGIME: VOLATILE
- Exercise extreme caution.
- Focus on major HTF levels only.
- Require higher confluence for any trade."""

        return base_prompt

    def _prepare_candle_data(
        self, 
        candles: Dict[str, List[Dict]],
        active_timeframes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Prepare and compress candle data
        Uses sliding window to include only relevant recent candles
        """
        prepared = {}

        # Candle limits per timeframe (most recent)
        limits = {
            '1d': 100,   # ~3 months
            '4h': 200,   # ~1 month
            '1h': 300,   # ~2 weeks
            '15m': 400,  # ~4 days
            '5m': 500    # ~2 days
        }

        for tf, candle_list in candles.items():
            # Skip if not in active timeframes (and not a reference TF like 1d)
            if active_timeframes and tf not in active_timeframes and tf != '1d':
                continue
                
            limit = limits.get(tf, 100)
            recent_candles = candle_list[-limit:] if len(candle_list) > limit else candle_list

            # Extract essential fields only
            prepared[tf] = [
                {
                    't': c.get('timestamp').isoformat() if hasattr(c.get('timestamp'), 'isoformat') else str(c.get('timestamp', c.get('t'))),
                    'o': round(c['open'], 2),
                    'h': round(c['high'], 2),
                    'l': round(c['low'], 2),
                    'c': round(c['close'], 2),
                    'v': int(c['volume'])
                }
                for c in recent_candles
            ]

        return prepared

    def _compress_indicators(
        self, 
        indicators: Dict[str, Dict],
        active_timeframes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compress indicator data - send only critical values
        Instead of full arrays, send current values + trend info
        """
        compressed = {}

        for tf, ind_dict in indicators.items():
            # Skip if not in active timeframes (and not a reference TF like 1d)
            if active_timeframes and tf not in active_timeframes and tf != '1d':
                continue
                
            # Convert pandas Series to float values to avoid JSON serialization issues
            def safe_get_last(series, default=0.0):
                """Safely get last value from pandas Series, converting to float"""
                if isinstance(series, pd.Series) and len(series) > 0:
                    val = series.iloc[-1]
                    # Handle numpy types that aren't JSON serializable
                    if hasattr(val, 'item'):  # numpy scalar
                        return float(val.item())
                    return float(val)
                return float(default)

            # Get RSI divergence and ensure it's JSON serializable
            rsi_div = ind_dict.get('rsi_divergence', {}).get('divergence')
            if isinstance(rsi_div, (bool, type(True), type(False))):
                rsi_div = bool(rsi_div)
            elif hasattr(rsi_div, 'item'):  # numpy type
                rsi_div = rsi_div.item()
            
            compressed[tf] = {
                'rsi': {
                    'current': round(safe_get_last(ind_dict.get('rsi_14', pd.Series([0]))), 2),
                    'trend': self._get_trend(ind_dict.get('rsi_14', pd.Series([0])), 5),
                    'oversold': bool(safe_get_last(ind_dict.get('rsi_14', pd.Series([0]))) < 30),
                    'overbought': bool(safe_get_last(ind_dict.get('rsi_14', pd.Series([0]))) > 70),
                    'divergence': rsi_div
                },
                'macd': {
                    'macd': round(safe_get_last(ind_dict.get('macd', pd.Series([0]))), 2),
                    'signal': round(safe_get_last(ind_dict.get('macd_signal', pd.Series([0]))), 2),
                    'histogram': round(safe_get_last(ind_dict.get('macd_histogram', pd.Series([0]))), 2),
                    'trend': 'bullish' if safe_get_last(ind_dict.get('macd_histogram', pd.Series([0]))) > 0 else 'bearish'
                },
                'bollinger': {
                    'upper': round(safe_get_last(ind_dict.get('bb_upper', pd.Series([0]))), 2),
                    'middle': round(safe_get_last(ind_dict.get('bb_middle', pd.Series([0]))), 2),
                    'lower': round(safe_get_last(ind_dict.get('bb_lower', pd.Series([0]))), 2),
                    'width': round(safe_get_last(ind_dict.get('bb_width', pd.Series([0]))), 4),
                    'squeeze': bool(safe_get_last(ind_dict.get('bb_width', pd.Series([0]))) < 0.02)
                },
                'ema': {
                    'ema_9': round(safe_get_last(ind_dict.get('ema_9', pd.Series([0]))), 2),
                    'ema_21': round(safe_get_last(ind_dict.get('ema_21', pd.Series([0]))), 2),
                    'ema_50': round(safe_get_last(ind_dict.get('ema_50', pd.Series([0]))), 2),
                    'ema_200': round(safe_get_last(ind_dict.get('ema_200', pd.Series([0]))), 2),
                    'alignment': self._get_ema_alignment(ind_dict)
                },
                'atr': {
                    'current': round(safe_get_last(ind_dict.get('atr_14', pd.Series([0]))), 2),
                    'volatility': self._classify_volatility(ind_dict.get('atr_14', pd.Series([0])))
                },
                'adx': {
                    'value': round(safe_get_last(ind_dict.get('adx', pd.Series([0]))), 2),
                    'trend_strength': 'strong' if safe_get_last(ind_dict.get('adx', pd.Series([0]))) > 25 else 'weak'
                }
            }

        return compressed

    def _filter_by_timeframe(
        self, 
        data: Dict[str, Any], 
        active_timeframes: Optional[List[str]]
    ) -> Dict[str, Any]:
        """Filter results by active timeframes"""
        if not active_timeframes:
            return data
            
        filtered = {}
        for tf, content in data.items():
            if tf in active_timeframes or tf == '1d':  # Always keep 1d context
                filtered[tf] = content
        return filtered

    def _get_trend(self, series: pd.Series, periods: int = 5) -> str:
        """Determine trend direction"""
        if len(series) < periods:
            return 'neutral'

        recent = series.iloc[-periods:]
        if recent.iloc[-1] > recent.iloc[0]:
            return 'rising'
        elif recent.iloc[-1] < recent.iloc[0]:
            return 'falling'
        return 'neutral'

    def _get_ema_alignment(self, indicators: Dict) -> str:
        """Check EMA alignment"""
        try:
            def safe_get_last(series, default=0.0):
                """Safely get last value from pandas Series, converting to float"""
                if isinstance(series, pd.Series) and len(series) > 0:
                    val = series.iloc[-1]
                    # Handle numpy types that aren't JSON serializable
                    if hasattr(val, 'item'):  # numpy scalar
                        return float(val.item())
                    return float(val)
                return float(default)

            ema_9 = safe_get_last(indicators.get('ema_9', pd.Series([0])))
            ema_21 = safe_get_last(indicators.get('ema_21', pd.Series([0])))
            ema_50 = safe_get_last(indicators.get('ema_50', pd.Series([0])))
            ema_200 = safe_get_last(indicators.get('ema_200', pd.Series([0])))

            if ema_9 > ema_21 > ema_50 > ema_200:
                return 'bullish'
            elif ema_9 < ema_21 < ema_50 < ema_200:
                return 'bearish'
            return 'neutral'
        except Exception:
            return 'neutral'

    def _classify_volatility(self, atr_series: pd.Series) -> str:
        """Classify volatility level"""
        if len(atr_series) < 14:
            return 'unknown'

        def safe_get_last(series, default=0.0):
            """Safely get last value from pandas Series, converting to float"""
            if isinstance(series, pd.Series) and len(series) > 0:
                val = series.iloc[-1]
                # Handle numpy types that aren't JSON serializable
                if hasattr(val, 'item'):  # numpy scalar
                    return float(val.item())
                return float(val)
            return float(default)

        current = safe_get_last(atr_series)
        avg = float(atr_series.iloc[-14:].mean())

        if current > avg * 1.5:
            return 'high'
        elif current > avg:
            return 'moderate'
        return 'low'

    def _prepare_historical_context(
        self,
        trades: Optional[List[Dict]],
        regime: Optional[str]
    ) -> Dict[str, Any]:
        """Prepare historical performance context"""

        if not trades:
            return {
                'recent_trades': [],
                'performance_summary': None,
                'market_regime': regime or 'unknown'
            }

        # Summarize recent trades
        recent_trades = trades[-20:] if len(trades) > 20 else trades

        wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
        losses = sum(1 for t in recent_trades if t.get('pnl', 0) < 0)
        win_rate = wins / len(recent_trades) if recent_trades else 0

        avg_rr = sum(t.get('r_multiple', 0) for t in recent_trades) / len(recent_trades) if recent_trades else 0

        return {
            'recent_trades': [
                {
                    'setup': t.get('strategy_type'),
                    'outcome': 'win' if t.get('pnl', 0) > 0 else 'loss',
                    'r_multiple': round(t.get('r_multiple', 0), 2),
                    'confluences': t.get('confluences', [])
                }
                for t in recent_trades[-10:]  # Last 10 only
            ],
            'performance_summary': {
                'win_rate': round(win_rate, 3),
                'avg_rr': round(avg_rr, 2),
                'total_trades': len(recent_trades),
                'wins': wins,
                'losses': losses
            },
            'market_regime': regime or 'unknown',
            'lessons': self._extract_lessons(recent_trades)
        }

    def _extract_lessons(self, trades: List[Dict]) -> List[str]:
        """Extract key lessons from recent trades"""
        lessons = []

        if not trades:
            return lessons

        # Find patterns in winning trades
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        if winning_trades:
            # Most common winning setup
            setups = {}
            for t in winning_trades:
                setup = t.get('strategy_type', 'unknown')
                setups[setup] = setups.get(setup, 0) + 1

            if setups:
                best_setup = max(setups, key=setups.get)
                lessons.append(f"{best_setup} setups have {setups[best_setup]}/{len(winning_trades)} win rate")

        # Recent losing streak
        recent_5 = trades[-5:]
        if all(t.get('pnl', 0) < 0 for t in recent_5):
            lessons.append("Recent losing streak - exercise caution, reduce position sizing")

        return lessons[:3]  # Max 3 lessons

    def _build_task_instructions(self, active_timeframes: Optional[List[str]] = None) -> str:
        """Build specific task instructions for LLM"""
        
        # Default timeframes if none provided
        if not active_timeframes:
            active_timeframes = ['1d', '4h', '1h']
            
        # Build trend fields dynamically
        trend_fields = []
        for tf in active_timeframes:
            trend_fields.append(f'    "{tf}_trend": "bullish/bearish/neutral",')
        trend_section = "\n".join(trend_fields)

        return f"""
ANALYSIS TASK:

Analyze the provided multi-timeframe market data and produce a comprehensive trading analysis.

REQUIRED OUTPUT FORMAT (JSON):
{{
  "market_structure": {{
{trend_section}
    "alignment": "aligned/conflicting",
    "overall_bias": "bullish/bearish/neutral"
  }},

  "key_levels": {{
    "resistance": ["price1", "price2", "price3"],
    "support": ["price1", "price2", "price3"],
    "most_significant": {{
      "level": "price",
      "type": "resistance/support",
      "reason": "explanation"
    }}
  }},

  "smc_confluences": [
    {{
      "type": "order_block/fvg/bos",
      "timeframe": "4h",
      "description": "detailed description",
      "significance": "high/medium/low"
    }}
  ],

  "ict_setup": {{
    "killzone_active": true/false,
    "liquidity_sweeps": ["asian_low", "swing_high"],
    "order_flow_phase": "accumulation/manipulation/distribution",
    "ote_zone_status": "in_zone/above/below"
  }},

  "trade_opportunities": [
    {{
      "direction": "LONG/SHORT",
      "entry_zone": ["low", "high"],
      "confluence_count": "number",
      "key_factors": [
        "factor 1",
        "factor 2",
        "factor 3"
      ],
      "confidence": 0.0-1.0,
      "invalidation_level": "price",
      "type": "SMC Breakout/ICT Killzone/Order Block Bounce"
    }}
  ],

  "reasoning": "Detailed step-by-step analysis explaining your conclusions"
}}

ANALYSIS STEPS:
1. Assess multi-timeframe trend alignment
2. Identify key SMC structures (OBs, FVGs, BOS)
3. Evaluate ICT setup quality (killzone, sweeps, OTE)
4. Check technical indicator confluence
5. Synthesize into trade opportunities
6. Quantify confidence based on confluence count

CRITICAL REQUIREMENTS:
- Only suggest trades with 3+ confluences
- Confidence score must reflect actual confluence strength
- Be specific about invalidation conditions
- Explain reasoning clearly for each factor
"""

    def _estimate_tokens(self, context: Dict[str, Any]) -> int:
        """Estimate token count for context"""
        def json_serializer(obj):
            """Custom JSON serializer to handle non-serializable objects"""
            # Handle numpy types
            if hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            # Handle numpy booleans
            elif isinstance(obj, (bool, type(True), type(False))):
                return bool(obj)
            # Handle pandas types
            elif isinstance(obj, pd.Series):
                return obj.tolist()
            elif isinstance(obj, pd.DataFrame):
                return obj.to_dict('records')
            # Handle numpy types that might slip through
            elif hasattr(obj, 'tolist'):  # numpy array
                return obj.tolist()
            else:
                return str(obj)

        context_str = json.dumps(context, default=json_serializer)
        char_count = len(context_str)
        return int(char_count * self.TOKENS_PER_CHAR)

    def _optimize_context(
        self,
        context: Dict[str, Any],
        current_tokens: int
    ) -> Dict[str, Any]:
        """
        Optimize context to fit within token budget
        Uses priority-based pruning
        """
        target_reduction = current_tokens - self.MAX_TOKENS
        logger.info(f"Need to reduce by ~{target_reduction:,} tokens")

        # Priority-based pruning
        optimized = context.copy()

        # 1. Reduce candle data (lowest priority impact)
        if target_reduction > 0:
            optimized['current_data'] = self._reduce_candles(
                context['current_data'],
                reduction_factor=0.7
            )
            current_tokens = self._estimate_tokens(optimized)
            target_reduction = current_tokens - self.MAX_TOKENS
            logger.debug(f"After candle reduction: {current_tokens:,} tokens")

        # 2. Simplify historical context
        if target_reduction > 0:
            hist = optimized['historical_context']
            if 'recent_trades' in hist:
                hist['recent_trades'] = hist['recent_trades'][:5]  # Only 5 trades
            if 'lessons' in hist:
                hist['lessons'] = hist['lessons'][:2]
            current_tokens = self._estimate_tokens(optimized)
            target_reduction = current_tokens - self.MAX_TOKENS
            logger.debug(f"After history reduction: {current_tokens:,} tokens")

        # 3. Filter patterns to top 5
        if target_reduction > 0:
            if 'patterns' in optimized['patterns']:
                optimized['patterns']['patterns'] = optimized['patterns']['patterns'][:5]
            current_tokens = self._estimate_tokens(optimized)
            logger.debug(f"After pattern reduction: {current_tokens:,} tokens")

        return optimized

    def _reduce_candles(self, candles: Dict[str, List], reduction_factor: float = 0.7) -> Dict[str, List]:
        """Reduce number of candles per timeframe"""
        reduced = {}
        for tf, candle_list in candles.items():
            new_size = int(len(candle_list) * reduction_factor)
            reduced[tf] = candle_list[-new_size:] if new_size > 0 else candle_list
        return reduced

    def _generate_hash(self, context: Dict[str, Any]) -> str:
        """Generate hash for context caching"""
        # Hash based on key data points
        hash_data = {
            'symbol': context.get('_symbol'),
            'last_price': context['current_data'].get('5m', [{}])[-1].get('c') if context.get('current_data') else None,
            'smc_count': len(context.get('smc_analysis', {}).get('order_blocks', [])),
            'ict_killzone': context.get('ict_analysis', {}).get('killzone', {}).get('current_killzone')
        }

        hash_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(hash_str.encode()).hexdigest()

    def build_incremental_update(
        self,
        previous_context: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build incremental context update
        Only include what changed since last analysis
        """
        # Check if significant change occurred
        prev_hash = previous_context.get('_context_hash')
        new_hash = self._generate_hash(new_data)

        if prev_hash == new_hash:
            logger.info("No significant changes, reusing previous context")
            return previous_context

        logger.info("Building incremental update")

        # Build delta context
        delta_context = {
            'system_prompt': "Continue from previous analysis. Focus on changes.",
            'changes_since_last': self._identify_changes(previous_context, new_data),
            'updated_data': new_data,
            'previous_conclusion': previous_context.get('last_analysis_summary'),
            'task_instructions': "Analyze changes and update your assessment."
        }

        return delta_context

    def _identify_changes(self, prev: Dict, new: Dict) -> List[str]:
        """Identify what changed between contexts"""
        changes = []

        # Price change
        try:
            prev_price = prev['current_data'].get('5m', [{}])[-1].get('c', 0)
            new_price = new['current_data'].get('5m', [{}])[-1].get('c', 0)
            if prev_price and new_price:
                price_change = ((new_price - prev_price) / prev_price) * 100
                if abs(price_change) > 1:
                    changes.append(f"Price moved {price_change:.2f}%")
        except Exception:
            pass

        # New SMC structures
        prev_ob_count = len(prev.get('smc_analysis', {}).get('order_blocks', []))
        new_ob_count = len(new.get('smc_analysis', {}).get('order_blocks', []))
        if new_ob_count > prev_ob_count:
            changes.append(f"{new_ob_count - prev_ob_count} new Order Blocks detected")

        # Killzone change
        prev_kz = prev.get('ict_analysis', {}).get('killzone', {}).get('current_killzone')
        new_kz = new.get('ict_analysis', {}).get('killzone', {}).get('current_killzone')
        if prev_kz != new_kz:
            changes.append(f"Killzone changed: {prev_kz} → {new_kz}")

        return changes[:5]  # Top 5 changes