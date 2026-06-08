"""IPC protocol message types for the Jules server (stdin/stdout, newline-delimited JSON)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


# --- Base ---

@dataclass
class IpcMessage:
    type: str


# --- Inbound ---

@dataclass
class InitRequest(IpcMessage):
    protocol_version: int = 1
    type: str = field(default="init", init=False)


@dataclass
class MessageRequest(IpcMessage):
    content: str = ""
    type: str = field(default="message", init=False)


@dataclass
class CommandRequest(IpcMessage):
    name: str = ""
    args: list[str] = field(default_factory=list)
    type: str = field(default="command", init=False)


@dataclass
class ModelSetRequest(IpcMessage):
    provider: str = ""
    model: str = ""
    type: str = field(default="model_set", init=False)


@dataclass
class ModelListRequest(IpcMessage):
    type: str = field(default="model_list", init=False)


@dataclass
class StatusGetRequest(IpcMessage):
    type: str = field(default="status_get", init=False)


@dataclass
class CancelRequest(IpcMessage):
    type: str = field(default="cancel", init=False)


@dataclass
class QuitRequest(IpcMessage):
    type: str = field(default="quit", init=False)


# --- Outbound ---

@dataclass
class ReadyEvent(IpcMessage):
    protocol_version: int = 1
    boot_ms: float = 0.0
    type: str = field(default="ready", init=False)


@dataclass
class TokenEvent(IpcMessage):
    content: str = ""
    type: str = field(default="token", init=False)


@dataclass
class ThoughtEvent(IpcMessage):
    content: str = ""
    type: str = field(default="thought", init=False)


@dataclass
class DoneEvent(IpcMessage):
    tokens: int = 0
    type: str = field(default="done", init=False)


@dataclass
class CancelledEvent(IpcMessage):
    type: str = field(default="cancelled", init=False)


@dataclass
class CommandResultEvent(IpcMessage):
    name: str = ""
    ok: bool = True
    data: Any = None
    error: str | None = None
    type: str = field(default="command_result", init=False)


@dataclass
class ModelChangedEvent(IpcMessage):
    provider: str = ""
    model: str = ""
    type: str = field(default="model_changed", init=False)


@dataclass
class ModelListEvent(IpcMessage):
    models: list[list[str]] = field(default_factory=list)
    type: str = field(default="model_list", init=False)


@dataclass
class StatusEvent(IpcMessage):
    online: bool = False
    episodes: int = 0
    scoring_healthy: bool = True
    type: str = field(default="status", init=False)


@dataclass
class ErrorEvent(IpcMessage):
    message: str = ""
    recoverable: bool = True
    type: str = field(default="error", init=False)


# --- Serialization ---

def to_json(msg: IpcMessage) -> str:
    return json.dumps(asdict(msg), ensure_ascii=False)


_INBOUND_DISPATCH: dict[str, type[IpcMessage]] = {
    "init": InitRequest,
    "message": MessageRequest,
    "command": CommandRequest,
    "model_set": ModelSetRequest,
    "model_list": ModelListRequest,
    "status_get": StatusGetRequest,
    "cancel": CancelRequest,
    "quit": QuitRequest,
}


def from_json(data: dict[str, Any]) -> IpcMessage:
    msg_type = data.get("type")
    if not msg_type or msg_type not in _INBOUND_DISPATCH:
        raise ValueError(f"Unknown or missing message type: {msg_type!r}")
    cls = _INBOUND_DISPATCH[msg_type]
    # Filter only fields the dataclass accepts
    valid_fields = {f.name for f in cls.__dataclass_fields__.values() if f.name != "type"}
    kwargs = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**kwargs)
