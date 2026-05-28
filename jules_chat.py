import asyncio
import sys
import re
from pathlib import Path

# Try to import rich for gorgeous aesthetics, fallback to plain text if not installed
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.table import Table
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from jules.core.config import load_config
from jules.core.router import CognitiveRouter, TaskType
from jules.memory.models import SessionContext
from jules.sanitizer.sanitizer import Sanitizer
from jules.providers.ollama import OllamaProvider
from jules.providers.opencode import OpenCodeProvider
from jules.providers.codex import CodexProvider
from jules.providers.base import ProviderError, ProviderTimeoutError, ProviderUnavailableError

# Set up console
if HAS_RICH:
    console = Console()
else:
    class SimpleConsole:
        def print(self, *args, **kwargs):
            text = str(args[0]) if args else ""
            clean_text = re.sub(r'\[/?\w+.*?\]', '', text)
            print(clean_text, *args[1:], **kwargs)
        def input(self, prompt_text):
            clean_prompt = re.sub(r'\[/?\w+.*?\]', '', prompt_text)
            return input(clean_prompt)
    console = SimpleConsole()

def print_banner():
    banner = """
 ██████╗██╗   ██╗██╗     ███████╗███████╗
   ██╔══╝██║   ██║██║     ██╔════╝██╔════╝
   ██║   ██║   ██║██║     █████╗  ███████╗
   ██║   ██║   ██║██║     ██╔══╝  ╚════██║
 ╚██████╗╚██████╔╝███████╗███████╗███████║
  ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝
 🧠 CAPA COGNITIVA LOCAL-FIRST — INTERACTIVE SANDBOX
    """
    if HAS_RICH:
        console.print(Panel(banner.strip(), style="bold cyan", border_style="cyan"))
    else:
        print("=" * 60)
        print(banner.strip())
        print("=" * 60)

async def get_available_ollama_models(provider: OllamaProvider) -> list[str]:
    try:
        session = provider._get_session()
        async with session.get(f"{provider.base_url}/api/tags", timeout=5) as response:
            if response.status == 200:
                payload = await response.json()
                return [m.get("name") for m in payload.get("models", []) if m.get("name")]
    except Exception:
        pass
    return []

async def check_health(router: CognitiveRouter):
    """Checks and displays health status for all configured providers."""
    if HAS_RICH:
        table = Table(title="🤖 ESTADO DE LOS PROVEEDORES", border_style="dim")
        table.add_column("Proveedor", style="bold")
        table.add_column("Modelo Configurado", style="cyan")
        table.add_column("Estado", style="bold")
        
        for name, provider in router.providers.items():
            try:
                healthy = await provider.health_check()
                if healthy:
                    if name == "ollama":
                        models = await get_available_ollama_models(provider)
                        if not models:
                            status = "[yellow]ONLINE (Sin modelos) ⚠️[/yellow]"
                        else:
                            status = "[green]ONLINE[/green] ✅"
                    else:
                        status = "[green]ONLINE[/green] ✅"
                else:
                    status = "[red]OFFLINE[/red] ❌"
            except Exception:
                status = "[red]OFFLINE[/red] ❌"
                
            # Get models
            if name == "ollama":
                model_str = provider.default_model
            elif name == "antigravity":
                model_str = ", ".join(provider._prepared_models) or "Ninguno"
            elif name == "codex":
                model_str = provider.default_model
            else:
                model_str = "openai/gpt-5.4-mini-fast"
                
            table.add_row(name.capitalize(), model_str, status)
        console.print(table)
        console.print()
    else:
        print("\n🤖 ESTADO DE LOS PROVEEDORES:")
        for name, provider in router.providers.items():
            try:
                healthy = await provider.health_check()
                if healthy:
                    if name == "ollama":
                        models = await get_available_ollama_models(provider)
                        status = "ONLINE (Sin modelos) ⚠️" if not models else "ONLINE ✅"
                    else:
                        status = "ONLINE ✅"
                else:
                    status = "OFFLINE ❌"
            except Exception:
                status = "OFFLINE ❌"
            print(f"  - {name.capitalize()}: {status}")
        print()

def get_session_context() -> SessionContext:
    return SessionContext(
        project="jules-interactive-sandbox",
        directory=str(Path(__file__).parent),
        active_files=[],
        inferred_intent="sandbox_chat",
        time_of_day="now"
    )

async def main():
    print_banner()
    
    # 1. Initialize configuration and router
    try:
        config = load_config()
        router = CognitiveRouter(config=config)
    except Exception as e:
        if HAS_RICH:
            console.print(f"[red]❌ Error inicializando el router o la configuración: {e}[/red]")
        else:
            print(f"❌ Error inicializando el router o la configuración: {e}")
        return

    # 2. Check and display health status
    await check_health(router)
    
    context = get_session_context()
    mode = "auto"  # Can be "auto", "ollama", "antigravity", "opencode"
    
    # Dynamically select Ollama model if default is not available
    ollama_provider = router.providers.get("ollama")
    available_ollama_models = []
    if ollama_provider:
        available_ollama_models = await get_available_ollama_models(ollama_provider)
        if available_ollama_models:
            if ollama_provider.default_model not in available_ollama_models:
                # Try to find a partial match (e.g. any llama3.2), otherwise use first available
                matching = [m for m in available_ollama_models if "llama3.2" in m.lower()]
                chosen = matching[0] if matching else available_ollama_models[0]
                
                old_default = ollama_provider.default_model
                ollama_provider.default_model = chosen
                ollama_provider.embedding_model = chosen
                
                if HAS_RICH:
                    console.print(f"[bold yellow]⚠️  Ollama: Modelo '{old_default}' no encontrado. Usando tu modelo local: '{chosen}'[/bold yellow]\n")
                else:
                    print(f"⚠️  Ollama: Modelo '{old_default}' no encontrado. Usando tu modelo local: '{chosen}'\n")

    if HAS_RICH:
        console.print("[bold yellow]💡 Comandos especiales en el chat:[/bold yellow]")
        console.print("  [bold cyan]/mode auto[/bold cyan]        ➔ Usar el Cognitive Router dinámico (decide el mejor cerebro)")
        console.print("  [bold cyan]/mode ollama[/bold cyan]      ➔ Forzar uso de Ollama local (streaming)")
        console.print("  [bold cyan]/mode antigravity[/bold cyan] ➔ Forzar uso de Antigravity (Gemini)")
        console.print("  [bold cyan]/mode opencode[/bold cyan]    ➔ Forzar uso de OpenCode (DeepSeek)")
        console.print("  [bold cyan]/mode codex[/bold cyan]       ➔ Forzar uso de Codex (GPT-5.4)")
        console.print("  [bold cyan]/status[/bold cyan]           ➔ Mostrar el panel de estado de proveedores")
        console.print("  [bold cyan]/exit[/bold cyan]             ➔ Finalizar el chat")
    else:
        print("💡 Comandos especiales en el chat:")
        print("  /mode auto        ➔ Usar el Cognitive Router dinámico")
        print("  /mode ollama      ➔ Forzar uso de Ollama local")
        print("  /mode antigravity ➔ Forzar uso de Antigravity")
        print("  /mode opencode    ➔ Forzar uso de OpenCode")
        print("  /mode codex       ➔ Forzar uso de Codex")
        print("  /status           ➔ Mostrar el panel de estado de proveedores")
        print("  /exit             ➔ Finalizar el chat")
        
    print()

    # System prompt adaptativo: simplificado para modelos chicos, completo para grandes
    system_prompt_complex = (
        "[INSTRUCCIÓN DE SISTEMA: Tu nombre es Jules. Sos una capa cognitiva local-first, "
        "inteligente, directa y serena. Respondé siempre en español rioplatense (con voseo), "
        "con calma, precisión y sin rodeos innecesarios o disculpas vacías. "
        "Bajo ninguna circunstancia digas que sos un modelo de Google, OpenAI, "
        "DeepSeek o tu proveedor. Sos Jules. Respondé de forma directa.]"
    )
    system_prompt_simple = "[INSTRUCCIÓN: Sos Jules. Respondé conciso en español rioplatense (voseo). No digas que sos una IA.]"

    # Historial de conversación en memoria RAM (libreta)
    chat_history = []

    try:
        while True:
            # 1. Prompt input
            prompt_style = f"Jules ({mode}) ❯ "
            if HAS_RICH:
                user_input = console.input(f"[bold green]{prompt_style}[/bold green]").strip()
            else:
                user_input = console.input(prompt_style).strip()
                
            if not user_input:
                continue
                
            # 2. Check commands
            if user_input.lower() == "/exit":
                break
            elif user_input.lower() == "/status":
                await check_health(router)
                # Re-fetch models
                if ollama_provider:
                    available_ollama_models = await get_available_ollama_models(ollama_provider)
                continue
            elif user_input.lower().startswith("/mode "):
                new_mode = user_input.split(" ")[1].lower()
                if new_mode in ["auto", "ollama", "antigravity", "opencode", "codex"]:
                    mode = new_mode
                    if HAS_RICH:
                        console.print(f"[bold cyan]🔄 Modo cambiado a: {mode.upper()}[/bold cyan]")
                    else:
                        print(f"🔄 Modo cambiado a: {mode.upper()}")
                else:
                    if HAS_RICH:
                        console.print(f"[red]❌ Modo inválido. Opciones: auto, ollama, antigravity, opencode, codex[/red]")
                    else:
                        print("❌ Modo inválido. Opciones: auto, ollama, antigravity, opencode, codex")
                continue

            # 3. Módulo 1 (Sanitizer) protection
            sanitized = Sanitizer.check(user_input)
            if not sanitized.is_safe:
                if HAS_RICH:
                    console.print(Panel(f"🔒 [bold red]ENTRADA BLOQUEADA POR SEGURIDAD[/bold red]\nContiene información sensible: [yellow]{sanitized.reason}[/yellow]\nNingún dato fue expuesto.", border_style="red"))
                else:
                    print(f"🔒 ENTRADA BLOQUEADA: Contiene información sensible ({sanitized.reason})")
                continue

            # Assemble full prompt with identity instruction and memory
            current_sys_prompt = system_prompt_complex
            if mode == "ollama" and ollama_provider and "1b" in ollama_provider.default_model.lower():
                current_sys_prompt = system_prompt_simple
                
            history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            if history_text:
                full_prompt = f"{current_sys_prompt}\n\n[CONTEXTO RECIENTE]\n{history_text}\n\nUsuario: {user_input}\nJules:"
            else:
                full_prompt = f"{current_sys_prompt}\n\nUsuario: {user_input}\nJules:"

            # Guardamos lo que dijo el usuario
            chat_history.append({"role": "Usuario", "content": user_input})
            # Limitamos el historial a los últimos 6 mensajes para no saturar contextos largos
            chat_history = chat_history[-6:]

            # 4. Routing and execution
            if HAS_RICH:
                console.print("[dim italic]Jules está pensando...[/dim italic]")
                
            try:
                # Mode A: Automatic routing
                if mode == "auto":
                    # Ingest task type based on prompt keywords for demonstration
                    task = TaskType.QUICK
                    if any(kw in user_input.lower() for kw in ["code", "código", "python", "clase", "def ", "function", "escribí"]):
                        task = TaskType.CODING
                    elif any(kw in user_input.lower() for kw in ["quién sos", "identidad", "jules", "tu nombre"]):
                        task = TaskType.IDENTITY

                    if HAS_RICH:
                        with Live(Spinner("dots", text="[cyan] Ruteando dinámicamente...[/cyan]"), refresh_per_second=10) as live:
                            # Let router determine best provider/model
                            provider, resolved_model = router.route(task)
                            live.update(f"[cyan] Ruteando ➔ [{provider.name.upper()}] usando [{resolved_model}][/cyan]")
                            await asyncio.sleep(0.5)  # Quick smooth visual transition
                    else:
                        provider, resolved_model = router.route(task)
                        print(f"➔ Ruteador seleccionó: {provider.name.upper()} ({resolved_model})")

                    # Execute ask with fallback
                    if provider.name == "ollama":
                        # If Ollama has no models, we block and explain to avoid HTTP 404
                        if not available_ollama_models:
                            msg = (
                                "❌ [bold red]Ollama local no tiene ningún modelo descargado.[/bold red]\n"
                                "Para poder usar Ollama, abrí otra terminal y descargá el modelo más liviano corriendo:\n"
                                "➔ [bold green]ollama pull qwen2.5:0.5b[/bold green] (solo ~397 MB) o [bold green]ollama pull llama3.2:1b[/bold green]"
                            )
                            if HAS_RICH:
                                console.print(Panel(msg, border_style="red"))
                            else:
                                print(msg.replace("[bold red]", "").replace("[/bold red]", "").replace("[bold green]", "").replace("[/bold green]", "").replace("➔ ", ""))
                            continue

                        # Ollama supports streaming
                        if HAS_RICH:
                            console.print("[bold cyan]Jules ❯ [/bold cyan]", end="")
                            full_response = ""
                            async for chunk in provider.stream(full_prompt, context, resolved_model):
                                console.print(chunk, end="")
                                full_response += chunk
                            console.print()
                        else:
                            print("Jules ❯ ", end="", flush=True)
                            full_response = ""
                            async for chunk in provider.stream(full_prompt, context, resolved_model):
                                print(chunk, end="", flush=True)
                                full_response += chunk
                            print()
                        chat_history.append({"role": "Jules", "content": full_response.strip()})
                    else:
                        # Cloud provider execution with spinner
                        if HAS_RICH:
                            with Live(Spinner("clock", text="[yellow] Consultando API en la nube...[/yellow]"), refresh_per_second=10) as live:
                                response, model_used, provider_used = await router.ask_with_fallback(full_prompt, context, task)
                                live.update(Panel(Markdown(response), title=f"🧠 Jules ➔ [{provider_used.upper()}] ({model_used})", border_style="blue"))
                        else:
                            response, model_used, provider_used = await router.ask_with_fallback(full_prompt, context, task)
                            print(f"\n🧠 Jules [{provider_used.upper()}] ({model_used}) ❯\n{response}")
                        chat_history.append({"role": "Jules", "content": response})

                # Mode B: Forced Ollama
                elif mode == "ollama":
                    # If Ollama has no models, we block and explain to avoid HTTP 404
                    if not available_ollama_models:
                        msg = (
                            "❌ [bold red]Ollama local no tiene ningún modelo descargado.[/bold red]\n"
                            "Para poder usar Ollama, abrí otra terminal y descargá el modelo más liviano corriendo:\n"
                            "➔ [bold green]ollama pull qwen2.5:0.5b[/bold green] (solo ~397 MB) o [bold green]ollama pull llama3.2:1b[/bold green]"
                        )
                        if HAS_RICH:
                            console.print(Panel(msg, border_style="red"))
                        else:
                            print(msg.replace("[bold red]", "").replace("[/bold red]", "").replace("[bold green]", "").replace("[/bold green]", "").replace("➔ ", ""))
                        continue

                    provider = router.providers["ollama"]
                    if HAS_RICH:
                        console.print("[bold cyan]Jules (Ollama) ❯ [/bold cyan]", end="")
                        full_response = ""
                        async for chunk in provider.stream(full_prompt, context, provider.default_model):
                            console.print(chunk, end="")
                            full_response += chunk
                        console.print()
                    else:
                        print("Jules (Ollama) ❯ ", end="", flush=True)
                        full_response = ""
                        async for chunk in provider.stream(full_prompt, context, provider.default_model):
                            print(chunk, end="", flush=True)
                            full_response += chunk
                        print()
                    chat_history.append({"role": "Jules", "content": full_response.strip()})

                # Mode C: Forced Antigravity
                elif mode == "antigravity":
                    provider = router.providers["antigravity"]
                    model = "gemini-3.5-flash-low"  # Standard default prepared model
                    if HAS_RICH:
                        with Live(Spinner("clock", text="[yellow] Invocando Antigravity CLI...[/yellow]"), refresh_per_second=10) as live:
                            response = await provider.ask(full_prompt, context, model)
                            live.update(Panel(Markdown(response), title="🧠 Jules [ANTIGRAVITY]", border_style="magenta"))
                    else:
                        response = await provider.ask(full_prompt, context, model)
                        print(f"\n🧠 Jules [ANTIGRAVITY] ❯\n{response}")
                    chat_history.append({"role": "Jules", "content": response})

                # Mode D: Forced OpenCode o Codex (Ambos soportan streaming ahora)
                elif mode in ["opencode", "codex"]:
                    provider = router.providers[mode]
                    model = provider.default_model if mode == "codex" else "openai/gpt-5.4-mini-fast"
                    
                    if HAS_RICH:
                        console.print(f"[bold cyan]🧠 Jules [{mode.upper()}] ❯ [/bold cyan]", end="")
                        full_response = ""
                        async for chunk in provider.stream(full_prompt, context, model):
                            console.print(chunk, end="")
                            full_response += chunk
                        console.print()
                    else:
                        print(f"\n🧠 Jules [{mode.upper()}] ❯ ", end="", flush=True)
                        full_response = ""
                        async for chunk in provider.stream(full_prompt, context, model):
                            print(chunk, end="", flush=True)
                            full_response += chunk
                        print()
                        
                    chat_history.append({"role": "Jules", "content": full_response.strip()})

            except ProviderTimeoutError:
                if HAS_RICH:
                    console.print("[bold red]❌ Error: La consulta excedió el tiempo límite de espera (timeout).[/bold red]")
                else:
                    print("❌ Error: La consulta excedió el tiempo límite de espera (timeout).")
            except ProviderUnavailableError as e:
                if HAS_RICH:
                    console.print(f"[bold red]❌ Proveedor no disponible: {e}[/bold red]")
                else:
                    print(f"❌ Proveedor no disponible: {e}")
            except ProviderError as e:
                if HAS_RICH:
                    console.print(f"[bold red]❌ Error de proveedor: {e}[/bold red]")
                else:
                    print(f"❌ Error de proveedor: {e}")
            except Exception as e:
                if HAS_RICH:
                    console.print(f"[bold red]❌ Error inesperado: {e}[/bold red]")
                else:
                    print(f"❌ Error inesperado: {e}")

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        # Resource cleanup
        for provider in router.providers.values():
            await provider.close()
        if HAS_RICH:
            console.print("\n[bold yellow]👋 Sesión interactiva finalizada. Chau, bro.[/bold yellow]")
        else:
            print("\n👋 Sesión interactiva finalizada. Chau, bro.")

if __name__ == "__main__":
    asyncio.run(main())
