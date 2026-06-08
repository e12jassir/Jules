# ROADMAP.md
## Versión 1.5
## Plan de Construcción — Jules

> **Principio:** Cada módulo debe funcionar y estar testeado antes de construir el siguiente.
> Un módulo roto que avanza es deuda que mata el proyecto.

---

## ENTORNO DE DESARROLLO

| Componente | Valor |
|---|---|
| OS | EndeavourOS (rolling release) |
| Escritorio | KDE Plasma 6 + Wayland |
| Compositor | Ghostty + KDE compositor con transparencia |
| Shell | Detectado en runtime — fish / zsh / bash |
| Python | Virtualenv dedicado — obligatorio, nunca el Python del sistema |
| Bun | Requerido para Fase 1.5 (TUI migration) |

---

## MODELOS POR FASE SDD

> Los modelos asignados por fase están en `AGENT.md` → sección **MODELOS POR FASE SDD — REGLA INVIOLABLE**.
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

## FASE 1 — NÚCLEO ✅ COMPLETADA

El objetivo de Fase 1 es simple: Jules responde en terminal, recuerda entre sesiones, conoce su entorno, y no filtra secrets. Nada más.

---

### [x] MÓDULO 0 — Estructura base del proyecto
**Clasificación:** MECÁNICO | **Estado:** ✅ Completado

### [x] MÓDULO 1 — Sanitizador
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 2 — Modelos de datos
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 3 — Provider local Ollama
**Clasificación:** MECÁNICO | **Estado:** ✅ Completado

### [x] MÓDULO 4 — Providers externos
**Clasificación:** MECÁNICO | **Estado:** ✅ Completado

### [x] MÓDULO 5 — Router quota-aware
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 6 — Motor de memoria
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 7 — Detector de intención de contexto
**Clasificación:** MECÁNICO | **Estado:** ✅ Completado

### [x] MÓDULO 8 — Sistema de eventos
**Clasificación:** SEMI-CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 9 — Sistema de permisos
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado

### [x] MÓDULO 10 — jules doctor
**Clasificación:** MECÁNICO | **Estado:** ✅ Completado

### [x] MÓDULO 11 — CLI principal (TUI Textual)
**Clasificación:** MECÁNICO/ALTA COMPLEJIDAD | **Estado:** ✅ Completado
**Nota:** TUI funcional con Textual. Reemplazado en Fase 1.5 por limitación arquitectónica irresoluble: Textual pinta cada celda con color sólido, rompiendo la transparencia del compositor (Ghostty + KDE).
**Pendiente menor:** inyección de chat history en el prompt al inicio de sesión.

### [x] MÓDULO 12 — Auth OpenAI via WebSockets
**Clasificación:** CRÍTICO | **Estado:** ✅ Completado
**Nota:** `openai_oauth.py` migrado a WebSockets (`wss://chatgpt.com/backend-api/codex/responses`). Requiere familia `gpt-5.4+` o `gpt-5.5+` — modelos anteriores bloqueados en esa ruta.

### REVISIÓN FINAL DE FASE 1
**Modelo:** Claude Opus 4.8 (con Thinking activado) | **Estado:** ⏳ Pendiente

Auditoría destructiva del sistema completo. Puede descubrir problemas en módulos ya completados que requieran retrabajo. Esto es por diseño.

| Fase | ¿Correr? | Modelo |
|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro |
| `sdd-verify` | ✅ Sí — **fase central** | Claude Opus 4.8 |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite |

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
- [ ] Shell detectado correctamente y hooks instalados para ese shell
- [ ] Límite de inotify verificado y configurado
- [ ] Ollama corre bajo el usuario correcto — verificado
- [ ] Startup < 500ms con Ollama caliente — medido
- [ ] Las fallas de memoria degradan, no rompen la respuesta
- [ ] El virtualenv está aislado y requirements.lock está actualizado
- [ ] Chat history se inyecta en el prompt al iniciar sesión
```

Si algo falla: arreglar antes de avanzar a Fase 1.5.

---

## FASE 1.5 — MIGRACIÓN TUI A RUST + RATATUI 🔜 Próxima

La TUI actual (Python Textual) tiene una limitación arquitectónica irresoluble: Textual pinta cada celda del terminal con color sólido, rompiendo la transparencia del compositor (Ghostty + KDE). La migración reemplaza **solo la capa de presentación** — el backend Python permanece intacto.

### Decisión de arquitectura

```
ANTES:  Python (backend) <-> Python Textual (frontend) — un proceso
AHORA:  Python (backend) <-> stdin/stdout (pipes) <-> Rust/Ratatui (frontend) — dos procesos
```

**Stack elegido:** Rust + Ratatui + Tokio + Crossterm
- **Ratatui**: immediate mode TUI — no emite background si no se especifica, transparencia nativa garantizada por diseño
- **Tokio**: async runtime para manejar el IPC con el backend Python sin bloquear el event loop del TUI
- **Crossterm**: manejo de input/output terminal multiplataforma
- **`cargo build --release`**: produce un binario nativo único sin runtime externo, startup sub-10ms

**Por qué Rust y no TypeScript (OpenTUI) o Node (Ink):**
- OpenTUI: proyecto experimental con API inestable — riesgo de abandono alto
- Ink: requiere Node runtime (~120MB), event loop compite con Python async
- Ratatui: v0.29+, comunidad activa, modelo immediate mode resuelve la transparencia en la capa correcta
- Aprendizaje de Rust es una inversión duradera; OpenTUI no lo es

**Protocolo**: stdin/stdout newline-delimited JSON (v1)
- La TUI Rust hace spawn de `python -m jules.server` al arrancar
- Comunicación bidireccional via pipes del proceso hijo
- Sin servidor HTTP, sin socket, sin configuración de red
- Testeable con: `echo '{"type":"message","content":"hola"}' | python -m jules.server`

### Estructura de archivos

```
Jules/
├── jules/                  <- backend Python, SIN CAMBIOS
├── jules/server/           <- NUEVO: servidor stdin/stdout (asyncio)
│   ├── __init__.py
│   ├── server.py           <- loop: lee stdin, escribe stdout
│   ├── handlers.py         <- dispatch type -> función del backend
│   └── protocol.py         <- dataclasses de mensajes (tipado)
├── tests/                  <- tests Python, SIN CAMBIOS
└── jules-tui/              <- NUEVO: frontend Rust
    ├── Cargo.toml
    ├── Cargo.lock
    └── src/
        ├── main.rs         <- entrypoint: spawn Python, IPC loop, event loop
        ├── ipc.rs          <- stdin/stdout protocol, (de)serialization
        ├── app.rs          <- AppState: mensajes, modelo activo, input
        ├── ui.rs           <- draw fn raíz (Ratatui frame)
        └── widgets/
            ├── chat_log.rs
            ├── input_bar.rs
            ├── sidebar.rs
            ├── status_bar.rs
            └── model_picker.rs
```

### Protocolo IPC — stdin/stdout newline-delimited JSON

```json
// TUI → Python (stdin del proceso hijo)
{"type": "message", "content": "pregunta del usuario"}
{"type": "command", "name": "sessions", "args": []}
{"type": "model_set", "provider": "google", "model": "gemini-3.5-flash-high"}
{"type": "model_list"}
{"type": "status_get"}
{"type": "quit"}

// Python → TUI (stdout del proceso hijo)
{"type": "token", "content": "hel"}
{"type": "thought", "content": "analyzing..."}
{"type": "done", "tokens": 342}
{"type": "model_changed", "provider": "google", "model": "gemini-3.5-flash-high"}
{"type": "model_list", "models": [["google", "gemini-3.5-flash-high"], ["ollama", "llama3.2:1b"]]}
{"type": "status", "online": true, "episodes": 25, "scoring_healthy": true}
{"type": "error", "message": "provider unavailable", "recoverable": true}
```

### Fases SDD

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto del proyecto + testing capabilities |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Estudiar Ratatui API, diseñar contrato IPC, mapear widgets actuales |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Decisiones: modelo de estado AppState, manejo de async Tokio, layout Ratatui |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Spec formal del protocolo stdin/stdout + contratos de cada widget |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Arquitectura Rust: AppState, event loop, IPC reader task, draw cycle |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Breakdown por batch de implementación |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación incremental por batch |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Paridad funcional con TUI Textual + transparencia verificada |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre + estado para Fase 2 |

### Orden de implementación

```
Batch 1 — Protocolo Python (1 día):
  1. jules/server/protocol.py — dataclasses de mensajes con tipado
  2. jules/server/server.py — loop asyncio: lee stdin, escribe stdout
  3. jules/server/handlers.py — dispatch type -> función del backend real
  4. Tests del server: `echo '{...}' | python -m jules.server`

Batch 2 — Scaffold Rust + IPC (1 día):
  5. Cargo.toml con ratatui + tokio + crossterm + serde_json
  6. main.rs: spawn proceso Python, pipes bidireccionales
  7. ipc.rs: deserialización JSON, canal tokio::sync::mpsc -> event loop
  8. app.rs: AppState struct (mensajes, input, modelo activo, status)
  9. Loop principal: tokio::select! sobre eventos de terminal e IPC

Batch 3 — Chat funcional (1 día):
  10. ui.rs: layout raíz (header + chat + input + status)
  11. widgets/chat_log.rs: renderizado de mensajes, scroll, streaming token a token
  12. widgets/input_bar.rs: input con history, slash command prefix detection
  13. Transparencia verificada en Ghostty — sin background en ninguna celda

Batch 4 — Completar TUI (1 día):
  14. widgets/model_picker.rs: overlay de selección de modelo
  15. widgets/sidebar.rs: panels colapsables (model, memory, stats)
  16. widgets/status_bar.rs: cwd, branch, clock, estado de scoring
  17. Keybindings: Tab cycle model, Ctrl+P command palette, Ctrl+C quit
  18. Resize handling
  19. cargo build --release -> binario distribuible
  20. `jules --legacy` sigue abriendo TUI Textual
```

### Estabilización backend (en paralelo con Batch 1)

```
- [ ] Completar inyección de chat history en el prompt (pendiente de M11)
- [ ] Medir y documentar latencia real de providers
- [ ] Calibrar scoring threshold con episodios reales
- [ ] Confirmar sanitizador sin falsos positivos en uso diario
```

### Criterio de DONE

```
- [ ] `jules` (binario Rust compilado) abre TUI sin error
- [ ] Terminal transparency funciona (verificado en Ghostty + KDE compositor)
- [ ] Paridad funcional completa con TUI Textual actual
- [ ] Streaming token a token funciona via IPC
- [ ] Slash commands funcionan via IPC
- [ ] Model picker interactivo funciona
- [ ] Sidebar con panels de modelo y memoria
- [ ] Degradación graceful cuando backend no responde (backend muerto = mensaje de error, no crash)
- [ ] Startup < 10ms (TUI Rust) + < 500ms (backend Python listo)
- [ ] `cargo build --release` produce binario distribuible sin dependencias externas
- [ ] Fallback: `jules --legacy` sigue abriendo la TUI Textual
- [ ] Tests del server Python pasan
- [ ] Tests del IPC (mock del servidor) pasan en Rust
```

### Criterio de entrada a Fase 2

```
- [ ] Fase 1.5 DONE completo
- [ ] 1 semana de uso real del TUI nuevo en workflow diario
- [ ] >=50 mensajes procesados via IPC sin errores
- [ ] Binario distribuible testeado en instalación limpia
- [ ] jules/cli/ (Textual) marcado como deprecated
```

---

## FASE 2 — EXPANSIÓN

No empezar hasta que Fase 1 y Fase 1.5 estén 100% done y usándose en el workflow diario real.

> **Regla de esta fase:** cada item es un flujo SDD independiente. No mezclar items en la misma sesión.

---

### ITEM 1 — Detector de intención mejorado
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Fase 1 completa + datos reales de contexto acumulados

Más señales, más intenciones, mejor precisión. Extiende el detector simple de Módulo 7.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Leer el detector actual + intenciones reales en episodios acumulados |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué señales nuevas agregar, cómo extender sin romper el contrato actual |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Intenciones nuevas, thresholds, interacción con memoria |
| `sdd-design` | ⚠️ Opcional | Claude Opus 4.8 | Solo si el diseño de extensión no es obvio desde el spec |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por señal nueva |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Sin falsos positivos sobre datos reales |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 2 — Iniciativa contextual (opt-in)
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Detector de intención mejorado + datos reales de episodios

Apagada por defecto en `config.toml`. Solo señales objetivas. Regla: no interrumpir dos veces por la misma razón.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Episodios reales para entender cuándo Jules hubiera querido interrumpir |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Señales que activan iniciativa, mecanismo anti-doble-interrupción, opt-in |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Contrato exacto: qué activa, qué bloquea, cómo se loggea |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Mecanismo "ya interrumpí por esto" — no trivial |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por tipo de señal |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Apagada por defecto funciona, no interrumpe dos veces |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 3 — Automatización de entorno Linux (KDE/Wayland)
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Módulo 9 (permisos) completado

Integración con KDE Plasma via D-Bus/KWin. `PermissionGate` en cada acción. No usar `hyprctl` (exclusivo de Hyprland). Evaluar `wmctrl` — soporte parcial bajo Wayland.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Explorar APIs D-Bus/KWin disponibles en el entorno real |
| `sdd-propose` | ✅ Sí — **obligatoria** | Claude Opus 4.8 | D-Bus vs wmctrl vs alternativas bajo Wayland — decisión arquitectónica real |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Acciones expuestas, integración con PermissionGate, degradación |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Adaptador Linux abstracto — no acoplar al DE específico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por acción de entorno |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Cada acción pasa por PermissionGate, falla gracefully |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 4 — Replay system
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** `model_used` y `provider_used` bien poblados en >=3 meses de episodios reales

Reconstrucción de sesiones de debugging. Si los datos no están, no empezar.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Verificar que `model_used` está bien poblado en episodios reales |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Cómo reconstruir una sesión, qué datos son necesarios |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Formato del replay, filtros, invocación |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Engine de replay con episodios fragmentados |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Contra sesiones reales grabadas |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 5 — Sistema de voz
**Clasificación:** MECÁNICO — Integración de terceros
**Depende de:** CLI principal completado

whisper.cpp para STT, Piper para TTS.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Verificar compatibilidad con Wayland + PipeWire en el entorno real |
| `sdd-propose` | ❌ No | — | Integración mecánica |
| `sdd-spec` | ❌ No | — | El contrato es el de las librerías |
| `sdd-design` | ❌ No | — | Mecánico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | STT + TTS + integración con CLI + tests |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Latencia STT, calidad TTS, sin bloquear event loop |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 6 — Desktop overlay (Tauri + SvelteKit)
**Clasificación:** MECÁNICO — Interfaz gráfica
**Depende de:** Fase 1.5 completada

UI encima del CLI — modelo activo, tier, contexto, memoria, salud del scoring. Complementa la TUI, no la reemplaza.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ❌ No | — | El spec de qué muestra la UI está definido |
| `sdd-propose` | ❌ No | — | UI mecánica encima de datos ya existentes |
| `sdd-spec` | ❌ No | — | Idem |
| `sdd-design` | ❌ No | — | Idem |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Componentes Svelte, comunicación Tauri <-> backend, actualizaciones en tiempo real |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | No bloquea CLI, actualizaciones en tiempo real funcionan |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 7 — Optimización de latencia (daemon mode)
**Clasificación:** MECÁNICO — Rendimiento
**Depende de:** Datos reales de latencia medidos en Fase 1.5

Eliminar boot tax de subprocess (~2s/invocación). Daemon mode o sockets locales para CLIs externos.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Métricas reales de latencia + explorar si los CLIs externos tienen daemon mode |
| `sdd-propose` | ❌ No | — | La solución depende de lo que explore muestra |
| `sdd-spec` | ❌ No | — | Mecánico |
| `sdd-design` | ❌ No | — | Mecánico |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por provider |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Medir latencia antes y después — la mejora debe ser medible |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 8 — Jerarquía interactiva de providers en TUI
**Clasificación:** UX — Mejora TUI
**Depende de:** Fase 1.5 completada (nuevo TUI en OpenTUI)

Refactorizar `/model` en árbol interactivo: `/provider <categoría>` (cli | oauth | api | local) -> modal de providers -> autocompletado de modelos según provider activo.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí | Gemini 3.1 Pro | Leer implementación actual del model picker en OpenTUI |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Diseño UX del árbol interactivo |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Spec de interacción |
| `sdd-design` | ❌ No | — | Mecánico una vez el spec está claro |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por nivel del árbol |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | UX fluida en el TUI nuevo |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

## FASE 3 — INTELIGENCIA ADAPTATIVA

No empezar hasta tener >=3 meses de uso real con memoria acumulada.

> **Regla de esta fase:** `sdd-explore` DEBE leer memoria real acumulada antes de cualquier propuesta. Sin datos reales, la propuesta es ficción.

---

### ITEM 1 — Perfilador cognitivo
**Clasificación:** CRÍTICO — Algoritmia avanzada
**Depende de:** >=3 meses de episodios reales con campos bien poblados

Análisis de patrones reales: horarios, tipos de tareas, errores recurrentes.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Leer patrones en episodios reales. Sin esto el algoritmo es especulativo |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué patrones analizar, cómo evitar over-fitting |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Definición precisa de "patrón" |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Motor de análisis — complejidad algorítmica real |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por tipo de patrón (horario, tarea, error) |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Patrones detectados tienen sentido sobre datos reales |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 2 — Diff cognitivo
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo + `model_used` en >=6 meses de episodios

"¿Cómo resolvía esto hace 6 meses vs ahora?" Prerequisito duro: si los datos no están, no empezar.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Verificar >=6 meses de `model_used` poblado |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Cómo comparar episodios de distintas épocas |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Formato del diff, invocación, qué muestra |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Algoritmo de comparación temporal |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Con episodios reales de distintas fechas |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 3 — Eventos cognitivos calibrados
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo completado + datos calibrados

`frustration_detected`, `burnout_signal`, `productivity_anomaly`. Sin calibración real = falsos positivos permanentes.

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Cuándo el usuario estaba frustrado vs fluido en datos reales |
| `sdd-propose` | ✅ Sí — **crítica** | Claude Opus 4.8 | Umbrales basados en datos reales — la propuesta más importante del item |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Los 3 eventos, umbrales, activación y desactivación |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Detector con datos ruidosos |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Por evento cognitivo |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí — **crítica** | Claude Opus 4.8 | Sin falsos positivos sobre episodios reales |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

### ITEM 4 — Mentoría técnica avanzada
**Clasificación:** CRÍTICO — Diseño SDD
**Depende de:** Perfilador cognitivo completado

Sugerencias basadas en historial propio. Ej: "Para este tipo de bug resolvés mejor con Gemini Pro."

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-init` | ✅ Sí | Gemini 3.5 Flash | Contexto |
| `sdd-explore` | ✅ Sí — **obligatoria** | Gemini 3.1 Pro | Qué patrones existen en el historial real |
| `sdd-propose` | ✅ Sí | Claude Opus 4.8 | Qué patrones activan sugerencia, cómo evitar ser invasivo |
| `sdd-spec` | ✅ Sí | Claude Sonnet 4.6 | Qué patrones del historial activan qué sugerencia |
| `sdd-design` | ✅ Sí | Claude Opus 4.8 | Motor de sugerencias |
| `sdd-tasks` | ✅ Sí | Claude Sonnet 4.6 | Descomposición atómica |
| `sdd-apply` | ✅ Sí | Gemini 3.5 Flash | Implementación |
| `sdd-verify` | ✅ Sí | Claude Opus 4.8 | Sugerencias relevantes y no repetitivas en uso real |
| `sdd-archive` | ✅ Sí | Gemini 3.1 Flash-Lite | Cierre |

---

## FASE 4 — AUTONOMÍA

Construir solo si las tres fases anteriores funcionan bien en uso real y prolongado.

> Fase 4 está intencionalmente sin especificar en detalle. Lo que se construya aquí debe emerger de los datos reales acumulados en Fases 1–3, no de spec previo.
> **Regla:** cuando llegue el momento, empezar siempre con `sdd-init` + `sdd-explore` profundo antes de cualquier propuesta.

**Items tentativos:** asistencia predictiva -> adaptación profunda -> personalización autónoma.

---

> `personality/coherence.py` es Fase 2. En Fase 1 la consistencia de identidad se garantiza con `master.md` + presets por provider + tests de integración.
>
> `jules_chat.py` es un prototipo. El CLI principal (Módulo 11) lo reemplaza completamente.
>
> `jules/cli/` (Textual) se mantiene como fallback hasta completar Fase 1.5, luego se marca deprecated.
