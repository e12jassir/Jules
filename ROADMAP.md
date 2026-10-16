# ROADMAP.md
## Versión 2.0 — Arquitectura Jarvis (Local-First Voice & OS Assistant)

> **Principio Inviolable:** Cada módulo debe funcionar y estar testeado antes de construir el siguiente.
> Un módulo roto que avanza es deuda técnica que mata el proyecto.
> **Regla de Ejecución:** Seguir estrictamente el [`MASTER_PLAN.md`](file:///home/e12jassir/Proyectos/Jules/MASTER_PLAN.md).

---

## 1. BALANCE DEL ESTADO ACTUAL: ¿QUÉ QUEDA, QUÉ SE PAUSA Y QUÉ SE DESCARTA?

### ✅ Lo que se mantiene y sirve de base (Fase 1 Núcleo — 100% Completada)
Los 12 módulos fundacionales en Python (`jules/`) permanecen como el cerebro operativo de Jules (225 tests unitarios):
- **Módulo 0:** Estructura base y empaquetado.
- **Módulo 1:** Sanitizador estricto en la frontera de entrada (`Sanitizer`).
- **Módulo 2:** Modelos de datos persistentes en SQLite con migraciones Alembic.
- **Módulo 3 & 4:** Proveedores LLM (Ollama local, Antigravity/Gemini, OpenCode/DeepSeek).
- **Módulo 5:** `CognitiveRouter` quota-aware con fallback en cascada.
- **Módulo 6:** `MemoryEngine` (SQLite para verdad persistente + LanceDB para vectores episódicos).
- **Módulo 7:** Detector de intención de contexto (`ContextEngine`).
- **Módulo 8:** Sistema de eventos desacoplado (`EventBus`).
- **Módulo 9:** `PermissionGate` (Safe, Required, Prohibited).
- **Módulo 10:** Herramienta de diagnóstico de entorno (`jules doctor`).
- **Módulo 11:** Entrypoint CLI funcional.
- **Módulo 12:** Autenticación OAuth de OpenAI vía WebSockets.

---

### ⏸️ Lo que queda PAUSADO y congelado
- **Fase 1.5: TUI en Rust ([`jules-tui/`](file:///home/e12jassir/Proyectos/Jules/jules-tui)):**
  - **Motivo:** Intentar clonar la interfaz de usuario de OpenCode (Ratatui, slash commands `/models`, `/sessions`, `/provider`, cálculo de geometría de terminal) desvió a Jules de su propósito real como asistente de voz y sistema operativo.
  - **Estado:** Se congela intacto con sus **23 pruebas pasando** (15 en `main.rs` + 8 en `commands_test.rs`). No se le agregará ni una sola línea de código durante la ejecución del nuevo plan. Queda disponible como interfaz alternativa para el futuro.

---

### ❌ Lo que queda DESCARTADO del viejo Roadmap
- **Item 6 (Viejo): Desktop App en Tauri + SvelteKit:** Descartado por redundante. Jules vive en el terminal, en la voz y en el socket del sistema operativo; no necesita una ventana WebView pesada.
- **Item 8 (Viejo): Tabs de múltiples sesiones en TUI:** Descartado; la concurrencia se maneja a nivel de daemon por `session_id`, no mediante pestañas gráficas en terminal.
- **Item 9 (Viejo): Panel decorativo "Herramientas" en TUI:** Descartado; las herramientas se ejecutan de verdad vía MCP y D-Bus con `PermissionGate`, no como íconos estáticos.
- **Dependencias de Infraestructura Pesada (Docker / Redis):** Prohibido el uso de Redis o contenedores Docker propuestos por arquitecturas como OpenJarvis de fábrica. Todo el bus de eventos e IPC corre sobre `asyncio` y UNIX Domain Sockets nativos.

---

## 2. EVOLUCIÓN DEL PROYECTO: ¿CÓMO QUEDA JULES A MEDIDA QUE PASAN LAS FASES?

La transformación desde un chat de terminal hacia un Jarvis local se ejecuta en 8 fases continuas:

| Fase | Nombre del Hito | ¿Cómo queda Jules para el usuario al terminar la fase? |
|---|---|---|
| **Fase 1** | **Desacoplamiento Cognitivo & Memoria 768d** | Jules tiene su cerebro (`ChatEngine`) separado de cualquier UI gráfica. Búsquedas vectoriales ultra precisas con `nomic-embed-text` (768d) y regeneración automática del índice desde SQLite. |
| **Fase 2** | **El Sistema Nervioso (Daemon & IPC Socket)** | Jules corre como servicio de fondo en Linux (`systemd --user`). Ya no requiere una terminal abierta. Responde en < 5ms por UNIX socket (`jules.sock`). Tu barra Waybar/Hyprland muestra su pulso en tiempo real (`jules.state`). |
| **Fase 3** | **El Fantasma en la Shell** | Tu terminal tiene conciencia contextual. Si un comando de compilación o test falla dos veces seguidas, Jules interviene proactivamente con la solución que usaste antes. |
| **Fase 4** | **Voz Local Full-Duplex (< 1.5s)** | **Nace Jarvis.** Oprimes tu atajo global o dices *"Hey Jules"*, hablas por micrófono, `faster-whisper` transcribe en local en 300ms, y Jules te habla al oído con síntesis en streaming por oraciones (Piper/Kokoro). Si lo interrumpes (Barge-in), se calla al instante. |
| **Fase 5** | **Vista, Portapapeles & Telemetría** | Jules tiene ojos. Le dices *"mira este error en mi pantalla"* y toma un screenshot en RAM con `grim`/`maim` para analizarlo; vigila la RAM y te avisa antes de que un proceso congelemel equipo. |
| **Fase 6** | **Ciclo REM, Replay & Espejo Cognitivo** | Mientras duermes o estás inactivo, Jules destila tus sesiones pasadas en hechos permanentes en SQLite. Te da un *Morning Briefing* a las 5 AM y te recuerda tus tropiezos técnicos históricos. |
| **Fase 7** | **Brazos, Piernas & Control OS (D-Bus / MCP)** | Jules le baja automáticamente el volumen a Spotify cuando tú hablas (Auto-Ducking), pausa notificaciones en modo concentración y ejecuta herramientas del sistema vía MCP pidiéndote autorización hablada (*"¿Autorizas?"*). |
| **Fase 8** | **Diagnóstico Total & Modo Presentación** | `jules doctor` audita todo el stack (voz, socket, modelos, herramientas) y `jules demo` ejecuta una demostración interactiva de 3 minutos en vivo lista para impresionar. |

---

## 3. ESPECIFICACIÓN DETALLADA DE LAS NUEVAS FASES

Para la implementación línea por línea, contratos de clase, pruebas obligatorias y arquitectura de archivos de cada una de estas 8 fases, la fuente de verdad única y mandatoria es:

👉 **Consulte [`MASTER_PLAN.md`](file:///home/e12jassir/Proyectos/Jules/MASTER_PLAN.md)**

---

## 4. CHECKLIST GENERAL DE PROGRESO

### Fase 1: Desacoplamiento Cognitivo y Memoria Semántica
- [x] **Tarea 1.1:** Crear [`jules/core/chat_engine.py`](file:///home/e12jassir/Proyectos/Jules/jules/core/chat_engine.py) y desacoplar de `jules/cli/app.py`.
- [x] **Tarea 1.1 Tests:** [`tests/unit/test_chat_engine.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_chat_engine.py) en verde.
- [x] **Tarea 1.2:** Migrar a `nomic-embed-text` (768d) y auto-reconstrucción de LanceDB desde SQLite en [`jules/memory/engine.py`](file:///home/e12jassir/Proyectos/Jules/jules/memory/engine.py).
- [x] **Tarea 1.2 Tests:** Tests de integración de memoria en verde.

### Fase 2: Daemon UNIX, Socket IPC y Estado en Vivo
- [x] **Tarea 2.1:** Implementar emisor de estado atómico en [`jules/daemon/state.py`](file:///home/e12jassir/Proyectos/Jules/jules/daemon/state.py).
- [x] **Tarea 2.1 Tests:** [`tests/unit/test_daemon_state.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_daemon_state.py) en verde.
- [x] **Tarea 2.2:** Implementar servidor y cliente de UNIX Domain Socket en [`jules/daemon/ipc.py`](file:///home/e12jassir/Proyectos/Jules/jules/daemon/ipc.py).
- [x] **Tarea 2.2 Tests:** [`tests/unit/test_ipc.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_ipc.py) en verde.
- [x] **Tarea 2.3:** Implementar bucle de servicio residente y unidad `systemd --user` en [`jules/daemon/service.py`](file:///home/e12jassir/Proyectos/Jules/jules/daemon/service.py).
- [x] **Tarea 2.3 Tests:** [`tests/unit/test_daemon_service.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_daemon_service.py) en verde.

### Fase 3: Conciencia de Terminal e Iniciativa Proactiva
- [x] **Tarea 3.1:** Conectar hooks de Zsh/Bash/Fish reales a `jules.sock` en [`jules/platform/shell.py`](file:///home/e12jassir/Proyectos/Jules/jules/platform/shell.py).
- [ ] **Tarea 3.2:** Implementar motor de iniciativa contextual y cooldown registry en [`jules/platform/initiative.py`](file:///home/e12jassir/Proyectos/Jules/jules/platform/initiative.py).
- [ ] **Tarea 3.2 Tests:** [`tests/unit/test_initiative.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_initiative.py) en verde.

### Fase 4: Voz Local Full-Duplex (< 1.5s) y Barge-In
- [ ] **Tarea 4.1:** Captura de micrófono, VAD y Push-to-Talk en [`jules/voice/listener.py`](file:///home/e12jassir/Proyectos/Jules/jules/voice/listener.py).
- [ ] **Tarea 4.2:** Transcripción ultrarrápida local con `faster-whisper` en [`jules/voice/transcriber.py`](file:///home/e12jassir/Proyectos/Jules/jules/voice/transcriber.py).
- [ ] **Tarea 4.3:** Síntesis por oraciones en streaming e interrupción en [`jules/voice/speaker.py`](file:///home/e12jassir/Proyectos/Jules/jules/voice/speaker.py).
- [ ] **Tarea 4.3 Tests:** [`tests/unit/test_voice_pipeline.py`](file:///home/e12jassir/Proyectos/Jules/tests/unit/test_voice_pipeline.py) en verde.

### Fase 5: Visión, Portapapeles y Telemetría del OS
- [ ] **Tarea 5.1:** Screenshot on-demand (`grim`/`maim`), portapapeles (`wl-paste`/`xclip`) y filtro `Sanitizer`.
- [ ] **Tarea 5.2:** Monitor ligero de recursos de Linux (`/proc`, RAM, discos) y auto-defensa en [`jules/perception/telemetry.py`](file:///home/e12jassir/Proyectos/Jules/jules/perception/telemetry.py).

### Fase 6: Consolidación REM, Replay Cognitivo y Gemelo Digital
- [ ] **Tarea 6.1:** Modelo `PersistentFactORM`, migración Alembic y motor `REMConsolidator` en [`jules/memory/consolidation.py`](file:///home/e12jassir/Proyectos/Jules/jules/memory/consolidation.py).
- [ ] **Tarea 6.2:** Reconstrucción de sesiones en [`jules/memory/replay.py`](file:///home/e12jassir/Proyectos/Jules/jules/memory/replay.py) y coherencia/espejo en [`jules/personality/coherence.py`](file:///home/e12jassir/Proyectos/Jules/jules/personality/coherence.py).

### Fase 7: Control del Entorno (D-Bus), MCP y PermissionGate Vocal
- [ ] **Tarea 7.1:** Control multimedia MPRIS, Auto-Ducking de volumen y modo Focus en [`jules/platform/dbus.py`](file:///home/e12jassir/Proyectos/Jules/jules/platform/dbus.py).
- [ ] **Tarea 7.2:** Cliente MCP seguro con confirmación hablada en [`jules/mcp/client.py`](file:///home/e12jassir/Proyectos/Jules/jules/mcp/client.py) y [`jules/core/permissions.py`](file:///home/e12jassir/Proyectos/Jules/jules/core/permissions.py).

### Fase 8: Diagnóstico y Demostración en Vivo
- [ ] **Tarea 8.1:** Extensión de `jules doctor` para verificar socket, audio, modelos de voz y visión.
- [ ] **Tarea 8.2:** Implementación del subcomando interactivo `jules demo`.
