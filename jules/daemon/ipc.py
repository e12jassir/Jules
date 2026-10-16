"""UNIX Domain Socket IPC protocol for the Jules daemon and clients.

Provides high-performance, local-first inter-process communication (<5ms)
over /run/user/$UID/jules.sock (with fallback to ~/.jules/run/jules.sock).
Enforces 0o600 file permissions and checks Sanitizer rules on incoming commands.
"""

from __future__ import annotations

import asyncio
from inspect import isawaitable
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from jules.providers.base import ContentEvent, StreamEvent, ThoughtEvent
from jules.sanitizer import Sanitizer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IPCError(Exception):
    """Base exception for Jules IPC errors."""


class IPCConnectionError(IPCError, ConnectionError):
    """Raised when connecting to the Jules daemon socket fails."""


class IPCTimeoutError(IPCError, TimeoutError):
    """Raised when an IPC request or streaming operation times out."""


# ---------------------------------------------------------------------------
# Socket Path Resolution
# ---------------------------------------------------------------------------


def resolve_socket_path(target_path: Path | str | None = None) -> Path:
    """Resolve the path for the jules.sock UNIX domain socket.

    1. If target_path is explicitly provided, use it.
    2. If XDG_RUNTIME_DIR is set and is an accessible writable directory, use $XDG_RUNTIME_DIR/jules.sock.
    3. Fallback to ~/.jules/run/jules.sock.
    """
    if target_path is not None:
        return Path(target_path).expanduser().resolve()

    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        p = Path(xdg_runtime).expanduser()
        if p.is_dir() and os.access(p, os.W_OK):
            return p / "jules.sock"

    return Path.home() / ".jules" / "run" / "jules.sock"


# ---------------------------------------------------------------------------
# Type Definitions
# ---------------------------------------------------------------------------

QueryHandler = Callable[[dict[str, Any]], AsyncIterator[StreamEvent | dict[str, Any]]]
CallbackHandler = Callable[..., Awaitable[dict[str, Any] | None] | dict[str, Any] | None]


# ---------------------------------------------------------------------------
# IPC Server
# ---------------------------------------------------------------------------


class IPCServer:
    """UNIX Domain Socket server implementing the Jules JSON-Lines IPC protocol."""

    def __init__(
        self,
        socket_path: Path | str | None = None,
        query_handler: QueryHandler | None = None,
        ptt_handler: CallbackHandler | None = None,
        barge_in_handler: CallbackHandler | None = None,
        voice_listen_once_handler: CallbackHandler | None = None,
        shell_handler: CallbackHandler | None = None,
        status_handler: CallbackHandler | None = None,
        sanitizer: type[Sanitizer] = Sanitizer,
    ) -> None:
        self.socket_path = resolve_socket_path(socket_path)
        self.query_handler = query_handler
        self.ptt_handler = ptt_handler
        self.barge_in_handler = barge_in_handler
        self.voice_listen_once_handler = voice_listen_once_handler
        self.shell_handler = shell_handler
        self.status_handler = status_handler
        self.sanitizer = sanitizer

        self._server: asyncio.Server | None = None
        self._serving_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Return True if the server is active and listening for connections."""
        return self._server is not None and self._server.is_serving()

    def set_query_handler(self, handler: QueryHandler) -> None:
        """Register the query stream handler."""
        self.query_handler = handler

    def set_ptt_handler(self, handler: CallbackHandler) -> None:
        """Register the Push-to-Talk toggle handler."""
        self.ptt_handler = handler

    def set_barge_in_handler(self, handler: CallbackHandler) -> None:
        """Register the voice barge-in handler."""
        self.barge_in_handler = handler

    def set_voice_listen_once_handler(self, handler: CallbackHandler) -> None:
        """Register the single-shot voice trigger handler."""
        self.voice_listen_once_handler = handler

    def set_shell_handler(self, handler: CallbackHandler) -> None:
        """Register the shell hook event handler."""
        self.shell_handler = handler

    def set_status_handler(self, handler: CallbackHandler) -> None:
        """Register the daemon health and status handler."""
        self.status_handler = handler

    async def start(self) -> None:
        """Start the UNIX domain socket server and enforce 0o600 permissions."""
        if self.is_running:
            return

        # Handle existing socket file
        if self.socket_path.exists():
            try:
                # Test if an active server is listening
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(str(self.socket_path)),
                    timeout=0.2,
                )
                writer.close()
                await writer.wait_closed()
                raise RuntimeError(f"Daemon socket is already active at {self.socket_path}")
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                # Stale or dead socket file left over from a previous crash
                logger.info("Removing stale socket file at %s", self.socket_path)
                try:
                    self.socket_path.unlink()
                except OSError as err:
                    logger.warning("Failed to unlink stale socket file: %s", err)

        # Ensure parent directory exists
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Start UNIX server
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )

        # Enforce secure socket permissions (0o600 - owner only)
        os.chmod(self.socket_path, 0o600)
        logger.info("Jules IPC server listening on %s (mode 0o600)", self.socket_path)

    async def stop(self) -> None:
        """Gracefully stop the server and clean up socket file."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError as err:
                logger.warning("Could not unlink socket file on stop: %s", err)

    async def __aenter__(self) -> IPCServer:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming client connection streaming line-delimited JSON."""
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break

                text = line.decode("utf-8").strip()
                if not text:
                    continue

                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    await self._send_json(writer, {"status": "error", "error": "Invalid JSON"})
                    continue

                if not isinstance(data, dict):
                    await self._send_json(
                        writer,
                        {"status": "error", "error": "Payload must be a JSON object"},
                    )
                    continue

                op = data.get("op")
                if not op or not isinstance(op, str):
                    await self._send_json(
                        writer,
                        {"status": "error", "error": "Missing or invalid 'op' field in payload"},
                    )
                    continue

                await self._dispatch_op(op, data, writer)
        except (ConnectionResetError, BrokenPipeError):
            logger.debug("Client disconnected abruptly.")
        except Exception as exc:
            logger.exception("Unexpected error in IPC client handler: %s", exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch_op(
        self,
        op: str,
        data: dict[str, Any],
        writer: asyncio.StreamWriter,
    ) -> None:
        """Route request by 'op' string."""
        if op == "query":
            await self._handle_query(data, writer)
        elif op == "voice_ptt_toggle":
            await self._handle_ptt(writer)
        elif op == "voice_barge_in":
            await self._handle_barge_in(writer)
        elif op == "voice_listen_once":
            await self._handle_voice_listen_once(writer)
        elif op == "shell_event":
            await self._handle_shell_event(data, writer)
        elif op == "status":
            await self._handle_status(writer)
        else:
            await self._send_json(
                writer,
                {"status": "error", "error": f"Unknown operation: {op}"},
            )

    async def _handle_query(
        self,
        data: dict[str, Any],
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle streaming conversational query."""
        user_input = data.get("text", "")

        # Sanitizer first, always
        sanitize_result = self.sanitizer.check(user_input)
        if not sanitize_result.is_safe:
            await self._send_json(
                writer,
                {
                    "type": "content",
                    "content": f"Mensaje bloqueado por sanitizador: {sanitize_result.reason}",
                },
            )
            await self._send_json(
                writer,
                {"type": "done", "status": "blocked", "reason": sanitize_result.reason},
            )
            return

        if self.query_handler is None:
            await self._send_json(
                writer,
                {"type": "content", "content": f"Echo: {user_input}"},
            )
            await self._send_json(writer, {"type": "done", "status": "ok"})
            return

        try:
            async for chunk in self.query_handler(data):
                if isinstance(chunk, ThoughtEvent):
                    msg = {"type": "thought", "content": chunk.content}
                elif isinstance(chunk, ContentEvent):
                    msg = {"type": "content", "content": chunk.content}
                elif isinstance(chunk, dict):
                    msg = chunk
                else:
                    msg = {"type": "content", "content": str(chunk)}
                await self._send_json(writer, msg)

            await self._send_json(writer, {"type": "done", "status": "ok"})
        except (ConnectionResetError, BrokenPipeError):
            logger.debug("Client disconnected during query streaming")
        except Exception as exc:
            logger.exception("Error during query streaming: %s", exc)
            try:
                await self._send_json(writer, {"type": "error", "error": str(exc)})
                await self._send_json(writer, {"type": "done", "status": "error"})
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass

    async def _handle_ptt(self, writer: asyncio.StreamWriter) -> None:
        """Handle Push-to-Talk toggle."""
        resp = {"status": "ok", "ptt": "toggled"}
        if self.ptt_handler is not None:
            try:
                res = self.ptt_handler()
                if isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    resp = {**res}
                    resp.setdefault("status", "ok")
            except Exception as exc:
                logger.exception("Error in ptt_handler: %s", exc)
                resp = {"status": "error", "error": str(exc)}
        await self._send_json(writer, resp)

    async def _handle_barge_in(self, writer: asyncio.StreamWriter) -> None:
        """Handle instant voice barge-in interruption."""
        resp = {"status": "ok", "barge_in": True}
        if self.barge_in_handler is not None:
            try:
                res = self.barge_in_handler()
                if isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    resp = {**res}
                    resp.setdefault("status", "ok")
            except Exception as exc:
                logger.exception("Error in barge_in_handler: %s", exc)
                resp = {"status": "error", "error": str(exc)}
        await self._send_json(writer, resp)

    async def _handle_voice_listen_once(self, writer: asyncio.StreamWriter) -> None:
        """Handle single-shot resident voice turn (record, transcribe, chat, TTS)."""
        resp: dict[str, Any] = {"status": "ok"}
        if self.voice_listen_once_handler is not None:
            try:
                res = self.voice_listen_once_handler()
                if isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    resp = {**res}
                    resp.setdefault("status", "ok")
            except Exception as exc:
                logger.exception("Error in voice_listen_once_handler: %s", exc)
                resp = {"status": "error", "error": str(exc)}
        await self._send_json(writer, resp)

    async def _handle_shell_event(
        self,
        data: dict[str, Any],
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle shell hook event, passing command through Sanitizer first."""
        cmd = data.get("cmd", "")

        # Sanitizer first, always
        sanitize_result = self.sanitizer.check(cmd)
        if not sanitize_result.is_safe:
            await self._send_json(
                writer,
                {
                    "status": "blocked",
                    "reason": sanitize_result.reason,
                    "blocked": True,
                },
            )
            return

        resp = {"status": "ok", "handled": True}
        if self.shell_handler is not None:
            try:
                res = self.shell_handler(data)
                if isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    resp = {**res}
                    resp.setdefault("status", "ok")
            except Exception as exc:
                logger.exception("Error in shell_handler: %s", exc)
                resp = {"status": "error", "error": str(exc)}
        await self._send_json(writer, resp)

    async def _handle_status(self, writer: asyncio.StreamWriter) -> None:
        """Handle daemon status request."""
        resp = {"status": "ok", "health": "healthy", "service": "jules-daemon"}
        if self.status_handler is not None:
            try:
                res = self.status_handler()
                if isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    resp = {**res}
                    resp.setdefault("status", "ok")
            except Exception as exc:
                logger.exception("Error in status_handler: %s", exc)
                resp = {"status": "error", "error": str(exc)}
        await self._send_json(writer, resp)

    async def _send_json(self, writer: asyncio.StreamWriter, data: dict[str, Any]) -> None:
        """Serialize dict to JSON line and flush."""
        payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        writer.write(payload)
        await writer.drain()


# ---------------------------------------------------------------------------
# IPC Client
# ---------------------------------------------------------------------------


class IPCClient:
    """Asynchronous client communicating with the Jules daemon over UNIX domain socket."""

    def __init__(
        self,
        socket_path: Path | str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.socket_path = resolve_socket_path(socket_path)
        self.timeout = timeout

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Establish connection to the UNIX socket with timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.open_unix_connection(str(self.socket_path)),
                timeout=self.timeout,
            )
        except (FileNotFoundError, ConnectionRefusedError, OSError) as err:
            raise IPCConnectionError(
                f"Could not connect to Jules daemon at {self.socket_path}: {err}"
            ) from err
        except TimeoutError as err:
            raise IPCTimeoutError(
                f"Connection timeout to Jules daemon at {self.socket_path}"
            ) from err

    async def send_raw_line(self, raw_line: str) -> str:
        """Send a raw string line and return the raw string response line."""
        reader, writer = await self._connect()
        try:
            if not raw_line.endswith("\n"):
                raw_line += "\n"
            writer.write(raw_line.encode("utf-8"))
            await writer.drain()

            try:
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            except TimeoutError as err:
                raise IPCTimeoutError("Read timeout waiting for response") from err

            if not line:
                raise IPCConnectionError("Server closed connection before response")
            return line.decode("utf-8")
        finally:
            writer.close()
            await writer.wait_closed()

    async def send_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON payload and return parsed response dictionary."""
        raw_res = await self.send_raw_line(json.dumps(payload, ensure_ascii=False))
        try:
            return json.loads(raw_res)
        except json.JSONDecodeError as err:
            raise IPCError(f"Server returned non-JSON response: {raw_res}") from err

    async def get_status(self) -> dict[str, Any]:
        """Query daemon health, memory, and model status."""
        return await self.send_raw({"op": "status"})

    async def toggle_ptt(self) -> dict[str, Any]:
        """Toggle Push-to-Talk voice listening."""
        return await self.send_raw({"op": "voice_ptt_toggle"})

    async def barge_in(self) -> dict[str, Any]:
        """Interrupt active TTS speech immediately."""
        return await self.send_raw({"op": "voice_barge_in"})

    async def voice_listen_once(self) -> dict[str, Any]:
        """Trigger single-shot resident voice turn (record, transcribe, chat, TTS)."""
        return await self.send_raw({"op": "voice_listen_once"})

    async def send_shell_event(
        self,
        phase: str,
        cmd: str,
        exit_code: int = 0,
        cwd: str | None = None,
        duration_ms: float = 0.0,
        **extra: Any,
    ) -> dict[str, Any]:
        """Notify daemon of a shell command execution (preexec/precmd)."""
        payload: dict[str, Any] = {
            "op": "shell_event",
            "phase": phase,
            "cmd": cmd,
            "exit_code": exit_code,
            "cwd": cwd,
            "duration_ms": duration_ms,
            **extra,
        }
        return await self.send_raw(payload)

    async def stream_query(
        self,
        text: str,
        session_id: str = "default",
        cwd: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        **extra: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Stream conversational query chunks (ThoughtEvent, ContentEvent) from daemon."""
        reader, writer = await self._connect()
        try:
            payload: dict[str, Any] = {
                "op": "query",
                "text": text,
                "session_id": session_id,
                "cwd": cwd,
                "chat_history": chat_history,
                **extra,
            }
            writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await writer.drain()

            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                except TimeoutError as err:
                    raise IPCTimeoutError("Read timeout while streaming response") from err

                if not line:
                    break

                try:
                    chunk = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as err:
                    raise IPCError(f"Malformed chunk from server: {line.decode('utf-8')}") from err

                chunk_type = chunk.get("type")
                if chunk_type == "done":
                    break
                elif chunk_type == "thought":
                    yield ThoughtEvent(content=chunk.get("content", ""))
                elif chunk_type == "content":
                    yield ContentEvent(content=chunk.get("content", ""))
                elif chunk_type == "error":
                    raise IPCError(chunk.get("error", "Error during streaming"))
        finally:
            writer.close()
            await writer.wait_closed()
