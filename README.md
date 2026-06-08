<div align="center">

# Jules

### The AI that lives inside your OS. Not in a tab. Not in a cloud. *Here.*

<br/>

![Phase](https://img.shields.io/badge/Phase_1-Complete-22c55e?style=flat-square&labelColor=1e1e2e)
![Phase](https://img.shields.io/badge/Phase_1.5-Planned-6366f1?style=flat-square&labelColor=1e1e2e)
![Tests](https://img.shields.io/badge/Tests-120_passing-22c55e?style=flat-square&labelColor=1e1e2e)
![Platform](https://img.shields.io/badge/EndeavourOS-KDE_Plasma_6-f97316?style=flat-square&labelColor=1e1e2e)
![Python](https://img.shields.io/badge/Python-3.11+-eab308?style=flat-square&labelColor=1e1e2e)
![License](https://img.shields.io/badge/License-MIT-64748b?style=flat-square&labelColor=1e1e2e)

<br/>

*Not another chatbot. Not another AI wrapper.*
*The only system that knows how you think.*

</div>

---

## Why Jules Exists

Every AI assistant forgets you the moment you close the tab.

Jules doesn't.

I built Jules because I was tired of re-explaining context to every tool I opened. Tired of assistants with no memory, no presence, no understanding of how I work. I wanted something that **lives alongside me** — not something I visit.

Jules is a **persistent cognitive layer** for the Linux operating system. It runs in the terminal, where real work happens. It remembers between sessions, understands the environment it's running in, routes tasks intelligently across multiple AI providers, and never touches your secrets.

This is a personal project. Built by one person, with intention, from the ground up. Every decision in this codebase was made deliberately.

---

## What Makes Jules Different

### It Remembers You

Jules doesn't store logs. It stores **episodes** — structured units of meaningful memory:

- What problem you were solving
- How you approached it
- What actually worked
- How much friction you experienced

Memory retrieval is **semantic**, not chronological. When you ask Jules something, it finds what's *contextually relevant* — not just what's most recent. Powered by LanceDB vector embeddings. Importance scoring runs locally via Llama, so external quota is never spent on memory decisions.

---

### It Routes Intelligently

Jules manages three AI providers and selects the right model for every task — without you thinking about it.

| Task | Provider | Tier |
|---|---|---|
| Identity / Memory Scoring | Ollama (local) | Free — always |
| Quick queries | Antigravity — Gemini Flash | Low cost |
| Deep reasoning | Antigravity — Gemini Pro / Claude Sonnet | High cost |
| Coding tasks | OpenCode — GPT / Codex / Deepseek | Low cost |
| Heavy coding | OpenCode — GPT high tier | High cost |
| Analysis | Antigravity — Claude / Gemini Pro | High cost |

No model name is hardcoded in the source. Everything lives in `config.toml`. Swap a model string there — the entire routing changes instantly.

**Fallback chain:** `primary → secondary same tier → Ollama`. Jules never fails silently.

---

### It Runs at Zero Latency

The response arrives before persistence completes.

The entire post-processing pipeline — scoring, sanitizing, embedding, storing — runs inside `asyncio.create_task()` *after* you've already seen the answer. You never wait for memory.

```
User input → Sanitizer → Context Engine → Router → Response ← IMMEDIATE
                                                         ↓  (background)
                                                    Score → Embed → Persist
```

The response line does not wait for anything below it. This is a hard rule of the architecture.

---

### It Knows Its Environment

Jules isn't a generic Linux tool. It was designed for a specific, deliberate environment:

| Component | Value |
|---|---|
| OS | EndeavourOS (Arch-based, rolling release) |
| Desktop | KDE Plasma 6 + Wayland |
| Compositor | KWin |
| Shell | Detected at runtime — fish / zsh / bash |

It detects your shell, watches the filesystem via inotify, integrates with KDE Plasma via D-Bus, and understands the difference between you debugging and you reading docs. OS-level integrations are designed for this environment from the start — not retrofitted later.

---

### It Protects Your Data

Every input passes through the sanitizer before it touches memory. Secrets, tokens, credentials, private keys, auth headers — none of it reaches the database.

```python
# What the sanitizer catches — always, before anything else
Bearer tokens · OpenAI keys · Google API keys
GitHub tokens · Slack tokens · Exported env secrets
URLs with embedded credentials · Private key files
```

The sanitizer runs **twice** — on input, and again on episode candidates before persistence. Strict mode by default: discard on doubt, never partial-clean.

Privacy is not a feature here. It's the foundation.

---

### It Has a Personality

Jules is calm, intelligent, analytical, technically competent. It doesn't hallucinate confidence it doesn't have. It doesn't pad responses. It doesn't pretend to be human.

Its identity is **independent of the model**. Swap Gemini for Claude for GPT — Jules remains Jules. Personality is defined through provider-specific presets and verified through coherence tests. The model provides reasoning. Jules provides continuity.

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
  ├── RAM       — active session context
  ├── LanceDB   — episodic memory, semantic retrieval via embeddings
  └── SQLite    — persistent facts, preferences, active projects
  ↓
Quota-Aware Router
  ├── Classify task type
  ├── Select optimal tier
  └── Invoke provider
       ├── Ollama / Llama 3.2   — local, offline, identity, scoring
       ├── Antigravity CLI      — Google Gemini, Claude, GPT
       └── OpenCode CLI         — GPT, Codex, Deepseek, Llama
  ↓
Response → user  ←── IMMEDIATE — no blocking
  ↓  (background, async)
Post-Processing
  ├── Sanitizer (second pass on episode candidates)
  ├── Importance scoring via Llama local (never external quota)
  ├── ScoringHealthMonitor — detects degenerate scoring
  └── Persist or discard
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | Native async, ML ecosystem |
| CLI | Click + asyncio | Phase 1: pure terminal, no HTTP server |
| Vector DB | LanceDB | Episodic embeddings, semantic retrieval |
| Relational DB | SQLite → PostgreSQL | Local-first; migrate only when scale demands |
| Migrations | Alembic | Versioned schema from day one |
| Local inference | Ollama + Llama 3.2 1B | Identity, routing, scoring — zero external quota |
| Provider 1 | Antigravity CLI | Google Gemini, Claude, GPT via subprocess |
| Provider 2 | OpenCode CLI | GPT, Codex, Deepseek via subprocess |
| Desktop app (Phase 2) | Tauri + SvelteKit | Lightweight overlay — CLI stays primary |

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
  [x] Module 9   — Permission system
  [x] Module 10  — jules doctor
  [x] Module 11  — Main CLI
  [x] Module 12  — OpenAI auth via WebSockets

Phase 1.5  — Rust/Ratatui TUI migration   (planned)
Phase 2    — Expansion                    (planned)
Phase 3    — Adaptive Intelligence        (planned)
Phase 4    — Autonomy                     (planned)
```

**120 tests passing** across all completed modules. Every module is tested before the next one starts. No red test goes to commit.

---

## `jules doctor`

Jules verifies its own environment on startup:

```
jules doctor
──────────────────────────────────────────────
✓ Ollama          active · llama3.2:1b available
✓ Antigravity     available in PATH
✓ OpenCode        available in PATH
✓ LanceDB         vectors OK
✓ SQLite          migrations up to date (rev: a3f9c1)
✗ inotify         8192 watches — recommended ≥65536
✓ Virtualenv      active (.venv)
✓ ~/.jules/       write permissions OK
⚠ Scoring         insufficient data to evaluate health
✓ Shell           fish detected — hooks at conf.d/jules.fish
──────────────────────────────────────────────
1 problem detected. Jules is operating in partial mode.
```

Doctor never blocks startup. It reports, warns, and lets you decide.

---

## Commands

```bash
# Direct query
jules "how does Python's GIL interact with asyncio?"

# Force a specific model
jules --model claude-opus-4-8 "review this architecture"

# Skip memory for this session
jules --no-memory "explain asyncio from scratch"

# Browse recent episodes
jules memory

# Provider and memory status
jules status

# Full environment diagnostic
jules doctor

# Last execution breakdown
jules debug last

# Sanitizer discard log (no sensitive content ever shown)
jules logs --sanitized

# Importance scorer health history
jules logs --scoring
```

---

## Documentation

| Document | Purpose |
|---|---|
| [`JULES.md`](JULES.md) | Canonical system specification — architecture, data models, design decisions |
| [`ROADMAP.md`](ROADMAP.md) | Build plan — modules, done criteria, model routing per item |
| [`AGENT.md`](AGENT.md) | AI agent rules — inviolable model assignment matrix for SDD phases |

---

<div align="center">

*Jules is not another chatbot.*
*It's the only system that knows how you think,*
*how you solve problems, and how you've changed.*

*Built with intention. One module at a time.*

</div>
