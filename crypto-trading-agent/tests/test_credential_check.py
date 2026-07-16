"""Exchange-credential verification: real-probe semantics, no network needed."""
import asyncio

import pytest

from src.execution.credential_check import (
    ExchangeUnreachable,
    verify_exchange_credentials,
)
from src.execution.error_handler import NetworkException


class FakeClient:
    def __init__(self, behavior):
        self.behavior = behavior
        self.closed = False

    async def get_account_balance(self):
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return self.behavior

    async def close(self):
        self.closed = True


def _factory(behavior, made=None):
    def factory(exchange, key, secret, testnet=True):
        client = FakeClient(behavior)
        if made is not None:
            made.append(client)
        return client
    return factory


@pytest.mark.asyncio
async def test_valid_keys_pass_and_client_is_closed():
    made = []
    ok, reason = await verify_exchange_credentials(
        "bingx", "k", "s", client_factory=_factory({"balance": 100.0}, made))
    assert ok is True and reason is None
    assert made[0].closed is True


@pytest.mark.asyncio
async def test_rejected_keys_fail_with_user_readable_reason():
    made = []
    ok, reason = await verify_exchange_credentials(
        "bingx", "garbage", "garbage", client_factory=_factory(Exception("100413 invalid api key"), made))
    assert ok is False
    assert "rejected" in reason.lower()
    assert made[0].closed is True  # closed even on failure


@pytest.mark.asyncio
async def test_unreachable_exchange_raises_not_blames_user():
    with pytest.raises(ExchangeUnreachable):
        await verify_exchange_credentials(
            "bingx", "k", "s", client_factory=_factory(NetworkException("DNS boom")))


@pytest.mark.asyncio
async def test_timeout_counts_as_unreachable():
    class SlowClient(FakeClient):
        async def get_account_balance(self):
            raise asyncio.TimeoutError()
    with pytest.raises(ExchangeUnreachable):
        await verify_exchange_credentials(
            "bingx", "k", "s", client_factory=lambda *a, **kw: SlowClient(None))
