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
from datetime import datetime
from typing import Any, List, Optional

from loguru import logger

from src.execution.exchange_client import ExchangeClientFactory

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

    def get_positions(self):
        """Sync stub for parity with the paper engine (live positions are async)."""
        return []
