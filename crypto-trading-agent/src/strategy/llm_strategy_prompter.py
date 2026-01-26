"""
LLM Strategy Prompt System
Creates optimized prompts for strategy generation
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()

class LLMStrategyPrompter:
    """
    Builds optimized prompts for strategy generation LLM
    Uses GPT-4o for faster, cheaper structured output
    """

    MAX_TOKENS = 100000  # Leave room for response

    def __init__(self):
        self.prompt_cache = {}

    def build_strategy_prompt(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float,
        atr: float,
        account_balance: float,
        historical_performance: Optional[Dict[str, Any]] = None,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build complete prompt for strategy generation

        Returns:
            {
                'system_prompt': str,
                'user_message': str,
                'output_schema': dict,
                'estimated_tokens': int
            }
        """
        try:
            plog.info(f"Building strategy prompt for {symbol}", agent="strategy", phase="strategy_generation")

            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Prepare compressed analysis
            compressed_analysis = self._compress_analysis(analysis)

            # Build user message
            user_message = self._build_user_message(
                symbol=symbol,
                analysis=compressed_analysis,
                current_price=current_price,
                atr=atr,
                account_balance=account_balance,
                historical_performance=historical_performance,
                entry_confirmation=entry_confirmation
            )

            # Define output schema
            output_schema = self._build_output_schema()

            # Estimate tokens
            estimated_tokens = self._estimate_tokens({
                'system': system_prompt,
                'user': user_message,
                'schema': output_schema
            })

            plog.info(f"Prompt built: ~{estimated_tokens:,} tokens", agent="strategy", phase="strategy_generation")

            return {
                'system_prompt': system_prompt,
                'user_message': user_message,
                'output_schema': output_schema,
                'estimated_tokens': estimated_tokens
            }

        except KeyError as ke:
            # Safely extract the missing key name
            try:
                missing_key = ke.args[0] if ke.args else str(ke)
            except Exception:
                missing_key = repr(ke)
            plog.error(f"KeyError building prompt - missing key: {missing_key}", exception=ke, agent="strategy", phase="strategy_generation")
            plog.error(f"Analysis keys available: {list(analysis.keys()) if isinstance(analysis, dict) else 'Not a dict'}", agent="strategy", phase="strategy_generation")
            raise
        except Exception as e:
            plog.error(f"Error building prompt: {type(e).__name__}: {str(e)}", exception=e, agent="strategy", phase="strategy_generation")
            raise

    def _build_system_prompt(self) -> str:
        """Build system prompt defining LLM role and rules"""

        return """You are an expert cryptocurrency futures trader specializing in generating precise trade setups based on Smart Money Concepts (SMC) and Inner Circle Trader (ICT) methodology.

Your role is to:
1. Analyze provided market analysis data
2. Generate a structured trade setup with exact entry, stop-loss, and take-profit levels
3. Calculate optimal position sizing based on risk parameters
4. Provide detailed reasoning for every decision
5. Assign accurate confidence scores based on confluence strength

CRITICAL RULES:
- Only generate setups with 3+ confluences
- Minimum risk-reward ratio: 2:1
- Maximum risk per trade: 2% of account
- Confidence score must reflect actual setup quality (0.65-0.95)
- All prices must be realistic and achievable
- Stop-loss must invalidate the setup (below OB, beyond structure)
- Take-profits must align with supply/demand zones or FVG fills

DECISION FRAMEWORK:
Step 1: Verify confluence count (need 3+)
Step 2: Determine optimal entry zone (OB, FVG, OTE)
Step 3: Calculate stop-loss at invalidation level
Step 4: Generate 3-level take-profits (1:1.5, 1:2.5, 1:4+)
Step 5: Calculate risk-reward ratio (must be ≥2.0)
Step 6: Assess confidence based on confluence quality
Step 7: Build invalidation conditions

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON matching the provided schema
- If no valid setup exists (< 3 confluences or < 2:1 RR), return: {"trade_setup": null, "reason": "..."}
- Include detailed reasoning for each level chosen
- Be conservative with confidence scores (0.75 is good, 0.85+ is excellent)

Remember: Quality over quantity. It's better to skip a trade than force a low-quality setup."""

    def _compress_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Compress analysis to fit token budget"""

        # Defensive check
        if not isinstance(analysis, dict):
            plog.warning(f"Analysis is not a dict, type: {type(analysis)}", agent="strategy", phase="strategy_generation")
            analysis = {}
        
        # Safely extract key_levels
        key_levels = analysis.get('key_levels', {})
        if not isinstance(key_levels, dict):
            key_levels = {}
        
        resistance = key_levels.get('resistance', [])
        support = key_levels.get('support', [])
        if not isinstance(resistance, list):
            resistance = []
        if not isinstance(support, list):
            support = []

        compressed = {
            'market_structure': analysis.get('market_structure', {}),
            'key_levels': {
                'resistance': resistance[:5],
                'support': support[:5]
            },
            'smc_summary': self._compress_smc(analysis.get('smc_analysis', {})),
            'ict_summary': self._compress_ict(analysis.get('ict_analysis', {})),
            'patterns': self._compress_patterns(analysis.get('patterns', {})),
            'confidence': analysis.get('overall_confidence', 0.0)
        }

        return compressed

    def _compress_smc(self, smc_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compress SMC data to essentials"""

        computational = smc_data.get('computational', {})

        # Top 3 order blocks only
        obs = computational.get('order_blocks', [])
        if isinstance(obs, list):
            obs = obs[:3]

        # Unfilled FVGs only
        fvgs = computational.get('fair_value_gaps', [])
        if isinstance(fvgs, list):
            fvgs = [
                fvg for fvg in fvgs
                if not fvg.get('filled', False)
            ][:3]

        # Break of structure - handle safely
        bos = computational.get('break_of_structure', [])
        if isinstance(bos, list) and len(bos) >= 2:
            bos = bos[-2:]
        elif isinstance(bos, list):
            bos = bos  # Take all if less than 2
        else:
            bos = []

        # Liquidity zones
        liq_zones = computational.get('liquidity_zones', [])
        if isinstance(liq_zones, list):
            liq_zones = liq_zones[:3]

        return {
            'order_blocks': obs,
            'fair_value_gaps': fvgs,
            'break_of_structure': bos,
            'liquidity_zones': liq_zones
        }

    def _compress_ict(self, ict_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compress ICT data to essentials"""

        computational = ict_data.get('computational', {})

        # Handle liquidity sweeps safely
        sweeps = computational.get('liquidity_sweeps', [])
        if isinstance(sweeps, list):
            sweeps = sweeps[:3]

        return {
            'killzone': computational.get('killzone', {}),
            'liquidity_sweeps': sweeps,
            'order_flow': computational.get('order_flow', {}),
            'ote_zones': computational.get('ote_zones', {})
        }

    def _compress_patterns(self, patterns: Dict[str, Any]) -> Dict[str, Any]:
        """Compress pattern data"""

        pattern_list = patterns.get('patterns', [])[:3]  # Top 3 only

        return {
            'patterns': pattern_list,
            'most_significant': patterns.get('most_recent')
        }

    def _build_user_message(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float,
        atr: float,
        account_balance: float,
        historical_performance: Optional[Dict[str, Any]],
        entry_confirmation: Optional[Dict[str, Any]]
    ) -> str:
        """Build user message with analysis data"""

        # Build context sections
        sections = []

        # Header
        sections.append(f"# Trade Setup Generation Request\n")
        sections.append(f"**Symbol:** {symbol}")
        sections.append(f"**Current Price:** ${current_price:,.2f}")
        sections.append(f"**ATR (14):** ${atr:,.2f}")
        sections.append(f"**Account Balance:** ${account_balance:,.2f}")
        sections.append(f"**Max Risk:** 2% = ${account_balance * 0.02:,.2f}\n")

        # Market Structure
        sections.append("## Market Structure")
        try:
            sections.append(f"```json\n{json.dumps(analysis.get('market_structure', {}), indent=2, default=str)}\n```\n")
        except:
            sections.append(f"```json\n{str(analysis.get('market_structure', {}))}\n```\n")

        # Key Levels
        sections.append("## Key Levels")
        try:
            sections.append(f"```json\n{json.dumps(analysis.get('key_levels', {}), indent=2, default=str)}\n```\n")
        except:
            sections.append(f"```json\n{str(analysis.get('key_levels', {}))}\n```\n")

        # SMC Analysis
        sections.append("## Smart Money Concepts (SMC)")
        try:
            sections.append(f"```json\n{json.dumps(analysis.get('smc_summary', {}), indent=2, default=str)}\n```\n")
        except:
            sections.append(f"```json\n{str(analysis.get('smc_summary', {}))}\n```\n")

        # ICT Analysis
        sections.append("## ICT Methodology")
        try:
            sections.append(f"```json\n{json.dumps(analysis.get('ict_summary', {}), indent=2, default=str)}\n```\n")
        except:
            sections.append(f"```json\n{str(analysis.get('ict_summary', {}))}\n```\n")

        # Patterns
        if analysis.get('patterns'):
            sections.append("## Chart Patterns")
            try:
                sections.append(f"```json\n{json.dumps(analysis.get('patterns', {}), indent=2, default=str)}\n```\n")
            except:
                sections.append(f"```json\n{str(analysis.get('patterns', {}))}\n```\n")

        # Entry Confirmation Analysis
        if entry_confirmation:
            sections.append("## Entry Confirmation Analysis")
            status = "✅ CONFIRMED" if entry_confirmation.get('confirmed', False) else "⏳ WAITING"
            sections.append(f"Status: {status}")

            if entry_confirmation.get('confirmed', False):
                pattern = entry_confirmation.get('candle_pattern', {})
                if pattern:
                    sections.append(f"Pattern Detected: {pattern.get('pattern_type', 'Unknown')}")
                    sections.append(f"Pattern Strength: {pattern.get('strength', 0):.2f}")
                    sections.append(f"Description: {pattern.get('description', '')}")

                sections.append(f"Entry Trigger: {entry_confirmation.get('price_action_signal', 'Unknown')}")
                sections.append(f"Confidence: {entry_confirmation.get('confidence', 0):.2f}")
                sections.append("Recommended Entry: Enter at market on confirmation candle close")
            else:
                sections.append(f"Waiting For: {entry_confirmation.get('price_action_signal', 'Pattern confirmation')}")
                sections.append("Setup is valid but entry not yet triggered")

            reasoning = entry_confirmation.get('reasoning', [])
            if reasoning:
                sections.append("Analysis Reasoning:")
                for reason in reasoning:
                    sections.append(f"  • {reason}")
            sections.append("")

        # Historical Performance
        if historical_performance:
            sections.append("## Historical Performance Context")
            sections.append(f"Similar setups have a {historical_performance.get('win_rate', 0) * 100:.1f}% win rate")
            sections.append(f"Average RR: {historical_performance.get('avg_rr', 0):.2f}\n")

        # Task
        sections.append("## Your Task")
        sections.append("""
Generate a precise trade setup based on the analysis above. Follow these steps:

1. **Verify Confluences**: Count all confirming factors (OB, FVG, sweeps, indicators, etc.)
2. **Determine Direction**: LONG or SHORT based on confluence
3. **Calculate Entry Zone**: Use OB/FVG/OTE for optimal entry
4. **Set Stop-Loss**: Place at invalidation level (below/above structure)
5. **Generate Take-Profits**: 3 levels at 1:1.5, 1:2.5, 1:4+ RR
6. **Calculate Position Size**: Based on 2% risk and entry-to-SL distance
7. **Assess Confidence**: Score 0-1 based on confluence quality
8. **Explain Reasoning**: Detail why each level was chosen

If the setup doesn't meet requirements (< 3 confluences or < 2:1 RR), return null with explanation.
""")

        return "\n".join(sections)

    def _build_output_schema(self) -> Dict[str, Any]:
        """Define expected output schema"""

        return {
            "type": "object",
            "properties": {
                "trade_setup": {
                    "type": ["object", "null"],
                    "properties": {
                        "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
                        "strategy_type": {"type": "string", "enum": ["SCALP", "DAY_TRADE", "SWING"]},
                        "entry_price": {"type": "number"},
                        "entry_zone_low": {"type": "number"},
                        "entry_zone_high": {"type": "number"},
                        "stop_loss": {"type": "number"},
                        "take_profit_levels": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "level": {"type": "integer"},
                                    "price": {"type": "number"},
                                    "size": {"type": "number"}
                                }
                            },
                            "minItems": 3,
                            "maxItems": 3
                        },
                        "position_size": {"type": "number"},
                        "risk_amount": {"type": "number"},
                        "risk_reward_ratio": {"type": "number", "minimum": 2.0},
                        "confidence_score": {"type": "number", "minimum": 0.65, "maximum": 0.95},
                        "confluences": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 3
                        },
                        "invalidation_conditions": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "reasoning": {
                            "type": "object",
                            "properties": {
                                "entry_rationale": {"type": "string"},
                                "stop_loss_rationale": {"type": "string"},
                                "take_profit_rationale": {"type": "string"},
                                "confidence_rationale": {"type": "string"}
                            }
                        }
                    },
                    "required": [
                        "direction", "entry_price", "stop_loss",
                        "take_profit_levels", "position_size",
                        "risk_reward_ratio", "confidence_score",
                        "confluences", "reasoning"
                    ]
                },
                "reason": {"type": ["string", "null"]}
            },
            "required": ["trade_setup"]
        }

    def _estimate_tokens(self, prompt_data: Dict[str, Any]) -> int:
        """Estimate token count"""

        # Use a custom JSON encoder to handle non-serializable objects
        def safe_serialize(obj):
            if isinstance(obj, (int, float, str, bool, type(None))):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [safe_serialize(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: safe_serialize(value) for key, value in obj.items()}
            else:
                return str(obj)  # Convert everything else to string

        safe_data = safe_serialize(prompt_data)
        total_text = json.dumps(safe_data)
        char_count = len(total_text)

        # GPT-4 approximation: ~4 chars per token
        estimated_tokens = char_count // 4

        return estimated_tokens