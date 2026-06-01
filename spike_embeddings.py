"""
Spike DD1 — Validación de embeddings semánticos con Ollama.

Objetivo: determinar si llama3.2:1b genera embeddings útiles para
recuperar episodios técnicos por relevancia semántica.

Ejecutar: .venv/bin/python spike_embeddings.py
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass


# ── Episodios de prueba ────────────────────────────────────────────────────────
# 5 grupos temáticos distintos. Cada query debería recuperar su grupo.

EPISODES: list[tuple[str, str]] = [
    # Grupo A — async/concurrencia
    ("async-1", "asyncio.create_task no esperaba el resultado y la tarea se cancelaba silenciosamente"),
    ("async-2", "CancelledError en background task no propagaba correctamente al caller"),
    ("async-3", "asyncio.gather con return_exceptions=True para no romper el loop principal"),

    # Grupo B — base de datos / SQLite
    ("db-1", "SQLAlchemy lazy loading lanzaba MissingGreenlet en contexto async"),
    ("db-2", "Alembic migration fallaba en SQLite por ALTER TABLE no soportado sin batch mode"),
    ("db-3", "aiosqlite connection pool se agotaba bajo carga con múltiples sesiones abiertas"),

    # Grupo C — providers / subprocess
    ("prov-1", "subprocess CLI no terminaba porque esperaba input interactivo en TTY"),
    ("prov-2", "timeout en asyncio.wait_for no mataba el proceso hijo correctamente"),
    ("prov-3", "ANSI escape codes en stdout del CLI rompían el parsing de la respuesta"),

    # Grupo D — memoria / vectores
    ("mem-1", "LanceDB schema incompatible al cambiar dimensión del vector entre sesiones"),
    ("mem-2", "vector de ceros como query devuelve resultados aleatorios en LanceDB"),
    ("mem-3", "time decay factor demasiado pequeño hacía que episodios viejos compitieran con recientes"),

    # Grupo E — sanitizador / seguridad
    ("san-1", "regex de assignment_secret generaba falsos positivos en nombres de función largos"),
    ("san-2", "Bearer token en header HTTP no se detectaba con capitalización mixta"),
    ("san-3", "private key en bloque multilinea no se detectaba si había texto antes"),
]

QUERIES: list[tuple[str, list[str]]] = [
    ("problema con tareas async que se cancelan", ["async-1", "async-2", "async-3"]),
    ("error en migración de base de datos SQLite", ["db-1", "db-2", "db-3"]),
    ("CLI subprocess no responde o timeout", ["prov-1", "prov-2", "prov-3"]),
    ("búsqueda semántica en LanceDB con vectores", ["mem-1", "mem-2", "mem-3"]),
    ("falso positivo en detección de secrets", ["san-1", "san-2", "san-3"]),
]


# ── Utilidades ─────────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k(query_vec: list[float], corpus: list[tuple[str, list[float]]], k: int = 3) -> list[tuple[str, float]]:
    scored = [(ep_id, cosine_similarity(query_vec, vec)) for ep_id, vec in corpus]
    return sorted(scored, key=lambda x: x[1], reverse=True)[:k]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    from jules.providers.ollama import OllamaProvider

    provider = OllamaProvider(timeout_seconds=60.0)

    try:
        # 1. Verificar que Ollama está corriendo
        if not await provider.health_check():
            print("❌ Ollama no está corriendo. Iniciá el daemon con: ollama serve")
            return

        # 2. Obtener dimensión real del embedding
        print("📐 Midiendo dimensión del embedding...")
        sample_vec = await provider.embed("test")
        dim = len(sample_vec)
        print(f"   Dimensión: {dim}\n")

        # 3. Generar embeddings para todos los episodios
        print(f"🔢 Generando embeddings para {len(EPISODES)} episodios...")
        corpus: list[tuple[str, list[float]]] = []
        for ep_id, text in EPISODES:
            vec = await provider.embed(text)
            corpus.append((ep_id, vec))
            print(f"   ✓ {ep_id}")

        # 4. Evaluar retrieval por cada query
        print("\n" + "═" * 60)
        print("📊 RESULTADOS DE RETRIEVAL SEMÁNTICO")
        print("═" * 60)

        hits = 0
        total = 0

        for query_text, expected_ids in QUERIES:
            query_vec = await provider.embed(query_text)
            results = top_k(query_vec, corpus, k=3)

            retrieved_ids = [r[0] for r in results]
            correct = sum(1 for r_id in retrieved_ids if r_id in expected_ids)
            hits += correct
            total += 3

            status = "✅" if correct >= 2 else ("⚠️ " if correct == 1 else "❌")
            print(f"\n{status} Query: \"{query_text}\"")
            print(f"   Esperados: {expected_ids}")
            for r_id, score in results:
                marker = "✓" if r_id in expected_ids else "✗"
                print(f"   {marker} {r_id:<10} sim={score:.4f}")

        # 5. Veredicto
        precision = hits / total
        print("\n" + "═" * 60)
        print(f"📈 Precisión@3: {hits}/{total} = {precision:.1%}")
        print("═" * 60)

        if precision >= 0.7:
            print("✅ VEREDICTO: Embeddings útiles para retrieval semántico.")
            print("   → Proceder con DD2: conectar embed() en MemoryEngine.")
        elif precision >= 0.4:
            print("⚠️  VEREDICTO: Embeddings parcialmente útiles.")
            print("   → Evaluar si un modelo más grande mejora la precisión.")
            print("   → Considerar: nomic-embed-text (modelo dedicado a embeddings).")
        else:
            print("❌ VEREDICTO: Embeddings no discriminan bien episodios técnicos.")
            print("   → llama3.2:1b no es adecuado para embeddings semánticos.")
            print("   → Alternativas: nomic-embed-text, mxbai-embed-large via Ollama.")

        print(f"\n   Dimensión del vector: {dim}")
        print(f"   Modelo usado: {provider.embedding_model}")

    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
