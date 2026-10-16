# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from typing import Any

try:
    import click  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class _Context:
        invoked_subcommand: str | None = None

    class _Group:
        def __init__(self, callback):
            self.callback = callback
            self.commands = {}

        def command(self, *_args, **_kwargs):
            def register(func):
                self.commands[func.__name__] = func
                return func
            return register

        def group(self, *_args, **_kwargs):
            def register(func):
                subgroup = _Group(func)
                self.commands[func.__name__] = subgroup
                return subgroup
            return register

        def __call__(self):
            args = sys.argv[1:]
            if args[:1] == ["doctor"]:
                self.commands["doctor"]("--json" in args)
                return
            if args[:1] == ["protocol"]:
                self.commands["protocol"]()
                return
            self.callback(_Context())

    class _ClickStub:
        @staticmethod
        def group(*_args, **_kwargs):
            return lambda func: _Group(func)

        @staticmethod
        def option(*_args, **_kwargs):
            return lambda func: func

        @staticmethod
        def argument(*_args, **_kwargs):
            return lambda func: func

        @staticmethod
        def pass_context(func):
            return func

        @staticmethod
        def echo(message, *args, **kwargs):
            print(message, file=sys.stderr if kwargs.get("err") else sys.stdout)

    click = _ClickStub()  # type: ignore[assignment]


from dataclasses import dataclass


@dataclass
class _FallbackCheck:
    name: str
    status: str
    message: str


@dataclass
class _FallbackReport:
    results: list[_FallbackCheck]
    exit_code: int


def _run_doctor_checks():
    return _FallbackReport(
        results=[_FallbackCheck("doctor", "fail", "Módulo jules.platform.doctor no disponible")],
        exit_code=1
    )


# Module-level aliases so tests can monkeypatch cli_main.run_all_checks and cli_main.gate
try:
    from jules.platform.doctor import run_all_checks  # type: ignore[assignment]
except Exception:
    run_all_checks = _run_doctor_checks  # type: ignore[assignment]

try:
    from jules.core.config import PermissionsConfig, load_config
    from jules.core.permissions import PermissionGate
    gate = PermissionGate(load_config().permissions)
except Exception:
    class _NoopGate:
        async def check(self, *_args, **_kwargs) -> None:
            pass
    gate = _NoopGate()  # type: ignore[assignment]


def _run_async(coro: Any) -> Any:
    """Safely execute an asynchronous coroutine from synchronous Click commands."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    """Jules — capa cognitiva persistente."""
    if ctx.invoked_subcommand is not None:
        return
    from jules.cli.app import JulesApp  # type: ignore[import-not-found]

    JulesApp().run(inline=False)


@cli.command()  # type: ignore[attr-defined]
def protocol() -> None:
    """Headless NDJSON protocol server for non-Textual frontends (e.g. jules-tui)."""
    from jules.cli.protocol import main as run_protocol

    run_protocol()


@cli.command()  # type: ignore[attr-defined]
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def doctor(as_json: bool) -> None:
    """Diagnóstico de salud del entorno."""
    report = run_all_checks()
    if as_json:
        click.echo(json.dumps({
            "results": [
                {"name": r.name, "status": r.status, "message": r.message}
                for r in report.results
            ],
            "exit_code": report.exit_code,
        }, indent=2))
        sys.exit(report.exit_code)

    from rich.console import Console  # type: ignore[import-not-found]
    from rich.table import Table  # type: ignore[import-not-found]

    console = Console()
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1, 0, 0))
    table.add_column("status", width=2)
    table.add_column("name", style="bold", width=15)
    table.add_column("message")
    for result in report.results:
        if result.status == "ok":
            symbol = "[green]✓[/green]"
        elif result.status == "fail":
            symbol = "[red]✗[/red]"
        else:
            symbol = "[yellow]⚠[/yellow]"
        table.add_row(symbol, result.name, result.message)

    console.print("──────────────────────────────────────")
    console.print(table)
    console.print("──────────────────────────────────────")
    problems = sum(1 for result in report.results if result.status in ("fail", "warn"))
    if problems == 0:
        console.print("[green]Entorno sano. Todos los chequeos pasaron con éxito.[/green]")
    else:
        console.print(f"[yellow]{problems} problema(s) detectado(s). Jules opera en modo parcialmente degradado.[/yellow]")
    sys.exit(report.exit_code)


# ---------------------------------------------------------------------------
# Daemon Group Commands
# ---------------------------------------------------------------------------


@cli.group()  # type: ignore[attr-defined]
def daemon() -> None:
    """Gestión del servicio residente de Jules."""
    pass


@daemon.command(name="start")  # type: ignore[attr-defined]
@click.option("--socket", "socket_path", default=None, help="Ruta personalizada del socket IPC")
@click.option("--state", "state_path", default=None, help="Ruta personalizada del archivo de estado")
def daemon_start(socket_path: str | None, state_path: str | None) -> None:
    """Iniciar el daemon residente de Jules."""
    from jules.daemon.service import JulesDaemon

    daemon_obj = JulesDaemon(
        socket_path=socket_path,
        state_path=state_path,
    )
    click.echo(f"Iniciando Jules daemon en socket: {daemon_obj.socket_path}")
    try:
        _run_async(daemon_obj.run_forever())
    except (KeyboardInterrupt, asyncio.CancelledError):
        click.echo("\nDaemon detenido por el usuario.")
    except Exception as exc:
        click.echo(f"Error fatal en daemon: {exc}", err=True)
        sys.exit(1)


@daemon.command(name="status")  # type: ignore[attr-defined]
@click.option("--socket", "socket_path", default=None, help="Ruta personalizada del socket IPC")
@click.option("--json", "as_json", is_flag=True, help="Mostrar estado en formato JSON")
def daemon_status(socket_path: str | None, as_json: bool) -> None:
    """Consultar el estado del daemon residente."""
    from jules.daemon.ipc import IPCClient, IPCConnectionError, IPCError

    client = IPCClient(socket_path=socket_path)

    async def _fetch():
        return await client.get_status()

    try:
        status_data = _run_async(_fetch())
    except (IPCConnectionError, FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        if as_json:
            click.echo(json.dumps({"status": "offline", "health": "stopped", "error": str(exc)}, indent=2))
        else:
            click.echo("Jules daemon is not running (offline). Start it with 'jules daemon start'.", err=True)
        sys.exit(1)
    except Exception as exc:
        if as_json:
            click.echo(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            click.echo(f"Error consultando daemon: {exc}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(status_data, indent=2))
        return

    icon = status_data.get("icon", "🌹")
    state = status_data.get("state", "UNKNOWN")
    health = status_data.get("health", "unknown")
    model = status_data.get("active_model") or "ninguno"
    project = status_data.get("active_project") or "ninguno"
    last_event = status_data.get("last_event") or "ninguno"

    click.echo("──────────────────────────────────────")
    click.echo(f" Estado Jules Daemon: {icon} {state} ({health})")
    click.echo(f" Modelo Activo:       {model}")
    click.echo(f" Proyecto Activo:     {project}")
    click.echo(f" Último Evento:       {last_event}")
    click.echo("──────────────────────────────────────")


@daemon.command(name="install")  # type: ignore[attr-defined]
@click.option("--path", "target_dir", default=None, help="Directorio destino para jules.service")
def daemon_install(target_dir: str | None) -> None:
    """Instalar unidad systemd --user para Jules."""
    from jules.daemon.service import install_systemd_user_service

    service_path = install_systemd_user_service(target_dir=target_dir)
    click.echo(f"✓ Unidad systemd instalada en: {service_path}")
    click.echo("\nPara activar e iniciar el servicio ahora:")
    click.echo("  systemctl --user daemon-reload")
    click.echo("  systemctl --user enable --now jules.service")
    click.echo("\nNota para distribuciones sin systemd (Alpine/Void per JULES.md):")
    click.echo("  Revise los comentarios en el archivo jules.service para OpenRC o runit.")


# ---------------------------------------------------------------------------
# Quick Ask Command
# ---------------------------------------------------------------------------


@cli.command(name="ask")  # type: ignore[attr-defined]
@click.argument("text")
@click.option("--session", "session_id", default="cli_ask", help="ID de sesión")
@click.option("--socket", "socket_path", default=None, help="Ruta personalizada del socket IPC")
def ask(text: str, session_id: str, socket_path: str | None) -> None:
    """Hacer una consulta rápida a Jules a través del daemon."""
    from jules.daemon.ipc import IPCClient, IPCConnectionError, IPCError
    from jules.providers.base import ContentEvent, ThoughtEvent

    client = IPCClient(socket_path=socket_path)

    async def _stream():
        async for chunk in client.stream_query(text=text, session_id=session_id):
            if isinstance(chunk, ContentEvent):
                click.echo(chunk.content, nl=False)

    try:
        _run_async(_stream())
        click.echo()
    except (IPCConnectionError, FileNotFoundError, ConnectionRefusedError, OSError):
        click.echo(
            "Daemon offline. Jules daemon is not running. "
            "Start it with 'jules daemon start' or run 'jules' for interactive mode.",
            err=True,
        )
        sys.exit(1)
    except IPCError as exc:
        click.echo(f"\nError en consulta IPC: {exc}", err=True)
        sys.exit(1)


@cli.command(name="voice")  # type: ignore[attr-defined]
@click.option("--once", is_flag=True, help="Grabar una sola frase y salir tras responder")
@click.option("--socket", "socket_path", default=None, help="Ruta personalizada del socket IPC")
def voice(once: bool, socket_path: str | None) -> None:
    """Conversar por voz en tiempo real con Jules (VAD + Whisper + Streaming TTS)."""
    from jules.daemon.ipc import IPCClient, IPCConnectionError
    from jules.providers.base import ContentEvent
    from jules.voice.listener import AudioListener
    from jules.voice.speaker import (
        EdgeTTSBackend,
        ElevenLabsTTSBackend,
        FallbackTTSBackend,
        KokoroTTSBackend,
        SentenceStreamChunker,
        VoiceSpeaker,
    )
    from jules.voice.transcriber import LocalTranscriber

    client = IPCClient(socket_path=socket_path)

    async def _run_voice():
        from jules.voice.listener import VADDetector
        listener = AudioListener(vad=VADDetector(speech_threshold=0.045, silence_timeout_ms=650.0))
        transcriber = LocalTranscriber(model_size="base", compute_type="int8", language="es")
        speaker = VoiceSpeaker()
        speaker.connect_listener(listener)
        chunker = SentenceStreamChunker()

        active_backend = (
            speaker.backend.primary
            if isinstance(speaker.backend, FallbackTTSBackend)
            else speaker.backend
        )
        backend_label = (
            "ElevenLabs Neural TTS"
            if isinstance(active_backend, ElevenLabsTTSBackend)
            else (
                "Edge TTS (Azure Neural + Kokoro Fallback)"
                if isinstance(speaker.backend, FallbackTTSBackend)
                else (
                    "Edge TTS (Azure Neural)"
                    if isinstance(active_backend, EdgeTTSBackend)
                    else (
                        "Kokoro Neural TTS"
                        if isinstance(active_backend, KokoroTTSBackend)
                        else "TTS"
                    )
                )
            )
        )
        click.echo(f"🎙️  Modo Voz Activado (VAD + Whisper INT8 + {backend_label}).")
        click.echo("Habla cuando quieras (detecta silencio automático). Presiona Ctrl+C para salir.\n")

        chat_history: list[tuple[str, str]] = []

        while True:
            click.echo("👂 Escuchando...")
            audio_bytes = await listener.record_phrase()
            # Require at least 0.5s of audio (16000 samples * 2 bytes)
            if not audio_bytes or len(audio_bytes) < 16000:
                continue

            click.echo("🧠 Transcribiendo...")
            res = await transcriber.transcribe(audio_bytes)
            user_text = res.text.strip()
            # Ignore empty, single-character, or Whisper repetition artifacts
            if not user_text or len(user_text) < 3 or user_text.lower().startswith("in all that"):
                continue

            click.echo(f"👤 Tú: {user_text}")
            if not res.is_safe:
                click.echo(f"⚠️  [Sanitizer]: Bloqueado por seguridad ({res.reason}).")
                continue

            click.echo("🌹 Jules: ", nl=False)

            assistant_parts: list[str] = []

            async def _token_generator():
                async for chunk in client.stream_query(
                    text=user_text,
                    session_id="voice_session",
                    chat_history=chat_history[-10:],
                ):
                    if isinstance(chunk, ContentEvent):
                        click.echo(chunk.content, nl=False)
                        assistant_parts.append(chunk.content)
                        yield chunk.content

            sentence_stream = chunker.stream(_token_generator())
            await speaker.speak_stream(sentence_stream)
            click.echo("\n")

            assistant_reply = "".join(assistant_parts).strip()
            if assistant_reply:
                chat_history.append(("user", user_text))
                chat_history.append(("assistant", assistant_reply))

            if once:
                break

    try:
        _run_async(_run_voice())
    except (KeyboardInterrupt, asyncio.CancelledError):
        click.echo("\nModo voz finalizado.")
    except (IPCConnectionError, FileNotFoundError, ConnectionRefusedError, OSError):
        click.echo(
            "Daemon offline. Inicia el servicio con 'jules daemon start' antes de usar la voz.",
            err=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    cli()  # type: ignore[call-arg]
