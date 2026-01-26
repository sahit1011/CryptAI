"""
Memory Agent
Manages trade history, performance analytics, and learning from past trades
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import os

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.memory.trade_history_manager import TradeHistoryManager
from src.memory.vector_memory import VectorMemoryStore
from src.memory.performance_analytics import PerformanceAnalyticsEngine
from src.memory.market_regime_detector import MarketRegimeDetector
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class MemoryAgent(BaseAgent):
    """
    Memory Agent - System Memory and Learning
    
    Responsibilities:
    - Store and retrieve trade history
    - Track performance metrics
    - Detect market regimes
    - Find similar historical trades
    - Generate performance reports
    - Provide context for decision-making
    - Enable continuous learning
    
    Message Handlers:
    - log_trade: Store new trade entry
    - update_trade: Update trade with exit details
    - get_trade: Retrieve specific trade
    - get_similar_trades: Find similar historical setups
    - get_performance_metrics: Calculate performance statistics
    - get_regime_analysis: Detect current market regime
    - get_performance_report: Generate comprehensive report
    - get_strategy_performance: Performance by strategy type
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        database_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        chroma_persist_dir: str = "./chroma_db",
        initial_capital: float = 10000.0
    ):
        super().__init__(
            name="memory_agent",
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        # Initialize database URL (use PostgreSQL from Docker)
        db_url = database_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://trader:secure_password_here@localhost:5432/trading_agent"
        )
        
        # Initialize Trade History Manager
        self.trade_history = TradeHistoryManager(database_url=db_url)
        
        # Initialize Vector Memory Store
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.vector_memory = VectorMemoryStore(
            openai_api_key=api_key,
            persist_directory=chroma_persist_dir
        )
        
        # Initialize Performance Analytics Engine
        self.performance_analytics = PerformanceAnalyticsEngine(
            initial_capital=initial_capital
        )
        
        # Initialize Market Regime Detector
        self.regime_detector = MarketRegimeDetector()
        
        # Statistics
        self.trades_logged = 0
        self.trades_updated = 0
        self.performance_reports_generated = 0
        self.similar_trade_queries = 0
        
        plog.info(
            f"Memory Agent initialized | db={db_url} | chroma={chroma_persist_dir}",
            agent="memory_agent",
            phase="initialization"
        )
    
    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("log_trade", self._handle_log_trade)
        self.register_handler("update_trade", self._handle_update_trade)
        self.register_handler("update_entry", self._handle_update_entry)
        self.register_handler("get_trade", self._handle_get_trade)
        self.register_handler("get_similar_trades", self._handle_get_similar_trades)
        self.register_handler("get_performance_metrics", self._handle_get_performance_metrics)
        self.register_handler("get_regime_analysis", self._handle_get_regime_analysis)
        self.register_handler("get_performance_report", self._handle_get_performance_report)
        self.register_handler("get_strategy_performance", self._handle_get_strategy_performance)
        self.register_handler("get_recent_trades", self._handle_get_recent_trades)
    
    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """
        Process incoming message
        
        PHASE 2 FIX: Now sends responses back to orchestrator for sequential execution
        """
        handler = self.handlers.get(message.type)
        
        if handler:
            result = await handler(message.payload)
            
            # PHASE 2 FIX: Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                # Ensure result has success flag
                if isinstance(result, dict) and 'success' not in result:
                    result['success'] = True
                
                # CRITICAL FIX: Pass correlation_id so orchestrator can match response to request
                await self.send_response(result, correlation_id=message.correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={message.correlation_id})",
                    agent="memory_agent"
                )
            
            # CRITICAL FIX: Support response_channel for inter-agent communication (e.g. Analysis Agent)
            elif isinstance(message.payload, dict) and message.payload.get('response_channel'):
                response_channel = message.payload['response_channel']
                await self.message_bus.publish(response_channel, result)
                plog.debug(
                    f"Sent response to {response_channel} for {message.type}",
                    agent="memory_agent"
                )
            
            return result
        else:
            plog.warning(
                f"No handler for message type: {message.type}",
                agent="memory_agent",
                phase="message_processing"
            )
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                # CRITICAL FIX: Pass correlation_id for error responses too
                await self.send_response(error_response, correlation_id=message.correlation_id)
                
            return None
    
    async def _handle_log_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log new trade entry
        
        Payload:
            trade_id, symbol, direction, entry_price, entry_time,
            position_size, stop_loss, take_profit_levels, risk_amount,
            strategy_type, confidence_score, confluence_count,
            market_regime, atr_at_entry, smc_patterns, ict_setups
        """
        self.trades_logged += 1
        
        plog.info(
            f"📝 Logging trade: {payload.get('trade_id')} - {payload.get('symbol')} {payload.get('direction')}",
            agent="memory_agent",
            phase="trade_logging"
        )
        
        try:
            # Store in trade history
            # Handle potential key mismatches and None values
            entry_price = payload.get('entry_price') or payload.get('price') or 0.0
            position_size = payload.get('position_size') or payload.get('recommended_position_size') or 0.0
            stop_loss = payload.get('stop_loss') or 0.0
            risk_amount = payload.get('risk_amount') or 0.0
            atr_at_entry = payload.get('atr_at_entry') or 0.0
            confidence_score = payload.get('confidence_score') or 0.0
            confluence_count = payload.get('confluence_count') or 0
            
            trade_record = await asyncio.to_thread(
                self.trade_history.store_trade,
                trade_id=payload.get('trade_id'),
                symbol=payload.get('symbol'),
                direction=payload.get('direction'),
                entry_price=float(entry_price),
                entry_time=payload.get('entry_time') if isinstance(payload.get('entry_time'), datetime) 
                           else datetime.fromisoformat(payload.get('entry_time')),
                position_size=float(position_size),
                stop_loss=float(stop_loss),
                take_profit_levels=payload.get('take_profit_levels', []),
                risk_amount=float(risk_amount),
                strategy_type=payload.get('strategy_type', ''),
                confidence_score=float(confidence_score),
                confluence_count=int(confluence_count),
                market_regime=payload.get('market_regime', ''),
                atr_at_entry=float(atr_at_entry),
                smc_patterns=payload.get('smc_patterns'),
                ict_setups=payload.get('ict_setups')
            )
            
            # Store in vector memory for similarity search
            trade_data = {
                'symbol': payload.get('symbol'),
                'direction': payload.get('direction'),
                'strategy_type': payload.get('strategy_type'),
                'market_regime': payload.get('market_regime'),
                'confidence_score': payload.get('confidence_score'),
                'confluence_count': payload.get('confluence_count'),
                'smc_patterns': payload.get('smc_patterns', []),
                'ict_setups': payload.get('ict_setups', []),
                'volatility_percentile': payload.get('volatility_percentile', 0.5)
            }
            
            await asyncio.to_thread(
                self.vector_memory.store_trade,
                trade_id=payload.get('trade_id'),
                trade_data=trade_data
            )
            
            plog.info(
                f"✅ Trade logged successfully: {payload.get('trade_id')}",
                agent="memory_agent",
                phase="trade_logging"
            )
            
            # Publish activity
            await self.publish_activity(
                action="trade_logged",
                message=f"Logged new trade for {payload.get('symbol')} ({payload.get('direction')})",
                phase="memory",
                severity="success",
                metadata={
                    "trade_id": payload.get('trade_id'),
                    "symbol": payload.get('symbol'),
                    "direction": payload.get('direction'),
                    "strategy": payload.get('strategy_type')
                }
            )

            
            return {
                'success': True,
                'trade_id': payload.get('trade_id'),
                'logged_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to log trade: {e}",
                agent="memory_agent",
                phase="trade_logging"
            )
            return {
                'success': False,
                'error': str(e)
            }
            
    async def _handle_update_entry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update trade with actual entry details
        
        Payload:
            trade_id, entry_price, entry_time
        """
        plog.info(
            f"📝 Updating trade entry: {payload.get('trade_id')}",
            agent="memory_agent",
            phase="trade_update"
        )
        
        try:
            # Update in trade history
            trade_record = await asyncio.to_thread(
                self.trade_history.update_trade_entry,
                trade_id=payload.get('trade_id'),
                entry_price=float(payload.get('entry_price')),
                entry_time=payload.get('entry_time') if isinstance(payload.get('entry_time'), datetime)
                          else datetime.fromisoformat(payload.get('entry_time'))
            )
            
            plog.info(
                f"✅ Trade entry updated: {payload.get('trade_id')} @ ${trade_record.entry_price:.2f}",
                agent="memory_agent",
                phase="trade_update"
            )
            
            return {
                'success': True,
                'trade_id': payload.get('trade_id'),
                'entry_price': trade_record.entry_price,
                'updated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to update trade entry: {e}",
                agent="memory_agent",
                phase="trade_update"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_update_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update trade with exit details
        
        Payload:
            trade_id, exit_price, exit_time, exit_reason, notes
        """
        self.trades_updated += 1
        
        plog.info(
            f"📝 Updating trade: {payload.get('trade_id')}",
            agent="memory_agent",
            phase="trade_update"
        )
        
        try:
            # Update in trade history
            trade_record = await asyncio.to_thread(
                self.trade_history.update_trade_exit,
                trade_id=payload.get('trade_id'),
                exit_price=float(payload.get('exit_price')),
                exit_time=payload.get('exit_time') if isinstance(payload.get('exit_time'), datetime)
                          else datetime.fromisoformat(payload.get('exit_time')),
                exit_reason=payload.get('exit_reason', 'manual'),
                notes=payload.get('notes')
            )
            
            # Update vector memory with outcome
            trade_data = {
                'is_winner': trade_record.is_winner,
                'pnl': trade_record.pnl,
                'risk_reward_ratio': trade_record.risk_reward_ratio
            }
            
            plog.info(
                f"✅ Trade updated: {payload.get('trade_id')} - P&L: ${trade_record.pnl:.2f}",
                agent="memory_agent",
                phase="trade_update"
            )
            
            # Publish activity
            await self.publish_activity(
                action="trade_updated",
                message=f"Updated trade {payload.get('trade_id')} (P&L: ${trade_record.pnl:.2f})",
                phase="memory",
                severity="success" if trade_record.is_winner else "warning",
                metadata={
                    "trade_id": payload.get('trade_id'),
                    "pnl": trade_record.pnl,
                    "is_winner": trade_record.is_winner,
                    "exit_reason": payload.get('exit_reason')
                }
            )

            
            return {
                'success': True,
                'trade_id': payload.get('trade_id'),
                'pnl': trade_record.pnl,
                'pnl_percentage': trade_record.pnl_percentage,
                'is_winner': trade_record.is_winner,
                'updated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to update trade: {e}",
                agent="memory_agent",
                phase="trade_update"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get specific trade by ID"""
        trade_id = payload.get('trade_id')
        
        try:
            trade = await asyncio.to_thread(self.trade_history.get_trade, trade_id)
            
            if trade:
                return {
                    'success': True,
                    'trade': {
                        'trade_id': trade.trade_id,
                        'symbol': trade.symbol,
                        'direction': trade.direction,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'pnl': trade.pnl,
                        'is_winner': trade.is_winner,
                        'strategy_type': trade.strategy_type,
                        'market_regime': trade.market_regime
                    }
                }
            else:
                return {
                    'success': False,
                    'error': 'Trade not found'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_similar_trades(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find similar historical trades
        
        Payload:
            current_setup (dict with symbol, direction, strategy_type, etc.)
            n_results (int, default 5)
            min_similarity (float, default 0.7)
        """
        self.similar_trade_queries += 1
        
        plog.info(
            f"🔍 Finding similar trades for {payload.get('current_setup', {}).get('symbol')}",
            agent="memory_agent",
            phase="similarity_search"
        )
        
        try:
            current_setup = payload.get('current_setup', {})
            n_results = payload.get('n_results', 5)
            min_similarity = payload.get('min_similarity', 0.7)
            
            similar_trades = await asyncio.to_thread(
                self.vector_memory.find_similar_trades,
                current_setup=current_setup,
                n_results=n_results,
                min_similarity=min_similarity
            )
            
            plog.info(
                f"✅ Found {len(similar_trades)} similar trades",
                agent="memory_agent",
                phase="similarity_search"
            )
            
            return {
                'success': True,
                'similar_trades': [trade.to_dict() for trade in similar_trades],
                'count': len(similar_trades)
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to find similar trades: {e}",
                agent="memory_agent",
                phase="similarity_search"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_performance_metrics(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate performance metrics
        
        Payload:
            start_date (optional)
            end_date (optional)
            symbol (optional)
            strategy_type (optional)
        """
        plog.info(
            "📊 Calculating performance metrics",
            agent="memory_agent",
            phase="performance_analysis"
        )
        
        try:
            start_date = payload.get('start_date')
            end_date = payload.get('end_date')
            symbol = payload.get('symbol')
            strategy_type = payload.get('strategy_type')
            
            # Convert string dates to datetime if needed
            if start_date and isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            if end_date and isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            
            metrics = await self.performance_analytics.calculate_metrics(
                start_date=start_date,
                end_date=end_date,
                symbol=symbol,
                strategy_type=strategy_type
            )
            
            plog.info(
                f"✅ Performance metrics calculated: Win Rate {metrics.win_rate*100:.1f}%",
                agent="memory_agent",
                phase="performance_analysis"
            )
            
            return {
                'success': True,
                'metrics': metrics.to_dict()
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to calculate metrics: {e}",
                agent="memory_agent",
                phase="performance_analysis"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_regime_analysis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get market regime analysis
        
        Note: The actual regime detection is done by the Analysis Agent's RegimeDetector.
        This is a fallback for compatibility.
        
        Payload:
            candles (list of OHLCV data)
            symbol (optional)
        """
        plog.info(
            f"🔍 Analyzing market regime for {payload.get('symbol', 'unknown')}",
            agent="memory_agent",
            phase="regime_detection"
        )
        
        try:
            candles = payload.get('candles', [])
            
            if not candles:
                return {
                    'success': False,
                    'error': 'No candle data provided'
                }
            
            # Simple fallback regime detection
            # The real regime detection is done by Analysis Agent's RegimeDetector
            # This is just for compatibility with older code
            regime_result = {
                'regime': 'UNKNOWN',
                'confidence': 0.5,
                'indicators': {},
                'detected_at': datetime.now().isoformat()
            }
            
            plog.info(
                f"✅ Regime: {regime_result['regime']} (using fallback - Analysis Agent provides actual regime)",
                agent="memory_agent",
                phase="regime_detection"
            )
            
            return {
                'success': True,
                'regime': regime_result,
                'recommendations': {}
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to detect regime: {e}",
                agent="memory_agent",
                phase="regime_detection"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_performance_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        self.performance_reports_generated += 1
        
        plog.info(
            "📊 Generating performance report",
            agent="memory_agent",
            phase="report_generation"
        )
        
        try:
            # Get overall metrics
            overall_metrics = await self.performance_analytics.calculate_metrics()
            
            # Get strategy breakdown
            strategy_performance = await asyncio.to_thread(self.trade_history.get_strategy_performance)
            
            # Get recent trades
            recent_trades = await asyncio.to_thread(self.trade_history.get_recent_trades, limit=10)
            
            report = {
                'generated_at': datetime.now().isoformat(),
                'overall_metrics': overall_metrics.to_dict(),
                'strategy_breakdown': {
                    strategy: stats.to_dict() 
                    for strategy, stats in strategy_performance.items()
                },
                'recent_trades': [
                    {
                        'trade_id': trade.trade_id,
                        'symbol': trade.symbol,
                        'direction': trade.direction,
                        'pnl': trade.pnl,
                        'is_winner': trade.is_winner,
                        'entry_time': trade.entry_time.isoformat() if trade.entry_time else None
                    }
                    for trade in recent_trades
                ],
                'statistics': {
                    'trades_logged': self.trades_logged,
                    'trades_updated': self.trades_updated,
                    'reports_generated': self.performance_reports_generated,
                    'similarity_queries': self.similar_trade_queries
                }
            }
            
            plog.info(
                "✅ Performance report generated",
                agent="memory_agent",
                phase="report_generation"
            )
            
            return {
                'success': True,
                'report': report
            }
            
        except Exception as e:
            plog.error(
                f"❌ Failed to generate report: {e}",
                agent="memory_agent",
                phase="report_generation"
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_strategy_performance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get performance breakdown by strategy type"""
        try:
            strategy_performance = await asyncio.to_thread(self.trade_history.get_strategy_performance)
            
            return {
                'success': True,
                'strategies': {
                    strategy: stats.to_dict()
                    for strategy, stats in strategy_performance.items()
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_recent_trades(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get recent trades"""
        try:
            limit = payload.get('limit', 50)
            symbol = payload.get('symbol')
            
            trades = await asyncio.to_thread(
                self.trade_history.get_recent_trades,
                limit=limit,
                symbol=symbol
            )
            
            return {
                'success': True,
                'trades': [
                    {
                        'trade_id': trade.trade_id,
                        'symbol': trade.symbol,
                        'direction': trade.direction,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'pnl': trade.pnl,
                        'is_winner': trade.is_winner,
                        'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                        'exit_time': trade.exit_time.isoformat() if trade.exit_time else None
                    }
                    for trade in trades
                ],
                'count': len(trades)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
