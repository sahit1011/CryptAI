"""Per-user LIVE execution engine — a thin adapter over a real ExchangeClient.

The multi-user engine (UserSession/OrderManager) is written against the interface the
PaperTradingEngine exposes: the OrderManager calls place_market_order / place_limit_order
/ place_stop_loss_order / cancel_order / close_position / get_order_status on its
`exchange`, and UserSession calls `publish_portfolio_update()`. A real `ExchangeClient`
already implements the six order methods, so this adapter:

  * delegates those six straight through to the tenant's connected exchange client, and
  * adds `publish_portfolio_update()` — reading live balance + positions from the
    exchange and publishing them to the user's WebSocket in the SAME shape the paper
    engine uses (so the dashboard renders identically).

HARD SAFETY GATE: this engine is testnet-only. It builds the client with testnet=True
and refuses to operate on mainnet unless LIVE_TRADING_CONFIRMED=true (the operator's
explicit, deliberate final step). Auto/manual live trading rides on this until the live
path is validated on testnet.
"""
import os
import time
from datetime import datetime
from typing import Any, List, Optional

from loguru import logger

from src.execution.exchange_client import ExchangeClientFactory

#: How long a cached venue position list may be trusted. Beyond this, get_positions()
#: reports NOTHING rather than something possibly closed at the venue — the monitor
#: showing "unknown" is safer than it managing a phantom.
POSITION_CACHE_TTL_S = float(os.getenv("LIVE_POSITION_CACHE_TTL_S", "120"))

# Exchange name the vault/settings use -> the factory's key.
_EXCHANGE_ALIASES = {"delta_india": "delta_india", "delta": "delta_india", "bingx": "bingx"}


class LiveExecutionEngine:
    """Adapts a tenant's real ExchangeClient to the engine interface the OrderManager uses."""

    def __init__(
        self,
        user_id: str,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        message_bus: Optional[Any] = None,
        state_manager: Optional[Any] = None,
        initial_balance: float = 0.0,
    ):
        self.user_id = user_id
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.initial_balance = initial_balance
        self.exchange_name = _EXCHANGE_ALIASES.get(exchange_name.lower(), exchange_name.lower())

        # HARD GATE: testnet only unless the operator has explicitly confirmed live.
        live_confirmed = os.getenv("LIVE_TRADING_CONFIRMED", "false").lower() == "true"
        testnet = not live_confirmed  # mainnet only when live is confirmed
        if not testnet:
            logger.warning(f"[live] LIVE_TRADING_CONFIRMED=true — {user_id} on MAINNET")
        self.testnet = testnet

        # Venue positions, refreshed by refresh_positions() (see get_positions()).
        self._positions_cache: List[dict] = []
        self._positions_cached_at: float = 0.0

        self.client = ExchangeClientFactory.create_client(
            self.exchange_name, api_key, api_secret, testnet=testnet
        )
        logger.info(f"[live] engine for {user_id} on {self.exchange_name} (testnet={testnet})")

    # --- order methods: delegate straight to the real exchange client ---------------
    async def place_market_order(self, *args, **kwargs):
        return await self.client.place_market_order(*args, **kwargs)

    async def place_limit_order(self, *args, **kwargs):
        return await self.client.place_limit_order(*args, **kwargs)

    async def place_stop_loss_order(self, *args, **kwargs):
        return await self.client.place_stop_loss_order(*args, **kwargs)

    async def cancel_order(self, *args, **kwargs):
        return await self.client.cancel_order(*args, **kwargs)

    async def cancel_all_orders(self, *args, **kwargs):
        return await self.client.cancel_all_orders(*args, **kwargs)

    async def close_position(self, *args, **kwargs):
        return await self.client.close_position(*args, **kwargs)

    async def get_order_status(self, *args, **kwargs):
        return await self.client.get_order_status(*args, **kwargs)

    # --- portfolio publishing: live balance + positions -> the user's WebSocket -------
    async def _publish(self, update_type: str, payload: Any):
        if not self.message_bus:
            return
        try:
            message = {"type": update_type, "payload": payload, "timestamp": datetime.now().isoformat()}
            if self.user_id:
                message["user_id"] = self.user_id  # route to this tenant's sockets only
            await self.message_bus.publish("execution_status", message)
        except Exception as e:
            logger.error(f"[live] publish failed for {self.user_id}: {e}")

    async def publish_portfolio_update(self):
        """Read live balance + positions from the exchange and push to the dashboard."""
        try:
            balance = await self.client.get_account_balance()
        except Exception as e:
            logger.warning(f"[live] balance fetch failed for {self.user_id}: {e}")
            balance = {}
        try:
            positions = await self.client.get_open_positions()
        except Exception as e:
            logger.warning(f"[live] positions fetch failed for {self.user_id}: {e}")
            positions = []

        equity = float(balance.get("equity", balance.get("total", balance.get("balance", 0.0))) or 0.0)
        avail = float(balance.get("available", balance.get("free", equity)) or 0.0)
        unrealized = sum(float(getattr(p, "unrealized_pnl", 0) or 0) for p in positions) if positions else 0.0

        await self._publish("balance_update", {
            "total_equity": round(equity, 2),
            "current_balance": round(avail, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": 0.0,
            "open_positions": len(positions),
            "live": True,
            "exchange": self.exchange_name,
        })
        # Normalize positions to plain dicts for the frontend.
        pos_payload: List[dict] = []
        for p in positions:
            if hasattr(p, "__dict__"):
                pos_payload.append({k: v for k, v in vars(p).items() if not k.startswith("_")})
            elif isinstance(p, dict):
                pos_payload.append(p)
        await self._publish("position_update", pos_payload)

        if self.state_manager and self.user_id:
            try:
                await self.state_manager.replace_positions(pos_payload, user_id=self.user_id)
            except Exception:
                pass

    async def publish_initial_state(self):
        await self.publish_portfolio_update()

    async def refresh_positions(self) -> int:
        """Pull open positions from the VENUE and cache them. Returns the count.

        The venue is the source of truth for a live account — unlike the paper desk,
        where our own rows are. This is the reconciliation read that makes live
        positions visible to the monitor at all.
        """
        try:
            positions = await self.client.get_open_positions()
        except Exception as e:
            # Do NOT clear the cache on a transient failure: dropping to zero would
            # tell the monitor "nothing to watch", which is exactly the silence this
            # method exists to end. Let it age out via POSITION_CACHE_TTL_S instead.
            logger.warning(f"[live] position refresh failed for {self.user_id}: {e}")
            return len(self._positions_cache)

        payload: List[dict] = []
        for p in positions or []:
            d = p.to_dict() if hasattr(p, "to_dict") else (
                dict(p) if isinstance(p, dict) else None)
            if not d:
                continue
            # Present in the SAME shape the paper engine publishes, so the monitor and
            # the dashboard need no per-engine special cases.
            qty = float(d.get("quantity") or 0)
            if qty == 0:
                continue  # a flat position is not an open position
            payload.append({
                "position_id": f"LIVE_{self.exchange_name}_{d.get('symbol')}",
                "symbol": d.get("symbol"),
                "positionSide": str(d.get("side") or "").upper(),
                "positionAmt": str(qty),
                "entryPrice": str(d.get("entry_price") or 0),
                "markPrice": str(d.get("mark_price") or d.get("entry_price") or 0),
                "unRealizedProfit": str(d.get("unrealized_pnl") or 0),
                "leverage": str(d.get("leverage") or 1),
                "live": True,
            })
        self._positions_cache = payload
        self._positions_cached_at = time.monotonic()
        return len(payload)

    def get_positions(self):
        """Cached venue positions, or [] when the cache is missing or STALE.

        Sync because the monitor's discovery is sync (and the paper engine's positions
        live in memory). Staleness returns [] deliberately: acting on a position list
        we can no longer confirm risks managing a phantom — one that may already have
        been closed at the venue. Empty means "we do not know", which is the same
        honest signal `/api/monitors` already renders as `monitored: false`.
        """
        if not self._positions_cache:
            return []
        age = time.monotonic() - self._positions_cached_at
        if age > POSITION_CACHE_TTL_S:
            logger.warning(
                f"[live] position cache for {self.user_id} is {age:.0f}s old "
                f"(> {POSITION_CACHE_TTL_S}s) — reporting NO positions rather than "
                "stale ones; live monitoring is blind until a refresh succeeds"
            )
            return []
        return list(self._positions_cache)
