"""Jules IPC server — async stdin/stdout loop with newline-delimited JSON."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys

from jules.server.handlers import (
    handle_cancel,
    handle_command,
    handle_init,
    handle_message,
    handle_model_list,
    handle_model_set,
    handle_quit,
    handle_status_get,
)
from jules.server.protocol import (
    CancelRequest,
    CommandRequest,
    ErrorEvent,
    InitRequest,
    MessageRequest,
    ModelListRequest,
    ModelSetRequest,
    QuitRequest,
    StatusGetRequest,
    from_json,
    to_json,
)

# All logs to stderr ONLY
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _write(msg) -> None:
    """Write a single JSON line to stdout and flush immediately."""
    sys.stdout.write(to_json(msg) + "\n")
    sys.stdout.flush()


async def main() -> None:
    loop = asyncio.get_running_loop()

    # SIGTERM: flush and exit cleanly
    def _sigterm_handler() -> None:
        sys.stdout.flush()
        raise SystemExit(0)

    try:
        loop.add_signal_handler(signal.SIGTERM, _sigterm_handler)
    except (NotImplementedError, OSError):
        pass  # Windows or restricted environment

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    active_task: asyncio.Task | None = None

    while True:
        try:
            line = await reader.readline()
        except asyncio.CancelledError:
            break

        if not line:
            break  # EOF

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue

        try:
            data = json.loads(line_str)
        except json.JSONDecodeError as exc:
            _write(ErrorEvent(message=f"Invalid JSON: {exc}", recoverable=True))
            continue

        try:
            msg = from_json(data)
        except ValueError as exc:
            _write(ErrorEvent(message=str(exc), recoverable=True))
            continue

        # Dispatch
        try:
            if isinstance(msg, InitRequest):
                _write(handle_init(msg.protocol_version))

            elif isinstance(msg, MessageRequest):
                # Run streaming in a background task so incoming cancel
                # messages can be processed concurrently.
                async def _stream_message(content: str) -> None:
                    try:
                        async for event in handle_message(content):
                            _write(event)
                    except asyncio.CancelledError:
                        pass  # cancelled cleanly via handle_cancel

                active_task = asyncio.create_task(_stream_message(msg.content))
                # Do NOT await here — keep reading stdin for cancel/quit

            elif isinstance(msg, CancelRequest):
                if active_task is not None and not active_task.done():
                    _write(handle_cancel(active_task))
                    await asyncio.sleep(0)  # yield so the task processes CancelledError
                    active_task = None
                # silently ignore cancel outside an active message

            elif isinstance(msg, ModelListRequest):
                _write(handle_model_list())

            elif isinstance(msg, ModelSetRequest):
                _write(handle_model_set(msg.provider, msg.model))

            elif isinstance(msg, StatusGetRequest):
                _write(await handle_status_get())

            elif isinstance(msg, CommandRequest):
                _write(handle_command(msg.name, msg.args))

            elif isinstance(msg, QuitRequest):
                if active_task is not None and not active_task.done():
                    active_task.cancel()
                handle_quit()

        except SystemExit:
            break
        except Exception as exc:
            logger.exception("Unhandled error in dispatch")
            _write(ErrorEvent(message=str(exc), recoverable=True))
