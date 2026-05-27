import asyncio
from jules.providers.ollama import OllamaProvider
from jules.memory.models import SessionContext
from jules.sanitizer.sanitizer import Sanitizer

async def main():
    print("="*50)
    print("🧪 JULES TESTER - MÓDULOS 1, 2 Y 3")
    print("="*50)
    
    provider = OllamaProvider(timeout_seconds=30.0)
    context = SessionContext(
        project="jules-test",
        directory="/home",
        active_files=[],
        inferred_intent="testing",
        time_of_day="now"
    )
    
    try:
        if not await provider.health_check():
            print("❌ Ollama no está corriendo o llama3.2:1b no está disponible.")
            return
            
        while True:
            try:
                prompt = input("\nVos ❯ ")
                if not prompt.strip():
                    continue
                if prompt.lower() in ['exit', 'quit', 'salir']:
                    break
                    
                # Pasamos por el Módulo 1 (Sanitizer)
                sanitized = Sanitizer.check(prompt)
                if not sanitized.is_safe:
                    print(f"🔒 [Sanitizador] Bloqueado: contiene un '{sanitized.reason}'")
                    continue
                
                print("Jules ❯ ", end="", flush=True)
                # Pasamos por el Módulo 3 (OllamaProvider streaming)
                async for chunk in provider.stream(prompt, context, "llama3.2:1b"):
                    print(chunk, end="", flush=True)
                print()
                
            except EOFError:
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
    finally:
        await provider.close()
        print("\n👋 Nos vemos.")

if __name__ == "__main__":
    asyncio.run(main())
