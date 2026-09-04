from __future__ import annotations

from app.ai.llm.base import LLMProvider, LLMResult, registry
from app.ai.llm.offline_provider import OfflineProvider
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("ai.llm")


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the configured provider; falls back to offline when the Anthropic SDK/key is unavailable."""
    settings = get_settings()
    wanted = name or settings.ai_provider
    if wanted in registry.providers:
        return registry.get(wanted)
    if wanted == "anthropic":
        try:
            from app.ai.llm.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider()
            registry.register(provider)
            return provider
        except Exception as exc:  # missing key/SDK → degrade safely
            log.warning("anthropic provider unavailable, using offline provider", error=str(exc))
    provider = OfflineProvider()
    registry.register(provider)
    return provider


__all__ = ["LLMProvider", "LLMResult", "get_provider", "registry"]
