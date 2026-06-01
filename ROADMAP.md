# ROADMAP.md
## Versión 1.4
## Plan de Construcción — Jules

> **Principio:** Cada módulo debe funcionar y estar testeado antes de construir el siguiente.
> Un módulo roto que avanza es deuda que mata el proyecto.

---

## ENTORNO DE DESARROLLO

| Componente | Valor |
|---|---|
| OS | EndeavourOS (rolling release) |
| Escritorio | KDE Plasma 6 + Wayland |
| Shell | Verificar con `echo $SHELL` antes del Módulo 8 |
| Python | Virtualenv dedicado — obligatorio, nunca el Python del sistema |

---

## STACK DE MODELOS POR TAREA

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

> **Nota sobre nombres de modelos:** los nombres en este ROADMAP son ilustrativos del esquema de tiers. Los strings exactos que acepta cada CLI pueden diferir. La fuente de verdad es siempre `config.toml`. Verificar con `antigravity --help` y `opencode --help` antes de configurar.

---

## REGLAS DE DESARROLLO

### Antes de codear cualquier módulo
1. Leer la sección correspondiente en `JULES.md`
2. Usar Gemini Pro para diseñar la arquitectura del módulo
3. Tener claro el criterio de "done" antes de empezar

### Durante el desarrollo
- Un módulo a la vez. Sin paralelizar módulos.
- Si aparece algo de Fase 2 mientras construyes Fase 1 → issue, no código
- Commit por módulo terminado, no por feature parcial
- Si un test falla → arreglar antes de seguir

### Después de cada módulo
- Sonnet 4.6 Thinking lo revisa
- Para módulos críticos (sanitizador, memoria, router, permisos, doctor): Opus 4.6 Thinking
- Si la revisión encuentra algo importante → arreglar antes del siguiente módulo

### Señales de que algo va mal
- Llevas más de 3 sesiones en el mismo módulo sin tenerlo done
- Estás construyendo algo de Fase 2 porque "es pequeño"
- No tienes tests para lo que acabas de construir
- El módulo funciona manualmente pero no tiene tests

Si cualquiera de estas señales aparece: parar, evaluar, retomar desde el criterio de done.

---

## FASE 1 — NÚCLEO

El objetivo de Fase 1 es simple: Jules responde en terminal, recuerda entre sesiones, conoce su entorno, y no filtra secrets. Nada más.

---

### MÓDULO 0 — Estructura base del proyecto
**Clasificación:** MECÁNICO
**Modelo:** Deepseek V4 Flash
**Tiempo estimado:** 1 sesión
**Depende de:** nada

Esto es lo primero. Sin estructura no hay nada.

```
Tareas:
- Crear virtualenv dedicado:
    python -m venv .venv
    source .venv/bin/activate
  (Nunca saltar este paso. En rolling release es obligatorio.)

- Inicializar repositorio git
- Crear pyproject.toml con dependencias base:
    click, rich, sqlalchemy, alembic, lancedb, aiohttp
    (NO incluir fastapi ni uvicorn — Fase 1 es CLI pura)
- Agregar al .gitignore:
    .venv/
    ~/.jules/memory/
    *.db
    vectors/
    __pycache__/
- Crear estructura de carpetas según JULES.md
- Crear __init__.py en todos los paquetes
- Inicializar Alembic: alembic init
- Crear ~/.jules/ con estructura de archivos
- Crear config.toml base con valores de JULES.md
- Generar requirements.lock después de instalar dependencias:
    pip freeze > requirements.lock
```

**Verificación:** `python -m jules.cli.main` corre sin errores de import.

**Done cuando:** estructura creada, virtualenv activo, `requirements.lock` generado, primer commit hecho.

---

### MÓDULO 1 — Sanitizador
**Clasificación:** CRÍTICO — Requiere Diseño SDD
**Modelo:** GPT 5.5 para implementación / Opus para revisión final
**Tiempo estimado:** 1–2 sesiones
**Depende de:** Módulo 0

El sanitizador es el primer módulo real porque todo lo demás depende de que exista. Sin él, nada puede tocar la memoria.

```
Tareas:
- Implementar jules/sanitizer/sanitizer.py
  - SENSITIVE_PATTERNS con los casos de JULES.md
    (SIN el patrón genérico r'[A-Za-z0-9]{20,}' — genera falsos positivos)
  - Sanitizer.check(text) → SanitizeResult
  - Logger de descartes sin contenido sensible
  - strict_mode: descartar ante la duda, nunca limpiar parcialmente

- Escribir tests exhaustivos (tests/unit/test_sanitizer.py):
  Casos positivos:
    - API keys (OpenAI sk-, Google AIza, GitHub ghp_)
    - Bearer tokens
    - exports con credenciales
    - URLs con usuario:password
    - private keys en bloque
    - Slack tokens
  Casos negativos (NO deben ser descartados):
    - código Python normal
    - comandos git con hashes
    - imports estándar
    - UUIDs
    - base64 inocente
    - nombres de función largos
    - paths de archivo
  Edge cases:
    - partial matches
    - multiline
    - credenciales en medio de código legítimo
```

**Verificación:** `pytest tests/unit/test_sanitizer.py -v` — todos los casos pasan.

**Done cuando:** todos los tests pasan incluyendo edge cases. Opus lo revisa antes de avanzar.

---

### MÓDULO 2 — Modelos de datos
**Clasificación:** CRÍTICO — Requiere Diseño SDD
**Modelo:** GPT 5.4
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 0

Definir las estructuras canónicas antes de cualquier lógica. Todo el proyecto depende de que `Episode` y `SessionContext` estén bien definidos desde el inicio.

```
Tareas:
- Implementar jules/memory/models.py
  - dataclass SessionContext:
      project, directory, active_files,
      inferred_intent, time_of_day, shell
    (el campo shell se puebla al arranque detectando $SHELL)
  - dataclass Episode:
      todos los campos de JULES.md incluyendo
      model_used, provider_used, memory_schema_version

- Implementar modelos SQLAlchemy para SQLite:
  - EpisodeORM, SessionContextORM

- Primera migración Alembic:
    alembic revision --autogenerate -m "initial_schema"
    alembic upgrade head

- Tests unitarios de los modelos:
  - serialización / deserialización
  - conversión ORM ↔ dataclass
  - memory_schema_version presente en todos los episodios
```

**Verificación:** `alembic upgrade head` sin errores. `pytest tests/unit/test_models.py -v`.

**Done cuando:** migración aplicada, tests pasan, `memory_schema_version` presente en el modelo.

---

### MÓDULO 3 — Provider local Ollama
**Clasificación:** MECÁNICO
**Modelo:** GPT 5.4
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 2

Ollama es el provider de identidad y el único que nunca puede fallar. Va antes que los CLIs externos porque el fallback depende de que funcione.

```
Tareas:
- Implementar jules/providers/base.py
  - Protocol Provider con todos los métodos
  - Excepciones: ProviderError, ProviderUnavailableError, ProviderTimeoutError

- Implementar jules/providers/ollama.py
  - ask() via aiohttp a localhost:11434
  - embed() para generar embeddings
  - health_check()
  - Manejo de timeout configurable

- Verificación crítica de Ollama en EndeavourOS:
  Ver bajo qué usuario corre el servicio:
    systemctl show ollama.service | grep User
  Si corre como usuario del sistema (no como el usuario actual):
    Opción A: sudo -u ollama ollama list → verificar que los modelos sean visibles
    Opción B: systemctl --user enable --now ollama → correr como servicio de usuario
  La visibilidad de los modelos bajo el usuario correcto es criterio de done.
  No delegar esta verificación a Fase 1.5.

- Tests de integración (requiere Ollama corriendo con Llama 3.2):
  - health_check retorna True cuando Ollama está activo
  - ask() retorna respuesta coherente
  - embed() retorna vector de dimensión correcta
  - Timeout funciona correctamente
  - Los modelos son visibles desde el proceso de Jules
```

**Verificación:** `jules status` (prototipo) muestra Ollama activo con usuario correcto.

**Done cuando:** Ollama responde desde Jules con Llama 3.2, modelos visibles, usuario verificado.

---

### MÓDULO 4 — Providers externos (Antigravity y OpenCode)
**Clasificación:** MECÁNICO
**Modelo:** GPT 5.5 para implementación / Sonnet para revisión
**Tiempo estimado:** 2 sesiones
**Depende de:** Módulo 3

Los providers externos son subprocesses. Antes de escribir una línea, probar manualmente cómo se invocan.

```
Preparación obligatoria (antes de codear):
- antigravity --help → anotar flags exactos de modo no-interactivo
- opencode --help → anotar flags de modelo y prompt
- Probar manualmente:
    antigravity ask "hola" --model gemini-3.5-flash-high
    opencode run --model openai/gpt-5.5 "hola"
- Verificar que responden a stdout y terminan solos sin input adicional
- Verificar comportamiento con permisos automáticos en OpenCode
- Verificar comportamiento bajo Wayland (algunos CLIs tienen problemas con TTY)

Tareas:
- Implementar jules/providers/antigravity.py
  - _run_cli() con patrón async subprocess
  - ask() con model como parámetro
  - health_check() verificando que el CLI existe y responde a --help
  - Manejo de timeout y returncode != 0
  - Solo traducción de I/O — ninguna lógica de decisión aquí

- Implementar jules/providers/opencode.py
  - Mismo patrón que Antigravity
  - Configurar permisos automáticos para evitar cuelgues en subprocess
  - Solo traducción de I/O — ninguna lógica de decisión aquí

- Tests de integración:
  - Antigravity responde con Gemini Flash
  - OpenCode responde con Deepseek
  - health_check retorna False cuando el CLI no está en PATH
  - Fallback funciona cuando el CLI no está disponible
  - Timeout funciona en ambos providers
```

**Verificación:** los tres providers responden desde Jules en prueba manual en terminal.

**Done cuando:** los tres providers responden. Sonnet revisa antes de avanzar.

---

### MÓDULO 5 — Router quota-aware
**Clasificación:** CRÍTICO — Requiere Diseño SDD
**Modelo:** GPT 5.5 para implementación / Opus para revisión
**Tiempo estimado:** 1–2 sesiones
**Depende de:** Módulo 4

El router es la pieza más crítica después de la memoria. Un error aquí quema cuota o deja a Jules sin respuesta.

```
Tareas:
- Implementar jules/core/router.py
  - Enum TaskType con todos los tipos de JULES.md
  - route(task, user_override) → (Provider, model)
  - ask_with_fallback() → (response, model_used, provider_used)
  - Leer tiers desde config.toml — sin hardcodear modelos en el código
  - Fallback chain: primary → secondary_same_tier → ollama
  - Logging estructurado de qué modelo se usó en cada llamada

- Tests unitarios exhaustivos:
  - IDENTITY/MEMORY_SCORING/OFFLINE → siempre Ollama (nunca otros)
  - CODING → OpenCode low_cost
  - CODING_HEAVY → OpenCode high_cost
  - Fallback cuando provider principal falla
  - user_override respetado siempre
  - Sin modelos hardcodeados en el código (verificar con grep)
  - Modificar config.toml en test → router respeta el cambio
```

**Verificación:** `pytest tests/unit/test_router.py -v` — todos los casos pasan. `grep -r "gpt-5\|gemini\|claude" jules/core/router.py` → sin resultados (modelos solo en config.toml).

**Done cuando:** Opus revisa el router y todos los tests pasan.

---

### MÓDULO 6 — Motor de memoria
**Clasificación:** CRÍTICO — Requiere Diseño SDD
**Modelo:** GPT 5.5 para implementación / Opus para revisión
**Tiempo estimado:** 2–3 sesiones
**Depende de:** Módulos 1, 2, 3, 5

El módulo más complejo de Fase 1. La memoria rota es el tipo de bug que aparece semanas después, cuando ya confiás en ella.

```
Tareas:

- Implementar jules/memory/scoring.py
  - score(episode) → float via Llama local (NUNCA modelo externo)
  - Prompt de scoring diseñado para Llama 3.2 1B sobre contenido técnico
  - Retorna 0.0–1.0
  - ScoringHealthMonitor:
    - record(score) — acumula scores recientes
    - is_healthy() → bool — detecta scoring degenerado (varianza < 0.01)
    - Threshold configurable desde config.toml

  CALIBRACIÓN OBLIGATORIA antes de integrar al flujo:
    Probar el prompt de scoring contra 10–15 episodios de ejemplo
    con Llama corriendo en Ollama. Verificar que la varianza sea real
    entre episodios de distinta importancia. El threshold 0.3 es punto
    de partida — ajustar con datos reales. Si el modelo devuelve scores
    constantes, rediseñar el prompt antes de continuar.

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
  - persist_async(response, context) — corre en background:
      sanitizar → score → ScoringHealthMonitor.record() →
      guardar si importa (o modo conservador si scoring degenerado)
  - La persistencia es siempre asyncio.create_task(), nunca await directo
  - Modo conservador cuando scoring degenerado:
      guardar episodios con friction_score > 0.5
      o con tags de proyecto activo
      loggear que se está en modo conservador

- Tests:
  - Episodio persiste y se recupera entre sesiones (reinicio real)
  - Scoring usa Ollama, no providers externos (mock para verificar)
  - Retrieval por relevancia, no por recencia
  - Decay funciona con timestamps artificiales
  - Sanitizador bloquea secrets antes del scoring
  - ScoringHealthMonitor detecta scoring constante
  - Modo conservador activa cuando scoring degenerado
```

**Verificación:** crear un episodio → cerrar Jules → abrir Jules → recuperar el episodio. Si funciona, el módulo está done.

**Done cuando:** Opus revisa el motor completo y el test de persistencia entre sesiones pasa manualmente.

---

### MÓDULO 7 — Detector de intención de contexto
**Clasificación:** MECÁNICO
**Modelo:** GPT 5.4
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 6

Simple en Fase 1. Infiere intención del contexto observable, no del comportamiento declarado.

```
Tareas:
- Implementar jules/core/context.py
  - build(session, input) → SessionContext
  - Detectar shell activo y poblarlo en SessionContext.shell:
      import os; os.environ.get("SHELL", "unknown")
  - Inferir inferred_intent desde:
      actividad terminal previa (errores recientes, comandos)
      directorio activo y proyecto
      historial de sesión
      hora del día
  - Mapeado simple:
      error reciente → "debugging"
      docs recientes → "learning"
      sin contexto → "review"

- Tests:
  - Contexto de debugging detectado correctamente
  - Contexto de aprendizaje detectado correctamente
  - Shell poblado correctamente en SessionContext
  - Hora del día poblada correctamente
```

**Verificación:** `pytest tests/unit/test_context.py -v`. `SessionContext.shell` siempre tiene valor.

**Done cuando:** SessionContext se construye con intención inferida y shell detectado en casos básicos.

---

### MÓDULO 8 — Sistema de eventos
**Clasificación:** SEMI-CRÍTICO
**Modelo:** GPT 5.4
**Tiempo estimado:** 1–2 sesiones
**Depende de:** Módulo 7

Solo los cinco eventos básicos. Sin eventos cognitivos, sin iniciativa. Más complejo de lo que parece por las particularidades del entorno.

```
Preparación obligatoria (antes de codear):

1. Detectar shell activo:
     echo $SHELL
   La implementación de hooks depende de este valor.
   No asumir bash. En EndeavourOS con KDE es común fish o zsh.

2. Verificar límite de inotify:
     cat /proc/sys/fs/inotify/max_user_watches
   Si está por debajo de 65536:
     echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf
     sudo sysctl -p /etc/sysctl.d/jules.conf
   Jules no puede depender de que este límite sea suficiente
   sin haberlo verificado primero.

Tareas:

- Implementar jules/core/events.py
  - Enum EventType (solo los 5 de Fase 1):
      SESSION_STARTED, PROJECT_OPENED, CODING_DETECTED,
      IDLE_DETECTED, SESSION_ENDED
  - EventBus simple con subscribe/emit
  - Handlers para cada evento:
      session_started → inicializar SessionContext con shell detectado
      project_opened  → actualizar directorio activo
      coding_detected → marcar actividad de código
      idle_detected   → registrar en sesión
      session_ended   → cerrar sesión y persistir resumen

- Implementar jules/linux/watcher.py
  - Detectar cambio de directorio activo
  - Detectar actividad de archivos de código
  - Verificar límite de inotify al inicializar:
      leer /proc/sys/fs/inotify/max_user_watches
      si está cerca del límite → loggear advertencia
      si se agota → desactivar watchers, emitir evento de degradación

- Implementar jules/linux/shell.py
  - Detectar shell activo desde $SHELL
  - Generar hooks para el shell correspondiente:

    Si fish → ~/.config/fish/conf.d/jules.fish
      function jules_session_start --on-event fish_prompt
          # solo en primera ejecución de la sesión
      end
      function jules_preexec --on-event fish_preexec
          # comandos antes de ejecutar
      end

    Si zsh → fragmento para ~/.zshrc
      precmd() { ... }
      preexec() { ... }

    Si bash → fragmento para ~/.bashrc
      PROMPT_COMMAND="..."
      trap '...' DEBUG

  - Nunca intentar adaptar hooks de bash a fish o viceversa.
  - El installer de hooks debe ser idempotente (correrlo dos veces no genera duplicados).

- Tests:
  - EventBus emite y recibe correctamente
  - session_started puebla SessionContext con shell correcto
  - Watcher detecta cambio de directorio
  - Watcher detecta actividad de código
  - Límite de inotify bajo → advertencia loggeada sin crashear
```

**Verificación:** Jules detecta cuando se abre un proyecto y cuando termina una sesión. Verificar manualmente con el shell activo real.

**Done cuando:** hooks instalados para el shell correcto, watcher detecta actividad, inotify verificado.

---

### MÓDULO 9 — Sistema de permisos
**Clasificación:** CRÍTICO — Requiere Diseño SDD
**Modelo:** GPT 5.4
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 0

```
Tareas:
- Implementar PermissionGate en jules/core/permissions.py
  - Enum Action con todas las acciones de JULES.md
  - check(action, target) → None o raise PermissionDeniedError
  - Leer configuración desde config.toml
  - Solicitar confirmación al usuario cuando es requerida (Rich prompt)
  - Acciones prohibidas → excepción siempre, sin posibilidad de override

- Tests:
  - Acciones seguras pasan sin confirmación
  - Acciones que requieren confirmación la solicitan
  - Acciones prohibidas lanzan PermissionDeniedError siempre
  - Config en modo test desactiva prompts interactivos
```

**Verificación:** `pytest tests/unit/test_permissions.py -v`. Ninguna acción con consecuencias pasa sin el gate.

**Done cuando:** el gate rechaza todo lo que debe rechazar. Sin excepciones.

---

### MÓDULO 10 — `jules doctor`
**Clasificación:** MECÁNICO
**Modelo:** GPT 5.4
**Tiempo estimado:** 1 sesión
**Depende de:** Módulos 3, 6, 8, 9

Doctor va antes que el CLI principal porque el CLI va a depender de él para el arranque. En un entorno rolling release, este comando es el primero que corre cuando algo falla.

```
Tareas:
- Implementar jules/linux/doctor.py
  Checks a implementar (ver tabla completa en JULES.md):
  - Ollama: servicio activo + modelos visibles + usuario correcto
  - Antigravity CLI: disponible en PATH + responde a --help
  - OpenCode CLI: disponible en PATH + responde a --help
  - LanceDB: directorio de vectores accesible + no corrupto
  - SQLite: jules.db accesible + migraciones Alembic al día
  - inotify: leer /proc/sys/fs/inotify/max_user_watches vs threshold de config.toml
  - Virtualenv: verificar que sys.prefix != sys.base_prefix
  - Permisos ~/.jules/: escritura disponible en todos los subdirectorios
  - Scoring health: último estado conocido desde scoring.log
  - Shell detectado: mostrar valor de $SHELL

  Reglas de output:
  - ✓ / ✗ / ⚠ por check
  - Nunca bloquear el arranque — solo reportar
  - Salida estructurada (Rich table en terminal, JSON si --json)
  - Código de salida 0 si todo OK, 1 si hay problemas

- Agregar comando al CLI (prototipo):
    jules doctor
    jules doctor --json

- Tests:
  - Cada check retorna resultado correcto en condiciones normales
  - Check de inotify bajo → ⚠ con mensaje de corrección
  - Check de virtualenv fuera de venv → ✗ claro
  - Output JSON parseable
```

**Verificación:** `jules doctor` muestra estado completo. `jules doctor --json | jq .` funciona.

**Done cuando:** todos los checks implementados, output claro, código de salida correcto.

---

### MÓDULO 11 — CLI principal
**Clasificación:** MECÁNICO
**Modelo:** GPT 5.4 / Deepseek para boilerplate
**Tiempo estimado:** 2–3 sesiones
**Depende de:** todos los módulos anteriores

El entrypoint que conecta todo. Más lento de lo estimado en versiones anteriores — aquí aparecen los bugs que no surgieron en tests aislados.

```
Tareas:
- Implementar jules/cli/main.py con Click
  Comandos:
    jules "tu pregunta"          # flujo principal
    jules --model MODEL "query"  # override de modelo
    jules --task TASK "query"    # override de task type
    jules --no-memory "query"    # sin recuperación ni persistencia
    jules memory                 # episodios recientes
    jules status                 # estado de providers y memoria
    jules doctor                 # diagnóstico completo (delega a Módulo 10)
    jules logs --sanitized       # descartes del sanitizador
    jules logs --scoring         # historial de salud del scorer
    jules debug last             # última ejecución detallada

  Flujo principal (flujo del JULES.md):
    1. jules doctor al arranque — solo advertencias, nunca bloqueo
    2. Sanitizar input
    3. Construir contexto (SessionContext con shell detectado)
    4. Recuperar memoria (con timeout)
    5. Router → Provider → respuesta
    6. Mostrar respuesta inmediatamente (Rich para formato)
    7. asyncio.create_task(persist_episode) en background

  Cuidados específicos para EndeavourOS + Wayland:
    - Verificar que Rich no rompe el output bajo algunos terminales de KDE
    - Verificar que asyncio.create_task() no crea conflictos con el event loop de Click
    - Si Ollama está frío al arranque → advertir al usuario con tiempo estimado

- Implementar jules/personality/loader.py
  - Cargar master.md + preset del provider activo
  - Inyectar como system prompt en cada llamada
  - Detectar cambios de versión en master.md y advertir

- Tests de integración end-to-end:
  - Jules responde una pregunta con el flujo completo
  - La respuesta llega antes de que termine la persistencia (verificar con logs)
  - La memoria persiste y se recupera en la siguiente sesión (reinicio real)
  - jules doctor corre al arranque sin bloquear
  - jules debug last muestra la última ejecución correctamente
  - Startup < 500ms con Ollama caliente (medir con time)
```

**Verificación:** `jules "hola"` responde con la personalidad de Jules, sin latencia perceptible. `jules debug last` explica qué pasó. La memoria persiste al reiniciar.

**Done cuando:** flujo completo funciona end-to-end, startup medido, tests de integración pasan.

---

### REVISIÓN FINAL DE FASE 1
**Modelo:** Opus 4.6 Thinking
**Tiempo estimado:** 1 sesión

Antes de declarar Fase 1 done, Opus revisa el proyecto completo.

```
Checklist de Fase 1:
- [ ] Jules responde en terminal sin latencia perceptible
- [ ] La memoria persiste entre reinicios — verificado manualmente
- [ ] El sanitizador descarta secrets — verificado con tests
- [ ] El router selecciona el modelo correcto — verificado con tests
- [ ] El fallback a Ollama funciona — verificado matando Antigravity
- [ ] La búsqueda semántica recupera por relevancia, no recencia
- [ ] Llama hace el scoring — verificado con mocks
- [ ] ScoringHealthMonitor activo y loggeable
- [ ] El sistema de permisos bloquea acciones no autorizadas
- [ ] Todas las migraciones Alembic aplicadas y versionadas
- [ ] Sin modelos hardcodeados fuera de config.toml (grep verifica)
- [ ] El post-procesamiento corre en background — verificado con logs
- [ ] jules doctor reporta estado completo del entorno
- [ ] jules debug last explica la última ejecución
- [ ] Shell detectado correctamente y hooks instalados para ese shell
- [ ] Límite de inotify verificado y configurado
- [ ] Ollama corre bajo el usuario correcto — verificado
- [ ] Startup < 500ms con Ollama caliente — medido
- [ ] Las fallas de memoria degradan, no rompen la respuesta
- [ ] El virtualenv está aislado y requirements.lock está actualizado
```

Si algo falla: arreglar antes de avanzar a Fase 1.5.

---

## FASE 1.5 — ESTABILIZACIÓN

No añadir features nuevas. Esta fase existe para evitar construir expansión sobre una base que apenas fue probada en condiciones reales.

### Tareas

```
Performance y latencia:
- Medir latencia real de startup (Ollama frío vs caliente)
- Medir tiempo de retrieval en condiciones reales
- Medir tiempo total de respuesta con providers externos

Memoria:
- Detectar retrieval irrelevante en sesiones reales
- Calibrar scoring threshold con episodios reales
- Observar consumo de RAM con LanceDB bajo carga real
- Revisar logs reales de qué se persistió y qué se descartó

Sanitizador:
- Detectar falsos positivos en workflows reales de desarrollo
- Documentar casos que generaron descarte inesperado

Entorno:
- Verificar hooks de shell bajo el shell real en uso diario
- Verificar watcher bajo carga real (proyectos grandes)
- Confirmar inotify no se agota en sesiones largas
- Verificar Ollama systemd bajo el usuario correcto en todas las condiciones

Resiliencia:
- Probar modo degradado sin LanceDB
- Probar modo degradado sin SQLite
- Probar modo degradado sin Antigravity
- Probar modo degradado sin OpenCode
- Probar modo degradado con scoring degenerado
- Verificar que jules doctor detecta cada modo degradado

Calidad:
- Revisar logs reales de fallback
- Mejorar prompts de identidad basándose en respuestas reales
- Eliminar complejidad innecesaria detectada en uso real
```

### Criterio de entrada a Fase 2

Ninguna feature de Fase 2 empieza antes de:

```
- [ ] 2 semanas de uso real en workflow diario
- [ ] ≥100 episodios persistidos en condiciones reales
- [ ] ≥10 sesiones completas reales
- [ ] Fallback probado manualmente múltiples veces
- [ ] jules debug last usado para diagnosticar errores reales
- [ ] Jules doctor no reporta ningún ✗ pendiente
- [ ] El sanitizador bloqueó secrets sin romper trabajo normal
- [ ] La memoria recuperó episodios útiles en sesiones reales
- [ ] Los falsos positivos conocidos están documentados
- [ ] El sistema funcionó en modo degradado parcial al menos una vez
```

Si esta fase parece aburrida, está funcionando.
La estabilidad rara vez se siente épica. Solo evita incendios.

---

## FASE 2 — EXPANSIÓN

No empezar hasta que Fase 1 y Fase 1.5 estén 100% done y usándose en el workflow diario real.

**Orden de construcción:**

```
1. Detector de intención mejorado  [CRÍTICO — Diseño SDD]
   Más señales, más intenciones, mejor precisión.
   Modelo: GPT 5.5

2. Iniciativa contextual (opt-in)  [CRÍTICO — Diseño SDD]
   Apagada por defecto en config.toml.
   Solo señales objetivas, nunca silencio como señal.
   Regla: no interrumpir dos veces por la misma razón.
   Modelo: GPT 5.5 / Opus para revisión

3. Automatización de entorno Linux  [CRÍTICO — Diseño SDD]
   Integración con KDE Plasma via D-Bus / KWin:
     qdbus org.kde.KWin ...
     dbus-send --session --dest=org.kde.KWin ...
   wmctrl disponible pero con soporte parcial bajo Wayland — evaluar
   en condiciones reales antes de depender de él.
   NO usar hyprctl — es exclusivo de Hyprland.
   PermissionGate en cada acción que toca el entorno.
   Modelo: GPT 5.5

4. Replay system  [CRÍTICO — Diseño SDD]
   Reconstrucción de sesiones de debugging.
   Requiere memoria episódica sólida y probada.
   Modelo: GPT 5.5 / Opus para revisión

5. Sistema de voz  [MECÁNICO — Integración de terceros]
   whisper.cpp para STT, Piper para TTS.
   Modelo: GPT 5.4 / Deepseek para integración

6. Desktop app  [MECÁNICO — Interfaz gráfica]
   Tauri + SvelteKit.
   Muestra: modelo activo, tier, contexto, memoria, salud del scoring.
   Modelo: GPT 5.5 para lógica / Deepseek para UI

7. Optimización de latencia cloud  [MECÁNICO — Rendimiento]
   Configurar acoplamiento a daemon mode de los CLIs externos.
   Comunicación via HTTP/Sockets locales para eliminar el boot tax
   de subprocess (~2 segundos por invocación).
   Modelo: GPT 5.4 / Deepseek
```

---

## FASE 3 — INTELIGENCIA ADAPTATIVA

No empezar hasta tener ≥3 meses de uso real con memoria acumulada.

```
1. Perfilador cognitivo  [CRÍTICO — Algoritmia avanzada SDD]
   Análisis de patrones reales: horarios, tipos de tareas, errores recurrentes.
   Modelo: GPT 5.5 / Opus para algoritmos de análisis

2. Diff cognitivo  [CRÍTICO — Diseño SDD]
   "¿Cómo resolvía esto hace 6 meses vs ahora?"
   Requiere episodios con model_used bien poblado.
   Modelo: GPT 5.5

3. Eventos cognitivos calibrados  [CRÍTICO — Diseño SDD]
   frustration_detected, burnout_signal, productivity_anomaly.
   Calibrar con datos reales antes de activar.
   Implementar antes → falsos positivos permanentes.
   Modelo: GPT 5.5 / Opus para validación

4. Mentoría técnica avanzada  [CRÍTICO — Diseño SDD]
   Sugerencias basadas en historial propio.
   "Para este tipo de bug resolvés mejor con Gemini Pro."
   Modelo: GPT 5.5
```

---

## FASE 4 — AUTONOMÍA

Construir solo si las tres fases anteriores funcionan bien en uso real.

```
1. Asistencia predictiva      [CRÍTICO]
2. Adaptación profunda        [CRÍTICO]
3. Personalización autónoma   [CRÍTICO]
```

---

## ORDEN FINAL DE CONSTRUCCIÓN — FASE 1

```
[x] 0.  Estructura base + virtualenv    → Deepseek             (Completado)
[x] 1.  Sanitizador                     → GPT 5.5 + Opus       (Completado)
[x] 2.  Modelos de datos                → GPT 5.4              (Completado)
[x] 3.  Provider Ollama                 → GPT 5.4              (Completado)
[x] 4.  Providers externos              → GPT 5.5 + Sonnet     (Completado)
[x] 5.  Router quota-aware              → GPT 5.5 + Opus       (Completado)
[x] 6.  Motor de memoria                → GPT 5.5 + Opus       (Completado)
[x] 7.  Detector de contexto            → GPT 5.4              (Completado)
[x] 8.  Sistema de eventos              → GPT 5.4              (Completado)
[ ] 9.  Sistema de permisos             → GPT 5.4              (Pendiente)
[ ] 10. jules doctor                    → GPT 5.4              (Pendiente)
[ ] 11. CLI principal                   → GPT 5.4 + Deepseek   (Pendiente)
[ ]     Revisión final Fase 1           → Opus 4.6 Thinking    (Pendiente)

Nota: personality/coherence.py es Fase 2.
En Fase 1 la consistencia de identidad se garantiza con
master.md + presets por provider + tests de integración.

Nota: jules_chat.py es solo un prototipo de chat.
El CLI principal (Módulo 11) lo reemplaza completamente.
```

Cada número es un módulo completo y testeado antes de avanzar al siguiente.
Sin excepciones.
