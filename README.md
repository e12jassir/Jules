<div align="center">

# Jules

### The AI that lives inside your OS. Not in a tab. Not in a cloud. *Here.*

<br/>

![Phase](https://img.shields.io/badge/Phase_1-Complete-22c55e?style=flat-square&labelColor=1e1e2e)
![Jarvis Layer](https://img.shields.io/badge/Jarvis_OS-Active-3b82f6?style=flat-square&labelColor=1e1e2e)
![Voice & Daemon](https://img.shields.io/badge/Resident_Daemon-Online-10b981?style=flat-square&labelColor=1e1e2e)
![Tests](https://img.shields.io/badge/Tests-450_passing-22c55e?style=flat-square&labelColor=1e1e2e)
![Platform](https://img.shields.io/badge/Platform-Linux_(any_distro)-f97316?style=flat-square&labelColor=1e1e2e)
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

Jules is built for Linux — any distribution. No fixed desktop environment, no fixed init system assumed.

| Component | Value |
|---|---|
| OS | Linux — any distribution. macOS is not supported |
| Desktop | Not assumed — detected at runtime, not hardcoded |
| Init system | systemd when available, with a fallback path for distros that don't use it |
| Shell | Detected at runtime — native hooks for fish / zsh / bash |

It detects your shell, watches the filesystem via a polling-based watcher (with an inotify limit health check), and understands the difference between you debugging and you reading docs. OS-level integrations are evaluated against what's actually available at runtime — never assumed from a fixed distro or desktop environment.

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

### It Has Senses and OS Reflexes

Jules is not limited to text in a terminal. It perceives and interacts with the host environment directly:

- **Ears (Local STT):** `faster-whisper INT8` running on local CPU with Silero VAD calibrated to a 300ms silence threshold. Speech transcription happens locally without transmitting audio bytes to third parties.
- **Mouth (Streaming Neural TTS):** Dual-tier synthesis engine. Edge TTS (`es-CO-SalomeNeural`) provides ultra-natural Spanish voice synthesis, with automatic, transparent failover to local Kokoro ONNX on network dropouts. Sentence-level early chunking (`min_first_chars=12`) plays the first spoken sentence while subsequent tokens are still streaming from the LLM.
- **Hands (OS Reflexes):** Real-time execution tags parsed from conversational streams:
  - Audio: `wpctl` (volume adjustment, muting, query default sink).
  - Media: `playerctl` (play, pause, next track, current metadata).
  - Wayland Window Management: `hyprctl` (launch apps, switch workspaces, manage windows).
  - System Telemetry: direct inspection of `/proc` and `free` (load averages, memory pressure).
- **Eyes (On-Demand Perception):** RAM-only Wayland screen capture via `grim -` and sanitized clipboard capture via `wl-paste` without temporary files written to disk.

---

### It Lives as a Resident Daemon

Jules operates as an always-on resident background service (`JulesDaemon`):

- **Zero Cold-Start:** Whisper models, VAD detectors, and audio streams remain warm in RAM.
- **UNIX Domain Socket IPC:** Inter-process communication through `/run/user/$UID/jules.sock` with atomic state emission at `/run/user/$UID/jules.state`.
- **Global Hotkey:** Triggered across the desktop via `SUPER + J` in Hyprland using an ultra-fast socket client (`~/.local/bin/jules-listen`, < 20ms invocation), completely decoupled from terminal windows.

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
| CLI & Daemon | Click + asyncio | Pure terminal + background resident UNIX daemon |
| Speech-to-Text | faster-whisper INT8 | 100% local, warm resident inference in RAM |
| Voice Activity Detection | Silero VAD | 300ms silence threshold, zero cloud dependence |
| Text-to-Speech | Edge TTS + Kokoro ONNX | Cloud neural quality + resilient offline local fallback |
| OS Reflexes | PipeWire (`wpctl`), MPRIS (`playerctl`), Hyprland (`hyprctl`) | Real-time system control without extra services |
| IPC & State | UNIX Domain Sockets | Secure `/run/user/$UID/jules.sock` with atomic permissions |
| Vector DB | LanceDB | Episodic embeddings, semantic retrieval |
| Relational DB | SQLite -> PostgreSQL | Local-first; migrate only when scale demands |
| Migrations | Alembic | Versioned schema from day one |
| Local inference | Ollama + Llama 3.2 1B | Identity, routing, scoring — zero external quota |
| Cloud Providers | Google GenAI / OpenRouter / Anthropic | High-speed reasoning with zero thinking delay |
| Desktop Hotkey | Hyprland + standalone micro-client | Sub-20ms instant trigger decoupled from terminal |

---

## Build Status

```
Phase 1 — Core Architecture
  [x] Module 0   — Project structure + virtualenv
  [x] Module 1   — Sanitizer
  [x] Module 2   — Data models
  [x] Module 3   — Ollama provider
  [x] Module 4   — External providers (Google GenAI + OpenCode)
  [x] Module 5   — Quota-aware router
  [x] Module 6   — Memory engine (SQLite + LanceDB + Scoring)
  [x] Module 7   — Context intent detector
  [x] Module 8   — Event system + shell hooks
  [x] Module 9   — Permission system
  [x] Module 10  — jules doctor
  [x] Module 11  — Main CLI
  [x] Module 12  — OpenAI auth via WebSockets

Phase 2 — Living OS & Jarvis Architecture
  [x] Phase 2.1  — Real-time atomic daemon state publisher (/run/user/$UID/jules.state)
  [x] Phase 2.2  — UNIX Domain Socket IPC (/run/user/$UID/jules.sock)
  [x] Phase 2.3  — Resident JulesDaemon service and systemd generator
  [x] Phase 3.1  — Asynchronous shell event hooks for fish/bash/zsh
  [x] Phase 3.2  — InitiativeEngine (friction detection, cooldown registry)
  [x] Phase 4.1  — AudioListener with resident Silero VAD (300ms window)
  [x] Phase 4.2  — LocalTranscriber with warm faster-whisper INT8
  [x] Phase 4.3  — Dual-tier VoiceSpeaker (Edge TTS + Kokoro ONNX) and SentenceStreamChunker
  [x] Phase 5.1  — Wayland RAM-only screen capture (grim) and sanitized clipboard (wl-paste)
  [x] Phase 7.1  — Native OS tools: PipeWire volume (wpctl), media (playerctl), Hyprland (hyprctl)
  [x] Global Hotkey — Standalone socket trigger script bound to SUPER + J
```

**450 tests passing** across all modules (`pytest tests/unit/`). Every module is tested before the next one starts. No red test goes to commit.

---

## Commands

```bash
# Resident daemon management
jules daemon start
jules daemon status
jules daemon stop
jules daemon install    # Installs systemd --user service

# Conversational voice loop (terminal interface)
jules voice

# Global Desktop Hotkey (Hyprland / Wayland)
# Press SUPER + J to trigger resident voice interaction instantly

# Direct query via CLI
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
