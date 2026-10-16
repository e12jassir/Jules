"""Headless NDJSON protocol server for non-Textual frontends (e.g. the
`jules-tui` Rust prototype).

Reads one JSON object per line from stdin, writes one JSON object per line
to stdout. No Textual dependency — drives `jules.core.chat_engine` directly.

Wire protocol
-------------
Client -> server, one message per line:
    {"type": "user_message", "content": "<text>"}
    {"type": "command", "name": "status", "args": []}

The `command` message reuses the slash-command handlers from
`jules.cli.commands` (the same logic the now-obsolete Textual TUI used —
see `jules.cli.commands.COMMANDS` for the full list: help, sessions,
memory, status, doctor, model, provider, login, logout, auth). `clear` and
`exit` are intentionally NOT dispatched here — they are pure client-side
concerns (clearing the local message list / quitting the process) and the
Rust frontend should handle them locally without sending anything over
the wire.

Server -> client, one or more messages per turn:
    {"type": "status", "provider": "...", "model": "..."}
    {"type": "thinking", "content": "..."}
    {"type": "content_chunk", "content": "..."}
    {"type": "done"}
    {"type": "error", "message": "..."}

Every line is a complete, self-contained JSON object (NDJSON) so the client
can parse it without buffering beyond a single newline.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

from jules.core.chat_engine import ChatEngineState, stream_turn
from jules.providers.base import ContentEvent, ThoughtEvent

if TYPE_CHECKING:
    from jules.memory.persistent import PersistentMemory


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def _dispatch_command(state: ChatEngineState, name: str, args: list[str]) -> None:
    """Run one of the slash commands ported from the Textual prototype
    (`jules.cli.commands`, now the only place that logic lives — the
    Textual UI itself is obsolete, but its command handlers are the real
    backend logic and are reused as-is here, per user decision 2026-07-19:
    "migra todo el backend... el cli y funciones que ya estaban").

    Each handler either returns a plain string (rendered as one
    `content_chunk`), or a `(display, provider, model)` tuple when the
    command changes the active model/provider — that tuple updates `state`
    the same way `stream_turn` does, so a subsequent chat turn picks it up.
    """
    from jules.cli import commands as cmds

    try:
        if name == "help":
            result = cmds.handle_help()
        elif name == "sessions":
            result = await cmds.handle_sessions()
        elif name == "sessions_json":
            sessions = await cmds.handle_sessions_json()
            _write({"type": "sessions_json", "sessions": sessions})
            return
        elif name == "load_session":
            sid = args[0] if args else ""
            msgs = await cmds.handle_load_session(sid)
            _write({"type": "loaded_session", "session_id": sid, "messages": msgs})
            return
        elif name == "delete_session":
            sid = args[0] if args else ""
            await cmds.handle_delete_session(sid)
            _write({"type": "deleted_session", "session_id": sid})
            return
        elif name == "memory":
            result = await cmds.handle_memory(" ".join(args))
        elif name == "status":
            result = await cmds.handle_status()
        elif name == "doctor":
            result = await cmds.handle_doctor(tuple(args))
        elif name == "model":
            result = await cmds.handle_model(tuple(args))
        elif name == "provider":
            result = await cmds.handle_provider(tuple(args))
        elif name == "login":
            result = await cmds.handle_login(tuple(args))
        elif name == "logout":
            result = await cmds.handle_logout(tuple(args))
        elif name == "auth":
            result = await cmds.handle_auth(tuple(args))
        elif name in ("clear", "exit"):
            # Purely client-side — the Rust frontend handles these locally
            # (clearing its own message list / quitting the process) and
            # should never actually send them over the wire. Handled here
            # too, defensively, so an unexpected "command" message with
            # this name still gets a clean response instead of falling
            # through to "unknown command".
            result = ""
        else:
            _write({"type": "error", "message": f"unknown command: /{name}"})
            return
    except Exception as exc:  # noqa: BLE001 - a broken command must not crash the session
        _write({"type": "error", "message": f"command /{name} failed: {exc}"})
        return

    if isinstance(result, tuple):
        display, provider, model = result
        state.active_provider = provider
        state.active_model = model
        state.user_model_override = f"{provider}:{model}"
        if display:
            _write({"type": "content_chunk", "content": display})
    elif result:
        _write({"type": "content_chunk", "content": result})

    _write({"type": "status", "provider": state.active_provider, "model": state.active_model})
    _write({"type": "done"})


async def handle_line(
    line: str,
    state: ChatEngineState,
    session_id: str,
    persistent: PersistentMemory | None = None,
) -> None:
    """Process a single JSON line protocol message."""
    # Defensively support (state, line, ...) if passed in reverse order
    if isinstance(line, ChatEngineState) and isinstance(state, str):
        state, line = line, state

    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        _write({"type": "error", "message": f"invalid json: {exc}"})
        return

    msg_type = msg.get("type")

    if msg_type == "command":
        name = msg.get("name")
        args = msg.get("args", [])
        if not isinstance(name, str) or not name:
            _write({"type": "error", "message": "command.name must be a non-empty string"})
            return
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            _write({"type": "error", "message": "command.args must be a list of strings"})
            return
        await _dispatch_command(state, name, args)
        return

    if msg_type != "user_message":
        _write({"type": "error", "message": f"unknown message type: {msg_type!r}"})
        return

    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        _write({"type": "error", "message": "user_message.content must be a non-empty string"})
        return

    try:
        async for event in stream_turn(state, content, session_id=session_id):
            if isinstance(event, ThoughtEvent):
                _write({"type": "thinking", "content": event.content})
            elif isinstance(event, ContentEvent):
                _write({"type": "content_chunk", "content": event.content})
            else:
                # ToolStatusEvent or any future variant — forward generically.
                _write({"type": "tool_status", "data": event.__dict__})

        _write({"type": "status", "provider": state.active_provider, "model": state.active_model})
        _write({"type": "done"})
    except Exception as exc:  # noqa: BLE001 - protocol boundary must degrade, not crash
        _write({"type": "error", "message": str(exc)})


async def _handle_line(
    state: ChatEngineState,
    line: str,
    session_id: str,
    persistent: PersistentMemory | None = None,
) -> None:
    """Compatibility alias for handle_line."""
    await handle_line(line, state, session_id, persistent)


async def run_protocol_loop() -> None:
    """Read stdin line by line until EOF, dispatching each as a turn."""
    import uuid
    from jules.memory.persistent import PersistentMemory

    state = ChatEngineState()
    session_id = str(uuid.uuid4())
    try:
        persistent = PersistentMemory()
    except Exception:  # noqa: BLE001
        persistent = None

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        raw = await reader.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        await handle_line(line, state, session_id, persistent)


def main() -> None:
    try:
        asyncio.run(run_protocol_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
