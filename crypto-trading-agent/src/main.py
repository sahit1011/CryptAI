"""
Main Entry Point for Multi-Agent Crypto Trading System
Initializes and coordinates all system components
"""
import asyncio
import signal
import sys
import os
from datetime import datetime
from typing import Optional
from loguru import logger

from dotenv import load_dotenv

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.core.orchestrator import TradingOrchestrator
from src.agents.data_agent import DataCollectionAgent
from src.agents.analysis_agent import MarketAnalysisAgent
from src.agents.strategy_agent import StrategyGenerationAgent
from src.agents.risk_agent import RiskManagementAgent
from src.agents.memory_agent import MemoryAgent
from src.execution.execution_agent import ExecutionAgent
from src.execution.paper_trading_engine import PaperTradingEngine
from src.utils.pipeline_logger import PipelineLogger
from src.utils.config import get_config

# Load environment variables
load_dotenv()

plog = PipelineLogger()


class TradingSystem:
    """
    Main Trading System
    
    Coordinates all components:
    - Infrastructure (MessageBus, StateManager, Database)
    - Agents (Data, Analysis, Strategy, Risk, Execution, Memory)
    - Orchestrator (LangGraph workflow coordinator)
    """
    
    def __init__(self):
        self.config = get_config()
        self.running = False
        
        # Infrastructure
        self.message_bus: Optional[MessageBus] = None
        self.state_manager: Optional[StateManager] = None
        
        # Agents
        self.data_agent: Optional[DataCollectionAgent] = None
        self.analysis_agent: Optional[MarketAnalysisAgent] = None
        self.strategy_agent: Optional[StrategyGenerationAgent] = None
        self.risk_agent: Optional[RiskManagementAgent] = None
        self.memory_agent: Optional[MemoryAgent] = None
        self.execution_agent: Optional[ExecutionAgent] = None

        # Trading engine (paper by default; live path is hard-gated in ExecutionAgent)
        self.paper_engine: Optional[PaperTradingEngine] = None

        # Orchestrator
        self.orchestrator: Optional[TradingOrchestrator] = None
        
        plog.info(
            "Trading System initialized",
            agent="system",
            phase="initialization"
        )
    
    async def initialize_infrastructure(self):
        """Initialize core infrastructure"""
        plog.info("🔧 Initializing infrastructure...", agent="system", phase="startup")
        
        try:
            # Initialize Message Bus (redis_url is required — read from config, which
            # falls back to redis://localhost:6379). Previously called with no args,
            # which raised TypeError and aborted startup before anything ran.
            plog.info("  ├─ Initializing Message Bus", agent="system")
            self.message_bus = MessageBus(redis_url=self.config.database.redis_url)
            await self.message_bus.connect()
            
            # Initialize State Manager
            plog.info("  ├─ Initializing State Manager", agent="system")
            self.state_manager = StateManager()
            await self.state_manager.connect()
            
            # Perform state recovery
            plog.info("  ├─ Recovering system state", agent="system")
            await self.state_manager.perform_state_recovery()
            
            plog.info("  └─ ✅ Infrastructure ready", agent="system")
            
        except Exception as e:
            plog.error(f"❌ Infrastructure initialization failed: {e}", agent="system")
            raise
    
    async def initialize_agents(self):
        """Initialize all trading agents"""
        plog.info("🤖 Initializing agents...", agent="system", phase="startup")
        
        try:
            # Get configuration
            openai_api_key = os.getenv("OPENAI_API_KEY")
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            database_url = os.getenv("DATABASE_URL", "sqlite:///./trading_data.db")
            
            # Initialize Data Agent. Exchange/symbols come from config, not kwargs —
            # DataCollectionAgent(__init__) only accepts (message_bus, state_manager).
            plog.info("  ├─ Initializing Data Agent", agent="system")
            self.data_agent = DataCollectionAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager
            )
            await self.data_agent.start()
            
            # Initialize Analysis Agent
            plog.info("  ├─ Initializing Analysis Agent", agent="system")
            self.analysis_agent = MarketAnalysisAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key
            )
            await self.analysis_agent.start()
            
            # Initialize Strategy Agent
            plog.info("  ├─ Initializing Strategy Agent", agent="system")
            self.strategy_agent = StrategyGenerationAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                openai_api_key=openai_api_key
            )
            await self.strategy_agent.start()
            
            # Initialize Risk Agent
            plog.info("  ├─ Initializing Risk Agent", agent="system")
            self.risk_agent = RiskManagementAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                initial_balance=float(os.getenv("INITIAL_BALANCE", "10000")),
                llm_api_key=openai_api_key
            )
            await self.risk_agent.start()
            
            # Initialize Memory Agent
            plog.info("  ├─ Initializing Memory Agent", agent="system")
            self.memory_agent = MemoryAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                database_url=database_url,
                openai_api_key=openai_api_key,
                initial_capital=float(os.getenv("INITIAL_BALANCE", "10000"))
            )
            await self.memory_agent.start()

            # Initialize Execution Agent. Without this the orchestrator's
            # execute_trade node publishes to execution_agent_inbox with no
            # subscriber, so every approved trade times out into the void.
            #
            # Mode selection:
            #   ENABLE_EXECUTION=false            -> paper trading (default, safe)
            #   ENABLE_EXECUTION=true             -> live path (BingX). The live path
            #     is still hard-gated inside ExecutionAgent._init_components, which
            #     refuses mainnet unless LIVE_TRADING_CONFIRMED=true, so enabling
            #     execution against USE_TESTNET=true is the only path that trades.
            plog.info("  ├─ Initializing Execution Agent", agent="system")
            self.paper_engine = PaperTradingEngine(
                initial_balance=float(os.getenv("INITIAL_BALANCE", "10000")),
                message_bus=self.message_bus,
                state_manager=self.state_manager
            )
            try:
                await self.paper_engine.restore_from_historical_trades(
                    self.config.database.postgres_url
                )
                await self.paper_engine.publish_initial_state()
            except Exception as e:
                plog.warning(f"Paper engine state restore skipped: {e}", agent="system")

            realtime_trading = os.getenv("ENABLE_EXECUTION", "false").lower() == "true"
            execution_config = {
                "EXCHANGE_NAME": os.getenv("EXCHANGE_NAME", "bingx"),
                "API_KEY": os.getenv("BINGX_API_KEY", ""),
                "API_SECRET": os.getenv("BINGX_SECRET_KEY", ""),
                "USE_TESTNET": os.getenv("USE_TESTNET", "true").lower() == "true",
                "LIVE_TRADING_CONFIRMED": os.getenv("LIVE_TRADING_CONFIRMED", "false"),
            }
            self.execution_agent = ExecutionAgent(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                config=execution_config,
                paper_trading_engine=self.paper_engine,
                realtime_trading=realtime_trading
            )
            # Wire the shared portfolio tracker so start() can reconcile persisted
            # risk state against the exchange before monitoring begins.
            portfolio_tracker = getattr(self.risk_agent, "portfolio_tracker", None)
            if portfolio_tracker is not None:
                self.execution_agent.set_portfolio_tracker(portfolio_tracker)
            await self.execution_agent.start()

            plog.info("  └─ ✅ All agents ready", agent="system")
            
        except Exception as e:
            plog.error(f"❌ Agent initialization failed: {e}", agent="system")
            raise
    
    async def initialize_orchestrator(self):
        """Initialize LangGraph orchestrator"""
        plog.info("🎯 Initializing orchestrator...", agent="system", phase="startup")
        
        try:
            symbol = os.getenv("TRADING_SYMBOL", "BTCUSDT")
            cycle_interval = int(os.getenv("CYCLE_INTERVAL", "180"))  # 3 minutes
            
            self.orchestrator = TradingOrchestrator(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                symbol=symbol,
                cycle_interval=cycle_interval
            )
            
            plog.info(
                f"  └─ ✅ Orchestrator ready | symbol={symbol} | cycle={cycle_interval}s",
                agent="system"
            )
            
        except Exception as e:
            plog.error(f"❌ Orchestrator initialization failed: {e}", agent="system")
            raise
    
    async def start(self):
        """Start the trading system"""
        if self.running:
            plog.warning("System already running", agent="system")
            return
        
        plog.info(
            "🚀 Starting Multi-Agent Crypto Trading System",
            agent="system",
            phase="startup"
        )
        plog.info("=" * 60, agent="system")
        
        try:
            # Initialize infrastructure
            await self.initialize_infrastructure()
            
            # Initialize agents
            await self.initialize_agents()
            
            # Initialize orchestrator
            await self.initialize_orchestrator()
            
            # Start orchestrator
            await self.orchestrator.start()
            
            self.running = True
            
            plog.info("=" * 60, agent="system")
            plog.info(
                "✅ System started successfully",
                agent="system",
                phase="startup_complete"
            )
            plog.info(
                f"📊 Trading {os.getenv('TRADING_SYMBOL', 'BTCUSDT')} with {os.getenv('CYCLE_INTERVAL', '180')}s cycles",
                agent="system"
            )
            plog.info("=" * 60, agent="system")
            
        except Exception as e:
            plog.error(f"❌ System startup failed: {e}", agent="system")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the trading system"""
        if not self.running:
            return
        
        plog.info(
            "🛑 Stopping Multi-Agent Crypto Trading System",
            agent="system",
            phase="shutdown"
        )
        
        try:
            # Stop orchestrator
            if self.orchestrator:
                plog.info("  ├─ Stopping orchestrator", agent="system")
                await self.orchestrator.stop()
            
            # Stop agents (execution first so in-flight orders are handled before
            # its dependencies — data/state — are torn down).
            plog.info("  ├─ Stopping agents", agent="system")
            agents = [
                self.execution_agent,
                self.memory_agent,
                self.risk_agent,
                self.strategy_agent,
                self.analysis_agent,
                self.data_agent
            ]
            
            for agent in agents:
                if agent:
                    await agent.stop()
            
            # Disconnect infrastructure
            plog.info("  ├─ Disconnecting infrastructure", agent="system")
            if self.state_manager:
                await self.state_manager.disconnect()
            
            if self.message_bus:
                await self.message_bus.disconnect()
            
            self.running = False
            
            plog.info("  └─ ✅ System stopped", agent="system", phase="shutdown_complete")
            
        except Exception as e:
            plog.error(f"❌ Error during shutdown: {e}", agent="system")
    
    async def run_forever(self):
        """Run the system indefinitely"""
        await self.start()
        
        try:
            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            plog.info("Received interrupt signal", agent="system")
        finally:
            await self.stop()
    
    def get_system_status(self) -> dict:
        """Get system status"""
        return {
            "running": self.running,
            "infrastructure": {
                "message_bus": self.message_bus is not None,
                "state_manager": self.state_manager is not None
            },
            "agents": {
                "data": self.data_agent is not None and self.data_agent.running,
                "analysis": self.analysis_agent is not None and self.analysis_agent.running,
                "strategy": self.strategy_agent is not None and self.strategy_agent.running,
                "risk": self.risk_agent is not None and self.risk_agent.running,
                "memory": self.memory_agent is not None and self.memory_agent.running
            },
            "orchestrator": self.orchestrator.get_stats() if self.orchestrator else None
        }


async def main():
    """Main entry point"""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "logs/trading_system_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG"
    )
    
    # Create trading system
    system = TradingSystem()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        plog.info("Received shutdown signal", agent="system")
        asyncio.create_task(system.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run system
    try:
        await system.run_forever()
    except Exception as e:
        plog.error(f"Fatal error: {e}", agent="system")
        await system.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
