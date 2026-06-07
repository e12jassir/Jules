"""OpenRouter native provider with thinking token streaming (OpenAI-compatible API)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncIterator

from jules.memory.models import SessionContext
from jules.providers.base import (
    ContentEvent,
    ProviderError,
    ProviderUnavailableError,
    StreamEvent,
    ThoughtEvent,
)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        env_file = Path.home() / ".jules" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise ProviderUnavailableError(
            "OPENROUTER_API_KEY not found. Set it in ~/.jules/.env or as an env var."
        )
    return key


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        chunks: list[str] = []
        async for event in self.stream_events(prompt, context, model):
            if isinstance(event, ContentEvent):
                chunks.append(event.content)
        return "".join(chunks)

    async def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        async for event in self.stream_events(prompt, context, model):
            if isinstance(event, ContentEvent):
                yield event.content

    async def stream_events(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[StreamEvent]:
        """Stream ThoughtEvent + ContentEvent via OpenRouter SSE."""
        try:
            import httpx  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderUnavailableError(
                "httpx not installed. Run: pip install httpx"
            ) from exc

        api_key = _load_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jules-ai/jules",
            "X-Title": "Jules",
        }
        payload = {
            "model": model,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
            # reasoning field enables thinking tokens on supported models (e.g. deepseek-r1)
            "reasoning": {"effort": "medium"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{_OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise ProviderError(
                            f"OpenRouter HTTP {response.status_code}: {body.decode()[:200]}"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        delta = chunk.get("choices", [{}])[0].get("delta", {})

                        # Thinking tokens arrive in delta.reasoning
                        reasoning = delta.get("reasoning")
                        if reasoning:
                            yield ThoughtEvent(content=reasoning)

                        content = delta.get("content")
                        if content:
                            yield ContentEvent(content=content)

        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenRouter stream error: {exc}") from exc

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Use Ollama for embeddings.")

    async def health_check(self) -> bool:
        try:
            _load_api_key()
            import httpx  # type: ignore[import-not-found]  # noqa: F401
            return True
        except Exception:
            return False

    async def close(self) -> None:
        pass
