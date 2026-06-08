## Exploration: TUI Migration to Rust + Ratatui

### Current State
The Jules TUI currently runs in Python using Textual (`jules/cli/`). Textual's architecture renders solid cell backgrounds, which breaks compositor transparency (e.g., Ghostty + KDE Plasma). 
To fix this, Phase 1.5 introduces a two-process architecture:
1. **Python Backend:** A new server module (`jules/server/`) runs `asyncio` to read/write IPC messages (newline-delimited JSON) via `stdin` and `stdout`. It implements zero-latency rules by pushing processing to background tasks.
2. **Rust Frontend:** A missing frontend that must spawn the Python server as a child process, handle terminal events via `crossterm`, update state, and render the immediate-mode UI using `ratatui` (which naturally supports transparency).

### Affected Areas
- `jules-tui/Cargo.toml` — New project dependencies (`tokio`, `ratatui`, `crossterm`, `serde_json`).
- `jules-tui/src/main.rs` — Needs entrypoint logic to spawn the Python child process, set up IPC, and manage the event loop.
- `jules-tui/src/app.rs` — AppState struct will manage messages, active model, input state, and UI redraw triggers.
- `jules-tui/src/ipc.rs` — Requires strongly-typed structs mapping to Python dataclasses (`MessageRequest`, `TokenEvent`, `DoneEvent`, etc.) and a parser.

### Approaches
1. **Monolithic Tokio Select Loop**
   - Single async task uses `tokio::select!` to await `EventStream` (terminal inputs) and a `BufReader` over the Python process `stdout`.
   - Pros: Single context for state mutation, avoiding `Arc<Mutex>`. Straightforward to reason about concurrently.
   - Cons: `crossterm`'s async `EventStream` can sometimes be tricky to align perfectly with UI redraw loops without stalling.
   - Effort: Medium

2. **Actor-Based Message Passing (MPSC Channels)**
   - Three independent tasks: (a) Blocking terminal input listener, (b) Async IPC stdout parser, (c) IPC stdin writer. They all send an `AppEvent` enum (e.g., `AppEvent::Terminal(KeyEvent)`, `AppEvent::Ipc(IpcMessage)`) via a `mpsc::unbounded_channel` to a central UI rendering loop.
   - Pros: Maximum decoupling. Terminal reads and IPC reads never block each other. Follows zero-latency principles by ensuring the central loop is just for fast `AppState` updates and Ratatui `draw()` calls.
   - Cons: Slightly higher boilerplate for channel setup and message routing.
   - Effort: Medium

3. **Synchronous UI with Background IPC**
   - Standard blocking UI loop, while `tokio` runs the IPC in the background updating an `Arc<Mutex<AppState>>`.
   - Pros: Traditional immediate-mode loop.
   - Cons: Lock contention on `AppState` during fast token streaming can cause UI stutter. Defeats the zero-latency goal.
   - Effort: Low

### Recommendation
**Approach 2 (Actor-Based Message Passing)** is the recommended path. It strictly adheres to Jules' zero-latency requirement. By defining a unified `AppEvent` enum, the main loop simply drains a channel, mutates `AppState` without locks, and calls Ratatui's `terminal.draw()`. It maps perfectly to Tokio's strengths while keeping Ratatui redraws detached from raw I/O.

### Risks
- **Zombie Processes:** If the Rust TUI panics or is killed (e.g., `SIGKILL`), the `python -m jules.server` child process might be left running. Clean shutdown and `Drop` handlers must be implemented for the child process.
- **Serialization Mismatches:** Differences between Rust `serde` and Python `dataclasses` (e.g., missing fields, optional fields) could silently drop IPC messages. Ensure strict parity between `protocol.py` and Rust structs.
- **Transparency Re-regression:** If Ratatui widgets explicitly set a background color (e.g., `Color::Reset` vs omitting `bg`), transparency will break again. UI styling must omit background color configurations.

### Ready for Proposal
Yes — the architecture is clear and the orchestrator can proceed to `sdd-propose` to confirm the state structure and Tokio task layout.
