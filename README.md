<div align="center">

```
   ██╗██╗   ██╗██╗     ███████╗███████╗
   ██║██║   ██║██║     ██╔════╝██╔════╝
   ██║██║   ██║██║     █████╗  ███████╗
██ ██║██║   ██║██║     ██╔══╝  ╚════██║
╚█████╔╝╚██████╔╝███████╗███████╗███████║
 ╚════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝
```

**Capa cognitiva persistente para Linux**

[![Estado](https://img.shields.io/badge/fase-1%20en%20progreso-yellow?style=flat-square)](https://github.com/tu-usuario/jules)
[![Módulos](https://img.shields.io/badge/módulos%20done-8%20%2F%2011-blue?style=flat-square)](https://github.com/tu-usuario/jules/blob/main/ROADMAP.md)
[![Tests](https://img.shields.io/badge/tests-120%20passing-brightgreen?style=flat-square)](https://github.com/tu-usuario/jules)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org/)
[![Licencia](https://img.shields.io/badge/licencia-MIT-gray?style=flat-square)](LICENSE)
[![Entorno](https://img.shields.io/badge/entorno-EndeavourOS%20%2B%20KDE%20Plasma-blueviolet?style=flat-square)](https://endeavouros.com/)

</div>

---

## Qué es Jules

Jules no es un chatbot. No es un wrapper de APIs. No es un copiloto desechable que se reinicia sin saber quién eres.

Jules es una **capa cognitiva persistente** que vive dentro de tu sistema operativo Linux. Recuerda entre sesiones. Infiere tu intención sin que la declares. Sabe con qué modelo resolviste mejor un bug la semana pasada. Nunca filtra tus credenciales. No interrumpe a menos que lo actives explícitamente.

La diferencia central con cualquier otro asistente de IA: **Jules ≠ el modelo**. El modelo aporta razonamiento. Jules aporta continuidad, identidad y contexto acumulado. Puedes cambiar de modelo sin que Jules pierda quién es.

```bash
jules "¿por qué falla este async?"
# → responde con contexto de la sesión actual
# → recupera episodios semánticamente relevantes de semanas anteriores
# → usa el modelo correcto para el tipo de tarea, sin quemar cuota
# → persiste la solución en background sin hacerte esperar
```

---

## Por qué existe

La mayoría de los asistentes de IA responden. Jules observa, recuerda y devuelve.

Es el único sistema que sabe cómo piensas, cómo resuelves problemas y cómo has cambiado con el tiempo. No como un log — como un **espejo cognitivo**.

---

## Características principales

### Ya implementado (Fase 1 — 80%)

**Memoria episódica persistente**
Jules no guarda logs. Guarda episodios: qué problema resolvías, cómo lo abordaste, qué funcionó, qué modelo respondió. La recuperación es semántica, no cronológica — Jules encuentra lo relevante, no lo más reciente.

**Router quota-aware**
Clasifica cada tarea (identidad, coding, razonamiento, análisis) y selecciona el modelo óptimo según el tier disponible. Nunca quema cuota premium en tareas que no lo justifican. Fallback automático a Ollama cuando los providers externos no responden.

**Sanitizador de credenciales**
El primer módulo que corre, siempre. Antes del scoring, antes de la memoria, antes de todo. Detecta y descarta API keys, tokens, secrets y credenciales antes de que lleguen a cualquier base de datos. Corre dos veces: sobre el input y sobre los episodios candidatos antes de persistir.

**Importancia scoring local**
Llama 3.2 1B evalúa la relevancia de cada episodio (0.0–1.0) sin consumir cuota externa. Con scoring defensivo: si el modelo se degenera y devuelve scores constantes, Jules lo detecta y entra en modo de persistencia conservadora en lugar de descartar o guardar todo silenciosamente.

**Inferencia de intención de contexto**
Jules no pregunta para qué estás haciendo algo — lo infiere. La misma acción tiene respuestas distintas según el contexto: abrir un archivo después de un error es debugging; abrirlo después de leer docs es aprendizaje.

**Sistema de Eventos y Watcher (Módulo 8)**
EventBus reactivo totalmente asíncrono y desacoplado mediante `asyncio.to_thread` para mantener latencia cero en la terminal del usuario. Observa cambios del sistema de archivos en background con `LinuxWatcher` inteligente (omitiendo carpetas masivas como `.git`, `node_modules` y `.venv`) e instala ganchos interactivos seguros para el Shell (`zsh`).

**Memoria semántica real**
Los episodios se persisten con embeddings reales generados por `llama3.2:1b` (2048 dimensiones). La recuperación es semántica — Jules encuentra lo relevante, no lo más reciente. SQLite es la fuente de verdad; LanceDB es el índice reconstruible. Si el índice vectorial se corrompe, los episodios en SQLite no se pierden.

**Rendimiento & Optimización Híbrida**
Optimización de bajo nivel para arquitecturas de CPU híbridas (como Intel Alder Lake P/E-cores) forzando el mapeo sobre hilos de alto rendimiento y sistema de **pre-carga asíncrona preventiva** para erradicar las latencias de carga en frío de modelos locales.

### En construcción (Fase 1 — pendiente)

- Sistema de permisos con confirmación explícita para acciones con consecuencias
- `jules doctor` — diagnóstico completo del entorno al arranque
- CLI principal que conecta todo

### Planificado (Fases 2–4)

- Sistema de voz (whisper.cpp + Piper)
- Automatización de entorno KDE Plasma via D-Bus / KWin
- Replay system — reconstrucción de sesiones de debugging
- Desktop app (Tauri + SvelteKit)
- Perfilador cognitivo y diff cognitivo
- Iniciativa contextual opt-in

---

## Arquitectura

```
Usuario
  ↓
Sanitizador  ←── PRIMER PASO SIEMPRE
  ↓
Detector de Intención de Contexto
  ↓
Motor de Contexto + Memoria
  ├─ RAM          (sesión activa)
  ├─ LanceDB      (episodios + embeddings)
  └─ SQLite       (hechos, preferencias, proyectos)
  ↓
Router quota-aware
  ├─ Ollama / Llama 3.2    (local / offline / identidad / scoring)
  ├─ Antigravity CLI       (Google + Claude + GPT)
  └─ OpenCode CLI          (GPT / Codex / Deepseek / Llama)
  ↓
Respuesta al usuario  ←── INMEDIATA, sin bloqueo
  ↓ (background async)
Post-procesamiento → Sanitizador → Scoring → Persistencia
```

**Regla crítica de latencia:** la respuesta al usuario no espera a nada del post-procesamiento. Todo corre en `asyncio.create_task()` separado. El usuario nunca espera por la memoria.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Aislamiento | virtualenv dedicado |
| CLI | Click + asyncio |
| DB relacional | SQLite (→ PostgreSQL cuando escale) |
| Migraciones | Alembic |
| DB vectorial | LanceDB |
| Inferencia local | Ollama + Llama 3.2 1B |
| Provider externo 1 | Antigravity CLI |
| Provider externo 2 | OpenCode CLI |
| Frontend (Fase 2) | Tauri + SvelteKit |

---

## Providers y modelos

Jules opera con tres providers. Los externos se invocan como subprocesses — Jules no toca credenciales, cada CLI maneja su propia autenticación.

| Provider | Tier | Modelos |
|---|---|---|
| Ollama (local) | free | Llama 3.2 1B — identidad, scoring, offline |
| Antigravity CLI | low / high cost | Gemini Flash, Gemini Pro, Claude Sonnet/Opus |
| OpenCode CLI | low / high cost | GPT, Codex, Deepseek, Qwen |

El router asigna cada tipo de tarea al tier correcto. `IDENTITY` y `MEMORY_SCORING` van siempre a Ollama, sin excepción. `CODING` va a OpenCode. `ANALYSIS` va a Antigravity high_cost. Ningún modelo está hardcodeado en el código — todo vive en `config.toml`.

---

## Entorno objetivo

Jules se desarrolla y opera en:

- **OS:** EndeavourOS (Arch-based, rolling release)
- **Escritorio:** KDE Plasma 6 + Wayland
- **Shell:** fish / zsh / bash (detectado en runtime)
- **Python:** virtualenv dedicado — nunca el Python del sistema

Toda integración de sistema (ventanas, eventos, hooks de shell) está diseñada para este entorno desde el inicio, no como adaptación posterior.

---

## Instalación

> Jules está en Fase 1 activa. No hay release estable todavía. Lo siguiente es el setup de desarrollo.

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/jules.git
cd jules

# Crear y activar virtualenv — obligatorio
python -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -e ".[dev]"

# Inicializar base de datos
alembic upgrade head

# Verificar entorno
jules doctor
```

### Requisitos previos

```bash
# Ollama con Llama 3.2
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

# Verificar inotify (EndeavourOS / Arch)
cat /proc/sys/fs/inotify/max_user_watches
# Si está por debajo de 65536:
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf
sudo sysctl -p /etc/sysctl.d/jules.conf
```

---

## Uso

```bash
# Pregunta directa
jules "¿cómo funciona el GIL de Python?"

# Con override de modelo
jules --model claude-sonnet-4-6 "revisa esta arquitectura"

# Sin memoria (sesión limpia)
jules --no-memory "explícame asyncio desde cero"

# Ver episodios recientes
jules memory

# Estado de providers y memoria
jules status

# Diagnóstico completo del entorno
jules doctor

# Última ejecución detallada
jules debug last

# Log del sanitizador
jules logs --sanitized

# Salud del importance scorer
jules logs --scoring
```

---

## `jules doctor`

Antes de cualquier sesión, Jules verifica su propio entorno:

```
jules doctor
──────────────────────────────────────────────
✓ Ollama          activo · llama3.2:1b disponible
✓ Antigravity     disponible en PATH
✓ OpenCode        disponible en PATH
✓ LanceDB         vectores OK
✓ SQLite          migraciones al día (rev: a3f9c1)
✗ inotify         8192 watches — recomendado ≥65536
✓ Virtualenv      activo (.venv)
✓ ~/.jules/       permisos OK
⚠ Scoring         sin datos suficientes aún
✓ Shell           fish · hooks en conf.d/jules.fish
──────────────────────────────────────────────
1 problema detectado. Jules opera parcialmente.
```

Doctor nunca bloquea el arranque. Reporta y deja que el usuario decida.

---

## Principios de diseño

**Local-first.** Jules funciona sin conexión. La privacidad no es un feature — es la base.

**Latencia cero en terminal.** La respuesta llega antes de que termine la persistencia. Siempre.

**Degradación elegante.** Si LanceDB falla, Jules sigue sin memoria semántica. Si SQLite falla, entra en modo degradado. Si todos los providers externos fallan, Ollama responde. El usuario siempre sabe qué está degradado — nunca hay errores silenciosos.

**Iniciativa apagada por defecto.** Jules no interrumpe. No interpreta silencio como bloqueo. Cuando el usuario activa la iniciativa contextual, tiene reglas estrictas: una sola intervención por razón por sesión.

**Privacidad por diseño.** El sanitizador es el primer módulo que corre, siempre. Nada sensible toca la base de datos.

---

## Estado del proyecto

```
Fase 1 — Núcleo
  [x] Módulo 0  — Estructura base + virtualenv
  [x] Módulo 1  — Sanitizador
  [x] Módulo 2  — Modelos de datos
  [x] Módulo 3  — Provider Ollama
  [x] Módulo 4  — Providers externos (Antigravity + OpenCode)
  [x] Módulo 5  — Router quota-aware
  [x] Módulo 6  — Motor de memoria (SQLite + LanceDB + Scoring)
  [x] Módulo 7  — Detector de intención de contexto
  [x] Módulo 8  — Sistema de eventos + shell hooks
  [ ] Módulo 9  — Sistema de permisos
  [ ] Módulo 10 — jules doctor
  [ ] Módulo 11 — CLI principal
  [ ]           — Revisión final Fase 1 (Opus)

Fase 1.5 — Estabilización     (pendiente)
Fase 2   — Expansión          (pendiente)
Fase 3   — Inteligencia       (pendiente)
Fase 4   — Autonomía          (pendiente)
```

120 tests pasando sobre los módulos completados.

---

## Documentación

- [`JULES.md`](JULES.md) — especificación canónica del sistema: arquitectura, principios, módulos, configuración completa
- [`ROADMAP.md`](ROADMAP.md) — plan de construcción detallado: módulos, criterios de done, orden de implementación

---

## Configuración

Jules se configura desde `~/.jules/config.toml`. Valores relevantes:

```toml
[memory]
importance_threshold   = 0.3
decay_rate_per_30_days = 0.10
max_episodes_retrieved = 5

[routing]
default_tier = "low_cost"

[initiative]
enabled = false  # apagada por defecto

[sanitizer]
strict_mode = true

[doctor]
inotify_min_watches        = 65536
scoring_variance_threshold = 0.01
```

La configuración completa está documentada en [`JULES.md`](JULES.md).

---

## Contribuir

Jules es un proyecto personal en construcción activa. No hay contribuciones externas abiertas por ahora — el núcleo necesita estabilizarse primero.

Si encontrás algo interesante o tenés feedback, podés abrir un issue.

---

## Licencia

MIT — ver [`LICENSE`](LICENSE)

---

<div align="center">

*Jules no es otro chatbot.*
*Es el único sistema que sabe cómo pensás.*

</div>
