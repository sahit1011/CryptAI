
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from src.data.binance_client import BinanceWebSocketClient
from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.utils.config import get_config


app = FastAPI(title="Antigravity Trading API")

# --- Auth & CORS configuration (env-driven, fail-closed) -----------------------
# API_AUTH_TOKEN, when set, is required as `Authorization: Bearer <token>` on every
# non-health endpoint and the /ws handshake. When unset, reads stay open for local
# dev but the destructive close-positions endpoint is hard-disabled (see below).
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "").strip()
# Allowed CORS origins — never wildcard-with-credentials (invalid + unsafe). Default
# to the local dashboard origin.
_cors_origins = [o.strip() for o in os.getenv("API_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_bearer = HTTPBearer(auto_error=False)


def require_auth(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
    """Require a valid bearer token IFF API_AUTH_TOKEN is configured.

    No token configured -> open (local-dev posture; server should be bound to
    127.0.0.1). Token configured -> every guarded endpoint must present it.
    """
    if not API_AUTH_TOKEN:
        return
    if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != API_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
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
# Shared, created once at startup. Building a TradeHistoryManager runs create_all DDL
# and opens a sync engine, so constructing it per request (as /api/trades used to)
# blocked the event loop and leaked engines.
trade_history_manager = None


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

    # 1. Start Binance Client. Guarded + bounded: if the exchange is unreachable
    # (region block, outage, restricted network), the API must STILL start so the
    # Redis WS bridge, REST endpoints, and agent feed keep working — the market feed
    # simply stays offline until connectivity returns.
    try:
        await asyncio.wait_for(binance_client.connect(), timeout=10)
        await binance_client.subscribe_ticker("btcusdt", handle_binance_update)
        await binance_client.subscribe_depth("btcusdt", levels=5, update_speed="100ms", callback=handle_binance_update)
        await binance_client.subscribe_kline("btcusdt", ["1m"], handle_binance_update)
    except Exception as e:
        logger.error(f"Binance market feed unavailable at startup (continuing without it): {e}")

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

        # Build the shared trade-history manager once (sync engine + create_all).
        global trade_history_manager
        try:
            from src.memory.trade_history_manager import TradeHistoryManager
            trade_history_manager = await asyncio.to_thread(
                TradeHistoryManager, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize TradeHistoryManager: {e}")

        
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
    # Auth on the WS handshake when a token is configured. Browsers can't set
    # Authorization headers on WebSocket, so accept either the header or a
    # ?token= query param.
    if API_AUTH_TOKEN:
        header = websocket.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else websocket.query_params.get("token", "")
        if token != API_AUTH_TOKEN:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
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
async def get_trades(
    limit: int = Query(50, ge=1, le=500, description="Number of recent trades to return (1-500)"),
    _auth: None = Depends(require_auth),
):
    """Get recent trade history from PostgreSQL.

    `limit` is validated at the request boundary (FastAPI/Pydantic Query bounds
    reject out-of-range values with a 422). The explicit clamp below is kept as
    a defense-in-depth safeguard in case this handler is ever called directly.
    """
    limit = max(1, min(limit, 500))  # clamp to a sane range
    try:
        if trade_history_manager is None:
            logger.error("TradeHistoryManager not initialized")
            return {"error": "trade history unavailable", "trades": []}

        # get_recent_trades is a blocking sync DB call — run it off the event loop
        # on the shared manager (no per-request engine / DDL).
        trades = await asyncio.to_thread(
            trade_history_manager.get_recent_trades, limit
        )

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
async def close_all_positions(_auth: None = Depends(require_auth)):
    """Emergency 'close all positions' control.

    This API process is SEPARATE from the trading process that owns live/paper
    positions, so it cannot close them directly — it dispatches a `panic_close`
    command to the running Execution Agent over the message bus (the same channel
    the orchestrator uses), and the agent performs the authoritative reduce-only
    close. The previous implementation built a throwaway PaperTradingEngine and
    called async methods without await, so it silently no-op'd while reporting
    success — a safety control that lied.

    Fail-closed: if no API_AUTH_TOKEN is configured this destructive endpoint is
    disabled entirely (binding to 127.0.0.1 is not sufficient protection for a
    money-moving control).
    """
    if not API_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="close-positions is disabled until API_AUTH_TOKEN is configured",
        )

    if not message_bus:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Message bus unavailable; cannot reach the execution agent",
        )

    correlation_id = f"api_panic_close_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    try:
        await message_bus.publish(
            "execution_agent_inbox",
            {
                "id": correlation_id,
                "correlation_id": correlation_id,
                "sender": "api",
                "receiver": "execution_agent",
                "type": "panic_close",
                "payload": {"reason": "Manual close via API"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Dispatched panic_close to execution agent (correlation_id={correlation_id})")
        return {
            "success": True,
            "dispatched": True,
            "message": "Close-all-positions command dispatched to the execution agent. "
                       "Watch the live position feed for confirmation.",
            "correlation_id": correlation_id,
        }
    except Exception as e:
        logger.error(f"Error dispatching close-positions command: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "online", 
        "connections": len(manager.active_connections),
        "message_bus": message_bus is not None
    }

if __name__ == "__main__":
    import uvicorn
    # Bind to localhost by default; only expose externally behind an authenticating
    # proxy (and with API_AUTH_TOKEN set). Override via API_HOST.
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("src.api.server:app", host=host, port=port, reload=True)
