import asyncio
from pathlib import Path
from jules.core.router import CognitiveRouter, TaskType
from jules.memory.models import SessionContext
from jules.sanitizer.sanitizer import Sanitizer

def get_test_context() -> SessionContext:
    return SessionContext(
        project="jules-router-test",
        directory=str(Path(__file__).parent),
        active_files=[],
        inferred_intent="interactive_chat",
        time_of_day="now"
    )

async def main():
    print("="*60)
    print("🧠 JULES COGNITIVE ROUTER - MÓDULO 5 (INTERACTIVE TESTER)")
    print("="*60)
    print("Este script rutea dinámicamente tu prompt al modelo óptimo")
    print("basándose en el tipo de tarea que elijas.")
    
    router = CognitiveRouter()
    context = get_test_context()
    
    print("\n💡 Comandos útiles:")
    print("  /exit - Salir de la sesión")
    
    try:
        while True:
            print("\n--- 🧭 TIPO DE TAREA ---")
            print("1. IDENTITY (Ollama local)")
            print("2. QUICK (Antigravity flash-low)")
            print("3. CODING (OpenCode low_cost)")
            print("4. REASONING (Antigravity default/pro)")
            
            choice = input("\nSeleccioná el tipo de tarea [1-4] ❯ ").strip()
            task_type = None
            if choice == "1":
                task_type = TaskType.IDENTITY
            elif choice == "2":
                task_type = TaskType.QUICK
            elif choice == "3":
                task_type = TaskType.CODING
            elif choice == "4":
                task_type = TaskType.REASONING
            elif choice.lower() == "/exit":
                break
            else:
                print("❌ Opción inválida.")
                continue

            # Para probar user_override
            override = input("Si querés forzar un override (ej: opencode:deepseek-v4) escribilo acá, o apretá Enter para ruteo automático: ").strip()
            user_override = override if override else None

            prompt = input("\nTu Prompt ❯ ").strip()
            if not prompt:
                continue
            if prompt.lower() == "/exit":
                break
                
            # Módulo 1 (Sanitizer)
            sanitized = Sanitizer.check(prompt)
            if not sanitized.is_safe:
                print(f"🔒 [Sanitizador] Bloqueado: contiene '{sanitized.reason}'")
                continue
            
            jules_prompt = (
                "[INSTRUCCIÓN DE SISTEMA: Tu nombre es Jules. Sos una capa cognitiva local-first, "
                "inteligente, directa y serena. Respondé siempre en español rioplatense (con voseo), "
                "con calma, precisión y sin rodeos innecesarios o disculpas vacías. "
                "Bajo ninguna circunstancia digas que sos un modelo de lenguaje de Google, OpenAI, "
                "DeepSeek o tu proveedor. Sos Jules. Respondé de forma directa al usuario.]\n\n"
                f"Usuario: {prompt}\n"
                "Jules:"
            )
            
            print(f"\n⚡ Ruteando consulta...")
            
            try:
                response, model_used, provider_used = await router.ask_with_fallback(
                    prompt=jules_prompt, 
                    context=context, 
                    task=task_type,
                    user_override=user_override
                )
                
                print(f"✅ Ruteo Exitoso ➔ Proveedor: [{provider_used}] | Modelo: [{model_used}]")
                print("Jules ❯", response)
                
            except Exception as e:
                print(f"\n❌ Error del Ruteador: {e}")
                
    finally:
        # Cerramos los recursos de todos los providers instanciados por el router
        for provider in router.providers.values():
            await provider.close()
        print("\n👋 Sesión terminada. Nos vemos.")

if __name__ == "__main__":
    asyncio.run(main())
