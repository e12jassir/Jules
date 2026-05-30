# JULES
## Capa Cognitiva Persistente para el Sistema Operativo

> **Versión:** 1.4 — Canónica
> **Estado:** Fase 1 en progreso — Módulos 0–7 completados y validados (103 tests). Módulos 8, 9, 10 y 11 pendientes.
> **Principio rector:** Construir lo mínimo que funcione, no lo máximo que se pueda imaginar.

---

## ENTORNO OBJETIVO

Jules se desarrolla y opera en el siguiente entorno de referencia:

| Componente | Valor |
|---|---|
| Distribución | EndeavourOS (Arch-based, rolling release) |
| Escritorio | KDE Plasma 6 |
| Servidor de display | Wayland (KWin como compositor) |
| Shell | Verificar antes del Módulo 8: `echo $SHELL` |
| Python | Virtualenv dedicado — nunca el Python del sistema |
| Gestor de paquetes | pacman + AUR (yay / paru) |

Toda decisión de arquitectura que toque el sistema operativo, ventanas, shell o servicios systemd debe validarse contra este entorno antes de considerarse done.

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

10. **ENTORNO-AWARE** — Jules conoce el entorno en el que vive. Las integraciones de sistema se diseñan para KDE Plasma + Wayland desde el inicio, no como adaptación posterior.

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

La verificación de coherencia en post-procesamiento async (`personality/coherence.py`) es **Fase 2**. En Fase 1, la consistencia se garantiza con `master.md` bien escrito, los presets por provider, y los tests de integración.

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
       ├─ Antigravity CLI       (Google + Claude + GPT)
       └─ OpenCode CLI          (GPT / Codex / Deepseek / Llama)
  ↓
Respuesta al usuario  ←─── INMEDIATA, sin bloqueo
  ↓ (en background, async)
Post-Procesamiento
  ├─ extracción de episodios candidatos
  └─ validación de scoring (ver: Scoring Defensivo)
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
| Aislamiento | virtualenv dedicado | Rolling release — nunca depender del Python del sistema |
| CLI | Click + asyncio | Fase 1: CLI pura, sin servidor HTTP |
| Backend | FastAPI | Fase 2+: solo si el dashboard Tauri lo requiere |
| DB relacional | SQLite → PostgreSQL | Local-first; migrar solo cuando escale |
| Migraciones | Alembic | Obligatorio desde el día uno |
| DB vectorial | LanceDB | Embeddings episódicos, búsqueda semántica |
| Inferencia local | Ollama | Fallback offline, identidad local |
| Modelo local | Llama 3.2 1B | Identidad, routing, scoring sin cuota |
| Provider externo 1 | Antigravity CLI | Google + Claude + GPT via subprocess |
| Provider externo 2 | OpenCode CLI | GPT / Codex / Deepseek / Llama via subprocess |

### Nota crítica: LanceDB en EndeavourOS

LanceDB no está en los repositorios oficiales de Arch. Se instala vía pip y compila dependencias de Rust localmente. Requisitos:

- `base-devel` instalado
- Rust actualizado (`rustup update`)
- Todo dentro del virtualenv de Jules — nunca en el Python del sistema

En rolling release, una actualización de sistema puede romper dependencias compiladas sin aviso. Si LanceDB falla después de una actualización, reconstruir el virtualenv antes de asumir que el problema es del código.

### Nota crítica: virtualenv es obligatorio

```bash
# Al iniciar el proyecto — una sola vez
python -m venv .venv
source .venv/bin/activate

# En cada sesión de desarrollo
source .venv/bin/activate
```

Jules nunca corre fuera de su virtualenv. Nunca.

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

#### Nota crítica: Ollama y systemd en EndeavourOS

Ollama instalado vía AUR crea `ollama.service`, que corre como usuario del sistema `ollama`, no como tu usuario. Los modelos descargados con `ollama pull` bajo tu usuario pueden no ser visibles para el servicio del sistema, y viceversa.

Verificar antes de dar el Módulo 3 por done:

```bash
# Ver bajo qué usuario corre el servicio
systemctl show ollama.service | grep User

# Si corre como usuario del sistema, verificar que los modelos sean visibles
sudo -u ollama ollama list

# Alternativa: correr Ollama como servicio de usuario
systemctl --user enable --now ollama
```

La verificación de este punto es criterio de done del Módulo 3, no de Fase 1.5.

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

**Advertencia:** CLI closed-source. Puede cambiar interfaz sin aviso. Probar flags de modo no-interactivo manualmente antes de escribir el provider. Tener un test de integración corriendo en cada sesión de desarrollo.

### OpenCode CLI — GPT / Codex / Deepseek / Llama

Invocación: `subprocess → opencode run --model provider/model "prompt"`
Modo no-interactivo nativo. Ideal para coding con contexto de archivos y repos.

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

**Advertencia:** OpenCode puede colgar esperando confirmaciones interactivas cuando se invoca como subprocess. Configurar permisos en modo automático antes de integrar. Verificar con `opencode --help` que el modo no-interactivo esté disponible.

> **Nota sobre nombres de modelos:** los nombres en estas tablas son ilustrativos del esquema de tiers. Los strings exactos que acepta cada CLI pueden diferir. La fuente de verdad siempre es `config.toml`. Verificar con `antigravity --help` y `opencode --help` antes de configurar.

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

> El patrón genérico `[A-Za-z0-9]{20,}` fue deliberadamente excluido. Genera falsos positivos sobre código legítimo (hashes, UUIDs, base64, nombres de función). Los patrones anteriores son suficientemente específicos.

### Reglas de sanitización

- Si el input contiene un patrón sensible → **descartar completamente**, nunca al scoring
- El sanitizador corre **dos veces**: sobre el input antes de procesar, y sobre los episodios candidatos antes de persistir
- Los descartes se loggean (sin el contenido sensible) para auditoría
- `jules logs --sanitized` muestra cuántos inputs fueron descartados y por categoría, sin el contenido
- En modo `strict_mode = true`: descartar ante la duda. Nunca intentar limpiar parcialmente.

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
    shell: str                   # fish / zsh / bash — poblado al arranque
```

El campo `model_used` habilita el diff cognitivo de Fase 3.
El campo `memory_schema_version` permite migraciones sin romper compatibilidad.
El campo `shell` en `SessionContext` documenta el entorno de ejecución para depuración futura.

---

## VERSIONADO DE MEMORIA

Cada `Episode` persistido incluye `memory_schema_version`. Objetivos:

- permitir migraciones futuras sin perder episodios viejos
- facilitar exportación e importación entre versiones

**Regla:** un episodio incompatible nunca rompe el arranque de Jules. Jules puede leerlo, migrarlo si es seguro, o ignorarlo de forma explícita.

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
- **Summarización** — compresión periódica de episodios similares antiguos
- **Pruning** — eliminación de memorias contradichas u obsoletas
- **Decay** — memorias sin acceso reducen su peso (10% por cada 30 días, mínimo 0.1)
- **Retrieval contextual** — recuperación por similitud semántica, no cronología

### Scoring defensivo

Llama 3.2 1B es un modelo pequeño. Puede devolver scores incoherentes (siempre 0.0, siempre 1.0, o constantes fuera de rango) especialmente con inputs técnicos que no se parecen a los ejemplos de calibración.

Jules detecta esto y actúa:

```python
def is_scoring_healthy(scores: list[float]) -> bool:
    """
    Detecta si el scoring está degenerado.
    Un scorer sano produce varianza real entre episodios distintos.
    """
    if len(scores) < 3:
        return True  # muestra insuficiente para diagnosticar
    variance = statistics.variance(scores)
    return variance > 0.01  # threshold empírico — ajustar con datos reales

# En el motor de persistencia:
if not is_scoring_healthy(recent_scores):
    logger.warning("scoring_degenerate", variance=variance, recent=recent_scores)
    # Entrar en modo de persistencia conservadora:
    # guardar todo lo que supere friction_score > 0.5 o tenga tags de proyecto activo
    # No descartar silenciosamente, no guardar todo indiscriminadamente
```

`jules doctor` y `jules debug last` reportan si el scoring está en modo degradado.

**Calibración obligatoria antes de integrar al flujo:** probar el prompt de scoring contra 10–15 episodios de ejemplo con Llama corriendo en Ollama. El threshold 0.3 es punto de partida, no valor definitivo. Ajustar con datos reales.

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
ScoringHealthMonitor.record(score)
  ↓
if score >= 0.3 AND scoring_healthy:
    EpisodicMemory.persist(episode)     # LanceDB
    PersistentMemory.upsert_facts(...)  # SQLite si hay hechos estables
elif not scoring_healthy:
    persistencia conservadora (ver: Scoring Defensivo)
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

Jules no solo observa *qué haces* — infiere *para qué lo haces*.

| Acción | Contexto previo | Intención inferida |
|---|---|---|
| Abrir archivo | Error en terminal | Debugging |
| Abrir archivo | Leer docs | Aprendizaje / exploración |
| Abrir archivo | Nada previo | Refactoring o revisión |

Señales usadas: actividad terminal previa, directorio activo, historial de sesión, hora del día, patrón habitual del usuario.

El usuario nunca declara su intención — Jules la infiere.

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

### Nota crítica: shell hooks en EndeavourOS

Los hooks de shell dependen del shell activo. **Verificar antes de implementar:**

```bash
echo $SHELL
# /usr/bin/fish  → usar fish_preexec / fish_postexec / fish_prompt
# /usr/bin/zsh   → usar precmd / preexec en .zshrc
# /usr/bin/bash  → usar PROMPT_COMMAND / trap DEBUG en .bashrc
```

Fish no es compatible con los hooks de bash/zsh. Si el shell activo es fish, los hooks deben implementarse en `~/.config/fish/conf.d/jules.fish` usando las funciones de evento de fish. No intentar adaptar hooks de bash a fish.

### Nota crítica: inotify en EndeavourOS

Los filesystem watchers usan inotify. El límite por defecto puede ser insuficiente en proyectos grandes:

```bash
# Ver límite actual
cat /proc/sys/fs/inotify/max_user_watches

# Si está por debajo de 65536, aumentar
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf
sudo sysctl -p /etc/sysctl.d/jules.conf
```

Jules verifica este límite al arranque (`jules doctor`) y advierte si está cerca del techo. Un watcher que se agota silenciosamente es difícil de depurar.

### Fase 2

```
focus_started, focus_broken, music_changed, error_repeated
```

### Fase 3 — solo con datos reales calibrados

```
frustration_detected, productivity_anomaly, burnout_signal
```

Los eventos cognitivos de Fase 3 requieren semanas de datos reales del usuario para calibrarse. Implementarlos antes genera falsos positivos permanentes.

---

## INICIATIVA CONTEXTUAL — APAGADA POR DEFECTO

```toml
[initiative]
enabled = false  # apagada por defecto
```

Cuando el usuario la activa:

| Situación | Acción de Jules |
|---|---|
| Mismo archivo >2h sin avance visible | Una sola pregunta |
| Proyecto no tocado >2 semanas, recién abierto | Ofrece resumen de estado |
| Error idéntico a uno ya resuelto | Sugiere solución anterior |
| Sesión larga sin break | Sugiere pausa, una sola vez |

**Regla de oro:** Jules no interrumpe dos veces por la misma razón en una sesión.

Jules nunca interpreta silencio, descanso o pensamiento como bloqueo. Solo actúa sobre señales objetivas (tiempo en archivo, error repetido), nunca sobre inactividad sola.

La iniciativa contextual es Fase 2. En Fase 1 no existe.

---

## COMANDO `jules doctor`

Antes de cualquier sesión de trabajo, `jules doctor` verifica que el entorno esté sano. Es el primer comando que corre Jules al arrancar en modo diagnóstico.

```
jules doctor
```

Verifica y reporta:

| Check | Qué verifica |
|---|---|
| Ollama | Servicio activo, modelos descargados, usuario correcto |
| Antigravity CLI | Disponible en PATH, responde a `--help` |
| OpenCode CLI | Disponible en PATH, responde a `--help` |
| LanceDB | Directorio de vectores accesible, no corrupto |
| SQLite | `jules.db` accesible, migraciones Alembic al día |
| inotify | Límite de watches verificado contra threshold |
| Virtualenv | Jules corre dentro de su entorno aislado |
| Permisos `~/.jules/` | Escritura disponible en todos los subdirectorios |
| Scoring health | Último estado conocido del importance scorer |
| Shell detectado | fish / zsh / bash — para validar hooks |

Output example:

```
jules doctor
──────────────────────────────────────
✓ Ollama          activo, llama3.2:1b disponible (usuario: esteban)
✓ Antigravity     disponible en PATH
✓ OpenCode        disponible en PATH
✓ LanceDB         vectores OK
✓ SQLite          migraciones al día (rev: a3f9c1)
✗ inotify         8192 watches (recomendado: ≥65536) — ver docs
✓ Virtualenv      activo (.venv)
✓ ~/.jules/       permisos OK
⚠ Scoring         sin datos suficientes para evaluar salud
✓ Shell           fish detectado — hooks en conf.d/jules.fish
──────────────────────────────────────
1 problema detectado. Jules opera en modo parcialmente degradado.
```

`jules doctor` nunca bloquea el arranque. Reporta, advierte, y deja que el usuario decida.

---

## DIFF COGNITIVO

Jules puede responder preguntas sobre la evolución del usuario en el tiempo:

```
"Jules, ¿con qué modelo resuelvo mejor bugs de async?"
"Jules, ¿cómo ha cambiado mi forma de debuggear en 6 meses?"
"Jules, ¿en qué áreas he mejorado este trimestre?"
"Jules, ¿qué tipos de errores ya no cometo?"
```

**Prioridad:** Fase 3. Requiere mínimo 3 meses de episodios acumulados para ser útil.

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

**Prioridad:** Fase 3.

---

## ENTORNO ADAPTATIVO (Fase 2)

Jules puede controlar el entorno Linux:
- abrir workspaces y organizar ventanas por proyecto
- preparar entornos de desarrollo automáticamente
- controlar música según estado de trabajo
- manejar sesiones tmux / zellij
- automatizar workflows repetitivos

### Herramientas por función — KDE Plasma + Wayland

| Función | Herramienta | Nota |
|---|---|---|
| Gestión de ventanas | `qdbus` / `dbus-send` → KWin | Correcto para KDE Plasma |
| Gestión de ventanas | `wmctrl` | Soporte parcial bajo Wayland — usar con precaución |
| Eventos del desktop | `DBus` | Funciona en Plasma |
| Sesiones tmux/zellij | `subprocess` | Sin restricciones |
| Actividad de archivos | filesystem watchers (inotify) | Ver nota de límites |
| Hooks de shell | fish / zsh / bash | Según shell detectado |
| Comandos y CLIs | `subprocess` | General |

> `hyprctl` es exclusivo de Hyprland y no existe en KDE Plasma. No usar.

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
- Muestra: modelo activo, tier, contexto de sesión, estado de memoria, salud del scoring
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
│   ├── sanitized.log      # log de descartes por sanitizador (sin contenido)
│   └── scoring.log        # log de salud del importance scorer
└── backups/               # snapshots diarios automáticos
```

```
jules/                     # repositorio del proyecto
├── .venv/                 # virtualenv — nunca commitear
├── pyproject.toml
├── alembic.ini
├── alembic/
├── jules/
│   ├── cli/
│   │   └── main.py        # entrypoint Click
│   ├── core/
│   │   ├── router.py
│   │   ├── context.py
│   │   ├── events.py
│   │   └── permissions.py
│   ├── memory/
│   │   ├── models.py
│   │   ├── episodic.py
│   │   ├── persistent.py
│   │   ├── engine.py
│   │   └── scoring.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── ollama.py
│   │   ├── antigravity.py
│   │   └── opencode.py
│   ├── sanitizer/
│   │   └── sanitizer.py
│   ├── personality/
│   │   └── loader.py
│   ├── linux/
│   │   ├── watcher.py     # filesystem watchers + inotify health check
│   │   ├── shell.py       # hooks fish / zsh / bash según shell detectado
│   │   └── doctor.py      # jules doctor — diagnóstico de entorno
│   └── observability/
│       └── logger.py
└── tests/
    ├── unit/
    └── integration/
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
- **Virtualenv versionado** — `requirements.lock` generado en cada sesión de desarrollo estable

---

## OBSERVABILIDAD Y DEBUGGING

Jules no puede depender de intuición para depurarse. Cada decisión importante del sistema debe poder inspeccionarse después.

### Eventos que siempre deben loggearse

| Evento | Información mínima |
|---|---|
| Router selecciona modelo | provider, modelo, task_type |
| Fallback activado | provider original, razón del fallo |
| Persistencia descartada | motivo del descarte |
| Sanitizador bloquea input | categoría detectada |
| Provider timeout | provider, duración |
| Retrieval de memoria | episodios recuperados |
| Scoring degenerado | varianza observada, modo activado |
| inotify cerca del límite | watches actuales vs máximo |
| Error inesperado | traceback completo |

### Reglas de logging

- Nunca loggear prompts completos ni respuestas completas por defecto
- Nunca loggear secrets detectados por el sanitizador
- Logs estructurados en JSON cuando sea posible
- Los logs deben poder desactivarse por categoría
- El modo debug nunca cambia comportamiento del sistema — solo visibilidad

### Comandos de observabilidad

```bash
jules debug last       # última ejecución: provider, modelo, fallback, memoria, scoring
jules logs --sanitized # descartes del sanitizador sin contenido sensible
jules logs --scoring   # historial de salud del importance scorer
jules doctor           # diagnóstico completo del entorno
jules memory           # episodios recientes
jules status           # estado de providers y memoria
```

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
| Startup CLI (Ollama caliente) | <500ms |
| Startup CLI (Ollama frío) | <3s — advertir al usuario |
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

Jules se degrada gradualmente. Nunca colapsa por una sola dependencia.

| Falla | Comportamiento |
|---|---|
| Ollama no disponible | desactivar scoring y modo offline |
| LanceDB corrupto | continuar sin memoria semántica |
| SQLite bloqueado | responder sin persistencia |
| Antigravity no disponible | fallback automático |
| OpenCode no disponible | fallback automático |
| Todos los providers fallan | informar claramente al usuario |
| Scoring degenerado | modo de persistencia conservadora |
| inotify agotado | desactivar watchers, notificar al usuario |

**Regla crítica:** una falla de memoria nunca impide responder al usuario.
**Regla crítica:** una falla de provider nunca corrompe memoria.
**Regla crítica:** el usuario siempre sabe qué falló, qué quedó degradado, y si Jules sigue operativa parcialmente. El modo degradado no es un error silencioso — es un estado explícito.

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
structured_logs        = true
debug_command_enabled  = true
log_prompts            = false
log_responses          = false

[performance]
startup_target_ms              = 500
routing_timeout_ms             = 50
memory_retrieval_timeout_ms    = 150

[doctor]
inotify_min_watches            = 65536   # advertir si está por debajo
scoring_variance_threshold     = 0.01    # mínimo para considerar scoring sano
```

---

## CRITERIOS DE ÉXITO POR FASE

### Fase 1 — Done cuando:
- [ ] Jules responde en terminal con contexto de sesión activa
- [x] La respuesta llega sin latencia perceptible por memoria (persistencia async)
- [x] La memoria persiste entre reinicios (SQLite + LanceDB)
- [x] El sanitizador descarta secrets antes de persistir — verificable con tests
- [x] El router selecciona el modelo correcto según tipo de tarea y tier
- [x] El fallback a Ollama funciona cuando los CLIs externos no responden
- [x] La búsqueda semántica recupera memorias relevantes (no solo las más recientes)
- [x] Llama local hace importance scoring sin consumir cuota externa
- [ ] Ollama corre bajo el usuario correcto y los modelos son visibles — verificado
- [ ] El sistema de permisos rechaza acciones no autorizadas
- [ ] `jules doctor` reporta estado completo del entorno
- [ ] Shell detectado correctamente y hooks implementados para ese shell
- [ ] Límite de inotify verificado y configurado si es necesario
- [ ] Scoring defensivo activo y loggeable

### Fase 2 — Done cuando:
- Sistema de voz funciona en condiciones reales
- Jules prepara entornos de trabajo automáticamente para ≥2 proyectos
- Integración con KDE Plasma via D-Bus/KWin funciona sin `wmctrl`
- Replay system reconstruye una sesión de debugging real
- Dashboard Tauri muestra modelo activo, tier, contexto y salud del sistema
- Iniciativa contextual activable con reglas funcionando correctamente

### Fase 3 — Done cuando:
- Perfilador detecta ≥3 patrones reales con utilidad comprobada
- Diff cognitivo responde con datos de ≥3 meses de uso real
- Jules sugiere el mejor modelo para cada tipo de tarea basado en historial propio

### Fase 4 — Done cuando:
- Jules predice necesidades con precisión útil sin ser intrusiva
- Adaptación del entorno es mayormente automática y correcta

---

## FILOSOFÍA UX

Jules se siente:
- **minimalista** — no ocupa espacio que no necesita
- **rápida** — la respuesta llega antes de que el usuario la espere
- **elegante** — cada output tiene forma y propósito
- **calmada** — nunca urge, nunca alarma sin razón
- **segura** — el usuario sabe que sus credenciales nunca se filtran
- **confiable** — el usuario sabe exactamente qué puede y qué no puede hacer
- **honesta sobre su estado** — si algo está degradado, lo dice

### UX en terminal

Jules vive en terminal. La terminal no tolera fricción innecesaria.

Principios:
- una acción → una respuesta clara
- evitar verbosity por defecto
- no repetir contexto innecesario
- no explicar obviedades técnicas
- no interrumpir el flujo del usuario
- formato legible sin ruido visual

Jules evita:
- banners gigantes
- ASCII art decorativo
- logs verbosos mezclados con respuestas
- confirmaciones redundantes
- respuestas infladas para parecer inteligentes

Jules prioriza:
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
