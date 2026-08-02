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
    """kwargs for create_engine / create_async_engine (env-tunable).

    Defaults are modest because the app opens SEVERAL engines (one per store) and the
    embedded-daemon deployment runs the API's set AND the daemon's set in one process, so
    the connection footprint is (engines x pool). Behind Supabase's transaction pooler
    those client connections multiplex onto far fewer server connections; the small pool
    keeps the client side bounded regardless.
    """
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "3")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "2")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_pre_ping": True,
    }


def async_pool_kwargs() -> dict:
    """pool_kwargs plus the one asyncpg setting that makes the async engine safe behind a
    pgbouncer TRANSACTION-mode pooler (Supabase :6543).

    asyncpg keeps a server-side prepared-statement cache per connection. pgbouncer in
    transaction mode hands the same server connection to different clients between
    statements, so a cached prepared statement vanishes underneath us — the classic
    "prepared statement __asyncpg_...__ does not exist". Setting statement_cache_size=0
    makes asyncpg use the unnamed statement, which is transaction-pooler-safe. It is
    harmless on a direct or session-mode connection, so it ships ahead of the URL switch.
    """
    kw = pool_kwargs()
    kw["connect_args"] = {"statement_cache_size": 0}
    return kw
