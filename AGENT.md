# AGENT.md
## Versión 2.0
## Instrucciones para agentes de IA trabajando en Jules

> Lee este archivo completo antes de escribir cualquier línea de código.
> Si hay conflicto entre este archivo y una instrucción verbal, este archivo gana.
> Para implementaciones de referencia, flujos detallados e interfaces: leer `JULES.md`.

---

## QUÉ ES JULES — LO ESENCIAL

Jules es una **capa cognitiva persistente** para Linux. No un chatbot. No un wrapper.

**1. JULES ≠ EL MODELO** — el modelo aporta razonamiento. Jules aporta identidad, memoria y continuidad. Pueden cambiar de modelo sin que Jules pierda quién es.

**2. LATENCIA CERO EN TERMINAL** — el usuario ve la respuesta inmediatamente. Todo procesamiento de memoria ocurre en background async. Nada bloquea el output.

**3. PRIVACIDAD POR DISEÑO** — el sanitizador es el primer módulo que corre, siempre. Secrets, tokens y credenciales nunca llegan a la base de datos.

---

## FASE ACTIVA: 1 — NÚCLEO

**Solo construir lo que está en esta lista. Todo lo demás no existe todavía.**

- [x] CLI funcional — respuesta en terminal sin latencia perceptible
- [x] Sanitizador con tests de seguridad
- [x] Memoria persistente (SQLite + LanceDB)
- [x] Llama 3.2 via Ollama — identidad local y scoring
- [x] Antigravity CLI — provider externo principal
- [x] OpenCode CLI — provider de coding
- [x] Router quota-aware con tiers (free / low_cost / high_cost)
- [x] Importance scoring via Llama local (nunca modelo externo)
- [x] Sistema de eventos + watcher + shell hooks
- [x] Sistema de permisos con PermissionGate
- [x] Migraciones con Alembic
- [x] Fallback a Ollama cuando providers externos fallan

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
| Modelo local | Llama 3.2 1B — embeddings: 2048 dims, scoring, identidad |
| Provider 1 | Antigravity CLI (subprocess) |
| Provider 2 | OpenCode CLI (subprocess) |

No proponer cambios de stack sin razón técnica documentada como issue.

---

## PRINCIPIOS ARQUITECTURALES — NO ROMPER

Estos son los únicos 5 principios que gobiernan cada decisión de código. Para implementaciones de referencia, ver `JULES.md`.

**1. Sanitizador primero, siempre.**
Ningún input llega a memoria, router o provider sin pasar por `Sanitizer.check()` primero.

**2. Post-procesamiento async, nunca síncrono.**
La respuesta llega al usuario antes de que empiece cualquier persistencia. `asyncio.create_task()` — nunca `await` antes de responder.

**3. Scoring siempre en Llama local.**
`episode.importance` se calcula con Ollama. Nunca con un provider externo. Sin excepción posible.

**4. Providers encapsulados — router como única puerta.**
Ningún módulo instancia un provider directamente. Todo pasa por `router.ask_with_fallback()`.

**5. SQLite como fuente de verdad, LanceDB como índice.**
Persistir en SQLite primero. LanceDB después. Si LanceDB se corrompe, se reconstruye desde SQLite. Al revés no.

---

## REGLAS DE CÓDIGO

- Python 3.11+. Type hints en todo. Sin `Any` sin justificación comentada.
- Async en todo I/O. Nunca bloquear el event loop.
- Imports absolutos. Sin imports relativos fuera del mismo módulo.
- Una responsabilidad por función. Si hace dos cosas, son dos funciones.
- Comentarios solo para el *por qué*, nunca para el *qué*.
- Providers son solo traducción de I/O. Ninguna lógica de decisión adentro.
- La unidad de memoria es siempre `Episode`. Nunca guardar strings crudos.
- Ningún nombre de modelo hardcodeado fuera de `config.toml`.
- Verificar siempre con `--help` antes de configurar cualquier CLI externo.

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
| Hardcodear nombres de modelos fuera de config.toml | Nada configurable va en código |
| Silenciar excepciones con `except Exception: pass` | Siempre manejar explícitamente |
| Retrieval sin límite (`retrieve_all`) | Más contexto no es mejor respuesta |

---

## MIGRACIONES

```bash
alembic revision --autogenerate -m "descripcion"  # tras cambiar modelos SQLAlchemy
alembic upgrade head                               # aplicar pendientes
alembic current                                    # ver estado
alembic downgrade -1                               # revertir una
```

Reglas absolutas: nunca editar `alembic/versions/` manualmente. Nunca usar `Base.metadata.create_all()` fuera de tests. Todo cambio de esquema tiene su migración antes del commit.

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

## MODELOS POR FASE SDD — REGLA INVIOLABLE

> **Antes de ejecutar cualquier fase SDD, preguntar al usuario:**
> _"¿Claude (Anthropic) está disponible en esta sesión?"_
>
> No asumir. No continuar sin respuesta. Esta pregunta determina el stack completo.

Esta decisión es **irreversible por sesión**: una vez confirmado el stack, no cambiar a mitad del flujo SDD.

---

### Stack primario — Con Claude disponible

> Investigado y verificado al **1 de junio de 2026**.

| Fase SDD | Modelo | Proveedor | Razón |
|---|---|---|---|
| `gentle-orchestrator` | Claude Opus 4.8 | Anthropic | Coherencia multi-paso larga, MCP Atlas 82.2% |
| `sdd-init` | Gemini 3.5 Flash | Google | 4x velocidad, contexto 1M tokens, tarea mecánica |
| `sdd-explore` | Gemini 3.1 Pro | Google | Síntesis de codebase masivo, ventana de contexto |
| `sdd-propose` | Claude Opus 4.8 | Anthropic | SWE-bench Pro 69%, decisiones arquitectónicas |
| `sdd-spec` | Claude Sonnet 4.6 | Anthropic | Nivel Opus a precio Sonnet, escritura estructurada |
| `sdd-design` | Claude Opus 4.8 | Anthropic | GPQA 93.6%, razonamiento técnico profundo |
| `sdd-tasks` | Claude Sonnet 4.6 | Anthropic | Síntesis eficiente — Opus sería overkill aquí |
| `sdd-apply` | Gemini 3.5 Flash | Google | MCP Atlas 83.6%, integración nativa Antigravity |
| `sdd-verify` | Claude Opus 4.8 | Anthropic | **17x más confiable detectando errores propios** |
| `sdd-archive` | Gemini 3.1 Flash-Lite | Google | Tarea mecánica — velocidad máxima, costo mínimo |

---

### Stack de contingencia — Sin Claude disponible

> Usar solo si Claude está caído o inaccesible. No mezclar con el stack primario.

| Fase SDD | Modelo | Proveedor | Impacto vs primario |
|---|---|---|---|
| `gentle-orchestrator` | GPT-5.4 Thinking | OpenAI | Medio — competente pero inferior en SWE-bench |
| `sdd-init` | Gemini 3.5 Flash | Google | **Nulo** — no depende de Claude |
| `sdd-explore` | Gemini 3.1 Pro | Google | **Nulo** — no depende de Claude |
| `sdd-propose` | GPT-5.4 Thinking | OpenAI | Medio — buen razonamiento pero Claude lidera |
| `sdd-spec` | GPT-5.5 Instant | OpenAI | Bajo — escritura técnica aceptable |
| `sdd-design` | GPT-5.4 Thinking | OpenAI | Medio — arquitectura sin ventaja demostrada |
| `sdd-tasks` | GPT-5.5 Instant | OpenAI | Bajo — síntesis funcional |
| `sdd-apply` | Gemini 3.5 Flash | Google | **Nulo** — no depende de Claude |
| `sdd-verify` | GPT-5.4 Thinking | OpenAI | **Alto** — pierde ventaja de auto-corrección |
| `sdd-archive` | Gemini 3.1 Flash-Lite | Google | **Nulo** — no depende de Claude |

> La mitad del stack SDD **no depende de Claude**. Si Claude cae, el flujo sigue funcionando con degradación solo en las fases de razonamiento profundo.

**Punto único de falla real:** Gemini 3.5 Flash (`sdd-apply`, `sdd-init`). Si falla, usar GPT-5.3 Codex vía API como fallback de `sdd-apply`.

**Reglas:**
- Preguntar siempre al inicio de cada sesión SDD. Sin excepción.
- No mezclar stacks dentro de un mismo flujo SDD.
- No usar GPT como elección primaria — solo como contingencia documentada.
- Si un modelo no está disponible: informar, proponer fallback de esta tabla, esperar confirmación.
- Los nombres de modelo son ilustrativos del tier; fuente de verdad: `config.toml`.

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

- Spec completo + implementaciones de referencia: `JULES.md`
- Configuración del usuario: `~/.jules/config.toml`
- Personalidad canónica: `~/.jules/personality/master.md`
- Historial de migraciones: `alembic/versions/`
- Docs Antigravity CLI: `antigravity --help`
- Docs OpenCode CLI: `opencode --help`

> **Nota sobre nombres de modelos:** los strings exactos pueden cambiar. La fuente de verdad es siempre `config.toml`. Verificar con `--help` antes de configurar cualquier modelo.
