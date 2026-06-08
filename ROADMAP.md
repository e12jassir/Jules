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
| Shell | Verificar con `echo $SHELL` antes del Módulo 8 |
| Python | Virtualenv dedicado — obligatorio, nunca el Python del sistema |

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

### [x] MÓDULO 11 — CLI principal
**Clasificación:** MECÁNICO (en superficie) / ALTA COMPLEJIDAD (en integración) | **Estado:** ✅ Completado
**Modelo:** GPT 5.4 / Deepseek para boilerplate

El entrypoint que conecta todo. Conecta todos los módulos, maneja asyncio+Click, gestiona Wayland/KDE.

```
Comandos implementados:
  jules "tu pregunta"          # flujo principal
  jules --model MODEL "query"  # override de modelo
  jules --no-memory "query"    # sin recuperación ni persistencia
  jules memory                 # episodios recientes
  jules status                 # estado de providers y memoria
  jules doctor                 # diagnóstico completo
  jules logs --sanitized       # descartes del sanitizador
  jules logs --scoring         # historial de salud del scorer
  jules debug last             # última ejecución detallada
  jules --legacy               # TUI Textual (fallback Fase 1.5)
```

---

### [x] MÓDULO 12 — Auth OpenAI via WebSockets
**Clasificación:** CRÍTICO | **Modelo:** GPT 5.5 | **Estado:** ✅ Completado

Migración del provider `openai_oauth.py` de peticiones HTTP planas a WebSockets (`wss://chatgpt.com/backend-api/codex/responses`) usando el protocolo asíncrono (`response.create`).

**Descubrimiento crítico:** La ruta Codex requiere obligatoriamente la familia `gpt-5.4` o `gpt-5.5`. Modelos anteriores (`o3`, `gpt-4o`, `o1`) son bloqueados explícitamente.

---

### REVISIÓN FINAL DE FASE 1
**Estado:** ✅ Completada
**Modelo:** Claude Opus 4.8 (con Thinking activado)

```
Checklist de Fase 1 — todos en verde:
[✓] Jules responde en terminal sin latencia perceptible
[✓] La memoria persiste entre reinicios
[✓] El sanitizador descarta secrets
[✓] El router selecciona el modelo correcto
[✓] El fallback a Ollama funciona
[✓] La búsqueda semántica recupera por relevancia, no recencia
[✓] Llama hace el scoring (nunca modelo externo)
[✓] ScoringHealthMonitor activo y loggeable
[✓] El sistema de permisos bloquea acciones no autorizadas
[✓] Todas las migraciones Alembic aplicadas y versionadas
[✓] Sin modelos hardcodeados fuera de config.toml
[✓] El post-procesamiento corre en background
[✓] jules doctor reporta estado completo del entorno
[✓] jules debug last explica la última ejecución
[✓] Shell detectado correctamente y hooks instalados
[✓] Startup < 500ms con Ollama caliente
[✓] OpenAI auth via WebSockets funcional (M12)
```

---

## FASE 1.5 — MIGRACIÓN TUI A RUST + RATATUI 📋 Planificado

La TUI actual (Python Textual) tiene una limitación arquitectónica irresoluble: Textual pinta cada celda del terminal con color sólido, rompiendo la transparencia del compositor (Ghostty + KDE). La migración reemplaza **solo la capa de presentación** — el backend Python permanece intacto.

### Decisión de arquitectura

```
ANTES:  Python (backend) <-> Python Textual (frontend) — un proceso
AHORA:  Python (backend) <-> stdin/stdout (pipes) <-> Rust/Ratatui (frontend) — dos procesos
```

**Stack elegido:** Rust + Ratatui + Tokio + Crossterm
- **Ratatui v0.29+**: immediate mode TUI — no emite background si no se especifica, transparencia nativa garantizada por diseño
- **Tokio**: async runtime para manejar IPC con backend Python sin bloquear el event loop del TUI
- **Crossterm**: input/output terminal multiplataforma, manejo de resize
- **`cargo build --release`**: binario nativo sin runtime externo, startup sub-10ms

**Por qué Rust y no TypeScript (OpenTUI) o Node (Ink):**
- OpenTUI: proyecto experimental con API inestable — riesgo de abandono alto, documentación escasa
- Ink: requiere Node runtime (~120MB), event loop compite con Python async
- Ratatui: v0.29+, comunidad activa, modelo immediate mode resuelve la transparencia en la capa correcta
- El aprendizaje de Rust es una inversión duradera; OpenTUI no lo es

**Protocolo IPC:** stdin/stdout newline-delimited JSON
- La TUI Rust hace spawn de `python -m jules.server` al arrancar
- Comunicación bidireccional vía pipes del proceso hijo
- Sin servidor HTTP, sin socket, sin configuración de red
- Testeable con: `echo '{"type":"message","content":"hola"}' | python -m jules.server`

**Fallback:** `jules --legacy` sigue abriendo la TUI Textual hasta que la migración esté completa.

---

### Estructura de archivos

```
Jules/
├── jules/server/           ← NUEVO: servidor Python stdin/stdout
│   ├── __init__.py
│   ├── protocol.py         ← dataclasses de mensajes (tipado completo)
│   ├── server.py           ← loop asyncio: lee stdin, escribe stdout
│   └── handlers.py         ← dispatch type -> función del backend real
├── tests/integration/
│   └── test_server_ipc.py  ← NUEVO: tests del servidor aislado
└── jules-tui/              ← NUEVO: frontend Rust (crate independiente)
    ├── Cargo.toml
    ├── Cargo.lock
    └── src/
        ├── main.rs         ← entrypoint: spawn Python, event loop principal
        ├── ipc.rs          ← stdin/stdout protocol, serde_json
        ├── app.rs          ← AppState: mensajes, input, modelo activo, status
        ├── ui.rs           ← draw fn raíz (Ratatui frame)
        └── widgets/
            ├── chat_log.rs     ← mensajes + streaming token a token
            ├── input_bar.rs    ← input + history + slash command detection
            ├── sidebar.rs      ← panels: model, memory, stats
            ├── status_bar.rs   ← cwd, branch, clock, estado
            └── model_picker.rs ← overlay de selección de modelo
```

---

### Protocolo IPC — Contrato completo

> **Versión del protocolo:** `1`. El campo `protocol_version` en el handshake permite detectar incompatibilidades sin crashear.

```json
// ─── TUI → Python (stdin del proceso hijo) — una línea por mensaje ───

// Handshake: primer mensaje que envía la TUI al arrancar
{"type": "init", "protocol_version": 1}

// Flujo principal
{"type": "message",   "content": "pregunta del usuario"}
{"type": "cancel"}                                          // cancela la generación activa; no mata el proceso

// Comandos internos
{"type": "command",   "name": "sessions", "args": []}
{"type": "model_set", "provider": "google", "model": "gemini-3.5-flash-high"}
{"type": "model_list"}
{"type": "status_get"}
{"type": "quit"}


// ─── Python → TUI (stdout del proceso hijo) — una línea por mensaje ───

// Handshake: Python responde cuando está listo para recibir mensajes
{"type": "ready", "protocol_version": 1, "boot_ms": 312}

// Streaming de respuesta
{"type": "token",         "content": "hel"}
{"type": "thought",       "content": "analizando..."}
{"type": "done",          "tokens": 342}
{"type": "cancelled"}                                       // confirma que la generación fue cancelada limpiamente

// Respuesta a comandos — shape genérica
{"type": "command_result", "name": "sessions", "ok": true, "data": [...]}
{"type": "command_result", "name": "sessions", "ok": false, "error": "store unavailable"}

// Estado y configuración
{"type": "model_changed", "provider": "google", "model": "gemini-3.5-flash-high"}
{"type": "model_list",    "models": [["google", "gemini-flash"], ["ollama", "llama3.2:1b"]]}
{"type": "status",        "online": true, "episodes": 25, "scoring_healthy": true}

// Errores
{"type": "error", "message": "provider unavailable", "recoverable": true}
```

**Reglas del protocolo:**
- Si `protocol_version` del `ready` ≠ `protocol_version` del `init` → TUI muestra error y no envía más mensajes.
- `cancel` solo es válido entre un `message` y su `done`. Fuera de ese rango se ignora silenciosamente.
- Logs internos de Python van a **stderr**, nunca a stdout. stdout es exclusivo del protocolo.
- En EOF de stdout (proceso muerto) la TUI emite `IpcEvent::Died` y aplica la política de respawn definida en `AppState`.

---

### Plan de implementación detallado

#### Batch 1 — Protocolo Python (Día 1)

```
Objetivo: tener un servidor Python testeable de forma aislada antes de tocar Rust.
Todo Python puro — sin dependencias nuevas.

B1.1  jules/server/protocol.py
      - Dataclass base IpcMessage con campo `type: str`
      - Subclases: InitRequest, MessageRequest, CommandRequest, ModelSetRequest,
        ModelListRequest, StatusGetRequest, CancelRequest, QuitRequest
      - Subclases de respuesta: ReadyEvent, TokenEvent, ThoughtEvent, DoneEvent,
        CancelledEvent, CommandResultEvent, ModelChangedEvent, ModelListEvent,
        StatusEvent, ErrorEvent
      - to_json() / from_json() para cada tipo
      - Tests: round-trip serialization para cada tipo

B1.2  jules/server/handlers.py
      - handle_init(protocol_version) → ReadyEvent con boot_ms real
      - handle_message(req) → async generator que emite eventos IPC
        ← llama al router real, emite token a token
      - handle_cancel() → interrumpe la generación activa, emite CancelledEvent
      - handle_model_list() → ModelListEvent con providers reales
      - handle_model_set(provider, model) → ModelChangedEvent
      - handle_status_get() → StatusEvent con datos reales
      - handle_command(name, args) → CommandResultEvent (ok: bool, data o error)
      - handle_quit() → cierra el proceso limpiamente

B1.3  jules/server/server.py
      - loop asyncio principal:
        asyncio.get_event_loop().run_until_complete(main())
      - main(): lee stdin línea por línea (asyncio.StreamReader)
      - Deserializa JSON -> IpcMessage
      - Dispatch a handler correspondiente
      - Escribe respuestas a stdout (flush inmediato por evento)
      - Escribe logs a stderr (nunca a stdout — stdout es del protocolo)
      - Manejo de SIGTERM: flush y exit limpio

B1.4  tests/integration/test_server_ipc.py
      - Test: enviar message -> recibir tokens -> done
      - Test: enviar model_list -> recibir lista real de providers
      - Test: enviar quit -> proceso termina con exit code 0
      - Test: JSON malformado -> error event, servidor no muere
      Ejecutar: python -m jules.server < fixtures/test_message.jsonl

Verificación del batch:
  echo '{"type":"model_list"}' | python -m jules.server
  # debe imprimir: {"type":"model_list","models":[...]}
```

#### Batch 2 — Scaffold Rust + IPC (Día 2)

```
Objetivo: un binario Rust que arranque, haga spawn de Python, se comunique
vía pipes, y renderice un frame básico con Ratatui. Sin widgets complejos aún.

B2.1  jules-tui/Cargo.toml
      ratatui = "0.29"
      crossterm = { version = "0.28", features = ["event-stream"] }
      tokio = { version = "1", features = ["rt-multi-thread", "macros", "io-std", "process", "sync", "time"] }
      serde = { version = "1", features = ["derive"] }
      serde_json = "1"
      anyhow = "1"
      # Nota: NO usar features = ["full"] — infla el binario ~1.5MB extra sin beneficio.
      # Las features listadas cubren exactamente lo que usa la TUI.

B2.2  jules-tui/src/ipc.rs
      - Enum IpcEvent (mismo contrato que protocol.py — lado Rust)
      - Enum IpcCommand
      - Serializar IpcCommand -> JSON + newline -> stdin del proceso
      - Loop async: leer stdout del proceso línea por línea
      - Deserializar JSON -> IpcEvent
      - Enviar a tokio::sync::mpsc::Sender<IpcEvent>
      - Manejo de EOF: el proceso Python murió -> emitir IpcEvent::Died

B2.3  jules-tui/src/app.rs
      - Struct AppState:
          messages: Vec<ChatMessage>  (role + content + timestamp)
          input: String
          cursor_pos: usize
          active_model: String
          active_provider: String
          status_online: bool
          episodes: u32
          generating: bool
          current_token_buffer: String
          scroll_offset: u16
          show_model_picker: bool
          model_list: Vec<(String, String)>  // (provider, model)
          backend_status: BackendStatus      // Ready | Connecting | Dead(reason)
          respawn_attempts: u8               // contador para política de respawn
      - impl AppState: new(), handle_event(IpcEvent)

      **Política de respawn** (ejecutar en handle_event para IpcEvent::Died):
      - Si `respawn_attempts < 3`: esperar 1s, respawnear Python, incrementar contador.
      - Si `respawn_attempts >= 3`: marcar `backend_status = Dead("max retries")`,
        mostrar error en chat log, NO seguir reintentando.
      - Un `ready` exitoso resetea `respawn_attempts` a 0.
      - El usuario puede forzar reconexión manual (Ctrl+R) desde cualquier estado Dead.

B2.4  jules-tui/src/main.rs
      - Inicializar crossterm (raw mode, alternate screen)
      - Spawn python -m jules.server como proceso hijo con pipes
      - Lanzar tokio task: ipc::reader_loop(stdout_pipe, tx)
      - Event loop principal (tokio::select!):
          terminal.draw(|f| ui::draw(f, &state))   // render
          event = terminal_events.next()            // input teclado
          msg = rx.recv()                           // IPC events
      - En SIGTERM/Ctrl+C: enviar {"type":"quit"}, esperar proceso, restaurar terminal
      - Manejo de panic: siempre restaurar terminal antes de propagar

B2.5  Tests Rust — jules-tui/src/ipc.rs y app.rs
      - Test: deserializar JSON de cada variante de IpcEvent
      - Test: serializar cada variante de IpcCommand produce JSON correcto
      - Test: AppState::handle_event(TokenEvent) → acumula en current_token_buffer
      - Test: AppState::handle_event(DoneEvent) → mueve buffer a messages, generating=false
      - Test: AppState::handle_event(IpcEvent::Died) → sets status a disconnected
      Ejecutar: cd jules-tui && cargo test

Verificación del batch:
  cd jules-tui && cargo build
  ./target/debug/jules-tui
  # debe abrir pantalla en blanco (alternate screen), sin crash,
  # sin background visible (celda transparente)
  # Ctrl+C cierra limpiamente
```

#### Batch 3 — Chat funcional con transparencia (Día 3)

```
Objetivo: enviar un mensaje real, ver tokens streamear en tiempo real,
verificar transparencia en Ghostty con compositor Wayland.

B3.1  jules-tui/src/ui.rs — layout raíz
      Layout::vertical([
          Constraint::Length(1),    // header: "🌹 jules  |  chat"
          Constraint::Fill(1),      // chat_log
          Constraint::Length(3),    // input_bar
          Constraint::Length(1),    // status_bar
      ])
      + Layout::horizontal para sidebar (30 cols) en la zona central
      REGLA: nunca llamar .style(Style::default().bg(Color::...)) en
      la raíz del frame — dejar que el compositor haga su trabajo.

B3.2  jules-tui/src/widgets/chat_log.rs
      impl Widget for ChatLog<'_>
      - Renderizar Vec<ChatMessage> con colores del mockup:
          usuario: Color::Rgb(102, 102, 102)   // #666666
          jules:   Color::Rgb(255, 121, 198)   // #ff79c6
          body:    Color::Rgb(204, 204, 204)   // #cccccc
      - Cursor parpadeante █ al final del mensaje en generación
        (alternar visibilidad cada 500ms con tokio::time::interval)
      - Scroll: calcular visible_lines desde scroll_offset
      - Auto-scroll al fondo cuando llega nuevo token

B3.3  jules-tui/src/widgets/input_bar.rs
      impl Widget for InputBar<'_>
      - Borde: Color::Rgb(255, 121, 198) // #ff79c6 — igual que mockup
      - Fondo del input: Color::Rgb(17, 17, 17) // #111111
      - Prompt “>” en rosa, cursor de texto en posición real
      - Keybindings:
          Enter     → enviar mensaje
          Backspace → borrar carácter
          Left/Right → mover cursor
          Up/Down   → history de inputs
          Ctrl+C    → quit
          / al inicio → activar prefijo de slash command

B3.4  Verificación de transparencia (obligatoria antes de B4)
      - Abrir jules-tui en Ghostty con blur activado
      - Verificar que el fondo del terminal se ve a través de las zonas
        donde no se renderiza contenido
      - Si alguna zona tiene fondo sólido no deseado: revisar .bg() calls
      - Captura de pantalla para documentar el resultado

B3.5  Tests Rust — widgets
      - Test: ChatLog renderiza mensaje de usuario con color correcto (buffer snapshot)
      - Test: InputBar captura Backspace → borra carácter en posición correcta
      - Test: InputBar captura Enter → emite IpcCommand::Message y limpia input
      - Test: auto-scroll cuando llega nuevo token (scroll_offset = max)
      Ejecutar: cd jules-tui && cargo test

Verificación del batch:
  Escribir “hola” + Enter -> ver tokens de Jules streamear en el chat log
  La pantalla NO tiene fondo sólido visible con transparencia activa
```

#### Batch 4 — TUI completa + build (Día 4)

```
Objetivo: paridad funcional completa con la TUI Textual anterior.
Binario distribuible. jules --legacy como fallback documentado.

B4.1  jules-tui/src/widgets/status_bar.rs
      - Izquierda: "~/cwd  ↳ branch  ● Auto-saved"
      - Centro: keybindings (dim)
      - Derecha: "HH:MM  🌹"
      - Colores: igual que mockup HTML
      - Branch: leer via Command::new("git") en background cada 30s

B4.2  jules-tui/src/widgets/sidebar.rs
      Panel MODELO (arriba):
        - Nombre del modelo activo (bold, Color::Rgb(240,240,240))
        - Provider + "online" badge en verde
      Panel MEMORIA:
        - Episodios, hechos, recuerdos — actualizados via StatusEvent
      Panel ESTADÍSTICAS:
        - Tokens usados, costo sesión, tiempo sesión (ticker local)
      Sidebar colapsable: Ctrl+B toggle

B4.3  jules-tui/src/widgets/model_picker.rs
      - Overlay centrado (popup sobre el chat)
      - Lista scrollable de (provider, model) recibida via model_list
      - Filtro por teclado (fuzzy sobre el nombre)
      - Enter → enviar model_set al backend
      - Esc → cerrar sin cambiar
      - Activar: Ctrl+M

B4.4  Keybindings finales
      Ctrl+C   → quit (con confirmación si hay generación activa)
      Ctrl+M   → toggle model picker
      Ctrl+B   → toggle sidebar
      Ctrl+P   → command palette (slash commands como overlay)
      Ctrl+R   → reconectar backend (solo visible cuando backend_status = Dead)
      Tab      → cycle model (sin abrir picker)
      PgUp/Dn  → scroll chat
      Home/End → ir al principio/final del chat

B4.5  Resize handling
      Evento terminal::Event::Resize(w, h) → actualizar dimensions en AppState
      → próximo frame recalcula layout automáticamente (Ratatui lo maneja)

B4.6  cargo build --release
      - Verificar tamaño del binario (target: < 5MB sin strip, < 2MB con strip)
      - strip jules-tui/target/release/jules-tui
      - Medir startup del binario hasta primer frame: `hyperfine './target/release/jules-tui --no-spawn' 2>/dev/null`
        (--no-spawn: flag que muestra el primer frame y sale sin spawnear Python — target: < 10ms)
        Nota: el arranque *percibido* incluye Python (~300-500ms). El < 10ms mide solo el binario.
        Ambos se muestran en la status bar al arrancar.

B4.7  Integración con jules CLI
      - jules sin args → detecta que hay un TUI disponible → lanza jules-tui
      - jules --legacy → lanza la TUI Textual (jules/cli/main.py)
      - jules "query" → modo CLI legacy (respuesta en terminal, sin TUI)

B4.8  Tests Rust — integración y regresión
      - Test: ModelPicker filtra lista por texto ingresado (fuzzy match)
      - Test: Ctrl+M toggle show_model_picker en AppState
      - Test: Resize(w, h) no rompe el layout (no panic, re-render limpio)
      - Test: input de mensaje largo (>200 chars) no desborda el buffer
      - Test end-to-end mock: spawn servidor mock Python en Rust → enviar init → recibir ready → enviar message → recibir tokens → done
      Ejecutar: cd jules-tui && cargo test --all

Verificación del batch:
  Flujo completo: abrir TUI → escribir mensaje → ver streaming →
  cambiar modelo (Ctrl+M) → ver sidebar actualizar → cerrar (Ctrl+C)
  Transparencia verificada en Ghostty + KDE compositor
  cargo build --release → binario funcional
```

---

### Fases SDD por Batch

> `sdd-init` se corre UNA sola vez antes del Batch 1 y no se repite. El contexto del proyecto y el Rust toolchain quedan cacheados en Engram para todos los batches.

**sdd-init** (una vez, antes de Batch 1) — **Gemini 3.5 Flash**
Detectar stack del proyecto + verificar que Rust toolchain esté instalado (`rustc`, `cargo`). Sin esto el apply de B2 falla silenciosamente.

---

#### Batch 1 — Protocolo Python

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-explore` | ❌ No | — | El protocolo ya está completamente especificado en el ROADMAP. No hay ambigüedad que investigar |
| `sdd-propose` | ❌ No | — | Las decisiones ya están tomadas: dataclasses, stdin/stdout, newline-delimited JSON |
| `sdd-spec` | ❌ No | — | El contrato IPC está canonizado arriba. Duplicarlo sería ruido |
| `sdd-design` | ❌ No | — | Python puro, sin arquitectura nueva. Diseño trivial |
| `sdd-tasks` | ✅ Sí | **Claude Sonnet 4.6** | Descomponer B1.1–B1.4 en tasks atómicas con archivos y firmas exactas |
| `sdd-apply` | ✅ Sí | **Gemini 3.5 Flash** | Implementación mecánica: dataclasses + loop asyncio + handlers |
| `sdd-verify` | ✅ Sí | **Claude Sonnet 4.6** | Verificar round-trip JSON de cada tipo + que stdout queda libre de logs |
| `sdd-archive` | ✅ Sí | **Gemini Flash-Lite** | Persistir contrato para que B2 lo use como referencia |

**Flujo:** `tasks` → `apply` → `verify` → `archive`

---

#### Batch 2 — Scaffold Rust + IPC

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-explore` | ✅ Sí | **Gemini 3.1 Pro** | Leer API de Ratatui 0.29 + Crossterm 0.28 + tokio::process. Hay detalles no obvios en cómo Crossterm maneja raw mode junto con tokio::select! |
| `sdd-propose` | ❌ No | — | La arquitectura (AppState + mpsc + ipc task) ya está definida en el ROADMAP |
| `sdd-spec` | ❌ No | — | Los contratos de AppState e IpcEvent están en el ROADMAP con suficiente precisión |
| `sdd-design` | ✅ Sí | **Claude Opus 4.8** | El event loop con `tokio::select!` sobre tres fuentes (terminal events, IPC channel, tick timer) tiene edge cases reales de ordering y cancellation. Merece diseño explícito antes del apply |
| `sdd-tasks` | ✅ Sí | **Claude Sonnet 4.6** | Descomponer B2.1–B2.5 en tasks con tipos Rust exactos |
| `sdd-apply` | ✅ Sí | **Claude Sonnet 4.6** | Rust con diseño no trivial — Sonnet entiende el borrow checker mejor que Flash para este scope |
| `sdd-verify` | ✅ Sí | **Claude Opus 4.8** | Verificar: spawn Python + handshake exitoso + primer frame sin background sólido + tests pasan |
| `sdd-archive` | ✅ Sí | **Gemini Flash-Lite** | Cierre |

**Flujo:** `explore` → `design` → `tasks` → `apply` → `verify` → `archive`

---

#### Batch 3 — Chat funcional + transparencia

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-explore` | ❌ No | — | La API de Ratatui ya se estudió en B2. No hay nuevo territorio |
| `sdd-propose` | ❌ No | — | El diseño de widgets y colores está en el ROADMAP con referencias al mockup HTML |
| `sdd-spec` | ❌ No | — | Los contratos de cada widget están suficientemente definidos |
| `sdd-design` | ⚠️ Breve | **Claude Sonnet 4.6** | Solo si la verificación de transparencia de B3.4 encuentra un problema. En ese caso, diseñar la solución antes de parchear a ciegas |
| `sdd-tasks` | ✅ Sí | **Claude Sonnet 4.6** | Descomponer B3.1–B3.5 en tasks con traits Ratatui exactos |
| `sdd-apply` | ✅ Sí | **Claude Sonnet 4.6** | Widgets con rendering Ratatui — requiere conocimiento del modelo immediate mode |
| `sdd-verify` | ✅ Sí | **Claude Opus 4.8** | CRÍTICO: verificar transparencia en Ghostty real + streaming token a token funciona. No se puede automatizar — requiere inspección visual |
| `sdd-archive` | ✅ Sí | **Gemini Flash-Lite** | Cierre + captura de pantalla de transparencia como evidencia |

**Flujo:** `tasks` → `apply` → `verify` → `archive` (+ `design` solo si transparencia falla)

---

#### Batch 4 — TUI completa + build

| Fase | ¿Correr? | Modelo | Razón |
|---|---|---|---|
| `sdd-explore` | ❌ No | — | No hay territorio nuevo: widgets adicionales sobre la base de B3 |
| `sdd-propose` | ❌ No | — | Sin decisiones arquitectónicas nuevas |
| `sdd-spec` | ❌ No | — | Contratos de ModelPicker, Sidebar y StatusBar están en el ROADMAP |
| `sdd-design` | ❌ No | — | Extensión mecánica de widgets existentes |
| `sdd-tasks` | ✅ Sí | **Claude Sonnet 4.6** | Descomponer B4.1–B4.8 incluyendo integración CLI (`jules` sin args) y `--no-spawn` |
| `sdd-apply` | ✅ Sí | **Gemini 3.5 Flash** | Widgets adicionales + keybindings + resize: mecánico una vez que B2/B3 están sólidos |
| `sdd-verify` | ✅ Sí | **Claude Opus 4.8** | Verificar paridad funcional completa con TUI Textual + flujo end-to-end + binario release |
| `sdd-archive` | ✅ Sí | **Gemini Flash-Lite** | Cierre final + marcar `jules/cli/` Textual como deprecated en AGENT.md |

**Flujo:** `tasks` → `apply` → `verify` → `archive`

---

### Criterio de DONE — Fase 1.5

```
- [ ] `jules` (binario Rust compilado) abre TUI sin error
- [ ] Transparencia verificada en Ghostty + KDE compositor (captura de pantalla)
- [ ] Paridad funcional completa con TUI Textual anterior
- [ ] Streaming token a token funciona vía IPC (stdin/stdout pipes)
- [ ] Slash commands funcionan vía IPC
- [ ] Model picker (Ctrl+M) funciona con datos reales
- [ ] Sidebar actualiza con datos reales de memoria y modelo
- [ ] Degradación graceful: backend muerto = mensaje de error visible, no crash
- [ ] Respawn automático: hasta 3 intentos con 1s de espera entre cada uno; después muestra error y espera Ctrl+R
- [ ] Startup TUI < 10ms (medido con `time`)
- [ ] Backend Python listo < 500ms (medido en status bar)
- [ ] `cargo build --release` produce binario sin dependencias externas
- [ ] `jules --legacy` sigue abriendo TUI Textual
- [ ] Tests del servidor Python pasan (test_server_ipc.py)
- [ ] Tests IPC Rust pasan (mock del servidor)
- [ ] Resize del terminal no rompe el layout
```

### Criterio de entrada a Fase 2

```
- [ ] Fase 1.5 DONE completo
- [ ] 1 semana de uso real en workflow diario con la TUI Rust
- [ ] ≥50 mensajes procesados vía IPC sin errores
- [ ] Binario distribuible testeado en instalación limpia
- [ ] jules/cli/ (Textual) marcado como deprecated en AGENT.md
```

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
