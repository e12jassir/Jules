import asyncio
from pathlib import Path
from jules.providers.ollama import OllamaProvider
from jules.providers.antigravity import AntigravityProvider
from jules.providers.opencode import OpenCodeProvider
from jules.providers.base import ProviderError, ProviderTimeoutError
from jules.memory.models import SessionContext
from jules.sanitizer.sanitizer import Sanitizer

def get_test_context() -> SessionContext:
    return SessionContext(
        project="jules-interactive-test",
        directory=str(Path(__file__).parent),
        active_files=[],
        inferred_intent="interactive_chat",
        time_of_day="now"
    )

async def select_provider():
    print("\n--- 🧭 SELECCIONÁ EL PROVEEDOR ---")
    print("1. 🦙 Ollama (Llama 3.2 1B - Streaming)")
    print("2. 🛸 Antigravity (agy - CLI)")
    print("3. 💻 OpenCode (DeepSeek v4 Flash - CLI)")
    print("---------------------------------")
    
    while True:
        choice = input("Selección [1-3] ❯ ").strip()
        if choice == "1":
            provider = OllamaProvider(timeout_seconds=30.0)
            model = "llama3.2:1b"
            name = "Ollama (llama3.2:1b)"
            break
        elif choice == choice == "2":
            provider = AntigravityProvider(timeout_seconds=30.0)
            model = "ignored"
            name = "Antigravity (agy)"
            break
        elif choice == choice == "3":
            provider = OpenCodeProvider(timeout_seconds=60.0)
            model = "opencode/deepseek-v4-flash-free"
            name = "OpenCode (deepseek-v4-flash)"
            break
        else:
            print("❌ Opción inválida. Elegí 1, 2 o 3.")
            
    print(f"\n⚡ Conectando con {name}...")
    if not await provider.health_check():
        print(f"⚠️  Advertencia: El health check de {name} falló. Es posible que el servicio o binario no esté disponible.")
    else:
        print(f"✅ Conexión establecida con {name}.")
        
    return provider, model, name

async def main():
    print("="*50)
    print("🧪 JULES INTERACTIVE TESTER - MÓDULOS 1, 2, 3 Y 4")
    print("="*50)
    
    provider, model, name = await select_provider()
    context = get_test_context()
    
    print("\n💡 Comandos útiles:")
    print("  /switch  - Cambiar de proveedor")
    print("  /exit    - Salir de la sesión")
    
    try:
        while True:
            try:
                user_input = input(f"\nVos [{name}] ❯ ").strip()
                if not user_input:
                    continue
                
                if user_input.lower() == "/exit":
                    break
                    
                if user_input.lower() == "/switch":
                    await provider.close()
                    provider, model, name = await select_provider()
                    continue
                
                # 🛡️ Módulo 1 (Sanitizer) - Validamos la entrada original del usuario
                sanitized = Sanitizer.check(user_input)
                if not sanitized.is_safe:
                    print(f"🔒 [Sanitizador] Bloqueado: contiene '{sanitized.reason}'")
                    continue
                
                # 🎭 Plantilla de Identidad: Le inyectamos la personalidad de Jules al prompt final
                # Esto asegura que el LLM adopte su identidad canónica y use el tono correcto.
                jules_prompt = (
                    "[INSTRUCCIÓN DE SISTEMA: Tu nombre es Jules. Sos una capa cognitiva local-first, "
                    "inteligente, directa y serena. Respondé siempre en español rioplatense (con voseo), "
                    "con calma, precisión y sin rodeos innecesarios o disculpas vacías. "
                    "Bajo ninguna circunstancia digas que sos un modelo de lenguaje de Google, OpenAI, "
                    "DeepSeek o tu proveedor. Sos Jules. Respondé de forma directa al usuario.]\n\n"
                    f"Usuario: {user_input}\n"
                    "Jules:"
                )
                
                print("Jules ❯ ", end="", flush=True)
                
                # Para Ollama usamos streaming (Módulo 3)
                if isinstance(provider, OllamaProvider):
                    async for chunk in provider.stream(jules_prompt, context, model):
                        print(chunk, end="", flush=True)
                    print()
                # Para Antigravity y OpenCode usamos ask (Módulo 4)
                else:
                    response = await provider.ask(jules_prompt, context, model)
                    print(response)
                    
            except EOFError:
                break
            except ProviderTimeoutError:
                print("\n❌ Error: El proveedor excedió el tiempo límite de espera.")
            except ProviderError as e:
                print(f"\n❌ Error de Proveedor: {e}")
            except Exception as e:
                print(f"\n❌ Error inesperado: {e}")
    finally:
        await provider.close()
        print("\n👋 Nos vemos.")

if __name__ == "__main__":
    asyncio.run(main())
