"""
Agent Health Monitor
Tracks agent heartbeats and system status
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager

logger = logging.getLogger(__name__)

class AgentHealthMonitor:
    """
    Monitors the health of all agents in the system.
    Tracks heartbeats and publishes health status updates.
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        check_interval: int = 5,
        heartbeat_timeout: int = 60
    ):
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.check_interval = check_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.running = False
        self.monitor_task = None
        
        # Track known agents (name -> instance)
        self.agents: Dict[str, Any] = {}
        
    def register_agent(self, agent_name: str, agent_instance: Any):
        """Register an agent for monitoring and potential restart"""
        self.agents[agent_name] = agent_instance
        logger.info(f"Registered {agent_name} for health monitoring")
        
    async def start(self):
        """Start the health monitor"""
        if self.running:
            return
            
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Agent Health Monitor started")
        
    async def stop(self):
        """Stop the health monitor"""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Agent Health Monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                health_status = await self._check_health()
                
                # Publish health update
                await self.message_bus.publish(
                    "system_health",
                    health_status
                )
                
                # Check for restarts
                await self._handle_restarts(health_status)
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _handle_restarts(self, health_status: Dict[str, Any]):
        """Handle agent restarts if needed"""
        agents_status = health_status.get("agents", {})
        
        for agent_name, status_data in agents_status.items():
            if status_data["status"] == "down" and agent_name in self.agents:
                # Only restart if we have the instance
                logger.warning(f"Agent {agent_name} is DOWN. Attempting restart...")
                await self._restart_agent(agent_name, self.agents[agent_name])

    async def _restart_agent(self, agent_name: str, agent_instance: Any):
        """Restart a failed agent"""
        try:
            logger.warning(f"Stopping {agent_name}...")
            await agent_instance.stop()
            
            await asyncio.sleep(2)
            
            logger.warning(f"Starting {agent_name}...")
            await agent_instance.start()
            
            logger.info(f"Successfully restarted {agent_name}")
            
            # Publish restart event
            await self.message_bus.publish("system_notifications", {
                "type": "agent_restart",
                "agent": agent_name,
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            logger.error(f"Failed to restart {agent_name}: {e}")
            
    async def _check_health(self) -> Dict[str, Any]:
        """Check health of all agents"""
        agent_statuses = {}
        system_status = "healthy"
        
        now = datetime.now(timezone.utc)
        
        # Check all registered agents, plus any known ones from state
        # For now, iterate over registered agents
        agents_to_check = list(self.agents.keys())
        if not agents_to_check:
             # Fallback to default list if no agents registered yet
             agents_to_check = [
                "data_agent", "analysis_agent", "strategy_agent", 
                "risk_agent", "execution_agent", "orchestrator"
            ]
        
        for agent_name in agents_to_check:
            # Get agent state from state manager
            agent_state = await self.state_manager.get_agent_state(agent_name)

            
            status = "unknown"
            details = "No heartbeat received"
            latency = 0
            
            if agent_state:
                last_heartbeat = agent_state.get('last_heartbeat')
                current_state = agent_state.get('state', 'unknown')
                
                if last_heartbeat:
                    if isinstance(last_heartbeat, str):
                        try:
                            last_heartbeat = datetime.fromisoformat(last_heartbeat)
                        except ValueError:
                            pass
                    
                    if isinstance(last_heartbeat, datetime):
                        # Ensure timezone awareness
                        if last_heartbeat.tzinfo is None:
                            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
                            
                        time_diff = (now - last_heartbeat).total_seconds()
                        latency = round(time_diff * 1000)  # ms
                        
                        if time_diff < self.heartbeat_timeout:
                            status = "healthy"
                            details = f"Active (State: {current_state})"
                        elif time_diff < self.heartbeat_timeout * 2:
                            status = "degraded"
                            details = f"Slow heartbeat ({int(time_diff)}s ago)"
                            if system_status == "healthy":
                                system_status = "degraded"
                        else:
                            status = "down"
                            details = f"Unresponsive ({int(time_diff)}s ago)"
                            system_status = "unhealthy"
                    else:
                        status = "unknown"
                        details = "Invalid heartbeat format"
                else:
                    status = "down"
                    details = "No heartbeat recorded"
                    if system_status == "healthy":
                        system_status = "degraded"
            else:
                status = "down"
                details = "Not registered"
                if system_status == "healthy":
                    system_status = "degraded"
            
            agent_statuses[agent_name] = {
                "status": status,
                "details": details,
                "latency_ms": latency,
                "last_updated": now.isoformat()
            }
            
        return {
            "system_status": system_status,
            "agents": agent_statuses,
            "timestamp": now.isoformat()
        }
