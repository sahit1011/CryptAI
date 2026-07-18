"""Free-tier OpenRouter model rotation — skip dead/limited models, use first good one."""
import pytest

from src.utils.openrouter_rotation import complete_with_rotation, looks_like_json_object


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class _FakeClient:
    """Records calls and returns a scripted result/exception per model."""

    def __init__(self, script):
        # script: {model_id: str content | Exception | ""}
        self.script = script
        self.calls = []

        client = self

        class _Completions:
            def create(self, *, model, messages, **kw):
                client.calls.append(model)
                outcome = client.script[model]
                if isinstance(outcome, Exception):
                    raise outcome
                return _Resp(outcome)

        self.chat = type("C", (), {"completions": _Completions()})()


def test_returns_first_usable_and_stops():
    # Arrange: first model is good.
    client = _FakeClient({"a": '{"ok": true}', "b": '{"ok": false}'})

    # Act
    content, model = complete_with_rotation(client, ["a", "b"], [{"role": "user", "content": "x"}])

    # Assert: used "a", never tried "b".
    assert model == "a"
    assert content == '{"ok": true}'
    assert client.calls == ["a"]


def test_skips_429_error_then_empty_then_succeeds():
    # Arrange: a rate-limited model, an empty one, then a good one.
    client = _FakeClient({
        "limited": Exception("HTTP Error 429: Too Many Requests"),
        "empty": "",
        "good": '{"trade_setup": {"symbol": "BTCUSDT"}}',
    })

    # Act
    content, model = complete_with_rotation(
        client, ["limited", "empty", "good"], [{"role": "user", "content": "x"}]
    )

    # Assert: rotated past both failures to the third model.
    assert model == "good"
    assert client.calls == ["limited", "empty", "good"]


def test_validate_skips_prose_only_reply():
    # Arrange: first model returns prose (no JSON), second returns a JSON object.
    client = _FakeClient({
        "chatty": "I cannot help with that request.",
        "json": '{"trade_setup": {}}',
    })

    # Act
    content, model = complete_with_rotation(
        client, ["chatty", "json"], [{"role": "user", "content": "x"}],
        validate=looks_like_json_object,
    )

    # Assert
    assert model == "json"
    assert client.calls == ["chatty", "json"]


def test_raises_when_all_models_fail():
    # Arrange: every model is dead/limited.
    client = _FakeClient({
        "a": Exception("429"),
        "b": Exception("provider returned error"),
    })

    # Act / Assert
    with pytest.raises(RuntimeError, match="all free OpenRouter models failed"):
        complete_with_rotation(client, ["a", "b"], [{"role": "user", "content": "x"}])
    assert client.calls == ["a", "b"]


def test_empty_model_list_raises():
    client = _FakeClient({})
    with pytest.raises(RuntimeError, match="no OpenRouter free models configured"):
        complete_with_rotation(client, [], [{"role": "user", "content": "x"}])


def test_error_message_is_brace_safe():
    # Arrange: a 429 whose body contains raw JSON braces (real OpenRouter shape).
    braced = "Error code: 429 - {'error': {'message': 'Rate limit exceeded: free-models-per-day'}}"
    client = _FakeClient({"a": Exception(braced), "b": Exception(braced)})

    # Act
    try:
        complete_with_rotation(client, ["a", "b"], [{"role": "user", "content": "x"}])
        assert False, "should have raised"
    except RuntimeError as e:
        msg = str(e)

    # Assert: no raw braces leak into the message (they break loguru's formatter).
    assert "{" not in msg and "}" not in msg
    assert "429" in msg  # the useful signal is preserved


def test_on_attempt_status_is_brace_safe():
    # Arrange
    client = _FakeClient({"a": Exception("boom {'x': 1}"), "b": '{"ok": 1}'})
    seen = []

    # Act
    complete_with_rotation(
        client, ["a", "b"], [{"role": "user", "content": "x"}],
        on_attempt=lambda m, s: seen.append(s),
    )

    # Assert: the failure status reported for "a" carries no raw braces.
    assert "{" not in seen[0] and "}" not in seen[0]


def test_on_attempt_callback_receives_status_per_model():
    # Arrange
    client = _FakeClient({"a": Exception("429"), "b": '{"x": 1}'})
    seen = []

    # Act
    complete_with_rotation(
        client, ["a", "b"], [{"role": "user", "content": "x"}],
        on_attempt=lambda m, s: seen.append((m, s)),
    )

    # Assert: "a" reported a failure reason, "b" reported ok.
    assert seen[0][0] == "a" and "429" in seen[0][1]
    assert seen[-1] == ("b", "ok")


@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', True),
    ('prefix {"a": 1} suffix', True),
    ("no json here", False),
    ("", False),
    ("}{", False),  # closing before opening
])
def test_looks_like_json_object(text, expected):
    assert looks_like_json_object(text) is expected
