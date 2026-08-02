"""Metered analysis sessions — the unit the free-tier 30 min/day is spent from.

Replaces the global owner-controlled engine switch (`src/core/engine_switch.py`) with
per-user metering. That switch is one boolean for the whole deployment; this is a clock
per tenant, which is what makes the product a product rather than a demo.

Four properties this module exists to guarantee. Each has a test.

1. **The clock is durable and server-authoritative.** Elapsed time is always DERIVED as
   ``accrued + (now - clock_started_at)``. A countdown is never stored, and the client is
   never trusted. A process restart mid-session loses at most the in-flight segment
   rather than the whole session, and can never silently grant unlimited time.

2. **The clock pauses while a proposal awaits a decision.** A user is not charged for
   thinking. It resumes only if they reject and ask for more scanning.

3. **Monitoring is never metered.** A session ends when its quota runs out; any position
   it opened keeps being monitored. That is a money-safety property, not a billing
   loophole — you cannot abandon someone's open trade because their free minutes expired.

4. **Two independent meters, both fail-closed.** Wall-clock minutes are the product and
   the thing a user understands. The LLM cost cap is the safety net underneath, because
   30 minutes of aggressive multi-agent analysis is bounded in time but not in spend.

The clock is injected (`now_fn`) so tests can rewind rather than sleep — see the
`time.sleep(61)` incident in CLAUDE.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.data_models import Session as SessionRow
from src.data.data_models import SessionEvent

# --- state machine -----------------------------------------------------------

SCANNING = "scanning"
SETUP_PROPOSED = "setup_proposed"
EXECUTING = "executing"
ENDED = "ended"

#: Only these transitions are legal. Anything else raises rather than silently
#: corrupting a session's accounting — an illegal transition usually means two callers
#: are racing, and a permissive state machine turns that into a billing bug.
LEGAL: Dict[str, set] = {
    SCANNING: {SETUP_PROPOSED, ENDED},
    SETUP_PROPOSED: {SCANNING, EXECUTING, ENDED},
    EXECUTING: {ENDED},
    ENDED: set(),
}

#: Only this state accrues metered time.
METERED_STATES = {SCANNING}

# --- end reasons -------------------------------------------------------------

QUOTA_EXHAUSTED = "quota_exhausted"
COST_CAP = "cost_cap"
USER_ENDED = "user_ended"
TRADE_OPENED = "trade_opened"
ERROR = "error"

DEFAULT_DAILY_QUOTA_SECONDS = 1800  # free tier: 30 minutes
DEFAULT_COST_CAP_MICROS = 500_000  # $0.50 per session


class SessionError(RuntimeError):
    """Base for session problems the caller is expected to handle."""


class QuotaExhausted(SessionError):
    """No metered time left today."""


class CostCapReached(SessionError):
    """The session's LLM spend cap is used up."""


class IllegalTransition(SessionError):
    """The requested state change is not allowed from the current state."""


class NoActiveSession(SessionError):
    """No live session for this user."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _trading_day(now: datetime) -> datetime:
    """UTC midnight for `now`.

    UTC rather than the user's local timezone so the reset boundary is unambiguous and
    identical for every tenant; the UI renders it in local time. A per-user boundary
    would let someone reset their quota by changing a device setting.
    """
    return datetime(now.year, now.month, now.day)


class SessionManager:
    """CRUD plus the state machine for metered sessions.

    Synchronous, matching `UserSettingsStore` and `CredentialVault`. The API layer calls
    it from a thread; introducing a second async DB path here would fork the connection
    handling for no benefit at this size.
    """

    def __init__(
        self,
        database_url: str,
        daily_quota_seconds: int = DEFAULT_DAILY_QUOTA_SECONDS,
        cost_cap_micros: int = DEFAULT_COST_CAP_MICROS,
        now_fn: Optional[Callable[[], datetime]] = None,
    ):
        from src.utils.db import pool_kwargs

        self.engine = create_engine(database_url, **pool_kwargs())
        SessionRow.__table__.create(self.engine, checkfirst=True)
        SessionEvent.__table__.create(self.engine, checkfirst=True)
        self._ensure_schema()
        self.Session = sessionmaker(bind=self.engine)
        self.daily_quota_seconds = daily_quota_seconds
        self.cost_cap_micros = cost_cap_micros
        self._now = now_fn or _utc_now

    def _ensure_schema(self) -> None:
        """Add columns the model has but an existing `sessions` table lacks.

        `checkfirst=True` creates the table only when absent — it never adds a column to
        one that already exists. A production DB where SessionManager booted before this
        column was introduced (or whose migrations haven't run) would be missing
        `channel`, and every insert referencing it would fail. This idempotent
        ADD-COLUMN-if-missing self-heal makes the code work regardless of alembic state;
        the alembic migration (b2d3e4f5a6c7) remains the managed source of truth.
        """
        from sqlalchemy import inspect, text

        inspector = inspect(self.engine)
        if "sessions" not in inspector.get_table_names():
            return  # checkfirst will create it fresh with every column
        existing = {c["name"] for c in inspector.get_columns("sessions")}
        additive = {"channel": "VARCHAR(16)"}
        for name, ddl_type in additive.items():
            if name in existing:
                continue
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE sessions ADD COLUMN {name} {ddl_type}"))
            except Exception:
                # TOCTOU: on Render the backend and daemon deploy from the same push and
                # construct SessionManager against the same Postgres at once — both can
                # pass the inspect above and race this ALTER. The loser gets a
                # duplicate-column error; that is success, not failure (the column now
                # exists). Re-inspect and swallow only if it really landed; re-raise a
                # genuine failure so a broken DB is not silently ignored.
                landed = {c["name"] for c in inspect(self.engine).get_columns("sessions")}
                if name not in landed:
                    raise
                logger.info(
                    f"sessions.{name} was added by a concurrent boot; continuing"
                )

    # -- clock ---------------------------------------------------------------

    def _elapsed(self, row: SessionRow, now: datetime) -> int:
        """Metered seconds consumed by this session so far.

        Derived, never stored. `clock_started_at` is non-null only while metering, so a
        paused or ended session contributes exactly its accrued total.
        """
        elapsed = row.metered_seconds_accrued
        if row.clock_started_at is not None:
            # max(0) guards a clock that went backwards (NTP correction, or a restore
            # onto a machine with skew). Negative elapsed would refund time.
            elapsed += max(0, int((now - row.clock_started_at).total_seconds()))
        return elapsed

    def _pause_clock(self, row: SessionRow, now: datetime) -> None:
        if row.clock_started_at is not None:
            row.metered_seconds_accrued += max(
                0, int((now - row.clock_started_at).total_seconds())
            )
            row.clock_started_at = None

    def _resume_clock(self, row: SessionRow, now: datetime) -> None:
        if row.clock_started_at is None:
            row.clock_started_at = now

    # -- quota ---------------------------------------------------------------

    def used_today(self, user_id: str) -> int:
        """Metered seconds consumed across ALL of today's sessions.

        The quota is daily and per user, not per session — otherwise starting a new
        session would reset it, which is the obvious way to get unlimited time.
        """
        now = self._now()
        day = _trading_day(now)
        db = self.Session()
        try:
            rows = (
                db.query(SessionRow)
                .filter(SessionRow.user_id == user_id, SessionRow.trading_day == day)
                .all()
            )
            return sum(self._elapsed(r, now) for r in rows)
        finally:
            db.close()

    def remaining_today(self, user_id: str) -> int:
        return max(0, self.daily_quota_seconds - self.used_today(user_id))

    # -- lifecycle -----------------------------------------------------------

    def start(
        self,
        user_id: str,
        quota_seconds: Optional[int] = None,
        channel: Optional[str] = None,
    ) -> dict:
        """Begin a metered session.

        Refuses if the user already has a live session (one at a time — two concurrent
        sessions would double-spend the same daily quota) or if no time is left.

        `channel` (scalp | intraday | swing | position) sets the trading style for this
        session, overriding the user's persistent goal_horizon persona. None keeps the
        persona default. An unknown channel is rejected rather than silently ignored.
        """
        from src.core.preferences import GOAL_HORIZONS

        now = self._now()
        if channel is not None and channel not in GOAL_HORIZONS:
            raise SessionError(
                f"unknown channel '{channel}'; expected one of {', '.join(GOAL_HORIZONS)}"
            )
        remaining = self.remaining_today(user_id)
        if remaining <= 0:
            raise QuotaExhausted(
                f"no metered time left today for {user_id}; resets at UTC midnight"
            )

        if self.get_active(user_id) is not None:
            raise SessionError(f"{user_id} already has an active session")

        row = SessionRow(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            status=SCANNING,
            channel=channel,
            # Grant at most what is left today. An explicit request may ask for less
            # (a short session) but never more — clamping here is what makes the daily
            # quota real; without it a caller could pass quota_seconds above the cap and
            # run a single session far past the daily allowance.
            quota_seconds_granted=min(quota_seconds, remaining) if quota_seconds else remaining,
            metered_seconds_accrued=0,
            clock_started_at=now,  # scanning meters immediately
            llm_cost_cap_micros=self.cost_cap_micros,
            trading_day=_trading_day(now),
            started_at=now,
        )

        db = self.Session()
        try:
            db.add(row)
            db.commit()
            db.refresh(row)
            self._log(db, row, "state_change", None, SCANNING, "session started")
            logger.info(
                f"session {row.session_id} started for {user_id} "
                f"({remaining}s remaining today)"
            )
            return self._to_dict(row, now)
        finally:
            db.close()

    def get_active(self, user_id: str) -> Optional[dict]:
        now = self._now()
        db = self.Session()
        try:
            row = (
                db.query(SessionRow)
                .filter(SessionRow.user_id == user_id, SessionRow.status != ENDED)
                .order_by(SessionRow.started_at.desc())
                .first()
            )
            return self._to_dict(row, now) if row else None
        finally:
            db.close()

    def active_sessions(self, limit: int = 200) -> List[dict]:
        """Every live session across all tenants, oldest first.

        The worker pool's discovery query. Bounded by `limit` so a runaway that somehow
        creates thousands of sessions degrades into "we serve the oldest N" rather than
        loading them all into memory — and the count is logged so the anomaly is visible
        rather than silently truncated.
        """
        now = self._now()
        db = self.Session()
        try:
            rows = (
                db.query(SessionRow)
                .filter(SessionRow.status != ENDED)
                .order_by(SessionRow.started_at.asc())
                .limit(limit + 1)
                .all()
            )
            if len(rows) > limit:
                logger.warning(
                    f"{len(rows)}+ active sessions exceeds the {limit} pool cap; "
                    f"serving the oldest {limit}"
                )
                rows = rows[:limit]
            return [self._to_dict(r, now) for r in rows]
        finally:
            db.close()

    def get(self, session_id: str) -> Optional[dict]:
        now = self._now()
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            return self._to_dict(row, now) if row else None
        finally:
            db.close()

    def _transition(
        self,
        session_id: str,
        to_status: str,
        *,
        end_reason: Optional[str] = None,
        message: str = "",
    ) -> dict:
        now = self._now()
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            if row is None:
                raise NoActiveSession(f"no session {session_id}")

            from_status = row.status
            if to_status not in LEGAL.get(from_status, set()):
                raise IllegalTransition(
                    f"session {session_id}: {from_status} -> {to_status} is not allowed"
                )

            # Settle the clock BEFORE changing state, so the seconds land against the
            # state that actually consumed them.
            self._pause_clock(row, now)
            row.status = to_status
            if to_status in METERED_STATES:
                self._resume_clock(row, now)

            if to_status == ENDED:
                row.ended_at = now
                row.end_reason = end_reason or USER_ENDED

            db.commit()
            db.refresh(row)
            self._log(db, row, "state_change", from_status, to_status, message)
            logger.info(
                f"session {session_id}: {from_status} -> {to_status}"
                + (f" ({row.end_reason})" if to_status == ENDED else "")
            )
            return self._to_dict(row, now)
        finally:
            db.close()

    def propose(self, session_id: str, message: str = "setup proposed") -> dict:
        """A setup is on the table. PAUSES the clock — deliberation is not charged."""
        return self._transition(session_id, SETUP_PROPOSED, message=message)

    def reject(self, session_id: str, message: str = "proposal rejected") -> dict:
        """User declined; resume scanning and resume metering."""
        return self._transition(session_id, SCANNING, message=message)

    def approve(self, session_id: str, message: str = "proposal approved") -> dict:
        """User accepted (or auto mode fired). Execution is not metered."""
        return self._transition(session_id, EXECUTING, message=message)

    def end(self, session_id: str, reason: str = USER_ENDED, message: str = "") -> dict:
        return self._transition(session_id, ENDED, end_reason=reason, message=message)

    # -- enforcement ---------------------------------------------------------

    def tick(self, session_id: str) -> dict:
        """Enforce both meters. Call before doing any metered work.

        Ends the session when either meter is exhausted. Returns the session either way,
        so a caller can check `status` rather than catching an exception on the hot path.
        """
        now = self._now()
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            if row is None:
                raise NoActiveSession(f"no session {session_id}")
            if row.status == ENDED:
                return self._to_dict(row, now)

            elapsed = self._elapsed(row, now)
            over_time = elapsed >= row.quota_seconds_granted
            over_cost = row.llm_cost_micros >= row.llm_cost_cap_micros
        finally:
            db.close()

        if over_cost:
            # Checked first: cost is the hard safety net, and reporting the binding
            # constraint accurately matters for support.
            return self.end(session_id, COST_CAP, "LLM cost cap reached")
        if over_time:
            return self.end(session_id, QUOTA_EXHAUSTED, "metered time exhausted")
        return self.get(session_id) or {}

    def record_llm_usage(self, session_id: str, tokens: int, cost_micros: int) -> dict:
        """Accumulate LLM spend. Fail-closed: ends the session once the cap is hit.

        Recorded AFTER the call, so the cap can be exceeded by at most one request. A
        pre-flight reservation would be tighter but needs a cost estimate the providers
        do not give reliably; one request of overshoot is the honest trade.
        """
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            if row is None:
                raise NoActiveSession(f"no session {session_id}")
            row.llm_tokens_used += max(0, tokens)
            row.llm_cost_micros += max(0, cost_micros)
            db.commit()
        finally:
            db.close()
        return self.tick(session_id)

    def record_cycle(self, session_id: str) -> None:
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            if row is not None:
                row.cycles_completed += 1
                db.commit()
        finally:
            db.close()

    # -- events --------------------------------------------------------------

    def _log(
        self,
        db,
        row: SessionRow,
        event_type: str,
        from_status: Optional[str],
        to_status: Optional[str],
        message: str,
        agent: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Append-only audit trail. Doubles as the user-facing agent feed."""
        try:
            db.add(
                SessionEvent(
                    session_id=row.session_id,
                    user_id=row.user_id,
                    event_type=event_type,
                    from_status=from_status,
                    to_status=to_status,
                    agent=agent,
                    message=message[:1000] if message else None,
                    payload=payload,
                    created_at=self._now(),
                )
            )
            db.commit()
        except Exception as e:  # an audit failure must not break the session
            logger.warning(f"failed to write session event: {e}")
            db.rollback()

    def log_agent_step(
        self, session_id: str, agent: str, message: str, payload: Optional[dict] = None
    ) -> None:
        db = self.Session()
        try:
            row = db.query(SessionRow).filter_by(session_id=session_id).first()
            if row is not None:
                self._log(db, row, "agent_step", None, None, message, agent, payload)
        finally:
            db.close()

    def events(self, session_id: str, limit: int = 200) -> List[dict]:
        db = self.Session()
        try:
            rows = (
                db.query(SessionEvent)
                .filter_by(session_id=session_id)
                .order_by(SessionEvent.created_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "event_type": e.event_type,
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "agent": e.agent,
                    "message": e.message,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in rows
            ]
        finally:
            db.close()

    # -- serialisation -------------------------------------------------------

    def _to_dict(self, row: SessionRow, now: datetime) -> dict:
        elapsed = self._elapsed(row, now)
        return {
            "session_id": row.session_id,
            "user_id": row.user_id,
            "status": row.status,
            "channel": row.channel,
            "quota_seconds_granted": row.quota_seconds_granted,
            "elapsed_seconds": elapsed,
            "remaining_seconds": max(0, row.quota_seconds_granted - elapsed),
            "clock_running": row.clock_started_at is not None,
            "llm_tokens_used": row.llm_tokens_used,
            "llm_cost_micros": row.llm_cost_micros,
            "llm_cost_cap_micros": row.llm_cost_cap_micros,
            "cycles_completed": row.cycles_completed,
            "trading_day": row.trading_day.date().isoformat() if row.trading_day else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "end_reason": row.end_reason,
        }
