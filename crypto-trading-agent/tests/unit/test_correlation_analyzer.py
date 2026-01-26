"""
Unit tests for Correlation Analyzer
"""
import pytest
from src.risk.correlation_analyzer import CorrelationAnalyzer, CorrelationResult


class TestCorrelationAnalyzer:
    """Test CorrelationAnalyzer class"""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer with default pairs"""
        return CorrelationAnalyzer()
    
    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initialization"""
        assert analyzer.max_correlated_exposure == 0.04
        assert len(analyzer.correlation_pairs) > 0
        assert ['BTCUSDT', 'ETHUSDT'] in analyzer.correlation_pairs
    
    def test_correlation_matrix_building(self, analyzer):
        """Test correlation matrix is built correctly"""
        matrix = analyzer.get_correlation_matrix()
        
        assert 'BTCUSDT' in matrix
        assert 'ETHUSDT' in matrix[' BTCUSDT']
        assert 'BNBUSDT' in matrix['BTCUSDT']
    
    def test_get_correlated_symbols(self, analyzer):
        """Test getting correlated symbols"""
        correlated = analyzer.get_correlated_symbols('BTCUSDT')
        
        assert 'ETHUSDT' in correlated
        assert 'BNBUSDT' in correlated
    
    def test_are_correlated(self, analyzer):
        """Test checking if two symbols are correlated"""
        assert analyzer.are_correlated('BTCUSDT', 'ETHUSDT') is True
        assert analyzer.are_correlated('BTCUSDT', 'ADAUSDT') is False
    
    def test_no_correlation_detected(self, analyzer):
        """Test when no correlation exists"""
        result = analyzer.analyze_correlation(
            new_symbol='ADAUSDT',
            new_direction='LONG',
            existing_positions=[],
            total_equity=10000
        )
        
        assert result.has_correlation is False
        assert result.recommended_size_multiplier == 1.0
    
    def test_correlation_same_direction(self, analyzer):
        """Test correlation with same direction (higher risk)"""
        existing_positions = [
            {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'risk_amount': 200
            }
        ]
        
        result = analyzer.analyze_correlation(
            new_symbol='ETHUSDT',
            new_direction='LONG',
            existing_positions=existing_positions,
            total_equity=10000
        )
        
        assert result.has_correlation is True
        assert len(result.correlated_symbols) == 1
        assert 'BTCUSDT' in result.correlated_symbols
        assert result.total_exposure == 200  # Full weight for same direction
    
    def test_correlation_opposite_direction(self, analyzer):
        """Test correlation with opposite direction (lower risk)"""
        existing_positions = [
            {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'risk_amount': 200
            }
        ]
        
        result = analyzer.analyze_correlation(
            new_symbol='ETHUSDT',
            new_direction='SHORT',
            existing_positions=existing_positions,
            total_equity=10000
        )
        
        assert result.has_correlation is True
        assert result.total_exposure == 100  # 0.5x weight for opposite direction
    
    def test_high_correlation_exposure(self, analyzer):
        """Test high correlated exposure triggers warnings"""
        existing_positions = [
            {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'risk_amount': 300
            },
            {
                'symbol': 'BNBUSDT',
                'direction': 'LONG',
                'risk_amount': 200
            }
        ]
        
        result = analyzer.analyze_correlation(
            new_symbol='ETHUSDT',
            new_direction='LONG',
            existing_positions=existing_positions,
            total_equity=10000
        )
        
        assert result.has_correlation is True
        assert result.total_exposure == 500  # 300 + 200
        assert len(result.warnings) > 0
        assert result.correlation_strength > 0.5
    
    def test_size_adjustment_calculation(self, analyzer):
        """Test size adjustment based on correlation"""
        existing_positions = [
            {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'risk_amount': 400  # 4% of 10k = max
            }
        ]
        
        result = analyzer.analyze_correlation(
            new_symbol='ETHUSDT',
            new_direction='LONG',
            existing_positions=existing_positions,
            total_equity=10000
        )
        
        # At max correlation (4%), should recommend 0.5x size
        assert result.correlation_strength == 1.0
        assert result.recommended_size_multiplier == 0.5
    
    def test_add_correlation_pair(self, analyzer):
        """Test adding new correlation pair"""
        analyzer.add_correlation_pair('SOLUSDT', 'AVAXUSDT')
        
        assert analyzer.are_correlated('SOLUSDT', 'AVAXUSDT') is True
        assert 'AVAXUSDT' in analyzer.get_correlated_symbols('SOLUSDT')
    
    def test_remove_correlation_pair(self, analyzer):
        """Test removing correlation pair"""
        # First add a pair
        analyzer.add_correlation_pair('SOLUSDT', 'AVAXUSDT')
        assert analyzer.are_correlated('SOLUSDT', 'AVAXUSDT') is True
        
        # Then remove it
        analyzer.remove_correlation_pair('SOLUSDT', 'AVAXUSDT')
        assert analyzer.are_correlated('SOLUSDT', 'AVAXUSDT') is False
    
    def test_calculate_correlated_exposure(self, analyzer):
        """Test calculating total correlated exposure"""
        positions = [
            {'symbol': 'BTCUSDT', 'risk_amount': 200},
            {'symbol': 'ETHUSDT', 'risk_amount': 150},
            {'symbol': 'ADAUSDT', 'risk_amount': 100}
        ]
        
        exposure = analyzer.calculate_correlated_exposure(positions)
        
        # BTC and ETH are correlated, so they should have higher exposure
        assert exposure['BTCUSDT'] > 200  # Own + partial from ETH
        assert exposure['ETHUSDT'] > 150  # Own + partial from BTC
    
    def test_suggest_size_adjustment(self, analyzer):
        """Test size adjustment suggestion"""
        # Low correlation risk
        adjusted = analyzer.suggest_size_adjustment(
            base_size=1.0,
            correlation_risk=0.2
        )
        assert adjusted > 0.9  # Minimal adjustment
        
        # High correlation risk
        adjusted = analyzer.suggest_size_adjustment(
            base_size=1.0,
            correlation_risk=0.8
        )
        assert adjusted <= 0.6  # Significant reduction
    
    def test_get_summary(self, analyzer):
        """Test getting analyzer summary"""
        summary = analyzer.get_summary()
        
        assert 'total_pairs' in summary
        assert 'total_symbols' in summary
        assert 'max_correlated_exposure' in summary
        assert summary['total_pairs'] > 0


class TestCorrelationResult:
    """Test CorrelationResult dataclass"""
    
    def test_result_creation(self):
        """Test creating correlation result"""
        result = CorrelationResult(
            has_correlation=True,
            correlated_symbols=['BTCUSDT'],
            total_exposure=200.0,
            correlation_strength=0.5,
            recommended_size_multiplier=0.75
        )
        
        assert result.has_correlation is True
        assert len(result.correlated_symbols) == 1
        assert result.total_exposure == 200.0
    
    def test_result_to_dict(self):
        """Test result serialization"""
        result = CorrelationResult(
            has_correlation=True,
            correlated_symbols=['BTCUSDT', 'ETHUSDT'],
            total_exposure=350.0,
            correlation_strength=0.75,
            recommended_size_multiplier=0.625,
            warnings=['High correlation detected']
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['has_correlation'] is True
        assert len(result_dict['correlated_symbols']) == 2
        assert result_dict['total_exposure'] == 350.0
        assert result_dict['correlation_strength'] == 0.75
        assert len(result_dict['warnings']) == 1
