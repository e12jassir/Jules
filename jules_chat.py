"""
jules_chat.py — Terminal interactivo de Jules (Fase 1 completa)

Módulos integrados:
  - Módulo 1:  Sanitizador en la frontera de entrada
  - Módulo 5:  CognitiveRouter quota-aware con fallback en cascada
  - Módulo 6:  MemoryEngine (persist_async fire-and-forget + retrieve_async)

Comandos disponibles en el chat:
  /mode auto        — Cognitive Router decide el proveedor según el tipo de tarea
  /mode ollama      — Fuerza Ollama local (streaming)
  /mode antigravity — Fuerza Antigravity (Gemini)
  /mode opencode    — Fuerza OpenCode (DeepSeek)
  /mode codex       — Fuerza Codex (GPT)
  /model <nombre>   — Cambia el modelo dentro del proveedor actual
  /memory           — Muestra los últimos episodios guardados en memoria
  /status           — Tabla de estado de los proveedores
  /history          — Muestra el historial de la sesión en RAM
  /clear            — Limpia el historial de la sesión
  /exit             — Cierra el chat
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Rich (UI premium) — graceful fallback a texto plano
# ──────────────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ──────────────────────────────────────────────────────────────────────────────
# Jules internals
# ──────────────────────────────────────────────────────────────────────────────
from jules.core.config import load_config
from jules.core.router import CognitiveRouter, TaskType
from jules.memory.engine import MemoryEngine
from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Base, Episode, SessionContext
from jules.memory.persistent import PersistentMemory
from jules.memory.scoring import evaluate_importance
from jules.providers.base import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from jules.providers.ollama import OllamaProvider
from jules.sanitizer.sanitizer import Sanitizer

logging.basicConfig(level=logging.WARNING, format="%(levelname)s │ %(name)s │ %(message)s")
log = logging.getLogger("jules.chat")

# ──────────────────────────────────────────────────────────────────────────────
# Console setup
# ──────────────────────────────────────────────────────────────────────────────
if HAS_RICH:
    console = Console()
else:
    class _SimpleConsole:
        @staticmethod
        def _strip(t: str) -> str:
            return re.sub(r"\[/?[^\[\]]*\]", "", str(t))

        def print(self, *args, **kwargs) -> None:
            end = kwargs.get("end", "\n")
            print(self._strip(args[0]) if args else "", end=end, flush=True)

        def input(self, prompt: str) -> str:
            return input(self._strip(prompt))

    console = _SimpleConsole()  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────────────────────
# Default paths
# ──────────────────────────────────────────────────────────────────────────────
JULES_HOME = Path.home() / ".jules"
SQLITE_PATH = JULES_HOME / "memory.sqlite3"
LANCEDB_PATH = JULES_HOME / "vectors"
VECTOR_DIM = 3  # dummy — real embeddings in a future module


# ══════════════════════════════════════════════════════════════════════════════
# UI helpers
# ══════════════════════════════════════════════════════════════════════════════

def print_banner() -> None:
    art = r"""
 ██████╗██╗   ██╗██╗     ███████╗███████╗
   ██╔══╝██║   ██║██║     ██╔════╝██╔════╝
   ██║   ██║   ██║██║     █████╗  ███████╗
   ██║   ██║   ██║██║     ██╔══╝  ╚════██║
 ╚██████╗╚██████╔╝███████╗███████╗███████║
  ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝
  🧠 CAPA COGNITIVA LOCAL-FIRST — Fase 1
    """
    if HAS_RICH:
        console.print(Panel(art.strip(), style="bold cyan", border_style="cyan"))
    else:
        print("=" * 62)
        print(art.strip())
        print("=" * 62)


def print_help() -> None:
    if HAS_RICH:
        table = Table(title="Comandos disponibles", border_style="dim", show_header=False)
        table.add_column("Comando", style="bold cyan", min_width=22)
        table.add_column("Descripción")
        rows = [
            ("/mode <provider>",  "auto | ollama | antigravity | opencode | codex"),
            ("/model <nombre>",   "Cambia el modelo dentro del proveedor actual"),
            ("/memory [N]",       "Muestra los últimos N episodios guardados (default 5)"),
            ("/status",           "Estado en tiempo real de todos los proveedores"),
            ("/history",          "Historial de la sesión en RAM"),
            ("/clear",            "Limpia el historial de la sesión"),
            ("/exit",             "Cierra Jules"),
        ]
        for cmd, desc in rows:
            table.add_row(cmd, desc)
        console.print(table)
    else:
        print("\n💡 Comandos:")
        print("  /mode <auto|ollama|antigravity|opencode|codex>")
        print("  /model <nombre>   — cambia modelo del proveedor actual")
        print("  /memory [N]       — últimos episodios en memoria")
        print("  /status           — salud de los proveedores")
        print("  /history          — historial de sesión")
        print("  /clear            — limpia historial")
        print("  /exit             — salir")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Ollama model discovery (lee manifests locales, no depende del daemon)
# ══════════════════════════════════════════════════════════════════════════════

def _discover_local_ollama_models() -> list[str]:
    """Lee el directorio de manifests de Ollama sin depender del daemon."""
    manifests_root = Path.home() / ".ollama" / "models" / "manifests"
    models: list[str] = []
    if not manifests_root.exists():
        return models
    for tag_file in manifests_root.glob("*/*/*"):
        if tag_file.is_file():
            # registry.ollama.ai/library/llama3.2/1b  →  llama3.2:1b
            parts = tag_file.parts[len(manifests_root.parts):]  # relative parts
            if len(parts) >= 3:
                name = parts[-2]  # e.g. "llama3.2"
                tag = parts[-1]   # e.g. "1b"
                models.append(f"{name}:{tag}")
    return sorted(set(models))


async def _get_daemon_ollama_models(provider: OllamaProvider) -> list[str]:
    """Consulta el daemon de Ollama vía HTTP. Retorna lista vacía si no corre."""
    try:
        session = provider._get_session()
        async with session.get(f"{provider.base_url}/api/tags", timeout=3) as r:
            if r.status == 200:
                data = await r.json()
                return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        pass
    return []


# ══════════════════════════════════════════════════════════════════════════════
# Provider health table
# ══════════════════════════════════════════════════════════════════════════════

async def check_health(router: CognitiveRouter, local_models: list[str]) -> None:
    if HAS_RICH:
        table = Table(title="🤖 Estado de los proveedores", border_style="dim")
        table.add_column("Proveedor", style="bold")
        table.add_column("Modelos", style="cyan")
        table.add_column("Estado", style="bold")

    rows = []
    for name, provider in router.providers.items():
        try:
            healthy = await provider.health_check()
        except Exception:
            healthy = False

        if name == "ollama":
            daemon_models = await _get_daemon_ollama_models(provider) if healthy else []
            models_str = ", ".join(daemon_models) if daemon_models else (
                "Sin modelos activos (daemon offline)" if not healthy else "Sin modelos en el daemon"
            )
            status = (
                "[green]ONLINE ✅[/green]" if daemon_models else
                "[yellow]DAEMON OFF ⚠️[/yellow]" if local_models else
                "[red]OFFLINE ❌[/red]"
            )
        else:
            models_str = getattr(provider, "default_model", "—")
            if hasattr(provider, "_prepared_models"):
                models_str = ", ".join(provider._prepared_models) or models_str
            status = "[green]ONLINE ✅[/green]" if healthy else "[red]OFFLINE ❌[/red]"

        rows.append((name.capitalize(), models_str, status))

    if HAS_RICH:
        for name, mstr, st in rows:
            table.add_row(name, mstr, st)
        console.print(table)

        # Modelos Ollama locales encontrados en disco
        if local_models:
            console.print(f"  [dim]📁 Modelos Ollama en disco: {', '.join(local_models)}[/dim]")
            console.print(f"  [dim]   (Para activarlos corré: [bold]ollama serve[/bold] en otra terminal)[/dim]")
        console.print()
    else:
        print("\n🤖 ESTADO DE LOS PROVEEDORES:")
        for name, mstr, st in rows:
            clean = re.sub(r"\[/?[^\[\]]*\]", "", st)
            print(f"  {name}: {mstr} — {clean}")
        if local_models:
            print(f"  📁 Ollama en disco: {', '.join(local_models)}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
# Memory Engine bootstrap
# ══════════════════════════════════════════════════════════════════════════════

async def _init_memory_engine(router: CognitiveRouter) -> MemoryEngine | None:
    """Inicializa el MemoryEngine con SQLite + LanceDB. Retorna None si falla."""
    try:
        JULES_HOME.mkdir(parents=True, exist_ok=True)
        LANCEDB_PATH.mkdir(parents=True, exist_ok=True)

        db_url = f"sqlite+aiosqlite:///{SQLITE_PATH}"
        persistent = PersistentMemory(database_url=db_url)
        async with persistent.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        episodic = EpisodicMemory(db_path=str(LANCEDB_PATH), vector_dimension=VECTOR_DIM)
        
        ollama_provider = router.providers.get("ollama")

        class ScoringAdapter:
            def __init__(self, prov):
                self.prov = prov

            async def generate_text(self, prompt: str) -> str:
                # Fast fail if the provider is offline to avoid waiting 30s
                try:
                    if not await self.prov.health_check():
                        raise RuntimeError("Ollama daemon is offline")
                except Exception:
                    raise RuntimeError("Ollama daemon is offline or unreachable")

                # Provide a dummy context just for scoring
                ctx = SessionContext(
                    project="internal",
                    directory="",
                    active_files=[],
                    inferred_intent="scoring",
                    time_of_day="now"
                )
                # Ensure we use default_model or a fallback string if it's missing
                model_to_use = getattr(self.prov, "default_model", "llama3.2:1b")
                return await self.prov.ask(prompt, ctx, model_to_use)

        adapter = ScoringAdapter(ollama_provider) if ollama_provider else None

        return MemoryEngine(
            persistent=persistent,
            episodic=episodic,
            provider=adapter,
        )
    except Exception as exc:
        log.warning("MemoryEngine no pudo inicializarse: %s — Jules operará sin memoria persistente.", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Session context builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_session_context(mode: str, model: str) -> SessionContext:
    hour = datetime.now().hour
    if hour < 12:
        tod = "morning"
    elif hour < 18:
        tod = "afternoon"
    else:
        tod = "night"

    return SessionContext(
        project="jules-chat",
        directory=str(Path(__file__).parent),
        active_files=[],
        inferred_intent=f"chat-{mode}",
        time_of_day=tod,
    )


def _build_episode(
    episode_id: str,
    user_input: str,
    response: str,
    mode: str,
    model: str,
    provider_name: str,
    duration_seconds: int,
    start_ts: datetime,
) -> Episode:
    return Episode(
        id=episode_id,
        timestamp=start_ts,
        context=_build_session_context(mode, model),
        problem=user_input,
        process=f"Routed to {provider_name} ({model}) via CognitiveRouter",
        solution=response[:1000],  # cap para no saturar el scorer
        duration_seconds=duration_seconds,
        friction_score=0.0,
        tags=["chat", mode, provider_name],
        model_used=model,
        provider_used=provider_name,
    )


# ══════════════════════════════════════════════════════════════════════════════
# /memory command
# ══════════════════════════════════════════════════════════════════════════════

async def show_memory(engine: MemoryEngine | None, limit: int = 5) -> None:
    if engine is None:
        console.print("[yellow]⚠️  Memoria no disponible en esta sesión.[/yellow]")
        return

    episodes = await engine.retrieve_async("recent", limit=limit)
    if not episodes:
        console.print("[dim]No hay episodios guardados todavía.[/dim]")
        return

    if HAS_RICH:
        table = Table(title=f"🧠 Últimos {len(episodes)} episodios", border_style="dim")
        table.add_column("ID", style="dim", max_width=10)
        table.add_column("Timestamp", style="cyan")
        table.add_column("Importancia", justify="center")
        table.add_column("Proveedor")
        table.add_column("Problema", max_width=45)
        for ep in episodes:
            table.add_row(
                ep.id[:8],
                ep.timestamp.strftime("%H:%M:%S"),
                f"{ep.importance:.2f}",
                ep.provider_used or "—",
                (ep.problem or "—")[:45],
            )
        console.print(table)
    else:
        print(f"\n🧠 Últimos {len(episodes)} episodios:")
        for ep in episodes:
            print(f"  [{ep.timestamp.strftime('%H:%M:%S')}] {ep.provider_used} | importance={ep.importance:.2f} | {(ep.problem or '')[:50]}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Keyword-based task classifier
# ══════════════════════════════════════════════════════════════════════════════

_CODING_KW = {"code", "código", "python", "clase", "def ", "function", "escribí", "implement", "fix", "bug", "refactor"}
_HEAVY_KW  = {"arquitectura", "design", "review", "analiz", "compara", "explica en detalle", "tradeoff"}
_ID_KW     = {"quién sos", "quien sos", "tu nombre", "sos jules", "identidad", "jules sos"}

def _classify_task(text: str) -> TaskType:
    t = text.lower()
    if any(k in t for k in _ID_KW):
        return TaskType.IDENTITY
    if any(k in t for k in _HEAVY_KW):
        return TaskType.ANALYSIS
    if any(k in t for k in _CODING_KW):
        return TaskType.CODING
    return TaskType.QUICK


# ══════════════════════════════════════════════════════════════════════════════
# Prompt builder
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_FULL = (
    "[INSTRUCCIÓN DE SISTEMA: Tu nombre es Jules. Sos una capa cognitiva local-first, "
    "inteligente, directa y serena. Respondé siempre en español rioplatense (con voseo), "
    "con calma, precisión y sin rodeos innecesarios o disculpas vacías. "
    "Bajo ninguna circunstancia digas que sos un modelo de Google, OpenAI, "
    "DeepSeek o tu proveedor. Sos Jules. Respondé de forma directa.]"
)
SYSTEM_MINI = "[INSTRUCCIÓN: Sos Jules. Respondé conciso en español rioplatense (voseo). No digas que sos una IA.]"


def _build_prompt(system: str, history: list[dict], user_input: str) -> str:
    hist = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    if hist:
        return f"{system}\n\n[CONTEXTO RECIENTE]\n{hist}\n\nUsuario: {user_input}\nJules:"
    return f"{system}\n\nUsuario: {user_input}\nJules:"


# ══════════════════════════════════════════════════════════════════════════════
# Single-turn ask dispatch
# ══════════════════════════════════════════════════════════════════════════════

async def _ask(
    router: CognitiveRouter,
    mode: str,
    current_model: str | None,
    prompt: str,
    context: SessionContext,
    local_ollama_models: list[str],
) -> tuple[str, str, str]:
    """
    Returns (response, model_used, provider_name).
    Raises ProviderError / ProviderTimeoutError / ProviderUnavailableError on failure.
    """
    ollama_provider = router.providers.get("ollama")

    def _ollama_active_model() -> str | None:
        """Returns the configured default model for Ollama."""
        return ollama_provider.default_model if ollama_provider else None

    if mode == "auto":
        task = _classify_task(prompt)
        provider, resolved_model = router.route(task)
        pname = provider.name
    elif mode == "ollama":
        provider = router.providers["ollama"]
        resolved_model = current_model or provider.default_model
        pname = "ollama"
    elif mode == "antigravity":
        provider = router.providers["antigravity"]
        resolved_model = current_model or "gemini-3.5-flash-low"
        pname = "antigravity"
    elif mode == "opencode":
        provider = router.providers["opencode"]
        # Use first model configured in config.toml for low_cost opencode
        low_cost_tier = router.config.routing.tiers.get("low_cost")
        config_model = (
            low_cost_tier.opencode[0]
            if low_cost_tier and low_cost_tier.opencode
            else "opencode/deepseek-v4-flash-free"
        )
        resolved_model = current_model or config_model
        pname = "opencode"
    elif mode == "codex":
        provider = router.providers["codex"]
        resolved_model = current_model or provider.default_model
        pname = "codex"
    else:
        raise ValueError(f"Modo desconocido: {mode}")

    # Guard: Ollama sin daemon corriendo
    if pname == "ollama" and not await _get_daemon_ollama_models(provider):
        if local_ollama_models:
            raise ProviderUnavailableError(
                f"Ollama daemon no está corriendo. Modelos disponibles en disco: "
                f"{', '.join(local_ollama_models)}. "
                f"Iniciá el daemon con: ollama serve"
            )
        raise ProviderUnavailableError(
            "Ollama no tiene modelos. Descargá uno con: ollama pull llama3.2:1b"
        )

    use_simple = pname == "ollama" and "1b" in resolved_model
    # Re-build prompt with correct system
    system = SYSTEM_MINI if use_simple else SYSTEM_FULL

    # Streaming providers
    if hasattr(provider, "stream") and pname in {"ollama", "opencode", "codex"}:
        if HAS_RICH:
            console.print(f"[bold cyan]🧠 Jules [{pname.upper()}] ({resolved_model}) ❯ [/bold cyan]", end="")
        else:
            print(f"\n🧠 Jules [{pname.upper()}] ({resolved_model}) ❯ ", end="", flush=True)
        chunks: list[str] = []
        async for chunk in provider.stream(prompt, context, resolved_model):
            console.print(chunk, end="")
            chunks.append(chunk)
        print()
        return "".join(chunks).strip(), resolved_model, pname

    # Non-streaming (antigravity / auto cloud fallback)
    if HAS_RICH:
        with Live(Spinner("clock", text=f"[yellow] Consultando {pname.upper()}...[/yellow]"), refresh_per_second=10) as live:
            if mode == "auto":
                response, model_used, prov_used = await router.ask_with_fallback(prompt, context, task)
            else:
                response = await provider.ask(prompt, context, resolved_model)
                model_used, prov_used = resolved_model, pname
            live.update(Panel(Markdown(response), title=f"🧠 Jules [{prov_used.upper()}] ({model_used})", border_style="blue"))
        return response, model_used, prov_used
    else:
        if mode == "auto":
            response, model_used, prov_used = await router.ask_with_fallback(prompt, context, task)
        else:
            response = await provider.ask(prompt, context, resolved_model)
            model_used, prov_used = resolved_model, pname
        print(f"\n🧠 Jules [{prov_used.upper()}] ({model_used}) ❯\n{response}")
        return response, model_used, prov_used


# ══════════════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print_banner()

    # ── Config & Router ───────────────────────────────────────────────────────
    try:
        config = load_config()
        router = CognitiveRouter(config=config)
    except Exception as exc:
        console.print(f"[red]❌ Error inicializando Jules: {exc}[/red]")
        return

    # ── Discover Ollama models ────────────────────────────────────────────────
    local_ollama_models = _discover_local_ollama_models()

    # Auto-configure Ollama default model if config default isn't available
    ollama_provider = router.providers.get("ollama")
    if ollama_provider and local_ollama_models:
        if ollama_provider.default_model not in local_ollama_models:
            preferred = next(
                (m for m in local_ollama_models if "llama3.2" in m),
                local_ollama_models[0],
            )
            console.print(
                f"[yellow]⚠️  Ollama: modelo por defecto '{ollama_provider.default_model}' "
                f"no encontrado. Usando: '{preferred}'[/yellow]\n"
            )
            ollama_provider.default_model = preferred
            ollama_provider.embedding_model = preferred

    # ── Health check ──────────────────────────────────────────────────────────
    await check_health(router, local_ollama_models)

    # ── Memory Engine ─────────────────────────────────────────────────────────
    memory_engine = await _init_memory_engine(router)
    if memory_engine:
        if HAS_RICH:
            console.print(f"[green]🧠 Motor de memoria iniciado — SQLite: {SQLITE_PATH.name} | LanceDB: {LANCEDB_PATH.name}[/green]\n")
        else:
            print(f"🧠 Motor de memoria iniciado — {SQLITE_PATH}\n")
    else:
        console.print("[yellow]⚠️  Memoria desactivada en esta sesión.[/yellow]\n")

    print_help()

    # ── Session state ─────────────────────────────────────────────────────────
    mode: str = "auto"
    current_model: str | None = None
    chat_history: list[dict] = []
    sanitizer = Sanitizer()
    session_id = str(uuid.uuid4())[:8]

    # ── Chat loop ─────────────────────────────────────────────────────────────
    try:
        while True:
            prompt_label = f"Jules ({mode}) ❯ "
            if HAS_RICH:
                user_input = console.input(f"[bold green]{prompt_label}[/bold green]").strip()
            else:
                user_input = input(prompt_label).strip()

            if not user_input:
                continue

            # ── Built-in commands ─────────────────────────────────────────────
            cmd = user_input.lower()

            if cmd in {"/exit", "/quit", "/q"}:
                break

            if cmd == "/help":
                print_help()
                continue

            if cmd == "/status":
                await check_health(router, local_ollama_models)
                continue

            if cmd == "/clear":
                chat_history.clear()
                console.print("[dim]Historial de sesión limpiado.[/dim]")
                continue

            if cmd == "/history":
                if not chat_history:
                    console.print("[dim]El historial de sesión está vacío.[/dim]")
                else:
                    for msg in chat_history:
                        role_color = "green" if msg["role"] == "Usuario" else "cyan"
                        if HAS_RICH:
                            console.print(f"[{role_color}]{msg['role']}:[/{role_color}] {msg['content'][:120]}")
                        else:
                            print(f"{msg['role']}: {msg['content'][:120]}")
                print()
                continue

            if cmd.startswith("/memory"):
                parts = cmd.split()
                limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5
                await show_memory(memory_engine, limit=limit)
                continue

            if cmd.startswith("/mode "):
                new_mode = user_input.split()[1].lower()
                valid = {"auto", "ollama", "antigravity", "opencode", "codex"}
                if new_mode in valid:
                    mode = new_mode
                    current_model = None  # reset model override when switching mode
                    console.print(f"[bold cyan]🔄 Modo → {mode.upper()}[/bold cyan]")
                else:
                    console.print(f"[red]❌ Modo inválido. Opciones: {', '.join(sorted(valid))}[/red]")
                continue

            if cmd.startswith("/model "):
                new_model = user_input.split(maxsplit=1)[1].strip()
                current_model = new_model
                console.print(f"[bold cyan]🔄 Modelo → {current_model}[/bold cyan]")
                continue

            # ── Sanitizer gate ────────────────────────────────────────────────
            check = sanitizer.check(user_input)
            if not check.is_safe:
                if HAS_RICH:
                    console.print(Panel(
                        f"🔒 [bold red]ENTRADA BLOQUEADA[/bold red]\n"
                        f"Contiene información sensible: [yellow]{check.reason}[/yellow]\n"
                        f"Ningún dato fue enviado al proveedor.",
                        border_style="red",
                    ))
                else:
                    print(f"🔒 BLOQUEADO — Información sensible detectada: {check.reason}")
                continue

            # ── Build prompt ──────────────────────────────────────────────────
            use_simple = mode == "ollama" and ollama_provider and "1b" in (current_model or ollama_provider.default_model)
            system = SYSTEM_MINI if use_simple else SYSTEM_FULL
            prompt = _build_prompt(system, chat_history[-6:], user_input)

            # ── Routing + inference ───────────────────────────────────────────
            context = _build_session_context(mode, current_model or "")
            t_start = time.perf_counter()
            start_ts = datetime.now(tz=timezone.utc)

            try:
                response, model_used, prov_used = await _ask(
                    router, mode, current_model, prompt, context, local_ollama_models
                )
            except (ProviderTimeoutError, ProviderUnavailableError, ProviderError, ValueError) as exc:
                console.print(f"[bold red]❌ {exc}[/bold red]")
                continue
            except Exception as exc:
                console.print(f"[bold red]❌ Error inesperado: {exc}[/bold red]")
                log.exception("Unexpected error in chat loop")
                continue

            duration = int(time.perf_counter() - t_start)

            # ── Update in-memory history ──────────────────────────────────────
            chat_history.append({"role": "Usuario", "content": user_input})
            chat_history.append({"role": "Jules", "content": response})
            chat_history = chat_history[-12:]  # max 6 turnos

            # ── Fire-and-forget memory persistence (Módulo 6) ─────────────────
            if memory_engine and response:
                episode = _build_episode(
                    episode_id=f"{session_id}-{uuid.uuid4().hex[:8]}",
                    user_input=user_input,
                    response=response,
                    mode=mode,
                    model=model_used,
                    provider_name=prov_used,
                    duration_seconds=duration,
                    start_ts=start_ts,
                )
                await memory_engine.persist_async(episode)
                # Retorna inmediatamente — el pipeline corre en background

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        for provider in router.providers.values():
            try:
                await provider.close()
            except Exception:
                pass
        if HAS_RICH:
            console.print("\n[bold yellow]👋 Sesión cerrada. Chau.[/bold yellow]")
        else:
            print("\n👋 Sesión cerrada. Chau.")


if __name__ == "__main__":
    asyncio.run(main())
