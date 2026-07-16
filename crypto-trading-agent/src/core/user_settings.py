"""Per-user trading settings store (trading mode + active exchange).

Thin sync wrapper over the UserSettings table — mirrors CredentialVault's shape so the
API can read/write a tenant's preferences without touching ORM internals. Safe defaults
(mode=paper, exchange=bingx) mean a brand-new user is immediately useful (suggestions +
paper auto-trade) with zero configuration.
"""
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.data_models import UserSettings

VALID_MODES = ("off", "paper", "manual", "auto")
DEFAULTS = {"trading_mode": "paper", "active_exchange": "bingx"}


class UserSettingsStore:
    """CRUD for per-user trading settings."""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        UserSettings.__table__.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)

    def get(self, user_id: str) -> dict:
        """Return the user's settings, falling back to safe defaults."""
        session = self.Session()
        try:
            row = session.query(UserSettings).filter_by(user_id=user_id).first()
            if not row:
                return {"user_id": user_id, **DEFAULTS}
            return {
                "user_id": user_id,
                "trading_mode": row.trading_mode,
                "active_exchange": row.active_exchange,
            }
        finally:
            session.close()

    def set(
        self,
        user_id: str,
        trading_mode: Optional[str] = None,
        active_exchange: Optional[str] = None,
    ) -> dict:
        """Upsert the user's settings. Unknown modes are rejected."""
        if trading_mode is not None and trading_mode not in VALID_MODES:
            raise ValueError(f"invalid trading_mode '{trading_mode}' (want one of {VALID_MODES})")
        session = self.Session()
        try:
            row = session.query(UserSettings).filter_by(user_id=user_id).first()
            if not row:
                row = UserSettings(user_id=user_id, **DEFAULTS)
                session.add(row)
            if trading_mode is not None:
                row.trading_mode = trading_mode
            if active_exchange is not None:
                row.active_exchange = active_exchange
            session.commit()
            logger.info(f"Updated settings for {user_id}: mode={row.trading_mode} exch={row.active_exchange}")
            return {"user_id": user_id, "trading_mode": row.trading_mode, "active_exchange": row.active_exchange}
        finally:
            session.close()

    def mode_for(self, user_id: str) -> str:
        """Convenience: just the trading_mode (default 'paper')."""
        return self.get(user_id)["trading_mode"]
