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
        from jules.core.router import CognitiveRouter
        from jules.providers.base import Provider

        router = await asyncio.to_thread(CognitiveRouter)
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


async def handle_doctor() -> str:
    """Run jules doctor checks and return summary."""
    import asyncio

    try:
        from jules.linux.doctor import run_all_checks

        report = await asyncio.to_thread(run_all_checks)
        symbols = {"ok": "✓", "fail": "✗", "warn": "⚠"}
        lines: list[str] = []
        for check in report.results:
            s = symbols.get(check.status, "?")
            lines.append(f"  {s} {check.name}: {check.message}")
        return "\n".join(lines)
    except Exception:
        return "No se pudo ejecutar doctor."


async def handle_model(args: tuple[str, ...]) -> str | tuple[str, str, str]:
    """List models (no args) or resolve a model switch (with args).

    With args: returns (display_str, provider, model) so the caller can apply the override.
    Without args: returns a formatted string listing available models.
    """
    import asyncio

    from jules.core.router import CognitiveRouter

    _OAUTH_PROVIDERS = {"codex"}

    router = await asyncio.to_thread(CognitiveRouter)

    if not args:
        models = router.available_models()
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

    name = " ".join(args)
    # Resolve to (provider, model) — try exact match first, then prefix match
    all_models = [(p, m) for p, m in router.available_models() if p not in _OAUTH_PROVIDERS]
    # exact match on model name
    for provider, model in all_models:
        if model == name or f"{provider}:{model}" == name:
            return (f"Modelo activo: {provider}:{model}", provider, model)
    # prefix/substring match
    for provider, model in all_models:
        if name.lower() in model.lower() or name.lower() == provider.lower():
            return (f"Modelo activo: {provider}:{model}", provider, model)
    return f"Modelo '{name}' no encontrado. Usá /model para ver los disponibles."


async def handle_provider(args: tuple[str, ...]) -> str | tuple[str, str, str]:
    """Resolve provider selection, initialize auth if needed, and set active override."""
    if not args:
        return "Uso: /provider <cli|oauth|api|local> <nombre>"
    
    cat = args[0].lower()
    if len(args) < 2:
        return f"Por favor especifica un proveedor para la categoría '{cat}'."
        
    name = args[1].lower()
    
    provider_id = None
    default_model = ""
    msg = ""

    if cat == "oauth":
        if name == "openai":
            # Delegate to handle_login which properly surfaces the device code URL
            return await handle_login(("openai", "device"))
        elif name == "claude":
            return "Claude OAuth no está configurado todavía."
            
    elif cat == "cli":
        if name == "codex":
            provider_id = "codex"
            default_model = "openai/gpt-5.4-mini"
            msg = "CLI configurado: Codex (Copilot)"
        elif name == "opencode":
            provider_id = "opencode"
            default_model = "opencode/minimax-m3-free"
            msg = "CLI configurado: OpenCode"
        elif name == "antigravity":
            provider_id = "antigravity"
            default_model = "gemini-3.5-flash-low"
            msg = "CLI configurado: Antigravity"
            
    elif cat == "local":
        provider_id = "ollama"
        default_model = "llama3.2:1b"
        msg = "Proveedor configurado: Ollama Local"
        
    else:
        return f"Categoría de proveedor desconocida: {cat}"
        
    if provider_id:
        return (f"{msg}\nModelo por defecto: {default_model}", provider_id, default_model)
    return f"Proveedor desconocido: {name}"


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
