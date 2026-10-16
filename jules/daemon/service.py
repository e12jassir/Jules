"""Resident JulesDaemon service, systemd --user unit generator, and lifecycle management.

Coordinates the central cognitive architecture in background RAM:
CognitiveRouter, PersistentMemory, EpisodicMemory, MemoryEngine, EventBus,
PlatformWatcher, ChatEngine, StatePublisher, and IPCServer.
"""

from __future__ import annotations

import asyncio
from inspect import isawaitable
import logging
import os
from pathlib import Path
import signal
import sys
from typing import Any, AsyncIterator

from jules.core.chat_engine import ChatEngine
from jules.core.events import EventBus
from jules.core.router import CognitiveRouter
from jules.core.session import SessionContext
from jules.daemon.ipc import IPCServer, resolve_socket_path
from jules.daemon.state import DaemonState, StatePublisher, resolve_state_path
from jules.memory.engine import MemoryEngine
from jules.memory.episodic import EpisodicMemory
from jules.memory.persistent import PersistentMemory
from jules.platform.initiative import InitiativeEngine
from jules.platform.watcher import PlatformWatcher
from jules.providers.base import ContentEvent, StreamEvent, ThoughtEvent
from jules.sanitizer import Sanitizer

logger = logging.getLogger(__name__)


def install_systemd_user_service(target_dir: Path | str | None = None) -> Path:
    """Generate and install systemd --user service unit for Jules.

    Non-systemd fallback:
    For Linux distributions without systemd (such as Alpine Linux with OpenRC
    or Void Linux with runit, per JULES.md):
      - OpenRC (/etc/init.d/jules):
          start-stop-daemon --start --exec <python_bin> -- -m jules.cli.main daemon start
      - runit (/var/service/jules/run):
          exec <python_bin> -m jules.cli.main daemon start

    Returns:
        Path to the installed jules.service file.
    """
    if target_dir is None:
        service_dir = Path.home() / ".config" / "systemd" / "user"
    else:
        service_dir = Path(target_dir).expanduser().resolve()

    service_dir.mkdir(parents=True, exist_ok=True)
    service_path = service_dir / "jules.service"

    python_bin = sys.executable
    service_content = f"""[Unit]
Description=Jules Cognitive Daemon
Documentation=https://github.com/e12jassir/Jules
After=network.target

[Service]
Type=simple
ExecStart={python_bin} -m jules.cli.main daemon start
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target

# Fallback note for non-systemd Linux distributions (e.g. Alpine with OpenRC, Void with runit):
# Per JULES.md, Jules runs local-first on any Linux distribution without containers.
# OpenRC service: start-stop-daemon --start --exec {python_bin} -- -m jules.cli.main daemon start
# runit service: exec {python_bin} -m jules.cli.main daemon start
"""
    service_path.write_text(service_content, encoding="utf-8")
    logger.info("Installed systemd user service at %s", service_path)
    return service_path


class JulesDaemon:
    """Resident Jules background daemon process.

    Maintains long-lived instances of all core subsystems in memory, exposes
    a low-latency UNIX domain socket for IPC commands, atomic state publisher,
    and handles graceful termination.
    """

    def __init__(
        self,
        router: CognitiveRouter | None = None,
        persistent_memory: PersistentMemory | None = None,
        episodic_memory: EpisodicMemory | None = None,
        memory_engine: MemoryEngine | None = None,
        event_bus: EventBus | None = None,
        platform_watcher: PlatformWatcher | None = None,
        chat_engine: ChatEngine | None = None,
        state_publisher: StatePublisher | None = None,
        ipc_server: IPCServer | None = None,
        socket_path: Path | str | None = None,
        state_path: Path | str | None = None,
        current_directory: str | None = None,
        sanitizer: type[Sanitizer] = Sanitizer,
        initiative_engine: InitiativeEngine | None = None,
    ) -> None:
        self.socket_path = resolve_socket_path(socket_path)
        self.state_path = resolve_state_path(state_path)
        self.sanitizer = sanitizer

        cwd = current_directory or os.getcwd()
        self.session_context = SessionContext(cwd=cwd)

        # 1. State Publisher
        self.state_publisher = state_publisher or StatePublisher(
            target_path=self.state_path,
            initial_state=DaemonState.IDLE,
            active_project=Path(cwd).name,
        )

        # 2. Event Bus
        self.event_bus = event_bus or EventBus()

        # 3. Platform Watcher
        self.platform_watcher = platform_watcher or PlatformWatcher(
            event_bus=self.event_bus,
            current_directory=cwd,
        )

        # 4. Memory subsystems
        if chat_engine is not None:
            self.chat_engine = chat_engine
            self.memory_engine = memory_engine or getattr(chat_engine, "memory_engine", None)  # type: ignore[assignment]
            self.router = router or getattr(chat_engine, "router", None)  # type: ignore[assignment]
            self.persistent_memory = persistent_memory or getattr(self.memory_engine, "persistent", None)  # type: ignore[assignment]
            self.episodic_memory = episodic_memory or getattr(self.memory_engine, "episodic", None)  # type: ignore[assignment]
        else:
            self.persistent_memory = persistent_memory or PersistentMemory()
            self.episodic_memory = episodic_memory or EpisodicMemory(
                Path.home() / ".jules" / "lancedb"
            )
            self.router = router or self._build_default_router()
            self.memory_engine = memory_engine or self._build_default_memory_engine(
                persistent=self.persistent_memory,
                episodic=self.episodic_memory,
                router=self.router,
            )
            self.chat_engine = self._build_default_chat_engine(
                router=self.router,
                memory_engine=self.memory_engine,
            )

        # 5. IPC Server
        self.ipc_server = ipc_server or IPCServer(
            socket_path=self.socket_path,
            sanitizer=self.sanitizer,
        )

        # 6. Initiative Engine ("El Fantasma en la Shell")
        self.initiative_engine = initiative_engine or InitiativeEngine(
            event_bus=self.event_bus,
            persistent_memory=self.persistent_memory,
            episodic_memory=self.episodic_memory,
            memory_engine=self.memory_engine,
        )

        # Wire IPC Server handlers
        self.ipc_server.set_query_handler(self._handle_query)
        self.ipc_server.set_ptt_handler(self._handle_ptt)
        self.ipc_server.set_barge_in_handler(self._handle_barge_in)
        self.ipc_server.set_shell_handler(self._handle_shell_event)
        self.ipc_server.set_status_handler(self._handle_status)

        self._stop_event = asyncio.Event()
        self._watcher_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @property
    def is_running(self) -> bool:
        """Return True if daemon IPC server is currently running."""
        return self.ipc_server.is_running

    def request_stop(self) -> None:
        """Signal the daemon to initiate graceful shutdown."""
        self._stop_event.set()

    async def start(self) -> None:
        """Start daemon components and begin listening on UNIX domain socket."""
        if self.is_running:
            return

        # Atomically write IDLE state
        self.state_publisher.update(
            state=DaemonState.IDLE,
            last_event="daemon_started",
            active_project=Path(self.session_context.cwd).name,
        )

        # Start IPC server
        await self.ipc_server.start()

        # Start PlatformWatcher polling in background task if available
        if self.platform_watcher is not None and not getattr(self.platform_watcher, "_running", False):
            if hasattr(self.platform_watcher, "start") and callable(self.platform_watcher.start):
                start_res = self.platform_watcher.start()
                if asyncio.iscoroutine(start_res):
                    self._watcher_task = asyncio.create_task(start_res)

    async def stop(self) -> None:
        """Gracefully stop daemon, clean up sockets, and unlink state file."""
        # 1. Stop watcher task
        if self.platform_watcher is not None and hasattr(self.platform_watcher, "stop"):
            self.platform_watcher.stop()
        if self._watcher_task is not None:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._watcher_task = None

        # 2. Stop IPC Server (unlinks socket file)
        if self.ipc_server is not None:
            await self.ipc_server.stop()

        # 3. Clean up StatePublisher (unlinks state file)
        if self.state_publisher is not None:
            self.state_publisher.cleanup()

        # 4. Await pending background tasks from memory engine
        if (
            self.memory_engine is not None
            and hasattr(self.memory_engine, "_background_tasks")
            and self.memory_engine._background_tasks
        ):
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(self.memory_engine._background_tasks), return_exceptions=True),
                    timeout=2.0,
                )
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("Timed out awaiting memory_engine background tasks")

        # 5. Close providers HTTP/socket connections
        if self.router is not None and hasattr(self.router, "providers"):
            for provider in self.router.providers.values():
                close = getattr(provider, "close", None)
                if callable(close):
                    try:
                        res = close()
                        if isawaitable(res):
                            await res
                    except Exception as err:
                        logger.debug("Error closing provider %s: %s", provider, err)

        # 6. Mark stop event as set
        self._stop_event.set()

    async def run_forever(self) -> None:
        """Run the daemon main loop until receiving SIGINT, SIGTERM, or stop signal."""
        await self.start()
        self._stop_event.clear()

        loop = asyncio.get_running_loop()
        signals = (signal.SIGINT, signal.SIGTERM)
        for sig in signals:
            try:
                loop.add_signal_handler(sig, self.request_stop)
            except (NotImplementedError, RuntimeError):
                pass

        try:
            await self._stop_event.wait()
        finally:
            for sig in signals:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass
            await self.stop()

    # -----------------------------------------------------------------------
    # IPC Handlers
    # -----------------------------------------------------------------------

    async def _handle_query(self, data: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        """Route IPC query to ChatEngine.stream_turn and emit streaming events."""
        user_input = data.get("text", "")
        session_id = data.get("session_id", "default")
        cwd = data.get("cwd") or self.session_context.cwd
        chat_history = data.get("chat_history") or []
        user_override = data.get("user_override") or data.get("model")

        self.state_publisher.update(
            state=DaemonState.THINKING,
            last_event="query_started",
            active_project=Path(cwd).name,
        )

        session_ctx = SessionContext(
            cwd=cwd,
            last_exit_code=self.session_context.last_exit_code,
            recent_commands=list(self.session_context.recent_commands),
        )

        has_spoken = False
        try:
            async for event in self.chat_engine.stream_turn(
                user_input=user_input,
                session_id=session_id,
                session_ctx=session_ctx,
                chat_history=chat_history,
                user_override=user_override,
            ):
                if isinstance(event, ContentEvent) and not has_spoken:
                    has_spoken = True
                    self.state_publisher.update(
                        state=DaemonState.SPEAKING,
                        last_event="streaming_response",
                    )
                yield event
        finally:
            last_model = getattr(self.chat_engine, "last_model", "") or ""
            self.state_publisher.update(
                state=DaemonState.IDLE,
                active_model=last_model,
                last_event="query_finished",
            )

    async def _handle_ptt(self) -> dict[str, Any]:
        """Toggle Push-to-Talk voice listening state."""
        current = self.state_publisher.get_current_state().state
        if current == DaemonState.LISTENING:
            self.state_publisher.update(
                state=DaemonState.IDLE,
                last_event="ptt_stop",
            )
            return {"status": "ok", "ptt": "inactive", "state": DaemonState.IDLE.value}

        self.state_publisher.update(
            state=DaemonState.LISTENING,
            last_event="ptt_start",
        )
        return {"status": "ok", "ptt": "active", "state": DaemonState.LISTENING.value}

    async def _handle_barge_in(self) -> dict[str, Any]:
        """Interrupt active TTS speech immediately."""
        self.state_publisher.update(
            state=DaemonState.IDLE,
            last_event="voice_barge_in",
        )
        return {"status": "ok", "barge_in": True, "state": DaemonState.IDLE.value}

    async def _handle_shell_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle shell hook execution events, updating session context and directory."""
        cmd = data.get("cmd", "")
        exit_code = int(data.get("exit_code", 0))
        cwd = data.get("cwd") or self.session_context.cwd
        phase = data.get("phase", "event")

        self.session_context.cwd = cwd
        self.session_context.last_exit_code = exit_code

        # Sanitizer first, always
        if cmd:
            san_result = self.sanitizer.check(cmd)
            if not san_result.is_safe:
                return {
                    "status": "blocked",
                    "reason": san_result.reason,
                    "blocked": True,
                }
            self.session_context.recent_commands.append(cmd)
            if len(self.session_context.recent_commands) > 50:
                self.session_context.recent_commands = self.session_context.recent_commands[-50:]

        if self.platform_watcher is not None and hasattr(self.platform_watcher, "on_directory_changed"):
            self.platform_watcher.on_directory_changed(cwd)

        # Wire shell event to InitiativeEngine
        if self.initiative_engine is not None and hasattr(self.initiative_engine, "on_shell_event"):
            try:
                session_id = data.get("session_id") or getattr(self.session_context, "session_id", "default")
                res = self.initiative_engine.on_shell_event(
                    cmd=cmd,
                    exit_code=exit_code,
                    cwd=cwd,
                    session_id=session_id,
                )
                if isawaitable(res):
                    await res
            except Exception as exc:
                logger.warning("InitiativeEngine on_shell_event error: %s", exc)

        self.state_publisher.update(
            last_event=f"shell_{phase}",
            active_project=Path(cwd).name,
        )
        return {"status": "ok", "handled": True}

    async def _handle_status(self) -> dict[str, Any]:
        """Return daemon health and full runtime state snapshot."""
        state_dict = self.state_publisher.get_current_state().to_dict()
        return {
            **state_dict,
            "status": "ok",
            "health": "healthy",
            "service": "jules-daemon",
        }

    # -----------------------------------------------------------------------
    # Subsystem Default Builders
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_default_router() -> CognitiveRouter:
        from jules.core.config import load_config
        from jules.providers.antigravity import AntigravityProvider
        from jules.providers.codex import CodexProvider
        from jules.providers.google import GoogleAIProvider
        from jules.providers.ollama import OllamaProvider
        from jules.providers.openai_oauth import OpenAIOAuthProvider
        from jules.providers.opencode import OpenCodeProvider
        from jules.providers.openrouter import OpenRouterProvider

        providers = {
            "antigravity": AntigravityProvider(),
            "codex": CodexProvider(),
            "google": GoogleAIProvider(),
            "ollama": OllamaProvider(),
            "openai_oauth": OpenAIOAuthProvider(),
            "opencode": OpenCodeProvider(),
            "openrouter": OpenRouterProvider(),
        }
        return CognitiveRouter(config=load_config(), providers=providers)

    @staticmethod
    def _build_default_memory_engine(
        persistent: PersistentMemory,
        episodic: EpisodicMemory,
        router: CognitiveRouter | None = None,
    ) -> MemoryEngine:
        from jules.memory.engine import MemoryEngine

        scoring_provider = None
        if router is not None and hasattr(router, "providers"):
            scoring_provider = router.providers.get("ollama")

        class _ScoringAdapter:
            def __init__(self, prov: Any, model: str = "llama3.2:1b") -> None:
                self.provider = prov
                self.model = model

            async def generate_text(self, prompt: str) -> str:
                if hasattr(self.provider, "ask"):
                    return await self.provider.ask(prompt, [], self.model)
                return "SCORE: 0.5"

        class _NoopScoringProvider:
            async def generate_text(self, prompt: str) -> str:
                del prompt
                return "SCORE: 0.5"

        scoring_adapter = _ScoringAdapter(scoring_provider) if scoring_provider else _NoopScoringProvider()
        embedding_prov = scoring_provider if hasattr(scoring_provider, "embed") else None

        return MemoryEngine(
            persistent=persistent,
            episodic=episodic,
            provider=scoring_adapter,
            embedding_provider=embedding_prov,
        )

    @staticmethod
    def _build_default_chat_engine(
        router: CognitiveRouter,
        memory_engine: MemoryEngine,
    ) -> ChatEngine:
        from jules.core.config import load_config
        from jules.core.permissions import PermissionGate
        from jules.personality.loader import PersonalityLoader
        from jules.sanitizer import Sanitizer

        config = load_config()
        return ChatEngine(
            router=router,
            memory_engine=memory_engine,
            personality_loader=PersonalityLoader(),
            sanitizer=Sanitizer,
            permission_gate=PermissionGate(config.permissions),
        )


__all__ = [
    "JulesDaemon",
    "install_systemd_user_service",
]
