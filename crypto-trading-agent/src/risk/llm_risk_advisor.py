"""
LLM Risk Advisor
LLM-based advisor for complex risk edge cases that deterministic rules can't handle
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import asyncio

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


@dataclass
class LLMRiskAdvice:
    """Result from LLM risk analysis"""
    recommendation: str  # 'APPROVE', 'REJECT', 'ADJUST'
    reasoning: str
    suggested_adjustments: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 0-1
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'recommendation': self.recommendation,
            'reasoning': self.reasoning,
            'suggested_adjustments': self.suggested_adjustments,
            'confidence': round(self.confidence, 2),
            'warnings': self.warnings
        }


class LLMRiskAdvisor:
    """
    LLM-based risk advisor for complex edge cases
    
    Used for <20% of validations when deterministic rules are insufficient:
    - Correlated positions with different setups
    - Recent losing streak - should we reduce size?
    - High volatility events - should we pause?
    - Market regime shifts - adjust risk?
    - Complex multi-factor scenarios
    
    Model: GPT-4o-mini (cost-effective, fast)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        enabled: bool = True
    ):
        self.enabled = enabled and AsyncOpenAI is not None
        self.model = model
        
        if self.enabled and api_key:
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            self.client = None
            if not AsyncOpenAI:
                plog.warning(
                    "OpenAI library not installed - LLM advisor disabled",
                    agent="risk_agent",
                    phase="initialization"
                )
        
        # Usage tracking
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.last_call_time: Optional[datetime] = None
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        plog.info(
            f"LLM risk advisor initialized | enabled={self.enabled} | model={model}",
            agent="risk_agent",
            phase="initialization"
        )
    
    async def analyze_edge_case(
        self,
        trade_setup: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        edge_case_context: str
    ) -> Optional[LLMRiskAdvice]:
        """
        Analyze complex edge case using LLM
        
        Args:
            trade_setup: Proposed trade details
            portfolio_state: Current portfolio state
            edge_case_context: Description of why this is an edge case
            
        Returns:
            LLMRiskAdvice or None if LLM unavailable
        """
        if not self.enabled or not self.client:
            plog.warning(
                "LLM advisor not available - falling back to deterministic",
                agent="risk_agent",
                phase="llm_analysis"
            )
            return None
        
        async with self._lock:
            self.total_calls += 1
            self.last_call_time = datetime.now()
            
            plog.info(
                f"🤖 Consulting LLM for edge case: {edge_case_context[:50]}...",
                agent="risk_agent",
                phase="llm_analysis"
            )
            
            try:
                # Build prompt
                prompt = self._build_risk_prompt(
                    trade_setup, portfolio_state, edge_case_context
                )
                
                # Call LLM
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": self._get_system_prompt()
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3,  # Low temperature for consistent risk analysis
                    max_tokens=500,
                    response_format={"type": "json_object"}
                )
                
                # Track usage
                usage = response.usage
                self.total_tokens += usage.total_tokens
                
                # Estimate cost (GPT-4o-mini: $0.15/1M input, $0.60/1M output)
                input_cost = (usage.prompt_tokens / 1_000_000) * 0.15
                output_cost = (usage.completion_tokens / 1_000_000) * 0.60
                call_cost = input_cost + output_cost
                self.total_cost += call_cost
                
                # Parse response
                advice = self._parse_llm_response(
                    response.choices[0].message.content
                )
                
                plog.info(
                    f"✅ LLM advice: {advice.recommendation} | "
                    f"confidence={advice.confidence:.2f} | "
                    f"cost=${call_cost:.4f}",
                    agent="risk_agent",
                    phase="llm_analysis"
                )
                
                return advice
                
            except Exception as e:
                plog.error(
                    f"LLM analysis failed: {e}",
                    exception=e,
                    agent="risk_agent",
                    phase="llm_analysis"
                )
                return None
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return """You are a professional risk management advisor for a crypto trading system.
Your role is to analyze complex edge cases that deterministic rules cannot handle.

You must respond in JSON format with:
{
    "recommendation": "APPROVE" | "REJECT" | "ADJUST",
    "reasoning": "detailed explanation",
    "suggested_adjustments": {
        "position_size_multiplier": 0.5-1.0,
        "additional_checks": ["list of recommendations"]
    },
    "confidence": 0.0-1.0,
    "warnings": ["list of warnings"]
}

Prioritize capital preservation. When in doubt, recommend REJECT or reduce position size.
Consider:
- Correlation risk
- Recent performance (losing streaks)
- Market volatility
- Portfolio heat
- Drawdown levels

Be conservative but not overly restrictive. The goal is to prevent catastrophic losses while allowing profitable trades."""
    
    def _build_risk_prompt(
        self,
        trade_setup: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        edge_case_context: str
    ) -> str:
        """Build detailed prompt for LLM"""
        
        prompt = f"""Analyze this edge case trade setup:

**Edge Case Context:**
{edge_case_context}

**Proposed Trade:**
- Symbol: {trade_setup.get('symbol')}
- Direction: {trade_setup.get('direction')}
- Entry: ${trade_setup.get('entry_price', 0):.2f}
- Stop Loss: ${trade_setup.get('stop_loss', 0):.2f}
- Take Profit: {trade_setup.get('take_profit_levels', [])}
- Position Size: {trade_setup.get('position_size', 0):.6f}
- Risk Amount: ${trade_setup.get('risk_amount', 0):.2f}
- Confidence: {trade_setup.get('confidence_score', 0):.2f}

**Current Portfolio State:**
- Total Equity: ${portfolio_state.get('total_equity', 0):.2f}
- Account Balance: ${portfolio_state.get('account_balance', 0):.2f}
- Portfolio Heat: {portfolio_state.get('portfolio_heat', 0):.1f}%
- Open Positions: {portfolio_state.get('open_positions', 0)}
- Daily P&L: ${portfolio_state.get('daily_pnl', 0):.2f}
- Current Drawdown: {portfolio_state.get('current_drawdown', 0):.1f}%
- Loss Streak: {portfolio_state.get('loss_streak', 0)}
- Win Streak: {portfolio_state.get('win_streak', 0)}

**Risk Parameters:**
- Max Risk per Trade: 2%
- Max Portfolio Heat: 6%
- Max Daily Loss: 5%
- Max Drawdown: 20%

Should this trade be approved, rejected, or adjusted? Provide detailed reasoning."""
        
        return prompt
    
    def _parse_llm_response(self, response_text: str) -> LLMRiskAdvice:
        """Parse LLM JSON response into LLMRiskAdvice"""
        try:
            data = json.loads(response_text)
            
            return LLMRiskAdvice(
                recommendation=data.get('recommendation', 'REJECT').upper(),
                reasoning=data.get('reasoning', 'No reasoning provided'),
                suggested_adjustments=data.get('suggested_adjustments', {}),
                confidence=float(data.get('confidence', 0.5)),
                warnings=data.get('warnings', [])
            )
            
        except json.JSONDecodeError as e:
            plog.error(
                f"Failed to parse LLM response: {e}",
                agent="risk_agent",
                phase="llm_analysis"
            )
            
            # Fallback: conservative rejection
            return LLMRiskAdvice(
                recommendation='REJECT',
                reasoning='Failed to parse LLM response - defaulting to rejection',
                confidence=0.0,
                warnings=['LLM response parsing failed']
            )
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics"""
        async with self._lock:
            avg_tokens = (
                self.total_tokens / self.total_calls
                if self.total_calls > 0
                else 0
            )
            
            avg_cost = (
                self.total_cost / self.total_calls
                if self.total_calls > 0
                else 0
            )
            
            return {
                'enabled': self.enabled,
                'model': self.model,
                'total_calls': self.total_calls,
                'total_tokens': self.total_tokens,
                'total_cost': round(self.total_cost, 4),
                'avg_tokens_per_call': round(avg_tokens, 0),
                'avg_cost_per_call': round(avg_cost, 4),
                'last_call': (
                    self.last_call_time.isoformat()
                    if self.last_call_time
                    else None
                )
            }
    
    async def reset_usage_stats(self):
        """Reset usage statistics"""
        async with self._lock:
            self.total_calls = 0
            self.total_tokens = 0
            self.total_cost = 0.0
            self.last_call_time = None
            
            plog.info(
                "LLM usage statistics reset",
                agent="risk_agent",
                phase="maintenance"
            )
    
    def is_available(self) -> bool:
        """Check if LLM advisor is available"""
        return self.enabled and self.client is not None
