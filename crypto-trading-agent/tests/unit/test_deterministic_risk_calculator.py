"""
Unit tests for Deterministic Risk Calculator
"""
import pytest
import asyncio
from src.risk.deterministic_risk_calculator import (
    DeterministicRiskCalculator,
    RiskParameters,
    RiskValidationResult
)
from src.risk.portfolio_state_tracker import PortfolioStateTracker


@pytest.fixture
def tracker():
    """Create a fresh tracker for each test"""
    return PortfolioStateTracker(initial_balance=10000.0)


@pytest.fixture
def calculator(tracker):
    """Create calculator with default risk parameters"""
    return DeterministicRiskCalculator(tracker)


@pytest.fixture
def strict_calculator(tracker):
    """Create calculator with stricter parameters"""
    params = RiskParameters(
        max_risk_per_trade=0.01,  # 1%
        max_portfolio_heat=0.03,  # 3%
        max_concurrent_positions=2
    )
    return DeterministicRiskCalculator(tracker, risk_params=params)


class TestRiskParameters:
    """Test RiskParameters dataclass"""

    def test_default_parameters(self):
        """Test default parameter values"""
        params = RiskParameters()

        assert params.max_risk_per_trade == 0.02
        assert params.min_risk_reward_ratio == 2.0
        assert params.max_portfolio_heat == 0.06
        assert params.max_concurrent_positions == 3
        assert params.max_daily_loss == 0.05

    def test_custom_parameters(self):
        """Test custom parameter values"""
        params = RiskParameters(
            max_risk_per_trade=0.01,
            max_portfolio_heat=0.04,
            max_concurrent_positions=2
        )

        assert params.max_risk_per_trade == 0.01
        assert params.max_portfolio_heat == 0.04
        assert params.max_concurrent_positions == 2

    def test_correlated_pairs_default(self):
        """Test default correlated pairs"""
        params = RiskParameters()

        assert len(params.correlated_pairs) > 0
        assert ['BTCUSDT', 'ETHUSDT'] in params.correlated_pairs


class TestRiskValidationResult:
    """Test RiskValidationResult dataclass"""

    def test_result_initialization(self):
        """Test result creation"""
        result = RiskValidationResult(approved=True)

        assert result.approved is True
        assert len(result.rejection_reasons) == 0
        assert len(result.warnings) == 0
        assert result.risk_score == 0.0

    def test_add_rejection(self):
        """Test adding rejection"""
        result = RiskValidationResult(approved=True)
        result.add_rejection("Risk too high")

        assert result.approved is False
        assert "Risk too high" in result.rejection_reasons

    def test_add_warning(self):
        """Test adding warning"""
        result = RiskValidationResult(approved=True)
        result.add_warning("Be careful")

        assert result.approved is True  # Warning doesn't reject
        assert "Be careful" in result.warnings

    def test_add_recommendation(self):
        """Test adding recommendation"""
        result = RiskValidationResult(approved=True)
        result.add_recommendation("Reduce size")

        assert "Reduce size" in result.recommendations

    def test_result_to_dict(self):
        """Test result serialization"""
        result = RiskValidationResult(approved=True, risk_score=0.5)
        result.add_warning("Warning 1")
        result.checks['test_check'] = True

        result_dict = result.to_dict()

        assert result_dict['approved'] is True
        assert result_dict['risk_score'] == 0.5
        assert len(result_dict['warnings']) == 1
        assert result_dict['checks_total'] == 1


class TestRiskRewardRatio:
    """Test risk-reward ratio validation"""

    @pytest.mark.asyncio
    async def test_excellent_rr_ratio(self, calculator):
        """Test setup with excellent RR ratio"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42000,  # 1000 risk
            take_profit_levels=[45000, 46000],  # 2000-3000 reward
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['risk_reward_ratio'] is True

    @pytest.mark.asyncio
    async def test_poor_rr_ratio(self, calculator):
        """Test rejection of poor RR ratio"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42900,  # 100 risk
            take_profit_levels=[43050],  # 50 reward (0.5:1 ratio)
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['risk_reward_ratio'] is False
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_invalid_stop_loss(self, calculator):
        """Test rejection of invalid stop loss"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=43100,  # Above entry (invalid)
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['risk_reward_ratio'] is False


class TestPerTradeRiskLimit:
    """Test per-trade risk limits"""

    @pytest.mark.asyncio
    async def test_risk_within_limit(self, calculator):
        """Test trade with acceptable risk"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,  # 2% of $10k
            confidence_score=0.85
        )

        assert result.checks['per_trade_risk'] is True

    @pytest.mark.asyncio
    async def test_risk_exceeds_limit(self, calculator):
        """Test rejection of excessive risk"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=500,  # 5% of $10k
            confidence_score=0.85
        )

        assert result.checks['per_trade_risk'] is False
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_risk_near_limit_warning(self, calculator):
        """Test warning when risk is near limit"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=180,  # 1.8% of $10k (90% of 2% limit)
            confidence_score=0.85
        )

        assert result.checks['per_trade_risk'] is True
        assert len(result.warnings) > 0


class TestPortfolioHeat:
    """Test portfolio heat (exposure) limits"""

    @pytest.mark.asyncio
    async def test_add_position_within_heat_limit(self, calculator, tracker):
        """Test adding position within heat limit"""
        # Add first position (2% risk)
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=200
        )

        # Try to add second position (2% risk, total 4% < 6% limit)
        result = await calculator.validate_trade_setup(
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            stop_loss=2400,
            take_profit_levels=[2600],
            recommended_position_size=1.0,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['portfolio_heat'] is True

    @pytest.mark.asyncio
    async def test_portfolio_heat_exceeded(self, calculator, tracker):
        """Test rejection when portfolio heat limit exceeded"""
        # Add position that uses 5% heat
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=500  # 5% of $10k
        )

        # Try to add another position that would exceed 6% limit
        result = await calculator.validate_trade_setup(
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            stop_loss=2400,
            take_profit_levels=[2600],
            recommended_position_size=1.0,
            risk_amount=200,  # Would total 7%
            confidence_score=0.85
        )

        assert result.checks['portfolio_heat'] is False


class TestPositionCount:
    """Test maximum concurrent position limits"""

    @pytest.mark.asyncio
    async def test_position_count_within_limit(self, calculator, tracker):
        """Test adding positions within limit"""
        # Add positions up to limit (3)
        for i in range(2):
            await tracker.add_position(
                position_id=f'pos_{i:03d}',
                symbol='BTCUSDT',
                direction='LONG',
                entry_price=43000,
                position_size=0.2,
                stop_loss=42500,
                take_profit_levels=[44000],
                risk_amount=100
            )

        # Should allow one more (total 3)
        result = await calculator.validate_trade_setup(
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            stop_loss=2400,
            take_profit_levels=[2600],
            recommended_position_size=1.0,
            risk_amount=100,
            confidence_score=0.85
        )

        assert result.checks['position_count'] is True

    @pytest.mark.asyncio
    async def test_position_count_exceeded(self, calculator, tracker):
        """Test rejection when max positions reached"""
        # Add maximum positions
        for i in range(3):
            await tracker.add_position(
                position_id=f'pos_{i:03d}',
                symbol='BTCUSDT',
                direction='LONG',
                entry_price=43000,
                position_size=0.1,
                stop_loss=42500,
                take_profit_levels=[44000],
                risk_amount=50
            )

        # Try to add one more (should fail)
        result = await calculator.validate_trade_setup(
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            stop_loss=2400,
            take_profit_levels=[2600],
            recommended_position_size=1.0,
            risk_amount=50,
            confidence_score=0.85
        )

        assert result.checks['position_count'] is False


class TestDailyLossLimit:
    """Test daily loss limits"""

    @pytest.mark.asyncio
    async def test_no_daily_loss(self, calculator):
        """Test when no daily loss"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['daily_loss_limit'] is True

    @pytest.mark.asyncio
    async def test_daily_loss_warning(self, calculator, tracker):
        """Test warning when approaching daily loss limit"""
        # Simulate 4% daily loss (80% of 5% limit)
        tracker.account_balance = 9600
        tracker.daily_start_equity = 10000

        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['daily_loss_limit'] is True
        assert len(result.warnings) > 0


class TestDrawdownLimit:
    """Test drawdown from peak limits"""

    @pytest.mark.asyncio
    async def test_no_drawdown(self, calculator):
        """Test when no drawdown"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['drawdown_limit'] is True

    @pytest.mark.asyncio
    async def test_drawdown_warning(self, calculator, tracker):
        """Test warning when approaching drawdown limit"""
        # Simulate 15% drawdown (75% of 20% limit)
        tracker.peak_equity = 10000
        tracker.account_balance = 8500

        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['drawdown_limit'] is True
        assert len(result.warnings) > 0


class TestPositionSizeBounds:
    """Test position size bounds"""

    @pytest.mark.asyncio
    async def test_position_size_too_small(self, calculator):
        """Test rejection of too-small position"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.0001,  # $4.30 - too small
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['position_size_bounds'] is False

    @pytest.mark.asyncio
    async def test_position_size_too_large(self, calculator):
        """Test rejection of too-large position"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=1.0,  # $43,000 - exceeds $5,000 max
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['position_size_bounds'] is False

    @pytest.mark.asyncio
    async def test_position_size_within_bounds(self, calculator):
        """Test valid position size"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.1,  # $4,300 - valid
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['position_size_bounds'] is True


class TestConfidenceThreshold:
    """Test confidence score validation"""

    @pytest.mark.asyncio
    async def test_confidence_too_low(self, calculator):
        """Test rejection of low confidence"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.60  # Below 0.65 minimum
        )

        assert result.checks['confidence_threshold'] is False

    @pytest.mark.asyncio
    async def test_high_confidence(self, calculator):
        """Test high confidence recommendation"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.90
        )

        assert result.checks['confidence_threshold'] is True
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_medium_confidence_warning(self, calculator):
        """Test medium confidence warning"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.70
        )

        assert result.checks['confidence_threshold'] is True
        assert len(result.recommendations) > 0


class TestLosingStreak:
    """Test losing streak handling"""

    @pytest.mark.asyncio
    async def test_no_losing_streak(self, calculator):
        """Test with no losing streak"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['losing_streak'] is True

    @pytest.mark.asyncio
    async def test_losing_streak_warning(self, calculator, tracker):
        """Test warning for 2 consecutive losses"""
        tracker.loss_streak = 2

        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['losing_streak'] is True
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_loss_streak(self, calculator, tracker):
        """Test rejection for 3+ consecutive losses"""
        tracker.loss_streak = 3

        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.85
        )

        assert result.checks['losing_streak'] is False


class TestRiskScore:
    """Test risk score calculation"""

    @pytest.mark.asyncio
    async def test_low_risk_score(self, calculator):
        """Test low risk score calculation"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=100,  # Low risk
            confidence_score=0.90  # High confidence
        )

        assert result.risk_score < 0.3

    @pytest.mark.asyncio
    async def test_high_risk_score(self, calculator, tracker):
        """Test high risk score calculation"""
        # Simulate high risk conditions
        tracker.peak_equity = 10000
        tracker.account_balance = 8000  # 20% drawdown
        tracker.loss_streak = 2

        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=200,
            confidence_score=0.65  # Low confidence
        )

        assert result.risk_score > 0.5


class TestPositionSizeAdjustment:
    """Test position size adjustment suggestions"""

    @pytest.mark.asyncio
    async def test_low_risk_no_adjustment(self, calculator):
        """Test no adjustment for low risk"""
        adjusted = await calculator.suggest_position_size_adjustment(
            original_size=1.0,
            risk_score=0.2
        )

        assert adjusted == 1.0

    @pytest.mark.asyncio
    async def test_moderate_risk_adjustment(self, calculator):
        """Test 25% reduction for moderate risk"""
        adjusted = await calculator.suggest_position_size_adjustment(
            original_size=1.0,
            risk_score=0.5
        )

        assert abs(adjusted - 0.75) < 0.01

    @pytest.mark.asyncio
    async def test_high_risk_adjustment(self, calculator):
        """Test 50% reduction for high risk"""
        adjusted = await calculator.suggest_position_size_adjustment(
            original_size=1.0,
            risk_score=0.8
        )

        assert abs(adjusted - 0.5) < 0.01


class TestIntegration:
    """Integration tests for complete validation flows"""

    @pytest.mark.asyncio
    async def test_approved_high_quality_trade(self, calculator):
        """Test approval of high-quality trade"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42000,  # 1000 risk
            take_profit_levels=[45000, 46000],  # 2-3k reward
            recommended_position_size=0.1,
            risk_amount=100,  # 1% risk
            confidence_score=0.90
        )

        assert result.approved is True
        assert result.risk_score < 0.3

    @pytest.mark.asyncio
    async def test_rejected_poor_setup(self, calculator):
        """Test rejection of poor setup"""
        result = await calculator.validate_trade_setup(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42900,  # Small risk
            take_profit_levels=[43050],  # Tiny reward (bad RR)
            recommended_position_size=5.0,  # Way too large
            risk_amount=500,  # Too much risk
            confidence_score=0.50  # Too low confidence
        )

        assert result.approved is False
        assert len(result.rejection_reasons) > 0
