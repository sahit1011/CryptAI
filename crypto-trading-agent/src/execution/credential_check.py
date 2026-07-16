"""Verify exchange API credentials by making a REAL authenticated call.

Used by POST /api/exchange-keys before anything is stored: "connected" must mean the
exchange actually accepted the keys, not merely that we encrypted whatever was pasted.
The probe is a read-only account-balance request on the exchange's TESTNET.

verify_exchange_credentials returns:
    (True,  None)        — credentials work
    (False, "<reason>")  — exchange rejected them (bad key/secret/permissions)
and raises ExchangeUnreachable when the exchange itself can't be reached, so the API
can answer 502 (try again) instead of blaming the user's keys.
"""
import asyncio
from typing import Optional, Tuple

from loguru import logger

from src.execution.error_handler import NetworkException

VERIFY_TIMEOUT_SECONDS = 12.0


class ExchangeUnreachable(RuntimeError):
    """The exchange API couldn't be reached — not a credentials problem."""


async def verify_exchange_credentials(
    exchange: str, api_key: str, api_secret: str, *, client_factory=None
) -> Tuple[bool, Optional[str]]:
    """Probe the exchange with the submitted keys (read-only balance call, testnet)."""
    if client_factory is None:
        from src.execution.exchange_client import ExchangeClientFactory
        client_factory = ExchangeClientFactory.create_client

    client = None
    try:
        client = client_factory(exchange, api_key, api_secret, testnet=True)
        await asyncio.wait_for(client.get_account_balance(), timeout=VERIFY_TIMEOUT_SECONDS)
        return True, None
    except (NetworkException, asyncio.TimeoutError) as e:
        # Exchange down / DNS / timeout — NOT the user's fault; let the caller 502.
        raise ExchangeUnreachable(str(e)) from e
    except Exception as e:
        # Auth/permission/param rejection from the exchange -> the keys are no good.
        logger.info(f"[verify] {exchange} rejected submitted credentials: {str(e)[:120]}")
        return False, (
            "The exchange rejected these credentials. Check that the API key and secret "
            "are correct, belong to the TESTNET/demo environment, and have futures "
            "read permissions."
        )
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass
