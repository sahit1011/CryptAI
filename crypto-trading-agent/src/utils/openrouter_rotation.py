"""Free-tier OpenRouter model rotation.

OpenRouter's ':free' catalog rotates and rate-limits hard: any single free model
can be pulled ("Provider returned error"), return HTTP 429, or hand back an empty
/ prose body at any moment. Pinning ONE free model turns that into a single point
of failure — the exact reason the engine went quiet when its configured model was
removed from the catalog.

This helper takes a LIST of free models and tries them in order, returning the
first that yields a usable (non-empty, optionally validated) completion. A
dead / rate-limited model is skipped (its 429 comes back in well under a second),
not fatal. Premium providers (Claude / GPT / Gemini) are unaffected — this governs
ONLY the OpenRouter open-source fallback tier. Keep the list current via the
OPENROUTER_FREE_MODELS env var (see src/utils/config.py).

Synchronous by design: it uses the sync OpenRouter OpenAI client the agents
already construct. Callers that need it off the event loop wrap it in an executor
(as the strategy agent does).
"""
from typing import Any, Callable, List, Optional, Tuple


def looks_like_json_object(text: str) -> bool:
    """Cheap gate: does the text contain a JSON object (an opening brace with a
    later closing brace)? Lets rotation skip a chatty/refusal reply in favour of
    the next model without paying for a full parse. Not a validator — the agents'
    existing parsers still do the real parsing/validation.
    """
    if not text:
        return False
    open_brace = text.find("{")
    return open_brace != -1 and text.rfind("}") > open_brace


def complete_with_rotation(
    client: Any,
    models: List[str],
    messages: List[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 20000,
    validate: Optional[Callable[[str], bool]] = None,
    on_attempt: Optional[Callable[[str, str], None]] = None,
) -> Tuple[str, str]:
    """Try each free model in order; return ``(content, model)`` for the first
    that returns non-empty content passing ``validate``.

    A single model's error / empty / invalid response is caught and rotation moves
    on to the next candidate. Raises ``RuntimeError`` only when EVERY model fails,
    so the caller's existing error handling still fires for a total outage.

    Args:
        client: sync OpenAI-compatible client pointed at OpenRouter.
        models: ordered free-model ids to try (primary first).
        messages: chat messages (system/user) to send unchanged to each model.
        temperature/max_tokens: sampling params, same for every attempt.
        validate: optional predicate on the raw content; a False result skips the
            model (e.g. ``looks_like_json_object`` to skip prose-only replies).
        on_attempt: optional ``(model, status)`` callback for per-attempt logging;
            ``status`` is ``"ok"`` on success or a short failure reason otherwise.
    """
    if not models:
        raise RuntimeError("no OpenRouter free models configured")

    def _safe(text: str) -> str:
        # Provider error bodies embed raw JSON with { } braces. These strings flow
        # into loguru, which treats { } as format placeholders and raises
        # "Single '}' encountered in format string" — masking the real cause. Strip
        # braces so error messages stay log-safe.
        return text.replace("{", "(").replace("}", ")")

    from src.utils.llm_request_budget import record_attempt

    last = "no attempts made"
    for model in models:
        status = "ok"
        try:
            # Counted BEFORE the request departs: a failed/empty attempt still spent
            # one of the day's requests — that is precisely what the budget meters.
            record_attempt()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = ""
            if response and getattr(response, "choices", None):
                content = (response.choices[0].message.content or "").strip()

            if not content:
                status = last = f"{model}: empty response"
            elif validate is not None and not validate(content):
                status = last = f"{model}: response failed validation"
            else:
                if on_attempt:
                    on_attempt(model, "ok")
                return content, model
        except Exception as e:  # per-model failure (429, provider error, timeout)
            status = last = f"{model}: {type(e).__name__}: {_safe(str(e)[:160])}"

        if on_attempt:
            on_attempt(model, status)

    raise RuntimeError(f"all free OpenRouter models failed (last: {last})")
