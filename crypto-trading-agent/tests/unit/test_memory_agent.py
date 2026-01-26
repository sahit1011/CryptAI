"""
Unit tests for Memory Agent
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.agents.memory_agent import MemoryAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager


@pytest.fixture
async def message_bus():
    """Create mock message bus"""
    bus = Mock(spec=MessageBus)
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
async def state_manager():
    """Create mock state manager"""
    manager = Mock(spec=StateManager)
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock()
    manager.update_agent_state = AsyncMock()
    manager.log_error = AsyncMock()
    return manager


@pytest.fixture
async def memory_agent(message_bus, state_manager):
    """Create Memory Agent instance"""
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'DATABASE_URL': 'sqlite:///:memory:'}):
        agent = MemoryAgent(
            message_bus=message_bus,
            state_manager=state_manager,
            database_url='sqlite:///:memory:',
            openai_api_key='test-key'
        )
        yield agent


class TestMemoryAgentInitialization:
    """Test Memory Agent initialization"""
    
    def test_agent_creation(self, memory_agent):
        """Test agent is created successfully"""
        assert memory_agent.name == "memory_agent"
        assert memory_agent.trade_history is not None
        assert memory_agent.vector_memory is not None
        assert memory_agent.performance_analytics is not None
        assert memory_agent.regime_detector is not None
    
    def test_handlers_registered(self, memory_agent):
        """Test all message handlers are registered"""
        expected_handlers = [
            "log_trade",
            "update_trade",
            "get_trade",
            "get_similar_trades",
            "get_performance_metrics",
            "get_regime_analysis",
            "get_performance_report",
            "get_strategy_performance",
            "get_recent_trades"
        ]
        
        for handler in expected_handlers:
            assert handler in memory_agent.handlers


class TestTradeLogging:
    """Test trade logging functionality"""
    
    @pytest.mark.asyncio
    async def test_log_trade_success(self, memory_agent):
        """Test successful trade logging"""
        payload = {
            'trade_id': 'TEST_001',
            'symbol': 'BTCUSDT',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'entry_time': datetime.now().isoformat(),
            'position_size': 0.1,
            'stop_loss': 49000.0,
            'take_profit_levels': [51000.0, 52000.0],
            'risk_amount': 100.0,
            'strategy_type': 'SCALP',
            'confidence_score': 0.85,
            'confluence_count': 3,
            'market_regime': 'trending_bullish',
            'atr_at_entry': 500.0,
            'smc_patterns': ['order_block'],
            'ict_setups': ['fair_value_gap']
        }
        
        # Mock vector memory store to avoid OpenAI API call
        memory_agent.vector_memory.store_trade = Mock()
        
        result = await memory_agent._handle_log_trade(payload)
        
        assert result['success'] is True
        assert result['trade_id'] == 'TEST_001'
        assert 'logged_at' in result
        assert memory_agent.trades_logged == 1
    
    @pytest.mark.asyncio
    async def test_log_trade_with_datetime_object(self, memory_agent):
        """Test trade logging with datetime object"""
        payload = {
            'trade_id': 'TEST_002',
            'symbol': 'ETHUSDT',
            'direction': 'SHORT',
            'entry_price': 3000.0,
            'entry_time': datetime.now(),  # datetime object instead of string
            'position_size': 0.5,
            'stop_loss': 3100.0,
            'take_profit_levels': [2900.0],
            'risk_amount': 50.0,
            'strategy_type': 'DAY_TRADE',
            'confidence_score': 0.75,
            'confluence_count': 2,
            'market_regime': 'ranging'
        }
        
        memory_agent.vector_memory.store_trade = Mock()
        
        result = await memory_agent._handle_log_trade(payload)
        
        assert result['success'] is True
        assert result['trade_id'] == 'TEST_002'


class TestTradeUpdate:
    """Test trade update functionality"""
    
    @pytest.mark.asyncio
    async def test_update_trade_success(self, memory_agent):
        """Test successful trade update"""
        # First log a trade
        log_payload = {
            'trade_id': 'TEST_003',
            'symbol': 'BTCUSDT',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'entry_time': datetime.now(),
            'position_size': 0.1,
            'stop_loss': 49000.0,
            'take_profit_levels': [51000.0],
            'risk_amount': 100.0
        }
        
        memory_agent.vector_memory.store_trade = Mock()
        await memory_agent._handle_log_trade(log_payload)
        
        # Now update it
        update_payload = {
            'trade_id': 'TEST_003',
            'exit_price': 51000.0,
            'exit_time': datetime.now().isoformat(),
            'exit_reason': 'take_profit',
            'notes': 'Hit TP1'
        }
        
        result = await memory_agent._handle_update_trade(update_payload)
        
        assert result['success'] is True
        assert result['trade_id'] == 'TEST_003'
        assert 'pnl' in result
        assert 'is_winner' in result
        assert memory_agent.trades_updated == 1


class TestPerformanceMetrics:
    """Test performance metrics calculation"""
    
    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, memory_agent):
        """Test performance metrics retrieval"""
        # Log and complete a few trades
        memory_agent.vector_memory.store_trade = Mock()
        
        for i in range(3):
            log_payload = {
                'trade_id': f'TEST_{i:03d}',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 50000.0,
                'entry_time': datetime.now() - timedelta(days=i),
                'position_size': 0.1,
                'stop_loss': 49000.0,
                'take_profit_levels': [51000.0],
                'risk_amount': 100.0
            }
            await memory_agent._handle_log_trade(log_payload)
            
            update_payload = {
                'trade_id': f'TEST_{i:03d}',
                'exit_price': 51000.0 if i % 2 == 0 else 49500.0,
                'exit_time': datetime.now(),
                'exit_reason': 'take_profit' if i % 2 == 0 else 'stop_loss'
            }
            await memory_agent._handle_update_trade(update_payload)
        
        # Get metrics
        result = await memory_agent._handle_get_performance_metrics({})
        
        assert result['success'] is True
        assert 'metrics' in result
        assert result['metrics']['total_trades'] == 3


class TestRegimeDetection:
    """Test market regime detection"""
    
    @pytest.mark.asyncio
    async def test_regime_analysis_with_candles(self, memory_agent):
        """Test regime detection with candle data"""
        # Create mock candle data
        candles = []
        base_price = 50000.0
        
        for i in range(100):
            candles.append({
                'timestamp': datetime.now() - timedelta(minutes=100-i),
                'open': base_price + i * 10,
                'high': base_price + i * 10 + 50,
                'low': base_price + i * 10 - 50,
                'close': base_price + i * 10 + 20,
                'volume': 1000000
            })
        
        payload = {
            'candles': candles,
            'symbol': 'BTCUSDT'
        }
        
        result = await memory_agent._handle_get_regime_analysis(payload)
        
        assert result['success'] is True
        assert 'regime' in result
        assert 'recommendations' in result
    
    @pytest.mark.asyncio
    async def test_regime_analysis_no_candles(self, memory_agent):
        """Test regime detection with no candle data"""
        payload = {
            'candles': [],
            'symbol': 'BTCUSDT'
        }
        
        result = await memory_agent._handle_get_regime_analysis(payload)
        
        assert result['success'] is False
        assert 'error' in result


class TestPerformanceReport:
    """Test performance report generation"""
    
    @pytest.mark.asyncio
    async def test_generate_performance_report(self, memory_agent):
        """Test comprehensive performance report"""
        # Log a trade first
        memory_agent.vector_memory.store_trade = Mock()
        
        log_payload = {
            'trade_id': 'TEST_REPORT',
            'symbol': 'BTCUSDT',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'entry_time': datetime.now(),
            'position_size': 0.1,
            'stop_loss': 49000.0,
            'take_profit_levels': [51000.0],
            'risk_amount': 100.0,
            'strategy_type': 'SCALP'
        }
        await memory_agent._handle_log_trade(log_payload)
        
        result = await memory_agent._handle_get_performance_report({})
        
        assert result['success'] is True
        assert 'report' in result
        assert 'overall_metrics' in result['report']
        assert 'strategy_breakdown' in result['report']
        assert 'recent_trades' in result['report']
        assert 'statistics' in result['report']
        assert memory_agent.performance_reports_generated == 1


class TestSimilarTrades:
    """Test similar trade retrieval"""
    
    @pytest.mark.asyncio
    async def test_get_similar_trades(self, memory_agent):
        """Test finding similar trades"""
        # Mock the vector memory search
        mock_similar_trade = Mock()
        mock_similar_trade.to_dict.return_value = {
            'trade_id': 'SIMILAR_001',
            'similarity_score': 0.85,
            'trade_data': {'symbol': 'BTCUSDT'}
        }
        
        memory_agent.vector_memory.find_similar_trades = Mock(
            return_value=[mock_similar_trade]
        )
        
        payload = {
            'current_setup': {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'strategy_type': 'SCALP',
                'market_regime': 'trending_bullish'
            },
            'n_results': 5,
            'min_similarity': 0.7
        }
        
        result = await memory_agent._handle_get_similar_trades(payload)
        
        assert result['success'] is True
        assert 'similar_trades' in result
        assert result['count'] == 1
        assert memory_agent.similar_trade_queries == 1


class TestGetTrade:
    """Test individual trade retrieval"""
    
    @pytest.mark.asyncio
    async def test_get_existing_trade(self, memory_agent):
        """Test retrieving an existing trade"""
        # Log a trade first
        memory_agent.vector_memory.store_trade = Mock()
        
        log_payload = {
            'trade_id': 'TEST_GET',
            'symbol': 'BTCUSDT',
            'direction': 'LONG',
            'entry_price': 50000.0,
            'entry_time': datetime.now(),
            'position_size': 0.1,
            'stop_loss': 49000.0,
            'take_profit_levels': [51000.0],
            'risk_amount': 100.0
        }
        await memory_agent._handle_log_trade(log_payload)
        
        # Get the trade
        result = await memory_agent._handle_get_trade({'trade_id': 'TEST_GET'})
        
        assert result['success'] is True
        assert 'trade' in result
        assert result['trade']['trade_id'] == 'TEST_GET'
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_trade(self, memory_agent):
        """Test retrieving a non-existent trade"""
        result = await memory_agent._handle_get_trade({'trade_id': 'NONEXISTENT'})
        
        assert result['success'] is False
        assert 'error' in result


class TestRecentTrades:
    """Test recent trades retrieval"""
    
    @pytest.mark.asyncio
    async def test_get_recent_trades(self, memory_agent):
        """Test getting recent trades"""
        # Log multiple trades
        memory_agent.vector_memory.store_trade = Mock()
        
        for i in range(5):
            log_payload = {
                'trade_id': f'RECENT_{i:03d}',
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry_price': 50000.0 + i * 100,
                'entry_time': datetime.now() - timedelta(hours=i),
                'position_size': 0.1,
                'stop_loss': 49000.0,
                'take_profit_levels': [51000.0],
                'risk_amount': 100.0
            }
            await memory_agent._handle_log_trade(log_payload)
        
        result = await memory_agent._handle_get_recent_trades({'limit': 3})
        
        assert result['success'] is True
        assert 'trades' in result
        assert result['count'] <= 3


class TestMessageProcessing:
    """Test message processing"""
    
    @pytest.mark.asyncio
    async def test_process_known_message(self, memory_agent):
        """Test processing a known message type"""
        message = AgentMessage(
            id='msg_001',
            sender='test_sender',
            receiver='memory_agent',
            type='get_performance_report',
            payload={},
            timestamp=datetime.now()
        )
        
        result = await memory_agent.process_message(message)
        
        assert result is not None
        assert result['success'] is True
    
    @pytest.mark.asyncio
    async def test_process_unknown_message(self, memory_agent):
        """Test processing an unknown message type"""
        message = AgentMessage(
            id='msg_002',
            sender='test_sender',
            receiver='memory_agent',
            type='unknown_message_type',
            payload={},
            timestamp=datetime.now()
        )
        
        result = await memory_agent.process_message(message)
        
        assert result is None
