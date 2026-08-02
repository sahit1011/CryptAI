"""Proposal lifecycle — deterministic sizing, shelf life, and re-validation.

This is the layer every LLM-produced setup passes through before it can become an order.
The division of labour is deliberate and load-bearing:

    the LLM proposes; this module disposes, and it can only ever SHRINK risk.

Nothing here calls a model. Position size, stop distance, exposure caps, expiry, and the
approval-time re-check are arithmetic — testable, reproducible, and auditable in a way an
LLM's judgement is not. A user asking "why was I sized at 0.3 BTC?" gets an answer.

# Two safety rules that are easy to get wrong

**Re-sizing is shrink-only in NOTIONAL terms, not just risk terms.** The obvious
implementation re-derives size from `risk_amount / stop_distance` at the new price and
calls it safe because the dollar risk is unchanged. It is not: if price has drifted
*toward* the stop, the stop distance collapses and that formula demands a far LARGER
position for the same nominal risk. Same risk on paper, several times the exposure to a
gap straight through the stop. Size is therefore capped at the originally approved size,
always.

**A proposal has a shelf life.** Crypto moves; a setup priced at X is a different trade at
X±0.5%. Every proposal carries an expiry and an invalidation price, and approving one
re-runs the whole check against live price. Approving a stale proposal must refuse or
re-size — never blind-fill.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.data_models import Proposal

# --- statuses -----------------------------------------------------------------

PROPOSED = "proposed"
APPROVED = "approved"
REJECTED = "rejected"
EXPIRED = "expired"
INVALIDATED = "invalidated"
EXECUTED = "executed"
FAILED = "failed"

# --- rejection reasons --------------------------------------------------------

OK = "ok"
REASON_EXPIRED = "expired"
REASON_INVALIDATED = "invalidation_price_breached"
REASON_PRICE_MOVED = "price_moved_beyond_tolerance"
REASON_RR_DEGRADED = "risk_reward_below_minimum"
REASON_CONFIDENCE_LOW = "confidence_below_minimum"
REASON_BAD_GEOMETRY = "invalid_setup_geometry"
REASON_NOT_PENDING = "not_pending"

#: Default shelf life. Long enough for a human to read a thesis and decide, short enough
#: that the market has not become a different market.
DEFAULT_TTL_SECONDS = 180

#: How far price may drift from the proposed entry before approval is refused, as a
#: fraction. Beyond this the trade is materially different from the one described.
DEFAULT_PRICE_TOLERANCE = 0.005  # 0.5%


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class SizingResult:
    """Outcome of deterministic position sizing."""

    ok: bool
    reason: str
    position_size: float = 0.0
    risk_amount: float = 0.0
    risk_reward_ratio: float = 0.0
    notional: float = 0.0


@dataclass(frozen=True)
class Revalidation:
    """Outcome of the approval-time re-check."""

    ok: bool
    reason: str
    position_size: float = 0.0
    resized: bool = False
    original_size: float = 0.0


def size_position(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profits: List[float],
    prefs: Dict[str, Any],
    min_confidence_ok: bool = True,
) -> SizingResult:
    """Deterministic position sizing from the user's own risk budget.

    `size = (capital x risk%) / |entry - stop|`, then clamped by every cap the user's
    preferences and plan impose. Geometry is validated first: a stop on the wrong side of
    entry is not a small error to size around, it is a setup that would take the position
    straight into its own stop.
    """
    if not min_confidence_ok:
        return SizingResult(False, REASON_CONFIDENCE_LOW)

    if entry_price <= 0 or stop_loss <= 0:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    is_long = direction.upper() == "LONG"
    # A long's stop must sit BELOW entry and a short's ABOVE. The mirrored case is not a
    # rounding problem — it is a setup that stops out on entry.
    if is_long and stop_loss >= entry_price:
        return SizingResult(False, REASON_BAD_GEOMETRY)
    if not is_long and stop_loss <= entry_price:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    capital = float(prefs.get("trading_capital") or 0.0)
    risk_pct = float(prefs.get("max_risk_per_trade_pct") or 0.0)
    if capital <= 0 or risk_pct <= 0:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    risk_amount = capital * risk_pct / 100.0
    size = risk_amount / stop_distance

    # Leverage cap: notional may not exceed capital x max_leverage.
    max_leverage = float(prefs.get("max_leverage") or 1.0)
    max_notional = capital * max(1.0, max_leverage)
    if size * entry_price > max_notional:
        size = max_notional / entry_price

    # Risk:reward against the FIRST target — the one most likely to be reached, and so
    # the honest basis for the ratio. Using the furthest target flatters every setup.
    first_target = next((float(t) for t in (take_profits or []) if float(t) > 0), None)
    if first_target is None:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    reward = (first_target - entry_price) if is_long else (entry_price - first_target)
    if reward <= 0:
        # Target on the wrong side of entry: the "profit" leg is a loss.
        return SizingResult(False, REASON_BAD_GEOMETRY)

    rr = reward / stop_distance
    min_rr = float(prefs.get("min_risk_reward") or 1.0)
    if rr < min_rr:
        return SizingResult(False, REASON_RR_DEGRADED, risk_reward_ratio=rr)

    if size <= 0:
        return SizingResult(False, REASON_BAD_GEOMETRY)

    return SizingResult(
        ok=True,
        reason=OK,
        position_size=size,
        risk_amount=risk_amount,
        risk_reward_ratio=rr,
        notional=size * entry_price,
    )


def invalidation_price_for(direction: str, entry_price: float, stop_loss: float) -> float:
    """Price beyond which the setup no longer exists.

    Set at the stop: if price has already reached where the trade would have been
    stopped out, entering now is opening a position that the thesis says is already
    wrong.
    """
    _ = direction
    _ = entry_price
    return stop_loss


class ProposalService:
    """Creates, expires, and re-validates proposals.

    Synchronous, matching the other stores. Every read is scoped by `user_id` — the
    backend bypasses RLS, so application-layer scoping is the only guard.
    """

    def __init__(
        self,
        database_url: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
        now_fn=None,
    ):
        from src.utils.db import pool_kwargs

        self.engine = create_engine(database_url, **pool_kwargs())
        Proposal.__table__.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)
        self.ttl_seconds = ttl_seconds
        self.price_tolerance = price_tolerance
        self._now = now_fn or _utc_now

    # -- create --------------------------------------------------------------

    def create(
        self,
        *,
        user_id: str,
        session_id: str,
        setup: Dict[str, Any],
        prefs: Dict[str, Any],
        pulse: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Size a candidate setup and persist it as a proposal.

        Returns None when the setup fails deterministic validation — an LLM that produces
        a setup violating the user's own risk rules gets it dropped here, not surfaced.
        """
        direction = str(setup.get("direction", "")).upper()
        entry = float(setup.get("entry_price") or 0.0)
        stop = float(setup.get("stop_loss") or 0.0)
        targets = [float(t) for t in (setup.get("take_profit_levels") or [])]
        confidence = setup.get("confidence_score")

        min_conf = float(prefs.get("min_confidence") or 0.0)
        conf_ok = confidence is None or float(confidence) >= min_conf

        sizing = size_position(
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            take_profits=targets,
            prefs=prefs,
            min_confidence_ok=conf_ok,
        )
        if not sizing.ok:
            logger.info(
                f"setup rejected for {user_id} ({setup.get('symbol')}): {sizing.reason}"
            )
            return None

        now = self._now()
        row = Proposal(
            proposal_id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            symbol=str(setup.get("symbol", "")).upper(),
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            take_profit_levels=[{"price": t} for t in targets],
            position_size=sizing.position_size,
            risk_amount=sizing.risk_amount,
            risk_currency=str(prefs.get("capital_currency") or "USDT"),
            risk_reward_ratio=sizing.risk_reward_ratio,
            leverage=float(prefs.get("max_leverage") or 1.0),
            confidence_score=float(confidence) if confidence is not None else None,
            thesis=(setup.get("thesis") or "")[:4000] or None,
            strategy_type=setup.get("strategy_type"),
            pulse_ts=(pulse or {}).get("ts_dt"),
            market_regime=(pulse or {}).get("regime"),
            tradability_score=(pulse or {}).get("tradability"),
            status=PROPOSED,
            expires_at=now + timedelta(seconds=ttl_seconds or self.ttl_seconds),
            invalidation_price=invalidation_price_for(direction, entry, stop),
            created_at=now,
        )

        db = self.Session()
        try:
            db.add(row)
            db.commit()
            db.refresh(row)
            logger.info(
                f"proposal {row.proposal_id} for {user_id}: {direction} {row.symbol} "
                f"size={sizing.position_size:.6f} rr={sizing.risk_reward_ratio:.2f}"
            )
            return self._to_dict(row)
        finally:
            db.close()

    # -- read ----------------------------------------------------------------

    def get_pending(self, user_id: str) -> Optional[Dict[str, Any]]:
        """The caller's newest still-pending proposal, or None.

        Expiry is evaluated on read as well as by the sweeper, so a proposal cannot be
        approved in the window between lapsing and the sweeper noticing.
        """
        now = self._now()
        db = self.Session()
        try:
            row = (
                db.query(Proposal)
                .filter(Proposal.user_id == user_id, Proposal.status == PROPOSED)
                .order_by(Proposal.created_at.desc())
                .first()
            )
            if row is None:
                return None
            if row.expires_at is not None and row.expires_at <= now:
                row.status = EXPIRED
                row.decided_at = now
                db.commit()
                db.refresh(row)
            return self._to_dict(row)
        finally:
            db.close()

    def latest_for_session(
        self, user_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """The newest proposal belonging to one session, regardless of status.

        Exists for the executed-but-reply-lost recovery path: a dispatch timeout after
        the daemon booked leaves the proposal EXECUTED while the API saw nothing —
        callers must be able to distinguish "your trade is open" from "it expired"
        before resuming a session that could then book a second trade.
        """
        db = self.Session()
        try:
            row = (
                db.query(Proposal)
                .filter(
                    Proposal.user_id == user_id, Proposal.session_id == session_id
                )
                .order_by(Proposal.created_at.desc())
                .first()
            )
            return self._to_dict(row) if row else None
        finally:
            db.close()

    def get(self, proposal_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Scoped by user_id: a proposal id from another tenant must not resolve."""
        db = self.Session()
        try:
            row = (
                db.query(Proposal)
                .filter(Proposal.proposal_id == proposal_id, Proposal.user_id == user_id)
                .first()
            )
            return self._to_dict(row) if row else None
        finally:
            db.close()

    # -- lifecycle -----------------------------------------------------------

    def revalidate(
        self,
        *,
        proposal_id: str,
        user_id: str,
        current_price: float,
        prefs: Dict[str, Any],
    ) -> Revalidation:
        """Re-check a proposal against live price at approval time.

        The whole reason this exists: a proposal approved minutes after it was made
        describes a trade that may no longer be available. Every gate is re-run, and any
        re-size is capped at the originally approved size (see the module note on why
        risk-neutral re-sizing is not safe).
        """
        row_dict = self.get(proposal_id, user_id)
        if row_dict is None:
            return Revalidation(False, REASON_NOT_PENDING)
        if row_dict["status"] != PROPOSED:
            return Revalidation(False, REASON_NOT_PENDING)

        now = self._now()
        if row_dict["expires_at"] and datetime.fromisoformat(row_dict["expires_at"]) <= now:
            self._set_status(proposal_id, EXPIRED)
            return Revalidation(False, REASON_EXPIRED)

        direction = row_dict["direction"]
        is_long = direction == "LONG"
        entry = row_dict["entry_price"]
        stop = row_dict["stop_loss"]
        original_size = row_dict["position_size"] or 0.0

        if current_price <= 0:
            return Revalidation(False, REASON_BAD_GEOMETRY)

        # Invalidation: price has already reached where the thesis says it was wrong.
        invalidation = row_dict["invalidation_price"]
        if invalidation:
            breached = current_price <= invalidation if is_long else current_price >= invalidation
            if breached:
                self._set_status(proposal_id, INVALIDATED)
                return Revalidation(False, REASON_INVALIDATED)

        drift = abs(current_price - entry) / entry if entry > 0 else 1.0
        if drift > self.price_tolerance:
            return Revalidation(False, REASON_PRICE_MOVED)

        # Re-size at the live price, then clamp. Re-deriving size from the new stop
        # distance alone would DEMAND A LARGER position when price drifted toward the
        # stop — same nominal risk, several times the gap exposure.
        resized = size_position(
            direction=direction,
            entry_price=current_price,
            stop_loss=stop,
            take_profits=[t["price"] for t in (row_dict["take_profit_levels"] or [])],
            prefs=prefs,
        )
        if not resized.ok:
            return Revalidation(False, resized.reason, original_size=original_size)

        final_size = min(resized.position_size, original_size) if original_size > 0 else resized.position_size
        return Revalidation(
            ok=True,
            reason=OK,
            position_size=final_size,
            resized=final_size < original_size,
            original_size=original_size,
        )

    def mark(self, proposal_id: str, status: str, trade_id: Optional[str] = None) -> None:
        self._set_status(proposal_id, status, trade_id)

    def _set_status(self, proposal_id: str, status: str, trade_id: Optional[str] = None) -> None:
        db = self.Session()
        try:
            row = db.query(Proposal).filter_by(proposal_id=proposal_id).first()
            if row is None:
                return
            row.status = status
            row.decided_at = self._now()
            if trade_id:
                row.trade_id = trade_id
            db.commit()
        finally:
            db.close()

    def expire_stale(self) -> int:
        """Sweep lapsed proposals. Returns how many were expired."""
        now = self._now()
        db = self.Session()
        try:
            rows = (
                db.query(Proposal)
                .filter(Proposal.status == PROPOSED, Proposal.expires_at <= now)
                .all()
            )
            for row in rows:
                row.status = EXPIRED
                row.decided_at = now
            db.commit()
            return len(rows)
        finally:
            db.close()

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _to_dict(row: Proposal) -> Dict[str, Any]:
        return {
            "proposal_id": row.proposal_id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "symbol": row.symbol,
            "direction": row.direction,
            "entry_price": row.entry_price,
            "stop_loss": row.stop_loss,
            "take_profit_levels": row.take_profit_levels or [],
            "position_size": row.position_size,
            "risk_amount": row.risk_amount,
            "risk_currency": row.risk_currency,
            "risk_reward_ratio": row.risk_reward_ratio,
            "leverage": row.leverage,
            "confidence_score": row.confidence_score,
            "thesis": row.thesis,
            "strategy_type": row.strategy_type,
            "market_regime": row.market_regime,
            "tradability_score": row.tradability_score,
            "status": row.status,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "invalidation_price": row.invalidation_price,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "trade_id": row.trade_id,
        }
