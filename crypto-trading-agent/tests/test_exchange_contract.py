"""
Contract tests for the live BingX exchange client (no network).

These lock in the Phase-1b live-path fixes so they can't regress:
- BingX signs over the sorted query string and SENDS params in the query string for
  every method (the prior POST-as-JSON-body bug rejected every live order).
- Orders carry positionSide, reduceOnly (for closes), and a clientOrderID.
- recvWindow + a query-string signature are appended on signed requests.
- Exchange errors are raised as typed, retryable exceptions.
- The live client and the paper engine expose identical order-method signatures.
- Per-leg client order ids are deterministic (idempotent retries).

Run: pytest tests/test_exchange_contract.py
"""
import hmac
import hashlib
import inspect
import urllib.parse
import pytest

from src.execution.exchange_client import BingXClient, OrderSide
from src.execution.error_handler import (
    NetworkException, RateLimitException, AuthenticationException, ExchangeException,
)
from src.execution.order_manager import OrderManager
from src.execution.paper_trading_engine import PaperTradingEngine


# --- Fake aiohttp session -----------------------------------------------------

class _FakeResp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status = status
        self._text = text or str(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._text


class _FakeSession:
    """Records the last request so tests can assert how params were transported."""
    def __init__(self, payload=None, status=200):
        self.payload = payload if payload is not None else {"code": 0, "data": {"orderId": "1", "symbol": "BTC-USDT", "type": "MARKET", "status": "NEW"}}
        self.status = status
        self.closed = False
        self.calls = []

    def request(self, method, url, params=None, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "params": params, "headers": headers, "json": json})
        return _FakeResp(self.payload, status=self.status)


def _client(session=None):
    c = BingXClient(api_key="k", api_secret="s", testnet=True)
    c.session = session or _FakeSession()
    return c


# --- symbol formatting --------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("BTCUSDT", "BTC-USDT"),
    ("BTC/USDT", "BTC-USDT"),
    ("BTC-USDT", "BTC-USDT"),
    ("ETHUSDC", "ETH-USDC"),
])
def test_format_symbol(raw, expected):
    assert BingXClient._format_symbol(raw) == expected


# --- order params -------------------------------------------------------------

def test_order_params_close_is_reduce_only_with_fields():
    c = _client()
    p = c._order_params("BTCUSDT", OrderSide.SELL, "MARKET", 0.5,
                        position_side="BOTH", reduce_only=True, client_order_id="cai123tp0")
    assert p["symbol"] == "BTC-USDT"
    assert p["side"] == "SELL"
    assert p["positionSide"] == "BOTH"
    assert p["reduceOnly"] == "true"
    assert p["clientOrderID"] == "cai123tp0"


def test_entry_market_is_not_reduce_only():
    c = _client()
    p = c._order_params("BTCUSDT", OrderSide.BUY, "MARKET", 0.5,
                        position_side="BOTH", reduce_only=False, client_order_id="cai123e")
    assert "reduceOnly" not in p


# --- signing ------------------------------------------------------------------

def test_sign_request_matches_sorted_query_string():
    c = _client()
    params = {"symbol": "BTC-USDT", "side": "BUY", "quantity": 1, "timestamp": 123}
    sig = c._sign_request(params)
    expected_qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    expected = hmac.new(b"s", expected_qs.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


# --- transport (the critical regression test) ---------------------------------

@pytest.mark.asyncio
async def test_request_sends_params_in_query_string_not_body():
    sess = _FakeSession()
    c = _client(sess)
    await c.place_market_order("BTCUSDT", OrderSide.BUY, 0.5, client_order_id="cai123e")
    call = sess.calls[-1]
    # Params must be on the query string; nothing may be sent as a JSON body
    # (a JSON body would not match the query-string signature -> rejected).
    assert call["json"] is None
    assert call["params"] is not None
    assert call["params"]["clientOrderID"] == "cai123e"
    assert "signature" in call["params"]
    assert call["params"]["recvWindow"] == 5000


@pytest.mark.asyncio
async def test_request_signature_covers_all_params_except_signature():
    sess = _FakeSession()
    c = _client(sess)
    await c.place_market_order("BTCUSDT", OrderSide.BUY, 0.5)
    sent = dict(sess.calls[-1]["params"])
    sig = sent.pop("signature")
    qs = "&".join(f"{k}={v}" for k, v in sorted(sent.items()))
    expected = hmac.new(b"s", qs.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


# --- typed errors -------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_error_code_raises_typed_exception():
    # BingX signature error -> AuthenticationException (non-retryable)
    sess = _FakeSession(payload={"code": 100001, "msg": "signature verification failed"})
    c = _client(sess)
    with pytest.raises(AuthenticationException):
        await c.place_market_order("BTCUSDT", OrderSide.BUY, 0.5)


@pytest.mark.asyncio
async def test_http_5xx_is_retryable_network_error():
    sess = _FakeSession(payload={"msg": "bad gateway"}, status=502)
    c = _client(sess)
    with pytest.raises(NetworkException):
        await c.place_market_order("BTCUSDT", OrderSide.BUY, 0.5)


@pytest.mark.asyncio
async def test_http_429_is_rate_limit():
    sess = _FakeSession(payload={"msg": "too many requests"}, status=429)
    c = _client(sess)
    with pytest.raises(RateLimitException):
        await c.place_market_order("BTCUSDT", OrderSide.BUY, 0.5)


# --- close_position / cancel_all exist and are reduce-only --------------------

@pytest.mark.asyncio
async def test_close_position_is_reduce_only_market():
    sess = _FakeSession()
    c = _client(sess)
    await c.close_position("BTCUSDT", OrderSide.SELL, 0.5)
    p = sess.calls[-1]["params"]
    assert p["type"] == "MARKET"
    assert p["reduceOnly"] == "true"


# --- paper/live signature parity ---------------------------------------------

@pytest.mark.parametrize("method", [
    "place_market_order", "place_limit_order", "place_stop_loss_order",
    "close_position", "cancel_all_orders", "cancel_order",
])
def test_paper_and_live_signatures_match(method):
    live = inspect.signature(getattr(BingXClient, method))
    paper = inspect.signature(getattr(PaperTradingEngine, method))
    live_params = set(live.parameters) - {"self"}
    paper_params = set(paper.parameters) - {"self"}
    assert live_params == paper_params, f"{method}: live={live_params} paper={paper_params}"


# --- idempotency --------------------------------------------------------------

def test_client_order_id_is_deterministic():
    eid = "11112222-3333-4444-5555-666677778888"
    assert OrderManager._coid(eid, "e") == OrderManager._coid(eid, "e")
    assert OrderManager._coid(eid, "e") != OrderManager._coid(eid, "sl")
    assert OrderManager._coid(eid, "tp0").startswith("cai")
