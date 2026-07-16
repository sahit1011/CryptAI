"""API rate limiter: sliding window + caller keying."""
from src.utils.api_rate_limit import SlidingWindowLimiter, client_key


def test_window_blocks_after_limit():
    lim = SlidingWindowLimiter(3, window_seconds=60)
    assert [lim.allow("k")[0] for _ in range(5)] == [True, True, True, False, False]


def test_keys_are_isolated():
    lim = SlidingWindowLimiter(1, window_seconds=60)
    assert lim.allow("a")[0] is True
    assert lim.allow("b")[0] is True     # different caller, own budget
    assert lim.allow("a")[0] is False


def test_retry_after_is_positive_when_blocked():
    lim = SlidingWindowLimiter(1, window_seconds=60)
    lim.allow("k")
    allowed, retry = lim.allow("k")
    assert allowed is False and retry >= 1


def test_client_key_prefers_auth_token_then_forwarded_ip():
    assert client_key({"authorization": "Bearer x"}, "1.2.3.4").startswith("tok:")
    assert client_key({}, "1.2.3.4") == "ip:1.2.3.4"
    # First hop of X-Forwarded-For (set by the reverse proxy) wins over the socket IP.
    assert client_key({"x-forwarded-for": "9.9.9.9, 10.0.0.1"}, "1.2.3.4") == "ip:9.9.9.9"


def test_token_key_is_hashed_not_raw():
    key = client_key({"authorization": "Bearer super-secret"}, "1.2.3.4")
    assert "super-secret" not in key
