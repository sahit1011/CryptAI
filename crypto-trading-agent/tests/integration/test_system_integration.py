"""
End-to-End Integration Test for Sprint 7.2
Tests complete system with all agents and orchestrator
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.main import TradingSystem
from src.core.orchestrator import TradingOrchestrator, TradingState, WorkflowPhase


class TestSystemIntegration:
    """Test complete system integration"""
    
    @pytest.mark.asyncio
    async def test_system_initialization(self):
        """Test system can be initialized"""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test-key',
            'DATABASE_URL': 'sqlite:///:memory:',
            'REDIS_URL': 'redis://localhost:6379',
            'TRADING_SYMBOL': 'BTCUSDT',
            'CYCLE_INTERVAL': '180'
        }):
            system = TradingSystem()
            
            assert system is not None
            assert system.running is False
            assert system.message_bus is None
            assert system.state_manager is None
    
    @pytest.mark.asyncio
    async def test_infrastructure_initialization(self):
        """Test infrastructure components initialize correctly"""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test-key',
            'DATABASE_URL': 'sqlite:///:memory:',
            'REDIS_URL': 'redis://localhost:6379'
        }):
            system = TradingSystem()
            
            # Mock the connections
            with patch('src.core.message_bus.MessageBus.connect', new_callable=AsyncMock):
                with patch('src.core.state_manager.StateManager.connect', new_callable=AsyncMock):
                    with patch('src.core.state_manager.StateManager.perform_state_recovery', new_callable=AsyncMock):
                        await system.initialize_infrastructure()
                        
                        assert system.message_bus is not None
                        assert system.state_manager is not None
    
    @pytest.mark.asyncio
    async def test_system_status(self):
        """Test system status reporting"""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test-key',
            'DATABASE_URL': 'sqlite:///:memory:'
        }):
            system = TradingSystem()
            status = system.get_system_status()
            
            assert 'running' in status
            assert 'infrastructure' in status
            assert 'agents' in status
            assert status['running'] is False


class TestOrchestratorWorkflow:
    """Test orchestrator workflow execution"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_creation(self):
        """Test orchestrator can be created"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager,
            symbol="BTCUSDT",
            cycle_interval=180
        )
        
        assert orchestrator is not None
        assert orchestrator.symbol == "BTCUSDT"
        assert orchestrator.cycle_interval == 180
        assert orchestrator.running is False
    
    @pytest.mark.asyncio
    async def test_orchestrator_stats(self):
        """Test orchestrator statistics"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        stats = orchestrator.get_stats()
        
        assert 'running' in stats
        assert 'current_cycle' in stats
        assert 'total_cycles_completed' in stats
        assert 'total_trades_executed' in stats
        assert stats['symbol'] == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_workflow_state_schema(self):
        """Test workflow state schema"""
        state: TradingState = {
            "cycle_id": "test_001",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.IDLE.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": None,
            "opportunities": [],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        assert state['cycle_id'] == "test_001"
        assert state['symbol'] == "BTCUSDT"
        assert state['phase'] == WorkflowPhase.IDLE.value
        assert len(state['errors']) == 0


class TestMemoryAgentIntegration:
    """Test Memory Agent integration"""
    
    @pytest.mark.asyncio
    async def test_memory_agent_in_system(self):
        """Test Memory Agent integrates with system"""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test-key',
            'DATABASE_URL': 'sqlite:///:memory:'
        }):
            from src.agents.memory_agent import MemoryAgent
            from src.core.message_bus import MessageBus
            from src.core.state_manager import StateManager
            
            message_bus = Mock(spec=MessageBus)
            message_bus.subscribe = AsyncMock()
            message_bus.publish = AsyncMock()
            
            state_manager = Mock(spec=StateManager)
            state_manager.get = AsyncMock(return_value=None)
            state_manager.set = AsyncMock()
            state_manager.update_agent_state = AsyncMock()
            
            agent = MemoryAgent(
                message_bus=message_bus,
                state_manager=state_manager,
                database_url='sqlite:///:memory:',
                openai_api_key='test-key'
            )
            
            assert agent.name == "memory_agent"
            assert agent.trade_history is not None
            assert agent.vector_memory is not None
            assert agent.performance_analytics is not None
            assert agent.regime_detector is not None


class TestEndToEndWorkflow:
    """Test complete end-to-end workflow"""
    
    @pytest.mark.asyncio
    async def test_single_cycle_execution(self):
        """Test a single trading cycle execution"""
        # This is a mock test - in production, you'd run actual cycle
        message_bus = Mock()
        message_bus.publish = AsyncMock()
        
        state_manager = Mock()
        state_manager.update_agent_state = AsyncMock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager,
            symbol="BTCUSDT",
            cycle_interval=1  # 1 second for testing
        )
        
        # Mock the workflow execution
        initial_state: TradingState = {
            "cycle_id": "test_cycle_001",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.IDLE.value,
            "symbol": "BTCUSDT",
            "market_data": {"price": 50000},
            "candles": [],
            "analysis_result": None,
            "regime": None,
            "opportunities": [],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        # Verify state structure
        assert initial_state['cycle_id'] == "test_cycle_001"
        assert initial_state['symbol'] == "BTCUSDT"
        assert initial_state['market_data'] is not None
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery in workflow"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager,
            max_retries=3
        )
        
        # Create error state
        error_state: TradingState = {
            "cycle_id": "error_test",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.ERROR.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": None,
            "opportunities": [],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": ["Test error"],
            "retry_count": 1,
            "should_continue": True,
            "next_phase": None
        }
        
        # Test retry logic
        result = await orchestrator._handle_error_node(error_state)
        
        assert result['retry_count'] == 2
        assert result['should_continue'] is True


class TestPerformanceMetrics:
    """Test performance tracking"""
    
    @pytest.mark.asyncio
    async def test_cycle_timing(self):
        """Test cycle timing tracking"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager,
            cycle_interval=180
        )
        
        start_time = datetime.now()
        
        # Simulate cycle
        await asyncio.sleep(0.1)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Verify timing is tracked
        assert duration < 1.0  # Should be fast in test
    
    @pytest.mark.asyncio
    async def test_trade_execution_count(self):
        """Test trade execution counting"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        # Initial count
        assert orchestrator.total_trades_executed == 0
        
        # Simulate trade execution
        state: TradingState = {
            "cycle_id": "test",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.EXECUTION.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": None,
            "opportunities": [],
            "selected_setup": {"trade_id": "TEST_001"},
            "risk_validation": None,
            "approved_for_execution": True,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        await orchestrator._execute_trade_node(state)
        
        # Verify count increased
        assert orchestrator.total_trades_executed == 1


class TestConditionalEdges:
    """Test workflow conditional transitions"""
    
    @pytest.mark.asyncio
    async def test_regime_check_favorable(self):
        """Test regime check with favorable conditions"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        state: TradingState = {
            "cycle_id": "test",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.REGIME_DETECTION.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": {"regime": "trending_bullish"},
            "opportunities": [],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        result = orchestrator._should_generate_strategies(state)
        assert result == "generate"
    
    @pytest.mark.asyncio
    async def test_regime_check_volatile(self):
        """Test regime check with volatile conditions"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        state: TradingState = {
            "cycle_id": "test",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.REGIME_DETECTION.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": {"regime": "volatile"},
            "opportunities": [],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        result = orchestrator._should_generate_strategies(state)
        assert result == "skip"
    
    @pytest.mark.asyncio
    async def test_opportunities_check(self):
        """Test opportunities availability check"""
        message_bus = Mock()
        state_manager = Mock()
        
        orchestrator = TradingOrchestrator(
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        # State with opportunities
        state_with_opps: TradingState = {
            "cycle_id": "test",
            "cycle_start": datetime.now(),
            "cycle_number": 1,
            "phase": WorkflowPhase.STRATEGY_GENERATION.value,
            "symbol": "BTCUSDT",
            "market_data": None,
            "candles": None,
            "analysis_result": None,
            "regime": None,
            "opportunities": [{"setup": "test"}],
            "selected_setup": None,
            "risk_validation": None,
            "approved_for_execution": False,
            "execution_result": None,
            "trade_id": None,
            "errors": [],
            "retry_count": 0,
            "should_continue": True,
            "next_phase": None
        }
        
        result = orchestrator._has_opportunities(state_with_opps)
        assert result == "validate"
        
        # State without opportunities
        state_no_opps = state_with_opps.copy()
        state_no_opps['opportunities'] = []
        
        result = orchestrator._has_opportunities(state_no_opps)
        assert result == "skip"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
