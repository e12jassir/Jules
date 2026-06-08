# Design: TUI Migration to Rust + Ratatui

## Technical Approach

Two-process design: Rust/Ratatui frontend spawns `python -m jules.server` and talks newline-delimited JSON over the child's stdin/stdout. Implements `rust-tui` + `ipc-protocol` specs via the **Actor-Based Message Passing** approach (exploration Approach 2). The Python server (`jules/server/`) is already implemented (Batch 1) — this design adapts the Rust side to the ACTUAL protocol, which is richer than the roadmap's v1 sketch.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Concurrency | 3 I/O tasks → `AppEvent` enum → `mpsc` → central loop | Monolithic `select!`; `Arc<Mutex<AppState>>` | Lock-free state mutation; no UI stutter during token streaming (zero-latency rule) |
| Handshake | TUI sends `init`, waits for `ready{boot_ms}` before enabling input | Assume ready immediately | Server already implements init/ready; gives real backend-ready signal for the 500ms budget |
| Streaming model | Server runs `message` in a background task; TUI keeps reading | Block on stream | Lets `cancel` interrupt mid-stream — already supported server-side |
| Log channel | Rust reads stdout for protocol ONLY; child stderr piped to a log file | Mix logs in stdout | Server logs to stderr by design; mixing would corrupt JSON framing |
| Shutdown | `quit` msg + `Drop` impl on child handle that kills the process | Rely on OS cleanup | Prevents zombie `python` on panic/SIGKILL |

## Data Flow

```
                 ┌──────────────── Rust TUI (jules-tui) ────────────────┐
 key/resize ───► [terminal task] ──┐
                                    ├─► mpsc<AppEvent> ─► [central loop] ─► AppState ─► ratatui.draw()
 child stdout ─► [ipc reader] ──────┘                          │
                                                               ▼
 child stdin  ◄─ [ipc writer] ◄──────────────────────── AppEvent::Send(req)
                                    │
        spawn ▼                     │ stderr ─► log file
   python -m jules.server  ◄────────┘
```

## Sequence: message + cancel

```
TUI            Server
 │  init   ───►│
 │◄── ready ───│ (boot_ms)
 │  message ──►│ spawns _stream_message task
 │◄── token ───│ (repeated, incremental)
 │  cancel  ──►│ task.cancel()
 │◄ cancelled ─│
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `jules-tui/Cargo.toml` | Create | deps: ratatui 0.29+, tokio (rt-multi-thread, macros, process, io-util, sync), crossterm, serde, serde_json |
| `jules-tui/src/main.rs` | Create | spawn child, set up tasks + mpsc, run central loop, restore terminal on exit |
| `jules-tui/src/ipc.rs` | Create | `IpcOutbound`/`IpcInbound` serde enums (tagged by `type`), line reader/writer, child `Drop` guard |
| `jules-tui/src/app.rs` | Create | `AppState` (messages, input, active model, status, mode), `AppEvent` enum |
| `jules-tui/src/ui.rs` | Create | root layout + frame draw; NO `bg` set anywhere |
| `jules-tui/src/widgets/*.rs` | Create | chat_log, input_bar, sidebar, status_bar, model_picker |
| `jules/cli/main.py` | Modify | route `jules`→Rust binary, `jules --legacy`→Textual |

## Interfaces / Contracts

Rust enums MUST mirror `jules/server/protocol.py` EXACTLY (field-parity requirement). Use serde internally-tagged enums:

```rust
#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum IpcOutbound {
    Init { protocol_version: u8 },
    Message { content: String },
    Command { name: String, args: Vec<String> },
    ModelSet { provider: String, model: String },
    ModelList, StatusGet, Cancel, Quit,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum IpcInbound {
    Ready { protocol_version: u8, boot_ms: f64 },
    Token { content: String }, Thought { content: String },
    Done { tokens: u32 }, Cancelled,
    CommandResult { name: String, ok: bool, data: serde_json::Value, error: Option<String> },
    ModelChanged { provider: String, model: String },
    ModelList { models: Vec<Vec<String>> },
    Status { online: bool, episodes: u32, scoring_healthy: bool },
    Error { message: String, recoverable: bool },
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (Python) | protocol round-trip, dispatch | pytest (exists: test_protocol.py) |
| Integration (Python) | server stdin→stdout flow | pytest (exists: test_server_ipc.py) |
| Unit (Rust) | serde parity for every variant against fixture JSON | `cargo test` with JSON fixtures generated from protocol.py |
| Integration (Rust) | spawn mock server script, assert AppState transitions | mock `echo`-style script piping canned JSON |

## Migration / Rollout

Additive. `jules --legacy` preserves Textual. No data migration. Ship Rust binary alongside; flip default entrypoint once parity verified.

## Open Questions

- [ ] **Spec reconciliation**: real `protocol.py` has `init`/`ready` + `cancel`/`cancelled` + `command_result`/`thought` not in the current spec. sdd-spec wrote 6+7 types; actual is 8 inbound + 10 outbound. Update `ipc-protocol` spec to match code (code is source of truth).
- [ ] Status DB path mismatch: handlers read `~/.jules/memory.sqlite3` but project uses `jules.db` — verify before wiring `status_get`.
