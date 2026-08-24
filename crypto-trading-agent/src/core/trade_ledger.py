"""The trade ledger consumer — row persistence decoupled from the memory agent.

Found during R2.1 (wiring law): production runs DAEMON_DISABLE_AGENTS=memory
because MemoryAgent pulls chromadb + ONNX embeddings that cannot fit a 512MB
instance — but MemoryAgent was ALSO the only subscriber to `memory_agent_inbox`,
so disabling it silently dropped every `log_trade` and `update_trade` message.
Consequence: the deployed daemon persisted NO trade rows — no journal for users,
nothing for rehydration to rebuild from, no outcome ledger for the evidence plan.

This consumer is the ~100-line core that must never be optional: it writes the
`trades` rows through TradeHistoryManager and nothing else. The full MemoryAgent
still handles the same messages when enabled (adding vector memory on top) — the
daemon subscribes EXACTLY ONE of the two, never both (double inserts).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from loguru import logger


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.now()


class TradeLedgerConsumer:
    """Subscribes to memory_agent_inbox and persists trade rows. Nothing more."""

    def __init__(self, database_url: str):
        # Deferred import keeps this module import-light (server smoke test).
        from src.memory.trade_history_manager import TradeHistoryManager

        self.trade_history = TradeHistoryManager(database_url)
        self.rows_written = 0
        self.rows_updated = 0

    async def handle(self, message: Dict[str, Any]) -> None:
        """Bus callback. Only log_trade / update_trade are ours; ignore the rest.

        Never raises: the bus loop must survive a malformed message or a DB blip —
        but every failure is LOUD, because a silently dropped row is exactly the
        failure mode this class exists to end.
        """
        try:
            msg_type = (message or {}).get("type")
            payload = (message or {}).get("payload") or {}
            if msg_type == "log_trade":
                await self._log_trade(payload)
            elif msg_type == "update_trade":
                await self._update_trade(payload)
        except Exception as e:
            logger.error(f"[trade-ledger] failed to persist {message.get('type')} "
                         f"for trade {((message or {}).get('payload') or {}).get('trade_id')}: {e}")

    async def _log_trade(self, p: Dict[str, Any]) -> None:
        await asyncio.to_thread(
            self.trade_history.store_trade,
            trade_id=p.get("trade_id"),
            symbol=p.get("symbol"),
            direction=p.get("direction"),
            entry_price=float(p.get("entry_price") or 0.0),
            entry_time=_parse_dt(p.get("entry_time")),
            position_size=float(p.get("position_size") or 0.0),
            stop_loss=float(p.get("stop_loss") or 0.0),
            take_profit_levels=p.get("take_profit_levels") or [],
            risk_amount=float(p.get("risk_amount") or 0.0),
            strategy_type=p.get("strategy_type", "") or "",
            confidence_score=float(p.get("confidence_score") or 0.0),
            confluence_count=int(p.get("confluence_count") or 0),
            market_regime=p.get("market_regime", "") or "",
            atr_at_entry=float(p.get("atr_at_entry") or 0.0),
            smc_patterns=p.get("smc_patterns"),
            ict_setups=p.get("ict_setups"),
            user_id=p.get("user_id"),
            leverage=p.get("leverage"),
            entry_order_id=p.get("entry_order_id"),
            sl_order_id=p.get("sl_order_id"),
            tp_order_ids=p.get("tp_order_ids"),
        )
        self.rows_written += 1
        logger.info(f"[trade-ledger] row written: {p.get('trade_id')} "
                    f"({p.get('direction')} {p.get('symbol')})")

    async def _update_trade(self, p: Dict[str, Any]) -> None:
        await asyncio.to_thread(
            self.trade_history.update_trade_exit,
            trade_id=p.get("trade_id"),
            exit_price=float(p.get("exit_price") or 0.0),
            exit_time=_parse_dt(p.get("exit_time")),
            exit_reason=p.get("exit_reason", "") or "",
            notes=p.get("notes"),
        )
        self.rows_updated += 1
        logger.info(f"[trade-ledger] exit recorded: {p.get('trade_id')} "
                    f"({p.get('exit_reason')})")
