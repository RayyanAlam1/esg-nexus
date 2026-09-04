"""LLM provider abstraction (strategy pattern). Agents never import a vendor SDK directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0
    stop_reason: str | None = None
    parsed: Any | None = None
    error: str | None = None
    refusal: dict | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.stop_reason != "refusal"


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        json_schema: dict | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
        purpose: str = "general",
    ) -> LLMResult: ...


@dataclass
class ProviderRegistry:
    providers: dict[str, LLMProvider] = field(default_factory=dict)

    def register(self, provider: LLMProvider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        return self.providers[name]


registry = ProviderRegistry()
