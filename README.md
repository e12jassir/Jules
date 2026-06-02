<div align="center">

# Jules

### A Persistent Cognitive Layer for Linux

*Not another chatbot. Not another AI wrapper.*
*The only system that knows how you think.*

<br/>

![Phase](https://img.shields.io/badge/Phase_1-In_Progress-blue?style=flat-square)
![Tests](https://img.shields.io/badge/Tests-120_passing-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux_(EndeavourOS)-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)

</div>

---

## What is Jules?

Jules is a persistent AI assistant that lives inside the Linux operating system — not in a browser tab, not in an Electron app, not as a cloud dependency. In the terminal, where real work happens.

Jules **remembers between sessions**. It builds a semantic memory of your work — problems you've solved, patterns in how you think, bugs you keep hitting — and uses that memory to give you more relevant, more personal assistance over time.

Jules **knows its environment**. It detects your shell, watches the filesystem, integrates with KDE Plasma via D-Bus, and understands the difference between you debugging and you reading docs.

Jules **routes intelligently**. It uses three providers — a local Ollama instance, Antigravity CLI (Google + Claude + GPT), and OpenCode CLI (GPT/Codex/Deepseek) — and selects the right model for each task type without burning premium quota on tasks that don't need it.

Jules **protects your data**. Every input passes through a sanitizer before touching memory. Secrets, tokens, and credentials never reach the database. Privacy is not a feature — it's the foundation.

---

## Core Principles

**Local-first.** Jules works offline. Ollama runs locally. Memory lives on your machine. No cloud dependency for the core loop.

**Zero terminal latency.** Your response arrives before persistence completes. The entire post-processing pipeline — scoring, sanitizing, embedding, storing — runs in `asyncio.create_task()` after you've already seen the answer. You never wait for memory.

**Graceful degradation.** If LanceDB is corrupted, Jules continues without semantic memory. If SQLite is locked, Jules responds without persistence. If all external providers fail, Ollama answers. The user always knows what's degraded — never a silent error.

**Initiative off by default.** Jules does not interrupt. It does not interpret silence as a signal. When the user enables contextual initiative, it has strict rules: one intervention per reason per session. Never twice.

**Privacy by design.** The sanitizer is always the first module to run. Always. Before scoring, before memory, before anything else.

**Provider-agnostic.** Jules does not depend on any specific model or provider. The router is the intelligence. The models are interchangeable.

---

## Architecture

```
User input
  ↓
Sanitizer  ←── ALWAYS FIRST — secrets, tokens, credentials
  ↓
Context Detector
  ├── What is the user doing?
  └── Why are they doing it? (inferred, never declared)
  ↓
Context Engine + Memory
  ├── RAM          — active session context
  ├── LanceDB      — episodic memory with embeddings (semantic retrieval)
  └── SQLite       — persistent facts, preferences, active projects
  ↓
Quota-Aware Router
  ├── Classify task type
  ├── Select optimal tier
  └── Invoke provider
       ├── Ollama / Llama 3.2   — local, offline, identity, scoring
       ├── Antigravity CLI      — Google Gemini, Claude, GPT
       └── OpenCode CLI         — GPT, Codex, Deepseek, Llama
  ↓
Response to user  ←── IMMEDIATE — no blocking
  ↓  (background, async)
Post-Processing
  ├── Sanitizer (second pass on episode candidates)
  ├── Importance scoring via Llama local (never external quota)
  ├── ScoringHealthMonitor — detects degenerate scoring
  └── Persist or discard
```

The critical latency rule: the response line does not wait for anything below it. The user never waits for memory.

---

## Memory

Jules does not store logs. It stores **episodes**.

An episode is the minimal unit of meaningful memory:

```python
@dataclass
class Episode:
    id: str
    timestamp: datetime
    context: SessionContext      # project, directory, shell, inferred intent
    problem: str | None          # what the user was solving
    process: str | None          # how they approached it
    solution: str | None         # what worked
    friction_score: float        # 0.0 = smooth, 1.0 = high friction
    importance: float            # 0.0–1.0, scored by Llama locally
    model_used: str              # which model responded
    provider_used: str           # which provider was used
    memory_schema_version: str   # for future migrations
```

Memory retrieval is semantic — by relevance, not recency. When you ask Jules something, it searches for episodes that are *contextually similar*, not just the most recent ones.

Importance scoring uses Llama 3.2 1B running locally. External quota is never spent on memory decisions.

---

## Routing

Jules routes each task to the optimal model and tier:

| Task Type | Provider | Tier |
|---|---|---|
| `IDENTITY` / `MEMORY_SCORING` / `OFFLINE` | Ollama | free — always |
| `QUICK` | Antigravity — Gemini Flash | low_cost |
| `REASONING` | Antigravity — Gemini Flash High / Pro | low_cost / high_cost |
| `CODING` | OpenCode — GPT / Codex / Deepseek | low_cost |
| `CODING_HEAVY` | OpenCode — GPT high_cost | high_cost |
| `ANALYSIS` | Antigravity — Gemini Pro / Claude | high_cost |

No model name is hardcoded in the source code. Everything lives in `config.toml`. The router reads from config — change a model string there, and the entire routing changes instantly.

Fallback chain: `primary → secondary_same_tier → ollama`. Jules never fails silently.

---

## Providers

Jules uses three providers. External ones are invoked as subprocesses — Jules never handles credentials. Each CLI manages its own authentication.

### Ollama — Local / Offline
- Runs at `http://localhost:11434`
- Used exclusively for: identity, memory scoring, offline mode
- Never replaced by external providers for these tasks

### Antigravity CLI — Google + Claude + GPT
- Successor to Gemini CLI, announced at Google I/O 2026
- Encapsulated entirely in `providers/antigravity.py`
- Models: Gemini 3.5 Flash, Gemini 3.1 Pro, Claude Sonnet 4.6, Claude Opus 4.8

### OpenCode CLI — GPT / Codex / Deepseek
- Native non-interactive mode, ideal for code-context tasks
- Models: GPT-4.5, Codex, Deepseek V4 Flash, Qwen 3.6, GPT-5.x

---

## `jules doctor`

Jules verifies its own environment at startup:

```
jules doctor
──────────────────────────────────────────────
✓ Ollama          active · llama3.2:1b available (user: esteban)
✓ Antigravity     available in PATH
✓ OpenCode        available in PATH
✓ LanceDB         vectors OK
✓ SQLite          migrations up to date (rev: a3f9c1)
✗ inotify         8192 watches — recommended ≥65536 — see docs
✓ Virtualenv      active (.venv)
✓ ~/.jules/       write permissions OK
⚠ Scoring         insufficient data to evaluate health
✓ Shell           fish detected — hooks at conf.d/jules.fish
──────────────────────────────────────────────
1 problem detected. Jules is operating in partial mode.
```

Doctor never blocks startup. It reports, warns, and lets the user decide.

---

## Commands

```bash
# Direct query — main flow
jules "how does Python's GIL interact with asyncio?"

# Model override
jules --model claude-opus-4-8 "review this architecture"

# Skip memory for this session
jules --no-memory "explain asyncio from scratch"

# Recent episodes
jules memory

# Provider and memory status
jules status

# Full environment diagnostic
jules doctor

# Last execution detailed breakdown
jules debug last

# Sanitizer discard log (no sensitive content)
jules logs --sanitized

# Importance scorer health history
jules logs --scoring
```

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | Native async, ML ecosystem |
| Isolation | Dedicated virtualenv | Rolling release safety — never the system Python |
| CLI | Click + asyncio | Phase 1: pure terminal, no HTTP server |
| Relational DB | SQLite → PostgreSQL | Local-first; migrate only when scale demands |
| Migrations | Alembic | Versioned schema from day one |
| Vector DB | LanceDB | Episodic embeddings, semantic retrieval |
| Local inference | Ollama + Llama 3.2 1B | Identity, routing, scoring — no external quota |
| External provider 1 | Antigravity CLI | Google + Claude + GPT via subprocess |
| External provider 2 | OpenCode CLI | GPT / Codex / Deepseek via subprocess |
| Desktop app (Phase 2) | Tauri + SvelteKit | Lightweight overlay, not a replacement for CLI |

---

## Target Environment

Jules is designed for one specific environment, not "any Linux":

| Component | Value |
|---|---|
| OS | EndeavourOS (Arch-based, rolling release) |
| Desktop | KDE Plasma 6 + Wayland |
| Compositor | KWin |
| Shell | Detected at runtime — fish / zsh / bash |
| Python | Dedicated virtualenv — never the system Python |

Every OS-level integration (window management, shell hooks, filesystem watchers, systemd services) is designed for this environment from the start — not retrofitted later.

---

## Installation

> Jules is in active Phase 1 development. No stable release yet. The following is the development setup.

### Prerequisites

```bash
# Ollama with Llama 3.2
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

# Verify inotify limit (EndeavourOS / Arch)
cat /proc/sys/fs/inotify/max_user_watches
# If below 65536:
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf
sudo sysctl -p /etc/sysctl.d/jules.conf

# Antigravity CLI and OpenCode CLI must be installed and available in PATH
```

### Setup

```bash
git clone https://github.com/esteban/jules.git
cd jules

# Virtualenv is mandatory — never use the system Python
python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

alembic upgrade head

jules doctor
```

---

## Build Status

```
Phase 1 — Core
  [x] Module 0   — Project structure + virtualenv
  [x] Module 1   — Sanitizer
  [x] Module 2   — Data models
  [x] Module 3   — Ollama provider
  [x] Module 4   — External providers (Antigravity + OpenCode)
  [x] Module 5   — Quota-aware router
  [x] Module 6   — Memory engine (SQLite + LanceDB + Scoring)
  [x] Module 7   — Context intent detector
  [x] Module 8   — Event system + shell hooks
  [ ] Module 9   — Permission system
  [ ] Module 10  — jules doctor
  [ ] Module 11  — Main CLI
  [ ]            — Phase 1 final review (Opus)

Phase 1.5  — Stabilization    (pending)
Phase 2    — Expansion        (pending)
Phase 3    — Adaptive Intelligence  (pending)
Phase 4    — Autonomy         (pending)
```

**120 tests passing** across completed modules.

---

## Documentation

| Document | Purpose |
|---|---|
| [`JULES.md`](JULES.md) | Canonical system specification — architecture, data models, configuration, design decisions |
| [`ROADMAP.md`](ROADMAP.md) | Build plan — modules, done criteria, SDD phase assignments, model routing per item |
| [`AGENT.md`](AGENT.md) | AI agent behavioral rules — inviolable model assignment matrix for SDD phases |

---

## Configuration

Jules is configured from `~/.jules/config.toml`:

```toml
[memory]
importance_threshold   = 0.3     # episodes below this are discarded
decay_rate_per_30_days = 0.10    # memory weight decays over time
max_episodes_retrieved = 5       # context window per query

[routing]
default_tier = "low_cost"

[initiative]
enabled = false  # off by default — user enables explicitly

[sanitizer]
strict_mode = true   # discard on doubt, never partial-clean

[doctor]
inotify_min_watches        = 65536
scoring_variance_threshold = 0.01
```

Full configuration reference: [`JULES.md → Configuration`](JULES.md).

---

## Contributing

Jules is a personal project in active construction. The core needs to stabilize before external contributions open.

If you find something interesting or have feedback, open an issue.

---

## License

MIT — see [`LICENSE`](LICENSE)

---

<div align="center">

*Jules is not another chatbot.*
*It's the only system that knows how you think,*
*how you solve problems, and how you've changed.*

</div>
