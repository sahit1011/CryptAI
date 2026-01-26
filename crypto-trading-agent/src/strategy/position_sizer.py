"""
Position Sizing Engine
Calculates optimal position sizes based on risk parameters
"""
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()

@dataclass
class PositionSizeResult:
    """Position sizing calculation result"""
    recommended_size: float
    max_size: float
    risk_amount: float
    position_value: float
    leverage_used: float
    sizing_method: str
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'recommended_size': round(self.recommended_size, 6),
            'max_size': round(self.max_size, 6),
            'risk_amount': round(self.risk_amount, 2),
            'position_value': round(self.position_value, 2),
            'leverage_used': round(self.leverage_used, 2),
            'sizing_method': self.sizing_method,
            'warnings': self.warnings
        }

class PositionSizer:
    """
    Intelligent position sizing engine

    Methods:
    1. Fixed Risk % (default 2%)
    2. Volatility-Adjusted (ATR-based)
    3. Kelly Criterion (optional)
    4. Portfolio Heat-Aware
    """

    def __init__(
        self,
        default_risk_percent: float = 2.0,
        max_portfolio_heat: float = 6.0,
        max_leverage: float = 10.0
    ):
        self.default_risk_percent = default_risk_percent
        self.max_portfolio_heat = max_portfolio_heat
        self.max_leverage = max_leverage

    def calculate_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
        atr: Optional[float] = None,
        current_exposure: float = 0.0,
        method: str = 'fixed_risk'
    ) -> PositionSizeResult:
        """
        Calculate position size

        Args:
            account_balance: Account balance in USD
            entry_price: Entry price
            stop_loss: Stop-loss price
            risk_percent: Risk percentage (default: 2%)
            atr: ATR for volatility adjustment
            current_exposure: Current portfolio exposure (%)
            method: 'fixed_risk', 'volatility_adjusted', 'kelly'

        Returns:
            PositionSizeResult object
        """
        try:
            risk_pct = risk_percent or self.default_risk_percent
            warnings = []

            # Check if risk exceeds available exposure
            available_exposure = self.max_portfolio_heat - current_exposure
            if risk_pct > available_exposure:
                warnings.append(
                    f"Risk {risk_pct}% exceeds available exposure {available_exposure:.1f}%"
                )
                risk_pct = available_exposure

            # Calculate based on method
            if method == 'volatility_adjusted' and atr:
                size = self._calculate_volatility_adjusted_size(
                    account_balance, entry_price, stop_loss, risk_pct, atr
                )
            elif method == 'kelly':
                size = self._calculate_kelly_size(
                    account_balance, entry_price, stop_loss
                )
            else:  # fixed_risk
                size = self._calculate_fixed_risk_size(
                    account_balance, entry_price, stop_loss, risk_pct
                )

            # Calculate max size (with leverage)
            max_size = self._calculate_max_size(
                account_balance, entry_price, self.max_leverage
            )

            # Cap at max size
            if size > max_size:
                warnings.append(
                    f"Position size {size:.4f} exceeds max {max_size:.4f}, capping"
                )
                size = max_size

            # Calculate metrics
            risk_per_unit = abs(entry_price - stop_loss)
            risk_amount = size * risk_per_unit
            position_value = size * entry_price
            leverage_used = position_value / account_balance if account_balance > 0 else 0

            # Validate reasonable size
            if size <= 0:
                warnings.append("Calculated size is zero or negative")

            if leverage_used > self.max_leverage:
                warnings.append(
                    f"Leverage {leverage_used:.1f}x exceeds max {self.max_leverage}x"
                )

            return PositionSizeResult(
                recommended_size=size,
                max_size=max_size,
                risk_amount=risk_amount,
                position_value=position_value,
                leverage_used=leverage_used,
                sizing_method=method,
                warnings=warnings
            )

        except Exception as e:
            plog.error(f"Error calculating position size: {e}", exception=e, agent="strategy", phase="strategy_generation")
            raise

    def _calculate_fixed_risk_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float
    ) -> float:
        """
        Fixed risk percentage method
        Size = (Balance × Risk%) / (Entry - StopLoss)
        """

        risk_amount = balance * (risk_percent / 100)
        price_risk = abs(entry - stop_loss)

        if price_risk == 0:
            return 0.0

        size = risk_amount / price_risk
        return size

    def _calculate_volatility_adjusted_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float,
        atr: float
    ) -> float:
        """
        Volatility-adjusted sizing
        Reduce size when volatility is high, increase when low
        """

        # Calculate base size
        base_size = self._calculate_fixed_risk_size(
            balance, entry, stop_loss, risk_percent
        )

        # Calculate volatility adjustment factor
        price_risk = abs(entry - stop_loss)

        # Normalize ATR
        atr_ratio = atr / entry  # ATR as % of price

        # Adjustment factor (reduce size if stop is wider than ATR)
        if atr > 0:
            volatility_factor = min(atr / price_risk, 2.0)  # Cap at 2x
            volatility_factor = max(volatility_factor, 0.5)  # Floor at 0.5x
        else:
            volatility_factor = 1.0

        adjusted_size = base_size * volatility_factor

        return adjusted_size

    def _calculate_kelly_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        win_rate: float = 0.5,
        avg_rr: float = 2.5
    ) -> float:
        """
        Kelly Criterion sizing (Conservative - Quarter Kelly)

        Kelly % = (Win% × RR - Loss%) / RR
        Position Size = Balance × Kelly% / Price Risk
        """

        loss_rate = 1 - win_rate

        # Kelly formula
        kelly_percent = ((win_rate * avg_rr) - loss_rate) / avg_rr
        kelly_percent = max(kelly_percent, 0)  # No negative

        # Use Quarter Kelly for safety
        conservative_kelly = kelly_percent * 0.25

        # Cap at 5% (safety)
        conservative_kelly = min(conservative_kelly, 0.05)

        # Calculate size
        risk_amount = balance * conservative_kelly
        price_risk = abs(entry - stop_loss)

        if price_risk == 0:
            return 0.0

        size = risk_amount / price_risk
        return size

    def _calculate_max_size(
        self,
        balance: float,
        entry_price: float,
        max_leverage: float
    ) -> float:
        """
        Calculate maximum possible position size with leverage
        """

        max_position_value = balance * max_leverage
        max_size = max_position_value / entry_price if entry_price > 0 else 0

        return max_size

    def calculate_with_correlation(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        existing_positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, float]
    ) -> PositionSizeResult:
        """
        Calculate position size considering correlation with existing positions

        Reduce size if highly correlated positions exist
        """

        # Calculate base size
        base_result = self.calculate_size(
            account_balance, entry_price, stop_loss
        )

        # Calculate correlation adjustment
        correlation_factor = 1.0

        for position in existing_positions:
            symbol_pair = f"{position['symbol']}"
            correlation = correlation_matrix.get(symbol_pair, 0.0)

            # If highly correlated (>0.7), reduce size
            if abs(correlation) > 0.7:
                reduction = abs(correlation) * 0.5  # Up to 50% reduction
                correlation_factor *= (1 - reduction)

        # Adjust size
        adjusted_size = base_result.recommended_size * correlation_factor

        base_result.recommended_size = adjusted_size
        base_result.warnings.append(
            f"Size adjusted by {correlation_factor:.2f}x for correlation"
        )

        return base_result

    def validate_size(
        self,
        position_size: float,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        max_risk_percent: float = 2.5
    ) -> Tuple[bool, List[str]]:
        """
        Validate if position size is safe

        Returns:
            (is_valid, list_of_issues)
        """

        issues = []

        # Check if size is positive
        if position_size <= 0:
            issues.append("Position size must be positive")

        # Check risk amount
        risk_per_unit = abs(entry_price - stop_loss)
        risk_amount = position_size * risk_per_unit
        risk_percent = (risk_amount / account_balance) * 100 if account_balance > 0 else 100

        if risk_percent > max_risk_percent:
            issues.append(
                f"Risk {risk_percent:.2f}% exceeds maximum {max_risk_percent}%"
            )

        # Check leverage
        position_value = position_size * entry_price
        leverage = position_value / account_balance if account_balance > 0 else 999

        if leverage > self.max_leverage:
            issues.append(
                f"Leverage {leverage:.1f}x exceeds maximum {self.max_leverage}x"
            )

        # Check minimum size
        if position_size < 0.001:
            issues.append("Position size too small (< 0.001)")

        return (len(issues) == 0, issues)