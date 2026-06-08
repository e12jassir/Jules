# Proposal: TUI Migration to Rust + Ratatui

## Intent

The Textual TUI (`jules/cli/`) paints every terminal cell with a solid background, breaking compositor transparency under Ghostty + KDE Plasma 6. This is an irresolvable architectural limit of Textual. Replace ONLY the presentation layer with a Rust/Ratatui frontend (immediate mode → native transparency). The Python backend is untouched and exposed over a stdin/stdout IPC server.

## Scope

### In Scope
- `jules/server/` — asyncio stdin/stdout server (newline-delimited JSON v1).
- `jules-tui/` — Rust frontend: spawns the Python server, IPC loop, Ratatui draw cycle.
- Functional parity with the current Textual TUI (chat streaming, slash commands, model picker, sidebar, status bar).
- `jules --legacy` keeps launching the Textual TUI as fallback.

### Out of Scope
- Any change to backend logic (router, memory, providers, permissions).
- Desktop overlay (Fase 2, ITEM 6) and interactive provider tree (Fase 2, ITEM 8).
- Removing the Textual TUI — it is deprecated, not deleted, this phase.

## Capabilities

### New Capabilities
- `ipc-protocol`: stdin/stdout newline-delimited JSON contract between Rust frontend and Python backend (message types, direction, parity rules).
- `rust-tui`: Rust/Ratatui frontend — AppState model, Tokio task layout, widgets, keybindings, transparency guarantees.

### Modified Capabilities
- `textual-tui`: behavior changes from default frontend to `--legacy` fallback (deprecated).

## Approach

Adopt **Approach 2 (Actor-Based Message Passing)** from exploration. Three I/O tasks (blocking terminal listener, async IPC stdout parser, IPC stdin writer) feed a unified `AppEvent` enum into a central loop over a `tokio::sync::mpsc` channel. The central loop drains events, mutates `AppState` lock-free, and calls `terminal.draw()`. This honors the zero-latency rule (no `Arc<Mutex>` contention during token streaming) and keeps Ratatui redraws detached from raw I/O.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `jules/server/` | New | asyncio IPC server, handlers, typed protocol |
| `jules-tui/` | New | Rust crate: main, ipc, app, ui, widgets |
| `jules/cli/` | Modified | Marked deprecated; reachable via `--legacy` |
| `openspec/specs/textual-tui` | Modified | Reframed as fallback |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Zombie Python child on TUI panic/SIGKILL | Med | `Drop` handler + explicit kill on shutdown |
| serde ↔ dataclass serialization mismatch | Med | Strict parity tests between `protocol.py` and Rust structs |
| Transparency re-regression | Med | UI must omit `bg`; never set `Color::Reset` as background |

## Rollback Plan

The Rust frontend is additive (new `jules-tui/` crate + new `jules/server/`). No backend code is modified. To revert: stop shipping the Rust binary and route `jules` back to the Textual entrypoint (`jules --legacy` path becomes default). Backend and Textual TUI remain fully functional throughout.

## Dependencies

- Rust toolchain + Cargo (Ratatui v0.29+, Tokio, Crossterm, serde_json).
- Bun listed in environment but NOT required for this Rust path.

## Success Criteria

- [ ] Rust binary opens TUI with verified transparency in Ghostty + KDE.
- [ ] Full functional parity with Textual TUI (streaming, commands, picker, sidebar).
- [ ] Graceful degradation when backend is dead (error message, no crash).
- [ ] Startup < 10ms (TUI) + < 500ms (backend ready); `cargo build --release` yields a standalone binary.
- [ ] Python server tests + Rust IPC (mock) tests pass; `jules --legacy` still works.
