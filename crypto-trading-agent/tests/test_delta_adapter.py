"""Delta Exchange India adapter — order-status parsing.

Regression coverage for the crash where `_to_order` referenced a non-existent
`OrderStatus.PENDING` on every non-filled order, making the reference live adapter unable
to place a bracket. No network: `__init__` is cheap and `_to_order`/`_map_state` are pure
over the response dict.
"""
import pytest

from src.execution.exchange_client import (
    DeltaExchangeClient,
    OrderSide,
    OrderStatus,
)


@pytest.fixture
def client():
    # __init__ only stores keys + base URL; the HTTP session is created lazily.
    return DeltaExchangeClient("test-key", "test-secret", testnet=True)


# --- _map_state: the full state table -----------------------------------------

@pytest.mark.parametrize("res,expected", [
    ({"state": "open"}, OrderStatus.NEW),
    ({"state": "pending"}, OrderStatus.NEW),
    ({"state": "closed", "size": 10, "filled_size": 10}, OrderStatus.FILLED),
    ({"state": "closed", "size": 10, "filled_size": 4}, OrderStatus.PARTIALLY_FILLED),
    ({"state": "closed", "size": 10, "filled_size": 0}, OrderStatus.CANCELED),
    ({"state": "cancelled"}, OrderStatus.CANCELED),
    ({"state": "canceled"}, OrderStatus.CANCELED),
    ({"state": "open", "size": 10, "filled_size": 3}, OrderStatus.PARTIALLY_FILLED),
    ({}, OrderStatus.NEW),
])
def test_map_state(res, expected):
    assert DeltaExchangeClient._map_state(res) == expected


# --- _to_order: the crash site ------------------------------------------------

def test_to_order_does_not_crash_on_a_resting_order(client):
    """The bug: any non-'closed' order raised AttributeError: OrderStatus.PENDING."""
    res = {"id": 123, "state": "open", "limit_price": "65000", "size": 2, "filled_size": 0}
    order = client._to_order(res, "BTCUSDT", OrderSide.BUY, "limit_order")
    assert order.status == OrderStatus.NEW
    assert order.order_id == "123"
    assert order.price == 65000.0
    assert order.quantity == 2.0


def test_to_order_maps_a_filled_market_order(client):
    res = {"id": 9, "state": "closed", "size": 1, "filled_size": 1,
           "average_fill_price": "2500.5"}
    order = client._to_order(res, "ETHUSDT", OrderSide.SELL, "market_order")
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 1.0
    assert order.average_price == 2500.5
