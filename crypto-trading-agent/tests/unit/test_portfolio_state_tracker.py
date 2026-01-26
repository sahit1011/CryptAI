"""
Unit tests for Portfolio State Tracker
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from src.risk.portfolio_state_tracker import (
    PortfolioStateTracker,
    Position,
    PortfolioSnapshot
)


@pytest.fixture
def tracker():
    """Create a fresh tracker for each test"""
    return PortfolioStateTracker(initial_balance=10000.0)


@pytest.fixture
def async_tracker():
    """Create an async tracker"""
    async def _create():
        return PortfolioStateTracker(initial_balance=10000.0)
    return _create


class TestPosition:
    """Test Position dataclass"""

    def test_position_creation(self):
        """Test creating a position"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            current_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000, 45000],
            risk_amount=250,
            unrealized_pnl=0,
            risk_percentage=0.025,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        assert pos.position_id == 'pos_001'
        assert pos.symbol == 'BTCUSDT'
        assert pos.direction == 'LONG'
        assert pos.entry_price == 43000

    def test_position_pnl_long(self):
        """Test P&L calculation for LONG position"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            current_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500,
            unrealized_pnl=0,
            risk_percentage=0.05,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        # Price goes up $1000
        pnl = pos.calculate_pnl(44000)
        assert pnl == 1000

        # Price goes down $500
        pnl = pos.calculate_pnl(42500)
        assert pnl == -500

    def test_position_pnl_short(self):
        """Test P&L calculation for SHORT position"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='SHORT',
            entry_price=43000,
            current_price=43000,
            position_size=1.0,
            stop_loss=44000,
            take_profit_levels=[42000],
            risk_amount=1000,
            unrealized_pnl=0,
            risk_percentage=0.10,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        # Price goes down $1000 (profit for short)
        pnl = pos.calculate_pnl(42000)
        assert pnl == 1000

        # Price goes up $500 (loss for short)
        pnl = pos.calculate_pnl(43500)
        assert pnl == -500

    def test_position_is_profitable(self):
        """Test profitability check"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            current_price=44000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[45000],
            risk_amount=500,
            unrealized_pnl=1000,
            risk_percentage=0.05,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        assert pos.is_profitable() is True

        pos.unrealized_pnl = -500
        assert pos.is_profitable() is False

    def test_position_hit_stop_loss_long(self):
        """Test stop-loss hit detection for LONG"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            current_price=42600,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500,
            unrealized_pnl=-400,
            risk_percentage=0.05,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        assert pos.hit_stop_loss(42500) is True
        assert pos.hit_stop_loss(42400) is True
        assert pos.hit_stop_loss(42600) is False

    def test_position_hit_stop_loss_short(self):
        """Test stop-loss hit detection for SHORT"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='SHORT',
            entry_price=43000,
            current_price=43400,
            position_size=1.0,
            stop_loss=44000,
            take_profit_levels=[42000],
            risk_amount=1000,
            unrealized_pnl=-400,
            risk_percentage=0.10,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        assert pos.hit_stop_loss(44000) is True
        assert pos.hit_stop_loss(44100) is True
        assert pos.hit_stop_loss(43900) is False

    def test_position_to_dict(self):
        """Test position serialization"""
        pos = Position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            current_price=43500,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000, 45000],
            risk_amount=500,
            unrealized_pnl=500,
            risk_percentage=0.05,
            opened_at=datetime.now(),
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        pos_dict = pos.to_dict()
        assert pos_dict['position_id'] == 'pos_001'
        assert pos_dict['symbol'] == 'BTCUSDT'
        assert pos_dict['unrealized_pnl'] == 500.0


class TestPortfolioSnapshot:
    """Test PortfolioSnapshot dataclass"""

    def test_snapshot_creation(self):
        """Test creating a snapshot"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            account_balance=10000,
            total_equity=10500,
            total_unrealized_pnl=500,
            total_risk_amount=600,
            portfolio_heat=0.057,
            daily_pnl=500,
            daily_trades=2,
            daily_wins=1,
            daily_losses=1,
            peak_equity=10500,
            current_drawdown=0.0,
            win_streak=1,
            loss_streak=0
        )

        assert snapshot.account_balance == 10000
        assert snapshot.total_equity == 10500
        assert snapshot.daily_trades == 2

    def test_snapshot_win_rate_calculation(self):
        """Test win rate calculation in snapshot dict"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            account_balance=10000,
            total_equity=10500,
            daily_trades=10,
            daily_wins=7,
            daily_losses=3
        )

        snapshot_dict = snapshot.to_dict()
        assert snapshot_dict['daily_win_rate'] == 70.0

    def test_snapshot_to_dict(self):
        """Test snapshot serialization"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            account_balance=10000,
            total_equity=10500,
            peak_equity=11000,
            current_drawdown=0.045
        )

        snapshot_dict = snapshot.to_dict()
        assert 'timestamp' in snapshot_dict
        assert snapshot_dict['account_balance'] == 10000.0
        assert snapshot_dict['current_drawdown'] == 4.5  # Percentage


class TestPortfolioStateTracker:
    """Test PortfolioStateTracker main class"""

    @pytest.mark.asyncio
    async def test_tracker_initialization(self, tracker):
        """Test tracker initialization"""
        assert tracker.initial_balance == 10000.0
        assert tracker.account_balance == 10000.0
        assert tracker.peak_equity == 10000.0
        assert len(tracker.positions) == 0

    @pytest.mark.asyncio
    async def test_add_position(self, tracker):
        """Test adding a position"""
        pos = await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000, 45000],
            risk_amount=250,
            strategy_type='DAY_TRADE',
            confidence_score=0.85
        )

        assert pos.position_id == 'pos_001'
        assert pos.symbol == 'BTCUSDT'
        assert await tracker.get_position_count() == 1

    @pytest.mark.asyncio
    async def test_update_position_price(self, tracker):
        """Test updating position price"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=250
        )

        await tracker.update_position_price('pos_001', 43500)

        pos = await tracker.get_position('pos_001')
        assert pos.current_price == 43500
        assert pos.unrealized_pnl == 250  # 0.5 * 500

    @pytest.mark.asyncio
    async def test_close_position_profit(self, tracker):
        """Test closing a profitable position"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        result = await tracker.close_position('pos_001', exit_price=44000)

        assert result['pnl'] == 1000
        assert result['pnl_percentage'] == 200.0
        assert tracker.account_balance == 11000
        assert tracker.daily_trades == 1
        assert tracker.daily_wins == 1
        assert tracker.win_streak == 1

    @pytest.mark.asyncio
    async def test_close_position_loss(self, tracker):
        """Test closing a losing position"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        result = await tracker.close_position('pos_001', exit_price=42500)

        assert result['pnl'] == -500
        assert tracker.account_balance == 9500
        assert tracker.daily_trades == 1
        assert tracker.daily_losses == 1
        assert tracker.loss_streak == 1

    @pytest.mark.asyncio
    async def test_win_loss_streak_tracking(self, tracker):
        """Test win/loss streak tracking"""
        # First win
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )
        await tracker.close_position('pos_001', exit_price=44000)

        assert tracker.win_streak == 1
        assert tracker.loss_streak == 0

        # Second win
        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=1.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=100
        )
        await tracker.close_position('pos_002', exit_price=2600)

        assert tracker.win_streak == 2
        assert tracker.loss_streak == 0

        # First loss breaks streak
        await tracker.add_position(
            position_id='pos_003',
            symbol='LTCUSDT',
            direction='LONG',
            entry_price=100,
            position_size=1.0,
            stop_loss=95,
            take_profit_levels=[105],
            risk_amount=5
        )
        await tracker.close_position('pos_003', exit_price=95)

        assert tracker.win_streak == 0
        assert tracker.loss_streak == 1

    @pytest.mark.asyncio
    async def test_get_current_snapshot(self, tracker):
        """Test getting current portfolio snapshot"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.update_position_price('pos_001', 43500)

        snapshot = await tracker.get_current_snapshot()

        assert snapshot.account_balance == 10000
        assert snapshot.total_equity == 10500  # 10000 + 500 unrealized
        assert snapshot.total_unrealized_pnl == 500
        assert snapshot.total_risk_amount == 500
        assert len(snapshot.open_positions) == 1

    @pytest.mark.asyncio
    async def test_portfolio_heat_calculation(self, tracker):
        """Test portfolio heat (total exposure) calculation"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=5.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=500
        )

        snapshot = await tracker.get_current_snapshot()
        # Total risk = 1000, total equity = 10000
        # Heat = 1000 / 10000 = 0.1 (10%)
        assert snapshot.portfolio_heat == 0.1

    @pytest.mark.asyncio
    async def test_drawdown_tracking(self, tracker):
        """Test drawdown from peak equity"""
        # Increase equity
        tracker.account_balance = 12000
        tracker.peak_equity = 12000

        # Add position with loss
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.update_position_price('pos_001', 41000)

        snapshot = await tracker.get_current_snapshot()
        # Account: 12000, Unrealized: -2000
        # Total Equity: 10000
        # Peak: 12000, Current: 10000, Drawdown = 2000/12000 = 0.1667 (16.67%)
        assert abs(snapshot.current_drawdown - 0.1667) < 0.001
        assert snapshot.current_drawdown_dollars == 2000

    @pytest.mark.asyncio
    async def test_get_positions_by_symbol(self, tracker):
        """Test getting positions filtered by symbol"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=250
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='BTCUSDT',
            direction='SHORT',
            entry_price=43500,
            position_size=0.3,
            stop_loss=44000,
            take_profit_levels=[43000],
            risk_amount=150
        )

        await tracker.add_position(
            position_id='pos_003',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=5.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=500
        )

        btc_positions = await tracker.get_positions_by_symbol('BTCUSDT')
        assert len(btc_positions) == 2

        eth_positions = await tracker.get_positions_by_symbol('ETHUSDT')
        assert len(eth_positions) == 1

    @pytest.mark.asyncio
    async def test_get_total_position_size(self, tracker):
        """Test calculating total position size for a symbol"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=250
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='BTCUSDT',
            direction='SHORT',
            entry_price=43500,
            position_size=0.3,
            stop_loss=44000,
            take_profit_levels=[43000],
            risk_amount=150
        )

        total_size = await tracker.get_total_position_size('BTCUSDT')
        assert total_size == 0.8  # 0.5 + 0.3

    @pytest.mark.asyncio
    async def test_calculate_symbol_heat(self, tracker):
        """Test calculating heat for specific symbol"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=5.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=500
        )

        btc_heat = await tracker.calculate_symbol_heat('BTCUSDT')
        # BTC risk = 500, total equity = 10000
        # Heat = 500 / 10000 = 0.05 (5%)
        assert btc_heat == 0.05

    @pytest.mark.asyncio
    async def test_can_add_risk(self, tracker):
        """Test checking if we can add more risk"""
        # Initial state - should allow adding risk
        can_add = await tracker.can_add_risk(500, max_heat=0.10)
        assert can_add is True

        # Add a position
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        # Current heat = 500/10000 = 5%, max = 10%
        # Should still allow adding 400 (5% + 4% = 9%)
        can_add = await tracker.can_add_risk(400, max_heat=0.10)
        assert can_add is True

        # But not 600 more (5% + 6% = 11% > 10%)
        can_add = await tracker.can_add_risk(600, max_heat=0.10)
        assert can_add is False

    @pytest.mark.asyncio
    async def test_reset_daily_stats(self, tracker):
        """Test resetting daily statistics"""
        # Make some trades
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )
        await tracker.close_position('pos_001', exit_price=44000)

        # Verify trade was recorded
        assert tracker.daily_trades == 1
        assert tracker.daily_wins == 1

        # Reset
        await tracker.reset_daily_stats()

        assert tracker.daily_trades == 0
        assert tracker.daily_wins == 0
        assert tracker.daily_losses == 0

    @pytest.mark.asyncio
    async def test_calculate_win_rate(self, tracker):
        """Test win rate calculation"""
        # No trades
        assert await tracker.calculate_win_rate() == 0.0

        # Add trades
        tracker.daily_trades = 10
        tracker.daily_wins = 7

        assert await tracker.calculate_win_rate() == 0.7

    @pytest.mark.asyncio
    async def test_get_winning_positions(self, tracker):
        """Test getting profitable positions"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=1.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=100
        )

        # Update prices
        await tracker.update_position_price('pos_001', 44000)  # +1000
        await tracker.update_position_price('pos_002', 2400)   # -100

        winning = await tracker.get_winning_positions()
        assert len(winning) == 1
        assert winning[0].position_id == 'pos_001'

    @pytest.mark.asyncio
    async def test_get_losing_positions(self, tracker):
        """Test getting losing positions"""
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=1.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=100
        )

        # Update prices
        await tracker.update_position_price('pos_001', 44000)  # +1000
        await tracker.update_position_price('pos_002', 2400)   # -100

        losing = await tracker.get_losing_positions()
        assert len(losing) == 1
        assert losing[0].position_id == 'pos_002'

    @pytest.mark.asyncio
    async def test_add_and_get_snapshots(self, tracker):
        """Test snapshot history"""
        snapshot1 = PortfolioSnapshot(
            timestamp=datetime.now(),
            account_balance=10000,
            total_equity=10000
        )

        snapshot2 = PortfolioSnapshot(
            timestamp=datetime.now(),
            account_balance=10100,
            total_equity=10100
        )

        await tracker.add_snapshot(snapshot1)
        await tracker.add_snapshot(snapshot2)

        snapshots = await tracker.get_snapshots(limit=10)
        assert len(snapshots) == 2
        assert snapshots[-1].account_balance == 10100

    @pytest.mark.asyncio
    async def test_tracker_to_dict(self, tracker):
        """Test tracker serialization"""
        tracker_dict = tracker.to_dict()

        assert tracker_dict['initial_balance'] == 10000.0
        assert tracker_dict['account_balance'] == 10000.0
        assert tracker_dict['total_positions'] == 0

        # Add a position
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500
        )

        tracker_dict = tracker.to_dict()
        assert tracker_dict['total_positions'] == 1
