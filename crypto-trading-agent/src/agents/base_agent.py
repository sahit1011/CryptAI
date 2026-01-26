"""
Base Agent class for all trading agents
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

class BaseAgent(ABC):
    """
    Base class for all agents in the system.
    Provides common functionality for message handling, state management, and lifecycle.
    """

    def __init__(
        self,
        name: str,
        message_bus: MessageBus,
        state_manager: StateManager
    ):
        self.name = name
        self.id = str(uuid.uuid4())
        self.message_bus = message_bus
        self.state_manager = state_manager

        self.state = "IDLE"
        self.running = False
        self.message_queue = asyncio.Queue()
        self.handlers: Dict[str, Callable] = {}

        self._setup_handlers()
        logger.info(f"[{self.name}] Agent initialized with ID: {self.id}")

    @abstractmethod
    def _setup_handlers(self):
        """Setup message handlers - must be implemented by subclass"""
        pass

    @abstractmethod
    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """Process incoming message - must be implemented by subclass"""
        pass

    async def start(self):
        """Start the agent"""
        if self.running:
            logger.warning(f"[{self.name}] Agent already running")
            return

        self.running = True
        self.state = "ACTIVE"

        # Subscribe to message bus
        await self.message_bus.subscribe(f"{self.name}_inbox", self._on_message)

        # Start heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start message processing loop
        asyncio.create_task(self._message_loop())

        logger.info(f"[{self.name}] Agent started")

    async def stop(self):
        """Stop the agent"""
        self.running = False
        self.state = "STOPPED"
        
        # Stop heartbeat
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"[{self.name}] Agent stopped")

    async def _message_loop(self):
        """Main message processing loop"""
        while self.running:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )

                # Process message
                await self._handle_message(message)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[{self.name}] Error in message loop: {e}")
                await self._handle_error(e)

    async def _handle_message(self, message: AgentMessage):
        """Handle incoming message with retry logic"""
        try:
            self.state = "PROCESSING"
            logger.debug(f"[{self.name}] Processing message: {message.type}")

            # Call message processor
            result = await self.process_message(message)

            # Send acknowledgment if required
            if message.requires_ack:
                await self.send_ack(message.id, result)

            self.state = "ACTIVE"

        except Exception as e:
            logger.error(f"[{self.name}] Error processing message: {e}")
            self.state = "ERROR"
            await self._handle_error(e)

    async def _on_message(self, message: Dict[str, Any]):
        """Callback for message bus"""
        agent_message = AgentMessage(**message)
        await self.message_queue.put(agent_message)

    async def send_message(
        self,
        receiver: str,
        message_type: str,
        payload: Dict[str, Any],
        priority: int = 5,
        requires_ack: bool = False
    ) -> str:
        """Send message to another agent"""

        message = AgentMessage(
            id=str(uuid.uuid4()),
            sender=self.name,
            receiver=receiver,
            type=message_type,
            payload=payload,
            priority=priority,
            requires_ack=requires_ack,
            timestamp=datetime.now(timezone.utc)
        )

        await self.message_bus.publish(f"{receiver}_inbox", message.dict())
        logger.debug(f"[{self.name}] Sent message to {receiver}: {message_type}")

        return message.id

    async def send_ack(self, message_id: str, result: Optional[Dict[str, Any]] = None):
        """Send acknowledgment"""
        await self.message_bus.publish(
            "acks",
            {
                "message_id": message_id,
                "agent": self.name,
                "result": result,
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            }
        )

    async def send_response(self, response_data: Dict[str, Any], correlation_id: str = None):
        """
        Send response back to orchestrator
        
        CRITICAL FIX: Preserves correlation_id from request to enable proper
        request/response matching in the orchestrator.
        
        Args:
            response_data: Response data to send (should include 'success' key)
            correlation_id: Correlation ID from the original request (if any)
        """
        response_channel = f"{self.name}_response"
        
        response_message = {
            **response_data,
            "agent": self.name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Preserve correlation_id if provided
        if correlation_id:
            response_message["correlation_id"] = correlation_id
        
        await self.message_bus.publish(
            response_channel,
            response_message,
            persist=True  # Persist for orchestrator to poll
        )
        
        logger.debug(f"[{self.name}] Sent response to orchestrator via {response_channel} (correlation_id={correlation_id})")

    async def _heartbeat_loop(self):
        """Send periodic heartbeat"""
        while self.running:
            try:
                await self.state_manager.update_agent_state(
                    agent_name=self.name,
                    state=self.state,
                    last_heartbeat=datetime.now(timezone.utc)
                )
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
            except Exception as e:
                logger.error(f"[{self.name}] Heartbeat error: {e}")

    async def _handle_error(self, error: Exception):
        """Handle errors"""
        await self.state_manager.log_error(
            agent_name=self.name,
            error=str(error)
        )

        # Alert orchestrator
        await self.send_message(
            receiver="orchestrator",
            message_type="agent_error",
            payload={
                "error": str(error),
                "agent": self.name,
                "state": self.state
            },
            priority=10
        )

    def register_handler(self, message_type: str, handler: Callable):
        """Register handler for specific message type"""
        self.handlers[message_type] = handler
        logger.debug(f"[{self.name}] Registered handler for: {message_type}")

    async def get_state(self, key: str) -> Any:
        """Get value from state manager"""
        return await self.state_manager.get(key)

    async def set_state(self, key: str, value: Any):
        """Set value in state manager"""
        await self.state_manager.set(key, value)
    
    async def publish_activity(
        self,
        action: str,
        message: str,
        phase: str = "processing",
        severity: str = "info",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Publish agent activity to the agent_activity channel for frontend neural feed.
        
        Args:
            action: The action being performed (e.g., "fetching_data", "analyzing_market")
            message: Human-readable message describing the activity
            phase: Current phase of operation (e.g., "data_collection", "analysis")
            severity: Message severity ("info", "success", "warning", "error")
            metadata: Optional additional metadata
        """
        if not self.message_bus:
            return
        
        try:
            activity_data = {
                "sender": self.name,
                "action": action,
                "message": message,
                "phase": phase,
                "severity": severity,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }
            
            await self.message_bus.publish("agent_activity", activity_data)
            logger.debug(f"[{self.name}] Published activity: {action} - {message}")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to publish activity: {e}")