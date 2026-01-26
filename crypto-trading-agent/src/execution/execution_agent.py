"""
Execution Agent Core
Orchestrates trade execution, monitoring, and error handling
"""
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
import asyncio
import os

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.execution.exchange_client import ExchangeClientFactory, ExchangeClient, OrderStatus
from src.execution.order_manager import OrderManager, TradeExecution, ExecutionStrategy
from src.execution.order_tracker import OrderTracker
from src.execution.position_monitor import PositionMonitor
from src.execution.error_handler import RetryHandler, CircuitBreaker
from src.execution.emergency_exit import EmergencyExit
from src.execution.pending_trades_queue import PendingTradesQueue, PendingTrade
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class ExecutionAgent(BaseAgent):
    """
    Execution Agent
    
    Responsibilities:
    - Receive trade setups from Risk Agent (via orchestrator)
    - Execute trades via Order Manager
    - Monitor active positions
    - Handle errors and emergencies
    - Report status
    
    Message Handlers:
    - execute_trade: Execute approved trade setup
    - get_positions: Get current positions
    - close_position: Close a specific position
    - panic_close: Emergency close all positions
    """

    def __init__(
        self, 
        message_bus: MessageBus,
        state_manager: StateManager,
        config: Dict[str, Any] = None,
        paper_trading_engine: Optional[Any] = None,
        realtime_trading: bool = False
    ):
        # Initialize BaseAgent
        super().__init__(
            name="execution_agent",
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        self.config = config or {}
        self.paper_trading_engine = paper_trading_engine
        self.realtime_trading = realtime_trading
        
        # Initialize components
        self._init_components()
        
        # Pending trades queue for managing unfilled limit orders
        self.pending_trades_queue = PendingTradesQueue()
        
        # Pending trades monitor task
        self.pending_monitor_task = None
        
        # Statistics
        self.trades_executed = 0
        self.trades_failed = 0
        
        mode = "LIVE TRADING" if realtime_trading else "PAPER TRADING"
        plog.info(
            f"Execution Agent initialized | Mode: {mode}",
            agent="execution_agent",
            phase="initialization"
        )
    
    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("execute_trade", self._handle_execute_trade)
        self.register_handler("get_positions", self._handle_get_positions)
        self.register_handler("close_position", self._handle_close_position)
        self.register_handler("panic_close", self._handle_panic_close)
        self.register_handler("get_status", self._handle_get_status)
    
    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """
        Process incoming message
        
        Sends responses back to orchestrator for sequential execution
        """
        handler = self.handlers.get(message.type)
        
        if handler:
            result = await handler(message.payload)
            
            # Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                # Ensure result has success flag
                if isinstance(result, dict) and 'success' not in result:
                    result['success'] = result.get('status') == 'success'
                
                # CRITICAL FIX: Pass correlation_id so orchestrator can match response to request
                await self.send_response(result, correlation_id=message.correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={message.correlation_id})",
                    agent="execution_agent"
                )
            
            return result
        else:
            plog.warning(
                f"No handler for message type: {message.type}",
                agent="execution_agent"
            )
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                # CRITICAL FIX: Pass correlation_id for error responses too
                await self.send_response(error_response, correlation_id=message.correlation_id)
                
            return None
    
    def _init_components(self):
        """Initialize all sub-components"""
        
        # 1. Exchange Client - Use Paper Trading Engine or Real Exchange
        if self.realtime_trading:
            # LIVE TRADING MODE - Connect to real BingX API
            plog.info("🔴 Initializing LIVE trading with BingX API", agent="execution_agent")
            exchange_name = self.config.get('EXCHANGE_NAME', 'bingx')
            api_key = self.config.get('API_KEY', os.getenv('BINGX_API_KEY', ''))
            api_secret = self.config.get('API_SECRET', os.getenv('BINGX_SECRET_KEY', ''))
            testnet = self.config.get('USE_TESTNET', True)
            
            self.exchange = ExchangeClientFactory.create_client(
                exchange_name=exchange_name,
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )
        else:
            # PAPER TRADING MODE - Use Paper Trading Engine
            plog.info("📄 Initializing PAPER trading mode", agent="execution_agent")
            if not self.paper_trading_engine:
                raise ValueError("Paper Trading Engine required when realtime_trading=False")
            
            # Use paper trading engine as the exchange client
            self.exchange = self.paper_trading_engine
        
        # 2. Order Manager
        self.order_manager = OrderManager(self.exchange)
        
        # 3. Order Tracker (only for live trading)
        if self.realtime_trading:
            self.order_tracker = OrderTracker(self.exchange)
        else:
            self.order_tracker = None  # Not needed for paper trading
        
        # 4. Position Monitor
        self.position_monitor = PositionMonitor()
        
        # 5. Emergency Exit (only for live trading)
        if self.realtime_trading:
            self.emergency_exit = EmergencyExit(
                self.exchange,
                self.position_monitor,
                self.order_tracker
            )
        else:
            self.emergency_exit = None  # Not needed for paper trading
        
        # 6. Error Handling
        self.retry_handler = RetryHandler()
        self.circuit_breaker = CircuitBreaker()
        
        # Wire up callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup component interactions"""
        
        # Position Monitor -> Order Manager
        # When TP hit, trigger partial close logic
        self.position_monitor.on_take_profit(self._handle_tp_trigger)
        
        # Position Monitor -> Risk Agent (via callback or queue)
        self.position_monitor.on_stop_loss(self._handle_sl_trigger)
    
    async def start(self):
        """Start the agent"""
        # Call BaseAgent start first
        await super().start()
        
        # Start sub-components (only if they exist)
        if self.order_tracker:
            await self.order_tracker.start()
        
        # Start position monitoring loop (for both paper and live trading)
        self.monitor_task = asyncio.create_task(self._position_monitor_loop())
        
        # Start pending trades monitoring loop
        self.pending_monitor_task = asyncio.create_task(self._pending_trades_monitor_loop())
        
        mode = "LIVE" if self.realtime_trading else "PAPER"
        plog.info(f"Execution Agent started in {mode} mode", agent="execution_agent")
        plog.info("Position monitoring loop started (5s interval)", agent="execution_agent")
        plog.info("Pending trades monitor started (5s interval)", agent="execution_agent")
    
    async def _position_monitor_loop(self):
        """
        Continuously monitor open positions for SL/TP triggers
        Runs every 5 seconds for both paper and live trading
        """
        logger.info("Position monitoring loop started (5s interval)")
        
        last_activity_log = 0
        log_interval = 10  # Log activity every 10 seconds to avoid spam
        
        while self.running:
            try:
                # Get all open positions from paper trading engine
                if not self.realtime_trading and self.paper_trading_engine:
                    positions = self.paper_trading_engine.get_positions()
                    
                    # CRITICAL FIX: Bidirectional sync between PaperTradingEngine and PositionMonitor
                    # This prevents "ghost" positions from being monitored after they're closed
                    
                    # Get current monitored positions
                    monitored_positions = self.position_monitor.get_positions()
                    monitored_ids = [p.position_id for p in monitored_positions]
                    
                    # Get current active position IDs from paper trading engine
                    active_position_ids = [pos.get('position_id') or pos.get('symbol') for pos in positions]
                    
                    # 1. ADD new positions to PositionMonitor
                    for pos in positions:
                        pos_id = pos.get('position_id') or pos.get('symbol')
                        
                        if pos_id not in monitored_ids:
                            logger.info(f"🔄 Syncing position {pos['symbol']} ({pos_id}) to PositionMonitor")
                            
                            # Add to PositionMonitor
                            self.position_monitor.add_position(
                                position_id=pos_id,
                                symbol=pos['symbol'],
                                side=pos['positionSide'],
                                quantity=float(pos['positionAmt']),
                                entry_price=float(pos['entryPrice']),
                                stop_loss=0.0, # We might need to fetch SL/TP from DB if not in PaperPosition
                                take_profit_levels=[],
                                trailing_stop_distance=None
                            )
                    
                    # 2. REMOVE closed positions from PositionMonitor
                    for monitored_pos in monitored_positions:
                        if monitored_pos.position_id not in active_position_ids:
                            logger.info(f"🗑️ Removing closed position {monitored_pos.symbol} ({monitored_pos.position_id}) from PositionMonitor")
                            self.position_monitor.remove_position(monitored_pos.position_id)
                    
                    # Always log monitoring activity periodically, even if no positions (to show agent is alive)
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_activity_log > log_interval:
                        if positions:
                            # Log detailed monitoring for active positions
                            for position in positions:
                                symbol = position['symbol']
                                pnl = float(position.get('unRealizedProfit', 0))
                                await self.publish_activity(
                                    action="monitoring_position",
                                    message=f"Monitoring {symbol} | P&L: ${pnl:+.2f}",
                                    phase="execution",
                                    severity="info",
                                    metadata={
                                        "symbol": symbol,
                                        "unrealized_pnl": pnl
                                    }
                                )
                        else:
                            # Log heartbeat if no positions
                            await self.publish_activity(
                                action="monitoring_idle",
                                message="Monitoring active positions (No open trades)",
                                phase="execution",
                                severity="info",
                                metadata={"status": "idle"}
                            )
                        last_activity_log = current_time
                    
                    if positions:
                        for position in positions:
                            symbol = position['symbol']
                            
                            # Get current price from state manager
                            # This now gets updated by server.py as well for redundancy
                            current_price = await self.state_manager.get(f"current_price:{symbol}")
                            
                            if current_price:
                                current_price = float(current_price)
                                
                                # Update position P&L
                                await self.paper_trading_engine.update_positions(symbol, current_price)
                                
                                # Check for SL/TP triggers
                                await self.paper_trading_engine.check_limit_orders(symbol, current_price)
                                
                                logger.debug(
                                    f"Monitoring position {symbol}: "
                                    f"Price=${current_price:.2f}, "
                                    f"P&L=${position.get('unRealizedProfit', 0)}"
                                )

                
                # Wait 5 seconds before next check
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                logger.info("Position monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                # Log error to feed so user knows something is wrong
                try:
                    await self.publish_activity(
                        action="monitoring_error",
                        message=f"Monitoring error: {str(e)}",
                        phase="execution",
                        severity="error",
                        metadata={"error": str(e)}
                    )
                except:
                    pass
                await asyncio.sleep(5)  # Continue even on error

    
    async def stop(self):
        """Stop the agent and cleanup all pending orders"""
        plog.info("🛑 Stopping Execution Agent...", agent="execution_agent")
        
        # CRITICAL: Cancel all pending limit orders before shutdown
        if hasattr(self, 'pending_trades_queue'):
            pending_trades = self.pending_trades_queue.get_all_pending()
            if pending_trades:
                plog.warning(
                    f"🚨 Cancelling {len(pending_trades)} pending limit order(s) during shutdown...",
                    agent="execution_agent"
                )
                
                for pending_trade in pending_trades:
                    try:
                        await self._cancel_pending_trade(
                            pending_trade.symbol,
                            reason="System Shutdown"
                        )
                        plog.info(
                            f"✅ Cancelled pending order: {pending_trade.symbol} @ ${pending_trade.entry_price:.2f}",
                            agent="execution_agent"
                        )
                    except Exception as e:
                        plog.error(
                            f"Failed to cancel pending order {pending_trade.symbol}: {e}",
                            agent="execution_agent"
                        )
                
                # Clear the queue
                self.pending_trades_queue.clear()
                plog.info("✅ All pending trades cancelled and queue cleared", agent="execution_agent")
            else:
                plog.info("No pending trades to cancel", agent="execution_agent")
        
        # Stop position monitoring
        if hasattr(self, 'monitor_task'):
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            plog.info("Position monitoring stopped", agent="execution_agent")
        
        # Stop pending trades monitoring
        if hasattr(self, 'pending_monitor_task') and self.pending_monitor_task:
            self.pending_monitor_task.cancel()
            try:
                await self.pending_monitor_task
            except asyncio.CancelledError:
                pass
            plog.info("Pending trades monitor stopped", agent="execution_agent")
        
        # Stop sub-components (only if they exist)
        if self.order_tracker:
            await self.order_tracker.stop()
        
        # Close exchange connection (only for live trading)
        if self.realtime_trading and hasattr(self.exchange, 'close'):
            await self.exchange.close()
        
        # Call BaseAgent stop
        await super().stop()
        
        plog.info("✅ Execution Agent stopped cleanly", agent="execution_agent")

    
    async def _handle_execute_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle execute_trade message from orchestrator
        
        Enhanced with pending trades queue logic:
        1. Check if we have an active position → Reject new trades
        2. Determine execution strategy (MARKET vs LIMIT)
        3. If MARKET → Execute immediately, cancel any pending trades
        4. If LIMIT → Check pending queue, replace if higher confidence
        
        Payload should contain the approved trade setup from risk agent
        """
        # Extract trade setup (might be nested)
        setup = payload.get('trade_setup', payload)
        
        symbol = setup.get('symbol', 'UNKNOWN')
        direction = setup.get('direction', 'UNKNOWN')
        entry_price = setup.get('entry_price', 0)
        confidence = setup.get('confidence_score', 0.0)
        
        plog.info(
            f"📥 Execution Agent received trade: {symbol} {direction} @ ${entry_price:.2f} "
            f"(Confidence: {confidence:.3f})",
            agent="execution_agent",
            phase="trade_execution"
        )
        
        # Publish activity
        await self.publish_activity(
            action="executing_trade",
            message=f"Executing {direction} trade for {symbol}",
            phase="execution",
            severity="info",
            metadata={
                "symbol": symbol,
                "direction": direction,
                "entry": entry_price,
                "confidence": confidence
            }
        )

        
        if not self.running:
            plog.error(
                "❌ Execution Agent is not running - cannot execute trade",
                agent="execution_agent"
            )
            return {
                'status': 'failed',
                'error': 'Agent is not running',
                'success': False
            }
            
        # CRITICAL CHECK: Active positions (MARKET orders filled)
        # Don't open new trades if one is already active
        active_positions = self.position_monitor.get_positions()
        if len(active_positions) > 0:
            plog.warning(
                f"⚠️ Cannot execute new trade - {len(active_positions)} active position(s) already exist",
                agent="execution_agent"
            )
            return {
                'status': 'rejected',
                'reason': 'active_position_exists',
                'error': 'Active position already exists',
                'success': False
            }
        
        if not self.circuit_breaker.can_execute():
            plog.error(
                "🚨 Circuit breaker OPEN - execution suspended",
                agent="execution_agent"
            )
            return {
                'status': 'failed',
                'error': 'Circuit breaker open - execution suspended',
                'success': False
            }
        
        plog.info(
            f"🚀 Starting trade execution for {symbol} {direction}",
            agent="execution_agent"
        )
        
        try:
            # CRITICAL FIX: Convert take_profit 'percentage' to 'size' for Order Manager
            total_quantity = setup.get('position_size', setup.get('recommended_position_size', 0))
            take_profit_raw = setup.get('take_profits', setup.get('take_profit_levels', []))
            
            # Convert percentage to size
            take_profit_levels = []
            for tp in take_profit_raw:
                if isinstance(tp, dict):
                    # If 'size' already exists, use it; otherwise convert 'percentage' to 'size'
                    if 'size' in tp:
                        take_profit_levels.append(tp)
                    elif 'percentage' in tp:
                        pct = float(tp['percentage'])
                        # Normalize percentage if > 1 (e.g. 33 -> 0.33)
                        if pct > 1.0:
                            pct = pct / 100.0
                            
                        take_profit_levels.append({
                            'price': tp['price'],
                            'size': total_quantity * pct
                        })
                    else:
                        # Fallback: assume equal distribution
                        take_profit_levels.append({
                            'price': tp.get('price', 0),
                            'size': total_quantity / len(take_profit_raw)
                        })
            
            # CRITICAL: Determine execution strategy based on current price vs entry price
            strategy = await self._determine_execution_strategy(
                symbol=setup['symbol'],
                direction=setup['direction'],
                entry_price=setup['entry_price']
            )
            
            plog.info(
                f"📋 Execution strategy selected: {strategy.value}",
                agent="execution_agent"
            )
            
            # ============================================================================
            # CRITICAL DECISION POINT: MARKET vs LIMIT
            # ============================================================================
            
            if strategy == ExecutionStrategy.IMMEDIATE:
                # ========== MARKET ORDER PATH ==========
                # Execute immediately, no queue
                plog.info("✅ MARKET order strategy → Executing immediately", agent="execution_agent")
                
                # Check if we have a pending trade for this symbol → Cancel it
                if self.pending_trades_queue.has_pending_trade(symbol):
                    plog.info(
                        f"🔄 Cancelling existing pending trade to execute MARKET order",
                        agent="execution_agent"
                    )
                    await self._cancel_pending_trade(symbol, reason="Replacing with MARKET order")
                
                # Execute trade immediately
                execution = await self.retry_handler.execute_with_retry(
                    self.order_manager.execute_trade_setup,
                    symbol=setup['symbol'],
                    direction=setup['direction'],
                    entry_price=setup['entry_price'],
                    stop_loss_price=setup['stop_loss'],
                    take_profit_levels=take_profit_levels,
                    total_quantity=total_quantity,
                    strategy=ExecutionStrategy.IMMEDIATE
                )
                
                plog.info(
                    f"✅ Order Manager execution complete - ID: {execution.execution_id}",
                    agent="execution_agent"
                )
                
                # Register with Position Monitor
                plog.info(
                    f"📌 Registering position with Position Monitor...",
                    agent="execution_agent"
                )
                self.position_monitor.add_position(
                    position_id=execution.execution_id,
                    symbol=execution.symbol,
                    side=execution.direction,
                    quantity=total_quantity,
                    entry_price=execution.entry_order.average_price if execution.entry_order else setup['entry_price'],
                    stop_loss=execution.stop_loss_price,
                    take_profit_levels=execution.take_profit_prices,
                    trailing_stop_distance=setup.get('trailing_stop_distance')
                )
                
                # Track orders (only for live trading)
                if self.order_tracker:
                    plog.info(
                        f"📋 Tracking orders with Order Tracker...",
                        agent="execution_agent"
                    )
                    if execution.entry_order:
                        self.order_tracker.track_order(execution.entry_order)
                        plog.info(f"  ✓ Entry order tracked: {execution.entry_order.order_id}", agent="execution_agent")
                    if execution.stop_loss_order:
                        self.order_tracker.track_order(execution.stop_loss_order)
                        plog.info(f"  ✓ Stop loss order tracked: {execution.stop_loss_order.order_id}", agent="execution_agent")
                    for tp_order in execution.take_profit_orders:
                        self.order_tracker.track_order(tp_order)
                        plog.info(f"  ✓ Take profit order tracked: {tp_order.order_id}", agent="execution_agent")
                
                self.circuit_breaker.record_success()
                self.trades_executed += 1
                
                avg_price = execution.entry_order.average_price if execution.entry_order else 0
                plog.success(
                    f"🎉 Trade execution SUCCESSFUL - {symbol} {direction} @ ${avg_price:.2f} | "
                    f"Execution ID: {execution.execution_id}",
                    agent="execution_agent"
                )
                
                await self.publish_activity(
                    action="trade_executed",
                    message=f"Trade executed: {symbol} {direction} @ ${avg_price:.2f}",
                    phase="execution",
                    severity="success",
                    metadata={
                        "execution_id": execution.execution_id,
                        "price": avg_price,
                        "size": total_quantity
                    }
                )

                
                # CRITICAL FIX: Publish portfolio update for paper trading
                if not self.realtime_trading and self.paper_trading_engine:
                    await self.paper_trading_engine.publish_portfolio_update()
                    plog.info("📊 Published portfolio update to frontend", agent="execution_agent")
                
                # Publish to execution_status channel for frontend
                await self.message_bus.publish(
                    "execution_status",
                    {
                        "type": "trade_executed",
                        "payload": {
                            "symbol": symbol,
                            "direction": direction,
                            "entry_price": avg_price,
                            "execution_id": execution.execution_id,
                            "position_size": total_quantity,
                            "stop_loss": execution.stop_loss_price,
                            "take_profits": execution.take_profit_prices
                        }
                    }
                )
                
                return {
                    'status': 'success',
                    'execution_id': execution.execution_id,
                    'entry_price': avg_price,
                    'symbol': symbol,
                    'direction': direction,
                    'success': True
                }
            
            else:  # ExecutionStrategy.PATIENT (LIMIT order)
                # ========== LIMIT ORDER PATH ==========
                # Add to pending queue
                plog.info("⏳ LIMIT order strategy → Adding to pending trades queue", agent="execution_agent")
                
                # Check if we should replace existing pending trade
                if not self.pending_trades_queue.should_replace(symbol, confidence):
                    plog.info(
                        f"⏭️ Skipping new setup (lower confidence than existing pending trade)",
                        agent="execution_agent"
                    )
                    
                    existing = self.pending_trades_queue.get_pending_trade(symbol)
                    await self.publish_activity(
                        action="trade_rejected",
                        message=f"Lower confidence than pending trade (existing: {existing.confidence_score:.3f}, new: {confidence:.3f})",
                        phase="execution",
                        severity="info",
                        metadata={
                            "symbol": symbol,
                            "existing_confidence": existing.confidence_score,
                            "new_confidence": confidence
                        }
                    )
                    
                    return {
                        'status': 'rejected',
                        'reason': 'lower_confidence_than_pending',
                        'existing_confidence': existing.confidence_score,
                        'new_confidence': confidence,
                        'success': False
                    }
                
                # Cancel existing pending trade if replacing
                if self.pending_trades_queue.has_pending_trade(symbol):
                    await self._cancel_pending_trade(symbol, reason="Replacing with higher confidence setup")
                
                # Place LIMIT order
                plog.info(
                    f"📊 Placing LIMIT order at ${entry_price:.2f}...",
                    agent="execution_agent"
                )
                
                execution = await self.retry_handler.execute_with_retry(
                    self.order_manager.execute_trade_setup,
                    symbol=setup['symbol'],
                    direction=setup['direction'],
                    entry_price=setup['entry_price'],
                    stop_loss_price=setup['stop_loss'],
                    take_profit_levels=take_profit_levels,
                    total_quantity=total_quantity,
                    strategy=ExecutionStrategy.PATIENT  # LIMIT order
                )
                
                # Create pending trade record
                pending_trade = PendingTrade(
                    trade_id=execution.execution_id,
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=setup['stop_loss'],
                    take_profit_levels=take_profit_levels,
                    position_size=total_quantity,
                    confidence_score=confidence,
                    limit_order_id=execution.entry_order.order_id if execution.entry_order else None,
                    order_placed_at=datetime.now(),
                    strategy_type=setup.get('strategy_type', ''),
                    market_regime=setup.get('market_regime', '')
                )
                
                # Add to queue
                self.pending_trades_queue.add_pending_trade(pending_trade)
                
                plog.success(
                    f"✅ LIMIT order placed and added to pending queue | "
                    f"Order ID: {pending_trade.limit_order_id} | Confidence: {confidence:.3f}",
                    agent="execution_agent"
                )
                
                await self.publish_activity(
                    action="pending_trade_added",
                    message=f"LIMIT order at ${entry_price:.2f} (Confidence: {confidence:.3f})",
                    phase="execution",
                    severity="info",
                    metadata={
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": entry_price,
                        "confidence": confidence,
                        "order_id": pending_trade.limit_order_id
                    }
                )
                
                return {
                    'status': 'pending',
                    'execution_id': execution.execution_id,
                    'order_id': pending_trade.limit_order_id,
                    'entry_price': entry_price,
                    'symbol': symbol,
                    'direction': direction,
                    'confidence': confidence,
                    'success': True
                }
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.trades_failed += 1
            plog.error(
                f"❌ Trade execution FAILED: {type(e).__name__}: {str(e)}",
                agent="execution_agent"
            )
            
            await self.publish_activity(
                action="execution_failed",
                message=f"Trade execution failed: {str(e)}",
                phase="execution",
                severity="error",
                metadata={
                    "error": str(e)
                }
            )

            return {
                'status': 'failed',
                'error': str(e),
                'success': False
            }
    
    async def _handle_get_positions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get current positions"""
        positions = self.position_monitor.get_positions()
        return {
            'status': 'success',
            'positions': [pos.to_dict() for pos in positions],
            'success': True
        }
    
    async def _handle_close_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Close a specific position"""
        position_id = payload.get('position_id')
        
        try:
            # Implementation would close the position
            plog.info(f"Closing position: {position_id}", agent="execution_agent")
            return {
                'status': 'success',
                'position_id': position_id,
                'success': True
            }
        except Exception as e:
            plog.error(f"Failed to close position: {e}", agent="execution_agent")
            return {
                'status': 'failed',
                'error': str(e),
                'success': False
            }
    
    async def _handle_panic_close(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger emergency panic close"""
        plog.critical("Triggering Panic Close via Execution Agent", agent="execution_agent")
        
        try:
            await self.emergency_exit.panic_close_all()
            return {
                'status': 'success',
                'message': 'Panic close initiated',
                'success': True
            }
        except Exception as e:
            plog.error(f"Panic close failed: {e}", agent="execution_agent")
            return {
                'status': 'failed',
                'error': str(e),
                'success': False
            }
    
    async def _handle_get_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get execution agent status"""
        return {
            'status': 'success',
            'agent_status': {
                'running': self.running,
                'state': self.state,
                'trades_executed': self.trades_executed,
                'trades_failed': self.trades_failed,
                'circuit_breaker_open': not self.circuit_breaker.can_execute(),
                'active_positions': len(self.position_monitor.get_positions())
            },
            'success': True
        }
    
    async def _handle_tp_trigger(self, position, tp_price):
        """Handle TP trigger from Position Monitor"""
        plog.info(
            f"TP Triggered for {position.symbol} @ {tp_price}",
            agent="execution_agent"
        )
        
        # Notify Order Manager to handle partial close / SL move
        await self.order_manager.on_take_profit_fill(
            execution_id=position.position_id,
            tp_order_id="triggered_by_monitor",
            filled_price=tp_price
        )
    
    async def _handle_sl_trigger(self, position):
        """Handle SL trigger from Position Monitor"""
        plog.warning(
            f"SL Triggered for {position.symbol}",
            agent="execution_agent"
        )
        # Logic to ensure SL order is actually filled or place market close
        pass
    
    async def _determine_execution_strategy(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        tolerance: float = 0.002  # 0.2% tolerance
    ) -> ExecutionStrategy:
        """
        Determine whether to use MARKET or LIMIT order based on current price.
        
        This is CRITICAL for realistic trade execution. Instead of always using market orders,
        we intelligently choose:
        - MARKET order: When current price is already at/near the strategy's entry price
        - LIMIT order: When current price is far from entry, so we wait for the price to reach our level
        
        This mimics how human traders work: they set alerts/limit orders and wait for the right price,
        rather than immediately buying at whatever the current market price is.
        
        Logic:
        - LONG: If current price <= entry price (+ tolerance) → MARKET (price is good, enter now)
                If current price > entry price → LIMIT (wait for pullback to entry level)
        - SHORT: If current price >= entry price (- tolerance) → MARKET (price is good, enter now)
                 If current price < entry price → LIMIT (wait for bounce to entry level)
        
        Args:
            symbol: Trading pair (e.g., 'BTC-USDT')
            direction: 'LONG' or 'SHORT'
            entry_price: Desired entry price from strategy agent
            tolerance: Price tolerance as decimal (0.002 = 0.2%)
        
        Returns:
            ExecutionStrategy.IMMEDIATE (market order) or ExecutionStrategy.PATIENT (limit order)
        """
        # Get current market price from state manager
        current_price = await self.state_manager.get_price(symbol)
        
        if not current_price:
            # Fallback: try alternate symbol format (remove slash)
            symbol_clean = symbol.replace('/', '')
            current_price = await self.state_manager.get_price(symbol_clean)
        
        if not current_price or float(current_price) == 0:
            plog.warning(
                f"⚠️ No current price available for {symbol}, defaulting to MARKET order",
                agent="execution_agent"
            )
            return ExecutionStrategy.IMMEDIATE
        
        current_price = float(current_price)
        price_diff = current_price - entry_price
        price_diff_pct = abs(price_diff) / entry_price
        
        plog.info(
            f"💰 Price Analysis | Current: ${current_price:.2f} | Entry: ${entry_price:.2f} | "
            f"Diff: {price_diff_pct*100:.3f}% | Tolerance: {tolerance*100:.2f}%",
            agent="execution_agent"
        )
        
        # Decision logic based on direction
        if direction == 'LONG':
            if current_price <= entry_price * (1 + tolerance):
                # Price is at or below entry level - good to enter immediately
                plog.info(
                    f"✅ LONG Strategy: Current price (${current_price:.2f}) is at/below entry (${entry_price:.2f}) "
                    f"→ Using MARKET order for immediate execution",
                    agent="execution_agent"
                )
                await self.publish_activity(
                    action="strategy_decision",
                    message=f"MARKET order: Price at entry level (${current_price:.2f})",
                    phase="execution",
                    severity="info"
                )
                return ExecutionStrategy.IMMEDIATE
            else:
                # Price is above entry - wait for pullback
                plog.info(
                    f"⏳ LONG Strategy: Current price (${current_price:.2f}) is above entry (${entry_price:.2f}) "
                    f"→ Using LIMIT order at ${entry_price:.2f} (waiting for pullback)",
                    agent="execution_agent"
                )
                await self.publish_activity(
                    action="strategy_decision",
                    message=f"LIMIT order at ${entry_price:.2f}: Waiting for pullback from ${current_price:.2f}",
                    phase="execution",
                    severity="info"
                )
                return ExecutionStrategy.PATIENT
        
        elif direction == 'SHORT':
            if current_price >= entry_price * (1 - tolerance):
                # Price is at or above entry level - good to enter immediately
                plog.info(
                    f"✅ SHORT Strategy: Current price (${current_price:.2f}) is at/above entry (${entry_price:.2f}) "
                    f"→ Using MARKET order for immediate execution",
                    agent="execution_agent"
                )
                await self.publish_activity(
                    action="strategy_decision",
                    message=f"MARKET order: Price at entry level (${current_price:.2f})",
                    phase="execution",
                    severity="info"
                )
                return ExecutionStrategy.IMMEDIATE
            else:
                # Price is below entry - wait for bounce
                plog.info(
                    f"⏳ SHORT Strategy: Current price (${current_price:.2f}) is below entry (${entry_price:.2f}) "
                    f"→ Using LIMIT order at ${entry_price:.2f} (waiting for bounce)",
                    agent="execution_agent"
                )
                await self.publish_activity(
                    action="strategy_decision",
                    message=f"LIMIT order at ${entry_price:.2f}: Waiting for bounce from ${current_price:.2f}",
                    phase="execution",
                    severity="info"
                )
                return ExecutionStrategy.PATIENT
        
        # Default to immediate if direction is unknown
        plog.warning(
            f"⚠️ Unknown direction '{direction}', defaulting to MARKET order",
            agent="execution_agent"
        )
        return ExecutionStrategy.IMMEDIATE
    
    async def _cancel_pending_trade(self, symbol: str, reason: str = "Cancelled"):
        """
        Cancel a pending trade and remove from queue
        
        Args:
            symbol: Trading symbol
            reason: Reason for cancellation (for logging)
        """
        pending_trade = self.pending_trades_queue.get_pending_trade(symbol)
        
        if not pending_trade:
            plog.debug(f"No pending trade found for {symbol} to cancel", agent="execution_agent")
            return
        
        plog.info(
            f"🗑️ Cancelling pending trade for {symbol} | Reason: {reason}",
            agent="execution_agent"
        )
        
        # Cancel the limit order
        if pending_trade.limit_order_id:
            try:
                await self.exchange.cancel_order(symbol, pending_trade.limit_order_id)
                plog.info(
                    f"✅ Cancelled limit order: {pending_trade.limit_order_id}",
                    agent="execution_agent"
                )
            except Exception as e:
                plog.error(
                    f"Failed to cancel order {pending_trade.limit_order_id}: {e}",
                    agent="execution_agent"
                )
        
        # Remove from queue
        self.pending_trades_queue.remove_pending_trade(symbol)
        
        await self.publish_activity(
            action="pending_trade_cancelled",
            message=f"Cancelled pending trade: {reason}",
            phase="execution",
            severity="info",
            metadata={
                "symbol": symbol,
                "reason": reason,
                "entry_price": pending_trade.entry_price,
                "confidence": pending_trade.confidence_score
            }
        )
    
    async def _pending_trades_monitor_loop(self):
        """
        Monitor pending trades for fills and timeouts
        Runs every 5 seconds
        
        Responsibilities:
        1. Check if any pending limit orders have filled
        2. Remove filled trades from queue
        3. Cleanup expired trades (timeout)
        4. Publish activity updates
        """
        logger.info("Pending trades monitor loop started (5s interval)")
        
        last_activity_log = 0
        log_interval = 30  # Log activity every 30 seconds to avoid spam
        
        while self.running:
            try:
                # Cleanup expired trades first
                expired = self.pending_trades_queue.cleanup_expired()
                for trade in expired:
                    await self._cancel_pending_trade(
                        trade.symbol,
                        reason=f"Timeout ({trade.timeout_seconds}s)"
                    )
                
                # Check if any pending trades have filled
                for pending_trade in self.pending_trades_queue.get_all_pending():
                    if pending_trade.limit_order_id:
                        try:
                            # Check order status
                            order = await self.exchange.get_order_status(
                                pending_trade.symbol,
                                pending_trade.limit_order_id
                            )
                            
                            if order and order.status == OrderStatus.FILLED:
                                plog.success(
                                    f"🎉 Pending trade FILLED! {pending_trade.symbol} {pending_trade.direction} "
                                    f"@ ${order.average_price:.2f} (Confidence: {pending_trade.confidence_score:.3f})",
                                    agent="execution_agent"
                                )
                                
                                # Remove from pending queue
                                self.pending_trades_queue.remove_pending_trade(pending_trade.symbol)
                                
                                # Publish activity
                                await self.publish_activity(
                                    action="pending_trade_filled",
                                    message=f"LIMIT order filled at ${order.average_price:.2f}",
                                    phase="execution",
                                    severity="success",
                                    metadata={
                                        "symbol": pending_trade.symbol,
                                        "direction": pending_trade.direction,
                                        "entry_price": order.average_price,
                                        "confidence": pending_trade.confidence_score,
                                        "order_id": pending_trade.limit_order_id
                                    }
                                )
                                
                                # Publish portfolio update
                                if not self.realtime_trading and self.paper_trading_engine:
                                    await self.paper_trading_engine.publish_portfolio_update()
                        
                        except Exception as e:
                            logger.error(
                                f"Error checking pending trade {pending_trade.symbol}: {e}"
                            )
                
                # Periodic activity logging
                current_time = asyncio.get_event_loop().time()
                if current_time - last_activity_log > log_interval:
                    pending_count = self.pending_trades_queue.get_count()
                    
                    if pending_count > 0:
                        # Log pending trades summary
                        pending_list = self.pending_trades_queue.get_all_pending()
                        for pt in pending_list:
                            await self.publish_activity(
                                action="monitoring_pending_trade",
                                message=f"Pending: {pt.symbol} {pt.direction} @ ${pt.entry_price:.2f} (Conf: {pt.confidence_score:.3f}, Remaining: {pt.time_remaining()}s)",
                                phase="execution",
                                severity="info",
                                metadata={
                                    "symbol": pt.symbol,
                                    "entry_price": pt.entry_price,
                                    "confidence": pt.confidence_score,
                                    "time_remaining": pt.time_remaining()
                                }
                            )
                    else:
                        # Log heartbeat if no pending trades
                        await self.publish_activity(
                            action="monitoring_idle",
                            message="No pending trades (Ready for new setups)",
                            phase="execution",
                            severity="info",
                            metadata={"status": "idle"}
                        )
                    
                    last_activity_log = current_time
                
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                logger.info("Pending trades monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in pending trades monitor: {e}")
                # Log error to feed so user knows something is wrong
                try:
                    await self.publish_activity(
                        action="monitoring_error",
                        message=f"Pending trades monitor error: {str(e)}",
                        phase="execution",
                        severity="error",
                        metadata={"error": str(e)}
                    )
                except:
                    pass
                await asyncio.sleep(5)  # Continue even on error

    async def _price_update_loop(self):
        """Mock price update loop for position monitor"""
        # In production, this would consume a websocket stream
        while self.running:
            # For each monitored position, get current price
            for position in self.position_monitor.get_positions():
                try:
                    # Get price from exchange (snapshot)
                    ticker = await self.exchange._request('GET', '/openApi/swap/v2/quote/ticker', {'symbol': position.symbol})
                    current_price = float(ticker.get('lastPrice', 0))
                    
                    if current_price > 0:
                        self.position_monitor.update_price(position.symbol, current_price)
                        
                except Exception as e:
                    logger.debug(f"Price update failed: {e}")
            
            await asyncio.sleep(1)  # 1s update interval
