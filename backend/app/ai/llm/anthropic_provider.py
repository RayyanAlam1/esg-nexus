"""Anthropic provider — official `anthropic` SDK.

Defaults: `claude-opus-5`, adaptive thinking (omitted → adaptive on Opus 5), `output_config.effort`, and
structured outputs via `output_config.format` when a JSON schema is supplied. Refusals are surfaced (never
silently swallowed) and every call reports token usage so it can be recorded as a ModelRun.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.ai.llm.base import LLMResult
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("ai.anthropic")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, effort: str | None = None):
        import anthropic  # imported lazily so the platform runs without the SDK configured

        settings = get_settings()
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()  # credentials resolved from ANTHROPIC_API_KEY / auth profile
        self.model = model or settings.anthropic_model
        self.effort = effort or settings.anthropic_effort
        self.max_tokens = settings.anthropic_max_tokens

    def complete(
        self, *, system: str, messages: list[dict[str, Any]], json_schema: dict | None = None, max_tokens: int | None = None, effort: str | None = None, purpose: str = "general"
    ) -> LLMResult:
        anthropic = self._anthropic
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or self.effort},
        }
        if json_schema is not None:
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": json_schema}
        try:
            # Streaming avoids HTTP timeouts on long narratives; get_final_message() returns the full Message.
            with self.client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        except anthropic.RateLimitError as exc:
            return self._error(f"rate_limited: {exc.message}", started)
        except anthropic.AuthenticationError:
            return self._error("authentication_failed: check ANTHROPIC_API_KEY", started)
        except anthropic.BadRequestError as exc:
            return self._error(f"bad_request: {exc.message}", started)
        except anthropic.APIStatusError as exc:
            return self._error(f"api_error_{exc.status_code}: {exc.message}", started)
        except anthropic.APIConnectionError as exc:
            return self._error(f"connection_error: {exc}", started)

        latency = int((time.perf_counter() - started) * 1000)
        text = "".join(block.text for block in response.content if block.type == "text")
        parsed = None
        if json_schema is not None and text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        refusal = None
        if response.stop_reason == "refusal" and getattr(response, "stop_details", None):
            refusal = {"category": getattr(response.stop_details, "category", None), "explanation": getattr(response.stop_details, "explanation", None)}
        usage = response.usage
        return LLMResult(
            text=text,
            provider=self.name,
            model=response.model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            latency_ms=latency,
            stop_reason=response.stop_reason,
            parsed=parsed,
            refusal=refusal,
        )

    def _error(self, message: str, started: float) -> LLMResult:
        log.warning("anthropic call failed", error=message)
        return LLMResult(text="", provider=self.name, model=self.model, latency_ms=int((time.perf_counter() - started) * 1000), error=message)
