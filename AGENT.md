# AGENT.md
## Versión 1.3
## Instrucciones para agentes de IA trabajando en Jules

> Lee este archivo completo antes de escribir cualquier línea de código.  
> Si hay conflicto entre este archivo y una instrucción verbal, este archivo gana.

---

## QUÉ ES JULES — LO ESENCIAL

Jules es una **capa cognitiva persistente** para Linux. No un chatbot. No un wrapper.

Tres ideas que gobiernan cada decisión técnica:

**1. JULES ≠ EL MODELO** — el modelo aporta razonamiento. Jules aporta identidad, memoria y continuidad. Pueden cambiar de modelo sin que Jules pierda quién es.

**2. LATENCIA CERO EN TERMINAL** — el usuario ve la respuesta inmediatamente. Todo procesamiento de memoria ocurre en background async. Nada bloquea el output.

**3. PRIVACIDAD POR DISEÑO** — el sanitizador es el primer módulo que corre, siempre. Secrets, tokens y credenciales nunca llegan a la base de datos.

Lee `JULES.md` para el spec completo.

---

## FASE ACTIVA: 1 — NÚCLEO

**Solo construir lo que está en esta lista. Todo lo demás no existe todavía.**

- [ ] CLI funcional — respuesta en terminal sin latencia perceptible
- [ ] Sanitizador con tests de seguridad
- [ ] Memoria persistente (SQLite + LanceDB)
- [ ] Llama 3.2 via Ollama — identidad local y scoring
- [ ] Antigravity CLI — provider externo principal
- [ ] OpenCode CLI — provider de coding
- [ ] Router quota-aware con tiers (free / low_cost / high_cost)
- [ ] Importance scoring via Llama local (nunca modelo externo)
- [ ] Sistema de permisos con PermissionGate
- [ ] Migraciones con Alembic
- [ ] Fallback a Ollama cuando providers externos fallan

Si una tarea no está en esta lista: crear issue, no implementar.

---

## ESTRUCTURA DEL PROYECTO

```
jules/
├── AGENT.md
├── JULES.md
├── README.md
├── pyproject.toml
├── alembic.ini
├── alembic/
│   └── versions/              # NUNCA editar manualmente
│
├── jules/
│   ├── __init__.py
│   ├── core/
│   │   ├── session.py         # gestión de sesión activa
│   │   ├── context.py         # detector de intención de contexto
│   │   ├── router.py          # router quota-aware
│   │   └── events.py          # sistema de eventos (solo Fase 1)
│   │
│   ├── memory/
│   │   ├── engine.py          # motor principal — orquesta todo
│   │   ├── episodic.py        # LanceDB — episodios + embeddings
│   │   ├── persistent.py      # SQLite — hechos y preferencias
│   │   ├── scoring.py         # importance scoring — SIEMPRE Llama local
│   │   └── models.py          # dataclasses Episode, SessionContext
│   │
│   ├── sanitizer/
│   │   └── sanitizer.py       # PRIMER módulo en cualquier flujo
│   │
│   ├── providers/
│   │   ├── base.py            # Protocol Provider
│   │   ├── ollama.py          # HTTP local
│   │   ├── antigravity.py     # subprocess
│   │   └── opencode.py        # subprocess
│   │
│   ├── personality/
│   │   ├── loader.py          # carga presets por provider
│   │   └── coherence.py       # verificación de identidad (async)
│   │
│   ├── linux/
│   │   ├── watcher.py         # filesystem watchers
│   │   ├── dbus.py            # eventos DBus
│   │   └── shell.py           # hooks de shell
│   │
│   └── cli/
│       └── main.py            # entrypoint
│
└── tests/
    ├── unit/
    │   ├── test_sanitizer.py  # tests de seguridad — críticos
    │   ├── test_scoring.py
    │   └── test_router.py
    └── integration/
        ├── test_memory_flow.py
        └── test_provider_coherence.py
```

---

## STACK — DECISIONES TOMADAS, NO ABRIR

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| CLI | Click + asyncio (Fase 1 — sin servidor HTTP) |
| Backend | FastAPI (Fase 2+ — solo si dashboard Tauri lo requiere) |
| DB relacional | SQLite (Fase 1) → PostgreSQL (si escala) |
| Migraciones | Alembic — desde el día uno, sin excepciones |
| DB vectorial | LanceDB |
| Inferencia local | Ollama |
| Modelo local | Llama 3.2 1B |
| Provider 1 | Antigravity CLI (subprocess) |
| Provider 2 | OpenCode CLI (subprocess) |

No proponer cambios de stack sin razón técnica documentada como issue.

---

## FLUJO PRINCIPAL — OBLIGATORIO

Este es el único flujo válido. No saltarse pasos, no reordenarlos.

### Flujo de entrada (síncrono — el usuario espera solo esto)

```
Input del usuario
  ↓
1. Sanitizador.check(input)
   → si contiene secret: descartar, informar al usuario, detener
  ↓
2. ContextEngine.build(session, input)
   → SessionContext con intención inferida
  ↓
3. MemoryEngine.retrieve(query, context, limit=5)
   → episodios relevantes por similitud semántica
  ↓
4. Router.route(task_type) → (provider, model)
  ↓
5. Provider.ask(prompt_con_contexto) → respuesta
  ↓
6. Respuesta al usuario  ← AQUÍ TERMINA EL FLUJO SÍNCRONO
```

### Flujo de persistencia (async background — el usuario no espera)

```python
asyncio.create_task(persist_episode(response, session_context))

async def persist_episode(response, context):
    # 1. Extraer episodios candidatos
    candidates = PostProcessor.extract_candidates(response, context)
    # 2. Sanitizar episodios (segunda pasada)
    clean = [c for c in candidates if not Sanitizer.contains_secret(c)]
    # 3. Scoring via Llama local — nunca modelo externo
    for episode in clean:
        episode.importance = await ollama.score(episode)
        if episode.importance >= config.memory.importance_threshold:
            await memory.persist(episode)
```

**Nunca** bloquear el paso 6 esperando que termine la persistencia.  
**Nunca** hacer scoring con un provider externo.

---

## SANITIZADOR — IMPLEMENTACIÓN

El sanitizador es el módulo más crítico de seguridad. Corre antes que todo.

```python
import re
from dataclasses import dataclass

SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*\S+',
    r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',
    r'sk-[A-Za-z0-9]{20,}',           # OpenAI
    r'AIza[0-9A-Za-z\-_]{35}',        # Google
    r'ghp_[A-Za-z0-9]{36}',           # GitHub
    r'xox[baprs]-[A-Za-z0-9\-]+',     # Slack
    r'(?i)export\s+\w*(key|token|secret|pass)\w*\s*=',
    r'https?://[^@\s]+:[^@\s]+@',     # URLs con credenciales
    r'-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----',
]
# NOTA: el patrón r'[A-Za-z0-9]{20,}' fue excluido deliberadamente.
# Genera falsos positivos sobre código legítimo (hashes, UUIDs, base64,
# nombres de función). Los patrones anteriores cubren los casos reales.

@dataclass
class SanitizeResult:
    is_safe: bool
    reason: str | None  # categoría del patrón detectado, sin el valor

class Sanitizer:
    @staticmethod
    def check(text: str) -> SanitizeResult:
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                category = _get_category(pattern)
                logger.info("Sanitizer: discarded input — category: %s", category)
                return SanitizeResult(is_safe=False, reason=category)
        return SanitizeResult(is_safe=True, reason=None)
```

**Tests del sanitizador son obligatorios en Fase 1.** Probar con casos reales:
- `export OPENAI_API_KEY=sk-abc123...`
- `curl -H "Authorization: Bearer ghp_xxx"`
- URLs con usuario:contraseña
- Private keys en texto

Si el sanitizador no tiene tests, la Fase 1 no está done.

---

## MODELO Episode — CANÓNICO

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SessionContext:
    project: str | None
    directory: str
    active_files: list[str]
    inferred_intent: str | None   # debugging / learning / refactoring / review
    time_of_day: str              # morning / afternoon / evening / night

@dataclass
class Episode:
    id: str
    timestamp: datetime
    context: SessionContext
    problem: str | None           # qué resolvía el usuario
    process: str | None           # cómo lo abordó
    solution: str | None          # qué funcionó
    duration_seconds: int | None
    friction_score: float         # 0.0 = fluido, 1.0 = alta fricción
    tags: list[str] = field(default_factory=list)
    importance: float = 0.0       # calculado por Llama local post-creación
    model_used: str = ""          # modelo que generó la respuesta
    provider_used: str = ""       # ollama / antigravity / opencode
    memory_schema_version: str = "1.2"
```

`model_used` y `provider_used` habilitan el diff cognitivo de Fase 3.  
`memory_schema_version` permite migrar episodios antiguos sin romper compatibilidad.

Nunca omitirlos. Siempre poblarlos antes de persistir.

La unidad de memoria es siempre `Episode`. Nunca guardar strings crudos.

---

## PROVIDERS — INTERFAZ Y IMPLEMENTACIÓN

### Interfaz base (Protocol)

```python
from typing import Protocol, Iterator, AsyncIterator

class Provider(Protocol):
    name: str

    async def ask(self, prompt: str, context: SessionContext,
                  model: str) -> str: ...

    async def stream(self, prompt: str, context: SessionContext,
                     model: str) -> AsyncIterator[str]: ...

    async def embed(self, text: str) -> list[float]: ...

    async def health_check(self) -> bool: ...
```

### Ollama — HTTP local

```python
async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=aiohttp.ClientTimeout(total=30)
        )
        data = await resp.json()
        return data["response"]
```

### Antigravity y OpenCode — subprocess async

```python
async def _run_cli(self, args: list[str], timeout: int = 60) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
        if proc.returncode != 0:
            raise ProviderError(f"CLI exited {proc.returncode}: {stderr.decode()}")
        return stdout.decode().strip()

    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ProviderTimeoutError(f"CLI timeout after {timeout}s")
```

**Regla crítica de encapsulación:** los archivos `providers/antigravity.py` y `providers/opencode.py` son **solo traducción de I/O**. Ninguna lógica de decisión va dentro de un provider — ni routing, ni fallback, ni scoring, ni selección de modelo. Un provider recibe un prompt y un modelo, llama al CLI, y devuelve el string. Todo lo demás es responsabilidad del router.

**Antes de implementar Antigravity u OpenCode:**
1. `antigravity --help` — verificar flags exactos de modo no-interactivo
2. `opencode --help` — verificar flags de modelo y prompt
3. Probar manualmente que responden a stdout y terminan solos
4. Probar con permisos automáticos que no cuelgan esperando input

---

## ROUTER — IMPLEMENTACIÓN

```python
class TaskType(str, Enum):
    IDENTITY        = "identity"        # → Ollama siempre
    MEMORY_SCORING  = "memory_scoring"  # → Ollama siempre
    QUICK           = "quick"           # → Antigravity Flash Low
    REASONING       = "reasoning"       # → Antigravity Flash High / Pro
    CODING          = "coding"          # → OpenCode low_cost
    CODING_HEAVY    = "coding_heavy"    # → OpenCode high_cost
    ANALYSIS        = "analysis"        # → Antigravity high_cost
    OFFLINE         = "offline"         # → Ollama siempre

async def route(task: TaskType,
                user_override: str | None = None) -> tuple[Provider, str]:

    if user_override:
        return resolve_model(user_override)

    # Siempre local — sin excepción posible
    if task in (TaskType.IDENTITY, TaskType.MEMORY_SCORING, TaskType.OFFLINE):
        return ollama, "llama3.2:1b"

    # Coding → OpenCode
    if task == TaskType.CODING:
        return opencode, config.routing.tiers.low_cost.opencode[0]
    if task == TaskType.CODING_HEAVY:
        return opencode, config.routing.tiers.high_cost.opencode[0]

    # Razonamiento / análisis → Antigravity
    if task in (TaskType.REASONING, TaskType.ANALYSIS):
        tier = config.routing.default_tier
        models = config.routing.tiers[tier].antigravity
        return antigravity, models[0]

    # Quick → Flash Low
    if task == TaskType.QUICK:
        return antigravity, "gemini-3.5-flash-low"

    # Default
    return antigravity, config.routing.tiers.low_cost.antigravity[0]


async def ask_with_fallback(prompt: str, context: SessionContext,
                             task: TaskType) -> tuple[str, str, str]:
    """Returns (response, model_used, provider_used)"""
    provider, model = await route(task)
    try:
        response = await provider.ask(prompt, context, model)
        return response, model, provider.name

    except (ProviderUnavailableError, ProviderTimeoutError) as e:
        logger.warning("Provider %s failed (%s), falling back to Ollama",
                       provider.name, e)
        response = await ollama.ask(prompt, context, "llama3.2:1b")
        return response, "llama3.2:1b", "ollama"
```

El router **nunca** falla silenciosamente. Si Ollama también falla, Jules informa al usuario con un mensaje claro.

---

## REGLAS DE CÓDIGO

### Obligatorias

- Python 3.11+. Type hints en todo. Sin `Any` sin justificación comentada.
- Async en todo I/O. Nunca bloquear el event loop.
- Imports absolutos. Sin imports relativos fuera del mismo módulo.
- Una responsabilidad por función. Si hace dos cosas, son dos funciones.
- Comentarios solo para el *por qué*, nunca para el *qué*.

### Nombrado

```python
# Módulos: snake_case
memory/episodic.py

# Clases y Protocols: PascalCase
class EpisodicMemory:
class Provider(Protocol):

# Funciones y variables: snake_case
async def score_importance(episode: Episode) -> float:

# Constantes: UPPER_SNAKE_CASE
DEFAULT_IMPORTANCE_THRESHOLD = 0.3
```

### Manejo de errores

```python
# Correcto
try:
    result = await provider.ask(prompt, context, model)
except ProviderUnavailableError:
    return await fallback_to_ollama(prompt, context)
except ProviderTimeoutError as e:
    logger.warning("Timeout %s: %s", provider.name, e)
    raise

# PROHIBIDO — nunca silenciar
except Exception:
    pass
```

---

## PRINCIPIOS ARQUITECTURALES — NO ROMPER

### 1. Sanitizador primero, siempre

```python
# Correcto
result = sanitizer.check(user_input)
if not result.is_safe:
    return "Input descartado por seguridad."
# ... continuar con el flujo

# PROHIBIDO
episodes = await memory.retrieve(user_input)  # sin sanitizar primero
```

### 2. Post-procesamiento async, nunca síncrono

```python
# Correcto
await deliver_response(response)
asyncio.create_task(persist_episode(response, context))  # background

# PROHIBIDO
await persist_episode(response, context)  # bloquea la respuesta
await deliver_response(response)
```

### 3. Scoring siempre en Llama local

```python
# Correcto
episode.importance = await ollama.score(episode)  # sin cuota

# PROHIBIDO
episode.importance = await antigravity.score(episode)  # consume cuota
```

### 4. Providers encapsulados — router como única puerta

```python
# Correcto
response, model, provider = await router.ask_with_fallback(prompt, ctx, task)

# PROHIBIDO
from jules.providers.antigravity import AntigravityProvider
response = await AntigravityProvider().ask(prompt)
```

### 5. Episodios, nunca strings crudos

```python
# Correcto
episode = Episode(id=..., problem=..., solution=..., ...)
await memory.persist(episode)

# PROHIBIDO
await memory.save_raw("el usuario resolvió un bug de async")
```

### 6. Permisos en el punto de acción

```python
async def run_script(path: str) -> None:
    await permission_gate.check(Action.RUN_SCRIPT, path)  # primero siempre
    await subprocess_runner.run(["bash", path])
```

### 7. Iniciativa contextual apagada en Fase 1

No implementar ningún sistema de intervención proactiva en Fase 1. Jules solo responde cuando el usuario habla. La iniciativa contextual es Fase 2 y es opt-in.

### 8. El contexto recuperado siempre es limitado

```python
# Correcto
episodes = await memory.retrieve(query, context, limit=5)

# PROHIBIDO
episodes = await memory.retrieve_all()
```

Más contexto no implica mejor respuesta.

El retrieval excesivo:
- aumenta latencia
- degrada relevancia
- incrementa costo de tokens
- introduce ruido semántico

### 9. Observabilidad sin exposición sensible

```python
# Correcto
logger.info("Router selected model", extra={"provider": provider.name, "model": model})

# PROHIBIDO
logger.info("Prompt completo: %s", prompt)
```

Jules debe poder explicar qué ocurrió sin exponer lo que el usuario escribió completo.

Logs útiles. No vigilancia interna.

---

## MIGRACIONES

```bash
# Crear migración tras cambiar modelos SQLAlchemy
alembic revision --autogenerate -m "descripcion_del_cambio"

# Aplicar todas las migraciones pendientes
alembic upgrade head

# Ver estado actual
alembic current

# Revertir una migración
alembic downgrade -1
```

**Reglas absolutas:**
- Nunca editar archivos en `alembic/versions/` manualmente
- Nunca usar `Base.metadata.create_all()` fuera de tests
- Todo cambio de esquema tiene su migración antes del commit

---

## SISTEMA DE EVENTOS — FASE 1 ÚNICAMENTE

```python
class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    PROJECT_OPENED  = "project_opened"
    CODING_DETECTED = "coding_detected"
    IDLE_DETECTED   = "idle_detected"
    SESSION_ENDED   = "session_ended"

# NO IMPLEMENTAR HASTA FASE 2
# focus_started, focus_broken, music_changed, error_repeated

# NO IMPLEMENTAR HASTA FASE 3 — requieren calibración con datos reales
# frustration_detected, burnout_signal, productivity_anomaly
```

Los eventos cognitivos implementados sin datos reales generan falsos positivos que degradan la experiencia de forma permanente y difícil de revertir.


---

## OBSERVABILIDAD OBLIGATORIA

Cada ejecución debe dejar una traza mínima suficiente para depurar.

### Log mínimo por respuesta

- timestamp
- provider usado
- modelo usado
- task_type
- duración total
- fallback usado o no
- cantidad de episodios recuperados
- persistencia programada o descartada

### Reglas

- No loggear prompts completos por defecto
- No loggear respuestas completas por defecto
- No loggear secrets, ni siquiera sanitizados parcialmente
- El modo debug solo aumenta visibilidad, no cambia comportamiento
- Los errores inesperados siempre conservan traceback

### Comando obligatorio

```bash
jules debug last
```

Este comando existe para revisar la última ejecución sin buscar manualmente en logs.

Si `jules debug last` no puede explicar qué provider respondió, qué modelo se usó y si hubo fallback, la observabilidad no está terminada.

---

## TESTS REQUERIDOS EN FASE 1

### Sanitizador (críticos — Fase 1 no está done sin estos)

```python
# tests/unit/test_sanitizer.py
def test_detects_openai_key():
    result = Sanitizer.check("sk-abc123xyz789..." * 2)
    assert not result.is_safe

def test_detects_export_statement():
    result = Sanitizer.check("export OPENAI_API_KEY=sk-xxx")
    assert not result.is_safe

def test_detects_bearer_token():
    result = Sanitizer.check("Authorization: Bearer ghp_abc123")
    assert not result.is_safe

def test_allows_normal_code():
    result = Sanitizer.check("def calculate_sum(a, b): return a + b")
    assert result.is_safe

def test_allows_normal_commands():
    result = Sanitizer.check("git commit -m 'fix async bug'")
    assert result.is_safe
```

### Memoria

```python
# tests/unit/test_memory_flow.py
async def test_episode_persists_across_sessions():
    # crear episodio, cerrar session, abrir nueva, recuperar

async def test_scoring_uses_ollama_not_external():
    # mock de providers externos — verificar que scoring no los llama

async def test_retrieval_by_relevance_not_recency():
    # insertar episodios viejos relevantes y nuevos irrelevantes
    # verificar que el relevante aparece primero
```

### Router

```python
# tests/unit/test_router.py
async def test_identity_task_always_uses_ollama():
    provider, model = await route(TaskType.IDENTITY)
    assert provider.name == "ollama"

async def test_fallback_on_provider_failure():
    # mock Antigravity para que falle
    # verificar que responde desde Ollama
```

### Coherencia de personalidad (integration)

```python
# tests/integration/test_provider_coherence.py
REFERENCE_PROMPTS = [
    "¿Cómo estás?",
    "Explícame qué eres",
    "Dame tu opinión sobre este código",
    "¿Qué recuerdas de nuestra última sesión?",
    "¿Eres mejor que ChatGPT?",
]

async def test_antigravity_maintains_jules_identity():
    for prompt in REFERENCE_PROMPTS:
        response = await antigravity.ask(prompt, mock_context, model)
        assert not contains_cringe(response)
        assert not is_sycophantic(response)
        assert is_direct(response)
```

---

## AÑADIR UN PROVIDER NUEVO

1. Crear `jules/providers/nombre.py` implementando `Provider`
2. Incluir `health_check()` — el router lo usa para fallback automático
3. Definir modelos disponibles y sus tiers
4. Añadir modelos a `config.toml` en el tier correcto
5. Añadir preset en `~/.jules/personality/nombre.md`
6. Registrar en `router.py`
7. Tests de coherencia de personalidad en `tests/integration/`
8. Probar manualmente el modo no-interactivo antes de integrar

Un provider sin test de coherencia no se activa en producción.

---

## LO QUE NO HACER

| Prohibido | Por qué |
|---|---|
| Scoring con modelo externo | Siempre Llama local — sin cuota |
| Post-procesamiento síncrono antes de responder | Destruye la latencia en terminal |
| Input a memoria sin sanitizar | Secrets llegan a la DB silenciosamente |
| Llamar provider directamente sin router | Rompe quota-aware y provider-agnostic |
| Lógica de decisión dentro de un provider | Los providers son solo traducción de I/O |
| Guardar strings crudos como memoria | La unidad es `Episode` siempre |
| Cambiar DB sin migración Alembic | Rompe durabilidad |
| Implementar iniciativa contextual en Fase 1 | No hay datos para calibrar |
| Implementar eventos cognitivos en Fase 1 | Garantiza falsos positivos |
| Hardcodear nombres de modelos fuera de config.toml | Nada configurable debe estar en código |
| Asumir que los nombres de modelos en los docs son exactos | Verificar siempre con el CLI antes de configurar |
| Integrar scoring sin calibrar el prompt de Llama primero | Sin calibración, el threshold es arbitrario |
| Bloquear el event loop con I/O síncrono | Async en todo I/O |
| Silenciar excepciones con `except Exception: pass` | Siempre manejar explícitamente |
| Interpretar silencio del usuario como bloqueo | Jules no interrumpe sin señal objetiva |

---

## CHECKLIST ANTES DE COMMIT

- [ ] Type hints completos — sin `Any` sin comentario justificado
- [ ] Tests para el flujo modificado
- [ ] Si toca DB: migración Alembic creada y aplicada
- [ ] Si toca providers: test de coherencia de personalidad
- [ ] Si toca permisos: `PermissionGate.check()` está en el punto de acción
- [ ] El sanitizador está en el primer paso del flujo modificado
- [ ] La respuesta al usuario no espera al post-procesamiento
- [ ] El scoring corre en Llama local, no en provider externo
- [ ] `memory_schema_version` está presente en cada episodio persistido
- [ ] `jules debug last` explica la última ejecución
- [ ] Sin modelos hardcodeados — todo en `config.toml`
- [ ] El router respeta tiers — no escala a high_cost sin justificación
- [ ] JULES ≠ EL MODELO — identidad y modelo completamente separados

---

## RECURSOS

- Spec completo del proyecto: `JULES.md`
- Configuración del usuario: `~/.jules/config.toml`
- Personalidad canónica: `~/.jules/personality/master.md`
- Historial de migraciones: `alembic/versions/`
- Docs Antigravity CLI: verificar con `antigravity --help`
- Docs OpenCode CLI: verificar con `opencode --help`

> **Nota sobre nombres de modelos:** los nombres de modelos en JULES.md, AGENT.md y ROADMAP.md son ilustrativos del esquema de tiers. Los strings exactos pueden cambiar. La fuente de verdad es siempre `config.toml`. Verificar con `antigravity --help` y `opencode --help` antes de configurar cualquier modelo.
