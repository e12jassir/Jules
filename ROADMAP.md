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

## MODELOS POR FASE SDD

> Los modelos asignados por fase están en `AGENT.md` → sección **MODELOS POR FASE SDD — REGLA INVIOLABLE**.
> Cada módulo pendiente (9, 10, 11) tiene su propia tabla con flujo y modelos específicos.
> Fuente de verdad de strings de modelos: `config.toml`.

---

## REGLAS DE DESARROLLO

- Un módulo a la vez. Sin paralelizar. Commit por módulo terminado.
- Si aparece algo de Fase 2 mientras construís Fase 1 → issue, no código.
- Si un test falla → arreglar antes de seguir. Nunca avanzar con rojo.
- Leer la sección de `JULES.md` correspondiente antes de codear cualquier módulo.
- Si llevás más de 3 sesiones en el mismo módulo sin tenerlo done: parar y re-evaluar el criterio de done.
- Un módulo que funciona manualmente pero sin tests no está done.

---

## FASE 1 — NÚCLEO

El objetivo de Fase 1 es simple: Jules responde en terminal, recuerda entre sesiones, conoce su entorno, y no filtra secrets. Nada más.

---

### [x] MÓDULO 0 — Estructura base del proyecto
**Clasificación:** MECÁNICO | **Modelo:** Deepseek V4 Flash | **Estado:** ✅ Completado

---

### [x] MÓDULO 1 — Sanitizador
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.5 + Opus revisión | **Estado:** ✅ Completado

---

### [x] MÓDULO 2 — Modelos de datos
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado

---

### [x] MÓDULO 3 — Provider local Ollama
**Clasificación:** MECÁNICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado

---

### [x] MÓDULO 4 — Providers externos (Antigravity y OpenCode)
**Clasificación:** MECÁNICO | **Modelo:** GPT 5.5 + Sonnet revisión | **Estado:** ✅ Completado

---

### [x] MÓDULO 5 — Router quota-aware
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.5 + Opus revisión | **Estado:** ✅ Completado

---

### [x] MÓDULO 6 — Motor de memoria
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.5 + Opus revisión | **Estado:** ✅ Completado

---

### [x] MÓDULO 7 — Detector de intención de contexto
**Clasificación:** MECÁNICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado

---

### [x] MÓDULO 8 — Sistema de eventos
**Clasificación:** SEMI-CRÍTICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado

---

### [x] MÓDULO 9 — Sistema de permisos
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 0

#### Fases SDD para este módulo

> Este módulo está marcado CRÍTICO porque el Módulo 11 hereda su contrato. Un Enum mal diseñado aquí se propaga a todo el CLI. Las fases de propuesta y spec son obligatorias por eso.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Una vez por sesión — detectar contexto del proyecto |
| `sdd-explore` | ⚠️ Breve | Gemini 3.1 Pro | Solo verificar que `config.toml` ya tiene sección `[permissions]` y revisar cómo el CLI futuro lo invocará. No requiere mapeo extenso |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Decisiones reales: granularidad del Enum Action, extensibilidad para Fase 2 (acciones de entorno Linux), contrato de `PermissionDeniedError`. Sin esto el CLI no puede integrarlo |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Producir spec técnico preciso: enum completo, firma de `check()`, modo test, estructura de config. Evita ambigüedad en el apply |
| `sdd-design` | ❌ No | — | Si propose + spec son precisos, el diseño es trivial para un solo archivo |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomponer en tasks atómicas: Enum, `check()`, prompts Rich, config, modo test, tests unitarios |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | CRÍTICO: verificar que ninguna acción prohibida puede ser overrideada, modo test funciona, config se lee correctamente |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Persistir spec para que Módulo 11 tenga el contrato de referencia |

**Flujo:** `init` → `explore (breve)` → `propose` → `spec` → `tasks` → `apply` → `verify` → `archive`

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

### [x] MÓDULO 10 — `jules doctor`
**Clasificación:** MECÁNICO | **Modelo:** GPT 5.4 | **Estado:** ✅ Completado
**Tiempo estimado:** 1 sesión
**Depende de:** Módulos 3, 6, 8, 9

Doctor va antes que el CLI principal porque el CLI va a depender de él para el arranque. En un entorno rolling release, este comando es el primero que corre cuando algo falla.

#### Fases SDD para este módulo

> Módulo mecánico. El spec completo ya existe en JULES.md (tabla de checks, reglas de output, exit codes). No hay ambigüedad que explorar ni decisiones arquitectónicas que tomar. Flujo SDD mínimo.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Una vez por sesión |
| `sdd-explore` | ❌ No | — | El spec en JULES.md está completo. No hay ambigüedad que investigar |
| `sdd-propose` | ❌ No | — | Módulo mecánico. No hay decisiones arquitectónicas — el diseño está canonizado |
| `sdd-spec` | ❌ No | — | El spec funcional ya vive en JULES.md. Duplicarlo sería ruido |
| `sdd-design` | ❌ No | — | 10 checks independientes. Diseño trivial y directo |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomponer los 10 checks en tasks atómicas verificables + output JSON + integración CLI |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que cada check retorna resultado correcto, JSON parseable, exit code correcto |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

**Flujo:** `init` → `tasks` → `apply` → `verify` → `archive` ← el más corto de los módulos pendientes

```
Tareas:
- Implementar jules/linux/doctor.py
  Checks a implementar (ver tabla completa en JULES.md):
  - Ollama: servicio activo + modelos visibles + usuario correcto
  - Antigravity CLI: disponible en PATH + responde a --help
  - OpenCode CLI: disponible en PATH + responde a --help
  - LanceDB: directorio de vectores accesible + no corrupto
  - SQLite: `~/.jules/memory.sqlite3` accesible + migraciones Alembic al día
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
**Clasificación:** MECÁNICO (en superficie) / ALTA COMPLEJIDAD (en integración)
**Modelo:** GPT 5.4 / Deepseek para boilerplate
**Tiempo estimado:** 2–3 sesiones
**Depende de:** todos los módulos anteriores (0–10)

El entrypoint que conecta todo. Más lento de lo estimado en versiones anteriores — aquí aparecen los bugs que no surgieron en tests aislados.

#### Fases SDD para este módulo

> Este es el único módulo que justifica el flujo SDD completo sin excepciones. No por complejidad algorítmica, sino por superficie de integración: conecta todos los módulos, maneja asyncio+Click, gestiona Wayland/KDE, y es el primero en ejecutar el sistema end-to-end. `sdd-explore` es especialmente crítico aquí — sin mapear los contratos reales de los módulos 0–10, el apply corre ciego.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto del proyecto completo |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Mapear contratos reales de módulos 0–10, identificar gaps (¿`persist_async` tiene la firma que el CLI asume? ¿el PermissionGate tiene el contrato correcto?), verificar estado de `personality/loader.py` que no existe aún |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Decisiones reales: estructura de `personality/loader.py` + detección de cambios en `master.md`, diseño del output de `jules debug last`, cómo manejar asyncio+Click sin conflictos, cómo comunicar el modo degradado |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | El flujo principal está en JULES.md pero el spec técnico del CLI (comandos, flags, timeouts, manejo de errores por módulo, startup sequence) necesita estar escrito antes del apply |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño de `personality/loader.py` + integración asyncio/Click + estructura del logging para `jules debug last` no son triviales |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Más de 8 componentes (comandos, flujo principal, personality loader, tests e2e, verificaciones Wayland, medición de startup). Sin descomposición es fácil perderse |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación — la más grande de Fase 1 |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Flujo e2e, medición real de startup (<500ms), persistencia entre reinicios (reinicio real del proceso), que la respuesta llega ANTES de que termine la persistencia |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre — el archive debe documentar el estado final para que la Revisión Final tenga contexto |

**Flujo:** flujo SDD completo sin excepciones — `init` → `explore` → `propose` → `spec` → `design` → `tasks` → `apply` → `verify` → `archive`

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
**Modelo:** Claude Opus 4.8 (con Thinking activado)
**Tiempo estimado:** 1 sesión
**Depende de:** Módulo 11 completado + todos los checks de abajo en verde

Antes de declarar Fase 1 done, Opus revisa el proyecto completo. Es una auditoría destructiva — puede descubrir problemas en módulos ya completados (0–8) que requieran retrabajo. Esto es por diseño.

#### Fases SDD para esta revisión

> No es implementación — es validación. No genera código nuevo salvo fixes puntuales. El flujo SDD es mínimo y orientado exclusivamente a verificación.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto del proyecto para el agente que hace la auditoría |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | La revisión debe leer el sistema completo para validar contra los 20 items del checklist. Sin esto la verificación es superficial |
| `sdd-propose` | ❌ No | — | No hay decisiones nuevas — es validación de decisiones ya tomadas |
| `sdd-spec` | ❌ No | — | No genera spec nuevo |
| `sdd-design` | ❌ No | — | No genera diseño nuevo |
| `sdd-tasks` | ⚠️ Opcional | Claude Sonnet 4.6 | Útil para estructurar los 20 items del checklist como tasks verificables si el agente lo necesita |
| `sdd-apply` | ❌ Solo si hay fixes | Gemini 3.5 Flash | Solo si la revisión encuentra problemas. En ese caso: volver al módulo correspondiente, no parchear en la revisión |
| `sdd-verify` | ✅ Sí — **es la fase central** | Claude Opus 4.8 | Esto es exactamente lo que hace la revisión: validar el sistema completo contra el spec. Usar Thinking activado |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre formal de Fase 1. Gate antes de Fase 1.5 |

**Flujo:** `init` → `explore` → `verify` → `archive`

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

### Fases SDD para Fase 1.5

> Esta fase es observación y calibración, no implementación. No hay código nuevo salvo fixes puntuales detectados en uso real. El flujo SDD es mínimo.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Una vez al inicio de la fase |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Leer logs reales, datos de latencia, episodios persistidos, fallbacks ocurridos. Es la base de la calibración |
| `sdd-propose` | ⚠️ Solo si aparece un problema | Claude Opus 4.8 | Si `explore` detecta un problema de fondo (ej: scoring threshold incorrecto, retrieval degradado), entonces sí. Si todo está bien, no |
| `sdd-spec` | ⚠️ Solo si hay fix | Claude Sonnet 4.6 | Solo para documentar cambios que surjan de problemas detectados |
| `sdd-design` | ❌ No | — | Sin features nuevas, no hay diseño |
| `sdd-tasks` | ❌ No | — | Sin features nuevas |
| `sdd-apply` | ⚠️ Solo si hay fix | Gemini 3.5 Flash | Fixes puntuales. No features |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Al final de la fase: validar que los criterios de entrada a Fase 2 se cumplen |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Documentar estado real del sistema antes de entrar a Fase 2 |

**Flujo normal:** `init` → `explore` → `verify` → `archive`
**Flujo con fix:** `init` → `explore` → `propose` → `spec` → `apply` → `verify` → `archive`

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

> **Regla de esta fase:** cada item es un flujo SDD independiente. No mezclar items en la misma sesión. No usar modelos GPT desactualizados que aparecen en el bloque de orden original — los modelos aquí son la fuente de verdad.

---

### ITEM 1 — Detector de intención mejorado
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Fase 1 completa + datos reales de contexto

Más señales, más intenciones, mejor precisión. Extiende el detector simple de Módulo 7.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto del proyecto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Leer el detector actual (Módulo 7), analizar qué intenciones reales aparecen en los episodios acumulados |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué señales nuevas agregar, cómo extender sin romper el contrato actual |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Especificar las intenciones nuevas, thresholds, y cómo interactúan con la memoria |
| `sdd-design` | ⚠️ Opcional | Claude Opus 4.8 | Solo si el diseño de extensión no es obvio desde el spec |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomponer por señal nueva |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que las intenciones nuevas no generan falsos positivos sobre datos reales |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 2 — Iniciativa contextual (opt-in)
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Detector de intención mejorado + datos reales de episodios

Apagada por defecto en `config.toml`. Solo señales objetivas, nunca silencio como señal. Regla: no interrumpir dos veces por la misma razón.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Leer episodios reales acumulados para entender cuándo Jules hubiera querido interrumpir. Sin datos reales la propuesta es ficción |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué señales activan iniciativa, cómo se evita la doble interrupción, cómo es el opt-in en config |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Contrato exacto: qué activa, qué bloquea, cómo se loggea |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del mecanismo de "ya interrumpí por esto" — no trivial |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Tareas atómicas por tipo de señal |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que apagada por defecto funciona, que no interrumpe dos veces |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 3 — Automatización de entorno Linux
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Módulo 9 (permisos) completado

Integración con KDE Plasma via D-Bus/KWin. NO usar `hyprctl` (exclusivo de Hyprland). `wmctrl` con soporte parcial bajo Wayland — evaluar antes de depender. `PermissionGate` en cada acción.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Explorar qué APIs de D-Bus/KWin están disponibles en el entorno real. No asumir |
| `sdd-propose` | ✅ Sí — **obligatoria** | Claude Opus 4.8 | Decisión arquitectónica real: D-Bus vs wmctrl vs alternativas bajo Wayland. Sin esto se codea a ciegas |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Qué acciones se exponen, cómo se integra con PermissionGate, qué falla gracefully |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del adaptador Linux — abstracto para no acoplar al DE específico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por acción de entorno |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que cada acción pasa por PermissionGate y falla gracefully si el entorno no responde |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 4 — Replay system
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Motor de memoria con `model_used` bien poblado (mínimo 3 meses de datos)

Reconstrucción de sesiones de debugging. Prerequisito duro: `model_used` y `provider_used` poblados en todos los episodios.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Verificar que `model_used` está bien poblado en episodios reales. Si no está, no empezar |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Cómo se reconstruye una sesión, qué datos son necesarios, qué se puede perder |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Contrato del replay: formato, filtros, cómo se invoca |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del engine de replay — no es trivial con episodios fragmentados |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar contra sesiones reales grabadas |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 5 — Sistema de voz
**Clasificación:** MECÁNICO — Integración de terceros
**Depende de:** CLI principal (Módulo 11) completado

whisper.cpp para STT, Piper para TTS. Integración de librerías, no arquitectura nueva.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Verificar compatibilidad de whisper.cpp y Piper con el entorno real (Wayland, PipeWire) |
| `sdd-propose` | ❌ No | — | Integración mecánica. No hay decisiones arquitectónicas — el diseño es usar las APIs documentadas |
| `sdd-spec` | ❌ No | — | No hay spec nuevo — el contrato es el de las librerías |
| `sdd-design` | ❌ No | — | Mecánico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | STT + TTS + integración con CLI + tests de audio |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar latencia de STT, calidad de TTS, y que no bloquea el event loop |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 6 — Desktop app (Tauri + SvelteKit)
**Clasificación:** MECÁNICO — Interfaz gráfica
**Depende de:** CLI principal (Módulo 11) completado

Muestra: modelo activo, tier, contexto, memoria, salud del scoring. UI encima del CLI, no en paralelo.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ❌ No | — | El spec de qué muestra la UI está definido. No hay ambigüedad que explorar |
| `sdd-propose` | ❌ No | — | UI mecánica encima de datos ya existentes |
| `sdd-spec` | ❌ No | — | Idem |
| `sdd-design` | ❌ No | — | Idem |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Componentes Svelte, comunicación Tauri ↔ backend, actualizaciones en tiempo real |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que la UI no bloquea el CLI, actualizaciones en tiempo real funcionan |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 7 — Optimización de latencia cloud
**Clasificación:** MECÁNICO — Rendimiento
**Depende de:** CLI principal + datos reales de latencia medidos en Fase 1.5

Eliminar boot tax de subprocess (~2s/invocación). Daemon mode o HTTP/Sockets locales para CLIs externos.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Leer métricas reales de latencia de Fase 1.5 + explorar si Antigravity y OpenCode tienen daemon mode |
| `sdd-propose` | ❌ No | — | El problema está identificado (subprocess boot tax). La solución depende de lo que explore muestra |
| `sdd-spec` | ❌ No | — | Mecánico |
| `sdd-design` | ❌ No | — | Mecánico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por provider (Antigravity daemon, OpenCode daemon, fallback si no soporta) |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Medir latencia real antes y después. La mejora debe ser medible |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

## FASE 3 — INTELIGENCIA ADAPTATIVA

No empezar hasta tener ≥3 meses de uso real con memoria acumulada.

> **Regla de esta fase:** `sdd-explore` DEBE leer memoria real acumulada antes de cualquier propuesta. Sin datos reales, la propuesta es ficción. El flujo SDD completo es obligatorio para todos los items.

---

### ITEM 1 — Perfilador cognitivo
**Clasificación:** CRÍTICO — Algoritmia avanzada SDD
**Depende de:** ≥3 meses de episodios reales con campos bien poblados

Análisis de patrones reales: horarios, tipos de tareas, errores recurrentes.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Leer patrones reales en episodios. Sin esto el algoritmo de análisis es especulativo |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué patrones analizar, cómo agregar, cómo evitar over-fitting a una sola persona |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Definición precisa de "patrón" y cómo se expone al resto del sistema |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del motor de análisis — complejidad algorítmica real |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por tipo de patrón (horario, tarea, error) |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar contra datos reales que los patrones detectados tienen sentido |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 2 — Diff cognitivo
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo + `model_used` bien poblado en ≥6 meses de episodios

"¿Cómo resolvía esto hace 6 meses vs ahora?" Prerequisito duro: si los datos no están, no empezar.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Verificar que `model_used` está bien poblado en ≥6 meses. Si no está: no empezar |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Cómo comparar episodios de distintas épocas, qué es una diferencia significativa |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Formato del diff cognitivo, cómo se invoca, qué muestra |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del algoritmo de comparación temporal |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar con episodios reales de distintas fechas |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 3 — Eventos cognitivos calibrados
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo completado + datos reales calibrados

`frustration_detected`, `burnout_signal`, `productivity_anomaly`. Implementar sin calibración real = falsos positivos permanentes y muy difíciles de revertir.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Leer episodios reales para entender cuándo el usuario estaba frustrado vs fluido. Sin esto los umbrales son inventados |
| `sdd-propose` | ✅ Sí — **crítica** | Claude Opus 4.8 | Definir umbrales basados en datos reales. Esta propuesta es la más importante del item |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Definir los 3 eventos, sus umbrales, cómo se activan y cómo se desactivan |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del detector — no trivial con datos ruidosos |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por evento cognitivo |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí — **crítica** | Claude Opus 4.8 | Verificar contra episodios reales que los umbrales no generan falsos positivos. Esta es la fase más importante del item |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 4 — Mentoría técnica avanzada
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo completado

Sugerencias basadas en historial propio. Ej: "Para este tipo de bug resolvés mejor con Gemini Pro."

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Leer el historial real para entender qué patrones existen antes de diseñar sugerencias |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué patrones activan una sugerencia, cómo se evita ser invasivo |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | El spec debe incluir exactamente qué patrones del historial activan qué sugerencia |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Diseño del motor de sugerencias |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Verificar que las sugerencias son relevantes y no repetitivas en uso real |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

## FASE 4 — AUTONOMÍA

Construir solo si las tres fases anteriores funcionan bien en uso real.

### Fases SDD para Fase 4

> Fase 4 está intencionalmente sin especificar en detalle. Definir flujos SDD ahora sería ficción — la arquitectura dependerá de lo que se aprendió en Fases 1–3.
> **Regla:** cuando llegue el momento, empezar siempre con `sdd-init` + `sdd-explore` profundo antes de cualquier propuesta. Lo que se construya aquí debe emerger de los datos reales acumulados, no de spec previo.

**Items:** Asistencia predictiva → Adaptación profunda → Personalización autónoma.

---

> `personality/coherence.py` es Fase 2. En Fase 1 la consistencia de identidad se garantiza con `master.md` + presets por provider + tests de integración.
>
> `jules_chat.py` es solo un prototipo. El CLI principal (Módulo 11) lo reemplaza completamente.
