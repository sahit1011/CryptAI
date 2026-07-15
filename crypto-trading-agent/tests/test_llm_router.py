"""LLM router: best premium per use case, OpenRouter open-source fallback."""
from types import SimpleNamespace

from src.utils.llm_router import LLMRouter


def _cfg(**keys):
    base = dict(
        anthropic_api_key=None, openai_api_key=None, openrouter_api_key=None,
        groq_api_key=None, google_api_key=None,
        claude_model="claude-x", gpt_model="gpt-x", gemini_model="gemini-x",
        groq_model="groq-x", openrouter_fallback_model="deepseek:free",
    )
    base.update(keys)
    return SimpleNamespace(**base)


def test_no_keys_disables_everything():
    r = LLMRouter(_cfg())
    assert not r.any_llm_configured()
    for uc in ("analysis", "strategy", "insights", "embeddings"):
        assert r.resolve(uc) is None


def test_openrouter_only_runs_everything_on_free_model():
    r = LLMRouter(_cfg(openrouter_api_key="sk-or"))
    assert r.any_llm_configured()
    for uc in ("analysis", "strategy", "insights"):
        c = r.resolve(uc)
        assert c.provider == "openrouter" and c.via_openrouter and c.model == "deepseek:free"
    # embeddings have no OpenRouter equivalent wired -> disabled
    assert r.resolve("embeddings") is None


def test_premium_key_takes_precedence_over_openrouter():
    r = LLMRouter(_cfg(anthropic_api_key="sk-ant", openrouter_api_key="sk-or"))
    a = r.resolve("analysis")
    assert a.provider == "anthropic" and a.model == "claude-x" and not a.via_openrouter
    # OpenRouter remains the fallback in the ordering
    assert r.provider_order("analysis") == ["anthropic", "openrouter"]


def test_gemini_supported_and_ordered():
    r = LLMRouter(_cfg(google_api_key="sk-goog"))
    a = r.resolve("analysis")
    assert a.provider == "google" and a.model == "gemini-x"


def test_embeddings_need_openai():
    assert LLMRouter(_cfg(openai_api_key="sk-oai")).resolve("embeddings").provider == "openai"
    assert LLMRouter(_cfg(anthropic_api_key="sk-ant")).resolve("embeddings") is None


def test_describe_is_readable():
    out = LLMRouter(_cfg(openrouter_api_key="sk-or")).describe()
    assert "analysis" in out and "open-source fallback" in out
