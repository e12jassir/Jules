# pyright: reportPossiblyUnboundVariable=false
"""
jules_benchmark.py — Benchmark premium de latencia para los proveedores de Jules.
Mide TTFT (Time to First Token), tiempo total de respuesta y velocidad de generación (tokens/seg).
"""

import asyncio
import time
import os
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.spinner import Spinner
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Jules imports
from jules.core.config import load_config
from jules.core.router import CognitiveRouter
from jules.memory.models import SessionContext

if HAS_RICH:
    console = Console()
else:
    class SimpleConsole:
        def print(self, *args, **kwargs):
            print(*args, **kwargs)
    console = SimpleConsole()

async def benchmark_provider(router, name, provider, model, prompt, context):
    """Ejecuta el benchmark para un proveedor específico y retorna los resultados."""
    start_time = time.perf_counter()
    ttft = None
    total_tokens = 0
    response_text = ""
    error = None

    try:
        if name == "ollama":
            # Verificar health check primero
            if not await provider.health_check():
                return {"status": "OFFLINE", "ttft": "—", "total": "—", "speed": "—", "error": "Daemon offline"}
            
        if hasattr(provider, "stream") and name in {"ollama", "opencode", "codex"}:
            stream_start = time.perf_counter()
            async for chunk in provider.stream(prompt, context, model):
                if ttft is None:
                    ttft = time.perf_counter() - stream_start
                response_text += chunk
            total_time = time.perf_counter() - stream_start
        else:
            # Non-streaming (Antigravity/Gemini)
            call_start = time.perf_counter()
            response_text = await provider.ask(prompt, context, model)
            total_time = time.perf_counter() - call_start
            ttft = total_time  # TTFT es igual al tiempo total si no hay streaming

        # Estimación simple de tokens (1 token ≈ 4 caracteres)
        total_tokens = len(response_text) / 4
        tokens_per_sec = total_tokens / total_time if total_time > 0 else 0
        
        return {
            "status": "ONLINE ✅",
            "ttft": f"{ttft:.3f}s" if ttft is not None else "—",
            "total": f"{total_time:.3f}s",
            "speed": f"{tokens_per_sec:.1f} t/s",
            "error": None
        }
    except Exception as exc:
        return {
            "status": "ERROR ❌",
            "ttft": "—",
            "total": "—",
            "speed": "—",
            "error": str(exc)
        }

async def main():
    if HAS_RICH:
        console.print(Panel(
            "[bold white]J U L E S   B E N C H M A R K[/bold white]\n[dim]Midiendo latencia, TTFT y throughput en tiempo real[/dim]",
            style="cyan",
            border_style="dim",
            padding=(1, 4)
        ))
    else:
        print("="*50)
        print("   JULES BENCHMARK — Latencia y Rendimiento")
        print("="*50)

    try:
        config = load_config()
        router = CognitiveRouter(config=config)
    except Exception as exc:
        console.print(f"[red]❌ Error cargando configuración: {exc}[/red]")
        return

    prompt = "Respondé con exactamente una frase corta de prueba sobre qué es el sistema operativo Linux."
    context = SessionContext(
        project="benchmark",
        directory=os.getcwd(),
        active_files=[],
        inferred_intent="benchmark",
        time_of_day="now",
        shell=os.environ.get("SHELL", "unknown"),
    )

    targets = []
    for pname, provider in router.providers.items():
        if pname == "ollama":
            # Llama3.2:1b o el default
            model = getattr(provider, "default_model", "llama3.2:1b")
        elif pname == "antigravity":
            model = "gemini-3.5-flash-low"
        elif pname == "opencode":
            model = "opencode/deepseek-v4-flash-free"
        elif pname == "codex":
            model = "openai/gpt-5.4-mini"
        else:
            model = "default"
        targets.append((pname, provider, model))

    results = {}
    
    if HAS_RICH:
        with Live(Spinner("clock", text="[yellow] Iniciando mediciones de latencia...[/yellow]"), refresh_per_second=10) as live:
            for name, provider, model in targets:
                live.update(Spinner("dots", text=f"[yellow] Midiendo latencia en [bold]{name.upper()}[/bold] ({model})...[/yellow]"))
                results[name] = await benchmark_provider(router, name, provider, model, prompt, context)
            
            # Construir tabla final
            table = Table(title="📊 Resultados del Benchmark", border_style="dim")
            table.add_column("Proveedor", style="bold cyan")
            table.add_column("Modelo de prueba", style="dim")
            table.add_column("Estado")
            table.add_column("TTFT (Time to First Token)", justify="right", style="green")
            table.add_column("Tiempo Total", justify="right", style="bold yellow")
            table.add_column("Velocidad Est.", justify="right", style="magenta")

            for name, provider, model in targets:
                res = results[name]
                table.add_row(
                    name.upper(),
                    model,
                    res["status"],
                    res["ttft"],
                    res["total"],
                    res["speed"]
                )
            
            live.update(table)
    else:
        for name, provider, model in targets:
            print(f"⌛ Midiendo {name.upper()} ({model})...")
            results[name] = await benchmark_provider(router, name, provider, model, prompt, context)
            res = results[name]
            print(f"   ↳ Estado: {res['status']} | TTFT: {res['ttft']} | Total: {res['total']} | Velocidad: {res['speed']}")
            if res["error"]:
                print(f"   ⚠️ Error: {res['error']}")
        print("\nBenchmark finalizado.")

if __name__ == "__main__":
    asyncio.run(main())
