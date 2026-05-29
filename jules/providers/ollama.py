from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import aiohttp

from jules.memory.models import SessionContext
from jules.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2:1b",
        embedding_model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.embedding_model = embedding_model or default_model
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def ask(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
        options: dict[str, object] | None = None,
    ) -> str:
        del context
        payload = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options
            
        data = await self._post_json("/api/generate", payload)

        response = data.get("response")
        if not isinstance(response, str):
            raise ProviderError("Ollama response did not include a text payload")
        return response

    async def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        del context
        timeout = aiohttp.ClientTimeout(total=None, sock_read=self.timeout_seconds, connect=5.0)

        try:
            session = self._get_session()
            async with session.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True},
                timeout=timeout,
            ) as response:
                await self._raise_for_status(response)
                async for line in response.content:
                    chunk = line.decode(errors="replace").strip()
                    if not chunk:
                        continue
                    payload = json.loads(chunk)
                    
                    if not isinstance(payload, dict):
                        raise ProviderError("Ollama streaming payload is not a JSON object")

                    if "error" in payload:
                        raise ProviderError(payload["error"])

                    text = payload.get("response")
                    if isinstance(text, str) and text:
                        yield text
                    if payload.get("done"):
                        return
        except asyncio.TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds}s"
            ) from exc
        except aiohttp.ClientError as exc:
            raise ProviderUnavailableError(f"Ollama is unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Invalid Ollama streaming payload: {exc}") from exc

    async def embed(self, text: str) -> list[float]:
        data = await self._post_json(
            "/api/embed",
            {"model": self.embedding_model, "input": text},
        )
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise ProviderError("Ollama embedding response did not include vectors")

        embedding = embeddings[0]
        if not isinstance(embedding, list) or not all(
            isinstance(value, (int, float)) for value in embedding
        ):
            raise ProviderError("Ollama embedding response did not include a vector")
        return [float(value) for value in embedding]

    async def health_check(self) -> bool:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            session = self._get_session()
            async with session.get(f"{self.base_url}/api/tags", timeout=timeout) as response:
                await self._raise_for_status(response)
                return True
        except (asyncio.TimeoutError, aiohttp.ClientError, ProviderError):
            return False

    async def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            session = self._get_session()
            async with session.post(f"{self.base_url}{path}", json=payload, timeout=timeout) as response:
                await self._raise_for_status(response)
                data = await response.json()
        except asyncio.TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds}s"
            ) from exc
        except (aiohttp.ContentTypeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Invalid Ollama JSON payload: {exc}") from exc
        except aiohttp.ClientError as exc:
            raise ProviderUnavailableError(f"Ollama is unavailable: {exc}") from exc

        if not isinstance(data, dict):
            raise ProviderError("Ollama returned a non-object JSON payload")
        return data

    async def _raise_for_status(self, response: aiohttp.ClientResponse) -> None:
        if response.status < 400:
            return

        details = await response.text()
        if response.status in {502, 503, 504}:
            raise ProviderUnavailableError(
                f"Ollama returned HTTP {response.status}: {details}"
            )
        raise ProviderError(f"Ollama returned HTTP {response.status}: {details}")
