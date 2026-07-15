
import asyncio
import json
import os
import jwt
from collections import deque
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


# --- Multi-tenancy: Supabase JWT identity at the API edge ----------------------
# Requests from a logged-in user carry their Supabase access token (a signed JWT).
# We verify it against the project's JWKS (asymmetric ES256/RS256 — no shared secret)
# and resolve the tenant's user_id (the `sub` claim). This is what lets reads be
# scoped per user instead of exposing one global account.
SUPABASE_URL = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
_jwks_client: Optional["jwt.PyJWKClient"] = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        # PyJWKClient fetches + caches the project's public keys.
        _jwks_client = jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")
    return _jwks_client


def verify_supabase_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Return {user_id, email} for a valid Supabase user token, else None."""
    client = _get_jwks_client()
    if not client or not token:
        return None
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{SUPABASE_URL}/auth/v1",
            # Tolerate small client/server clock skew — otherwise a just-issued token
            # is briefly rejected as "not yet valid (iat)".
            leeway=60,
        )
        return {"user_id": claims.get("sub"), "email": claims.get("email"), "kind": "user"}
    except Exception as e:
        logger.debug(f"Supabase JWT verify failed: {e}")
        return None


def current_principal(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    """Resolve the caller: a per-user tenant, an internal service, or (dev) anonymous.

    - Valid Supabase user JWT -> {'kind':'user','user_id': <uuid>} (scope to this tenant)
    - Static API_AUTH_TOKEN    -> {'kind':'service','user_id': None} (internal/admin, unscoped)
    - Nothing configured       -> {'kind':'anonymous','user_id': None} (local dev, open)
    - Otherwise                -> 401
    """
    token = creds.credentials if (creds and creds.scheme.lower() == "bearer") else ""
    if token:
        user = verify_supabase_jwt(token)
        if user and user.get("user_id"):
            return user
        if API_AUTH_TOKEN and token == API_AUTH_TOKEN:
            return {"kind": "service", "user_id": None}
    if not API_AUTH_TOKEN and not SUPABASE_URL:
        return {"kind": "anonymous", "user_id": None}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

class ConnectionManager:
    """Per-tenant WebSocket fan-out.

    Each connection is tagged with the tenant's user_id (from the verified Supabase
    JWT on the handshake) or None for a service/anonymous connection. Broadcasts that
    carry a target user_id are delivered ONLY to that tenant's sockets; untenanted
    messages (no user_id — e.g. dev/global) go to everyone. Cached hydration state and
    the recent-activity replay buffer are kept per tenant so a new client only ever
    sees its own data. The empty-string key is the untenanted/global bucket.
    """

    GLOBAL = ""  # cache key for untenanted messages

    def __init__(self):
        self.connections: Dict[WebSocket, Optional[str]] = {}
        self.state_manager: Optional[StateManager] = None
        # Per-tenant latest {portfolio, positions} for connect-time hydration.
        self.initial_state: Dict[str, Dict[str, Any]] = {}
        # Per-tenant ring buffers of recent activity, replayed on connect.
        self.recent_activity: Dict[str, deque] = {}

    @property
    def active_connections(self) -> List[WebSocket]:
        return list(self.connections.keys())

    def set_state_manager(self, state_manager: StateManager):
        self.state_manager = state_manager

    @staticmethod
    def _message_user(message: Dict[str, Any]) -> Optional[str]:
        """Extract the target tenant from a broadcast message, if any."""
        uid = message.get("user_id")
        if not uid and isinstance(message.get("data"), dict):
            uid = message["data"].get("user_id")
        return uid or None

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        self.connections[websocket] = user_id
        logger.info(f"Client connected (user={user_id or 'anon'}). Total: {len(self.connections)}")

        key = user_id or self.GLOBAL
        cached = self.initial_state.get(key, {})
        try:
            # Portfolio: cached tenant state -> (global bot only) persisted state -> for
            # the global/dev bucket, a $10k default; a fresh tenant with no data gets
            # nothing (the UI shows an honest "waiting" state rather than a fake $10k).
            portfolio = cached.get("portfolio")
            if not portfolio and key == self.GLOBAL and self.state_manager:
                portfolio = await self.state_manager.get_portfolio_state()
            if not portfolio and key == self.GLOBAL:
                portfolio = {
                    "initial_balance": 10000.0, "current_balance": 10000.0,
                    "total_equity": 10000.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0,
                    "win_rate": 0.0, "total_trades": 0, "open_positions": 0,
                }
            if portfolio:
                await websocket.send_text(json.dumps({
                    "type": "execution_status",
                    "data": {"type": "balance_update", "payload": portfolio},
                }, default=str))

            positions = cached.get("positions")
            if positions is None and key == self.GLOBAL and self.state_manager:
                positions = await self.state_manager.get_positions()
            positions = positions or []
            await websocket.send_text(json.dumps({
                "type": "execution_status",
                "data": {"type": "position_update", "payload": positions},
            }, default=str))

            # Replay this tenant's recent activity so the feed isn't empty on open.
            for msg in list(self.recent_activity.get(key, ())):
                try:
                    await websocket.send_text(json.dumps(msg, default=str))
                except Exception:
                    break
        except Exception as e:
            logger.error(f"Error hydrating client state: {e}")

    def disconnect(self, websocket: WebSocket):
        if self.connections.pop(websocket, "missing") != "missing":
            logger.info(f"Client disconnected. Total: {len(self.connections)}")

    def _cache_state(self, key: str, portfolio: Optional[Dict] = None, positions: Optional[List] = None):
        bucket = self.initial_state.setdefault(key, {})
        if portfolio:
            bucket["portfolio"] = portfolio
        if positions is not None:
            bucket["positions"] = positions

    async def broadcast(self, message: Dict[str, Any]):
        try:
            json_msg = json.dumps(message, default=str)
            target = self._message_user(message)     # None => untenanted/global
            key = target or self.GLOBAL
            msg_type = message.get("type")
            data = message.get("data", {}) if isinstance(message.get("data"), dict) else {}

            # Cache latest portfolio/positions per tenant for connect-time hydration.
            if msg_type in ("execution_status", "agent_update"):
                if data.get("type") == "balance_update":
                    self._cache_state(key, portfolio=data.get("payload"))
                elif data.get("type") == "position_update":
                    self._cache_state(key, positions=data.get("payload"))

            # Buffer activity per tenant for replay to new clients.
            if msg_type in ("agent_activity", "agent_update"):
                self.recent_activity.setdefault(key, deque(maxlen=50)).append(message)

            dead: List[WebSocket] = []
            for connection, uid in list(self.connections.items()):
                # Tenanted message -> only its owner's sockets. Untenanted -> everyone.
                if target is not None and uid != target:
                    continue
                try:
                    if connection.client_state.value == 1:  # CONNECTED
                        await connection.send_text(json_msg)
                    else:
                        dead.append(connection)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    dead.append(connection)

            for conn in dead:
                self.connections.pop(conn, None)
            if dead:
                logger.info(f"Removed {len(dead)} dead connection(s). Active: {len(self.connections)}")
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
    # Handshake auth + tenant resolution. Browsers can't set an Authorization header on
    # a WS upgrade, so the token comes via ?token= (or the header for non-browser
    # clients). A valid Supabase JWT scopes the socket to that user; the static service
    # token connects unscoped; when neither SUPABASE_URL nor API_AUTH_TOKEN is set the
    # socket is open (local dev). An invalid/absent token when auth IS configured is
    # rejected before accept.
    header = websocket.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else websocket.query_params.get("token", "")

    user_id: Optional[str] = None
    if token:
        user = verify_supabase_jwt(token)
        if user and user.get("user_id"):
            user_id = user["user_id"]
        elif API_AUTH_TOKEN and token == API_AUTH_TOKEN:
            user_id = None  # service/admin — unscoped
        elif SUPABASE_URL or API_AUTH_TOKEN:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    elif SUPABASE_URL or API_AUTH_TOKEN:
        # Auth is configured but no token presented — reject.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)
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
    principal: Dict[str, Any] = Depends(current_principal),
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

        # Scope to the authenticated tenant. A user principal only ever sees their own
        # trades; a service/anonymous principal (user_id=None) sees all (unscoped).
        user_id = principal.get("user_id")
        trades = await asyncio.to_thread(
            trade_history_manager.get_recent_trades, limit, None, user_id
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
