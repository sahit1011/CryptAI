"""Error tracking — Sentry, activated by the SENTRY_DSN env var.

No DSN (or sentry-sdk not installed) → clean no-op, zero overhead. With a DSN set,
unhandled exceptions in the API and the trading daemon are reported with environment
tagging. Call init_monitoring() once at process startup.
"""
import os

from loguru import logger


def init_monitoring(component: str) -> bool:
    """Initialize Sentry for this process. Returns True if active."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info(f"[monitoring] SENTRY_DSN not set — error tracking disabled ({component})")
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENVIRONMENT", "development"),
            release=os.getenv("RELEASE_VERSION") or None,
            # Trading errors matter individually — keep full error capture, light tracing.
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,  # never ship user PII/keys with events
        )
        sentry_sdk.set_tag("component", component)
        logger.info(f"[monitoring] Sentry active ({component})")
        return True
    except ImportError:
        logger.warning("[monitoring] SENTRY_DSN set but sentry-sdk not installed — run pip install sentry-sdk")
        return False
    except Exception as e:
        logger.error(f"[monitoring] Sentry init failed: {e}")
        return False
