# ROADMAP.md
## Versión 1.3
## Plan de Construcción — Jules

> **Principio:** Cada módulo debe funcionar y estar testeado antes de construir el siguiente.  
> Un módulo roto que avanza es deuda que mata el proyecto.

---

## STACK DE DESARROLLO

| Tarea | Modelo |
|---|---|
| Módulos críticos | GPT 5.5 en OpenCode |
| Desarrollo diario | GPT 5.4 en OpenCode |
| Boilerplate y mecánico | Deepseek V4 Flash en OpenCode |
| Diseño previo a codear | Gemini 3.1 Pro High en Antigravity |
| Dudas rápidas | Gemini Flash 3.5 High en Antigravity |
| Revisión por módulo | Sonnet 4.6 Thinking en Antigravity |
| Revisión crítica final | Opus 4.6 Thinking en Antigravity |

**Regla de oro:** antes de codear cualquier módulo complejo, usar Gemini Pro para diseñarlo. Después GPT 5.5 para construirlo. Después Sonnet o Opus para revisarlo. En ese orden siempre.

> **Nota sobre nombres de modelos:** los nombres en este ROADMAP son ilustrativos del esquema de tiers. Los strings exactos que acepta cada CLI pueden diferir. Verificar con `antigravity --help` y `opencode --help` antes de configurar. La fuente de verdad es siempre `config.toml`.

---

## FASE 1 — NÚCLEO

El objetivo de Fase 1 es simple: Jules responde en terminal, recuerda entre sesiones, y no filtra secrets. Nada más.

---

### MÓDULO 0 — Estructura base del proyecto
**Modelo:** Deepseek V4 Flash  
**Tiempo estimado:** 1 sesión

Esto es lo primero. Sin estructura no hay nada.

```
Tareas:
- Inicializar repositorio git
- Crear pyproject.toml con dependencias base
  (click, rich, sqlalchemy, alembic, lancedb, aiohttp)
  [NO incluir fastapi ni uvicorn — Fase 1 es CLI pura]
- Crear estructura de carpetas según AGENT.md
- Crear __init__.py en todos los paquetes
- Inicializar Alembic (alembic init)
- Crear ~/.jules/ con estructura de archivos
- Crear config.toml base con valores por defecto
- Crear .gitignore (incluir ~/.jules/memory/, *.db, vectors/)
```

**Done cuando:** `python -m jules.cli.main` corre sin errores de import.

---

### MÓDULO 1 — Sanitizador
**Modelo:** GPT 5.5 para implementación / Opus para revisión final  
**Tiempo estimado:** 1–2 sesiones  
**Depende de:** Módulo 0

El sanitizador es el primer módulo real porque todo lo demás depende de que exista. Sin él, nada puede tocar la memoria.

```
Tareas:
- Implementar jules/sanitizer/sanitizer.py
  - SENSITIVE_PATTERNS con los casos del AGENT.md
    [SIN el patrón genérico r'[A-Za-z0-9]{20,}' — genera falsos positivos]
  - Sanitizer.check(text) → SanitizeResult
  - Logger de descartes sin contenido sensible
- Escribir tests exhaustivos (tests/unit/test_sanitizer.py)
  - Casos positivos: API keys, Bearer tokens, exports, URLs con credenciales
  - Casos negativos: código normal, comandos git, imports Python,
    hashes de commit, UUIDs, base64 inocente, nombres de función largos
  - Edge cases: partial matches, multiline, encodings raros
```

**Done cuando:** todos los tests pasan, incluyendo edge cases. Opus lo revisa antes de avanzar.

---

### MÓDULO 2 — Modelos de datos
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 0

Definir las estructuras de datos canónicas antes de cualquier lógica. Todo el proyecto depende de que `Episode` y `SessionContext` estén bien definidos desde el inicio.

```
Tareas:
- Implementar jules/memory/models.py
  - dataclass SessionContext (project, directory, active_files,
    inferred_intent, time_of_day)
  - dataclass Episode (todos los campos del AGENT.md incluyendo
    model_used y provider_used)
- Implementar modelos SQLAlchemy para SQLite
  - EpisodeORM, SessionContextORM
- Primera migración Alembic
  - alembic revision --autogenerate -m "initial_schema"
  - alembic upgrade head
- Tests unitarios de los modelos
  - serialización / deserialización
  - conversión ORM ↔ dataclass
```

**Done cuando:** migración aplicada sin errores, tests de modelos pasan.

---

### MÓDULO 3 — Proveedor local Ollama
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 2

Ollama es el proveedor de identidad y el único que nunca puede fallar. Va antes que los CLIs externos porque el fallback depende de que funcione.

```
Tareas:
- Implementar jules/providers/base.py
  - Protocol Provider con todos los métodos del AGENT.md
  - Excepciones: ProviderError, ProviderUnavailableError, ProviderTimeoutError
- Implementar jules/providers/ollama.py
  - ask() via aiohttp a localhost:11434
  - embed() para generar embeddings
  - health_check() 
  - Manejo de timeout configurable
- Tests de integración (requiere Ollama corriendo con Qwen 2.5)
  - health_check retorna True cuando Ollama está activo
  - ask() retorna respuesta coherente
  - Timeout funciona correctamente
```

**Done cuando:** Ollama responde desde Jules con Qwen 2.5. Probar manualmente en terminal.

---

### MÓDULO 4 — Providers externos (Antigravity y OpenCode)
**Modelo:** GPT 5.5 para implementación / Sonnet para revisión  
**Tiempo estimado:** 2 sesiones  
**Depende de:** Módulo 3

Los providers externos son subprocesses. Antes de escribir una línea, probar manualmente cómo se invocan.

```
Preparación obligatoria (antes de codear):
- antigravity --help → anotar flags exactos de modo no-interactivo
- opencode --help → anotar flags de modelo y prompt
- Probar: antigravity ask "hola" --model gemini-3.5-flash-high
- Probar: opencode run --model openai/gpt-5.5 "hola"
- Verificar que responden a stdout y terminan solos
- Verificar comportamiento con permisos automáticos

Tareas:
- Implementar jules/providers/antigravity.py
  - _run_cli() con patrón async del AGENT.md
  - ask() con model como parámetro
  - health_check() verificando que el CLI existe y responde
  - Manejo de timeout y returncode != 0
  - Solo traducción de I/O — ninguna lógica de decisión aquí
- Implementar jules/providers/opencode.py
  - Mismo patrón que Antigravity
  - Configurar permisos automáticos para evitar cuelgues
  - Solo traducción de I/O — ninguna lógica de decisión aquí
- Tests de integración
  - Antigravity responde con Gemini Flash
  - OpenCode responde con Deepseek
  - Fallback funciona cuando el CLI no está disponible
```

**Done cuando:** los tres providers responden desde Jules. Probar los tres manualmente.

---

### MÓDULO 5 — Router quota-aware
**Modelo:** GPT 5.5 para implementación / Opus para revisión  
**Tiempo estimado:** 1–2 sesiones  
**Depende de:** Módulo 4

El router es la pieza más crítica después de la memoria. Un error aquí quema cuota o deja a Jules sin respuesta.

```
Tareas:
- Implementar jules/core/router.py
  - Enum TaskType con todos los tipos del AGENT.md
  - route(task, user_override) → (Provider, model)
  - ask_with_fallback() → (response, model_used, provider_used)
  - Leer tiers desde config.toml — sin hardcodear modelos
  - Fallback chain: primary → secondary_same_tier → ollama
  - Logging de qué modelo se usó en cada llamada
- Tests unitarios exhaustivos
  - IDENTITY/MEMORY_SCORING/OFFLINE → siempre Ollama
  - CODING → OpenCode low_cost
  - CODING_HEAVY → OpenCode high_cost
  - Fallback cuando provider principal falla
  - user_override respetado siempre
  - Sin modelos hardcodeados en el código
```

**Done cuando:** Opus revisa el router y los tests pasan todos los casos.

---

### MÓDULO 6 — Motor de memoria
**Modelo:** GPT 5.5 para implementación / Opus para revisión  
**Tiempo estimado:** 2–3 sesiones  
**Depende de:** Módulos 1, 2, 3, 5

El módulo más complejo de Fase 1. Tómalo con calma — un motor de memoria roto es el tipo de bug que aparece semanas después.

```
Tareas:
- Implementar jules/memory/scoring.py
  - score(episode) → float via Qwen local (NUNCA modelo externo)
  - Prompt de scoring que Qwen pueda evaluar bien
  - Retorna 0.0–1.0
  - **Calibración obligatoria antes de integrar al flujo:**
    probar el prompt de scoring contra 10–15 episodios de ejemplo
    con Qwen corriendo en Ollama. Ajustar prompt y threshold (0.3 es
    el punto de partida, no un valor definitivo) con datos reales
    antes de conectar scoring al motor de persistencia.
- Implementar jules/memory/episodic.py
  - LanceDB como store vectorial
  - persist(episode) — con embeddings via Ollama
  - retrieve(query, context, limit) — búsqueda semántica
  - Decay: ajuste de score por tiempo sin acceso
- Implementar jules/memory/persistent.py
  - SQLite via SQLAlchemy
  - upsert_facts(episode) — hechos estables
  - get_facts(project) — recuperación por proyecto
- Implementar jules/memory/engine.py
  - retrieve(query, context) — orquesta episodic + persistent
  - persist_async(response, context) — corre en background
    → sanitizar → score → guardar si importa
  - La persistencia es siempre asyncio.create_task(), nunca await directo
- Tests
  - Episodio persiste y se recupera entre sesiones
  - Scoring usa Ollama, no providers externos (mock para verificar)
  - Retrieval por relevancia, no por recencia
  - Decay funciona correctamente con timestamps artificiales
  - Sanitizador bloquea secrets antes del scoring
```

**Done cuando:** Opus revisa el motor completo. Crear un episodio, cerrar Jules, abrir Jules, recuperar el episodio. Si funciona, el módulo está done.

---

### MÓDULO 7 — Detector de intención de contexto
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 6

Simple en Fase 1. El detector infiere intención del contexto observable, no del comportamiento del usuario.

```
Tareas:
- Implementar jules/core/context.py
  - build(session, input) → SessionContext
  - Inferir inferred_intent desde:
    - actividad terminal previa (errores recientes, comandos)
    - directorio activo y proyecto
    - historial de sesión
    - hora del día
  - Mapeado simple: error reciente → "debugging",
    docs recientes → "learning", sin contexto → "review"
- Tests
  - Contexto de debugging detectado correctamente
  - Contexto de aprendizaje detectado correctamente
  - Hora del día poblada correctamente
```

**Done cuando:** SessionContext se construye con intención inferida en casos básicos.

---

### MÓDULO 8 — Sistema de eventos (Fase 1)
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 7

Solo los cinco eventos básicos. Sin eventos cognitivos, sin iniciativa.

```
Tareas:
- Implementar jules/core/events.py
  - Enum EventType (solo los 5 de Fase 1)
  - EventBus simple con subscribe/emit
  - Handlers para cada evento:
    - session_started → inicializar SessionContext
    - project_opened → actualizar directorio activo
    - coding_detected → marcar actividad de código
    - idle_detected → registrar en sesión
    - session_ended → cerrar sesión y persistir resumen
- Filesystem watcher básico (jules/linux/watcher.py)
  - Detectar cambio de directorio activo
  - Detectar actividad de archivos de código
- Shell hooks (jules/linux/shell.py)
  - Hook de zsh/bash para session_started y session_ended
```

**Done cuando:** Jules detecta cuando abres un proyecto y cuando terminas una sesión.

---

### MÓDULO 9 — Sistema de permisos
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 0

```
Tareas:
- Implementar PermissionGate en jules/core/
  - Enum Action con todas las acciones del JULES.md
  - check(action, target) → None o raise PermissionDeniedError
  - Leer configuración desde config.toml
  - Solicitar confirmación al usuario cuando es requerida
- Tests
  - Acciones seguras pasan sin confirmación
  - Acciones que requieren confirmación la solicitan
  - Acciones prohibidas lanzan excepción siempre
```

**Done cuando:** ninguna acción con consecuencias pasa sin el gate.

---

### MÓDULO 10 — CLI principal
**Modelo:** GPT 5.4 / Deepseek para el boilerplate  
**Tiempo estimado:** 1–2 sesiones  
**Depende de:** Todos los módulos anteriores

El entrypoint que conecta todo. Jules responde en terminal.

```
Tareas:
- Implementar jules/cli/main.py con Click
  - Comando principal: jules "tu pregunta"
  - Flags: --model, --task, --no-memory
  - Inicializar sesión al arrancar
  - Flujo completo del AGENT.md:
    1. Sanitizar input
    2. Construir contexto
    3. Recuperar memoria
    4. Router → Provider → respuesta
    5. Mostrar respuesta inmediatamente (Rich para formato)
    6. asyncio.create_task(persist_episode) en background
  - Comando jules memory → ver episodios recientes
  - Comando jules status → estado de providers y memoria
  - Comando jules logs --sanitized → ver descartes del sanitizador
- Personalidad loader (jules/personality/loader.py)
  - Cargar master.md + preset del provider activo
  - Inyectar como system prompt en cada llamada
- Tests de integración end-to-end
  - Jules responde una pregunta
  - La respuesta llega antes de que termine la persistencia (verificar orden)
  - La memoria persiste y se recupera en la siguiente sesión
```

**Done cuando:** `jules "hola"` responde con la personalidad de Jules, sin latencia perceptible, y recuerda el intercambio en la siguiente sesión.

---

### MÓDULO 11 — Observabilidad y modo debug
**Modelo:** GPT 5.4  
**Tiempo estimado:** 1 sesión  
**Depende de:** Módulo 10

Sin observabilidad, Jules se vuelve una caja negra con personalidad. Eso no es arquitectura, es superstición con logs bonitos.

```
Tareas:
- Implementar logging estructurado mínimo
  - provider usado
  - modelo usado
  - task_type
  - duración total
  - fallback usado o no
  - episodios recuperados
  - episodios persistidos o descartados
- Implementar comando jules debug last
  - mostrar última ejecución sin prompts completos
  - mostrar fallos degradados
  - mostrar si la memoria fue omitida por timeout
- Asegurar que no se loggean secrets
- Asegurar que prompts y respuestas completas no se loggean por defecto
- Tests
  - debug last muestra provider/modelo
  - fallback queda registrado
  - sanitizador no expone contenido sensible en logs
```

**Done cuando:** una ejecución fallida puede entenderse con `jules debug last` sin abrir archivos manualmente ni exponer contenido sensible.

---

### REVISIÓN FINAL DE FASE 1
**Modelo:** Opus 4.6 Thinking  
**Tiempo estimado:** 1 sesión

Antes de declarar Fase 1 done, Opus revisa el proyecto completo con estos criterios:

```
Checklist de Fase 1:
- [ ] Jules responde en terminal sin latencia perceptible
- [ ] La memoria persiste entre reinicios — verificado manualmente
- [ ] El sanitizador descarta secrets — verificado con tests
- [ ] El router selecciona el modelo correcto — verificado con tests
- [ ] El fallback a Ollama funciona — verificado matando Antigravity
- [ ] La búsqueda semántica recupera por relevancia, no recencia
- [ ] Qwen hace el scoring — verificado con mocks
- [ ] El sistema de permisos bloquea acciones no autorizadas
- [ ] Todas las migraciones Alembic aplicadas y versionadas
- [ ] Sin modelos hardcodeados fuera de config.toml
- [ ] El post-procesamiento corre en background — verificado con logs
- [ ] `jules debug last` explica la última ejecución
- [ ] Los objetivos de latencia de Fase 1 están medidos
- [ ] Las fallas de memoria degradan, no rompen la respuesta
```

Si algo falla: arreglar antes de avanzar a Fase 1.5.

---

## FASE 1.5 — ESTABILIZACIÓN

No añadir features nuevas.

Objetivo: usar Jules diariamente hasta encontrar fricción real.

Esta fase existe para evitar el error clásico: construir expansión sobre una base que apenas fue probada en condiciones reales.

### Tareas

- medir latencia real
- detectar retrieval irrelevante
- calibrar scoring threshold
- detectar falsos positivos del sanitizador
- observar consumo de RAM
- revisar logs reales de fallback
- mejorar prompts de identidad
- eliminar complejidad innecesaria
- probar modo degradado sin LanceDB
- probar modo degradado sin SQLite
- probar modo degradado sin Antigravity
- probar modo degradado sin OpenCode

### Regla

Ninguna feature de Fase 2 empieza antes de:
- 2 semanas de uso real
- ≥100 episodios persistidos
- ≥10 sesiones completas reales
- fallback probado manualmente múltiples veces
- `jules debug last` usado para diagnosticar errores reales

### Done cuando

```
Checklist de Fase 1.5:
- [ ] Jules se usó en workflow diario real
- [ ] El sanitizador bloqueó secrets sin romper trabajo normal
- [ ] La memoria recuperó episodios útiles en sesiones reales
- [ ] Los falsos positivos conocidos están documentados
- [ ] La latencia promedio es aceptable en terminal
- [ ] Los logs explican fallos sin exponer contenido sensible
- [ ] El sistema funciona en modo degradado parcial
```

Si esta fase parece aburrida, está funcionando.  
La estabilidad rara vez se siente épica. Solo evita incendios.

---

## FASE 2 — EXPANSIÓN

No empezar hasta que Fase 1 y Fase 1.5 estén 100% done y usándose en el workflow diario real.

**Orden de construcción:**

```
1. Detector de intención mejorado
   → más señales, más intenciones, mejor precisión
   → Modelo: GPT 5.5

2. Iniciativa contextual (opt-in)
   → apagada por defecto en config.toml
   → solo señales objetivas, nunca silencio
   → regla de no interrumpir dos veces
   → Modelo: GPT 5.5 / Opus para revisión

3. Automatización de entorno Linux
   → DBus, wmctrl/hyprctl, sesiones tmux
   → PermissionGate en cada acción
   → Modelo: GPT 5.5

4. Replay system
   → reconstrucción de sesiones de debugging
   → requiere memoria episódica sólida funcionando
   → Modelo: GPT 5.5 / Opus para revisión

5. Sistema de voz
   → whisper.cpp para STT
   → Piper para TTS
   → Modelo: GPT 5.4 / Deepseek para integración

6. Desktop app
   → Tauri + SvelteKit
   → muestra modelo activo, tier, contexto, memoria
   → Modelo: GPT 5.5 para lógica / Deepseek para UI básica
```

---

## FASE 3 — INTELIGENCIA ADAPTATIVA

No empezar hasta tener ≥3 meses de uso real con memoria acumulada.

```
1. Perfilador cognitivo
   → análisis de patrones reales del usuario
   → horarios, tipos de tareas, errores recurrentes
   → Modelo: GPT 5.5 / Opus para algoritmos de análisis

2. Diff cognitivo
   → "¿cómo resolvía esto hace 6 meses vs ahora?"
   → requiere episodios con model_used bien poblado
   → Modelo: GPT 5.5

3. Eventos cognitivos calibrados
   → frustration_detected, burnout_signal, productivity_anomaly
   → calibrar con datos reales antes de activar
   → Modelo: GPT 5.5 / Opus para validación

4. Mentoría técnica avanzada
   → sugerencias basadas en historial propio
   → "para este tipo de bug usas mejor Gemini Pro"
   → Modelo: GPT 5.5
```

---

## FASE 4 — AUTONOMÍA

Construir solo si las tres fases anteriores funcionan bien en uso real.

```
1. Asistencia predictiva
2. Adaptación profunda del entorno
3. Personalización autónoma
```

---

## REGLAS DE DESARROLLO

### Antes de codear cualquier módulo
1. Leer la sección correspondiente en `JULES.md` y `AGENT.md`
2. Usar Gemini Pro para diseñar la arquitectura del módulo
3. Tener claro el criterio de "done" antes de empezar

### Durante el desarrollo
- Un módulo a la vez. Sin paralelizar módulos.
- Si aparece algo de Fase 2 mientras construyes Fase 1 → issue, no código
- Commit por módulo terminado, no por feature parcial
- Si un test falla → arreglar antes de seguir

### Después de cada módulo
- Sonnet 4.6 Thinking lo revisa
- Para módulos críticos (sanitizador, memoria, router): Opus 4.6 Thinking
- Si la revisión encuentra algo importante → arreglar antes del siguiente módulo

### Señal de que algo va mal
- Llevas más de 3 sesiones en el mismo módulo sin tenerlo done
- Estás construyendo algo de Fase 2 porque "es pequeño"
- No tienes tests para lo que acabas de construir
- El módulo funciona manualmente pero no tiene tests

Si cualquiera de estas señales aparece: parar, evaluar, retomar desde el criterio de done.

---

## ORDEN FINAL DE CONSTRUCCIÓN — FASE 1

```
0. Estructura base          → Deepseek
1. Sanitizador              → GPT 5.5 + Opus
2. Modelos de datos         → GPT 5.4
3. Provider Ollama          → GPT 5.4
4. Providers externos       → GPT 5.5 + Sonnet
5. Router quota-aware       → GPT 5.5 + Opus
6. Motor de memoria         → GPT 5.5 + Opus
7. Detector de contexto     → GPT 5.4
8. Sistema de eventos       → GPT 5.4
9. Sistema de permisos      → GPT 5.4
10. CLI principal           → GPT 5.4 + Deepseek
    Revisión final Fase 1   → Opus 4.6 Thinking

Nota: personality/coherence.py es Fase 2.
En Fase 1 la consistencia de identidad se garantiza con
master.md + presets + tests de integración (test_provider_coherence.py).
```

Cada número es un módulo completo y testeado antes de avanzar al siguiente.
