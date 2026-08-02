
import asyncio
import json
import os
import jwt
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def _metrics_mw(request, call_next):
    """Prometheus instrumentation: count + time every request (normalized path)."""
    import time as _time
    from src.utils.metrics import HTTP_LATENCY, HTTP_REQUESTS, normalize_path
    path = normalize_path(request.url.path)
    start = _time.perf_counter()
    response = await call_next(request)
    HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    HTTP_LATENCY.labels(request.method, path).observe(_time.perf_counter() - start)
    return response


@app.middleware("http")
async def _request_id(request, call_next):
    """Correlate every request with an ID: honor the client/proxy's X-Request-ID or mint
    one; expose it on the response and on every log line emitted while handling it."""
    import uuid
    from src.utils.logging_setup import request_id_var
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


@app.middleware("http")
async def _rate_limit(request, call_next):
    """Per-caller rate limiting (sliding 60s window; user token if present, else IP).

    Writes (POST/DELETE) have a tighter budget than reads. /health is exempt so
    orchestrator probes never get throttled.
    """
    if request.url.path != "/health":
        from fastapi.responses import JSONResponse
        from src.utils.api_rate_limit import client_key, read_limiter, write_limiter
        key = client_key(request.headers, request.client.host if request.client else "")
        limiter = write_limiter if request.method in ("POST", "DELETE") else read_limiter
        allowed, retry_after = limiter.allow(key)
        if not allowed:
            from src.utils.metrics import RATE_LIMITED
            RATE_LIMITED.labels(request.method).inc()
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded — slow down."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


@app.middleware("http")
async def _security_headers(request, call_next):
    """Baseline security headers on every response (clickjacking, MIME-sniffing, etc.)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # HSTS is honored only over HTTPS (ignored on plain HTTP), safe to always send.
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


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
        # Recent trade-setup suggestions (shared across users), replayed on connect
        # and served by GET /api/setups for load-time hydration.
        self.recent_signals: deque = deque(maxlen=30)
        # Per-connection market-channel subscriptions ("ticker.ETHUSDT",
        # "kline.1m.XAUTUSDT", "depth.ETHUSDT"). The base BTCUSDT streams stay an
        # untargeted broadcast (the dashboard predates the protocol); everything
        # else is delivered only to sockets that asked for it.
        self.channel_subs: Dict[WebSocket, set] = {}

    # Cap per connection — enough for every symbol×stream we serve, hostile-proof.
    MAX_CHANNELS_PER_CONNECTION = 24

    def add_channels(self, websocket: WebSocket, channels: set) -> set:
        subs = self.channel_subs.setdefault(websocket, set())
        room = self.MAX_CHANNELS_PER_CONNECTION - len(subs)
        subs.update(list(channels)[: max(0, room)])
        return subs

    def remove_channels(self, websocket: WebSocket, channels: set) -> set:
        subs = self.channel_subs.setdefault(websocket, set())
        subs.difference_update(channels)
        return subs

    def get_recent_signals(self) -> List[Dict[str, Any]]:
        """Newest-first list of recent setup payloads (for GET /api/setups)."""
        return [m.get("data", m) for m in reversed(self.recent_signals)]

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
            if not portfolio and self.state_manager:
                # Read this tenant's persisted state (namespaced by user_id); the global
                # bucket reads the legacy keys.
                portfolio = await self.state_manager.get_portfolio_state(user_id)
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
            if positions is None and self.state_manager:
                positions = await self.state_manager.get_positions(user_id)
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

            # Replay recent trade-setup suggestions (shared across users).
            for msg in list(self.recent_signals):
                try:
                    await websocket.send_text(json.dumps(msg, default=str))
                except Exception:
                    break
        except Exception as e:
            logger.error(f"Error hydrating client state: {e}")

    def disconnect(self, websocket: WebSocket):
        self.channel_subs.pop(websocket, None)
        if self.connections.pop(websocket, "missing") != "missing":
            logger.info(f"Client disconnected. Total: {len(self.connections)}")

    def _cache_state(self, key: str, portfolio: Optional[Dict] = None, positions: Optional[List] = None):
        bucket = self.initial_state.setdefault(key, {})
        if portfolio:
            bucket["portfolio"] = portfolio
        if positions is not None:
            bucket["positions"] = positions

    async def broadcast(self, message: Dict[str, Any], channel: Optional[str] = None):
        """Fan a message out to connected sockets.

        `channel` (e.g. "ticker.ETHUSDT") makes delivery OPT-IN: only sockets
        that subscribed to that market channel receive it. None keeps the
        legacy behavior — tenanted messages to their owner, untenanted to all.
        """
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

            # Buffer trade-setup suggestions (shared) for replay + GET /api/setups.
            if msg_type == "trade_setup":
                self.recent_signals.append(message)

            dead: List[WebSocket] = []
            for connection, uid in list(self.connections.items()):
                # Tenanted message -> only its owner's sockets. Untenanted -> everyone.
                if target is not None and uid != target:
                    continue
                # Channel-scoped market data -> only sockets that subscribed.
                if channel is not None and channel not in self.channel_subs.get(connection, ()):
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
# Per-user encrypted exchange-key vault (created once at startup, reuses the DB engine).
credential_vault = None
# Per-user trading settings (mode + active exchange), created once at startup.
user_settings_store = None
# Metered analysis sessions and per-user trading persona (M2 control plane).
session_manager = None
preferences_store = None


# --- Market-channel subscribe protocol -----------------------------------------
# Clients ask for extra symbols/streams over the socket:
#   {"op": "subscribe",   "channels": ["ticker.ETHUSDT", "kline.1m.ETHUSDT", "depth.ETHUSDT"]}
#   {"op": "unsubscribe", "channels": [...]}
# Channel grammar: ticker.<SYM> | depth.<SYM> | kline.<interval>.<SYM>, with SYM
# restricted to the configured traded symbols (no arbitrary upstream fan-out).
# The base BTCUSDT streams are always-on broadcasts for back-compat.

BASE_CHANNELS = {"ticker.BTCUSDT", "depth.BTCUSDT", "kline.1m.BTCUSDT"}
_ALLOWED_KLINE_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
_allowed_symbols = {s.upper() for s in get_config().trading.symbols}
# Streams already requested from Binance this process-lifetime. Add-only: with a
# handful of symbols the upstream cost is tiny, and per-connection filtering
# controls who actually receives frames.
_upstream_channels: set = set()


def _parse_channel(channel: str) -> Optional[Dict[str, str]]:
    """Validate + decompose a channel string; None when malformed/not allowed."""
    parts = channel.split(".")
    if len(parts) == 2 and parts[0] in ("ticker", "depth"):
        kind, symbol = parts[0], parts[1].upper()
    elif len(parts) == 3 and parts[0] == "kline" and parts[1] in _ALLOWED_KLINE_INTERVALS:
        kind, symbol = "kline", parts[2].upper()
    else:
        return None
    if symbol not in _allowed_symbols:
        return None
    return {"kind": kind, "symbol": symbol, "interval": parts[1] if kind == "kline" else ""}


def _market_channel(data: Dict[str, Any]) -> Optional[str]:
    """The channel key a raw Binance market event belongs to."""
    event = data.get("e")
    symbol = str(data.get("s", "")).upper()
    if not symbol:
        return None
    if event == "24hrTicker":
        return f"ticker.{symbol}"
    if event == "depthUpdate":
        return f"depth.{symbol}"
    if event == "kline":
        interval = (data.get("k") or {}).get("i", "1m")
        return f"kline.{interval}.{symbol}"
    return None


async def _ensure_upstream(channels: set) -> None:
    """Make sure Binance is streaming every requested channel (add-only)."""
    if binance_client is None:
        return
    for channel in channels:
        if channel in _upstream_channels or channel in BASE_CHANNELS:
            continue
        parsed = _parse_channel(channel)
        if parsed is None:
            continue
        symbol = parsed["symbol"].lower()
        try:
            if parsed["kind"] == "ticker":
                await binance_client.subscribe_ticker(symbol, handle_binance_update)
            elif parsed["kind"] == "depth":
                await binance_client.subscribe_depth(
                    symbol, levels=5, update_speed="100ms", callback=handle_binance_update
                )
            else:
                await binance_client.subscribe_kline(symbol, [parsed["interval"]], handle_binance_update)
            _upstream_channels.add(channel)
            logger.info(f"[ws] upstream subscribed: {channel}")
        except Exception as e:
            logger.error(f"[ws] upstream subscribe failed for {channel}: {e}")


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

    # Base BTCUSDT streams broadcast to everyone (legacy contract — the
    # dashboard predates the subscribe protocol). Every other market frame is
    # channel-scoped: delivered only to sockets that subscribed to it.
    channel = _market_channel(data)
    await manager.broadcast(payload, channel=None if channel in BASE_CHANNELS else channel)

async def handle_agent_message(data: Dict[str, Any]):
    """Callback for agent messages from MessageBus"""
    # Determine message type for frontend
    msg_type = "agent_update"
    
    # Check if this is an execution update (balance, positions, or resting orders)
    if data.get("type") in ["balance_update", "position_update", "open_orders"]:
        msg_type = "execution_status"

    # Trade-setup suggestion (from the daemon's analysis) -> Signals feed
    elif data.get("type") == "trade_setup":
        msg_type = "trade_setup"

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
    # Structured logging (LOG_JSON=true → JSON lines) + request-ID on every line.
    from src.utils.logging_setup import setup_logging
    setup_logging()
    logger.info("Starting up Antigravity API...")

    # Error tracking (Sentry) — no-op unless SENTRY_DSN is set.
    from src.utils.monitoring import init_monitoring
    init_monitoring("api")

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
        global trade_history_manager, credential_vault
        try:
            from src.memory.trade_history_manager import TradeHistoryManager
            trade_history_manager = await asyncio.to_thread(
                TradeHistoryManager, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize TradeHistoryManager: {e}")

        # Per-user exchange-key vault (needs VAULT_ENC_KEY; created lazily-safe).
        # Fail LOUDLY at startup when the master key is missing: without it every
        # connect-exchange attempt 500s at request time, which looks like a random
        # outage instead of a config error.
        if not os.getenv("VAULT_ENC_KEY", "").strip():
            logger.critical(
                "VAULT_ENC_KEY is NOT set — the exchange-key vault cannot encrypt/decrypt. "
                "Users cannot connect exchanges until it is configured. Generate once: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            from src.security.credential_vault import CredentialVault
            credential_vault = await asyncio.to_thread(
                CredentialVault, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize CredentialVault: {e}")

        # Per-user trading settings store (mode + active exchange).
        global user_settings_store
        try:
            from src.core.user_settings import UserSettingsStore
            user_settings_store = await asyncio.to_thread(
                UserSettingsStore, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize UserSettingsStore: {e}")

        # M2 control plane: metered sessions + per-user trading persona. Each is
        # initialised independently so one failing store does not take out the other.
        global session_manager, preferences_store
        try:
            from src.core.session_manager import SessionManager
            session_manager = await asyncio.to_thread(
                SessionManager, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize SessionManager: {e}")
        try:
            from src.core.preferences import PreferencesStore
            preferences_store = await asyncio.to_thread(
                PreferencesStore, config.database.postgres_url
            )
        except Exception as e:
            logger.error(f"Failed to initialize PreferencesStore: {e}")

        
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

    # Optional: run the multi-user trading daemon INSIDE this process. This is how the
    # free tier gets an always-on daemon — free hosts (e.g. Render) offer a free WEB
    # service but no free background workers, and it's all asyncio anyway. A keep-alive
    # ping (see .github/workflows/keepalive.yml) prevents the idle spin-down. Failure
    # is isolated: a daemon that can't start must never take the API down.
    if os.getenv("RUN_DAEMON_IN_API", "false").lower() == "true":
        global embedded_daemon
        try:
            from src.multi_user_daemon import MultiUserTradingDaemon
            embedded_daemon = MultiUserTradingDaemon()

            # Start in the BACKGROUND — daemon init backfills ~500 candles x 5
            # timeframes x 3 symbols (minutes). Awaiting it here blocks uvicorn's
            # startup, so the service serves nothing during a cold start and
            # health checks fail — on free tiers that reads as "never wakes up".
            async def _start_daemon_bg(d: "MultiUserTradingDaemon") -> None:
                global embedded_daemon
                try:
                    await d.start()
                    logger.info("Embedded trading daemon started in the API process")
                except Exception as e:
                    logger.error(f"Embedded daemon failed to start (API continues without it): {e}")
                    embedded_daemon = None

            asyncio.get_running_loop().create_task(_start_daemon_bg(embedded_daemon))
        except Exception as e:
            logger.error(f"Embedded daemon setup failed (API continues without it): {e}")
            embedded_daemon = None


# In-process daemon instance when RUN_DAEMON_IN_API=true (else None).
embedded_daemon = None


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down...")
    if embedded_daemon is not None:
        try:
            await embedded_daemon.stop()
        except Exception as e:
            logger.warning(f"Embedded daemon stop error: {e}")
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

    # Cap concurrent sockets per caller (tenant, or client IP when unscoped) so one
    # misbehaving client can't exhaust server connections.
    from src.utils.api_rate_limit import WS_CONNECTIONS_PER_CLIENT
    ws_key = user_id or (websocket.client.host if websocket.client else "unknown")
    open_count = sum(
        1 for ws, uid in manager.connections.items()
        if (uid or (ws.client.host if ws.client else "unknown")) == ws_key
    )
    if open_count >= WS_CONNECTIONS_PER_CLIENT:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            raw = await websocket.receive_text()
            # Client-driven market subscriptions (see the protocol block above).
            # Anything unparseable is ignored — never a reason to drop the socket.
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(msg, dict):
                continue
            op = msg.get("op")
            if op not in ("subscribe", "unsubscribe"):
                continue
            requested = {
                c for c in (msg.get("channels") or [])
                if isinstance(c, str) and _parse_channel(c) is not None
            }
            if op == "subscribe":
                current = manager.add_channels(websocket, requested)
                await _ensure_upstream(requested)
            else:
                current = manager.remove_channels(websocket, requested)
            # Ack with the connection's full channel set so the client can verify.
            try:
                await websocket.send_text(json.dumps(
                    {"type": "subscriptions", "data": sorted(current)}
                ))
            except Exception:
                pass
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
        
    except Exception:
        # Full details (with request_id) go to the logs; clients get a generic error so
        # internal paths/SQL/hostnames never leak in responses.
        logger.exception("Error fetching trades from database")
        return {"error": "Trade history is temporarily unavailable", "trades": []}


@app.get("/api/portfolio")
async def get_portfolio(principal: Dict[str, Any] = Depends(current_principal)):
    """The caller's current portfolio — persisted paper/live state if present,
    otherwise a freshly SEEDED paper account at the user's plan balance.

    This is what makes paper trading the honest default: a brand-new user's
    dashboard shows a real $10k virtual account immediately (0 trades, $0 P&L),
    no daemon push required. Once they connect an exchange, the live engine's
    published state takes over. Balance-update payload shape (matches the WS
    frame) so the frontend maps it identically.
    """
    user_id = principal.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="A logged-in user is required")
    if state_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio state unavailable")

    def _f(v, d=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    # 1) Persisted state (paper engine or live engine has published for this tenant).
    try:
        state = await state_manager.get_portfolio_state(user_id)
    except Exception:
        state = None
    if state and (state.get("current_balance") is not None or state.get("total_equity") is not None):
        return {
            "mode": state.get("mode", "paper"),
            "initial_balance": _f(state.get("initial_balance")),
            "current_balance": _f(state.get("current_balance")),
            "total_equity": _f(state.get("total_equity", state.get("current_balance"))),
            "unrealized_pnl": _f(state.get("unrealized_pnl")),
            "realized_pnl": _f(state.get("realized_pnl")),
            "win_rate": _f(state.get("win_rate")),
            "total_trades": int(_f(state.get("total_trades"))),
        }

    # 2) No state yet. If the user has connected exchange keys, they're live-pending
    #    (don't fabricate a paper balance); otherwise seed a paper account.
    has_keys = False
    try:
        if credential_vault is not None:
            active = "bingx"
            if user_settings_store is not None:
                active = user_settings_store.get(user_id).get("active_exchange", "bingx")
            has_keys = bool(credential_vault.get(user_id, active))
    except Exception:
        has_keys = False

    if has_keys:
        return {"mode": "live", "pending": True, "initial_balance": 0.0, "current_balance": 0.0,
                "total_equity": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0, "win_rate": 0.0,
                "total_trades": 0}

    initial = 10000.0
    try:
        from src.billing import plan_config
        initial = float(plan_config(user_id).initial_balance)
    except Exception:
        pass

    # Fold the user's settled-trade history into the seed so equity, realized P&L
    # and win-rate reconcile with the trade list + equity curve on the dashboard
    # (a brand-new user has none → clean $10k / $0 / 0).
    realized, wins, total = 0.0, 0, 0
    try:
        if trade_history_manager is not None:
            hist = await asyncio.to_thread(trade_history_manager.get_recent_trades, 500, None, user_id)
            closed = [t for t in hist if getattr(t, "exit_price", None)]
            total = len(closed)
            realized = sum(float(getattr(t, "pnl", 0) or 0) for t in closed)
            wins = sum(1 for t in closed if float(getattr(t, "pnl", 0) or 0) >= 0)
    except Exception:
        realized, wins, total = 0.0, 0, 0
    win_rate = (wins / total * 100.0) if total else 0.0

    baseline = {
        "initial_balance": initial, "current_balance": initial + realized,
        "total_equity": initial + realized, "unrealized_pnl": 0.0,
        "realized_pnl": realized, "win_rate": win_rate, "total_trades": total,
    }
    # Persist the seed so it's stable across loads (idempotent — only when empty).
    try:
        await state_manager.update_portfolio({**baseline, "mode": "paper"}, user_id=user_id)
    except Exception:
        logger.warning("Failed to persist seeded paper portfolio")
    return {"mode": "paper", **baseline}


# --- Per-user exchange-key vault endpoints -------------------------------------
def require_user(principal: Dict[str, Any] = Depends(current_principal)) -> str:
    """Require an authenticated end-user (not the service token). Returns user_id."""
    user_id = principal.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A logged-in user is required for this action",
        )
    return user_id


# Owner/admin allow-list — Supabase UUIDs from the ADMIN_USER_IDS env (comma-separated).
# These users may control the AI engine; everyone else can only read its status.
ADMIN_USER_IDS = {u.strip() for u in os.getenv("ADMIN_USER_IDS", "").split(",") if u.strip()}


def require_admin(principal: Dict[str, Any] = Depends(current_principal)) -> str:
    """Require an admin. The service token is always admin; end-users must be allow-listed."""
    # Service token (no user_id, authenticated via API_AUTH_TOKEN) is trusted. In local
    # dev with no auth configured, the anonymous principal is also allowed through.
    if principal.get("kind") in ("service", "anonymous"):
        return principal.get("kind")
    user_id = principal.get("user_id")
    # If no allow-list is configured, admin control is open (dev). Once ADMIN_USER_IDS
    # is set (prod), only those UUIDs pass — mirrors get_engine's `is_admin`.
    if not ADMIN_USER_IDS and user_id:
        return user_id
    if user_id and user_id in ADMIN_USER_IDS:
        return user_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the owner can control the AI engine",
    )


class ExchangeKeysBody(BaseModel):
    api_key: str
    api_secret: str
    exchange: str = "bingx"
    label: Optional[str] = None
    is_testnet: bool = True


@app.get("/api/exchange-keys")
async def get_exchange_keys(user_id: str = Depends(require_user)):
    """Non-secret status of the caller's stored exchange keys (masked)."""
    if credential_vault is None:
        return {"connected": False, "error": "vault unavailable"}
    st = await asyncio.to_thread(credential_vault.status, user_id)
    return st or {"connected": False}


@app.post("/api/exchange-keys")
async def save_exchange_keys(body: ExchangeKeysBody, user_id: str = Depends(require_user)):
    """Store (encrypted) the caller's own exchange API keys. Testnet-only for now."""
    if credential_vault is None:
        raise HTTPException(status_code=503, detail="Credential vault is not configured")
    # Hard safety gate: only testnet keys may be stored until live trading is unlocked.
    if not body.is_testnet:
        raise HTTPException(
            status_code=400,
            detail="Only testnet credentials may be stored while live trading is gated",
        )
    if not body.api_key.strip() or not body.api_secret.strip():
        raise HTTPException(status_code=400, detail="api_key and api_secret are required")

    # VERIFY before storing: "connected" must mean the exchange actually accepted the
    # keys (read-only balance probe on testnet), not merely that we encrypted whatever
    # was pasted. Bad keys -> 400; exchange unreachable -> 502 (not the user's fault).
    from src.execution.credential_check import ExchangeUnreachable, verify_exchange_credentials
    try:
        ok, reason = await verify_exchange_credentials(
            body.exchange, body.api_key.strip(), body.api_secret.strip()
        )
    except ExchangeUnreachable:
        logger.warning(f"Exchange {body.exchange} unreachable during key verification")
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach {body.exchange} to verify the keys — try again shortly.",
        )
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    try:
        await asyncio.to_thread(
            credential_vault.save, user_id, body.api_key.strip(), body.api_secret.strip(),
            body.exchange, body.label, body.is_testnet,
        )
    except Exception as e:
        logger.error(f"Failed to store exchange keys: {e}")
        raise HTTPException(status_code=500, detail="Could not store credentials")
    st = await asyncio.to_thread(credential_vault.status, user_id, body.exchange)
    return st or {"connected": True}


@app.delete("/api/exchange-keys")
async def delete_exchange_keys(exchange: str = "bingx", user_id: str = Depends(require_user)):
    """Remove the caller's stored keys for an exchange."""
    if credential_vault is None:
        raise HTTPException(status_code=503, detail="Credential vault is not configured")
    removed = await asyncio.to_thread(credential_vault.delete, user_id, exchange)
    return {"connected": False, "deleted": removed}


class SettingsBody(BaseModel):
    trading_mode: Optional[str] = None      # off | paper | manual | auto
    active_exchange: Optional[str] = None   # bingx | delta_india
    onboarded: Optional[bool] = None        # first-run onboarding completed


@app.get("/api/settings")
async def get_settings(user_id: str = Depends(require_user)):
    """The caller's trading settings (mode + active exchange), with safe defaults."""
    if user_settings_store is None:
        # Degraded fallback: report onboarded so a broken store can't trap users
        # in the onboarding redirect loop.
        return {"trading_mode": "paper", "active_exchange": "bingx", "onboarded": True}
    return await asyncio.to_thread(user_settings_store.get, user_id)


@app.post("/api/settings")
async def set_settings(body: SettingsBody, user_id: str = Depends(require_user)):
    """Update the caller's trading mode / active exchange."""
    if user_settings_store is None:
        raise HTTPException(status_code=503, detail="Settings store is not configured")
    try:
        return await asyncio.to_thread(
            user_settings_store.set, user_id, body.trading_mode, body.active_exchange,
            body.onboarded,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Metered analysis sessions (M2 control plane) ------------------------------
#
# Every handler here resolves the session THROUGH the caller's user_id rather than
# trusting a session_id from the request body. The backend connects as a privileged role
# that bypasses RLS, so application-layer scoping is the only guard against one user
# ending, approving, or reading another's session by guessing an id.

class SessionStartBody(BaseModel):
    # Lets a caller request less than their full remaining quota (e.g. a 10-minute
    # session). Never more: the manager clamps to what is actually left today.
    quota_seconds: Optional[int] = Field(default=None, ge=60, le=24 * 3600)


def _require_sessions():
    if session_manager is None:
        raise HTTPException(status_code=503, detail="Session manager is not configured")
    return session_manager


async def _owned_session(user_id: str) -> Dict[str, Any]:
    """The caller's own active session, or 404. Never takes an id from the client."""
    mgr = _require_sessions()
    active = await asyncio.to_thread(mgr.get_active, user_id)
    if active is None:
        raise HTTPException(status_code=404, detail="No active session")
    return active


@app.get("/api/session")
async def get_session(user_id: str = Depends(require_user)):
    """The caller's active session plus today's remaining quota.

    Returns `session: null` rather than 404 when idle — "you have no session" is a normal
    state the dashboard renders, not an error.
    """
    mgr = _require_sessions()
    active = await asyncio.to_thread(mgr.get_active, user_id)
    remaining = await asyncio.to_thread(mgr.remaining_today, user_id)
    used = await asyncio.to_thread(mgr.used_today, user_id)
    return {
        "session": active,
        "daily_quota_seconds": mgr.daily_quota_seconds,
        "used_today_seconds": used,
        "remaining_today_seconds": remaining,
    }


@app.post("/api/session/start")
async def start_session(
    body: SessionStartBody = SessionStartBody(),
    user_id: str = Depends(require_user),
):
    """Begin a metered session. 429 when the daily quota is spent."""
    from src.core.session_manager import QuotaExhausted, SessionError

    mgr = _require_sessions()
    try:
        return await asyncio.to_thread(mgr.start, user_id, body.quota_seconds)
    except QuotaExhausted as e:
        # 429 rather than 403: this is a rate limit that resets, not a permission
        # problem the user can do anything about.
        raise HTTPException(status_code=429, detail=str(e))
    except SessionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/session/end")
async def end_session(user_id: str = Depends(require_user)):
    """End the caller's session early. Any open position keeps being monitored."""
    from src.core.session_manager import USER_ENDED, SessionError

    mgr = _require_sessions()
    active = await _owned_session(user_id)
    try:
        return await asyncio.to_thread(mgr.end, active["session_id"], USER_ENDED, "ended by user")
    except SessionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/session/approve")
async def approve_proposal(user_id: str = Depends(require_user)):
    """Manual mode: accept the pending proposal and move to execution.

    Re-validation of price, spread, and risk limits happens in the execution path, not
    here — a proposal approved minutes later is not the same trade, and this endpoint
    must not be the thing that decides it still is.
    """
    from src.core.session_manager import IllegalTransition

    mgr = _require_sessions()
    active = await _owned_session(user_id)
    try:
        return await asyncio.to_thread(mgr.approve, active["session_id"])
    except IllegalTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/session/reject")
async def reject_proposal(user_id: str = Depends(require_user)):
    """Decline the pending proposal and resume scanning. Restarts the meter."""
    from src.core.session_manager import IllegalTransition

    mgr = _require_sessions()
    active = await _owned_session(user_id)
    try:
        return await asyncio.to_thread(mgr.reject, active["session_id"])
    except IllegalTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/session/events")
async def get_session_events(limit: int = 200, user_id: str = Depends(require_user)):
    """The caller's live agent feed for their active session."""
    mgr = _require_sessions()
    active = await _owned_session(user_id)
    events = await asyncio.to_thread(
        mgr.events, active["session_id"], max(1, min(limit, 500))
    )
    return {"session_id": active["session_id"], "events": events}


# --- Per-user trading preferences ---------------------------------------------

class PreferencesBody(BaseModel):
    """Partial update. Every field optional; only what is sent is changed.

    Bounds here are input sanity only — the real ceiling is applied by the store, which
    clamps against the caller's plan and an absolute hard cap. Preferences may only ever
    tighten risk, never widen it.
    """
    model_config = {"extra": "forbid"}  # reject typos loudly rather than dropping them

    trading_capital: Optional[float] = Field(default=None, gt=0)
    capital_currency: Optional[str] = Field(default=None, max_length=8)
    risk_appetite: Optional[str] = None
    max_risk_per_trade_pct: Optional[float] = Field(default=None, gt=0)
    max_concurrent_positions: Optional[int] = Field(default=None, ge=1)
    max_daily_trades: Optional[int] = Field(default=None, ge=1)
    max_leverage: Optional[float] = Field(default=None, gt=0)
    monthly_pnl_target_pct: Optional[float] = Field(default=None, gt=0)
    goal_horizon: Optional[str] = None
    goal_notes: Optional[str] = Field(default=None, max_length=500)
    symbol_universe: Optional[List[str]] = Field(default=None, max_length=50)
    allowed_strategies: Optional[List[str]] = Field(default=None, max_length=50)
    min_risk_reward: Optional[float] = Field(default=None, ge=1.0)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    avoid_high_funding: Optional[bool] = None


def _plan_caps_for(user_id: str) -> Dict[str, float]:
    """Risk ceilings from the caller's subscription tier."""
    try:
        from src.billing.plans import plan_for_user
        plan = plan_for_user(user_id)
        return {
            "max_risk_per_trade_pct": plan.max_risk_per_trade * 100.0,
            "max_concurrent_positions": float(plan.max_concurrent_positions),
            "max_daily_trades": float(plan.max_daily_trades),
        }
    except Exception as e:
        # Fail CLOSED: an unresolvable plan must not mean "no ceiling".
        logger.warning(f"could not resolve plan caps for {user_id}: {e}; using free tier")
        return {
            "max_risk_per_trade_pct": 1.0,
            "max_concurrent_positions": 1.0,
            "max_daily_trades": 3.0,
        }


@app.get("/api/preferences")
async def get_preferences(user_id: str = Depends(require_user)):
    """The caller's trading persona, with conservative defaults when unset."""
    if preferences_store is None:
        raise HTTPException(status_code=503, detail="Preferences store is not configured")
    return await asyncio.to_thread(preferences_store.get, user_id)


@app.post("/api/preferences")
async def set_preferences(body: PreferencesBody, user_id: str = Depends(require_user)):
    """Partial update. Risk fields are clamped to the caller's plan; see the store."""
    from src.core.preferences import PreferencesError

    if preferences_store is None:
        raise HTTPException(status_code=503, detail="Preferences store is not configured")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return await asyncio.to_thread(preferences_store.get, user_id)
    try:
        return await asyncio.to_thread(
            preferences_store.set, user_id, updates, _plan_caps_for(user_id)
        )
    except PreferencesError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- AI engine switch (owner-controlled; protects the LLM quota) --------------
class EngineBody(BaseModel):
    enabled: bool
    # How long to stay on before auto-off. None/0 = "always on" (until turned off).
    # Bounded so a fat-finger can't leave it running for weeks.
    duration_seconds: Optional[int] = Field(default=None, ge=0, le=7 * 24 * 3600)


def _engine_switch():
    """Build an EngineSwitch on the shared Redis client, or None if Redis is down."""
    if state_manager is None or getattr(state_manager, "redis", None) is None:
        return None
    from src.core.engine_switch import EngineSwitch
    return EngineSwitch(state_manager.redis)


@app.get("/api/engine")
async def get_engine(principal: Dict[str, Any] = Depends(current_principal)):
    """AI-engine status — any authenticated caller can see whether analysis is running.

    Also reports `is_admin` so the dashboard only shows the toggle to the owner.
    """
    sw = _engine_switch()
    status_obj = await sw.status() if sw else {"enabled": False, "expires_in_seconds": None, "enabled_by": None}
    uid = principal.get("user_id")
    # Admin if: service/anonymous principal, allow-list unset (dev), or listed owner.
    status_obj["is_admin"] = (
        principal.get("kind") in ("service", "anonymous")
        or not ADMIN_USER_IDS
        or (uid is not None and uid in ADMIN_USER_IDS)
    )
    return status_obj


@app.post("/api/engine")
async def set_engine(body: EngineBody, admin: str = Depends(require_admin)):
    """Turn the AI engine on/off (owner only). On = daemon resumes analysis + LLM calls."""
    sw = _engine_switch()
    if sw is None:
        raise HTTPException(status_code=503, detail="Engine switch unavailable (Redis down)")
    if body.enabled:
        return await sw.turn_on(duration_seconds=body.duration_seconds, enabled_by=admin)
    return await sw.turn_off(disabled_by=admin)


@app.get("/api/setups")
async def get_setups():
    """Recent trade-setup suggestions (shared across users) for load-time hydration.

    Not user-scoped: setups are the same for everyone; only EXECUTION is per-user.
    Live updates arrive over the WebSocket as `trade_setup` messages.
    """
    return {"setups": manager.get_recent_signals()}


class ExecuteSetupBody(BaseModel):
    # Bounded inputs so a malformed/hostile body can't submit a nonsensical or oversized
    # order; per-user risk validation still runs downstream.
    symbol: str = Field(..., min_length=3, max_length=20)
    direction: str = Field(..., pattern="^(LONG|SHORT)$")
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    take_profit_levels: List[float] = Field(default_factory=list, max_length=10)
    confidence_score: Optional[float] = Field(default=None, ge=0)
    market_regime: Optional[str] = Field(default=None, max_length=40)
    recommended_position_size: Optional[float] = Field(default=None, ge=0)


def _build_user_engine(user_id: str):
    """Build the caller's execution engine: LIVE (connected exchange) or paper fallback.

    Manual execution routes through the SAME per-user risk-gate + full-bracket path the
    daemon uses (UserSession.evaluate_and_book), so a manual order behaves identically to
    an auto one — just triggered by the user.
    """
    exchange = "bingx"
    if user_settings_store is not None:
        exchange = user_settings_store.get(user_id).get("active_exchange", "bingx")
    if credential_vault is not None:
        creds = credential_vault.get(user_id, exchange)
        if creds:
            from src.execution.live_execution_engine import LiveExecutionEngine
            api_key, api_secret = creds
            return LiveExecutionEngine(
                user_id=user_id, exchange_name=exchange,
                api_key=api_key, api_secret=api_secret,
                message_bus=message_bus, state_manager=state_manager,
            ), exchange, True
    return None, exchange, False  # no connected exchange -> paper (UserSession default)


@app.post("/api/execute-setup")
async def execute_setup(body: ExecuteSetupBody, user_id: str = Depends(require_user)):
    """Manually place a setup as a full bracket (entry + SL + TPs) for the caller.

    Uses the caller's connected exchange (testnet-gated) if present, else a paper engine.
    """
    try:
        from src.core.multi_user import UserSession, UserRiskConfig
        try:
            from src.billing import plan_config
            config = await asyncio.to_thread(plan_config, user_id)
        except Exception:
            config = UserRiskConfig()

        engine, exchange, is_live = await asyncio.to_thread(_build_user_engine, user_id)
        session = UserSession(
            user_id, message_bus=message_bus, state_manager=state_manager,
            config=config, exchange=engine,
        )

        # The risk gate VALIDATES a size — it never invents one. AI setups arrive
        # pre-sized by the strategy agent's PositionSizer; a hand-built terminal
        # ticket doesn't, so size it here with the SAME sizer (fixed-risk % of the
        # account over the stop distance) against the caller's plan-sized account.
        # Without this, ticket brackets validated at $0 and always rejected.
        recommended = body.recommended_position_size or 0.0
        risk_amount = 0.0
        if recommended <= 0:
            from src.strategy.position_sizer import PositionSizer
            # Size INSIDE the caller's plan limits (the sizer's own defaults can
            # exceed a small plan's caps and get the bracket auto-rejected):
            # risk% from the plan's max_risk_per_trade, notional capped at the
            # plan's max_position_size_usd.
            params = config.risk_params
            plan_risk_pct = (params.max_risk_per_trade * 100) if params else None
            sizing = PositionSizer().calculate_size(
                account_balance=config.initial_balance,
                entry_price=body.entry_price,
                stop_loss=body.stop_loss,
                risk_percent=plan_risk_pct,
            )
            recommended = sizing.recommended_size
            risk_amount = sizing.risk_amount
            if params and recommended * body.entry_price > params.max_position_size_usd:
                recommended = params.max_position_size_usd / body.entry_price
                risk_amount = recommended * abs(body.entry_price - body.stop_loss)

        setup = {
            "symbol": body.symbol,
            "direction": body.direction,
            "entry_price": body.entry_price,
            "stop_loss": body.stop_loss,
            "take_profit_levels": body.take_profit_levels,
            # The risk gate's 0.65 confidence floor exists for MACHINE-proposed
            # setups. A hand-built ticket carries no model score — the human
            # reviewed and confirmed the bracket, which IS the confidence — so
            # an absent score defaults to 1.0 rather than 0.0 (which made every
            # manual/paper ticket auto-reject). AI setups executed manually still
            # pass their real score through and stay gated.
            "confidence_score": body.confidence_score if body.confidence_score is not None else 1.0,
            "market_regime": body.market_regime,
            "recommended_position_size": recommended,
            "risk_amount": risk_amount,
        }

        if is_live and engine is not None:
            # Keyed users book at the exchange — it is the source of truth, so a
            # request-scoped engine is correct here.
            result = await session.evaluate_and_book(setup)
        else:
            # PAPER books in the DAEMON's long-lived engine (over the bus, reply
            # via a short-lived Redis key). A request-scoped paper engine dies
            # with the request: its position couldn't settle on close and its
            # resting SL/TP legs were unlistable. Daemon ownership fixes both.
            result = await _dispatch_user_command({
                "type": "execute_setup",
                "user_id": user_id,
                "setup": setup,
            })
            if result is None:
                raise HTTPException(
                    status_code=504,
                    detail="The trading daemon didn't answer in time — nothing was booked. Try again.",
                )
        result["exchange"] = exchange
        result["live"] = is_live
        return result
    except Exception:
        # Log the full error server-side (correlated via X-Request-ID); keep the client
        # message generic — exception text can carry internal details.
        logger.exception(f"execute-setup failed for {user_id}")
        raise HTTPException(
            status_code=500,
            detail="Execution failed — see server logs (X-Request-ID header correlates).",
        )


import uuid as _uuid

REPLY_POLL_INTERVAL_S = 0.25
REPLY_TIMEOUT_S = 12.0


async def _dispatch_user_command(command: Dict[str, Any], *, wait: bool = True) -> Optional[Dict[str, Any]]:
    """Send a tenant command to the daemon over the bus; await its reply key.

    Transport is deliberately boring: the daemon writes the result to
    `cmd_reply:{correlation_id}` (60s TTL) and this polls it — identical
    behavior whether the daemon is embedded in this process or a separate
    container. Returns None on timeout / when the bus is down.
    """
    if message_bus is None or state_manager is None:
        return None
    cid = str(_uuid.uuid4())
    command = {**command, "correlation_id": cid,
               "timestamp": datetime.now(timezone.utc).isoformat()}
    await message_bus.publish("user_commands", command, persist=False)
    if not wait:
        return {"dispatched": True}
    deadline = asyncio.get_event_loop().time() + REPLY_TIMEOUT_S
    while asyncio.get_event_loop().time() < deadline:
        reply = await state_manager.get(f"cmd_reply:{cid}")
        if reply is not None:
            return reply
        await asyncio.sleep(REPLY_POLL_INTERVAL_S)
    return None


# --- Per-user positions: list + close (the terminal's P0 surface) ---------------
# A trading UI that can open but not close reads broken. These are PER-USER,
# tenant-scoped routes — the global panic_close below stays a service control and
# must never be user-facing.

@app.get("/api/positions")
async def get_user_positions(user_id: str = Depends(require_user)):
    """The caller's open positions (Redis read-through — per-user engines persist here).

    Covers the page-refresh race where the WS hydration frame hasn't arrived yet.
    """
    if state_manager is None:
        raise HTTPException(status_code=503, detail="State manager unavailable")
    positions = await state_manager.get_positions(user_id=user_id)
    return {"positions": positions, "source": "state"}


class ClosePositionBody(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    position_id: Optional[str] = Field(default=None, max_length=80)


async def _close_live_position(engine, symbol: str) -> Dict[str, Any]:
    """Reduce-only market close of one symbol's position at the exchange.

    The exchange is the source of truth for keyed users, so a freshly built
    engine (same pattern as execute-setup) resolves side/quantity server-side.
    """
    from src.execution.exchange_client import OrderSide
    norm = symbol.replace("-", "").upper()
    positions = await engine.client.get_open_positions()
    target = next(
        (p for p in positions if str(p.symbol).replace("-", "").upper() == norm), None
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"No open {symbol} position at the exchange")
    side = OrderSide.SELL if str(target.side).upper() == "LONG" else OrderSide.BUY
    order = await engine.close_position(
        symbol=target.symbol, side=side, quantity=abs(float(target.quantity))
    )
    await engine.publish_portfolio_update()
    return {"closed": True, "live": True, "order_id": getattr(order, "order_id", None)}


@app.post("/api/positions/close")
async def close_user_position(body: ClosePositionBody, user_id: str = Depends(require_user)):
    """Close ONE of the caller's positions.

    Keyed users close directly at the exchange (source of truth). Paper positions
    live in the daemon's long-lived engine, so the close dispatches over the bus
    and settles there; the UI receives the authoritative removal on the next
    position_update frame.
    """
    try:
        engine, exchange, is_live = await asyncio.to_thread(_build_user_engine, user_id)
        if is_live and engine is not None:
            result = await _close_live_position(engine, body.symbol)
            result["exchange"] = exchange
            return result
        if message_bus is None:
            raise HTTPException(status_code=503, detail="Message bus unavailable")
        await message_bus.publish("user_commands", {
            "type": "close_position",
            "user_id": user_id,
            "symbol": body.symbol,
            "position_id": body.position_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, persist=False)
        return {
            "closed": False, "dispatched": True, "live": False,
            "detail": "Close dispatched to the paper engine — the next position_update confirms.",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"close-position failed for {user_id}")
        raise HTTPException(status_code=500, detail="Close failed — see server logs (X-Request-ID correlates).")


@app.post("/api/positions/close-all")
async def close_all_user_positions(user_id: str = Depends(require_user)):
    """Close ALL of the caller's positions — their account only, never global."""
    try:
        engine, exchange, is_live = await asyncio.to_thread(_build_user_engine, user_id)
        if is_live and engine is not None:
            from src.execution.exchange_client import OrderSide
            positions = await engine.client.get_open_positions()
            order_ids = []
            for p in positions:
                side = OrderSide.SELL if str(p.side).upper() == "LONG" else OrderSide.BUY
                order = await engine.close_position(
                    symbol=p.symbol, side=side, quantity=abs(float(p.quantity))
                )
                order_ids.append(getattr(order, "order_id", None))
            await engine.publish_portfolio_update()
            return {"closed": len(order_ids), "live": True, "exchange": exchange}
        if message_bus is None:
            raise HTTPException(status_code=503, detail="Message bus unavailable")
        await message_bus.publish("user_commands", {
            "type": "close_all",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, persist=False)
        return {"dispatched": True, "live": False}
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"close-all failed for {user_id}")
        raise HTTPException(status_code=500, detail="Close-all failed — see server logs (X-Request-ID correlates).")


# --- Working orders: list + cancel ----------------------------------------------
# Paper orders live in the daemon's long-lived engine and are mirrored to Redis
# on every portfolio publish; keyed users read through to the exchange.

@app.get("/api/orders")
async def get_user_orders(user_id: str = Depends(require_user)):
    """The caller's open (resting) orders — e.g. a bracket's SL/TP legs."""
    try:
        engine, exchange, is_live = await asyncio.to_thread(_build_user_engine, user_id)
        if is_live and engine is not None:
            try:
                orders = await engine.client.get_open_orders()
                return {"orders": orders, "source": "exchange", "exchange": exchange}
            except AttributeError:
                # Exchange client without an open-orders endpoint: disclose it.
                return {"orders": [], "source": "unsupported", "exchange": exchange}
        if state_manager is None:
            raise HTTPException(status_code=503, detail="State manager unavailable")
        orders = await state_manager.get_orders(user_id=user_id)
        return {"orders": orders, "source": "paper"}
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"get-orders failed for {user_id}")
        raise HTTPException(status_code=500, detail="Orders unavailable — see server logs.")


@app.delete("/api/orders/{order_id}")
async def cancel_user_order(
    order_id: str,
    symbol: str = Query(..., min_length=3, max_length=20),
    user_id: str = Depends(require_user),
):
    """Cancel ONE of the caller's resting orders."""
    try:
        engine, exchange, is_live = await asyncio.to_thread(_build_user_engine, user_id)
        if is_live and engine is not None:
            ok = await engine.client.cancel_order(symbol, order_id)
            return {"canceled": bool(ok), "live": True, "exchange": exchange}
        result = await _dispatch_user_command({
            "type": "cancel_order",
            "user_id": user_id,
            "order_id": order_id,
            "symbol": symbol,
        })
        if result is None:
            raise HTTPException(
                status_code=504,
                detail="The trading daemon didn't answer in time — the order may still be open.",
            )
        return {**result, "live": False}
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"cancel-order failed for {user_id}")
        raise HTTPException(status_code=500, detail="Cancel failed — see server logs.")


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
    except Exception:
        logger.exception("Error dispatching close-positions command")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not dispatch close-positions — see server logs.",
        )

@app.get("/health")
async def health_check():
    """Human/dashboard status. Always 200 — this is a report, not a gate.

    `message_bus` must reflect whether Redis is actually REACHABLE, not merely whether
    the object was constructed. `startup_event` catches the connection failure and
    carries on, so `message_bus is not None` stays True against a dead Redis and this
    endpoint used to report a broken instance as fully healthy.

    Gates live elsewhere and are unchanged: /health/live for liveness (never checks
    dependencies), /health/ready for readiness (503s when deps are down).
    """
    try:
        bus_ok = bool(message_bus) and bool(
            await asyncio.wait_for(message_bus.redis_client.ping(), timeout=2)
        )
    except Exception:
        bus_ok = False

    return {
        "status": "online" if bus_ok else "degraded",
        "connections": len(manager.active_connections),
        "message_bus": bus_ok,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint (request counts/latency, rate-limit hits, WS gauge,
    process metrics)."""
    from fastapi.responses import Response
    from src.utils.metrics import WS_CONNECTIONS, render_latest
    WS_CONNECTIONS.set(len(manager.connections))
    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)


@app.get("/health/live")
async def health_live():
    """Liveness: the process is up and serving. Never checks dependencies — a dead
    Redis must NOT make the orchestrator kill/restart the API pod."""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """Readiness: can this instance actually serve traffic? Checks the message bus
    (Redis) and the trade DB. Returns 503 while not ready so load balancers /
    orchestrators keep traffic away without restarting the process."""
    from fastapi.responses import JSONResponse
    checks: Dict[str, bool] = {}

    try:
        checks["redis"] = bool(message_bus) and await asyncio.wait_for(
            message_bus.redis_client.ping(), timeout=2
        )
    except Exception:
        checks["redis"] = False

    try:
        if trade_history_manager is not None:
            def _db_ping() -> bool:
                from sqlalchemy import text
                with trade_history_manager.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return True
            checks["database"] = await asyncio.wait_for(asyncio.to_thread(_db_ping), timeout=3)
        else:
            checks["database"] = False
    except Exception:
        checks["database"] = False

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )

if __name__ == "__main__":
    import uvicorn
    # Bind to localhost by default; only expose externally behind an authenticating
    # proxy (and with API_AUTH_TOKEN set). Override via API_HOST.
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("src.api.server:app", host=host, port=port, reload=True)
