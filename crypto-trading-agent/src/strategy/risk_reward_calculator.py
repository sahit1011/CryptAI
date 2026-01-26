"""
Risk-Reward Calculator
Advanced RR calculation and optimization
"""
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()

@dataclass
class RiskRewardAnalysis:
    """Complete RR analysis result"""
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    expected_value: float
    break_even_win_rate: float
    optimized_tp_levels: List[Dict[str, float]]
    scenario_analysis: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'risk_amount': round(self.risk_amount, 2),
            'reward_amount': round(self.reward_amount, 2),
            'risk_reward_ratio': round(self.risk_reward_ratio, 2),
            'expected_value': round(self.expected_value, 2),
            'break_even_win_rate': round(self.break_even_win_rate, 3),
            'optimized_tp_levels': self.optimized_tp_levels,
            'scenario_analysis': self.scenario_analysis
        }

class RiskRewardCalculator:
    """
    Calculate and optimize risk-reward metrics
    """

    # Trading costs
    COMMISSION_RATE = 0.0004  # 0.04% per side (Binance futures)
    SLIPPAGE_RATE = 0.0002    # 0.02% estimated slippage

    def __init__(self):
        pass

    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[Dict[str, float]],
        win_rate_estimate: float = 0.5,
        include_costs: bool = True
    ) -> RiskRewardAnalysis:
        """
        Complete risk-reward analysis

        Args:
            entry_price: Entry price
            stop_loss: Stop-loss price
            take_profit_levels: List of TPs with sizes
            win_rate_estimate: Expected win rate (0-1)
            include_costs: Include commission/slippage

        Returns:
            RiskRewardAnalysis object
        """
        try:
            # Calculate base risk
            risk = abs(entry_price - stop_loss)
            plog.debug(f"RR Calculator: Entry={entry_price:.2f}, SL={stop_loss:.2f}, Risk={risk:.2f}", agent="strategy", phase="strategy_generation")

            # Calculate weighted reward
            total_reward = 0.0
            for tp in take_profit_levels:
                tp_reward = abs(tp['price'] - entry_price)
                total_reward += tp_reward * tp['size']
                plog.debug(f"RR Calculator: TP level {tp.get('level', '?')} @ {tp['price']:.2f}, size={tp['size']:.2f}, reward={tp_reward:.2f}", agent="strategy", phase="strategy_generation")

            plog.debug(f"RR Calculator: Total weighted reward = {total_reward:.2f}", agent="strategy", phase="strategy_generation")

            # Apply costs if requested
            if include_costs:
                cost_per_dollar = self.COMMISSION_RATE + self.SLIPPAGE_RATE
                risk_with_costs = risk + (entry_price * cost_per_dollar * 2)  # Entry + Exit
                reward_with_costs = total_reward - (entry_price * cost_per_dollar * 2)

                plog.debug(f"RR Calculator: Costs applied - cost_per_dollar={cost_per_dollar:.6f}, risk_with_costs={risk_with_costs:.2f}, reward_with_costs={reward_with_costs:.2f}", agent="strategy", phase="strategy_generation")

                risk = risk_with_costs
                total_reward = max(reward_with_costs, 0)

            # Calculate RR ratio
            rr_ratio = total_reward / risk if risk > 0 else 0
            plog.debug(f"RR Calculator: Final RR = {total_reward:.2f} / {risk:.2f} = {rr_ratio:.2f}", agent="strategy", phase="strategy_generation")

            # Calculate expected value
            expected_value = self._calculate_expected_value(
                risk, total_reward, win_rate_estimate
            )

            # Calculate break-even win rate
            break_even_wr = self._calculate_break_even_win_rate(risk, total_reward)

            # Optimize TP levels
            optimized_tps = self._optimize_tp_levels(
                entry_price, stop_loss, take_profit_levels
            )

            # Scenario analysis
            scenarios = self._run_scenario_analysis(
                entry_price, stop_loss, take_profit_levels, win_rate_estimate
            )

            return RiskRewardAnalysis(
                risk_amount=risk,
                reward_amount=total_reward,
                risk_reward_ratio=rr_ratio,
                expected_value=expected_value,
                break_even_win_rate=break_even_wr,
                optimized_tp_levels=optimized_tps,
                scenario_analysis=scenarios
            )

        except Exception as e:
            plog.error(f"Error calculating RR: {e}", exception=e, agent="strategy", phase="strategy_generation")
            raise

    def _calculate_expected_value(
        self,
        risk: float,
        reward: float,
        win_rate: float
    ) -> float:
        """
        Calculate expected value (expectancy)
        EV = (Win% × Reward) - (Loss% × Risk)
        """
        loss_rate = 1 - win_rate
        ev = (win_rate * reward) - (loss_rate * risk)
        return ev

    def _calculate_break_even_win_rate(
        self,
        risk: float,
        reward: float
    ) -> float:
        """
        Calculate minimum win rate needed to break even
        BE_WR = Risk / (Risk + Reward)
        """
        if risk + reward == 0:
            return 1.0

        be_wr = risk / (risk + reward)
        return min(be_wr, 1.0)

    def _optimize_tp_levels(
        self,
        entry_price: float,
        stop_loss: float,
        tp_levels: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """
        Optimize TP levels to maximize RR while maintaining structure

        Strategy:
        - Keep TP1 conservative (1.5:1 to 2:1)
        - Extend TP2 and TP3 if possible
        - Maintain logical progression
        """

        if len(tp_levels) < 3:
            return tp_levels

        risk = abs(entry_price - stop_loss)
        direction = 1 if tp_levels[0]['price'] > entry_price else -1

        # Optimize each TP level
        optimized = []

        for i, tp in enumerate(tp_levels):
            current_rr = abs(tp['price'] - entry_price) / risk

            if i == 0:
                # TP1: Keep conservative (1.5:1 to 2:1)
                target_rr = max(1.5, min(current_rr, 2.0))
            elif i == 1:
                # TP2: Aim for 2.5:1 to 3:1
                target_rr = max(2.5, min(current_rr, 3.5))
            else:
                # TP3+: Aim for 4:1+
                target_rr = max(4.0, current_rr)

            optimized_price = entry_price + (direction * risk * target_rr)

            optimized.append({
                'level': tp['level'],
                'price': round(optimized_price, 2),
                'size': tp['size'],
                'rr_ratio': round(target_rr, 2)
            })

        return optimized

    def _run_scenario_analysis(
        self,
        entry_price: float,
        stop_loss: float,
        tp_levels: List[Dict[str, float]],
        win_rate: float
    ) -> Dict[str, float]:
        """
        Run various scenario simulations
        """

        risk = abs(entry_price - stop_loss)

        scenarios = {}

        # Scenario 1: Full loss
        scenarios['full_loss'] = -risk

        # Scenario 2: Partial hits (only TP1)
        if len(tp_levels) >= 1:
            tp1_reward = abs(tp_levels[0]['price'] - entry_price) * tp_levels[0]['size']
            scenarios['tp1_only'] = tp1_reward - (risk * (1 - tp_levels[0]['size']))

        # Scenario 3: TP1 + TP2
        if len(tp_levels) >= 2:
            tp1_reward = abs(tp_levels[0]['price'] - entry_price) * tp_levels[0]['size']
            tp2_reward = abs(tp_levels[1]['price'] - entry_price) * tp_levels[1]['size']
            remaining_risk = risk * (1 - tp_levels[0]['size'] - tp_levels[1]['size'])
            scenarios['tp1_tp2'] = tp1_reward + tp2_reward - remaining_risk

        # Scenario 4: All TPs hit
        total_reward = sum(
            abs(tp['price'] - entry_price) * tp['size']
            for tp in tp_levels
        )
        scenarios['all_tps'] = total_reward

        # Scenario 5: Average outcome (probability-weighted)
        scenarios['expected_outcome'] = self._calculate_expected_value(
            risk,
            sum(abs(tp['price'] - entry_price) * tp['size'] for tp in tp_levels),
            win_rate
        )

        return {k: round(v, 2) for k, v in scenarios.items()}

    def validate_minimum_rr(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[Dict[str, float]],
        minimum_rr: float = 2.0
    ) -> Tuple[bool, float]:
        """
        Validate if setup meets minimum RR requirement

        Returns:
            (meets_requirement, actual_rr)
        """

        risk = abs(entry_price - stop_loss)

        total_reward = sum(
            abs(tp['price'] - entry_price) * tp['size']
            for tp in take_profit_levels
        )

        actual_rr = total_reward / risk if risk > 0 else 0

        return (actual_rr >= minimum_rr, actual_rr)

    def calculate_position_risk(
        self,
        entry_price: float,
        stop_loss: float,
        position_size: float,
        account_balance: float
    ) -> Dict[str, float]:
        """
        Calculate position risk metrics
        """

        risk_per_unit = abs(entry_price - stop_loss)
        total_risk = risk_per_unit * position_size
        risk_percentage = (total_risk / account_balance) * 100 if account_balance > 0 else 0

        return {
            'risk_per_unit': round(risk_per_unit, 2),
            'total_risk_dollars': round(total_risk, 2),
            'risk_percentage': round(risk_percentage, 2),
            'position_value': round(entry_price * position_size, 2)
        }

    def adjust_tp_for_better_rr(
        self,
        entry_price: float,
        stop_loss: float,
        current_tp: float,
        target_rr: float
    ) -> float:
        """
        Adjust a single TP to achieve target RR
        """

        risk = abs(entry_price - stop_loss)
        required_reward = risk * target_rr

        direction = 1 if current_tp > entry_price else -1
        new_tp = entry_price + (direction * required_reward)

        return round(new_tp, 2)