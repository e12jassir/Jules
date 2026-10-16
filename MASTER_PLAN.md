# MASTER_PLAN.md — Especificación Ejecutable para Agentes de IA
## Proyecto: JULES (Living OS Cognitive Layer & Local-First Jarvis Architecture)

> **INSTRUCCIÓN CRÍTICA PARA EL AGENTE DE IA:**
> Este documento es la hoja de ruta técnica y especificación de implementación de Jules.
> Tu trabajo no es rediseñar ni debatir la arquitectura: es **ejecutar cada Fase y Tarea en estricto orden secuencial**, escribiendo el código y los tests indicados y respetando las reglas inviolables de `AGENT.md` y `JULES.md`.
> Ninguna fase se da por terminada hasta que `pytest` pase al 100% en verde.

---

## 0. REGLAS INVIOLABLES DEL AGENTE (HEREDADAS DE `AGENT.md` Y `JULES.md`)

1. **Sanitizador primero, siempre:** Ningún input (texto, voz transcrita, comando de shell, portapapeles o OCR/visión) llega a memoria, router o provider sin pasar por `Sanitizer.check()` primero.
2. **Latencia cero al usuario:** Toda persistencia, scoring, consolidación de memoria y embeddings corren en `asyncio.create_task()` en segundo plano después de entregar la respuesta.
3. **Scoring y Consolidación 100% Locales:** `evaluate_importance()` y la extracción de hechos corren exclusivamente en Ollama local (`TaskType.MEMORY_SCORING` / `TaskType.IDENTITY`), jamás gastando cuota externa.
4. **Encapsulamiento de Providers:** Ningún módulo instancia un provider directamente; todo pasa por `CognitiveRouter` (`route`, `ask_with_fallback`, `stream_with_fallback`).
5. **SQLite es la Fuente de Verdad; LanceDB es el Índice:** Primero se guarda en SQLite (`PersistentMemory`) con migración `Alembic` al día; luego se indexa en `LanceDB` (`EpisodicMemory`). Si LanceDB falla o cambia la dimensión del vector, se reconstruye desde SQLite.
6. **Gobierno de Acciones (`PermissionGate`):** Ningún comando de shell, herramienta MCP o acción del sistema operativo se ejecuta sin invocar primero `await gate.check(action, target, cwd)`.
7. **Filosofía UNIX & Cero Infraestructura Pesada:** Prohibido introducir Docker, Redis o servidores web pesados. Toda comunicación entre procesos usa `asyncio` y UNIX Domain Sockets (`/run/user/$UID/jules.sock`).
8. **Congelamiento de `jules-tui` (Rust):** El directorio `jules-tui/` permanece intacto con sus 23 tests en verde; no modificarlo durante la ejecución de este plan.

---

## 1. MAPA DE ARQUITECTURA OBJETIVO (ESTRUCTURA DE ARCHIVOS)

```text
jules/
├── auth/                        # [EXISTENTE] OAuth PKCE y Device Code (OpenAI, Claude)
├── sanitizer/                   # [EXISTENTE] Filtro de secrets y credenciales
├── personality/
│   ├── loader.py                # [EXISTENTE] Carga master.md + preset por provider
│   └── coherence.py             # [COMPLETAR] Verificador de identidad + Modo Abogado del Diablo
├── core/
│   ├── config.py                # [MODIFICAR] Añadir secciones [voice], [daemon], [perception], [initiative]
│   ├── context.py               # [MODIFICAR] Enriquecer con ventana activa, errores de shell y telemetría
│   ├── events.py                # [MODIFICAR] Añadir eventos de voz, errores repetidos, recursos y foco
│   ├── permissions.py           # [MODIFICAR] Añadir confirmación por voz + notify-send
│   ├── provider_registry.py     # [EXISTENTE] Catálogo de proveedores y modelos
│   ├── router.py                # [MODIFICAR] Añadir TaskType.VISION y TaskType.TOOL_USE
│   ├── session.py               # [MODIFICAR] Historial de comandos con exit_code, stderr_snippet y duración
│   └── chat_engine.py           # [NUEVO] Cerebro central desacoplado de la TUI
├── memory/
│   ├── models.py                # [MODIFICAR] Añadir PersistentFactORM y CommandTraceORM
│   ├── persistent.py            # [MODIFICAR] CRUD de hechos persistentes y reconstrucción de vectores
│   ├── episodic.py              # [MODIFICAR] Migrar a nomic-embed-text (768d) + auto-rebuild
│   ├── scoring.py               # [EXISTENTE] Evaluador de importancia + ScoringHealthMonitor
│   ├── engine.py                # [MODIFICAR] Integrar extracción de hechos y rebuild de LanceDB
│   ├── consolidation.py         # [NUEVO] "Ciclo de Sueño REM" (destila Episodios -> Hechos) y Morning Briefing
│   └── replay.py                # [NUEVO] "Git para pensamiento técnico": reconstrucción causal de debugging
├── daemon/
│   ├── __init__.py              # [NUEVO]
│   ├── ipc.py                   # [NUEVO] Servidor/Cliente UNIX Domain Socket + archivo de estado
│   ├── state.py                 # [NUEVO] Emisor de estado en tiempo real (/run/user/$UID/jules.state)
│   └── service.py               # [NUEVO] Bucle principal residente en RAM + generador systemd --user
├── voice/
│   ├── __init__.py              # [NUEVO]
│   ├── listener.py              # [NUEVO] Captura de audio + VAD (Silero/WebRTC) + Push-to-Talk + WakeWord
│   ├── transcriber.py           # [NUEVO] STT 100% local con faster-whisper INT8
│   ├── speaker.py               # [NUEVO] TTS en streaming por oraciones (Kokoro/Piper) + Barge-in
│   └── pipeline.py              # [NUEVO] Orquestador full-duplex de voz (<1.5s latencia)
├── perception/
│   ├── __init__.py              # [NUEVO]
│   ├── vision.py                # [NUEVO] Captura de pantalla/ventana bajo demanda (Wayland grim / X11 maim)
│   ├── clipboard.py             # [NUEVO] Lectura segura de portapapeles (wl-paste / xclip) + Sanitizer
│   └── telemetry.py             # [NUEVO] Conciencia de salud del OS (RAM, CPU, disco, systemd journal)
├── platform/
│   ├── doctor.py                # [MODIFICAR] Añadir chequeos de daemon, audio, TTS/STT y nomic-embed
│   ├── shell.py                 # [MODIFICAR] Conectar hooks precmd/preexec reales vía socket IPC
│   ├── watcher.py               # [EXISTENTE] Watcher de archivos con control de inotify
│   ├── dbus.py                  # [COMPLETAR] Control multimedia MPRIS (playerctl) y modo Focus/DND
│   └── initiative.py            # [NUEVO] Motor de Iniciativa Contextual ("Fantasma en la Shell")
└── mcp/
    ├── __init__.py              # [NUEVO]
    ├── client.py                # [NUEVO] Cliente Model Context Protocol gobernado por PermissionGate
    └── builtin_tools.py         # [NUEVO] Herramientas nativas del sistema (ejecución segura, git, multimedia)
```

---

## 2. FASES DE IMPLEMENTACIÓN PASO A PASO

### FASE 1: Desacoplamiento Cognitivo y Re-ingeniería de Memoria Semántica

**Objetivo:** Liberar el cerebro de Jules de la interfaz gráfica (`jules/cli/app.py`) y solucionar la precisión de embeddings detectada en `spike_embeddings.py`.

#### Tarea 1.1: [x] Crear `jules/core/chat_engine.py`
- **QUÉ hacer:** Extraer toda la lógica de negocio que hoy vive en `JulesApp.process_message`, `JulesApp._stream_response`, `_retrieve_memory_references`, `_persist_episode_background` y `_compose_prompt` dentro de `jules/cli/app.py` hacia una clase independiente `ChatEngine`.
- **CÓMO hacerlo:**
  1. Definir `class ChatEngine` recibiendo `router: CognitiveRouter`, `memory_engine: MemoryEngine`, `personality_loader: PersonalityLoader`, `sanitizer: type[Sanitizer]` y `permission_gate: PermissionGate`.
  2. Implementar `async def stream_turn(self, user_input: str, session_id: str, session_ctx: CoreSessionContext, chat_history: list[tuple[str, str]], user_override: str | None = None) -> AsyncIterator[StreamEvent]`.
  3. **Paso 1 interno:** Ejecutar `Sanitizer.check(user_input)`. Si `not result.is_safe`, emitir un `ContentEvent` informando el bloqueo y abortar sin tocar memoria ni proveedores.
  4. **Paso 2 interno:** Llamar a `self.memory_engine.start_active_query()` para cancelar tareas de fondo que ocupen a Ollama.
  5. **Paso 3 interno:** Ejecutar en paralelo (`asyncio.gather`) `ContextEngine.build(session_ctx, user_input)` y `self.memory_engine.retrieve_async(user_input, limit=3)` con `asyncio.wait_for(..., timeout=0.15)` (cumpliendo los <150ms de `JULES.md`).
  6. **Paso 4 interno:** Ensamblar el prompt con `PersonalityLoader.load(provider.name)`, hechos persistentes del proyecto, episodios recuperados e historial reciente.
  7. **Paso 5 interno:** Hacer streaming de eventos desde `router.stream_with_fallback(...)`.
  8. **Paso 6 interno (en bloque finally):** Llamar a `self.memory_engine.end_active_query()` y disparar mediante `asyncio.create_task()` la persistencia del `Episode` (pasando por una segunda revisión de `Sanitizer.check()`) y de `save_chat_history`.
  9. Refactorizar `jules/cli/app.py` para que `JulesApp` simplemente consuma `self.chat_engine.stream_turn(...)`.
- **POR QUÉ:** En `PLAN_JARVIS.md` se requiere que tanto la voz, como el daemon IPC, como la CLI hablen con el mismo cerebro sin levantar la TUI de Textual.
- **TEST OBLIGATORIO:** Crear `tests/unit/test_chat_engine.py` verificando: (a) bloqueo por Sanitizer, (b) respuesta inmediata sin bloquear por persistencia, (c) degradación elegante si EpisodicMemory lanza timeout.

#### Tarea 1.2: [x] Upgrade de Embeddings Semánticos y Auto-Reconstrucción de LanceDB
- **QUÉ hacer:** Cambiar el modelo de embeddings por defecto de `llama3.2:1b` (2048 dims) a `nomic-embed-text` (768 dims) en `jules/providers/ollama.py` y `jules/memory/episodic.py`, e implementar la reconstrucción automática del índice vectorial desde SQLite.
- **CÓMO hacerlo:**
  1. En `jules/providers/ollama.py`, configurar `embedding_model: str = "nomic-embed-text"` configurable desde `config.toml` (`[memory].embedding_model = "nomic-embed-text"`, `embedding_dimension = 768`).
  2. En `jules/memory/episodic.py`, cambiar `DEFAULT_VECTOR_DIMENSION = 768`. En `_open_or_create_table()`, si `existing_dim != self.vector_dimension`, en lugar de romper el sistema con `ValueError`, eliminar la tabla incompatible (`db.drop_table(self.table_name)`), recrearla con la nueva dimensión y marcar `self.needs_rebuild = True`.
  3. En `jules/memory/persistent.py`, añadir `async def list_all_episodes_async(self) -> list[Episode]`.
  4. En `jules/memory/engine.py`, añadir `async def rebuild_vector_index_if_needed(self) -> int` que lea todos los episodios de `PersistentMemory` (SQLite) y regenere sus vectores en `EpisodicMemory` (LanceDB) en background.
- **POR QUÉ:** Cumple el Principio 5 de `AGENT.md` ("SQLite como fuente de verdad, LanceDB como índice. Si LanceDB se corrompe, se reconstruye desde SQLite") y multiplica la precisión de búsqueda semántica.
- **TEST OBLIGATORIO:** Actualizar `tests/unit/test_episodic.py` y `tests/integration/test_memory_flow.py` probando que un cambio de dimensión reconstruye LanceDB desde SQLite sin perder un solo episodio.

---

### FASE 2: El Sistema Nervioso — Daemon UNIX, Socket IPC y Estado en Vivo

**Objetivo:** Hacer que Jules exista como un ente residente en el sistema operativo Linux sin depender de tener una terminal abierta.

#### Tarea 2.1: [x] Estado en Tiempo Real (`jules/daemon/state.py`)
- **QUÉ hacer:** Crear un gestor de estado atómico que escriba el estado actual de Jules en `/run/user/$UID/jules.state` (con fallback a `~/.jules/run/jules.state` si `XDG_RUNTIME_DIR` no existe) en formato JSON.
- **CÓMO hacerlo:**
  1. Definir `class DaemonState(str, Enum): IDLE, LISTENING, THINKING, SPEAKING, AWAITING_PERMISSION, DEGRADED`.
  2. Crear `StatePublisher` que escriba de forma atómica (escribir a `.tmp` y hacer `os.replace`) un JSON: `{"state": "IDLE", "icon": "🌹", "active_model": "...", "active_project": "...", "last_event": "...", "updated_at": ...}`.
- **POR QUÉ:** Permite que barras de estado de Linux (Waybar, Polybar, Hyprpanel) o widgets de escritorio muestren el "pulso vivo" de Jules con cero consumo de CPU.

#### Tarea 2.2: [x] Protocolo IPC por UNIX Domain Socket (`jules/daemon/ipc.py`)
- **QUÉ hacer:** Implementar el servidor y cliente asíncrono sobre `/run/user/$UID/jules.sock`.
- **CÓMO hacerlo:**
  1. Usar `asyncio.start_unix_server` y `asyncio.open_unix_connection` con mensajes JSON delimitados por salto de línea (`\n`, protocolo JSON-Lines).
  2. Soportar las siguientes acciones (`op`):
     - `{"op": "query", "text": "...", "cwd": "...", "session_id": "..."}` -> hace streaming de eventos `ThoughtEvent` y `ContentEvent` de vuelta al cliente.
     - `{"op": "voice_ptt_toggle"}` -> activa/detiene la escucha Push-to-Talk instantáneamente.
     - `{"op": "voice_barge_in"}` -> calla a Jules inmediatamente si está hablando.
     - `{"op": "shell_event", "phase": "preexec"|"precmd", "cmd": "...", "exit_code": 0, "cwd": "...", "duration_ms": 120}` -> alimenta el contexto de terminal en tiempo real.
     - `{"op": "status"}` -> devuelve salud del daemon, memoria y modelos cargados.
  3. Asegurar permisos `0o600` sobre el archivo socket para que ningún otro usuario del sistema pueda inyectar comandos.
- **POR QUÉ:** Permite que atajos de teclado globales en Linux (Hyprland, i3, GNOME, KDE) o hooks de shell se comuniquen con Jules en < 5ms sin pagar el arranque del intérprete de Python.
- **TEST OBLIGATORIO:** Crear `tests/unit/test_ipc.py` probando envío de `query`, `shell_event` y `voice_barge_in` sobre un socket temporal.

#### Tarea 2.3: [x] Servicio Principal y Unidad Systemd (`jules/daemon/service.py`)
- **QUÉ hacer:** Crear el proceso residente `JulesDaemon` y el instalador del servicio `systemd --user`.
- **CÓMO hacerlo:**
  1. `JulesDaemon` inicializa una sola vez en RAM: `CognitiveRouter`, `PersistentMemory`, `EpisodicMemory`, `MemoryEngine`, `EventBus`, `PlatformWatcher`, `ChatEngine` y `IPCServer`.
  2. Manejar señales `SIGINT` y `SIGTERM` para cerrar limpiamente sockets, conexiones HTTP de providers y esperar tareas pendientes de `MemoryEngine`.
  3. Añadir función `install_systemd_user_service()` que genere `~/.config/systemd/user/jules.service` apuntando al ejecutable dentro de `.venv/bin/jules daemon start` (y fallback documentado para distros sin systemd como Alpine/Void, respetando `JULES.md`).
  4. Añadir subcomandos en `jules/cli/main.py`: `jules daemon start`, `jules daemon status`, `jules daemon install`, y `jules ask "pregunta rápida"` (que usa el socket IPC si el daemon está activo).

---

### FASE 3: "El Fantasma en la Shell" — Conciencia de Terminal e Iniciativa Proactiva

**Objetivo:** Conectar los sensores de terminal que estaban en `# TODO` y lograr que Jules te asista sin que se lo pidas cuando detecte fricción técnica real.

#### Tarea 3.1: [x] Conectar los Hooks de Shell Reales (`jules/platform/shell.py`)
- **QUÉ hacer:** Reemplazar los bloques `# TODO: IPC hacia Jules` en `ZSH_HOOKS_BLOCK`, `BASH_HOOKS_BLOCK` y `FISH_HOOKS_BLOCK` dentro de `jules/platform/shell.py`.
- **CÓMO hacerlo:**
  1. En `_jules_preexec` y `_jules_precmd`, enviar de forma asíncrona y no bloqueante (en subshell en background `(... &) >/dev/null 2>&1` usando `socat`, `nc -U` o un micro-cliente `jules-hook-emit`) un JSON `{"op": "shell_event", "cmd": "...", "exit_code": $?, "cwd": "$PWD"}` al socket `/run/user/$UID/jules.sock`.
  2. Garantizar que si el daemon no está corriendo, el hook tarde 0ms y jamás imprima errores en la terminal del usuario.
  3. Cuando el `IPCServer` reciba `shell_event`, pasar `cmd` por `Sanitizer.check()` antes de guardarlo en `SessionContext.recent_commands` y actualizar `SessionContext.last_exit_code`.
- **POR QUÉ:** Hace que `ContextEngine._infer_intent()` (que hoy mira `last_exit_code != 0` para detectar "debugging") funcione con datos reales de tu trabajo en vivo.

#### Tarea 3.2: [x] Motor de Iniciativa Contextual (`jules/platform/initiative.py`)
- **QUÉ hacer:** Implementar las reglas de iniciativa proactiva definidas en `JULES.md` + detección de errores repetidos en terminal.
- **CÓMO hacerlo:**
  1. Crear `InitiativeEngine` suscrito al `EventBus`.
  2. **Disparador 1 (Error Conocido / Fricción en Shell):** Si el usuario recibe `exit_code != 0` dos veces seguidas en menos de 3 minutos, `InitiativeEngine` consulta `EpisodicMemory.retrieve_async(query=ultimo_comando, limit=1)`. Si hay un episodio previo con alta similitud semántica (o si puede inferir la solución rápida), Jules interviene por voz (si el módulo de voz está activo) o mediante notificación interactiva `notify-send`: *"Esteban, ese comando acaba de fallar igual que cuando configuramos X. ¿Quieres que te diga cómo lo resolvimos?"*.
  3. **Disparador 2 (Proyecto Retomado):** Al recibir `EventType.PROJECT_OPENED`, si el último episodio de ese proyecto en SQLite tiene más de 14 días, ofrece un resumen ejecutivo de 1 línea del estado en que quedó.
  4. **Disparador 3 (Atasco Prolongado):** Si `PlatformWatcher` detecta modificaciones sobre el mismo archivo por más de 2 horas con alta tasa de fallos de test (`exit_code != 0`), hace una única pregunta de desbloqueo.
  5. **Regla de Oro (`CooldownRegistry`):** Guardar en memoria un registro `(session_id, trigger_reason)`. Jules tiene estrictamente prohibido interrumpir dos veces por la misma razón en una misma sesión.
- **TEST OBLIGATORIO:** Crear `tests/unit/test_initiative.py` verificando que ante 2 fallos seguidos de comando se dispara una sugerencia, y que un tercer fallo idéntico es silenciado por la Regla de Oro.

---

### FASE 4: Voz Local Full-Duplex con Latencia Crítica (< 1.5s) y Barge-In

**Objetivo:** Implementar el pipeline de voz 100% offline descrito en `PLAN_JARVIS.md` pero optimizado con streaming por oraciones para que responda casi al instante.

#### Tarea 4.1: [x] Captura Auditiva y VAD (`jules/voice/listener.py`)
- **QUÉ hacer:** Crear `AudioListener` con soporte para Push-to-Talk (vía IPC), detección de actividad de voz (`silero-vad` o `webrtcvad`) y Wake Word opcional (`openWakeWord`: "Hey Jules").
- **CÓMO hacerlo:**
  1. Capturar audio a 16kHz mono en bloques de 30ms usando `sounddevice` en un hilo dedicado acoplado a `asyncio.Queue`.
  2. Cuando se activa por Push-to-Talk (`jules-listen` -> `{"op": "voice_ptt_toggle"}`) o por Wake Word, cambiar `StatePublisher` a `LISTENING` y grabar hasta detectar 600ms de silencio continuo post-habla.
  3. Si el usuario empieza a hablar mientras `StatePublisher` está en `SPEAKING`, emitir inmediatamente el evento `BargeInDetected` para callar el altavoz en < 50ms.

#### Tarea 4.2: [x] Transcripción Ultrarrápida (`jules/voice/transcriber.py`)
- **QUÉ hacer:** Implementar `LocalTranscriber` usando `faster-whisper` (`base` o `small` con `compute_type="int8"`).
- **CÓMO hacerlo:**
  1. Mantener el modelo pre-cargado en memoria dentro del daemon para evitar el costo de carga en frío.
  2. Ejecutar la inferencia en `asyncio.to_thread` con `beam_size=1` y `vad_filter=True` para lograr transcripciones de clips de 3 segundos en < 350ms.
  3. Pasar el texto transcrito inmediatamente por `Sanitizer.check()` antes de enviarlo a `ChatEngine`.

#### Tarea 4.3: [x] Síntesis en Streaming por Oraciones, Pila Dual (Edge TTS + Kokoro) e Interrupción (`jules/voice/speaker.py`)
- **QUÉ hacer:** Implementar `VoiceSpeaker` con acumulador de frases (`SentenceStreamChunker`) y pila dual de síntesis: `EdgeTTSBackend` (Azure Neural gratuito) como primario y `KokoroTTSBackend` (ONNX local) como fallback offline resiliente via `FallbackTTSBackend`.
- **CÓMO hacerlo:**
  1. **El secreto de la latencia < 1.5s:** No esperar a que el LLM genere todo el párrafo. `SentenceStreamChunker` consume los `ContentEvent` que salen de `ChatEngine.stream_turn()`.
  2. Cada vez que acumula al menos 40 caracteres y encuentra un signo de puntuación fuerte (`.`, `?`, `!`, `:`, `\n`), envía esa oración a una cola `tts_queue` mientras el LLM sigue pensando la segunda oración.
  3. **Pila Dual Resiliente (Edge TTS + Kokoro ONNX):**
     - **Primario (Edge TTS):** Utiliza `EdgeTTSBackend` (voz por defecto `es-CO-SalomeNeural`, rate `+0%`, 24000Hz, decodificado a PCM float32 con `ffmpeg`) sin límites de cuota ni costo de API keys.
     - **Fallback Offline (Kokoro ONNX):** `FallbackTTSBackend` envuelve primario y secundario; ante caídas de red, timeout o errores de modelo, conmuta automáticamente y sin interrupciones a `KokoroTTSBackend` (modelos locales en `~/.jules/models/kokoro/`).
     - **Jerarquía de selección:** (1) Edge TTS + Kokoro/Mock fallback, (2) Kokoro local puro si Edge TTS no está disponible, (3) MockTTSBackend. Soporta configuración explícita de `ElevenLabsTTSBackend` (`JULES_TTS_BACKEND=elevenlabs`) o backend personalizado inyectado.
  4. Un worker sintetiza la oración a PCM y la envía al stream de salida (`sounddevice` sobre PipeWire/ALSA).
  5. Implementar `speaker.stop()` que vacía `tts_queue` y ejecuta `sd.stop()` instantáneamente (< 50ms) cuando ocurre un Barge-In.
- **TEST OBLIGATORIO:** `tests/unit/test_voice_pipeline.py` y `tests/unit/test_voice_speaker.py` probando `SentenceStreamChunker`, `EdgeTTSBackend`, `FallbackTTSBackend`, prioridad de selección y latencia de interrupción < 50ms.

---

### FASE 5: Sentido de la Vista, Portapapeles y Conciencia del Sistema Operativo

**Objetivo:** Darle "ojos" y percepción del entorno físico de tu PC a Jules cuando se lo pidas, respetando la privacidad por diseño.

#### Tarea 5.1: Visión Bajo Demanda y Portapapeles (`jules/perception/vision.py` y `clipboard.py`)
- **QUÉ hacer:** Permitir que Jules vea tu pantalla/ventana activa o lea tu portapapeles únicamente cuando tu consulta tenga intención visual o de portapapeles (ej. *"mira esto"*, *"¿qué significa este error en mi pantalla?"*, *"analiza lo que acabo de copiar"*).
- **CÓMO hacerlo:**
  1. En `clipboard.py`, detectar en runtime si corre Wayland (`wl-paste`) o X11 (`xclip -o -selection clipboard`). Pasar el texto extraído por `Sanitizer.check()` obligatoriamente antes de inyectarlo al contexto. Si contiene una API key o contraseña copiada en el portapapeles, el Sanitizer lo bloquea y protege al usuario.
  2. En `vision.py`, detectar compositor en runtime: usar `grim` en Wayland o `maim` / `import` en X11 para tomar un screenshot en memoria (bytes PNG) sin dejar archivos basura en disco.
  3. En `jules/core/router.py`, añadir `TaskType.VISION` que enrute hacia un proveedor multimodal configurado (`google` con `gemini-2.5-flash` o `ollama` con un modelo de visión local si está offline).

#### Tarea 5.2: Telemetría y Reflejos de Autocuración (`jules/perception/telemetry.py`)
- **QUÉ hacer:** Crear un monitor ligero en el daemon que vigile la salud vital de tu Linux cada 30 segundos leyendo `/proc/meminfo`, `/proc/loadavg`, uso de disco (`shutil.disk_usage`) y fallos críticos de servicios (`journalctl --user -p err -n 5`).
- **CÓMO hacerlo:**
  1. Si la memoria RAM libre + caché disponible cae por debajo del 10%, identificar el proceso de usuario que más RAM consume leyendo `/proc/[pid]/status`.
  2. Emitir un evento `SystemResourceAlert` en el `EventBus`. Jules avisa por voz: *"Atención: el proceso X está consumiendo 12 gigabytes de memoria y el sistema está por congelarse. ¿Autorizas que lo termine?"*.
  3. Si el usuario responde afirmativamente, ejecutar `kill -15 <pid>` pasando primero por `PermissionGate.check(Action.SHELL_COMMAND, ...)`.

---

### FASE 6: "Ciclo de Sueño REM", Replay Cognitivo y Gemelo Digital

**Objetivo:** Transformar la memoria episódica en sabiduría a largo plazo sobre ti (el "Espejo Cognitivo" y "Git para pensamiento técnico" prometidos en `JULES.md`).

#### Tarea 6.1: Tabla de Hechos Persistentes y Consolidación REM (`jules/memory/consolidation.py`)
- **QUÉ hacer:** Hoy `PersistentMemory` solo guarda `EpisodeORM` y `ChatHistoryORM`. Hay que crear la tabla `persistent_facts` con su migración Alembic y el motor de consolidación.
- **CÓMO hacerlo:**
  1. En `jules/memory/models.py`, añadir `PersistentFactORM` con columnas: `id`, `category` (`preference` | `project_architecture` | `recurring_pitfall` | `skill_growth`), `project`, `fact_statement`, `confidence` (float), `evidence_episode_ids` (JSON list), `created_at`, `updated_at`.
  2. Generar migración con `alembic revision --autogenerate -m "add_persistent_facts"` y aplicarla.
  3. Crear `REMConsolidator` en `jules/memory/consolidation.py`: cuando el daemon detecte `EventType.IDLE_DETECTED` (15 minutos de inactividad) y haya $\ge 5$ episodios nuevos no consolidados, usar Ollama local (`TaskType.IDENTITY`) para destilar hechos permanentes sobre cómo piensa el usuario, qué arquitectura prefiere y en qué errores tuvo mayor `friction_score`.
  4. **El Morning Briefing:** En la primera actividad del día (primer comando de shell o primer saludo a Jules después de las 05:00 AM), sintetizar un saludo de 15 segundos con el resumen de lo logrado el día anterior y los temas pendientes del proyecto activo.

#### Tarea 6.2: Replay Cognitivo (`jules/memory/replay.py`) y Modo "Abogado del Diablo" (`jules/personality/coherence.py`)
- **QUÉ hacer:** Implementar el sistema de reconstrucción de sesiones de debugging y completar `jules/personality/coherence.py` (actualmente vacío con `# TODO`).
- **CÓMO hacerlo:**
  1. En `replay.py`, correlacionar por rango de timestamps los comandos capturados por `shell.py`, los archivos modificados por `watcher.py` y los `Episode` de SQLite para reconstruir una línea de tiempo causal cuando el usuario pregunte: *"¿Cómo resolví el problema de X la semana pasada?"*.
  2. En `jules/personality/coherence.py`, implementar dos funciones:
     - `verify_identity_coherence(response: str) -> float`: verifica asíncronamente que la respuesta no viole las reglas de `JULES.md` (no ser servil, no usar frases de relleno tipo "¡Claro que sí! Estaré encantado de ayudarte", mantener tono directo y analítico).
     - `inject_cognitive_mirror(facts: list[PersistentFact]) -> str`: inyecta en el prompt advertencias basadas en tus tropiezos históricos (`category == "recurring_pitfall"`), permitiendo que Jules actúe como mentora técnica real.

---

### FASE 7: Brazos y Piernas — Control del Entorno (D-Bus), MCP y PermissionGate Vocal

**Objetivo:** Permitir que Jules ejecute acciones reales en el sistema operativo con seguridad militar y confirmación hablada.

#### Tarea 7.1: Completar `jules/platform/dbus.py` (Multimedia y Modo Focus)
- **QUÉ hacer:** Implementar el módulo `jules/platform/dbus.py` (actualmente un placeholder vacío) con detección en runtime de `playerctl` / `dbus-send` / `notify-send`.
- **CÓMO hacerlo:**
  1. Implementar control multimedia agnóstico del escritorio (`play_pause()`, `next_track()`, `set_volume()`, `get_current_track()`) vía especificación MPRIS D-Bus o `playerctl`.
  2. **Auto-Ducking de Audio:** Cuando Jules empiece a escucharte (`LISTENING`) o a hablarte (`SPEAKING`), bajar automáticamente el volumen de tu música/Spotify al 20% y restaurarlo al terminar.
  3. **Focus Shield:** Cuando el usuario pida *"Jules, entra en modo concentración"* (o cuando se detecte una sesión intensa de debugging), pausar notificaciones distractivas del escritorio y reproducir tu playlist de programación.

#### Tarea 7.2: Cliente MCP y Herramientas Nativas con PermissionGate Vocal (`jules/mcp/client.py` y `jules/core/permissions.py`)
- **QUÉ hacer:** Crear el cliente MCP y actualizar `PermissionGate._prompt_background` en `jules/core/permissions.py` para soportar autorización multimodal (Voz + Notificación).
- **CÓMO hacerlo:**
  1. En `jules/mcp/client.py`, implementar la conexión stdio/SSE a servidores Model Context Protocol locales y registrar herramientas nativas (`run_shell`, `git_status_diff`, `read_file`, `write_file`, `media_control`, `system_vitals`).
  2. Cada invocación de herramienta traduce su intención al enum `Action` (`SHELL_COMMAND`, `FILE_WRITE`, `PACKAGE_OP`, `FILE_READ`, `SYSTEM_QUERY`) y llama obligatoriamente a `await permission_gate.check(action, target, cwd)`.
  3. En `jules/core/permissions.py`, cuando `classify()` devuelva `PermissionClassification.REQUIRED` y el daemon tenga voz activa:
     - Cambiar estado del daemon a `AWAITING_PERMISSION`.
     - Lanzar en paralelo (`asyncio.wait(..., return_when=FIRST_COMPLETED)`) la notificación `notify-send` con botones `[Approve / Deny]` Y una pregunta hablada por `VoiceSpeaker`: *"Confirmación requerida para ejecutar [target]. ¿Autorizas?"* seguida de 5 segundos de escucha en `AudioListener`.
     - Aceptar tanto el clic en la notificación como un "Autorizo" / "Sí, ejecútalo" por voz. Si dice "No" o "Cancela", lanzar `PermissionDeniedError`.

---

### FASE 8: Diagnóstico Completo (`jules doctor`) y Suite de Demostración en Vivo

**Objetivo:** Dejar el proyecto blindado, documentado y con un modo de demostración listo para presentar ante cualquier jurado o reclutador.

#### Tarea 8.1: Expandir `jules/platform/doctor.py`
- **QUÉ hacer:** Añadir verificaciones para los nuevos módulos en `run_all_checks()` de `jules/platform/doctor.py`:
  - `check_daemon_socket()`: Verifica si `/run/user/$UID/jules.sock` responde al ping.
  - `check_embedding_model()`: Verifica que `nomic-embed-text` esté descargado en Ollama y que la dimensión de LanceDB coincida (768d).
  - `check_voice_stack()`: Verifica disponibilidad de micrófono/PipeWire, `faster-whisper` y modelos de voz ONNX de Piper/Kokoro.
  - `check_vision_tools()`: Reporta si `grim`/`wl-paste` (Wayland) o `maim`/`xclip` (X11) están disponibles en PATH (con `status="warn"` si faltan, degradando sin bloquear el arranque, fiel a `JULES.md`).

#### Tarea 8.2: Comando `jules demo` (Modo Presentación Interactiva)
- **QUÉ hacer:** Crear en `jules/cli/main.py` un subcomando `jules demo` que guíe una demostración en vivo de 3 minutos mostrando las capacidades únicas de Jules en tiempo real:
  1. Muestra el bloqueo instantáneo de una API key por el Sanitizer.
  2. Simula un fallo en terminal y muestra a Jules interviniendo proactivamente con un recuerdo recuperado de LanceDB ("El Fantasma en la Shell").
  3. Muestra al CognitiveRouter eligiendo modelo según tier y haciendo fallback automático.
  4. Dispara una acción `REQUIRED` para demostrar a Jules pidiendo autorización por voz y notificación de escritorio a través del `PermissionGate`.
  5. Muestra el estado del `ScoringHealthMonitor` y el Morning Briefing generado por el consolidado REM.

---

## 3. ORDEN DE EJECUCIÓN PARA EL AGENTE (CHECKLIST DE SDD)

El agente debe ejecutar una sola tarea por turno, siguiendo este ciclo estricto:
1. Leer los archivos existentes involucrados en la tarea.
2. Escribir o modificar los tests correspondientes primero (TDD).
3. Implementar el código cumpliendo tipado estricto (`mypy` / `pyright` sin errores) y reglas de `AGENT.md`.
4. Ejecutar `pytest` y confirmar que los tests nuevos y los 225 tests existentes en Python pasen en verde.
5. Si se modificó `jules/memory/models.py`, generar y aplicar la migración `alembic` antes de continuar.
