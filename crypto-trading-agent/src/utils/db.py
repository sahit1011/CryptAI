"""Shared SQLAlchemy engine configuration.

Production pooling for every engine (sync + async). Without this, each manager used
create_engine defaults / a single unpooled connection, which exhausts DB connections
under multi-user load and errors on stale connections after idle periods.

  pool_pre_ping   — validate a connection before use (kills "server closed the
                    connection" errors after Supabase/idle timeouts)
  pool_recycle    — recycle connections before typical server-side idle cutoffs
  pool_size/overflow — bound concurrent connections (Supabase pooler + our own cap)
"""
import os


def pool_kwargs() -> dict:
    """kwargs for create_engine / create_async_engine (env-tunable)."""
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_pre_ping": True,
    }
