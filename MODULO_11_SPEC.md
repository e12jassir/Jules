# MÓDULO 11 — CLI Principal (Rediseño)
## Spec Técnico v2.0

> **Decisión de arquitectura:** TUI persistente con Textual.
> El paradigma cambia de `jules "query" → respuesta → exit` a `jules → app abierta → sesión continua`.
> Los módulos 0–10 no cambian. Este módulo es la capa de presentación encima de todo lo construido.

---

## DECISIONES DE ARQUITECTURA

### Por qué Textual

- Python nativo — integración directa con módulos 0–10 sin IPC, sin serialización, sin proceso separado
- CSS real para layout — el sidebar de dos columnas de la imagen se expresa en CSS de Textual, no en constraints frágiles
- Reactive widgets — el sidebar actualiza tokens/tiempo/modelo en tiempo real con `reactive()` de Textual
- Async nativo — compatible con el asyncio que ya usan los providers y el motor de memoria
- Control total del render — cada píxel del layout es definible

### Paradigma nuevo: sesión persistente

**Antes (spec original):**
```
jules "pregunta" → proceso → respuesta → exit
```

**Ahora:**
```
jules → TUI abre → sesión continua → el usuario escribe dentro → jules cierra con Ctrl+C o /exit
```

Esto implica:
- El `SessionContext` vive durante toda la sesión TUI, no por invocación
- Los eventos `SESSION_STARTED` / `SESSION_ENDED` se disparan al abrir/cerrar la TUI
- La memoria temporal (RAM) persiste durante toda la sesión abierta
- El doctor corre una vez al arrancar la TUI, no en cada query

### `jules doctor` sigue siendo comando CLI separado

```bash
jules doctor          # CLI clásico, sin TUI, para scripting y diagnóstico
jules doctor --json   # idem con output JSON
jules               # abre la TUI persistente
```

`doctor` no cambia de paradigma porque necesita funcionar fuera de la TUI (en scripts, en CI, antes de arrancar Jules).

---

## LAYOUT VISUAL — REFERENCIA CANÓNICA

### Pantalla de bienvenida (welcome screen)

```
┌─────────────────────────────────────────────────────────────────────┐
│ >_ Welcome to Jules                                        v0.1.0   │
│                                                                     │
│                    [rosa en caracteres braille]                     │
│                                                                     │
│                          j u l e s                                  │
│                  Tu asistente de IA. Tu memoria.                    │
│                                                                     │
│         ┌──────────────────────────────────────────────┐            │
│         │ > Pregúntame cualquier cosa...               │            │
│         │   Modelo: GPT-5.5 · Claude · Gemini · Local  │            │
│         └──────────────────────────────────────────────┘            │
│                                                                     │
│   ctrl+t variantes    tab agentes    ctrl+p comandos    ctrl+h ayuda│
│                                                                     │
│   ● Tip: Usa /sessions para ver tus conversaciones anteriores       │
│                                                                     │
│ ~/proyectos/Jules  ⎇ main    🌹 Jules CLI  ⏱ 22:48  ● conectado   │
└─────────────────────────────────────────────────────────────────────┘
```

**Comportamiento:** al escribir el primer mensaje, la welcome screen transiciona al layout de chat.

---

### Layout de chat (estado principal)

```
┌──────────────────────────────────────┬──────────────────────────────┐
│ 🌹 jules    chat  +          v0.1.0  │ CONTEXTO                     │
├──────────────────────────────────────┤                              │
│                                      │ 📁 Proyecto   ~/Jules        │
│  👤 tú                    22:48:12   │ ⎇  Rama       main          │
│  ¿Cuál es el stack de este proyecto? │ 📄 Archivos   512            │
│                                      │                              │
│  🌹 jules                 22:48:14   │ MODELO ACTIVO                │
│  He analizado el proyecto y este     │                              │
│  es el stack tecnológico encontrado: │ GPT-5.5      ● online        │
│                                      │ 128k contexto            ∨   │
│  Lenguajes                           │                              │
│  • TypeScript                        │ MEMORIA                      │
│  • JavaScript (ESNext)               │                              │
│  • CSS / SCSS                        │ ⏱ Episodios   24             │
│  • HTML                              │ ⏱ Hechos      153            │
│                                      │ ⏱ Recuerdos   89             │
│  📄 Referencias: package.json, ...   │ > Ver memoria                │
│                                      │                              │
│ ┌──────────────────────────────────┐ │ HERRAMIENTAS                 │
│ │ > Escribe tu mensaje o usa /...  │ │                              │
│ └──────────────────────────────────┘ │ • filesystem   ✓             │
│                                      │ • terminal     ✓             │
├──────────────────────────────────────┤ • git          ✓             │
│ ~/Jules  ⎇ main  ● Auto-saved        │ • search       ✓             │
│ ctrl+t variantes  tab agentes  ...   │ • web          ○             │
└──────────────────────────────────────┴──────────────────────────────┘
                                        │ ESTADÍSTICAS                │
                                        │                             │
                                        │ Tokens usados   24,932      │
                                        │ Costo sesión    $0.0031     │
                                        │ Tiempo sesión   00:12:48    │
                                        └─────────────────────────────┘
```

---

## PALETA DE COLORES

```python
# jules/cli/theme.py
JULES_THEME = {
    "background":     "#0d0d0d",   # negro casi puro
    "surface":        "#141414",   # superficie de paneles
    "surface_alt":    "#1a1a1a",   # hover / selección
    "border":         "#2a2a2a",   # bordes sutiles
    "border_active":  "#ff79c6",   # rosa — elemento activo
    "text_primary":   "#e8e8e8",   # texto principal
    "text_secondary": "#888888",   # texto secundario
    "text_muted":     "#555555",   # texto apagado
    "accent":         "#ff79c6",   # rosa — color de marca
    "accent_dim":     "#c45fa0",   # rosa oscuro
    "success":        "#50fa7b",   # verde — online / ok
    "warning":        "#f1fa8c",   # amarillo — warn
    "error":          "#ff5555",   # rojo — fail
    "scrollbar":      "#333333",
    "input_border":   "#ff79c6",   # rosa en el input activo
    "header_bg":      "#0d0d0d",
    "sidebar_bg":     "#111111",
}
```

---

## TIPOGRAFÍA

Fuente monoespaciada en toda la app. En orden de preferencia:

1. `JetBrains Mono` — primera opción
2. `Fira Code` — fallback
3. `Cascadia Code` — fallback
4. Cualquier monoespaciada disponible

La fuente la define el terminal del usuario. Jules no puede forzar la fuente — pero el diseño asume monoespaciada y se ve correcto con cualquiera de las anteriores.

---

## ESTRUCTURA DE ARCHIVOS DEL MÓDULO

```
jules/cli/
├── main.py              # entrypoint Click — jules doctor + jules (TUI)
├── app.py               # JulesApp(App) — clase principal Textual
├── theme.py             # paleta, CSS variables, TCSS base
├── screens/
│   ├── welcome.py       # WelcomeScreen — pantalla inicial
│   └── chat.py          # ChatScreen — pantalla principal
├── widgets/
│   ├── chat_log.py      # ChatLog — historial de mensajes
│   ├── input_bar.py     # InputBar — input con comandos /
│   ├── sidebar.py       # Sidebar — panel derecho completo
│   ├── context_panel.py # ContextPanel — proyecto/rama/archivos
│   ├── model_panel.py   # ModelPanel — modelo activo + tier
│   ├── memory_panel.py  # MemoryPanel — episodios/hechos/recuerdos
│   ├── tools_panel.py   # ToolsPanel — herramientas y estado
│   ├── stats_panel.py   # StatsPanel — tokens/costo/tiempo
│   └── status_bar.py    # StatusBar — barra inferior
└── commands.py          # parser de comandos / (slash commands)
```

---

## COMPONENTES — SPEC DETALLADO

### `JulesApp` — `jules/cli/app.py`

```python
class JulesApp(App):
    """Aplicación principal de Jules."""

    CSS_PATH = "theme.tcss"
    BINDINGS = [
        ("ctrl+t", "toggle_variants", "Variantes"),
        ("tab",    "toggle_agents",   "Agentes"),
        ("ctrl+p", "command_palette", "Comandos"),
        ("ctrl+h", "show_help",       "Ayuda"),
        ("ctrl+c", "quit",            "Salir"),
    ]

    # Reactive state — el sidebar se actualiza automáticamente
    active_model:    reactive[str]   = reactive("---")
    active_provider: reactive[str]   = reactive("---")
    active_tier:     reactive[str]   = reactive("---")
    tokens_used:     reactive[int]   = reactive(0)
    session_cost:    reactive[float] = reactive(0.0)
    session_time:    reactive[str]   = reactive("00:00:00")
    memory_episodes: reactive[int]   = reactive(0)
    memory_facts:    reactive[int]   = reactive(0)
    online_status:   reactive[bool]  = reactive(True)
```

**Al arrancar:**
1. Correr `doctor` en background — si hay problemas, mostrar en status bar, nunca bloquear
2. Detectar shell, proyecto activo (git), rama
3. Cargar `personality/loader.py` → system prompt
4. Disparar evento `SESSION_STARTED`
5. Mostrar `WelcomeScreen`
6. Arrancar timer de sesión (actualiza `session_time` cada segundo)

---

### `WelcomeScreen` — `jules/cli/screens/welcome.py`

Pantalla inicial. Se muestra hasta que el usuario envía el primer mensaje.

**Contenido:**
- Header: `>_ Welcome to Jules` (izquierda) + `v0.1.0` (derecha)
- Rosa en caracteres braille — centrada, generada con `drawille` o hardcodeada como string
- Logo: `j u l e s` con espaciado
- Subtítulo: `Tu asistente de IA. Tu memoria. Tu compañera.`
- Input box con placeholder `> Pregúntame cualquier cosa...`
- Indicador de modelos disponibles: `Modelo: GPT-5.5 · Claude-3.7 · Gemini-1.5 · Local`
- Bindings: `ctrl+t variantes  tab agentes  ctrl+p comandos  ctrl+h ayuda`
- Tip rotativo en la parte inferior
- Status bar igual que en chat

**Transición:** al enviar el primer mensaje, `push_screen(ChatScreen)` con el mensaje ya procesado.

---

### `ChatScreen` — `jules/cli/screens/chat.py`

Layout de dos columnas:

```
Columna izquierda (75%):
├── Header con tabs (chat, +)
├── ChatLog (scrollable, crece hacia arriba)
└── InputBar (fijo en el fondo)

Columna derecha (25%):
└── Sidebar (scroll propio)
    ├── ContextPanel
    ├── ModelPanel
    ├── MemoryPanel
    ├── ToolsPanel
    └── StatsPanel
```

---

### `ChatLog` — `jules/cli/widgets/chat_log.py`

Historial de mensajes. Cada mensaje tiene:

```
👤 tú                                    22:48:12
¿Cuál es el stack tecnológico de este proyecto?

🌹 jules                                 22:48:14
He analizado el proyecto y este es el stack...
```

**Reglas de formato:**
- Avatar del usuario: `👤 tú` en `text_secondary`
- Avatar de Jules: `🌹 jules` en `accent` (rosa)
- Timestamp alineado a la derecha, en `text_muted`
- Separación visual entre mensajes (línea vacía)
- Markdown renderizado con Rich Markup para respuestas de Jules:
  - Headers en `accent`
  - Bullets con `•` en rosa
  - Code blocks con borde sutil
- Referencias al pie del mensaje: `📄 Referencias: archivo1, archivo2`
- Streaming: el texto de Jules aparece token a token — `ChatLog` soporta update incremental del último mensaje

**Durante streaming:**
- Cursor parpadeante al final del texto en construcción
- El input queda deshabilitado hasta que termina el stream
- La barra de status muestra `● generando...`

---

### `InputBar` — `jules/cli/widgets/input_bar.py`

```
┌────────────────────────────────────────────────────────────────┐
│ > Escribe tu mensaje o usa / para comandos...                  │
└────────────────────────────────────────────────────────────────┘
```

**Comportamiento:**
- Borde rosa cuando está activo
- Al escribir `/`, muestra autocomplete de slash commands
- `Enter` envía el mensaje
- `Shift+Enter` inserta salto de línea
- Multiline soportado (el box crece verticalmente hasta 5 líneas)
- Historial de mensajes: `↑` / `↓` navega mensajes anteriores de la sesión

**Slash commands disponibles (Fase 1):**
```
/exit        → cerrar Jules
/sessions    → ver sesiones anteriores
/memory      → ver episodios recientes
/status      → estado de providers
/doctor      → correr diagnóstico
/model MODEL → cambiar modelo para el siguiente mensaje
/clear       → limpiar el chat log (no borra memoria)
/help        → mostrar ayuda
```

---

### `Sidebar` — `jules/cli/widgets/sidebar.py`

Panel derecho. Ancho fijo: `25%` del terminal, mínimo `28` caracteres.

Contiene en orden vertical:

#### `ContextPanel`

```
CONTEXTO

📁 Proyecto   ~/proyectos/Jules
⎇  Rama       main
📄 Archivos   512
```

Se actualiza al arrancar y cuando cambia el directorio de trabajo (evento de filesystem).

#### `ModelPanel`

```
MODELO ACTIVO

GPT-5.5           ● online
128k contexto                ∨
```

- `●` verde = online, rojo = degradado, amarillo = warning
- `∨` abre selector de modelo (Fase 1: solo muestra info, no cambia)
- Se actualiza reactivamente cuando el router selecciona un modelo

#### `MemoryPanel`

```
MEMORIA

⏱ Episodios    24
⏱ Hechos      153
⏱ Recuerdos    89
> Ver memoria
```

Contadores en tiempo real — se actualizan después de cada persistencia async.
`> Ver memoria` ejecuta `/memory`.

#### `ToolsPanel`

```
HERRAMIENTAS

• filesystem   ✓
• terminal     ✓
• git          ✓
• search       ✓
• web          ○
```

`✓` verde = disponible, `○` gris = no disponible / no configurado.
Estado determinado por `jules doctor` al arrancar.

#### `StatsPanel`

```
ESTADÍSTICAS

Tokens usados    24,932
Costo sesión     $0.0031
Tiempo sesión    00:12:48
```

- Tokens: suma acumulada de la sesión activa
- Costo: calculado según modelo y tokens (tabla de precios en `config.toml` — Fase 2, en Fase 1 mostrar `---`)
- Tiempo: timer desde que arrancó la sesión

---

### `StatusBar` — `jules/cli/widgets/status_bar.py`

Barra inferior fija. Dos filas en pantallas chicas, una en pantallas anchas:

```
~/proyectos/Jules  ⎇ main  ● Auto-saved    ctrl+t variantes  tab agentes  ctrl+p comandos  ctrl+h ayuda    22:48  🌹
```

- Directorio + rama (izquierda)
- Estado de auto-save (centro-izquierda)
- Bindings activos (centro)
- Hora (derecha)
- Logo rosa (extremo derecho)

---

## FLUJO PRINCIPAL — MANEJO DE UN MENSAJE

```
Usuario presiona Enter en InputBar
  ↓
InputBar.on_submit(message)
  ↓
ChatLog.add_user_message(message)
  ↓
InputBar.disable()  ← bloquear hasta que llegue respuesta
StatusBar.set_status("generando...")
  ↓
asyncio.create_task(process_message(message))
  ↓
  [en background async]
  Sanitizador.check(message)
    → si falla: ChatLog.add_error("Mensaje bloqueado por sanitizador")
                InputBar.enable() ; return
  ↓
  ContextEngine.build(session, message) → SessionContext
  ↓
  EpisodicMemory.retrieve(message, ctx) [timeout 150ms]
  ↓
  Router.select(message, ctx) → provider, model
  SideBar.ModelPanel.update(model, provider)  ← actualizar sidebar
  ↓
  Provider.stream(message, context, personality)
    → cada token: ChatLog.append_token(token)
  ↓
  ChatLog.finalize_message()
  StatsPanel.update(tokens=response.tokens)
  InputBar.enable()
  StatusBar.set_status("● Auto-saved")
  ↓
  asyncio.create_task(persist_episode(...))  ← background, no bloquea
    → cuando termina: MemoryPanel.update(episodes, facts)
```

---

## `personality/loader.py`

Vacío actualmente. Este módulo crea en Módulo 11.

```python
class PersonalityLoader:
    """
    Carga master.md + preset del provider activo.
    Inyecta como system prompt en cada llamada.
    Detecta cambios de versión en master.md y advierte.
    """

    def load(self, provider: str) -> str:
        """
        Retorna el system prompt completo para el provider dado.
        master.md (base) + {provider}.md (ajustes específicos)
        """

    def detect_version_change(self) -> bool:
        """
        Compara la versión en master.md con la última conocida.
        Si cambió, loggear y notificar en StatusBar.
        """
```

**Archivos que lee:**
```
~/.jules/personality/master.md       # identidad canónica
~/.jules/personality/local.md        # para Ollama
~/.jules/personality/antigravity.md  # para Antigravity
~/.jules/personality/opencode.md     # para OpenCode
```

Si algún archivo no existe, usar el master.md como fallback sin error.

---

## ENTRYPOINT — `main.py` (reescrito)

```python
@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Jules — capa cognitiva persistente."""
    if ctx.invoked_subcommand is None:
        # Sin subcomando → abrir TUI
        app = JulesApp()
        app.run()

@cli.command()
@click.option("--json", "as_json", is_flag=True)
def doctor(as_json):
    """Diagnóstico de salud del entorno."""
    # igual que ahora — no cambia
```

---

## MANEJO DE DEGRADACIÓN EN LA TUI

| Falla al arrancar | Comportamiento |
|---|---|
| Doctor detecta problemas | Mostrar en StatusBar con `⚠` — nunca bloquear |
| Ollama no disponible | ModelPanel muestra `● offline` — providers externos siguen activos |
| LanceDB no disponible | MemoryPanel muestra `⚠ sin memoria semántica` |
| SQLite no disponible | StatsPanel muestra `⚠ sin persistencia` |
| Todos los providers fallan | ChatLog muestra error claro, InputBar sigue activo |

**Regla:** la TUI siempre abre. Nunca crashea en el arranque. Los fallos se comunican en el sidebar, no en el stdout.

---

## CSS / TCSS — REGLAS BASE

```css
/* jules/cli/theme.tcss */

Screen {
    background: #0d0d0d;
}

.sidebar {
    width: 25%;
    min-width: 28;
    background: #111111;
    border-left: tall #2a2a2a;
}

.chat-area {
    width: 75%;
}

.panel-header {
    color: #ff79c6;
    text-style: bold;
    padding: 1 0 0 1;
}

.panel-section {
    padding: 0 1 1 1;
    border-bottom: solid #2a2a2a;
}

InputBar {
    border: tall #ff79c6;
    background: #141414;
}

InputBar:focus {
    border: tall #ff79c6;
}

.message-user .avatar {
    color: #888888;
}

.message-jules .avatar {
    color: #ff79c6;
}

.timestamp {
    color: #555555;
}

StatusBar {
    background: #0d0d0d;
    border-top: solid #2a2a2a;
    color: #555555;
}

.status-accent {
    color: #ff79c6;
}

.online {
    color: #50fa7b;
}

.offline {
    color: #ff5555;
}

.warn {
    color: #f1fa8c;
}
```

---

## DEPENDENCIAS NUEVAS

```toml
# pyproject.toml — agregar
textual >= 0.70.0
drawille >= 0.1.0    # para la rosa en braille (opcional — puede hardcodearse)
```

---

## TESTS

### Unit tests

```
tests/unit/test_commands.py       → parser de slash commands
tests/unit/test_personality.py    → loader carga master.md + preset
tests/unit/test_stats.py          → cálculo de tokens y tiempo
```

### Integration tests (Textual pilot)

```
tests/integration/test_tui_welcome.py    → welcome screen carga sin error
tests/integration/test_tui_chat.py       → flujo completo: mensaje → respuesta → persistencia
tests/integration/test_tui_degraded.py   → TUI abre con providers caídos
tests/integration/test_tui_commands.py   → slash commands ejecutan correctamente
```

Textual provee `App.run_test()` y `Pilot` para tests automatizados de TUI.

---

## FLUJO SDD RECOMENDADO

| Fase | Modelo | Razón |
|---|---|---|
| `sdd-init` | Gemini 3.5 Flash | Contexto del proyecto + estado real de módulos 0–10 |
| `sdd-explore` | Gemini 3.1 Pro | **Obligatoria** — mapear contratos reales de módulos 0–10 antes de integrar |
| `sdd-propose` | Claude Opus 4.8 | Decisiones: estructura TCSS, reactive state design, streaming en ChatLog |
| `sdd-spec` | Claude Sonnet 4.6 | Este documento es el spec — usarlo como referencia |
| `sdd-design` | Claude Opus 4.8 | Diseño de `personality/loader.py` + integración asyncio/Textual |
| `sdd-tasks` | Claude Sonnet 4.6 | Descomponer por widget: welcome → chat → sidebar → input → status |
| `sdd-apply` | Gemini 3.5 Flash | Implementación widget por widget — no todo junto |
| `sdd-verify` | Claude Opus 4.8 | Flujo e2e, degradación, streaming, persistencia entre reinicios |
| `sdd-archive` | Gemini 3.1 Flash-Lite | Cierre formal — documentar estado final |

**Orden de implementación recomendado en `sdd-apply`:**
1. `theme.tcss` + paleta
2. `JulesApp` esqueleto + `main.py` reescrito
3. `StatusBar`
4. `WelcomeScreen` con input funcional
5. `ChatScreen` layout (sin lógica)
6. `Sidebar` con todos los paneles (datos estáticos primero)
7. `ChatLog` con mensajes hardcodeados
8. `InputBar` con slash commands
9. Integrar flujo real: sanitizador → router → provider → stream
10. Reactive state: sidebar se actualiza con datos reales
11. `personality/loader.py`
12. Persistencia async + update de MemoryPanel
13. Tests

---

## CRITERIOS DE DONE

```
- [ ] jules                    → abre TUI sin error
- [ ] jules doctor             → CLI clásico sigue funcionando (no regresión)
- [ ] WelcomeScreen muestra rosa braille, logo, input funcional
- [ ] Primer mensaje transiciona a ChatScreen correctamente
- [ ] Respuesta de Jules aparece con streaming token a token
- [ ] Sidebar actualiza modelo en tiempo real durante la respuesta
- [ ] MemoryPanel actualiza contadores después de persistencia async
- [ ] StatsPanel actualiza tokens después de cada respuesta
- [ ] Slash commands /exit /memory /status /doctor /clear funcionan
- [ ] Autocompletado visual (dropdown) aparece al teclear '/' en el InputBar
- [ ] Jules recupera el historial de la sesión activa (ChatHistoryORM) y lo inyecta en el prompt (cura de amnesia)
- [ ] TUI abre con Ollama caído — degradación visible en sidebar, no crash
- [ ] TUI abre con LanceDB caído — degradación visible, no crash
- [ ] personality/loader.py carga master.md + preset del provider activo
- [ ] Startup < 500ms con Ollama caliente (medir con time)
- [ ] Tests de integración pasan con Textual Pilot
- [ ] Sin modelos hardcodeados fuera de config.toml
```

---

> **Nota final:** este spec reemplaza completamente el Módulo 11 original.
> El `main.py` actual se descarta excepto el comando `doctor` que se porta sin cambios.
> Los módulos 0–10 no se tocan.
