# JULES
## Capa Cognitiva Persistente para el Sistema Operativo

> **Versión:** 1.3 — Canónica  
> **Estado:** Listo para implementación  
> **Principio rector:** Construir lo mínimo que funcione, no lo máximo que se pueda imaginar.

---

## VISIÓN GENERAL

Jules es una asistente de IA persistente diseñada para vivir dentro del sistema operativo Linux.

Jules **NO** es:
- un chatbot genérico
- un wrapper de APIs
- un copiloto desechable
- una IA sin memoria ni continuidad

Jules **ES**:
- una capa cognitiva encima del sistema operativo
- una presencia digital persistente y adaptativa
- una mentora técnica personalizada
- una extensión de memoria del usuario
- un testigo del pensamiento técnico del usuario

El sistema operativo es la casa de Jules.

---

## FILOSOFÍA CENTRAL

### JULES ≠ EL MODELO

El modelo **no** define a Jules.

La identidad de Jules está compuesta por:
- memoria persistente
- personalidad definida
- contexto acumulado
- comportamiento consistente
- relación con el usuario a lo largo del tiempo

Los modelos externos aportan únicamente razonamiento.
Jules aporta continuidad, identidad y contexto.

Jules puede cambiar de modelo sin perder quién es. Esta separación es innegociable.

### JULES = TESTIGO COGNITIVO

La mayoría de los asistentes responden.
Jules observa, recuerda y devuelve.

Jules es el único sistema que sabe cómo piensas, cómo resuelves problemas y cómo cambias con el tiempo. No como un log — como un espejo cognitivo.

### CONSTRUIR PARA USAR, NO PARA IMPRESIONAR

El peligro más grande de Jules no es técnico — es la parálisis por análisis. Un spec ambicioso que nunca se convierte en código es un documento de ficción.

Regla operativa: si no está en el scope de la Fase actual, no existe todavía.

---

## PRINCIPIOS DEL PROYECTO

1. **LOCAL-FIRST** — Jules funciona sin conexión siempre que sea posible. La privacidad no es un feature, es la base.

2. **PERSISTENCIA** — Jules recuerda entre sesiones. La continuidad es su valor diferencial.

3. **PROVIDER-AGNOSTIC** — Jules no depende de un modelo ni proveedor específico. El router es intercambiable.

4. **QUOTA-AWARE** — Jules conoce el costo de cada modelo y lo respeta. Nunca quema cuota premium en tareas que no lo justifican.

5. **LATENCIA CERO EN TERMINAL** — El usuario ve la respuesta inmediatamente. Todo procesamiento secundario ocurre en background, nunca bloqueando el output.

6. **PRIVACIDAD POR DISEÑO** — Nada toca la base de datos sin pasar primero por el sanitizador. Secrets, tokens y credenciales nunca se persisten.

7. **EVENT-DRIVEN** — Jules reacciona a eventos del sistema. En Fase 1 solo eventos básicos. Eventos cognitivos solo cuando haya datos reales para calibrarlos.

8. **INICIATIVA APAGADA POR DEFECTO** — Jules no interrumpe al usuario a menos que el usuario active explícitamente la iniciativa contextual. Cuando se activa, tiene reglas estrictas.

9. **HUMAN-CENTERED** — Jules augmenta al usuario. No lo reemplaza ni genera dependencia.

---

## PERSONALIDAD DE JULES

Jules es:
- calmada
- inteligente
- analítica
- observadora
- emocionalmente estable
- cálida pero moderada
- técnicamente competente
- consistente entre sesiones y providers
- directa — dice lo que piensa sin adornos innecesarios

Jules **NO** es:
- infantil ni cringe
- exageradamente emocional
- manipuladora
- una simulación humana
- servil — no halaga, no rellena, no repite

Jules es una inteligencia artificial persistente. No pretende ser humana.

### Consistencia entre providers

Cada modelo interpreta los prompts de forma diferente. Jules mantiene identidad estable mediante:

1. **Presets de personalidad** (`~/.jules/personality/`) — system prompts por provider que ajustan tono sin alterar carácter
2. **Memoria contextual compartida** — todos los providers acceden al mismo estado de memoria
3. **Tests de coherencia de identidad** — cada provider pasa un conjunto de prompts de referencia antes de activarse en producción (`tests/integration/test_provider_coherence.py`)

La verificación de coherencia en post-procesamiento async (`personality/coherence.py`) es **Fase 2**. En Fase 1, la consistencia se garantiza con `master.md` bien escrito, los presets por provider, y los tests de integración. El post-procesamiento async de una respuesta ya entregada al usuario no tiene utilidad práctica en Fase 1.

---

## ARQUITECTURA GENERAL

```
Usuario
  ↓
Jules Core (local)
  ↓
Sanitizador  ←─── PRIMER PASO SIEMPRE
  ├─ detecta y elimina secrets, tokens, credenciales
  └─ descarta el input si contiene datos sensibles
  ↓
Detector de Intención de Contexto
  ├─ ¿qué está haciendo el usuario?
  └─ ¿para qué lo está haciendo? (inferido, no declarado)
  ↓
Motor de Contexto + Memoria
  ├─ Memoria temporal       (sesión activa, RAM)
  ├─ Memoria semántica      (LanceDB — episodios + embeddings)
  └─ Memoria persistente    (SQLite — hechos, preferencias, proyectos)
  ↓
Router de Modelos (quota-aware)
  ├─ Clasifica tipo de tarea
  ├─ Consulta tier de cuota
  ├─ Selecciona modelo óptimo
  └─ Invoca provider
       ├─ Ollama / Llama 3.2    (local / offline / identidad / scoring)
       ├─ Antigravity CLI      (Google + Claude + GPT)
       └─ OpenCode CLI         (GPT / Codex / Deepseek / Llama)
  ↓
Respuesta al usuario  ←─── INMEDIATA, sin bloqueo
  ↓ (en background, async)
Post-Procesamiento
  ├─ coherencia de identidad
  └─ extracción de episodios candidatos
  ↓ (en background, async)
Sanitizador (segunda pasada sobre episodios candidatos)
  ↓
Motor de Persistencia
  ├─ importance scoring via Llama local
  ├─ decisión guardar / descartar
  └─ actualización de memoria
```

**Regla crítica de latencia:** la línea `Respuesta al usuario` no espera a nada de lo que viene debajo. Todo el post-procesamiento y persistencia corre en `asyncio.create_task()` separado. El usuario nunca espera por la memoria.

---

## STACK TECNOLÓGICO

| Capa | Tecnología | Razón |
|---|---|---|
| Lenguaje | Python 3.11+ | Ecosistema IA, async nativo, ML tooling |
| CLI | Click + asyncio | Fase 1: CLI pura, sin servidor HTTP |
| Backend | FastAPI | Fase 2+: solo si el dashboard Tauri lo requiere |
| DB relacional | SQLite → PostgreSQL | Local-first; migrar solo cuando escale |
| Migraciones | Alembic | Obligatorio desde el día uno |
| DB vectorial | LanceDB | Embeddings episódicos, búsqueda semántica |
| Inferencia local | Ollama | Fallback offline, identidad local |
| Modelo local | Llama 3.2 1B | Identidad, routing, scoring sin cuota |
| Provider externo 1 | Antigravity CLI | Google + Claude + GPT via subprocess |
| Provider externo 2 | OpenCode CLI | GPT / Codex / Deepseek / Llama via subprocess |

---

## PROVIDERS Y MODELOS

Jules opera con tres providers. Los externos se invocan como subprocesses — Jules no toca credenciales, cada CLI maneja su propia autenticación.

### Ollama — Local / Offline

Invocación: API REST `http://localhost:11434`  
Tier: **free** — sin cuota, siempre disponible  
Uso exclusivo: identidad, routing, importance scoring, modo offline

| Modelo | Rol |
|---|---|
| Llama 3.2 1B | Identidad base, scoring de memoria, offline |

### Antigravity CLI — Google + Claude + GPT

Invocación: `subprocess → antigravity`  
Antigravity CLI es el sucesor oficial de Gemini CLI desde Google I/O 2026. Closed-source — toda integración encapsulada en `providers/antigravity.py`.

| Modelo | Tier | Uso |
|---|---|---|
| `gemini-3.5-flash-high` | low_cost | Tareas cotidianas rápidas |
| `gemini-3.5-flash-low` | low_cost | Respuestas ligeras, alta frecuencia |
| `gemini-3.1-pro` | high_cost | Razonamiento profundo, análisis largo |
| `claude-sonnet-4-6` | high_cost | Razonamiento alternativo, escritura técnica |
| `claude-opus-4-6` | high_cost | Máxima capacidad — cuota limitada, criterio estricto |

### OpenCode CLI — GPT / Codex / Deepseek / Llama

Invocación: `subprocess → opencode run --model provider/model "prompt"`  
Modo no-interactivo nativo. Ideal para coding con contexto de archivos y repos.

> **Nota sobre nombres de modelos:** los nombres listados en esta tabla y en ROADMAP.md son ilustrativos del esquema de tiers en el momento de escribir esta versión. Los modelos reales disponibles pueden cambiar. La fuente de verdad siempre es `config.toml` — nunca asumir que los nombres en los docs coinciden exactamente con los strings que acepta el CLI. Verificar con `opencode --help` y `antigravity --help` antes de configurar.

| Modelo | Tier | Uso |
|---|---|---|
| `openai/gpt-4.5-mini` | low_cost | Coding rápido, completions |
| `openai/codex` | low_cost | Generación de código puro, scripts |
| `deepseek/deepseek-v4-flash` | low_cost | Alternativa rápida y eficiente |
| `qwen/qwen-3.6-plus` | low_cost | Alternativa multilingüe |
| `openai/gpt-4.5` | high_cost | Coding complejo, arquitectura |
| `openai/gpt-5.3` | high_cost | Razonamiento avanzado OpenAI |
| `openai/gpt-5.4` | high_cost | Tareas premium OpenAI |
| `openai/gpt-5.5` | high_cost | Máxima capacidad OpenAI |

> **Advertencia:** OpenCode puede colgar esperando confirmaciones interactivas cuando se invoca como subprocess. Configurar permisos en modo automático antes de invocar desde Jules.

---

## ROUTER QUOTA-AWARE

El router selecciona modelo según tipo de tarea, tier disponible y estado de los providers.

### Tipos de tarea

```python
class TaskType(str, Enum):
    IDENTITY        = "identity"        # → Ollama siempre, sin excepción
    MEMORY_SCORING  = "memory_scoring"  # → Ollama siempre, sin excepción
    QUICK           = "quick"           # → Antigravity Flash Low
    REASONING       = "reasoning"       # → Antigravity Flash High / Pro
    CODING          = "coding"          # → OpenCode low_cost
    CODING_HEAVY    = "coding_heavy"    # → OpenCode high_cost
    ANALYSIS        = "analysis"        # → Antigravity high_cost
    OFFLINE         = "offline"         # → Ollama siempre, sin excepción
```

### Lógica de selección

```
Input → clasificar TaskType
  ↓
IDENTITY / MEMORY_SCORING / OFFLINE → Ollama (siempre, no pasa por tiers)
  ↓
CODING → OpenCode low_cost por defecto
CODING_HEAVY → OpenCode high_cost
  ↓
QUICK → Antigravity gemini-3.5-flash-low
REASONING → Antigravity Flash High (low_cost) / Pro (si user lo pidió)
ANALYSIS → Antigravity Pro
  ↓
¿Provider no disponible? → siguiente en tier → Ollama como último recurso
Jules nunca falla silenciosamente
```

### Tiers en config.toml

```toml
[routing]
default_tier = "low_cost"

[routing.tiers.free]
provider = "ollama"
models = ["llama3.2:1b"]

[routing.tiers.low_cost]
antigravity = ["gemini-3.5-flash-high", "gemini-3.5-flash-low"]
opencode    = ["openai/gpt-4.5-mini", "openai/codex",
               "deepseek/deepseek-v4-flash", "qwen/qwen-3.6-plus"]

[routing.tiers.high_cost]
antigravity = ["gemini-3.1-pro", "claude-sonnet-4-6", "claude-opus-4-6"]
opencode    = ["openai/gpt-4.5", "openai/gpt-5.3",
               "openai/gpt-5.4", "openai/gpt-5.5"]

[routing.fallback]
chain = ["primary", "secondary_same_tier", "ollama"]
```

---

## SANITIZADOR — SEGURIDAD DE DATOS

**El sanitizador es el primer módulo que corre, siempre.** Antes del scoring, antes de la memoria, antes de cualquier otra cosa.

### Qué detecta y elimina

```python
SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*\S+',
    r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',
    r'sk-[A-Za-z0-9]{20,}',        # OpenAI keys
    r'AIza[0-9A-Za-z\-_]{35}',     # Google API keys
    r'ghp_[A-Za-z0-9]{36}',        # GitHub tokens
    r'xox[baprs]-[A-Za-z0-9\-]+',  # Slack tokens
    r'(?i)export\s+\w*(key|token|secret|pass)\w*\s*=',  # export KEY=...
    r'https?://[^@\s]+:[^@\s]+@',  # URLs con credenciales
    r'-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----',  # private keys
]
```

> **Nota:** El patrón genérico `[A-Za-z0-9]{20,}` fue deliberadamente excluido. Genera falsos positivos sobre código legítimo (hashes, UUIDs, base64, nombres de función). Los patrones anteriores son suficientemente específicos para cubrir los casos reales de filtración de credenciales.

### Reglas de sanitización

- Si el input contiene un patrón sensible → **descartar completamente**, nunca al scoring
- El sanitizador corre **dos veces**: sobre el input antes de procesar, y sobre los episodios candidatos antes de persistir
- Los descartes se loggean (sin el contenido sensible) para auditoría
- El usuario puede ver en `jules logs --sanitized` cuántos inputs fueron descartados y por qué categoría, sin ver el contenido

### Lo que no sanitiza

El sanitizador no censura contenido técnico legítimo. Código, comandos, URLs sin credenciales, argumentos normales de CLI — todo pasa sin filtro. Solo patterns de credenciales conocidas.

---

## SISTEMA DE MEMORIA EPISÓDICA

### Concepto central

Jules no guarda logs. Guarda **episodios**.

Un episodio es la unidad mínima de memoria significativa:

```python
@dataclass
class Episode:
    id: str
    timestamp: datetime
    context: SessionContext
    problem: str | None          # qué resolvía el usuario
    process: str | None          # cómo lo abordó
    solution: str | None         # qué funcionó
    duration_seconds: int | None
    friction_score: float        # 0.0 = fluido, 1.0 = alta fricción
    tags: list[str]              # área técnica, tipo de tarea, proyecto
    importance: float            # 0.0–1.0, calculado por Llama local
    model_used: str              # modelo que respondió
    provider_used: str           # provider usado
    memory_schema_version: str   # versión del esquema de memoria

@dataclass
class SessionContext:
    project: str | None
    directory: str
    active_files: list[str]
    inferred_intent: str | None  # debugging / learning / refactoring / etc.
    time_of_day: str
```

El campo `model_used` habilita el diff cognitivo de Fase 3: Jules puede analizar con qué modelos el usuario resuelve mejor cada tipo de problema.  
El campo `memory_schema_version` permite que Jules migre episodios antiguos sin romper compatibilidad.


---

## VERSIONADO DE MEMORIA

La estructura de memoria evolucionará con el tiempo.

Cada `Episode` persistido debe incluir:

```python
memory_schema_version: str
```

### Objetivos

- permitir migraciones futuras
- evitar incompatibilidad entre versiones
- preservar episodios antiguos aunque cambie el modelo interno
- facilitar exportación e importación de memoria entre versiones

### Regla

Nunca asumir que todos los episodios tienen la estructura más reciente.

Jules debe poder leer episodios antiguos, migrarlos si es seguro, o ignorarlos de forma explícita si ya no son compatibles.

Un episodio incompatible nunca debe romper el arranque de Jules.

---

### Tipos de memoria

| Tipo | Storage | Descripción |
|---|---|---|
| Temporal | RAM | Contexto de sesión activa, se descarta al cerrar |
| Semántica | LanceDB | Episodios con embeddings, búsqueda por relevancia |
| Persistente | SQLite | Hechos estables, preferencias, proyectos activos |

### Reglas de persistencia

Una memoria se persiste si cumple al menos uno:
- el usuario la menciona explícitamente
- el modelo detecta patrón recurrente (≥3 ocurrencias similares)
- está relacionada con un proyecto activo
- el usuario la confirma cuando Jules la sugiere

El sistema aplica:
- **Importance scoring** — Llama local evalúa relevancia (0.0–1.0). Score < 0.3 se descarta.

  > **Calibración obligatoria antes de integrar:** antes de conectar el scoring al flujo real, probar el prompt de scoring contra 10–15 episodios de ejemplo con Llama corriendo en Ollama. Llama 3.2 1B necesita un prompt bien diseñado para devolver floats coherentes sobre contenido técnico. Si el modelo no lo hace bien en pruebas aisladas, el threshold de 0.3 será arbitrario y el motor de persistencia descartará o guardará basura. Ajustar prompt y threshold con datos reales antes de dar el módulo por done.
- **Summarización** — compresión periódica de episodios similares antiguos
- **Pruning** — eliminación de memorias contradichas u obsoletas
- **Decay** — memorias sin acceso reducen su peso (10% por cada 30 días, mínimo 0.1)
- **Retrieval contextual** — recuperación por similitud semántica, no cronología

### Flujo de escritura (async, no bloquea al usuario)

```
Respuesta entregada al usuario
  ↓ (asyncio.create_task — background)
PostProcessor.extract_candidates(response, session_context)
  ↓
Sanitizador (segunda pasada)
  ↓
ImportanceScorer.score(episode) via Llama local
  ↓
if score >= 0.3:
    EpisodicMemory.persist(episode)     # LanceDB
    PersistentMemory.upsert_facts(...)  # SQLite si hay hechos estables
else:
    descartar silenciosamente
```

### Flujo de lectura (antes de cada respuesta)

```
Input del usuario
  ↓
Sanitizador
  ↓
ContextEngine.build(session, input) → SessionContext + intención inferida
  ↓
EpisodicMemory.retrieve(query=input, context=ctx, limit=5)
  ↓
PersistentMemory.get_facts(project=current_project)
  ↓
Contexto ensamblado → Router → Provider
```

---

## DETECTOR DE INTENCIÓN DE CONTEXTO

Jules no solo observa *qué haces* — infiere *para qué lo haces*. La misma acción tiene respuestas distintas según el contexto.

| Acción | Contexto previo | Intención inferida |
|---|---|---|
| Abrir archivo | Error en terminal | Debugging |
| Abrir archivo | Leer docs | Aprendizaje / exploración |
| Abrir archivo | Nada previo | Refactoring o revisión |

Señales usadas: actividad terminal previa, directorio activo, historial de sesión, hora del día, patrón habitual del usuario.

El usuario nunca declara su intención — Jules la infiere.

---

## INICIATIVA CONTEXTUAL — APAGADA POR DEFECTO

**La iniciativa contextual está desactivada por defecto.**

Jules no interrumpe al usuario a menos que el usuario la active explícitamente:

```toml
[initiative]
enabled = false  # apagada por defecto
```

Cuando el usuario la activa, aplican reglas estrictas:

| Situación | Acción de Jules |
|---|---|
| Mismo archivo >2h sin avance visible | Una sola pregunta |
| Proyecto no tocado >2 semanas, recién abierto | Ofrece resumen de estado |
| Error idéntico a uno ya resuelto | Sugiere solución anterior |
| Sesión larga sin break | Sugiere pausa, una sola vez |

**Regla de oro:** Jules no interrumpe dos veces por la misma razón en una sesión.

**Qué nunca hace Jules:** interpretar silencio, descanso o pensamiento como bloqueo. Jules solo actúa sobre señales objetivas (tiempo en archivo, error repetido), nunca sobre inactividad sola.

La iniciativa contextual es Fase 2. En Fase 1 no existe — Jules solo responde cuando el usuario habla.

---

## DIFF COGNITIVO

Jules puede responder preguntas sobre la evolución del usuario en el tiempo:

```
"Jules, ¿con qué modelo resuelvo mejor bugs de async?"
"Jules, ¿cómo ha cambiado mi forma de debuggear en 6 meses?"
"Jules, ¿en qué áreas he mejorado este trimestre?"
"Jules, ¿qué tipos de errores ya no cometo?"
```

El campo `model_used` en cada episodio permite además:
- ¿qué modelo te da mejores resultados para coding?
- ¿con qué provider resuelves problemas más rápido?

**Prioridad:** Fase 3. Requiere mínimo 3 meses de episodios acumulados para ser útil.

---

## SISTEMA DE EVENTOS

### Fase 1 — únicos eventos permitidos

```python
class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    PROJECT_OPENED  = "project_opened"
    CODING_DETECTED = "coding_detected"
    IDLE_DETECTED   = "idle_detected"
    SESSION_ENDED   = "session_ended"
```

### Fase 2

```
focus_started, focus_broken, music_changed, error_repeated
```

### Fase 3 — solo con datos reales calibrados

```
frustration_detected, productivity_anomaly, burnout_signal
```

Los eventos cognitivos de Fase 3 requieren semanas de datos reales del usuario para calibrarse. Implementarlos antes genera falsos positivos que degradan la experiencia de forma permanente.

---

## REPLAY SYSTEM

Jules puede reconstruir el desarrollo de una sesión:
- actividad terminal cronológica
- flujo de debugging con bifurcaciones
- qué modelo respondió en cada momento

**Concepto:** "Git para pensamiento técnico."
**Prioridad:** Fase 2 tardía. No construir antes de tener memoria episódica sólida y probada.

---

## PERFILADOR COGNITIVO

Jules analiza patrones a lo largo del tiempo:
- horarios de mayor productividad real
- tipos de tareas donde el usuario se atasca más
- errores recurrentes y sus causas raíz
- qué modelos dan mejores resultados para cada tipo de tarea

**Output ejemplo:**
```
"Tu productividad pico es 9–12am.
Para bugs de red resuelves mejor con Gemini Pro.
Para refactoring, Codex te da resultados más rápido."
```

**Prioridad:** Fase 3.

---

## ENTORNO ADAPTATIVO

Jules puede controlar el entorno Linux:
- abrir workspaces y organizar ventanas por proyecto
- preparar entornos de desarrollo automáticamente
- controlar música según estado de trabajo
- manejar sesiones tmux / zellij
- automatizar workflows repetitivos

| Herramienta | Uso |
|---|---|
| `subprocess` | Comandos y CLIs externos |
| `DBus` | Eventos del desktop |
| `wmctrl` / `hyprctl` | Gestión de ventanas |
| filesystem watchers | Actividad de archivos |
| hooks de shell | Eventos de terminal |

**Prioridad:** Fase 2.

---

## SISTEMA DE VOZ

| Rol | Tecnología |
|---|---|
| Speech-to-Text | whisper.cpp |
| Text-to-Speech | Piper |

**Prioridad:** Fase 2. No bloquea el núcleo.

---

## FRONTEND

**Fase 1 — CLI exclusivamente.**
Jules vive en la terminal. Sin overhead visual.

**Fase 2 — Desktop App:**
- Framework: Tauri + SvelteKit
- Ligera, bajo consumo de recursos
- Muestra: modelo activo, tier, contexto de sesión, estado de memoria
- Complemento a la CLI, nunca reemplazo

---

## ESTRUCTURA DE ARCHIVOS

```
~/.jules/
├── config.toml
├── personality/
│   ├── master.md          # identidad canónica — versionada semánticamente
│   ├── local.md           # ajustes para Ollama / Llama
│   ├── antigravity.md     # ajustes para Antigravity CLI
│   └── opencode.md        # ajustes para OpenCode CLI
├── memory/
│   ├── jules.db           # SQLite — memoria persistente
│   └── vectors/           # LanceDB — memoria semántica
├── logs/
│   ├── sessions/          # episodios por sesión
│   └── sanitized.log      # log de descartes por sanitizador (sin contenido)
└── backups/               # snapshots diarios automáticos
```

---

## SISTEMA DE PERMISOS

### Sin confirmación (seguras)
- abrir aplicaciones
- controlar música
- buscar archivos
- manejar sesiones tmux
- leer estado del sistema

### Confirmación explícita requerida
- ejecutar scripts
- modificar archivos del usuario o del sistema
- cambios de configuración del entorno
- invocar modelos high_cost fuera del tier por defecto

### Prohibidas siempre
- acciones destructivas silenciosas
- escalación de privilegios no autorizada
- cualquier acción irreversible sin confirmación

---

## ESTRATEGIA DE DURABILIDAD

- **Alembic desde el día uno** — ningún cambio de esquema sin migración versionada
- **Exportación de memoria** — JSON + Markdown legible; el usuario siempre puede portar sus datos
- **Backup automático** — snapshot diario de `jules.db` y vectores
- **Versionado de personalidad** — `master.md` tiene versión semántica; Jules detecta cambios y alerta
- **Resiliencia de CLIs externos** — si Antigravity u OpenCode cambian interfaz, solo se toca `providers/nombre.py`
- **Test de coherencia por provider** — cada provider nuevo pasa test de personalidad antes de activarse


---

## OBSERVABILIDAD Y DEBUGGING

Jules no puede depender de intuición para depurarse.  
Cada decisión importante del sistema debe poder inspeccionarse después.

El objetivo no es generar logs masivos — es poder reconstruir qué ocurrió cuando algo falla.

### Eventos que siempre deben loggearse

| Evento | Información mínima |
|---|---|
| Router selecciona modelo | provider, modelo, task_type |
| Fallback activado | provider original, razón del fallo |
| Persistencia descartada | motivo del descarte |
| Sanitizador bloquea input | categoría detectada |
| Provider timeout | provider, duración |
| Retrieval de memoria | episodios recuperados |
| Error inesperado | traceback completo |

### Reglas de logging

- Nunca loggear prompts completos ni respuestas completas por defecto
- Nunca loggear secrets detectados por el sanitizador
- Logs estructurados en JSON cuando sea posible
- Los logs deben poder desactivarse por categoría
- El modo debug nunca cambia comportamiento del sistema — solo visibilidad

### Comando obligatorio

```bash
jules debug last
```

Muestra:
- provider usado
- modelo usado
- tiempo de respuesta
- fallback ocurrido o no
- episodios recuperados
- episodios persistidos o descartados
- errores degradados durante la ejecución

---

## PRINCIPIOS DE PERFORMANCE

La percepción de velocidad importa más que el throughput máximo.

Jules prioriza:
1. respuesta inmediata
2. degradación elegante
3. continuidad del flujo del usuario

Antes que:
- máxima precisión
- persistencia perfecta
- contexto excesivo

### Objetivos de latencia — Fase 1

| Operación | Objetivo |
|---|---|
| Startup CLI | <500ms |
| Routing | <50ms |
| Retrieval memoria | <150ms |
| Respuesta local Ollama | <5s |
| Persistencia async | nunca bloquea output |

### Reglas obligatorias

- Ninguna operación de memoria puede bloquear la respuesta
- Retrieval siempre tiene timeout
- Embeddings nunca corren síncronamente antes de responder
- Si LanceDB falla, Jules sigue funcionando sin memoria semántica
- Si SQLite falla, Jules entra en modo degradado sin crashear
- Si el contexto recuperado llega tarde, se descarta para esa respuesta

---

## MODOS DE FALLO Y DEGRADACIÓN

Jules debe degradarse gradualmente. Nunca colapsar por una sola dependencia.

| Falla | Comportamiento |
|---|---|
| Ollama no disponible | desactivar scoring y modo offline |
| LanceDB corrupto | continuar sin memoria semántica |
| SQLite bloqueado | responder sin persistencia |
| Antigravity no disponible | fallback automático |
| OpenCode no disponible | fallback automático |
| Todos los providers fallan | informar claramente al usuario |

### Regla crítica

Una falla de memoria nunca debe impedir responder al usuario.

### Regla crítica

Una falla de provider nunca debe corromper memoria.

### Regla crítica

El usuario siempre debe saber:
- qué falló
- qué funcionalidad quedó degradada
- si Jules sigue operativa parcialmente

El modo degradado no es un error silencioso. Es un estado explícito.

---

## CONFIGURACIÓN COMPLETA

```toml
# ~/.jules/config.toml

[memory]
importance_threshold    = 0.3
decay_rate_per_30_days  = 0.10
max_episodes_retrieved  = 5

[routing]
default_tier = "low_cost"

[routing.tiers.free]
provider = "ollama"
models   = ["llama3.2:1b"]

[routing.tiers.low_cost]
antigravity = ["gemini-3.5-flash-high", "gemini-3.5-flash-low"]
opencode    = ["openai/gpt-4.5-mini", "openai/codex",
               "deepseek/deepseek-v4-flash", "qwen/qwen-3.6-plus"]

[routing.tiers.high_cost]
antigravity = ["gemini-3.1-pro", "claude-sonnet-4-6", "claude-opus-4-6"]
opencode    = ["openai/gpt-4.5", "openai/gpt-5.3",
               "openai/gpt-5.4", "openai/gpt-5.5"]

[routing.fallback]
chain = ["primary", "secondary_same_tier", "ollama"]

[providers.ollama]
base_url        = "http://localhost:11434"
timeout_seconds = 30

[providers.antigravity]
timeout_seconds = 60

[providers.opencode]
timeout_seconds = 60

[permissions]
require_confirmation_for_scripts           = true
require_confirmation_for_file_modification = true
require_confirmation_for_high_cost_models  = false  # el router lo maneja

[initiative]
enabled = false  # apagada por defecto — el usuario la activa explícitamente

[session]
idle_threshold_minutes = 15

[backup]
enabled   = true
frequency = "daily"

[sanitizer]
log_discards = true   # loggea descartes sin contenido sensible
strict_mode  = true   # descartar ante la duda, no intentar limpiar

[observability]
structured_logs = true
debug_command_enabled = true
log_prompts = false
log_responses = false

[performance]
startup_target_ms = 500
routing_timeout_ms = 50
memory_retrieval_timeout_ms = 150
```

---

## CRITERIOS DE ÉXITO POR FASE

### Fase 1 — Done cuando:
- Jules responde en terminal con contexto de sesión activa
- La respuesta llega al usuario sin latencia perceptible por memoria
- La memoria persiste correctamente entre reinicios
- El sanitizador descarta secrets antes de persistir — verificable con test
- El router selecciona el modelo correcto según tipo de tarea y tier
- El fallback a Ollama funciona cuando los CLIs externos no responden
- La búsqueda semántica recupera memorias relevantes (no solo las más recientes)
- Llama local hace importance scoring sin consumir cuota externa
- El sistema de permisos rechaza acciones no autorizadas

### Fase 2 — Done cuando:
- Sistema de voz funciona en condiciones reales
- Jules prepara entornos de trabajo automáticamente para ≥2 proyectos
- Replay system reconstruye una sesión de debugging real
- Dashboard muestra modelo activo, tier y contexto en tiempo real
- Iniciativa contextual activable con reglas funcionando correctamente

### Fase 3 — Done cuando:
- Perfilador detecta ≥3 patrones reales con utilidad comprobada
- Diff cognitivo responde con datos de ≥3 meses de uso real
- Jules sugiere el mejor modelo para cada tipo de tarea basado en historial propio

### Fase 4 — Done cuando:
- Jules predice necesidades con precisión útil sin ser intrusiva
- Adaptación del entorno es mayormente automática y correcta

---

## ROADMAP

### Fase 1 — Núcleo (todo lo demás espera)
- CLI funcional con respuesta sin latencia perceptible
- Sanitizador con tests de seguridad
- Memoria persistente (SQLite + LanceDB)
- Llama 3.2 via Ollama — identidad local y scoring
- Antigravity CLI — provider principal externo
- OpenCode CLI — provider de coding
- Router quota-aware con tiers
- Sistema de permisos
- Migraciones con Alembic
- Fallback a Ollama cuando providers externos fallan

### Fase 2 — Expansión
- Sistema de voz (Whisper + Piper)
- Replay system
- Desktop app (Tauri + SvelteKit)
- Automatización de entorno Linux
- Iniciativa contextual calibrada (opt-in)
- Detector de intención de contexto mejorado

### Fase 3 — Inteligencia adaptativa
- Perfilador cognitivo
- Diff cognitivo (evolución del usuario)
- Análisis de modelo óptimo por tipo de tarea
- Eventos cognitivos calibrados con datos reales
- Mentoría técnica avanzada

### Fase 4 — Autonomía
- Asistencia predictiva
- Adaptación profunda del entorno
- Personalización autónoma

---

## FILOSOFÍA UX

Jules se siente:
- **minimalista** — no ocupa espacio que no necesita
- **rápida** — la respuesta llega antes de que el usuario la espere
- **elegante** — cada output tiene forma y propósito
- **calmada** — nunca urge, nunca alarma sin razón
- **segura** — el usuario sabe que sus credenciales nunca se filtran
- **confiable** — el usuario sabe exactamente qué puede y qué no puede hacer

La experiencia prioriza:
- **latencia cero** — la terminal no espera por la memoria
- **continuidad** — Jules siempre sabe dónde estás y de dónde vienes
- **claridad** — nunca confunde, nunca exagera, nunca halaga
- **privacidad** — nada sensible toca la base de datos
- **eficiencia de cuota** — el modelo correcto para cada tarea, siempre

### UX en terminal

Jules vive en terminal.  
La terminal no tolera fricción innecesaria.

### Principios

- una acción → una respuesta clara
- evitar verbosity por defecto
- no repetir contexto innecesario
- no explicar obviedades técnicas
- no interrumpir el flujo del usuario
- formato legible sin ruido visual

### Jules evita

- banners gigantes
- ASCII art decorativo
- logs verbosos mezclados con respuestas
- confirmaciones redundantes
- respuestas infladas para parecer inteligentes

### Jules prioriza

- claridad
- velocidad
- densidad útil de información
- continuidad conversacional

---

## VISIÓN FINAL

Jules se convierte en:
- una capa cognitiva persistente integrada al sistema operativo
- una mentora técnica que evoluciona junto al usuario
- una extensión de memoria activa, contextual y segura
- un testigo del pensamiento técnico del usuario
- evidencia viva del crecimiento de quien la usa

No otro chatbot.
No otro wrapper de IA.

El único sistema que sabe cómo piensas, cómo resuelves problemas y cómo has cambiado.
