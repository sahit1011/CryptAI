"""
Professional Quant Trader Psychology Module
Implements decision-making framework of professional quantitative traders
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger

from playground.evaluation.regime_detector import MarketRegime


@dataclass
class TraderDecision:
    """Decision output from quant trader psychology"""
    action: str  # 'LONG', 'SHORT', 'WAIT', 'REDUCE'
    confidence: float  # 0.0 to 1.0
    reasoning: List[str]  # Step-by-step reasoning
    risk_assessment: str  # 'LOW', 'MEDIUM', 'HIGH'
    position_size_multiplier: float  # 0.0 to 1.0 (1.0 = full size)
    required_confluences: int  # Minimum confluences needed
    stop_loss_buffer: float  # ATR multiplier for SL
    take_profit_ratio: float  # R:R ratio target


class QuantTraderPsychology:
    """
    Professional Quant Trader Decision Framework
    
    Core Principles:
    1. **Top-Down Analysis**: HTF bias → MTF setup → LTF entry
    2. **Risk-First Mindset**: "Where am I wrong?" before "Where's the opportunity?"
    3. **Confluence-Based**: Minimum 3 confluences for any trade
    4. **Regime-Adaptive**: Adjust strategy based on market conditions
    5. **Probability Thinking**: Focus on edge, not individual trades
    6. **Position Sizing**: Scale based on confidence and regime
    
    Professional Trader Questions:
    - What is the market regime? (Trending/Ranging/Volatile)
    - What is the HTF bias? (Bullish/Bearish/Neutral)
    - Where are the key levels? (Support/Resistance/Order Blocks)
    - What is the setup? (Pullback/Breakout/Reversal)
    - Where am I wrong? (Stop loss placement)
    - What is my edge? (Confluence count, R:R ratio)
    - How much should I risk? (Position sizing based on confidence)
    """
    
    def __init__(self):
        """Initialize quant trader psychology module"""
        self.decision_history = []
        logger.info("QuantTraderPsychology initialized")
    
    def make_decision(
        self,
        regime: MarketRegime,
        htf_bias: str,  # 'BULLISH', 'BEARISH', 'NEUTRAL'
        mtf_setup: Optional[Dict[str, Any]] = None,
        ltf_entry: Optional[Dict[str, Any]] = None,
        confluence_count: int = 0,
        risk_reward_ratio: float = 0.0
    ) -> TraderDecision:
        """
        Make trading decision using professional quant trader framework
        
        Args:
            regime: Market regime
            htf_bias: Higher timeframe bias
            mtf_setup: Medium timeframe setup details
            ltf_entry: Lower timeframe entry details
            confluence_count: Number of confluences
            risk_reward_ratio: Risk-reward ratio
        
        Returns:
            TraderDecision with action and reasoning
        """
        reasoning = []
        
        # Step 1: Regime Assessment
        regime_decision = self._assess_regime(regime)
        reasoning.extend(regime_decision['reasoning'])
        
        # Step 2: HTF Bias Check
        bias_decision = self._assess_htf_bias(htf_bias, regime)
        reasoning.extend(bias_decision['reasoning'])
        
        # Step 3: Setup Quality
        setup_decision = self._assess_setup_quality(
            mtf_setup, ltf_entry, confluence_count, risk_reward_ratio
        )
        reasoning.extend(setup_decision['reasoning'])
        
        # Step 4: Risk Assessment
        risk_decision = self._assess_risk(regime, confluence_count, risk_reward_ratio)
        reasoning.extend(risk_decision['reasoning'])
        
        # Step 5: Final Decision
        final_decision = self._synthesize_decision(
            regime_decision,
            bias_decision,
            setup_decision,
            risk_decision,
            regime
        )
        
        decision = TraderDecision(
            action=final_decision['action'],
            confidence=final_decision['confidence'],
            reasoning=reasoning,
            risk_assessment=risk_decision['level'],
            position_size_multiplier=final_decision['position_size'],
            required_confluences=regime_decision['required_confluences'],
            stop_loss_buffer=risk_decision['sl_buffer'],
            take_profit_ratio=risk_decision['tp_ratio']
        )
        
        # Log decision
        logger.info(
            f"Trader Decision: {decision.action} "
            f"(confidence: {decision.confidence:.2%}, "
            f"risk: {decision.risk_assessment}, "
            f"size: {decision.position_size_multiplier:.2f}x)"
        )
        
        # Store in history
        self.decision_history.append(decision)
        
        return decision
    
    def _assess_regime(self, regime: MarketRegime) -> Dict[str, Any]:
        """Assess market regime and set parameters"""
        reasoning = []
        
        reasoning.append(f"📊 Market Regime: {regime.regime} (confidence: {regime.confidence:.2%})")
        reasoning.append(f"   Trend Strength: {regime.trend_strength:.2%}, Volatility: {regime.volatility_level:.2%}")
        
        # Set regime-specific parameters
        if regime.regime == 'TRENDING_BULLISH' or regime.regime == 'TRENDING_BEARISH':
            required_confluences = 3
            reasoning.append("   ✓ Trending market: Focus on pullbacks to demand/supply zones")
            reasoning.append("   ✓ Required confluences: 3 (trend provides strong directional bias)")
        
        elif regime.regime == 'RANGING':
            required_confluences = 4
            reasoning.append("   ⚠️ Ranging market: Trade range boundaries with tight stops")
            reasoning.append("   ⚠️ Required confluences: 4 (need more confirmation in ranges)")
        
        elif regime.regime == 'VOLATILE':
            required_confluences = 5
            reasoning.append("   🔴 High volatility: Reduce size or wait for clarity")
            reasoning.append("   🔴 Required confluences: 5 (very high bar in volatile conditions)")
        
        else:  # UNKNOWN
            required_confluences = 4
            reasoning.append("   ⚠️ Unknown regime: Use conservative approach")
            reasoning.append("   ⚠️ Required confluences: 4 (higher bar for unclear conditions)")
        
        return {
            'regime': regime.regime,
            'required_confluences': required_confluences,
            'reasoning': reasoning
        }
    
    def _assess_htf_bias(self, htf_bias: str, regime: MarketRegime) -> Dict[str, Any]:
        """Assess higher timeframe bias"""
        reasoning = []
        
        reasoning.append(f"🎯 HTF Bias: {htf_bias}")
        
        # Check alignment with regime
        if regime.regime == 'TRENDING_BULLISH' and htf_bias == 'BULLISH':
            reasoning.append("   ✓ HTF bias aligned with trending regime - strong setup")
            bias_quality = 'STRONG'
        
        elif regime.regime == 'TRENDING_BEARISH' and htf_bias == 'BEARISH':
            reasoning.append("   ✓ HTF bias aligned with trending regime - strong setup")
            bias_quality = 'STRONG'
        
        elif htf_bias == 'NEUTRAL':
            reasoning.append("   ⚠️ Neutral HTF bias - wait for clear direction")
            bias_quality = 'WEAK'
        
        else:
            reasoning.append("   🔴 HTF bias conflicts with regime - avoid counter-trend trades")
            bias_quality = 'CONFLICTING'
        
        return {
            'bias': htf_bias,
            'quality': bias_quality,
            'reasoning': reasoning
        }
    
    def _assess_setup_quality(
        self,
        mtf_setup: Optional[Dict[str, Any]],
        ltf_entry: Optional[Dict[str, Any]],
        confluence_count: int,
        risk_reward_ratio: float
    ) -> Dict[str, Any]:
        """Assess setup quality"""
        reasoning = []
        
        reasoning.append(f"🔍 Setup Quality Assessment:")
        reasoning.append(f"   Confluences: {confluence_count}")
        reasoning.append(f"   Risk:Reward: {risk_reward_ratio:.2f}:1")
        
        # Confluence check
        if confluence_count >= 5:
            reasoning.append("   ✓ Excellent confluence (5+) - high probability setup")
            confluence_quality = 'EXCELLENT'
        elif confluence_count >= 3:
            reasoning.append("   ✓ Good confluence (3-4) - acceptable setup")
            confluence_quality = 'GOOD'
        else:
            reasoning.append("   🔴 Insufficient confluence (<3) - skip this setup")
            confluence_quality = 'POOR'
        
        # R:R check
        if risk_reward_ratio >= 3.0:
            reasoning.append("   ✓ Excellent R:R (3:1+) - asymmetric risk/reward")
            rr_quality = 'EXCELLENT'
        elif risk_reward_ratio >= 2.0:
            reasoning.append("   ✓ Good R:R (2:1+) - acceptable risk/reward")
            rr_quality = 'GOOD'
        else:
            reasoning.append("   🔴 Poor R:R (<2:1) - skip this setup")
            rr_quality = 'POOR'
        
        # Overall setup quality
        if confluence_quality in ['EXCELLENT', 'GOOD'] and rr_quality in ['EXCELLENT', 'GOOD']:
            setup_quality = 'GOOD'
        else:
            setup_quality = 'POOR'
        
        return {
            'quality': setup_quality,
            'confluence_quality': confluence_quality,
            'rr_quality': rr_quality,
            'reasoning': reasoning
        }
    
    def _assess_risk(
        self,
        regime: MarketRegime,
        confluence_count: int,
        risk_reward_ratio: float
    ) -> Dict[str, Any]:
        """Assess risk level and set parameters"""
        reasoning = []
        
        reasoning.append(f"⚖️ Risk Assessment:")
        
        # Base risk on regime
        if regime.regime == 'VOLATILE':
            risk_level = 'HIGH'
            sl_buffer = 2.0  # 2x ATR for stop loss
            tp_ratio = 3.0   # 3:1 R:R minimum
            reasoning.append("   🔴 High risk due to volatility - use wider stops")
        
        elif regime.regime == 'RANGING':
            risk_level = 'MEDIUM'
            sl_buffer = 1.0  # 1x ATR for stop loss
            tp_ratio = 2.0   # 2:1 R:R minimum
            reasoning.append("   ⚠️ Medium risk in range - use tight stops")
        
        else:  # TRENDING
            risk_level = 'LOW'
            sl_buffer = 1.5  # 1.5x ATR for stop loss
            tp_ratio = 2.5   # 2.5:1 R:R minimum
            reasoning.append("   ✓ Low risk in trend - trend is your friend")
        
        # Adjust based on confluence
        if confluence_count >= 5:
            reasoning.append(f"   ✓ High confluence ({confluence_count}) reduces risk")
        elif confluence_count < 3:
            risk_level = 'HIGH'
            reasoning.append(f"   🔴 Low confluence ({confluence_count}) increases risk")
        
        return {
            'level': risk_level,
            'sl_buffer': sl_buffer,
            'tp_ratio': tp_ratio,
            'reasoning': reasoning
        }
    
    def _synthesize_decision(
        self,
        regime_decision: Dict[str, Any],
        bias_decision: Dict[str, Any],
        setup_decision: Dict[str, Any],
        risk_decision: Dict[str, Any],
        regime: MarketRegime
    ) -> Dict[str, Any]:
        """Synthesize final trading decision"""
        
        # Decision logic: All checks must pass
        
        # Check 1: Regime must not be VOLATILE with low confidence
        if regime.regime == 'VOLATILE' and regime.volatility_level > 0.8:
            return {
                'action': 'WAIT',
                'confidence': 0.0,
                'position_size': 0.0
            }
        
        # Check 2: HTF bias must not be conflicting
        if bias_decision['quality'] == 'CONFLICTING':
            return {
                'action': 'WAIT',
                'confidence': 0.0,
                'position_size': 0.0
            }
        
        # Check 3: Setup quality must be GOOD
        if setup_decision['quality'] == 'POOR':
            return {
                'action': 'WAIT',
                'confidence': 0.0,
                'position_size': 0.0
            }
        
        # All checks passed - determine action
        if bias_decision['bias'] == 'BULLISH':
            action = 'LONG'
        elif bias_decision['bias'] == 'BEARISH':
            action = 'SHORT'
        else:
            action = 'WAIT'
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            regime,
            bias_decision,
            setup_decision,
            risk_decision
        )
        
        # Calculate position size
        position_size = self._calculate_position_size(
            confidence,
            risk_decision['level'],
            regime
        )
        
        return {
            'action': action,
            'confidence': confidence,
            'position_size': position_size
        }
    
    def _calculate_confidence(
        self,
        regime: MarketRegime,
        bias_decision: Dict[str, Any],
        setup_decision: Dict[str, Any],
        risk_decision: Dict[str, Any]
    ) -> float:
        """Calculate overall confidence score"""
        
        # Start with regime confidence
        confidence = regime.confidence
        
        # Boost for strong bias
        if bias_decision['quality'] == 'STRONG':
            confidence *= 1.1
        
        # Boost for excellent setup
        if setup_decision['confluence_quality'] == 'EXCELLENT':
            confidence *= 1.15
        
        if setup_decision['rr_quality'] == 'EXCELLENT':
            confidence *= 1.1
        
        # Reduce for high risk
        if risk_decision['level'] == 'HIGH':
            confidence *= 0.8
        elif risk_decision['level'] == 'MEDIUM':
            confidence *= 0.9
        
        # Cap at 0.95 (never 100% confident)
        return min(confidence, 0.95)
    
    def _calculate_position_size(
        self,
        confidence: float,
        risk_level: str,
        regime: MarketRegime
    ) -> float:
        """Calculate position size multiplier"""
        
        # Base size on confidence
        if confidence >= 0.85:
            size = 1.0  # Full size
        elif confidence >= 0.75:
            size = 0.75
        elif confidence >= 0.65:
            size = 0.5
        else:
            size = 0.25
        
        # Reduce for high risk
        if risk_level == 'HIGH':
            size *= 0.5
        elif risk_level == 'MEDIUM':
            size *= 0.75
        
        # Reduce for volatile markets
        if regime.regime == 'VOLATILE':
            size *= 0.5
        
        return max(size, 0.1)  # Minimum 10% size


def test_quant_trader_psychology():
    """Test the quant trader psychology module"""
    from playground.evaluation.regime_detector import MarketRegime
    
    # Test trending bullish market
    trending_regime = MarketRegime(
        regime='TRENDING_BULLISH',
        confidence=0.85,
        trend_strength=0.75,
        volatility_level=0.40,
        adx_value=32.5,
        atr_ratio=1.2,
        bb_width=0.025,
        reasoning="Strong bullish trend"
    )
    
    trader = QuantTraderPsychology()
    
    # Good setup
    logger.info("\n=== Test 1: Good Setup in Trending Market ===")
    decision = trader.make_decision(
        regime=trending_regime,
        htf_bias='BULLISH',
        confluence_count=4,
        risk_reward_ratio=3.0
    )
    
    logger.info(f"Action: {decision.action}")
    logger.info(f"Confidence: {decision.confidence:.2%}")
    logger.info(f"Position Size: {decision.position_size_multiplier:.2f}x")
    logger.info("Reasoning:")
    for reason in decision.reasoning:
        logger.info(f"  {reason}")
    
    # Poor setup
    logger.info("\n=== Test 2: Poor Setup (Low Confluence) ===")
    decision = trader.make_decision(
        regime=trending_regime,
        htf_bias='BULLISH',
        confluence_count=2,
        risk_reward_ratio=1.5
    )
    
    logger.info(f"Action: {decision.action}")
    logger.info(f"Confidence: {decision.confidence:.2%}")
    
    # Volatile market
    volatile_regime = MarketRegime(
        regime='VOLATILE',
        confidence=0.90,
        trend_strength=0.50,
        volatility_level=0.85,
        adx_value=25.0,
        atr_ratio=2.1,
        bb_width=0.045,
        reasoning="High volatility"
    )
    
    logger.info("\n=== Test 3: Volatile Market ===")
    decision = trader.make_decision(
        regime=volatile_regime,
        htf_bias='BULLISH',
        confluence_count=5,
        risk_reward_ratio=3.5
    )
    
    logger.info(f"Action: {decision.action}")
    logger.info(f"Position Size: {decision.position_size_multiplier:.2f}x")


if __name__ == "__main__":
    test_quant_trader_psychology()
