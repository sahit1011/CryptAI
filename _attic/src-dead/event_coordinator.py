"""
Event Coordinator for Hybrid Event-Driven Architecture
Lightweight coordinator that triggers cycles and monitors event flow without blocking
"""
import asyncio
import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime
from loguru import logger

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.core.cycle_state import CycleState, CycleStatus, CycleStatistics
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class EventCoordinator:
    """
    Event Coordinator for Event-Driven Trading Cycles
    
    Responsibilities:
    - Trigger cycle_start events every N minutes
    - Track active cycles via correlation IDs
    - Monitor cycle completion via cycle_complete events
    - Handle cycle timeouts (300s max)
    - Provide cycle statistics and monitoring
    
    Does NOT:
    - Block waiting for agent responses (non-blocking)
    - Directly call agents (uses events only)
    - Manage agent state (agents are autonomous)
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        cycle_interval: int = 300,  # 5 minutes
        cycle_timeout: int = 300,   # 5 minutes max per cycle
        enabled: bool = True
    ):
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.cycle_interval = cycle_interval
        self.cycle_timeout = cycle_timeout
        self.enabled = enabled
        
        # Active cycles tracking
        self.active_cycles: Dict[str, CycleState] = {}
        self.completed_cycles: List[CycleState] = []
        
        # Statistics
        self.statistics = CycleStatistics()
        
        # Control
        self.running = False
        self._cycle_trigger_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
        plog.info(
            f"EventCoordinator initialized | interval={cycle_interval}s, timeout={cycle_timeout}s, enabled={enabled}",
            agent="event_coordinator",
            phase="initialization"
        )
    
    async def start(self):
        """Start the event coordinator"""
        if not self.enabled:
            plog.warning(
                "EventCoordinator is disabled, not starting",
                agent="event_coordinator"
            )
            return
        
        if self.running:
            plog.warning(
                "EventCoordinator already running",
                agent="event_coordinator"
            )
            return
        
        self.running = True
        
        # Subscribe to cycle completion events
        await self.message_bus.subscribe("cycle_complete", self._handle_cycle_complete)
        await self.message_bus.subscribe("cycle_error", self._handle_cycle_error)
        
        # Subscribe to intermediate events for tracking
        await self.message_bus.subscribe("data_ready", self._handle_data_ready)
        await self.message_bus.subscribe("regime_detected", self._handle_regime_detected)
        await self.message_bus.subscribe("analysis_complete", self._handle_analysis_complete)
        await self.message_bus.subscribe("setup_generated", self._handle_setup_generated)
        await self.message_bus.subscribe("trade_approved", self._handle_trade_approved)
        await self.message_bus.subscribe("trade_rejected", self._handle_trade_rejected)
        await self.message_bus.subscribe("trade_executed", self._handle_trade_executed)
        
        # Start cycle trigger loop
        self._cycle_trigger_task = asyncio.create_task(self._cycle_trigger_loop())
        
        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_cycles())
        
        plog.success(
            "EventCoordinator started successfully",
            agent="event_coordinator",
            phase="startup"
        )
    
    async def stop(self):
        """Stop the event coordinator"""
        self.running = False
        
        # Cancel tasks
        if self._cycle_trigger_task:
            self._cycle_trigger_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        
        # Unsubscribe from events
        await self.message_bus.unsubscribe("cycle_complete")
        await self.message_bus.unsubscribe("cycle_error")
        await self.message_bus.unsubscribe("data_ready")
        await self.message_bus.unsubscribe("regime_detected")
        await self.message_bus.unsubscribe("analysis_complete")
        await self.message_bus.unsubscribe("setup_generated")
        await self.message_bus.unsubscribe("trade_approved")
        await self.message_bus.unsubscribe("trade_rejected")
        await self.message_bus.unsubscribe("trade_executed")
        
        plog.info(
            "EventCoordinator stopped",
            agent="event_coordinator",
            phase="shutdown"
        )
    
    async def start_cycle(self, symbol: str) -> str:
        """
        Trigger a new trading cycle via event
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT')
            
        Returns:
            cycle_id: Unique cycle identifier
        """
        # Generate unique cycle ID
        cycle_id = f"{symbol.replace('/', '')}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
        
        # Create cycle state
        cycle_state = CycleState(
            cycle_id=cycle_id,
            symbol=symbol,
            start_time=datetime.now()
        )
        
        # Track cycle
        self.active_cycles[cycle_id] = cycle_state
        
        # Publish cycle_start event
        await self.message_bus.publish(
            "cycle_start",
            {
                'cycle_id': cycle_id,
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'coordinator': 'event_coordinator'
            },
            persist=False  # Event-driven, no persistence
        )
        
        plog.info(
            f"🚀 Cycle started | cycle_id={cycle_id}, symbol={symbol}",
            agent="event_coordinator",
            phase="cycle_start"
        )
        
        # Schedule timeout
        asyncio.create_task(self._timeout_cycle(cycle_id))
        
        return cycle_id
    
    async def _cycle_trigger_loop(self):
        """Periodically trigger new cycles"""
        plog.info(
            f"Cycle trigger loop started | interval={self.cycle_interval}s",
            agent="event_coordinator"
        )
        
        while self.running:
            try:
                # Wait for interval
                await asyncio.sleep(self.cycle_interval)
                
                # Trigger cycle for each configured symbol
                # TODO: Get symbols from config
                symbols = ["BTC/USDT"]  # Hardcoded for now
                
                for symbol in symbols:
                    await self.start_cycle(symbol)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                plog.error(
                    f"Error in cycle trigger loop: {e}",
                    exception=e,
                    agent="event_coordinator"
                )
                await asyncio.sleep(10)  # Wait before retry
    
    async def _timeout_cycle(self, cycle_id: str):
        """Timeout a cycle if it doesn't complete in time"""
        await asyncio.sleep(self.cycle_timeout)
        
        # Check if cycle still active
        if cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            
            if not cycle.is_complete():
                plog.warning(
                    f"⏱️ Cycle timed out | cycle_id={cycle_id}, elapsed={cycle.get_elapsed_time():.1f}s",
                    agent="event_coordinator",
                    phase="timeout"
                )
                
                # Update cycle state
                cycle.update_status(CycleStatus.TIMEOUT)
                cycle.error = f"Cycle timed out after {self.cycle_timeout}s"
                
                # Move to completed
                self._complete_cycle(cycle_id)
    
    async def _monitor_cycles(self):
        """Monitor active cycles and log status"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if self.active_cycles:
                    plog.debug(
                        f"Active cycles: {len(self.active_cycles)} | "
                        f"Completed: {len(self.completed_cycles)}",
                        agent="event_coordinator"
                    )
                    
                    # Log individual cycle status
                    for cycle_id, cycle in list(self.active_cycles.items()):
                        plog.debug(
                            f"Cycle {cycle_id}: {cycle.status.value} | "
                            f"elapsed={cycle.get_elapsed_time():.1f}s, "
                            f"remaining={cycle.get_remaining_time():.1f}s, "
                            f"events={len(cycle.events_received)}",
                            agent="event_coordinator"
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                plog.error(
                    f"Error in monitor loop: {e}",
                    exception=e,
                    agent="event_coordinator"
                )
    
    def _complete_cycle(self, cycle_id: str):
        """Mark cycle as complete and update statistics"""
        if cycle_id not in self.active_cycles:
            return
        
        cycle = self.active_cycles.pop(cycle_id)
        
        # Update statistics
        self.statistics.update(cycle)
        
        # Store completed cycle (keep last 100)
        self.completed_cycles.append(cycle)
        if len(self.completed_cycles) > 100:
            self.completed_cycles.pop(0)
        
        plog.info(
            f"✅ Cycle completed | cycle_id={cycle_id}, status={cycle.status.value}, "
            f"duration={cycle.total_duration:.1f}s",
            agent="event_coordinator",
            phase="cycle_complete"
        )
    
    # Event handlers for tracking
    
    async def _handle_data_ready(self, message: Dict[str, Any]):
        """Handle data_ready event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('data_ready')
            cycle.update_status(CycleStatus.DATA_READY)
            cycle.data_fetch_duration = cycle.get_event_duration('data_ready')
            
            plog.debug(
                f"Data ready | cycle_id={cycle_id}, duration={cycle.data_fetch_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_regime_detected(self, message: Dict[str, Any]):
        """Handle regime_detected event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('regime_detected')
            cycle.update_status(CycleStatus.REGIME_DETECTED)
            cycle.regime_detection_duration = cycle.get_event_duration('regime_detected')
            
            plog.debug(
                f"Regime detected | cycle_id={cycle_id}, duration={cycle.regime_detection_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_analysis_complete(self, message: Dict[str, Any]):
        """Handle analysis_complete event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('analysis_complete')
            cycle.update_status(CycleStatus.ANALYSIS_COMPLETE)
            cycle.analysis_duration = cycle.get_event_duration('analysis_complete')
            
            plog.debug(
                f"Analysis complete | cycle_id={cycle_id}, duration={cycle.analysis_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_setup_generated(self, message: Dict[str, Any]):
        """Handle setup_generated event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('setup_generated')
            cycle.update_status(CycleStatus.SETUP_GENERATED)
            cycle.strategy_duration = cycle.get_event_duration('setup_generated')
            
            plog.debug(
                f"Setup generated | cycle_id={cycle_id}, duration={cycle.strategy_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_trade_approved(self, message: Dict[str, Any]):
        """Handle trade_approved event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('trade_approved')
            cycle.update_status(CycleStatus.TRADE_APPROVED)
            cycle.trade_decision = 'approved'
            cycle.risk_duration = cycle.get_event_duration('trade_approved')
            
            plog.info(
                f"✅ Trade approved | cycle_id={cycle_id}, duration={cycle.risk_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_trade_rejected(self, message: Dict[str, Any]):
        """Handle trade_rejected event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('trade_rejected')
            cycle.update_status(CycleStatus.TRADE_REJECTED)
            cycle.trade_decision = 'rejected'
            cycle.risk_duration = cycle.get_event_duration('trade_rejected')
            
            # Cycle ends here for rejected trades
            cycle.update_status(CycleStatus.CYCLE_COMPLETE)
            self._complete_cycle(cycle_id)
            
            plog.info(
                f"❌ Trade rejected | cycle_id={cycle_id}, reason={message.get('reason')}",
                agent="event_coordinator"
            )
    
    async def _handle_trade_executed(self, message: Dict[str, Any]):
        """Handle trade_executed event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('trade_executed')
            cycle.update_status(CycleStatus.TRADE_EXECUTED)
            cycle.trade_id = message.get('trade_id')
            cycle.execution_duration = cycle.get_event_duration('trade_executed')
            
            plog.success(
                f"🎯 Trade executed | cycle_id={cycle_id}, trade_id={cycle.trade_id}, "
                f"duration={cycle.execution_duration:.1f}s",
                agent="event_coordinator"
            )
    
    async def _handle_cycle_complete(self, message: Dict[str, Any]):
        """Handle cycle_complete event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.add_event('cycle_complete')
            cycle.update_status(CycleStatus.CYCLE_COMPLETE)
            
            self._complete_cycle(cycle_id)
    
    async def _handle_cycle_error(self, message: Dict[str, Any]):
        """Handle cycle_error event"""
        cycle_id = message.get('cycle_id')
        if cycle_id and cycle_id in self.active_cycles:
            cycle = self.active_cycles[cycle_id]
            cycle.update_status(CycleStatus.ERROR)
            cycle.error = message.get('error', 'Unknown error')
            
            self._complete_cycle(cycle_id)
            
            plog.error(
                f"Cycle error | cycle_id={cycle_id}, error={cycle.error}",
                agent="event_coordinator"
            )
    
    # Public API
    
    async def get_cycle_status(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific cycle"""
        if cycle_id in self.active_cycles:
            return self.active_cycles[cycle_id].to_dict()
        
        # Check completed cycles
        for cycle in reversed(self.completed_cycles):
            if cycle.cycle_id == cycle_id:
                return cycle.to_dict()
        
        return None
    
    async def get_active_cycles(self) -> List[Dict[str, Any]]:
        """Get all active cycles"""
        return [cycle.to_dict() for cycle in self.active_cycles.values()]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get coordinator statistics"""
        return self.statistics.to_dict()
    
    async def wait_for_completion(self, cycle_id: str, timeout: int = 300) -> Optional[Dict[str, Any]]:
        """
        Wait for a specific cycle to complete (blocking)
        
        Args:
            cycle_id: Cycle to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            Cycle state dict or None if timeout
        """
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # Check if cycle completed
            if cycle_id not in self.active_cycles:
                # Find in completed cycles
                for cycle in reversed(self.completed_cycles):
                    if cycle.cycle_id == cycle_id:
                        return cycle.to_dict()
                return None
            
            # Wait a bit
            await asyncio.sleep(1)
        
        # Timeout
        return None
