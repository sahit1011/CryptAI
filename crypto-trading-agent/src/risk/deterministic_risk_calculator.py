"""
Deterministic Risk Calculator
Fast, rule-based risk validation without LLM
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import asyncio
import time

from src.risk.portfolio_state_tracker import PortfolioStateTracker
from src.utils.pipeline_logger import PipelineLogger

# Create pipeline logger instance
plog = PipelineLogger()


def at_or_above(value: float, threshold: float, rel_tol: float = 1e-9) -> bool:
    """`value >= threshold`, tolerant of float representation.

    Safety WARNINGS fire on thresholds computed as products (0.20 * 0.75), which land
    a hair above the round number they represent: 0.20 * 0.75 == 0.15000000000000002,
    so an exactly-15% drawdown compared `0.15 >= 0.15000000000000002` and stayed
    SILENT at precisely the moment the warning existed for. Rejections deliberately
    keep their strict comparisons — a hard limit should err toward allowing the edge
    case, a warning toward speaking up.
    """
    return value >= threshold - abs(threshold) * rel_tol


@dataclass
class RiskParameters:
    """Risk management parameters"""
    # Per-trade limits
    max_risk_per_trade: float = 0.02  # 2% of capital
    min_risk_reward_ratio: float = 1.0  # Changed from 2.0 to 1.0 for more trade opportunities

    # Portfolio limits
    max_portfolio_heat: float = 0.06  # 6% total exposure
    max_concurrent_positions: int = 3
    max_daily_trades: int = 5  # Max 5 trades per day

    # Drawdown limits
    max_daily_loss: float = 0.05  # 5% daily
    max_weekly_loss: float = 0.10  # 10% weekly
    max_total_drawdown: float = 0.20  # 20% from peak

    # Position sizing
    min_position_size_usd: float = 50  # Minimum $50 position
    max_position_size_usd: float = 100000  # Maximum per position (increased for 10x leverage)

    # Correlation
    max_correlated_exposure: float = 0.04  # 4% in correlated assets
    correlated_pairs: List[List[str]] = field(default_factory=list)

    def __post_init__(self):
        if not self.correlated_pairs:
            self.correlated_pairs = [
                ['BTCUSDT', 'ETHUSDT'],  # Crypto correlation
                ['BTCUSDT', 'BNBUSDT'],
            ]


@dataclass
class RiskValidationResult:
    """Result of risk validation"""
    approved: bool
    # ABSOLUTE adjusted size (in base-asset units), or None if unchanged from the
    # recommended size. Consumers send this directly to execution.
    adjusted_position_size: Optional[float] = None
    # Accumulated sizing MULTIPLIER (1.0 == no change). Correlation/regime adjustments
    # multiply into this; the absolute adjusted_position_size is derived from it against
    # the recommended size. Kept separate so the two units are never confused.
    position_size_multiplier: float = 1.0
    rejection_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    risk_score: float = 0.0  # 0-1 (1 = max risk)
    recommendations: List[str] = field(default_factory=list)
    checks: Dict[str, bool] = field(default_factory=dict)

    def add_rejection(self, reason: str):
        """Add rejection reason"""
        self.rejection_reasons.append(reason)
        self.approved = False

    def add_warning(self, warning: str):
        """Add warning (doesn't reject)"""
        self.warnings.append(warning)

    def add_recommendation(self, recommendation: str):
        """Add recommendation"""
        self.recommendations.append(recommendation)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'approved': self.approved,
            'adjusted_position_size': (
                round(self.adjusted_position_size, 6)
                if self.adjusted_position_size
                else None
            ),
            'rejection_reasons': self.rejection_reasons,
            'warnings': self.warnings,
            'risk_score': round(self.risk_score, 3),
            'recommendations': self.recommendations,
            'checks_passed': sum(1 for v in self.checks.values() if v),
            'checks_total': len(self.checks),
            'checks': self.checks
        }


class DeterministicRiskCalculator:
    """
    Performs fast, deterministic risk validation

    Uses pure computational logic - no LLM calls
    95% of validations should pass through here
    """

    def __init__(
        self,
        portfolio_tracker: PortfolioStateTracker,
        risk_params: Optional[RiskParameters] = None
    ):
        self.portfolio_tracker = portfolio_tracker
        self.risk_params = risk_params or RiskParameters()
        self._lock = asyncio.Lock()
        
        # Performance tracking
        self.validation_count = 0
        self.approval_count = 0
        self.rejection_count = 0
        self.total_validation_time = 0.0
        self.last_validation_time = 0.0

        plog.info(
            "Deterministic risk calculator initialized",
            agent="risk_agent",
            phase="initialization"
        )

    async def validate_trade_setup(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[float],
        recommended_position_size: float,
        risk_amount: float,
        confidence_score: float,
        market_regime: Optional[str] = None
    ) -> RiskValidationResult:
        """
        Comprehensive risk validation of trade setup

        Returns:
            RiskValidationResult with approval/rejection decision
        """
        start_time = time.time()
        
        async with self._lock:
            plog.info(
                f"🔍 Starting risk validation: {direction} {symbol} @ ${entry_price:.2f} | "
                f"Risk: ${risk_amount:.2f} | Confidence: {confidence_score:.2%} | "
                f"Regime: {market_regime or 'unknown'}",
                agent="risk_agent",
                phase="risk_validation"
            )

            result = RiskValidationResult(approved=True)

            plog.info(
                f"📋 Running {12} risk validation checks...",
                agent="risk_agent",
                phase="risk_validation"
            )

            # Run all validation checks
            await self._check_risk_reward_ratio(
                entry_price, stop_loss, take_profit_levels, direction, result
            )

            await self._check_per_trade_risk_limit(risk_amount, result)

            await self._check_portfolio_heat(risk_amount, result)

            await self._check_position_count(result)
            
            # NEW: Check daily trade count
            await self._check_daily_trade_count(result)

            await self._check_daily_loss_limit(result)

            await self._check_drawdown_limits(result)

            await self._check_position_size_bounds(
                entry_price, recommended_position_size, result
            )

            await self._check_confidence_threshold(confidence_score, result)

            await self._check_losing_streak(result)
            
            # NEW: Check correlation risk
            await self._check_correlation_risk(symbol, direction, risk_amount, result)
            
            # NEW: Apply market regime adjustments
            if market_regime:
                await self._apply_market_regime_adjustments(market_regime, result)

            # Derive the ABSOLUTE adjusted position size from the accumulated
            # sizing multiplier. Only set it when the multiplier actually reduced
            # size (< 1.0); otherwise leave it None to mean "use the recommended size".
            if result.position_size_multiplier < 1.0:
                result.adjusted_position_size = (
                    recommended_position_size * result.position_size_multiplier
                )

            # Calculate overall risk score
            result.risk_score = await self._calculate_risk_score(
                risk_amount, confidence_score
            )
            
            # Track performance
            validation_time = time.time() - start_time
            self.last_validation_time = validation_time
            self.total_validation_time += validation_time
            self.validation_count += 1

            # Log check results
            checks_passed = sum(1 for v in result.checks.values() if v)
            checks_total = len(result.checks)
            plog.info(
                f"📊 Validation checks: {checks_passed}/{checks_total} passed | "
                f"Warnings: {len(result.warnings)} | Risk score: {result.risk_score:.2f}",
                agent="risk_agent",
                phase="risk_validation"
            )

            # Final decision
            if result.approved:
                self.approval_count += 1
                plog.info(
                    f"✅ Trade APPROVED - {direction} {symbol} @ ${entry_price:.2f} | "
                    f"Risk score: {result.risk_score:.2f} | "
                    f"Validation time: {validation_time*1000:.0f}ms",
                    agent="risk_agent",
                    phase="risk_validation"
                )
                if result.warnings:
                    plog.info(
                        f"⚠️  Warnings: {', '.join(result.warnings[:3])}",
                        agent="risk_agent",
                        phase="risk_validation"
                    )
            else:
                self.rejection_count += 1
                plog.warning(
                    f"❌ Trade REJECTED - {direction} {symbol} @ ${entry_price:.2f} | "
                    f"Reasons: {', '.join(result.rejection_reasons)} | "
                    f"Validation time: {validation_time*1000:.0f}ms",
                    agent="risk_agent",
                    phase="risk_validation"
                )

            return result

    async def _check_risk_reward_ratio(
        self,
        entry: float,
        sl: float,
        tps: List[float],
        direction: str,
        result: RiskValidationResult
    ):
        """Check if RR ratio meets minimum"""

        # Calculate average TP
        avg_tp = sum(tps) / len(tps) if tps else entry

        # Calculate RR
        if direction == 'LONG':
            risk_distance = entry - sl
            reward_distance = avg_tp - entry
        else:
            risk_distance = sl - entry
            reward_distance = entry - avg_tp

        if risk_distance <= 0:
            result.add_rejection(
                "Invalid stop-loss placement (zero or negative risk)"
            )
            result.checks['risk_reward_ratio'] = False
            return

        rr_ratio = reward_distance / risk_distance

        if rr_ratio < self.risk_params.min_risk_reward_ratio:
            result.add_rejection(
                f"RR ratio too low: {rr_ratio:.2f} < "
                f"{self.risk_params.min_risk_reward_ratio}"
            )
            result.checks['risk_reward_ratio'] = False
        else:
            result.checks['risk_reward_ratio'] = True
            if rr_ratio >= 3.0:
                result.add_recommendation(f"Excellent RR ratio: {rr_ratio:.2f}")

    async def _check_per_trade_risk_limit(
        self,
        risk_amount: float,
        result: RiskValidationResult
    ):
        """Check if trade risk exceeds per-trade limit"""

        snapshot = await self.portfolio_tracker.get_current_snapshot()
        max_risk = snapshot.total_equity * self.risk_params.max_risk_per_trade

        # Allow small tolerance for floating point precision
        if risk_amount > max_risk + 0.01:
            result.add_rejection(
                f"Risk amount ${risk_amount:.2f} exceeds "
                f"max ${max_risk:.2f} ({self.risk_params.max_risk_per_trade*100}%)"
            )
            result.checks['per_trade_risk'] = False
        else:
            result.checks['per_trade_risk'] = True

            # Warning if close to limit. `>=` not `>`: a safety warning must fire AT
            # its threshold, not only past it — at exactly 90% of the cap the old
            # strict comparison stayed silent, which is the one moment the user most
            # needs to know how little headroom is left.
            if at_or_above(risk_amount, max_risk * 0.9):
                result.add_warning(
                    f"Risk amount ${risk_amount:.2f} is close to limit "
                    f"${max_risk:.2f}"
                )

    async def _check_portfolio_heat(
        self,
        new_risk_amount: float,
        result: RiskValidationResult
    ):
        """Check if adding this trade exceeds portfolio heat"""

        can_add = await self.portfolio_tracker.can_add_risk(
            new_risk_amount,
            max_heat=self.risk_params.max_portfolio_heat
        )

        if not can_add:
            snapshot = await self.portfolio_tracker.get_current_snapshot()
            new_heat_pct = (new_risk_amount / snapshot.total_equity) * 100
            result.add_rejection(
                f"Portfolio heat limit exceeded: "
                f"Current {snapshot.portfolio_heat*100:.2f}% "
                f"+ New {new_heat_pct:.2f}% "
                f"> Max {self.risk_params.max_portfolio_heat*100}%"
            )
            result.checks['portfolio_heat'] = False
        else:
            result.checks['portfolio_heat'] = True

    async def _check_position_count(self, result: RiskValidationResult):
        """Check if max concurrent positions reached"""

        current_count = await self.portfolio_tracker.get_position_count()

        if current_count >= self.risk_params.max_concurrent_positions:
            result.add_rejection(
                f"Max concurrent positions reached: "
                f"{current_count}/{self.risk_params.max_concurrent_positions}"
            )
            result.checks['position_count'] = False
        else:
            result.checks['position_count'] = True

    async def _check_daily_trade_count(self, result: RiskValidationResult):
        """Check if daily trade limit reached"""

        snapshot = await self.portfolio_tracker.get_current_snapshot()

        # PortfolioSnapshot's field is `daily_trades` (incremented by the tracker's
        # close_position). The old name here, `daily_trades_count`, doesn't exist on the
        # snapshot, so getattr silently returned 0 and the cap never rejected a trade.
        daily_trades = getattr(snapshot, 'daily_trades', 0)

        if daily_trades >= self.risk_params.max_daily_trades:
            result.add_rejection(
                f"Daily trade limit reached: {daily_trades}/{self.risk_params.max_daily_trades}"
            )
            result.checks['daily_trade_limit'] = False
        else:
            result.checks['daily_trade_limit'] = True

    async def _check_daily_loss_limit(self, result: RiskValidationResult):
        """Check if daily loss limit hit"""

        snapshot = await self.portfolio_tracker.get_current_snapshot()

        # Calculate daily loss percentage
        daily_loss_pct = (
            abs(min(0, snapshot.daily_pnl)) /
            self.portfolio_tracker.daily_start_equity
            if self.portfolio_tracker.daily_start_equity > 0
            else 0
        )

        if daily_loss_pct >= self.risk_params.max_daily_loss:
            result.add_rejection(
                f"Daily loss limit hit: "
                f"-${abs(snapshot.daily_pnl):.2f} "
                f"({daily_loss_pct*100:.2f}% >= "
                f"{self.risk_params.max_daily_loss*100}%)"
            )
            result.checks['daily_loss_limit'] = False
        else:
            result.checks['daily_loss_limit'] = True

            # Warning at 80% of limit
            if at_or_above(daily_loss_pct, self.risk_params.max_daily_loss * 0.8):
                result.add_warning(
                    f"Approaching daily loss limit: {daily_loss_pct*100:.2f}%"
                )

    async def _check_drawdown_limits(self, result: RiskValidationResult):
        """Check overall drawdown from peak"""

        snapshot = await self.portfolio_tracker.get_current_snapshot()

        if snapshot.current_drawdown >= self.risk_params.max_total_drawdown:
            result.add_rejection(
                f"Maximum drawdown exceeded: "
                f"{snapshot.current_drawdown*100:.2f}% >= "
                f"{self.risk_params.max_total_drawdown*100}%"
            )
            result.checks['drawdown_limit'] = False
        else:
            result.checks['drawdown_limit'] = True

            # Warning at 75% of max drawdown
            if at_or_above(snapshot.current_drawdown,
                           self.risk_params.max_total_drawdown * 0.75):
                result.add_warning(
                    f"Approaching max drawdown: "
                    f"{snapshot.current_drawdown*100:.2f}%"
                )
                result.add_recommendation(
                    "Consider reducing position sizes"
                )

    async def _check_position_size_bounds(
        self,
        entry_price: float,
        position_size: float,
        result: RiskValidationResult
    ):
        """Check if position size is within bounds"""

        position_value = entry_price * position_size

        if position_value < self.risk_params.min_position_size_usd:
            result.add_rejection(
                f"Position too small: ${position_value:.2f} < "
                f"${self.risk_params.min_position_size_usd}"
            )
            result.checks['position_size_bounds'] = False
        elif position_value > self.risk_params.max_position_size_usd:
            result.add_rejection(
                f"Position too large: ${position_value:.2f} > "
                f"${self.risk_params.max_position_size_usd}"
            )
            result.checks['position_size_bounds'] = False
        else:
            result.checks['position_size_bounds'] = True

    async def _check_confidence_threshold(
        self,
        confidence_score: float,
        result: RiskValidationResult
    ):
        """Check if confidence score meets threshold"""

        min_confidence = 0.65  # Minimum confidence for any trade

        if confidence_score < min_confidence:
            result.add_rejection(
                f"Confidence too low: {confidence_score:.2f} < {min_confidence}"
            )
            result.checks['confidence_threshold'] = False
        else:
            result.checks['confidence_threshold'] = True

            if confidence_score >= 0.85:
                result.add_recommendation(
                    "High confidence setup - consider standard sizing"
                )
            elif confidence_score < 0.75:
                result.add_recommendation(
                    "Medium confidence - consider reducing size by 25%"
                )

    async def _check_losing_streak(self, result: RiskValidationResult):
        """Check if on a losing streak (requires caution)"""

        snapshot = await self.portfolio_tracker.get_current_snapshot()

        # Circuit breaker at 2 consecutive losses (Changed from 3)
        if snapshot.loss_streak >= 2:
            result.add_rejection(
                f"Circuit breaker: {snapshot.loss_streak} consecutive losses. "
                f"Stop trading for the day to preserve capital."
            )
            result.checks['losing_streak'] = False
        else:
            result.checks['losing_streak'] = True

            if snapshot.loss_streak == 1:
                result.add_warning(
                    "1 loss recently - proceed with caution"
                )

    async def _calculate_risk_score(
        self,
        risk_amount: float,
        confidence_score: float
    ) -> float:
        """
        Calculate overall risk score (0-1)

        Higher score = higher risk
        """
        snapshot = await self.portfolio_tracker.get_current_snapshot()

        # Components of risk score
        heat_score = (
            snapshot.portfolio_heat / self.risk_params.max_portfolio_heat
        )
        drawdown_score = (
            snapshot.current_drawdown / self.risk_params.max_total_drawdown
        )
        streak_score = min(snapshot.loss_streak / 3, 1.0)
        confidence_score_inv = 1.0 - confidence_score

        # Weighted average
        risk_score = (
            heat_score * 0.3 +
            drawdown_score * 0.3 +
            streak_score * 0.2 +
            confidence_score_inv * 0.2
        )

        return min(risk_score, 1.0)

    async def suggest_position_size_adjustment(
        self,
        original_size: float,
        risk_score: float
    ) -> float:
        """
        Suggest adjusted position size based on risk score

        Higher risk score = smaller position
        """
        if risk_score < 0.3:
            return original_size  # Low risk, keep original
        elif risk_score < 0.6:
            return original_size * 0.75  # Moderate risk, reduce by 25%
        else:
            return original_size * 0.5  # High risk, reduce by 50%

    async def _check_correlation_risk(
        self,
        symbol: str,
        direction: str,
        risk_amount: float,
        result: RiskValidationResult
    ):
        """Check correlation risk with existing positions"""
        
        try:
            # Add timeout to prevent hanging
            correlation_analysis = await asyncio.wait_for(
                self.portfolio_tracker.check_correlation(symbol, direction),
                timeout=5.0  # 5 second timeout
            )
            
            if correlation_analysis['has_correlation']:
                risk_score = correlation_analysis['correlation_risk_score']
                total_exposure = correlation_analysis['total_correlated_exposure']
                
                # Check if correlated exposure exceeds limit
                snapshot = await self.portfolio_tracker.get_current_snapshot()
                corr_exposure_pct = total_exposure / snapshot.total_equity if snapshot.total_equity > 0 else 0
                
                if corr_exposure_pct > self.risk_params.max_correlated_exposure:
                    result.add_rejection(
                        f"Correlated exposure too high: ${total_exposure:.2f} "
                        f"({corr_exposure_pct*100:.1f}%) > "
                        f"{self.risk_params.max_correlated_exposure*100}%"
                    )
                    result.checks['correlation_risk'] = False
                else:
                    result.checks['correlation_risk'] = True
                    
                    # Add warning and recommendation
                    if risk_score > 0.5:
                        result.add_warning(
                            f"Moderate correlation detected: {correlation_analysis['correlation_message']}"
                        )
                        size_adj = correlation_analysis['recommended_size_adjustment']
                        result.add_recommendation(
                            f"Consider reducing position size to {size_adj:.0%} due to correlation"
                        )
                        result.position_size_multiplier *= size_adj
            else:
                result.checks['correlation_risk'] = True
        except asyncio.TimeoutError:
            plog.warning(
                "Correlation check timed out after 5s, skipping",
                agent="risk_agent",
                phase="risk_validation"
            )
            result.checks['correlation_risk'] = True  # Pass check if timeout
        except Exception as e:
            plog.error(
                f"Correlation check failed: {e}",
                agent="risk_agent",
                phase="risk_validation"
            )
            result.checks['correlation_risk'] = True  # Pass check if error
    
    async def _apply_market_regime_adjustments(
        self,
        market_regime: str,
        result: RiskValidationResult
    ):
        """Apply risk adjustments based on market regime"""
        
        regime_adjustments = {
            'TRENDING_BULLISH': {'multiplier': 1.0, 'note': 'Favorable conditions'},
            'TRENDING_BEARISH': {'multiplier': 1.0, 'note': 'Favorable conditions'},
            'RANGING': {'multiplier': 0.75, 'note': 'Reduce size in choppy markets'},
            'HIGH_VOLATILITY': {'multiplier': 0.5, 'note': 'High volatility - reduce exposure'},
            'LOW_LIQUIDITY': {'multiplier': 0.5, 'note': 'Low liquidity - reduce exposure'},
        }
        
        adjustment = regime_adjustments.get(market_regime)
        if adjustment:
            multiplier = adjustment['multiplier']
            
            if multiplier < 1.0:
                result.add_warning(
                    f"Market regime '{market_regime}': {adjustment['note']}"
                )
                result.add_recommendation(
                    f"Reduce position size to {multiplier:.0%} due to market conditions"
                )
                result.position_size_multiplier *= multiplier
            
            plog.debug(
                f"Applied market regime adjustment: {market_regime} -> {multiplier:.0%}",
                agent="risk_agent",
                phase="risk_validation"
            )
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get risk calculator performance metrics"""
        avg_validation_time = (
            self.total_validation_time / self.validation_count
            if self.validation_count > 0
            else 0
        )
        
        approval_rate = (
            self.approval_count / self.validation_count
            if self.validation_count > 0
            else 0
        )
        
        return {
            'total_validations': self.validation_count,
            'approvals': self.approval_count,
            'rejections': self.rejection_count,
            'approval_rate': round(approval_rate * 100, 1),
            'avg_validation_time_ms': round(avg_validation_time * 1000, 1),
            'last_validation_time_ms': round(self.last_validation_time * 1000, 1)
        }
    
    async def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of validation rules and current status"""
        snapshot = await self.portfolio_tracker.get_current_snapshot()
        performance = await self.get_performance_metrics()

        return {
            'timestamp': datetime.now().isoformat(),
            'risk_parameters': {
                'max_risk_per_trade': f"{self.risk_params.max_risk_per_trade*100}%",
                'min_risk_reward_ratio': self.risk_params.min_risk_reward_ratio,
                'max_portfolio_heat': f"{self.risk_params.max_portfolio_heat*100}%",
                'max_concurrent_positions': self.risk_params.max_concurrent_positions,
                'max_daily_loss': f"{self.risk_params.max_daily_loss*100}%",
                'max_total_drawdown': f"{self.risk_params.max_total_drawdown*100}%",
                'max_correlated_exposure': f"{self.risk_params.max_correlated_exposure*100}%",
            },
            'current_status': {
                'portfolio_heat': f"{snapshot.portfolio_heat*100:.2f}%",
                'open_positions': len(snapshot.open_positions),
                'daily_pnl': f"${snapshot.daily_pnl:.2f}",
                'current_drawdown': f"{snapshot.current_drawdown*100:.2f}%",
                'loss_streak': snapshot.loss_streak,
            },
            'capacity': {
                'risk_capacity_remaining': (
                    f"{(self.risk_params.max_portfolio_heat - snapshot.portfolio_heat)*100:.2f}%"
                ),
                'positions_remaining': (
                    self.risk_params.max_concurrent_positions -
                    len(snapshot.open_positions)
                ),
            },
            'performance': performance
        }
