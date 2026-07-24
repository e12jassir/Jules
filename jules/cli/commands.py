"""Slash command parsing for the Jules TUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib

COMMANDS = {
    "exit": "Cerrar Jules",
    "sessions": "Ver sesiones anteriores",
    "memory": "Ver episodios recientes",
    "status": "Estado de providers",
    "doctor": "Correr diagnóstico",
    "model": "Cambiar modelo para el proveedor activo",
    "provider": "Configurar proveedor (cli | oauth | api | local)",
    "login": "Login OAuth: openai | claude",
    "logout": "Borrar token OAuth guardado",
    "auth": "Ver estado OAuth guardado",
    "clear": "Limpiar el chat log",
    "help": "Mostrar ayuda",
}


@dataclass(frozen=True)
class SlashCommand:
    """Parsed slash command."""

    name: str
    args: tuple[str, ...]
    known: bool


def parse_slash_command(value: str) -> SlashCommand | None:
    """Return a parsed command when value starts with `/`, else None."""
    text = value.strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    name = parts[0].lower() if parts else "help"
    return SlashCommand(name=name, args=tuple(parts[1:]), known=name in COMMANDS)


def handle_help() -> str:
    """Return formatted help string listing all commands."""
    lines = ["Comandos disponibles:\n"]
    for name, description in COMMANDS.items():
        lines.append(f"  /{name} — {description}")
    return "\n".join(lines)


async def handle_sessions(limit: int = 10) -> str:
    """List recent chat sessions from persistence."""
    try:
        import asyncio

        from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
        from jules.models.chat_history import list_recent_sessions

        engine = await asyncio.to_thread(create_memory_engine)
        session_factory = create_memory_sessionmaker(engine)
        async with session_factory() as session:
            sessions = await list_recent_sessions(session, limit)
        await engine.dispose()
        if not sessions:
            return "No hay sesiones guardadas todavía."
        lines: list[str] = []
        for i, sid in enumerate(sessions, 1):
            display = sid[:20] if len(sid) > 20 else sid
            lines.append(f"{i}. {display}")
        return "\n".join(lines)
    except Exception:
        return "No hay sesiones guardadas todavía."


async def handle_sessions_json(limit: int = 20) -> list[dict]:
    """List recent chat sessions as structured JSON list."""
    try:
        import asyncio
        from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
        from jules.models.chat_history import list_recent_sessions_info

        engine = await asyncio.to_thread(create_memory_engine)
        session_factory = create_memory_sessionmaker(engine)
        async with session_factory() as session:
            sessions = await list_recent_sessions_info(session, limit)
        await engine.dispose()
        return sessions
    except Exception:
        return []


async def handle_load_session(session_id: str) -> list[dict]:
    """Load messages for a session ID as structured JSON list."""
    if not session_id:
        return []
    try:
        import asyncio
        from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
        from jules.models.chat_history import list_session_messages

        engine = await asyncio.to_thread(create_memory_engine)
        session_factory = create_memory_sessionmaker(engine)
        async with session_factory() as session:
            entries = await list_session_messages(session, session_id)
        await engine.dispose()
        return [{"role": e.role, "content": e.content} for e in entries]
    except Exception:
        return []


async def handle_delete_session(session_id: str) -> bool:
    """Delete a session from persistence."""
    if not session_id:
        return False
    try:
        import asyncio
        from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
        from jules.models.chat_history import delete_session

        engine = await asyncio.to_thread(create_memory_engine)
        session_factory = create_memory_sessionmaker(engine)
        async with session_factory() as session:
            await delete_session(session, session_id)
        await engine.dispose()
        return True
    except Exception:
        return False


async def handle_memory(query: str = "", limit: int = 8) -> str:
    """Show recent memory episodes."""
    try:
        import asyncio
        from pathlib import Path

        from jules.memory.engine import MemoryEngine
        from jules.memory.episodic import EpisodicMemory
        from jules.memory.persistent import PersistentMemory

        class _Noop:
            async def generate_text(self, prompt: str) -> str:
                return "SCORE: 0.5"

        persistent_mem = await asyncio.to_thread(PersistentMemory)
        episodic_mem = await asyncio.to_thread(EpisodicMemory, Path.home() / ".jules" / "lancedb")

        engine = MemoryEngine(
            persistent=persistent_mem,
            episodic=episodic_mem,
            provider=_Noop(),  # type: ignore[arg-type]
            embedding_provider=None,
        )
        results = await engine.retrieve_async(query or "recent", limit)
        if not results:
            return "No hay episodios en memoria."
        lines: list[str] = []
        for ep in results:
            content = (ep.problem or ep.solution or "")[:80]
            lines.append(f"  [{ep.importance:.2f}] {content}")
        return "\n".join(lines)
    except Exception:
        return "No hay episodios en memoria."


async def handle_status() -> str:
    """Show provider health status."""
    import asyncio

    try:
        from jules.core.router import _get_router
        from jules.providers.base import Provider

        router = await _get_router()
        lines: list[str] = ["Estado de providers:\n"]

        async def _check(name: str, provider: Provider) -> str:
            try:
                ok = await asyncio.wait_for(provider.health_check(), timeout=3.0)
                symbol = "✅ disponible" if ok else "❌ no disponible"
            except Exception:
                symbol = "❌ no disponible"
            return f"  {name}: {symbol}"

        results = await asyncio.gather(
            *[_check(name, p) for name, p in router.providers.items()]
        )
        lines.extend(results)
        return "\n".join(lines)
    except Exception:
        return "No se pudo obtener el estado de los providers."


async def handle_doctor(args: tuple[str, ...] = ()) -> str:
    """Run jules doctor checks and return summary, or run auto-fix if requested."""
    import asyncio

    try:
        from jules.platform.doctor import run_all_checks, run_auto_repair

        if args and args[0] in ("fix", "--fix", "repair"):
            actions = await asyncio.to_thread(run_auto_repair)
            report = await asyncio.to_thread(run_all_checks)
            lines = ["Reparaciones automáticas aplicadas:"]
            if actions:
                lines.extend(f"  ✓ {a}" for a in actions)
            else:
                lines.append("  (No se requirieron reparaciones)")
            lines.extend(["", "Estado actual del sistema:"])
        else:
            report = await asyncio.to_thread(run_all_checks)
            lines = []

        symbols = {"ok": "✓", "fail": "✗", "warn": "⚠"}
        for check in report.results:
            s = symbols.get(check.status, "?")
            lines.append(f"  {s} {check.name}: {check.message}")
        return "\n".join(lines)
    except Exception as e:
        return f"No se pudo ejecutar doctor: {e}"


async def handle_model(args: tuple[str, ...]) -> str | tuple[str, str, str]:
    """List models (no args) or resolve a model switch (with args).

    With args: returns (display_str, provider, model) so the caller can apply the override.
    Without args: returns a formatted string listing available models.
    """
    import asyncio

    from jules.core.router import _get_router

    _OAUTH_PROVIDERS = {"codex"}

    router = await _get_router()

    if not args:
        models = await router.available_models()
        grouped: dict[str, list[str]] = {}
        for provider, model in models:
            if provider in _OAUTH_PROVIDERS:
                continue
            grouped.setdefault(provider, []).append(model)
        lines = ["Modelos disponibles:\n"]
        for provider, model_list in grouped.items():
            lines.append(f"  {provider}:")
            for m in model_list:
                lines.append(f"    • {m}")
        return "\n".join(lines)

    name = " ".join(args).strip()
    if ":" in name:
        p_name, m_name = name.split(":", 1)
        p_key = p_name.lower().strip()
        m_name = m_name.strip()
        if p_key in ("opencode zen", "opencode"):
            p_name = "opencode"
        elif p_key == "openrouter":
            p_name = "openrouter"
        elif p_key == "ollama":
            p_name = "ollama"
        elif p_key == "antigravity":
            p_name = "antigravity"
        elif p_key in ("openai oauth", "openai"):
            p_name = "openai_oauth"
        return (f"Modelo activo: {p_name}:{m_name}", p_name, m_name)

    # exact match on model name
    available_models = await router.available_models()
    all_models = [(p, m) for p, m in available_models if p not in _OAUTH_PROVIDERS]
    for provider, model in all_models:
        if model == name or f"{provider}:{model}" == name:
            return (f"Modelo activo: {provider}:{model}", provider, model)
    # prefix/substring match
    for provider, model in all_models:
        if name.lower() in model.lower() or name.lower() == provider.lower():
            return (f"Modelo activo: {provider}:{model}", provider, model)
    return f"Modelo '{name}' no encontrado. Usá /model para ver los disponibles."


def _set_api_key(provider_name: str, key: str) -> str:
    import os
    from pathlib import Path

    p_map = {
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_AI_API_KEY",
        "gemini": "GOOGLE_AI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gpt": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    var_name = p_map.get(provider_name.lower())
    if not var_name:
        return f"Proveedor de API Key desconocido: '{provider_name}'. Opciones válidas: openrouter, google, openai, claude."

    os.environ[var_name] = key
    env_path = Path.home() / ".jules" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if not line.startswith(f"{var_name}="):
                lines.append(line)
    lines.append(f"{var_name}={key}")
    env_path.write_text("\n".join(lines) + "\n")
    return f"✓ API key para {provider_name} ({var_name}) guardada correctamente en ~/.jules/.env"


async def handle_provider(args: tuple[str, ...]) -> str | tuple[str, str, str]:
    """Resolve provider selection, initialize auth if needed, and set active override."""
    if not args:
        return (
            "Proveedores disponibles:\n\n"
            "  • openrouter  — OpenRouter (Claude, GPT-4o, Gemini, DeepSeek) [API Key]\n"
            "  • google      — Google Gemini API [API Key]\n"
            "  • openai      — OpenAI / GPT [API Key / OAuth]\n"
            "  • opencode    — OpenCode Zen (modelos libres)\n"
            "  • antigravity — Antigravity (modelos AGY)\n"
            "  • ollama      — Ollama Local\n\n"
            "Comandos de configuración:\n"
            "  /provider set <proveedor> <API_KEY>   (Guarda tu API key en ~/.jules/.env)\n"
            "  /provider <nombre>                     (Activa el proveedor)"
        )

    first = args[0].lower()

    if first == "set":
        if len(args) < 3:
            return "Uso: /provider set <openrouter|google|openai|claude> <TU_API_KEY>"
        return _set_api_key(args[1], args[2])

    # Direct provider selection, e.g. `/provider openrouter` or `/provider google`
    name = first
    cat = args[1].lower() if len(args) >= 2 else ""

    if name in ("openrouter", "api") and (cat == "openrouter" or name == "openrouter"):
        return ("Proveedor configurado: OpenRouter", "openrouter", "openrouter:anthropic/claude-3.7-sonnet")

    if name in ("google", "gemini", "api") and (cat in ("google", "gemini") or name in ("google", "gemini")):
        return ("Proveedor configurado: Google Gemini API", "google", "google:gemini-2.5-flash")

    if name in ("opencode", "cli") and (cat == "opencode" or name == "opencode"):
        return ("Proveedor configurado: OpenCode", "opencode", "opencode:deepseek-v4-flash-free")

    if name in ("antigravity", "cli") and (cat == "antigravity" or name == "antigravity"):
        return ("Proveedor configurado: Antigravity", "antigravity", "antigravity:gemini-3.5-flash-low")

    if name in ("codex", "cli") and (cat == "codex" or name == "codex"):
        return ("Proveedor configurado: Codex (Copilot)", "codex", "codex:openai/gpt-5.4-mini")

    if name in ("ollama", "local") and (cat == "ollama" or name == "ollama"):
        return ("Proveedor configurado: Ollama Local", "ollama", "ollama:llama3.2:1b")

    if name in ("openai", "oauth") and (cat == "openai" or name == "openai"):
        return await handle_login(("openai", "device"))

    return f"Proveedor no reconocido: '{name}'. Usá /provider para ver la lista."


def _format_expiry(expires_at: float | None) -> str:
    if expires_at is None:
        return "sin vencimiento"
    return datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M")


async def handle_login(args: tuple[str, ...]) -> str:
    auth_pkce = importlib.import_module("jules.core.auth_pkce")
    OAuthError = auth_pkce.OAuthError
    login_provider = auth_pkce.login_provider
    normalize_provider_name = auth_pkce.normalize_provider_name

    provider = normalize_provider_name(args[0] if args else "openai")
    prefer_device_code = any(arg.lower() in {"device", "device-code", "headless"} for arg in args[1:])
    notices: list[str] = []
    try:
        token = await login_provider(
            provider,
            prefer_device_code=prefer_device_code,
            notify=notices.append,
        )
    except OAuthError as exc:
        prefix = "\n".join(notices)
        suffix = f"Login OAuth falló para {provider}: {exc}"
        return f"{prefix}\n{suffix}".strip()
    expiry = _format_expiry(token.expires_at)
    notices.append(f"Login OAuth exitoso para {provider}. Expira: {expiry}.")
    return "\n".join(notices)


async def handle_logout(args: tuple[str, ...]) -> str:
    auth_pkce = importlib.import_module("jules.core.auth_pkce")
    logout_provider = auth_pkce.logout_provider
    normalize_provider_name = auth_pkce.normalize_provider_name

    provider = normalize_provider_name(args[0] if args else "openai")
    removed = logout_provider(provider)
    if removed:
        return f"Token OAuth eliminado para {provider}."
    return f"No había token OAuth guardado para {provider}."


async def handle_auth(args: tuple[str, ...]) -> str:
    auth_pkce = importlib.import_module("jules.core.auth_pkce")
    get_auth_status = auth_pkce.get_auth_status
    normalize_provider_name = auth_pkce.normalize_provider_name

    providers = [normalize_provider_name(args[0])] if args else ["openai", "claude"]
    lines: list[str] = []
    for provider in providers:
        status = get_auth_status(provider)
        if not status.logged_in:
            lines.append(f"{provider}: no autenticado")
            continue
        state = "expirado" if status.expired else "vigente"
        lines.append(f"{provider}: {state} · vence {_format_expiry(status.expires_at)}")
    return "\n".join(lines)
