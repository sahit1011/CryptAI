

"""
State Manager for managing system-wide state
Fixed SQLAlchemy 2.0 compatibility
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

from src.data.data_models import AgentState, Trade
from src.utils.config import get_config
from src.utils.enhanced_logging import PhaseLogger, StepLogger, MetricsLogger
from src.utils.pipeline_logger import PipelineLogger

# Create pipeline logger instance
plog = PipelineLogger()

class StateManager:
    """
    Manages system state across Redis (hot) and PostgreSQL (persistent)
    """

    def __init__(self):
        config = get_config()

        # Redis for hot state
        self.redis_url = config.database.redis_url
        self.redis: Optional[redis.Redis] = None

        # PostgreSQL for persistent state
        self.postgres_url = config.database.postgres_url.replace('postgresql://', 'postgresql+asyncpg://')
        self.engine = create_async_engine(self.postgres_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def connect(self):
        """Initialize connections"""
        plog.method_entry("connect", agent="state_manager", phase="setup")
        try:
            self.redis = redis.from_url(self.redis_url)
            plog.success(
                "State Manager connected to Redis and PostgreSQL",
                agent="state_manager",
                phase="setup"
            )
            plog.method_exit("connect", result="State Manager initialized")
        except Exception as e:
            plog.error(
                f"Failed to initialize State Manager: {e}",
                exception=e,
                agent="state_manager",
                phase="setup"
            )
            raise

    async def disconnect(self):
        """Close connections"""
        plog.method_entry("disconnect", agent="state_manager", phase="shutdown")
        try:
            if self.redis:
                await self.redis.close()
            await self.engine.dispose()
            plog.success(
                "State Manager disconnected from Redis and PostgreSQL",
                agent="state_manager",
                phase="shutdown"
            )
            plog.method_exit("disconnect", result="State Manager shutdown complete")
        except Exception as e:
            plog.error(
                f"Error disconnecting State Manager: {e}",
                exception=e,
                agent="state_manager",
                phase="shutdown"
            )
            raise

    # === Hot State (Redis) ===

    async def get(self, key: str) -> Optional[Any]:
        """Get value from hot state"""
        try:
            plog.debug(
                f"Getting state value for key: {key}",
                agent="state_manager",
                phase="state_read"
            )
            value = await self.redis.get(f"state:{key}")
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            plog.error(
                f"Error reading state for key {key}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_read"
            )
            raise

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in hot state"""
        try:
            plog.debug(
                f"Setting state value | key={key}, ttl={ttl}",
                agent="state_manager",
                phase="state_write"
            )
            value_json = json.dumps(value, default=str)
            if ttl:
                await self.redis.setex(f"state:{key}", ttl, value_json)
            else:
                await self.redis.set(f"state:{key}", value_json)
        except Exception as e:
            plog.error(
                f"Error writing state for key {key}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_write"
            )
            raise

    async def delete(self, key: str):
        """Delete key from hot state"""
        try:
            plog.debug(
                f"Deleting state key: {key}",
                agent="state_manager",
                phase="state_delete"
            )
            await self.redis.delete(f"state:{key}")
        except Exception as e:
            plog.error(
                f"Error deleting state key {key}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_delete"
            )
            raise

    async def get_hash(self, key: str, field: str) -> Optional[str]:
        """Get hash field"""
        try:
            plog.debug(
                f"Getting hash field | key={key}, field={field}",
                agent="state_manager",
                phase="state_read"
            )
            return await self.redis.hget(f"state:{key}", field)
        except Exception as e:
            plog.error(
                f"Error reading hash field {key}:{field}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_read"
            )
            raise

    async def set_hash(self, key: str, field: str, value: Any):
        """Set hash field"""
        try:
            plog.debug(
                f"Setting hash field | key={key}, field={field}",
                agent="state_manager",
                phase="state_write"
            )
            await self.redis.hset(f"state:{key}", field, json.dumps(value, default=str))
        except Exception as e:
            plog.error(
                f"Error writing hash field {key}:{field}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_write"
            )
            raise

    async def get_all_hash(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            plog.debug(
                f"Getting all hash fields for key: {key}",
                agent="state_manager",
                phase="state_read"
            )
            data = await self.redis.hgetall(f"state:{key}")
            return {k.decode(): json.loads(v.decode()) for k, v in data.items()}
        except Exception as e:
            plog.error(
                f"Error reading all hash fields for {key}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_read"
            )
            raise

    # === Portfolio State ===

    async def get_portfolio_state(self) -> Dict[str, Any]:
        """Get current portfolio state"""
        return await self.get_all_hash("portfolio")

    async def update_portfolio(self, updates: Dict[str, Any]):
        """Update portfolio state"""
        for key, value in updates.items():
            await self.set_hash("portfolio", key, value)

    # Lua script for atomically removing a single position by its 'id' field
    # from the "state:positions" list. Runs entirely server-side under Redis's
    # single-threaded execution model, so no concurrent LPUSH/remove can
    # interleave (no read-modify-write race, no loss of other positions on a
    # crash mid-op). We keep the list storage format because other components
    # (paper_trading_engine, ops scripts) read/write this same list directly;
    # switching to a hash here would break those callers we don't own.
    # KEYS[1] = list key, ARGV[1] = position_id to remove.
    # Returns the number of entries removed.
    _REMOVE_POSITION_LUA = """
    local items = redis.call('LRANGE', KEYS[1], 0, -1)
    local removed = 0
    redis.call('DEL', KEYS[1])
    -- Rebuild the list preserving original order, dropping only matching ids.
    -- Iterate in reverse so RPUSH restores the LRANGE (head-to-tail) order.
    for i = #items, 1, -1 do
        local raw = items[i]
        local ok, decoded = pcall(cjson.decode, raw)
        if ok and decoded ~= nil and tostring(decoded['id']) == ARGV[1] then
            removed = removed + 1
        else
            -- Keep entries that don't match (or that fail to decode, to avoid
            -- silently dropping data we can't parse).
            redis.call('RPUSH', KEYS[1], raw)
        end
    end
    return removed
    """

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions"""
        positions_json = await self.redis.lrange("state:positions", 0, -1)
        return [json.loads(p) for p in positions_json]

    async def add_position(self, position: Dict[str, Any]):
        """Add new position

        LPUSH is itself atomic, so a concurrent add and a concurrent
        remove_position (Lua, also atomic) can no longer clobber each other.
        """
        await self.redis.lpush("state:positions", json.dumps(position, default=str))

    async def remove_position(self, position_id: str) -> int:
        """Remove a single position by id, atomically.

        Previously this read the whole list, filtered in Python, DEL'd the key,
        and re-pushed the survivors. That read-modify-write was not atomic: a
        concurrent add_position (LPUSH) landing between the DEL and the re-push,
        or a crash mid-op, could lose open positions. We now do the
        filter-and-rebuild inside a single Lua script (EVAL), which Redis runs
        atomically server-side, so no other position mutation can interleave.

        Returns the number of positions removed (0 if no match) so callers can
        detect a no-op. Existing callers that ignore the return value are
        unaffected (signature is otherwise unchanged).
        """
        removed = await self.redis.eval(
            self._REMOVE_POSITION_LUA, 1, "state:positions", position_id
        )
        return int(removed)

    # === Reconciliation note ===
    # Redis holds the *hot* view of open positions; the exchange is the true
    # source of truth. The execution side owns the actual reconcile loop, which
    # should periodically (and on startup/recovery) fetch live positions from
    # the exchange and converge Redis to match:
    #   - exchange has a position Redis is missing  -> add_position(...)
    #   - Redis has a position the exchange closed   -> remove_position(id)
    #   - same position, differing fields            -> remove + re-add (or a
    #     future atomic update) to overwrite stale fields.
    # Because add_position (LPUSH) and remove_position (Lua EVAL) are each
    # atomic, a reconcile pass can mutate individual positions without racing
    # the live trading path. Do NOT treat Redis as authoritative on conflicts.

    # === Agent State ===

    async def update_agent_state(
        self,
        agent_name: str,
        state: str,
        last_heartbeat: datetime,
        state_data: Optional[Dict[str, Any]] = None
    ):
        """Update agent state"""
        plog.method_entry("update_agent_state", agent="state_manager")
        try:
            plog.debug(
                f"Updating agent state | agent={agent_name}, state={state}",
                agent="state_manager",
                phase="state_update"
            )
            
            # Convert timezone-aware datetime to naive for database storage
            last_heartbeat_naive = last_heartbeat.replace(tzinfo=None) if last_heartbeat.tzinfo else last_heartbeat

            async with self.async_session() as session:
                # Check if agent exists using select()
                result = await session.execute(
                    select(AgentState).where(AgentState.agent_name == agent_name)
                )
                agent_state = result.scalar_one_or_none()

                if agent_state:
                    # Update existing
                    agent_state.state = state
                    agent_state.last_heartbeat = last_heartbeat_naive
                    agent_state.state_data = state_data or {}
                    agent_state.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    plog.debug(f"Updated existing agent state for {agent_name}", agent="state_manager")
                else:
                    # Create new
                    new_state = AgentState(
                        agent_name=agent_name,
                        state=state,
                        last_heartbeat=last_heartbeat_naive,
                        state_data=state_data or {}
                    )
                    session.add(new_state)
                    plog.debug(f"Created new agent state for {agent_name}", agent="state_manager")

                await session.commit()
                plog.method_exit("update_agent_state", result=f"Agent state updated: {agent_name}")
        except Exception as e:
            plog.error(
                f"Error updating agent state for {agent_name}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_update"
            )
            raise

    async def get_agent_state(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get agent state"""
        plog.method_entry("get_agent_state", agent="state_manager")
        try:
            plog.debug(
                f"Retrieving agent state for: {agent_name}",
                agent="state_manager",
                phase="state_read"
            )
            async with self.async_session() as session:
                result = await session.execute(
                    select(AgentState).where(AgentState.agent_name == agent_name)
                )
                agent_state = result.scalar_one_or_none()
                if agent_state:
                    state_data = {
                        "agent_name": agent_state.agent_name,
                        "state": agent_state.state,
                        "last_heartbeat": agent_state.last_heartbeat,
                        "state_data": agent_state.state_data
                    }
                    plog.method_exit("get_agent_state", result=f"Retrieved state for {agent_name}")
                    return state_data
            plog.debug(f"No state found for agent: {agent_name}", agent="state_manager")
            plog.method_exit("get_agent_state", result=f"No state for {agent_name}")
            return None
        except Exception as e:
            plog.error(
                f"Error retrieving agent state for {agent_name}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_read"
            )
            raise

    async def log_error(self, agent_name: str, error: str):
        """Log agent error"""
        plog.method_entry("log_error", agent="state_manager")
        try:
            plog.error(
                f"Logging agent error | agent={agent_name}, error={error}",
                agent="state_manager",
                phase="state_update"
            )
            async with self.async_session() as session:
                result = await session.execute(
                    select(AgentState).where(AgentState.agent_name == agent_name)
                )
                agent_state = result.scalar_one_or_none()
                if agent_state:
                    agent_state.error_count += 1
                    agent_state.last_error = error
                    agent_state.last_error_time = datetime.now(timezone.utc).replace(tzinfo=None)
                    await session.commit()
                    plog.method_exit("log_error", result=f"Error logged for {agent_name}")
                else:
                    plog.warning(f"Agent state not found for {agent_name}", agent="state_manager")
        except Exception as e:
            plog.error(
                f"Error logging agent error for {agent_name}: {e}",
                exception=e,
                agent="state_manager",
                phase="state_update"
            )
            raise

    # === Market State ===

    async def update_price(self, symbol: str, price: float):
        """Update current price"""
        await self.set_hash("current_prices", symbol, price)

    async def get_price(self, symbol: str) -> Optional[float]:
        """Get current price"""
        price_str = await self.get_hash("current_prices", symbol)
        return float(json.loads(price_str)) if price_str else None

    async def get_all_prices(self) -> Dict[str, float]:
        """Get all current prices"""
        return await self.get_all_hash("current_prices")

    # === Trade Persistence ===

    async def save_trade(self, trade_data: Dict[str, Any]) -> str:
        """Save trade to database"""
        async with self.async_session() as session:
            trade = Trade(**trade_data)
            session.add(trade)
            await session.commit()
            await session.refresh(trade)
            return trade.trade_id

    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        """Update trade"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Trade).where(Trade.trade_id == trade_id)
            )
            trade = result.scalar_one_or_none()
            if trade:
                for key, value in updates.items():
                    setattr(trade, key, value)
                trade.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()

    async def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get trade by ID"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Trade).where(Trade.trade_id == trade_id)
            )
            trade = result.scalar_one_or_none()
            if trade:
                return {
                    "id": trade.id,
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "strategy_type": trade.strategy_type,
                    "entry_price": trade.entry_price,
                    "entry_time": trade.entry_time,
                    "position_size": trade.position_size,
                    "exit_price": trade.exit_price,
                    "exit_time": trade.exit_time,
                    "stop_loss": trade.stop_loss,
                    "take_profit": trade.take_profit,
                    "pnl": trade.pnl,
                    "pnl_percentage": trade.pnl_percentage,
                    "r_multiple": trade.r_multiple,
                    "duration_minutes": trade.duration_minutes,
                    "status": trade.status,
                    "exit_reason": trade.exit_reason,
                    "analysis_snapshot": trade.analysis_snapshot,
                    "confluences": trade.confluences,
                    "confidence_score": trade.confidence_score,
                    "entry_order_id": trade.entry_order_id,
                    "sl_order_id": trade.sl_order_id,
                    "tp_order_ids": trade.tp_order_ids,
                    "created_at": trade.created_at,
                    "updated_at": trade.updated_at
                }
        return None

    async def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trades"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Trade)
                .order_by(Trade.created_at.desc())
                .limit(limit)
            )
            trades = result.scalars().all()
            
            return [
                {
                    "id": trade.id,
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "strategy_type": trade.strategy_type,
                    "entry_price": trade.entry_price,
                    "entry_time": trade.entry_time,
                    "exit_price": trade.exit_price,
                    "exit_time": trade.exit_time,
                    "position_size": trade.position_size,
                    "pnl": trade.pnl,
                    "pnl_percentage": trade.pnl_percentage,
                    "status": trade.status,
                    "exit_reason": trade.exit_reason,
                    "is_winner": trade.is_winner,
                    "confidence_score": trade.confidence_score,
                    "leverage": trade.leverage if hasattr(trade, 'leverage') else 10,
                    "created_at": trade.created_at
                }
                for trade in trades
            ]

    # === State Recovery ===

    async def recover_agent_states(self) -> Dict[str, Dict[str, Any]]:
        """Recover agent states from database"""
        async with self.async_session() as session:
            result = await session.execute(select(AgentState))
            agent_states = result.scalars().all()

            recovery_data = {}
            for state in agent_states:
                recovery_data[state.agent_name] = {
                    "state": state.state,
                    "last_heartbeat": state.last_heartbeat,
                    "state_data": state.state_data,
                    "error_count": state.error_count,
                    "last_error": state.last_error,
                    "last_error_time": state.last_error_time
                }
            return recovery_data

    async def recover_portfolio_state(self) -> Dict[str, Any]:
        """Recover portfolio state from Redis"""
        return await self.get_portfolio_state()

    async def recover_positions(self) -> List[Dict[str, Any]]:
        """Recover positions from Redis"""
        return await self.get_positions()

    async def recover_market_prices(self) -> Dict[str, float]:
        """Recover market prices from Redis"""
        return await self.get_all_prices()

    async def perform_state_recovery(self) -> Dict[str, Any]:
        """Perform complete state recovery"""
        plog.method_entry("perform_state_recovery", agent="state_manager", phase="state_recovery")
        try:
            plog.info(
                "Starting complete state recovery",
                agent="state_manager",
                phase="state_recovery"
            )
            
            recovery_data = {
                "agent_states": await self.recover_agent_states(),
                "portfolio": await self.recover_portfolio_state(),
                "positions": await self.recover_positions(),
                "prices": await self.recover_market_prices(),
                "recovery_timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            }
            
            plog.success(
                "State recovery completed successfully",
                agent="state_manager",
                phase="state_recovery"
            )
            plog.method_exit("perform_state_recovery", result="Recovery successful")
            return recovery_data
        except Exception as e:
            plog.error(
                f"State recovery failed: {e}",
                exception=e,
                agent="state_manager",
                phase="state_recovery"
            )
            raise