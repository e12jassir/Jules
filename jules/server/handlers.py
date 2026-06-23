"""IPC server handlers — bridge protocol messages to Jules subsystems."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from jules.server.protocol import (
    CancelledEvent,
    CommandResultEvent,
    DoneEvent,
    ErrorEvent,
    IpcMessage,
    MemoryStatsEvent,
    ModelChangedEvent,
    ModelListEvent,
    ProjectInfoEvent,
    ReadyEvent,
    StatusEvent,
    TokenEvent,
    ToolsEvent,
)

logger = logging.getLogger(__name__)

_BOOT_TIME: float = time.perf_counter()

# Mutable override state for model_set
_override_provider: str | None = None
_override_model: str | None = None


def handle_init(protocol_version: int) -> ReadyEvent:
    boot_ms = (time.perf_counter() - _BOOT_TIME) * 1000
    return ReadyEvent(protocol_version=protocol_version, boot_ms=boot_ms)


async def handle_message(content: str) -> AsyncGenerator[IpcMessage, None]:
    """Route user message through the cognitive router and stream tokens."""
    yielded_any_token = False
    token_count = 0
    router = None
    context = None
    task_type = None
    user_override = f"{_override_provider}:{_override_model}" if _override_provider else None
    try:
        from jules.core.router import CognitiveRouter, TaskType
        from jules.memory.models import SessionContext

        context = SessionContext(
            project=None,
            directory=".",
            active_files=[],
            inferred_intent=None,
            time_of_day="unknown",
        )

        router = CognitiveRouter()
        task_type = TaskType.QUICK

        provider, model = router.route(task_type, user_override=user_override)

        # Try streaming first
        stream = provider.stream(content, context, model)
        async for chunk in stream:
            yielded_any_token = True
            token_count += 1
            yield TokenEvent(content=chunk)
    except Exception as exc:
        if yielded_any_token:
            # Mid-stream failure — do NOT run fallback (would corrupt TUI buffer)
            logger.error("handle_message mid-stream failure: %s", exc)
            yield ErrorEvent(
                message=f"Streaming interrupted: {exc}", recoverable=True
            )
        elif router is not None and context is not None and task_type is not None:
            # Clean first-attempt failure: try non-streaming fallback
            try:
                response, model, provider_name = await router.ask_with_fallback(
                    content, context, task_type, user_override=user_override
                )
                token_count = 1
                yield TokenEvent(content=response)
            except Exception as inner_exc:
                logger.error("handle_message failed: %s", inner_exc)
                yield ErrorEvent(message=str(inner_exc), recoverable=True)
        else:
            # Setup itself failed (import / constructor / context build) —
            # router is unbound, so the fallback path cannot run.
            logger.error("handle_message setup failed: %s", exc)
            yield ErrorEvent(
                message=f"Setup failed: {exc}", recoverable=True
            )

    yield DoneEvent(tokens=token_count)


def handle_cancel(active_task: asyncio.Task[Any] | None) -> CancelledEvent:
    if active_task is not None and not active_task.done():
        active_task.cancel()
    return CancelledEvent()


def handle_model_list() -> ModelListEvent:
    """Read available models from config via the router's registry."""
    try:
        from jules.core.router import CognitiveRouter

        router = CognitiveRouter()
        models = router.available_models()
        return ModelListEvent(models=[list(pair) for pair in models])
    except Exception as exc:
        logger.error("handle_model_list failed: %s", exc)
        return ModelListEvent(models=[["ollama", "llama3.2:1b"]])


def handle_model_set(provider: str, model: str) -> ModelChangedEvent:
    global _override_provider, _override_model
    _override_provider = provider
    _override_model = model
    return ModelChangedEvent(provider=provider, model=model)


def handle_tools_get() -> ToolsEvent:
    """Detect which tools are actually available in the current environment."""
    import shutil

    filesystem = True  # always available
    terminal = bool(shutil.which("bash") or shutil.which("sh"))
    git = bool(shutil.which("git"))
    search = bool(shutil.which("rg") or shutil.which("grep"))
    web = False  # Phase 2 feature

    return ToolsEvent(
        filesystem=filesystem,
        terminal=terminal,
        git=git,
        search=search,
        web=web,
    )


def _count_project_files(root: Path) -> int:
    ignored_dirs = {".git", ".venv", "target", "__pycache__", ".pytest_cache"}
    total = 0
    for current_root, dirs, files in os.walk(root):
        del current_root
        dirs[:] = [name for name in dirs if name not in ignored_dirs]
        total += len(files)
    return total


def _project_info_get_sync() -> ProjectInfoEvent:
    import asyncio
    from jules.core.context import ContextEngine
    from jules.core.session import SessionContext

    cwd = Path.cwd()
    # ContextEngine.build is async — run it in a fresh event loop since we're
    # already on an executor thread (cannot use the main loop's running one).
    built = asyncio.new_event_loop().run_until_complete(
        ContextEngine.build(SessionContext(cwd=str(cwd)), "")
    )
    project_root = Path(built.project_root) if built.project_root else cwd
    branch = "---"

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip() or "---"
    except Exception:
        pass

    return ProjectInfoEvent(
        path=str(project_root),
        branch=branch,
        file_count=_count_project_files(project_root),
    )


def _memory_stats_get_sync() -> MemoryStatsEvent:
    status = _status_get_sync()
    return MemoryStatsEvent(episodes=status.episodes, facts=0, memories=0)


async def handle_project_info_get() -> ProjectInfoEvent:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _project_info_get_sync)


async def handle_memory_stats_get() -> MemoryStatsEvent:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _memory_stats_get_sync)


async def handle_context_get() -> list[IpcMessage]:
    tools = handle_tools_get()
    project_info, memory_stats = await asyncio.gather(
        handle_project_info_get(),
        handle_memory_stats_get(),
    )
    return [tools, project_info, memory_stats]


def _status_get_sync() -> StatusEvent:
    """Blocking I/O — run via run_in_executor, never call from the event loop directly."""
    online = False
    episodes = 0
    scoring_healthy = True

    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        online = resp.status_code == 200
    except Exception:
        pass

    try:
        import sqlite3

        from jules.memory.persistent import DEFAULT_SQLITE_PATH

        db_path = DEFAULT_SQLITE_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM episodes")
            episodes = cursor.fetchone()[0]
            conn.close()
    except Exception:
        pass

    return StatusEvent(online=online, episodes=episodes, scoring_healthy=scoring_healthy)


async def handle_status_get() -> StatusEvent:
    """Non-blocking: offloads sync I/O (httpx + SQLite) to a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _status_get_sync)


async def handle_command(name: str, args: list[str]) -> CommandResultEvent:
    """Dispatch slash commands to their handlers. Mirrors legacy jules/cli/commands.py."""
    try:
        if name == "status":
            status = await handle_status_get()
            data = {
                "online": status.online,
                "episodes": status.episodes,
                "scoring_healthy": status.scoring_healthy,
            }
            lines = [
                f"online: {'✓' if status.online else '✗'}",
                f"episodes: {status.episodes}",
                f"scoring: {'healthy' if status.scoring_healthy else 'degraded'}",
            ]
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines), **data})

        if name == "doctor":
            from jules.linux.doctor import run_all_checks
            loop = asyncio.get_running_loop()
            report = await loop.run_in_executor(None, run_all_checks)
            symbols = {"ok": "✓", "fail": "✗", "warn": "⚠"}
            lines = [f"  {symbols.get(r.status, '?')} {r.name}: {r.message}" for r in report.results]
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})

        if name == "memory":
            from jules.memory.engine import MemoryEngine
            from jules.memory.episodic import EpisodicMemory
            from jules.memory.persistent import PersistentMemory

            class _Noop:
                async def generate_text(self, prompt: str) -> str:
                    return "SCORE: 0.5"

            query = " ".join(args) if args else "recent"
            loop = asyncio.get_running_loop()
            persistent = await loop.run_in_executor(None, PersistentMemory)
            episodic = await loop.run_in_executor(
                None, EpisodicMemory, Path.home() / ".jules" / "lancedb"
            )
            engine = MemoryEngine(persistent=persistent, episodic=episodic, provider=_Noop(), embedding_provider=None)  # type: ignore[arg-type]
            results = await engine.retrieve_async(query, 8)
            if not results:
                return CommandResultEvent(name=name, ok=True, data={"text": "No hay episodios en memoria."})
            lines = [f"  [{ep.importance:.2f}] {(ep.problem or ep.solution or '')[:80]}" for ep in results]
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})

        if name == "sessions":
            from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
            from jules.models.chat_history import list_recent_sessions

            limit = int(args[0]) if args and args[0].isdigit() else 10
            engine = await asyncio.to_thread(create_memory_engine)
            factory = create_memory_sessionmaker(engine)
            async with factory() as session:
                sessions = await list_recent_sessions(session, limit)
            await engine.dispose()
            if not sessions:
                return CommandResultEvent(name=name, ok=True, data={"text": "No hay sesiones guardadas todavía."})
            lines = [f"{i}. {sid[:20]}" for i, sid in enumerate(sessions, 1)]
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})

        if name == "model":
            from jules.core.router import CognitiveRouter
            _OAUTH_PROVIDERS = {"codex"}
            loop = asyncio.get_running_loop()
            router = await loop.run_in_executor(None, CognitiveRouter)
            if not args:
                all_models = [(p, m) for p, m in router.available_models() if p not in _OAUTH_PROVIDERS]
                grouped: dict[str, list[str]] = {}
                for p, m in all_models:
                    grouped.setdefault(p, []).append(m)
                lines = ["Modelos disponibles:\n"]
                for p, ms in grouped.items():
                    lines.append(f"  {p}:")
                    lines.extend(f"    • {m}" for m in ms)
                return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})
            # Switch model
            target = " ".join(args)
            all_models = [(p, m) for p, m in router.available_models() if p not in _OAUTH_PROVIDERS]
            for p, m in all_models:
                if m == target or f"{p}:{m}" == target or target.lower() in m.lower():
                    handle_model_set(p, m)
                    return CommandResultEvent(name=name, ok=True, data={"text": f"Modelo activo: {p}:{m}", "provider": p, "model": m})
            return CommandResultEvent(name=name, ok=False, error=f"Modelo '{target}' no encontrado.")

        if name == "provider":
            if len(args) < 2:
                return CommandResultEvent(name=name, ok=False, error="Uso: /provider <cli|oauth|api|local> <nombre>")
            cat, prov_name = args[0].lower(), args[1].lower()
            _CAT_MAP = {
                ("cli", "opencode"): ("opencode", "opencode/minimax-m3-free"),
                ("cli", "antigravity"): ("antigravity", "gemini-3.5-flash-low"),
                ("cli", "codex"): ("codex", "openai/gpt-5.4-mini"),
                ("local", "ollama"): ("ollama", "llama3.2:1b"),
            }
            entry = _CAT_MAP.get((cat, prov_name))
            if not entry:
                return CommandResultEvent(name=name, ok=False, error=f"Proveedor desconocido: {cat} {prov_name}")
            provider_id, default_model = entry
            handle_model_set(provider_id, default_model)
            return CommandResultEvent(name=name, ok=True, data={"text": f"Proveedor: {provider_id}\nModelo: {default_model}", "provider": provider_id, "model": default_model})

        if name == "login":
            import importlib
            auth_pkce = importlib.import_module("jules.core.auth_pkce")
            provider_name = auth_pkce.normalize_provider_name(args[0] if args else "openai")
            prefer_device = any(a in {"device", "device-code", "headless"} for a in args[1:])
            notices: list[str] = []
            try:
                token = await auth_pkce.login_provider(provider_name, prefer_device_code=prefer_device, notify=notices.append)
                from datetime import datetime
                expiry = datetime.fromtimestamp(token.expires_at).strftime("%Y-%m-%d %H:%M") if token.expires_at else "sin vencimiento"
                notices.append(f"Login exitoso para {provider_name}. Expira: {expiry}.")
                return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(notices)})
            except Exception as exc:
                return CommandResultEvent(name=name, ok=False, error=f"Login falló: {exc}\n" + "\n".join(notices))

        if name == "logout":
            import importlib
            auth_pkce = importlib.import_module("jules.core.auth_pkce")
            provider_name = auth_pkce.normalize_provider_name(args[0] if args else "openai")
            removed = auth_pkce.logout_provider(provider_name)
            text = f"Token eliminado para {provider_name}." if removed else f"No había token para {provider_name}."
            return CommandResultEvent(name=name, ok=True, data={"text": text})

        if name == "auth":
            import importlib
            auth_pkce = importlib.import_module("jules.core.auth_pkce")
            providers = [auth_pkce.normalize_provider_name(args[0])] if args else ["openai", "claude"]
            lines = []
            for p in providers:
                st = auth_pkce.get_auth_status(p)
                if not st.logged_in:
                    lines.append(f"{p}: no autenticado")
                else:
                    from datetime import datetime
                    expiry = datetime.fromtimestamp(st.expires_at).strftime("%Y-%m-%d %H:%M") if st.expires_at else "sin vencimiento"
                    state_str = "expirado" if st.expired else "vigente"
                    lines.append(f"{p}: {state_str} · vence {expiry}")
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})

        if name == "help":
            lines = [
                "Comandos disponibles:\n",
                "  /exit        — Cerrar Jules",
                "  /sessions    — Ver sesiones anteriores",
                "  /memory      — Ver episodios recientes",
                "  /status      — Estado de providers",
                "  /doctor      — Correr diagnóstico",
                "  /model       — Cambiar modelo activo",
                "  /provider    — Configurar proveedor",
                "  /login       — Login OAuth",
                "  /logout      — Cerrar sesión OAuth",
                "  /auth        — Ver estado OAuth",
                "  /clear       — Limpiar chat log",
                "  /cancel      — Cancelar generación",
            ]
            return CommandResultEvent(name=name, ok=True, data={"text": "\n".join(lines)})

        return CommandResultEvent(name=name, ok=False, error=f"Unknown command: {name}")

    except Exception as exc:
        logger.error("handle_command %s failed: %s", name, exc)
        return CommandResultEvent(name=name, ok=False, error=str(exc))


def handle_quit() -> None:
    raise SystemExit(0)
