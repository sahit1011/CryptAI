
import asyncio
import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from src.data.binance_client import BinanceWebSocketClient
from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.utils.config import get_config


app = FastAPI(title="Antigravity Trading API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.state_manager: Optional[StateManager] = None
        self.initial_state: Dict[str, Any] = {
            "portfolio": None,
            "positions": []
        }

    def set_state_manager(self, state_manager: StateManager):
        self.state_manager = state_manager

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
        
        # CRITICAL FIX: Fetch latest state from StateManager with fallbacks
        if self.state_manager:
            try:
                # Fetch portfolio using get_portfolio_state() which reads from hash
                portfolio = await self.state_manager.get_portfolio_state()
                if portfolio:
                    await websocket.send_text(json.dumps({
                        "type": "execution_status",
                        "data": {
                            "type": "balance_update",
                            "payload": portfolio
                        }
                    }, default=str))
                    logger.info(f"✅ Sent portfolio state to client: ${portfolio.get('total_equity', 0):,.2f}")
                else:
                    # Send default initial state
                    default_portfolio = {
                        "initial_balance": 10000.0,
                        "current_balance": 10000.0,
                        "total_equity": 10000.0,
                        "unrealized_pnl": 0.0,
                        "realized_pnl": 0.0,
                        "win_rate": 0.0,
                        "total_trades": 0,
                        "total_commission": 0.0,
                        "max_drawdown": 0.0,
                        "open_positions": 0
                    }
                    await websocket.send_text(json.dumps({
                        "type": "execution_status",
                        "data": {
                            "type": "balance_update",
                            "payload": default_portfolio
                        }
                    }, default=str))
                    logger.info(f"✅ Sent default portfolio state to client: $10,000.00")
                
                # Fetch positions with fallback to empty array
                positions = await self.state_manager.get_positions()
                if positions is None:
                    positions = []
                    
                await websocket.send_text(json.dumps({
                    "type": "execution_status",
                    "data": {
                        "type": "position_update",
                        "payload": positions
                    }
                }, default=str))
                logger.info(f"✅ Sent {len(positions)} positions to client")
                
            except Exception as e:
                logger.error(f"Error hydrating client state: {e}")
                # Send default state on error
                await websocket.send_text(json.dumps({
                    "type": "execution_status",
                    "data": {
                        "type": "balance_update",
                        "payload": {
                            "initial_balance": 10000.0,
                            "current_balance": 10000.0,
                            "total_equity": 10000.0,
                            "unrealized_pnl": 0.0,
                            "realized_pnl": 0.0
                        }
                    }
                }, default=str))


    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total: {len(self.active_connections)}")
    
    def update_initial_state(self, portfolio: Optional[Dict] = None, positions: Optional[List] = None):
        """Update the initial state cache"""
        if portfolio:
            self.initial_state["portfolio"] = portfolio
        if positions is not None:
            self.initial_state["positions"] = positions

    async def broadcast(self, message: Dict[str, Any]):
        # Broadcast to all connected clients
        # We'll send JSON string
        try:
            json_msg = json.dumps(message, default=str)
            
            # Update initial state cache for new clients
            msg_type = message.get("type")
            data = message.get("data", {})
            
            if msg_type == "execution_status":
                if data.get("type") == "balance_update":
                    self.update_initial_state(portfolio=data.get("payload"))
                elif data.get("type") == "position_update":
                    self.update_initial_state(positions=data.get("payload"))
            elif msg_type == "agent_update":
                if data.get("type") == "balance_update":
                    self.update_initial_state(portfolio=data.get("payload"))
                elif data.get("type") == "position_update":
                    self.update_initial_state(positions=data.get("payload"))
            
            # CRITICAL FIX: Track dead connections for removal
            dead_connections = []
            
            for connection in self.active_connections:
                try:
                    # CRITICAL FIX: Check if connection is still open before sending
                    # WebSocketState: CONNECTING=0, CONNECTED=1, DISCONNECTED=2
                    if connection.client_state.value == 1:  # CONNECTED state
                        await connection.send_text(json_msg)
                    else:
                        # Connection is not in CONNECTED state, mark for removal
                        dead_connections.append(connection)
                        logger.debug(f"Skipping broadcast to connection in state: {connection.client_state.name}")
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    # Mark connection as dead if send fails
                    dead_connections.append(connection)
            
            # CRITICAL FIX: Remove dead connections from active list
            if dead_connections:
                for conn in dead_connections:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)
                logger.info(f"Removed {len(dead_connections)} dead connection(s). Active connections: {len(self.active_connections)}")
                    
        except Exception as e:
            logger.error(f"Error serializing message: {e}")

manager = ConnectionManager()
binance_client = BinanceWebSocketClient()
message_bus: Optional[MessageBus] = None
state_manager: Optional[StateManager] = None


async def handle_binance_update(data: Dict[str, Any]):
    """Callback for Binance updates"""
    # Forward directly to frontend
    # Map Binance event types to frontend-friendly types
    msg_type = data.get('e')
    
    # Map Binance event types to our frontend types
    type_mapping = {
        '24hrTicker': '24hrTicker',
        'depthUpdate': 'depthUpdate',
        'kline': 'kline'
    }
    
    frontend_type = type_mapping.get(msg_type, msg_type)
    
    # CRITICAL FIX: Persist live price to Redis for Execution Agent
    if msg_type == '24hrTicker' and state_manager:
        try:
            symbol = data.get('s')
            price = float(data.get('c', 0))
            if symbol and price > 0:
                # Store as both raw symbol (BTCUSDT) and formatted (BTC/USDT)
                # The StateManager.update_price handles the formatting logic usually, 
                # but we'll be explicit here to be safe
                await state_manager.update_price(symbol, price)
                # logger.debug(f"Persisted live price for {symbol}: ${price}")
        except Exception as e:
            logger.error(f"Failed to persist price update: {e}")
    
    payload = {
        "type": frontend_type,
        "data": data
    }
    
    await manager.broadcast(payload)

async def handle_agent_message(data: Dict[str, Any]):
    """Callback for agent messages from MessageBus"""
    # Determine message type for frontend
    msg_type = "agent_update"
    
    # Check if this is an execution update (balance or positions)
    if data.get("type") in ["balance_update", "position_update"]:
        msg_type = "execution_status"
    
    # Check if this is an activity log
    elif "action" in data and "sender" in data:
        msg_type = "agent_activity"
        
    payload = {
        "type": msg_type,
        "data": data
    }
    await manager.broadcast(payload)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Antigravity API...")
    
    # 1. Start Binance Client
    await binance_client.connect()
    
    # Subscribe to BTCUSDT ticker and depth
    # Ticker for live price
    await binance_client.subscribe_ticker("btcusdt", handle_binance_update)
    
    # Depth for order book (level 5 for speed)
    await binance_client.subscribe_depth("btcusdt", levels=5, update_speed="100ms", callback=handle_binance_update)
    
    # Kline for chart (1m for now)
    await binance_client.subscribe_kline("btcusdt", ["1m"], handle_binance_update)

    # 2. Start MessageBus and StateManager
    global message_bus, state_manager
    try:
        config = get_config()
        message_bus = MessageBus(redis_url=config.database.redis_url)
        await message_bus.connect()
        
        state_manager = StateManager()
        await state_manager.connect()
        
        # Pass state_manager to connection manager
        manager.set_state_manager(state_manager)

        
        # Subscribe to all relevant agent channels
        channels = [
            'market_data',       # From Data Agent
            'analysis_results',  # From Analysis Agent
            'trade_signals',     # From Strategy Agent
            'risk_decisions',    # From Risk Agent
            'approved_trades',   # From Risk Agent
            'execution_status',  # From Execution Agent
            'agent_activity',    # Agent neural feed activity
            'alerts'             # System alerts
        ]
        
        for channel in channels:
            await message_bus.subscribe(channel, handle_agent_message)
            logger.info(f"Subscribed to agent channel: {channel}")
            
    except Exception as e:
        logger.error(f"Failed to initialize MessageBus: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down...")
    await binance_client.disconnect()
    
    if message_bus:
        await message_bus.disconnect()
        
    if state_manager:
        await state_manager.disconnect()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, maybe listen for client commands later
            data = await websocket.receive_text()
            # Echo or process (optional)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """Get recent trade history from PostgreSQL"""
    try:
        from src.memory.trade_history_manager import TradeHistoryManager
        from src.utils.config import get_config
        
        config = get_config()
        trade_manager = TradeHistoryManager(config.database.postgres_url)
        trades = trade_manager.get_recent_trades(limit=limit)
        
        # Format trades for frontend
        formatted_trades = []
        for trade in trades:
            formatted_trades.append({
                "id": trade.trade_id,
                "symbol": trade.symbol,
                "side": trade.direction.upper(),
                "entry": float(trade.entry_price),
                "current": float(trade.exit_price) if trade.exit_price else float(trade.entry_price),
                "pnl": float(trade.pnl) if trade.pnl else 0.0,
                "pnlPercent": float(trade.pnl_percentage) if trade.pnl_percentage else 0.0,
                "status": "CLOSED" if trade.exit_price else "OPEN",
                "entryTime": trade.entry_time.isoformat() if trade.entry_time else None,
                "exitTime": trade.exit_time.isoformat() if trade.exit_time else None,
                "exitReason": trade.exit_reason,
                "strategy": trade.strategy_type,
                "leverage": trade.leverage if hasattr(trade, 'leverage') else 10,
                "confidence": float(trade.confidence_score) if trade.confidence_score else 0.0,
                "isWinner": trade.is_winner
            })
        
        logger.info(f"📊 Fetched {len(formatted_trades)} trades from database")
        return {"trades": formatted_trades}
        
    except Exception as e:
        logger.error(f"Error fetching trades from database: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "trades": []}

@app.post("/api/close-positions")
async def close_all_positions():
    """Close all active positions immediately"""
    try:
        from src.execution.paper_trading_engine import PaperTradingEngine
        from src.memory.trade_history_manager import TradeHistoryManager
        from datetime import datetime
        
        config = get_config()
        
        # Initialize paper trading engine
        engine = PaperTradingEngine(initial_balance=10000.0)
        
        # Restore state from database
        try:
            engine.restore_from_historical_trades(config.database.postgres_url)
        except Exception as e:
            logger.warning(f"Could not restore from historical trades: {e}")
        
        # Get current positions
        positions = engine.get_positions()
        
        if not positions:
            return {"success": True, "message": "No active positions to close", "closed_count": 0}
        
        # Close all positions
        result = engine.close_all_positions(reason="Manual close via API")
        
        if result.get('success'):
            closed_positions = result.get('closed_positions', [])
            total_pnl = result.get('total_realized_pnl', 0)
            
            # Update database
            trade_manager = TradeHistoryManager(config.database.postgres_url)
            
            for pos in closed_positions:
                symbol = pos.get('symbol')
                exit_price = pos.get('exit_price')
                
                # Find active trade in database
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from src.memory.trade_history_manager import TradeRecord
                
                engine_db = create_engine(config.database.postgres_url)
                SessionLocal = sessionmaker(bind=engine_db)
                session = SessionLocal()
                
                try:
                    active_trade = session.query(TradeRecord).filter(
                        TradeRecord.symbol == symbol,
                        TradeRecord.exit_time.is_(None)
                    ).first()
                    
                    if active_trade:
                        trade_manager.update_trade_exit(
                            trade_id=active_trade.trade_id,
                            exit_price=exit_price,
                            exit_time=datetime.now(),
                            exit_reason="manual_close_api",
                            notes="Closed via API endpoint"
                        )
                        logger.info(f"Updated trade {active_trade.trade_id} in database")
                except Exception as e:
                    logger.error(f"Error updating database: {e}")
                finally:
                    session.close()
            
            # Broadcast update to frontend
            if message_bus:
                await message_bus.publish('execution_status', {
                    'type': 'position_update',
                    'payload': []
                })
                
                # Update portfolio
                portfolio = {
                    "current_balance": engine.get_balance(),
                    "total_equity": engine.get_total_equity(),
                    "unrealized_pnl": 0.0,
                    "open_positions": 0
                }
                await message_bus.publish('execution_status', {
                    'type': 'balance_update',
                    'payload': portfolio
                })
            
            logger.info(f"✅ Closed {len(closed_positions)} positions via API, Total P&L: ${total_pnl:.2f}")
            
            return {
                "success": True,
                "message": f"Successfully closed {len(closed_positions)} position(s)",
                "closed_count": len(closed_positions),
                "total_pnl": total_pnl,
                "positions": closed_positions
            }
        else:
            error = result.get('error', 'Unknown error')
            return {"success": False, "error": error}
            
    except Exception as e:
        logger.error(f"Error closing positions via API: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/health")
async def health_check():
    return {
        "status": "online", 
        "connections": len(manager.active_connections),
        "message_bus": message_bus is not None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)
