"""Central LLM provider policy: best premium model per use case, OpenRouter fallback.

One place that answers "which model powers X, given the keys that are configured?" The
policy is: for each use case, prefer the best PREMIUM provider whose direct key is set
(Anthropic / Google Gemini / OpenAI); if none is set, fall back to a free open-source
model on **OpenRouter**. So the whole system runs on an OpenRouter key alone today, and
automatically upgrades to premium models the moment their keys are added — no code change.

The agents keep their own resilient call chains; this module is the shared source of
truth for selection order + a human-readable startup summary (`describe`), so ops can
see exactly what's active. `provider_order` returns the ordered candidates an agent
should try for a use case, filtered to what's actually configured.
"""
from dataclasses import dataclass
from typing import List, Optional

# Preference order per use case — best premium first, OpenRouter open-source last.
# Each entry names a provider; the concrete model comes from LLMConfig at resolve time.
_POLICY = {
    # Deep market reasoning — Claude leads, then Gemini, then GPT, then OS fallback.
    "analysis": ["anthropic", "google", "openai", "openrouter", "groq"],
    # Structured setup generation — GPT/Claude strong; DeepSeek (OS) is a capable fallback.
    "strategy": ["anthropic", "openai", "google", "openrouter", "groq"],
    # Narrative insights — any capable chat model.
    "insights": ["anthropic", "openai", "google", "openrouter"],
    # Embeddings are OpenAI-specific; no OS OpenRouter equivalent wired, so this
    # degrades to disabled (semantic recall off) rather than falling back.
    "embeddings": ["openai"],
}

_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class ProviderChoice:
    provider: str          # anthropic | google | openai | openrouter | groq
    model: str
    via_openrouter: bool   # True when the call should go through the OpenRouter client


class LLMRouter:
    """Resolves provider/model per use case from the configured keys."""

    def __init__(self, llm_config):
        self.cfg = llm_config

    def _has_key(self, provider: str) -> bool:
        return {
            "anthropic": bool(self.cfg.anthropic_api_key),
            "openai": bool(self.cfg.openai_api_key),
            "google": bool(self.cfg.google_api_key),
            "openrouter": bool(self.cfg.openrouter_api_key),
            "groq": bool(self.cfg.groq_api_key),
        }.get(provider, False)

    def _model_for(self, provider: str) -> str:
        return {
            "anthropic": self.cfg.claude_model,
            "openai": self.cfg.gpt_model,
            "google": self.cfg.gemini_model,
            "openrouter": self.cfg.openrouter_fallback_model,
            "groq": self.cfg.groq_model,
        }[provider]

    def resolve(self, use_case: str) -> Optional[ProviderChoice]:
        """Best available provider for a use case, or None if nothing is configured."""
        if use_case == "embeddings":
            return ProviderChoice("openai", _EMBEDDING_MODEL, False) if self._has_key("openai") else None
        for provider in _POLICY.get(use_case, []):
            if self._has_key(provider):
                return ProviderChoice(provider, self._model_for(provider), provider == "openrouter")
        return None

    def provider_order(self, use_case: str) -> List[str]:
        """Ordered providers to try for a use case, filtered to configured keys."""
        return [p for p in _POLICY.get(use_case, []) if self._has_key(p)]

    def any_llm_configured(self) -> bool:
        return any(self._has_key(p) for p in ("anthropic", "openai", "google", "openrouter", "groq"))

    def describe(self) -> str:
        """One-line-per-use-case summary for startup logs."""
        lines = []
        for uc in ("analysis", "strategy", "insights", "embeddings"):
            c = self.resolve(uc)
            if c is None:
                lines.append(f"  {uc:10s}: DISABLED (no key)")
            else:
                tag = " (via OpenRouter, open-source fallback)" if c.via_openrouter else ""
                lines.append(f"  {uc:10s}: {c.provider}/{c.model}{tag}")
        return "LLM routing:\n" + "\n".join(lines)
