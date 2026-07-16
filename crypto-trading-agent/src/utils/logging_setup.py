"""Process-wide logging setup + request-ID correlation.

- setup_logging(): call once per process. LOG_JSON=true switches loguru to structured
  JSON lines (one object per log — what log aggregators want); otherwise keeps the
  human-readable format. Level from LOG_LEVEL.
- request_id_var: contextvar carrying the current request's ID; the API middleware sets
  it per request and every log line emitted while handling that request includes it
  (patcher below), so errors can be correlated with the exact client call.
"""
import contextvars
import os
import sys

from loguru import logger

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def _patch_record(record):
    record["extra"].setdefault("request_id", request_id_var.get())


def setup_logging() -> None:
    logger.remove()
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    json_logs = os.getenv("LOG_JSON", "false").lower() == "true"
    logger.configure(patcher=_patch_record)
    if json_logs:
        logger.add(sys.stdout, level=level, serialize=True)
    else:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
                "<dim>{extra[request_id]}</dim> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | "
                "<level>{message}</level>"
            ),
        )
