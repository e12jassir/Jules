"""Google AI native provider with thinking token streaming (google.genai SDK)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, AsyncIterator, cast


from jules.providers.base import (
    ContentEvent,
    ProviderError,
    ProviderUnavailableError,
    StreamEvent,
    ThoughtEvent,
)


def _read_api_key_from_file() -> str | None:
    env_file = Path.home() / ".jules" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GOOGLE_AI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


async def _load_api_key() -> str:
    key = os.environ.get("GOOGLE_AI_API_KEY")
    if not key:
        key = await asyncio.to_thread(_read_api_key_from_file)
    if not key:
        raise ProviderUnavailableError(
            "GOOGLE_AI_API_KEY not found. Set it in ~/.jules/.env or as an env var."
        )
    return key


class GoogleAIProvider:
    name = "google"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def ask(self, prompt: str, context: list[dict], model: str) -> str:
        chunks: list[str] = []
        async for event in self.stream_events(prompt, context, model):
            if isinstance(event, ContentEvent):
                chunks.append(event.content)
        return "".join(chunks)

    async def stream(
        self,
        prompt: str,
        context: list[dict],
        model: str,
    ) -> AsyncIterator[str]:
        async for event in self.stream_events(prompt, context, model):
            if isinstance(event, ContentEvent):
                yield event.content

    async def stream_events(
        self,
        prompt: str,
        context: list[dict],
        model: str,
    ) -> AsyncIterator[StreamEvent]:
        """Stream ThoughtEvent + ContentEvent from Google AI Gemini (google.genai SDK)."""
        try:
            from google import genai  # type: ignore[import-not-found]
            from google.genai import types  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderUnavailableError(
                "google-genai not installed. Run: pip install google-genai"
            ) from exc

        api_key = await _load_api_key()
        client = genai.Client(api_key=api_key)

        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
        )

        try:
            response = await client.aio.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=config,
            )
            async for chunk in response:
                chunk_any = cast(Any, chunk)
                candidates = cast(list[Any], getattr(chunk_any, "candidates", []) or [])
                if not candidates:
                    continue
                first_candidate = candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = cast(list[Any], getattr(content, "parts", []) or [])
                for part in parts:
                    text = getattr(part, "text", None)
                    if getattr(part, "thought", False):
                        yield ThoughtEvent(content=text or "")
                    elif text:
                        yield ContentEvent(content=text)
        except Exception as exc:
            raise ProviderError(f"Google AI stream error: {exc}") from exc

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Use Ollama for embeddings.")

    async def health_check(self) -> bool:
        try:
            await _load_api_key()
            from google import genai  # type: ignore[import-not-found]  # noqa: F401
            return True
        except Exception:
            return False

    async def close(self) -> None:
        pass
