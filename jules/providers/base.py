from __future__ import annotations

from typing import AsyncIterator, Protocol

from jules.memory.models import SessionContext


class ProviderError(Exception):
    """Base provider error for transport or response failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when the backing provider cannot be reached."""


class ProviderTimeoutError(ProviderError):
    """Raised when the provider does not respond before the timeout."""


class Provider(Protocol):
    name: str

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        ...

    async def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        ...

    async def embed(self, text: str) -> list[float]:
        ...

    async def health_check(self) -> bool:
        ...

    async def close(self) -> None:
        ...
