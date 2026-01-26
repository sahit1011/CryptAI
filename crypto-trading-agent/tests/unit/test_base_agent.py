"""
Unit tests for Base Agent
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

class MockAgent(BaseAgent):
    """Mock agent for testing"""

    def __init__(self, name: str, message_bus: MessageBus, state_manager: StateManager):
        super().__init__(name, message_bus, state_manager)
        self.processed_messages = []

    def _setup_handlers(self):
        """Setup mock handlers"""
        pass

    async def process_message(self, message: AgentMessage) -> dict:
        """Mock message processing"""
        self.processed_messages.append(message)
        return {"status": "processed"}

@pytest.fixture
def mock_message_bus():
    """Mock message bus fixture"""
    bus = MessageBus("redis://localhost:6379")
    bus.redis_client = AsyncMock()
    bus.pubsub = AsyncMock()
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus

@pytest.fixture
def mock_state_manager():
    """Mock state manager fixture"""
    manager = StateManager()
    manager.redis = AsyncMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.update_agent_state = AsyncMock()
    manager.log_error = AsyncMock()
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock()
    return manager

@pytest.mark.asyncio
async def test_base_agent_initialization(mock_message_bus, mock_state_manager):
    """Test BaseAgent initialization"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    assert agent.name == "test_agent"
    assert agent.state == "IDLE"
    assert agent.running == False
    assert agent.id is not None
    assert len(agent.id) == 36  # UUID length

@pytest.mark.asyncio
async def test_base_agent_start_stop(mock_message_bus, mock_state_manager):
    """Test agent start/stop lifecycle"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    # Start agent
    await agent.start()
    assert agent.running == True
    assert agent.state == "ACTIVE"
    mock_message_bus.subscribe.assert_called_once()

    # Stop agent
    await agent.stop()
    assert agent.running == False
    assert agent.state == "STOPPED"

@pytest.mark.asyncio
async def test_send_message(mock_message_bus, mock_state_manager):
    """Test sending messages"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    message_id = await agent.send_message(
        receiver="other_agent",
        message_type="test_type",
        payload={"data": "test"}
    )

    assert message_id is not None
    mock_message_bus.publish.assert_called_once()

@pytest.mark.asyncio
async def test_message_processing(mock_message_bus, mock_state_manager):
    """Test message processing"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    message = AgentMessage(
        id="123",
        sender="sender",
        receiver="test_agent",
        type="test",
        payload={"data": "test"}
    )

    result = await agent.process_message(message)
    assert result == {"status": "processed"}
    assert len(agent.processed_messages) == 1

@pytest.mark.asyncio
async def test_state_management(mock_message_bus, mock_state_manager):
    """Test state management methods"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    # Test set_state
    await agent.set_state("test_key", "test_value")
    mock_state_manager.set.assert_called_with("test_key", "test_value")

    # Test get_state
    mock_state_manager.get.return_value = "test_value"
    value = await agent.get_state("test_key")
    assert value == "test_value"
    mock_state_manager.get.assert_called_with("test_key")

@pytest.mark.asyncio
async def test_error_handling(mock_message_bus, mock_state_manager):
    """Test error handling"""
    agent = MockAgent("test_agent", mock_message_bus, mock_state_manager)

    # Mock process_message to raise exception
    agent.process_message = AsyncMock(side_effect=Exception("Test error"))

    message = AgentMessage(
        id="123",
        sender="sender",
        receiver="test_agent",
        type="test",
        payload={"data": "test"}
    )

    # Process message (should handle error)
    await agent._handle_message(message)

    # Check that error was logged
    mock_state_manager.log_error.assert_called_once()
    assert agent.state == "ERROR"