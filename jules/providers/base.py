from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol, Union




class ProviderError(Exception):
    """Base provider error for transport or response failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when the backing provider cannot be reached."""


class ProviderTimeoutError(ProviderError):
    """Raised when the provider does not respond before the timeout."""


# ---------------------------------------------------------------------------
# Stream event types — emitted by providers that support native streaming
# ---------------------------------------------------------------------------

@dataclass
class ThoughtEvent:
    """Internal reasoning token (dim/italic in UI)."""
    content: str
    type: Literal["thought"] = field(default="thought", init=False)


@dataclass
class ContentEvent:
    """Final response token visible to the user."""
    content: str
    type: Literal["content"] = field(default="content", init=False)


@dataclass
class ToolStatusEvent:
    """Tool call start or completion."""
    tool: str
    args: dict
    status: Literal["start", "done"]
    type: Literal["tool_status"] = field(default="tool_status", init=False)


StreamEvent = Union[ThoughtEvent, ContentEvent, ToolStatusEvent]


class Provider(Protocol):
    name: str

    async def ask(self, prompt: str, context: list[dict], model: str) -> str:
        ...

    def stream(
        self,
        prompt: str,
        context: list[dict],
        model: str,
    ) -> AsyncIterator[str]:
        ...

    async def embed(self, text: str) -> list[float]:
        ...

    async def health_check(self) -> bool:
        ...

    async def close(self) -> None:
        ...
