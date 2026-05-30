```
   ██╗██╗   ██╗██╗     ███████╗███████╗
   ██║██║   ██║██║     ██╔════╝██╔════╝
   ██║██║   ██║██║     █████╗  ███████╗
██ ██║██║   ██║██║     ██╔══╝  ╚════██║
╚█████╔╝╚██████╔╝███████╗███████╗███████║
 ╚════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝
```

**Persistent cognitive layer for Linux**

[![Phase](https://img.shields.io/badge/phase-1%20in%20progress-yellow?style=flat-square)](https://github.com/e12jassir/Jules) [![Modules](https://img.shields.io/badge/modules%20done-8%20%2F%2011-blue?style=flat-square)](https://github.com/e12jassir/Jules/blob/main/ROADMAP.md) [![Tests](https://img.shields.io/badge/tests-103%20passing-brightgreen?style=flat-square)](https://github.com/e12jassir/Jules) [![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org/) [![License](https://img.shields.io/badge/license-MIT-gray?style=flat-square)](https://github.com/e12jassir/Jules/blob/main/LICENSE) [![Environment](https://img.shields.io/badge/env-EndeavourOS%20%2B%20KDE%20Plasma-blueviolet?style=flat-square)](https://endeavouros.com/)

---

## What is Jules

Jules is not a chatbot. Not an API wrapper. Not a disposable copilot that resets without knowing who you are.

Jules is a **persistent cognitive layer** that lives inside your Linux OS. It remembers across sessions. It infers your intent without you having to declare it. It knows which model helped you debug that async issue last week. It never leaks your credentials. It never interrupts unless you explicitly enable it.

The core distinction from every other AI assistant: **Jules ≠ the model**. The model provides reasoning. Jules provides continuity, identity, and accumulated context. You can swap models without Jules losing who it is.

```bash
jules "why is this async failing?"
# → responds with active session context
# → retrieves semantically relevant episodes from weeks ago
# → uses the right model for the task type, without burning quota
# → persists the solution in background without making you wait
```

---

## Why it exists

Most AI assistants respond. Jules observes, remembers, and reflects back.

It's the only system that knows how you think, how you solve problems, and how you've changed over time. Not as a log — as a **cognitive mirror**.

---

## Features

### Implemented (Phase 1 — 80%)

**Persistent episodic memory**
Jules doesn't save logs. It saves episodes: what problem you were solving, how you approached it, what worked, which model responded. Retrieval is semantic, not chronological — Jules finds what's relevant, not what's newest.

**Quota-aware router**
Classifies every task (identity, coding, reasoning, analysis) and selects the optimal model based on available tier. Never burns premium quota on tasks that don't justify it. Automatic fallback to Ollama when external providers don't respond.

**Credential sanitizer**
The first module to run, always. Before scoring, before memory, before everything. Detects and discards API keys, tokens, secrets, and credentials before they reach any database. Runs twice: on input and on candidate episodes before persisting.

**Local importance scoring**
Llama 3.2 1B evaluates the relevance of each episode (0.0–1.0) without consuming external quota. Includes defensive scoring: if the model degenerates and returns constant scores, Jules detects it and enters conservative persistence mode rather than silently discarding or saving everything.

**Context intent inference**
Jules doesn't ask what you're doing — it infers it. The same action triggers different responses based on context: opening a file after an error is debugging; opening it after reading docs is learning.

**Event system and file watcher (Module 8)**
Fully async, decoupled reactive EventBus via `asyncio.to_thread` to maintain zero latency in the user's terminal. Observes filesystem changes in background with a smart `LinuxWatcher` that skips heavy directories (`.git`, `node_modules`, `.venv`) and installs safe interactive shell hooks for `zsh`.

**Hybrid CPU performance optimization**
Low-level optimization for hybrid CPU architectures (such as Intel Alder Lake P/E-cores), forcing mapping to high-performance threads, plus an async preloading system to eliminate cold-start latency for local models.

### In progress (Phase 1 — remaining)

- Permission system with explicit confirmation for consequential actions
- `jules doctor` — full environment diagnostic at startup
- Main CLI that connects everything

### Planned (Phases 2–4)

- Voice system (whisper.cpp + Piper)
- KDE Plasma environment automation via D-Bus / KWin
- Replay system — reconstruction of debugging sessions
- Desktop app (Tauri + SvelteKit)
- Cognitive profiler and cognitive diff
- Opt-in contextual initiative

---

## Architecture

```
User input
  ↓
Sanitizer  ←── ALWAYS FIRST
  ↓
Context Intent Detector
  ↓
Context + Memory Engine
  ├─ RAM          (active session)
  ├─ LanceDB      (episodes + embeddings)
  └─ SQLite       (facts, preferences, projects)
  ↓
Quota-aware Router
  ├─ Ollama / Llama 3.2    (local / offline / identity / scoring)
  ├─ Antigravity CLI       (Google + Claude + GPT)
  └─ OpenCode CLI          (GPT-5 / Codex / Deepseek / Llama)
  ↓
Response to user  ←── IMMEDIATE, non-blocking
  ↓ (background async)
Post-processing → Sanitizer → Scoring → Persistence
```

**Critical latency rule:** the response to the user never waits for anything in post-processing. Everything runs in a separate `asyncio.create_task()`. The user never waits on memory.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Isolation | Dedicated virtualenv |
| CLI | Click + asyncio |
| Relational DB | SQLite (→ PostgreSQL when scaled) |
| Migrations | Alembic |
| Vector DB | LanceDB |
| Local inference | Ollama + Llama 3.2 1B |
| External provider 1 | Antigravity CLI |
| External provider 2 | OpenCode CLI |
| Frontend (Phase 2) | Tauri + SvelteKit |

---

## Providers and models

Jules operates with three providers. External ones are invoked as subprocesses — Jules never touches credentials; each CLI manages its own authentication.

| Provider | Tier | Models |
|---|---|---|
| Ollama (local) | free | Llama 3.2 1B — identity, scoring, offline |
| Antigravity CLI | low / high cost | Gemini Flash, Gemini Pro, Claude Sonnet/Opus |
| OpenCode CLI | low / high cost | GPT-5, GPT-5.4, Codex, Deepseek, Qwen |

The router assigns each task type to the correct tier. `IDENTITY` and `MEMORY_SCORING` always go to Ollama, no exceptions. `CODING` goes to OpenCode. `ANALYSIS` goes to Antigravity high_cost. No model is hardcoded in the source — everything lives in `config.toml`.

---

## Target environment

Jules is developed and operated on:

- **OS:** EndeavourOS (Arch-based, rolling release)
- **Desktop:** KDE Plasma 6 + Wayland
- **Shell:** fish / zsh / bash (detected at runtime)
- **Python:** dedicated virtualenv — never the system Python

All system integrations (window management, events, shell hooks) are designed for this environment from the ground up, not retrofitted.

---

## Installation

> Jules is in active Phase 1 development. No stable release yet. The following is the development setup.

```bash
# Clone the repository
git clone https://github.com/e12jassir/Jules.git
cd Jules

# Create and activate virtualenv — required
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Initialize the database
alembic upgrade head

# Verify environment
jules doctor
```

### Prerequisites

```bash
# Ollama with Llama 3.2
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

# Check inotify (EndeavourOS / Arch)
cat /proc/sys/fs/inotify/max_user_watches
# If below 65536:
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf
sudo sysctl -p /etc/sysctl.d/jules.conf
```

---

## Usage

```bash
# Direct question
jules "how does Python's GIL work?"

# With model override
jules --model claude-sonnet-4-6 "review this architecture"

# No memory (clean session)
jules --no-memory "explain asyncio from scratch"

# View recent episodes
jules memory

# Provider and memory status
jules status

# Full environment diagnostic
jules doctor

# Last execution details
jules debug last

# Sanitizer log
jules logs --sanitized

# Importance scorer health
jules logs --scoring
```

---

## `jules doctor`

Before any session, Jules verifies its own environment:

```
jules doctor
──────────────────────────────────────────────
✓ Ollama          active · llama3.2:1b available
✓ Antigravity     available in PATH
✓ OpenCode        available in PATH
✓ LanceDB         vectors OK
✓ SQLite          migrations current (rev: a3f9c1)
✗ inotify         8192 watches — recommended ≥65536
✓ Virtualenv      active (.venv)
✓ ~/.jules/       permissions OK
⚠ Scoring         insufficient data yet
✓ Shell           fish · hooks in conf.d/jules.fish
──────────────────────────────────────────────
1 issue detected. Jules operating partially.
```

Doctor never blocks startup. It reports and lets the user decide.

---

## Design principles

**Local-first.** Jules works offline. Privacy is not a feature — it's the foundation.

**Zero latency in terminal.** The response arrives before persistence finishes. Always.

**Graceful degradation.** If LanceDB fails, Jules continues without semantic memory. If SQLite fails, it enters degraded mode. If all external providers fail, Ollama responds. The user always knows what's degraded — no silent errors.

**Initiative off by default.** Jules doesn't interrupt. It doesn't interpret silence as a blocker. When the user enables contextual initiative, it operates under strict rules: one intervention per reason per session.

**Privacy by design.** The sanitizer is the first module to run, always. Nothing sensitive touches the database.

---

## Project status

```
Phase 1 — Core
  [x] Module 0  — Base structure + virtualenv
  [x] Module 1  — Sanitizer
  [x] Module 2  — Data models
  [x] Module 3  — Ollama provider
  [x] Module 4  — External providers (Antigravity + OpenCode)
  [x] Module 5  — Quota-aware router
  [x] Module 6  — Memory engine (SQLite + LanceDB + Scoring)
  [x] Module 7  — Context intent detector
  [x] Module 8  — Event system + shell hooks
  [ ] Module 9  — Permission system
  [ ] Module 10 — jules doctor
  [ ] Module 11 — Main CLI
  [ ]           — Phase 1 final review (Opus)

Phase 1.5 — Stabilization     (pending)
Phase 2   — Expansion         (pending)
Phase 3   — Intelligence      (pending)
Phase 4   — Autonomy          (pending)
```

103 tests passing across completed modules.

---

## Documentation

- [`JULES.md`](./JULES.md) — canonical system specification: architecture, principles, modules, full configuration
- [`ROADMAP.md`](./ROADMAP.md) — detailed build plan: modules, done criteria, implementation order

---

## Configuration

Jules is configured from `~/.jules/config.toml`. Key values:

```toml
[memory]
importance_threshold   = 0.3
decay_rate_per_30_days = 0.10
max_episodes_retrieved = 5

[routing]
default_tier = "low_cost"

[initiative]
enabled = false  # off by default

[sanitizer]
strict_mode = true

[doctor]
inotify_min_watches        = 65536
scoring_variance_threshold = 0.01
```

Full configuration is documented in [`JULES.md`](./JULES.md).

---

## Contributing

Jules is a personal project in active construction. External contributions aren't open yet — the core needs to stabilize first.

If you find something interesting or have feedback, feel free to open an issue.

---

## License

MIT — see [`LICENSE`](./LICENSE)

---

*Jules is not another chatbot.*  
*It's the only system that knows how you think.*
