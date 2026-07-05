"""Offline unit tests for BingX client correctness fixes (no network).

Covers the money-critical execution P0/P1s:
- signature is computed over the EXACT string transmitted (sorted order + signature last)
- order responses are un-nested from BingX's data.order envelope
- positions parse BingX field names (avgPrice / unrealizedProfit / positionSide)
- get_order_status normalizes the symbol
"""
import hashlib
import hmac

import pytest

from src.execution.exchange_client import BingXClient, OrderSide, OrderStatus, OrderType


def _client():
    return BingXClient(api_key="k", api_secret="s3cr3t", testnet=True)


def test_signed_query_signature_matches_transmitted_string():
    c = _client()
    params = {"symbol": "BTC-USDT", "side": "BUY", "type": "MARKET", "quantity": 0.01,
              "timestamp": 111, "recvWindow": 5000}
    items = c._signed_query(dict(params))

    # signature must be the last element
    assert items[-1][0] == "signature"
    signature = items[-1][1]

    # the transmitted string (everything before the signature) must be what was signed
    transmitted = "&".join(f"{k}={v}" for k, v in items[:-1])
    expected = hmac.new(b"s3cr3t", transmitted.encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    # and it must equal the client's own _sign_request over the same params
    assert signature == c._sign_request(dict(params))

    # and the transmitted params must be in sorted key order (matches BingX either way)
    keys = [k for k, _ in items[:-1]]
    assert keys == sorted(keys)


def test_parse_order_unnests_data_order_envelope():
    c = _client()
    # BingX wraps the payload in {order: {...}} (after _request already stripped outer data)
    resp = {"order": {"orderId": 987654321, "symbol": "BTC-USDT", "side": "BUY",
                      "type": "MARKET", "origQty": "0.010", "executedQty": "0.010",
                      "avgPrice": "65000.5", "status": "FILLED",
                      "clientOrderID": "cai-abc-e", "time": 1700000000000,
                      "updateTime": 1700000000500}}
    order = c._parse_order(resp)
    assert order.order_id == "987654321"          # was 'None' before the fix
    assert order.client_order_id == "cai-abc-e"
    assert order.side == OrderSide.BUY
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == pytest.approx(0.010)
    assert order.average_price == pytest.approx(65000.5)


def test_parse_order_handles_flat_payload_too():
    c = _client()
    flat = {"orderId": 42, "symbol": "ETH-USDT", "side": "SELL", "type": "LIMIT",
            "price": "3000", "origQty": "1", "status": "NEW"}
    order = c._parse_order(flat)
    assert order.order_id == "42"
    assert order.order_type == OrderType.LIMIT
    assert order.side == OrderSide.SELL


@pytest.mark.asyncio
async def test_get_open_positions_parses_bingx_fields(monkeypatch):
    c = _client()

    async def fake_request(method, endpoint, params=None, signed=True):
        # BingX swap-v2 field names: avgPrice, unrealizedProfit, positionSide
        return [
            {"symbol": "BTC-USDT", "positionSide": "LONG", "positionAmt": "0.02",
             "avgPrice": "64000", "markPrice": "64500", "unrealizedProfit": "10.0",
             "leverage": "10"},
            {"symbol": "ETH-USDT", "positionSide": "SHORT", "positionAmt": "1.5",
             "avgPrice": "3200", "markPrice": "3150", "unrealizedProfit": "75.0",
             "leverage": "5"},
            {"symbol": "SOL-USDT", "positionSide": "LONG", "positionAmt": "0",  # flat, skip
             "avgPrice": "150", "markPrice": "150", "unrealizedProfit": "0", "leverage": "3"},
        ]

    monkeypatch.setattr(c, "_request", fake_request)
    positions = await c.get_open_positions()
    assert len(positions) == 2  # the zero-amount position is skipped
    btc = positions[0]
    assert btc.side == "LONG"
    assert btc.entry_price == pytest.approx(64000)      # avgPrice, not entryPrice
    assert btc.unrealized_pnl == pytest.approx(10.0)    # unrealizedProfit, not unRealizedProfit
    eth = positions[1]
    assert eth.side == "SHORT"
    assert eth.quantity == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_get_order_status_normalizes_symbol(monkeypatch):
    c = _client()
    seen = {}

    async def fake_request(method, endpoint, params=None, signed=True):
        seen["symbol"] = params.get("symbol")
        return {"order": {"orderId": 1, "symbol": params.get("symbol"), "side": "BUY",
                          "type": "MARKET", "status": "FILLED", "origQty": "1"}}

    monkeypatch.setattr(c, "_request", fake_request)
    await c.get_order_status("BTCUSDT", "1")
    assert seen["symbol"] == "BTC-USDT"  # normalized from BTCUSDT
