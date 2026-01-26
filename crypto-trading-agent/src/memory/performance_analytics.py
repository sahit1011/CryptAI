"""
Performance Analytics Engine
Calculates comprehensive trading performance metrics
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from loguru import logger
import numpy as np
from scipy import stats

@dataclass
class PerformanceMetrics:
    """Complete performance metrics"""
    # Basic metrics
    total_trades: int
    win_rate: float
    profit_factor: float
    
    # P&L metrics
    total_pnl: float
    total_pnl_percentage: float
    average_win: float
    average_loss: float
    average_trade: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_percentage: float
    average_rr_ratio: float
    
    # Advanced metrics
    expectancy: float
    kelly_criterion: float
    recovery_factor: float
    
    # Consistency
    best_day: float
    worst_day: float
    consecutive_wins: int
    consecutive_losses: int
    
    # Time metrics
    average_trade_duration: float
    total_trading_days: int
    
    def to_dict(self) -> Dict:
        return {
            'total_trades': self.total_trades,
            'win_rate': round(self.win_rate * 100, 2),
            'profit_factor': round(self.profit_factor, 2),
            'total_pnl': round(self.total_pnl, 2),
            'total_pnl_percentage': round(self.total_pnl_percentage, 2),
            'average_win': round(self.average_win, 2),
            'average_loss': round(self.average_loss, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'sortino_ratio': round(self.sortino_ratio, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_percentage': round(self.max_drawdown_percentage, 2),
            'expectancy': round(self.expectancy, 2),
            'kelly_criterion': round(self.kelly_criterion * 100, 2),
            'recovery_factor': round(self.recovery_factor, 2)
        }

class PerformanceAnalyticsEngine:
    """
    Performance analytics engine
    
    Calculates comprehensive metrics from trade history
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        logger.info("Performance analytics engine initialized")
    
    def calculate_metrics(
        self,
        trades: List[Dict],
        current_balance: float
    ) -> PerformanceMetrics:
        """
        Calculate complete performance metrics
        
        Args:
            trades: List of trade records (dicts)
            current_balance: Current account balance
            
        Returns:
            PerformanceMetrics
        """
        
        if not trades:
            return self._empty_metrics()
        
        # Filter closed trades
        closed_trades = [t for t in trades if t.get('exit_time')]
        
        if not closed_trades:
            return self._empty_metrics()
        
        # Basic counts
        total_trades = len(closed_trades)
        winners = [t for t in closed_trades if t.get('is_winner')]
        losers = [t for t in closed_trades if not t.get('is_winner')]
        
        win_rate = len(winners) / total_trades if total_trades > 0 else 0
        
        # P&L calculations
        wins = [t.get('pnl', 0) for t in winners]
        losses = [t.get('pnl', 0) for t in losers]
        all_pnl = [t.get('pnl', 0) for t in closed_trades]
        
        total_pnl = sum(all_pnl)
        total_pnl_pct = (total_pnl / self.initial_capital) * 100
        
        average_win = sum(wins) / len(wins) if wins else 0
        average_loss = sum(losses) / len(losses) if losses else 0
        average_trade = sum(all_pnl) / len(all_pnl) if all_pnl else 0
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Risk-reward
        rr_ratios = [
            t.get('risk_reward_ratio', 0) for t in closed_trades
            if t.get('risk_reward_ratio') is not None
        ]
        avg_rr = np.mean(rr_ratios) if rr_ratios else 0
        
        # Expectancy
        expectancy = (win_rate * average_win) - ((1 - win_rate) * abs(average_loss))
        
        # Kelly Criterion
        kelly = self._calculate_kelly_criterion(win_rate, average_win, abs(average_loss))
        
        # Equity curve and drawdown
        equity_curve = self._calculate_equity_curve(closed_trades)
        max_dd, max_dd_pct = self._calculate_max_drawdown(equity_curve)
        
        # Sharpe and Sortino ratios
        sharpe = self._calculate_sharpe_ratio(all_pnl)
        sortino = self._calculate_sortino_ratio(all_pnl)
        
        # Recovery factor
        recovery_factor = abs(total_pnl / max_dd) if max_dd != 0 else 0
        
        # Streaks
        max_win_streak, max_loss_streak = self._calculate_streaks(closed_trades)
        
        # Time metrics
        durations = [t.get('duration_minutes', 0) for t in closed_trades if t.get('duration_minutes')]
        avg_duration = np.mean(durations) if durations else 0
        
        # Trading days
        dates = []
        for t in closed_trades:
            entry_time = t.get('entry_time')
            if isinstance(entry_time, str):
                try:
                    entry_time = datetime.fromisoformat(entry_time)
                except ValueError:
                    continue
            if entry_time:
                dates.append(entry_time.date())
                
        total_days = len(set(dates)) if dates else 0
        
        # Daily P&L for best/worst day
        daily_pnl = self._calculate_daily_pnl(closed_trades)
        best_day = max(daily_pnl.values()) if daily_pnl else 0
        worst_day = min(daily_pnl.values()) if daily_pnl else 0
        
        return PerformanceMetrics(
            total_trades=total_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_pnl=total_pnl,
            total_pnl_percentage=total_pnl_pct,
            average_win=average_win,
            average_loss=average_loss,
            average_trade=average_trade,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_percentage=max_dd_pct,
            average_rr_ratio=avg_rr,
            expectancy=expectancy,
            kelly_criterion=kelly,
            recovery_factor=recovery_factor,
            best_day=best_day,
            worst_day=worst_day,
            consecutive_wins=max_win_streak,
            consecutive_losses=max_loss_streak,
            average_trade_duration=avg_duration,
            total_trading_days=total_days
        )
    
    def _calculate_equity_curve(
        self,
        trades: List[Dict]
    ) -> List[Tuple[datetime, float]]:
        """Calculate equity curve over time"""
        
        # Sort by exit time
        def get_exit_time(t):
            et = t.get('exit_time')
            if isinstance(et, str):
                try:
                    return datetime.fromisoformat(et)
                except ValueError:
                    return datetime.now()
            return et or datetime.now()
            
        sorted_trades = sorted(trades, key=get_exit_time)
        
        equity = self.initial_capital
        curve = [(datetime.now(), equity)]
        
        for trade in sorted_trades:
            equity += trade.get('pnl', 0)
            curve.append((get_exit_time(trade), equity))
        
        return curve
    
    def _calculate_max_drawdown(
        self,
        equity_curve: List[Tuple[datetime, float]]
    ) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        
        if len(equity_curve) < 2:
            return 0.0, 0.0
        
        equities = [eq for _, eq in equity_curve]
        
        peak = equities[0]
        max_dd = 0
        max_dd_pct = 0
        
        for equity in equities:
            if equity > peak:
                peak = equity
            
            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0
            
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
        
        return max_dd, max_dd_pct
    
    def _calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02
    ) -> float:
        """Calculate Sharpe ratio"""
        
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        # Annualized return (assuming daily trades)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)
        
        if std_return == 0:
            return 0.0
        
        # Daily risk-free rate
        daily_rf = risk_free_rate / 252
        
        sharpe = (mean_return - daily_rf) / std_return * np.sqrt(252)
        
        return sharpe
    
    def _calculate_sortino_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02
    ) -> float:
        """Calculate Sortino ratio"""
        
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        mean_return = np.mean(returns_array)
        
        # Downside deviation (only negative returns)
        negative_returns = returns_array[returns_array < 0]
        
        if len(negative_returns) == 0:
            return 0.0
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0.0
        
        daily_rf = risk_free_rate / 252
        
        sortino = (mean_return - daily_rf) / downside_std * np.sqrt(252)
        
        return sortino
    
    def _calculate_kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """Calculate optimal position size using Kelly Criterion"""
        
        if avg_loss == 0:
            return 0.0
        
        win_loss_ratio = avg_win / avg_loss
        
        if win_loss_ratio == 0:
            return 0.0
            
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Cap at 25% for safety
        return min(max(kelly * 0.5, 0), 0.25)
    
    def _calculate_streaks(
        self,
        trades: List[Dict]
    ) -> Tuple[int, int]:
        """Calculate maximum win/loss streaks"""
        
        def get_exit_time(t):
            et = t.get('exit_time')
            if isinstance(et, str):
                try:
                    return datetime.fromisoformat(et)
                except ValueError:
                    return datetime.now()
            return et or datetime.now()
            
        sorted_trades = sorted(trades, key=get_exit_time)
        
        max_win_streak = 0
        max_loss_streak = 0
        current_win_streak = 0
        current_loss_streak = 0
        
        for trade in sorted_trades:
            if trade.get('is_winner'):
                current_win_streak += 1
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)
        
        return max_win_streak, max_loss_streak
    
    def _calculate_daily_pnl(
        self,
        trades: List[Dict]
    ) -> Dict[datetime, float]:
        """Calculate P&L grouped by day"""
        
        daily_pnl = {}
        
        for trade in trades:
            exit_time = trade.get('exit_time')
            if not exit_time:
                continue
                
            if isinstance(exit_time, str):
                try:
                    exit_time = datetime.fromisoformat(exit_time)
                except ValueError:
                    continue
            
            date = exit_time.date()
            pnl = trade.get('pnl', 0)
            
            if date in daily_pnl:
                daily_pnl[date] += pnl
            else:
                daily_pnl[date] = pnl
        
        return daily_pnl
    
    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics"""
        return PerformanceMetrics(
            total_trades=0, win_rate=0.0, profit_factor=0.0,
            total_pnl=0.0, total_pnl_percentage=0.0,
            average_win=0.0, average_loss=0.0, average_trade=0.0,
            sharpe_ratio=0.0, sortino_ratio=0.0,
            max_drawdown=0.0, max_drawdown_percentage=0.0,
            average_rr_ratio=0.0, expectancy=0.0,
            kelly_criterion=0.0, recovery_factor=0.0,
            best_day=0.0, worst_day=0.0,
            consecutive_wins=0, consecutive_losses=0,
            average_trade_duration=0.0, total_trading_days=0
        )
