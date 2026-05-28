import asyncio
from pathlib import Path
from jules.providers.antigravity import AntigravityProvider
from jules.providers.opencode import OpenCodeProvider
from jules.providers.base import ProviderError, ProviderTimeoutError
from jules.memory.models import SessionContext

def get_test_context() -> SessionContext:
    return SessionContext(
        project="jules-manual-test",
        directory=str(Path(__file__).parent),
        active_files=[],
        inferred_intent="manual_testing",
        time_of_day="now"
    )

async def test_antigravity():
    print("\n--- 🛸 PROBANDO ANTIGRAVITY PROVIDER (agy) ---")
    provider = AntigravityProvider(timeout_seconds=10.0)
    context = get_test_context()
    try:
        if not await provider.health_check():
            print("❌ Antigravity CLI (agy) no está disponible en el PATH.")
            return
        
        prompt = "Explain gravity in one sentence."
        print(f"Pregunta: \"{prompt}\"")
        response = await provider.ask(prompt, context, model="ignored")
        print(f"Respuesta ❯ {response}")
    except ProviderError as e:
        print(f"❌ Error del Proveedor: {e}")
    finally:
        await provider.close()

async def test_opencode():
    print("\n--- 💻 PROBANDO OPENCODE PROVIDER (opencode) ---")
    provider = OpenCodeProvider(timeout_seconds=30.0)
    context = get_test_context()
    model = "opencode/deepseek-v4-flash-free"
    try:
        if not await provider.health_check():
            print("❌ OpenCode CLI (opencode) no está disponible en el PATH.")
            return
        
        prompt = "Reply with exactly one word: Jules"
        print(f"Pregunta: \"{prompt}\" (usando {model})")
        response = await provider.ask(prompt, context, model=model)
        print(f"Respuesta ❯ {response}")
    except ProviderError as e:
        print(f"❌ Error del Proveedor: {e}")
    finally:
        await provider.close()

async def test_security_guards():
    print("\n--- 🛡️ PROBANDO GUARDS DE SEGURIDAD (Argument Injection) ---")
    context = get_test_context()
    
    # 1. Antigravity prompt startswith("-") guard
    agy_provider = AntigravityProvider()
    try:
        print("Intentando inyectar flag en Antigravity prompt...")
        await agy_provider.ask("-v", context, "ignored")
    except ProviderError as e:
        print(f"🛡️ Bloqueado correctamente: {e}")
        
    # 2. OpenCode model regex guard
    opencode_provider = OpenCodeProvider()
    try:
        print("Intentando inyectar model malicioso en OpenCode...")
        await opencode_provider.ask("Hola", context, "invalid_provider/model --evil-flag")
    except ProviderError as e:
        print(f"🛡️ Bloqueado correctamente: {e}")

async def main():
    print("🧪 JULES TESTER - MÓDULO 4: PROVEEDORES EXTERNOS")
    print("="*60)
    await test_antigravity()
    await test_opencode()
    await test_security_guards()
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
