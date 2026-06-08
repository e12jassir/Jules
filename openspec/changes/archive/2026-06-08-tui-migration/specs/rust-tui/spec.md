# Rust TUI Specification

## Purpose

Define the behavior of the Rust/Ratatui frontend — terminal transparency, IPC lifecycle, AppState management, widget behavior, keybindings, and degraded mode.

## Requirements

### Requirement: Terminal Transparency

The TUI MUST NOT set a background color on any widget or surface. Ratatui MUST render with default terminal background so the compositor transparency is preserved.

#### Scenario: No background color emitted

- GIVEN the TUI renders any widget
- WHEN Ratatui draws the frame
- THEN no `bg` color attribute MUST be set — `Color::Reset` used only for explicit resets, never as a background fill

### Requirement: Process Lifecycle

The Rust binary MUST spawn `python -m jules.server` as a child process on startup, establishing bidirectional pipes. On TUI exit or panic, the child process MUST be killed.

#### Scenario: Child process started on launch

- GIVEN the user runs `jules`
- WHEN the Rust binary starts
- THEN `python -m jules.server` MUST be spawned with stdin/stdout pipes attached

#### Scenario: Child killed on clean exit

- GIVEN the TUI is running
- WHEN the user presses `Ctrl+C` or sends `/exit`
- THEN the TUI MUST send `{"type":"quit"}` via IPC, wait for the child to exit, then terminate

#### Scenario: Child killed on panic

- GIVEN the TUI panics
- WHEN the Rust `Drop` handler for the child process runs
- THEN the child MUST be killed to prevent zombie processes

### Requirement: AppState and Event Loop

AppState MUST be mutated only by the central event loop. Three I/O tasks (terminal input, IPC stdout reader, IPC stdin writer) MUST communicate with the central loop exclusively via `tokio::sync::mpsc` channels carrying an `AppEvent` enum.

#### Scenario: Token event updates AppState without locks

- GIVEN the IPC reader task receives a `token` message
- WHEN it sends `AppEvent::Ipc(IpcMessage::Token)` to the central loop
- THEN the loop MUST append the token to AppState and call `terminal.draw()` — no `Mutex` involved

#### Scenario: Terminal input forwarded as AppEvent

- GIVEN the user presses a key
- WHEN the terminal input task captures it
- THEN it MUST send `AppEvent::Terminal(KeyEvent)` to the central loop

### Requirement: Startup Budget

The Rust TUI MUST be interactive within 10ms. The Python backend MUST be ready to accept messages within 500ms.

#### Scenario: TUI ready under 10ms

- GIVEN the user runs `jules`
- WHEN measured from process start to first rendered frame
- THEN the TUI MUST be interactive in ≤ 10ms

#### Scenario: Backend readiness without blocking TUI

- GIVEN the Python server takes up to 500ms to warm up
- WHEN the TUI starts
- THEN the TUI MUST render a loading indicator and remain interactive while waiting

### Requirement: Widget Functional Parity

The Rust TUI MUST implement all widgets from the Textual TUI: chat log (streaming), input bar (history, slash command prefix), model picker (overlay), sidebar (model/memory/stats panels), status bar (cwd, branch, clock, scoring state).

#### Scenario: Streaming renders token-by-token

- GIVEN the IPC reader is receiving `token` events
- WHEN each `AppEvent::Ipc(Token)` is processed
- THEN ChatLog MUST append the token and trigger a Ratatui redraw

#### Scenario: Input bar detects slash commands

- GIVEN the user types `/` as the first character
- WHEN subsequent keys are typed
- THEN the input bar MUST display a slash command hint or autocomplete prefix

#### Scenario: Model picker opens as overlay

- GIVEN the TUI is on any screen
- WHEN the user presses `Tab`
- THEN a model picker overlay MUST appear, cycling to the next model on each press and dismissing on Enter or Escape

### Requirement: Degraded Mode

The TUI MUST remain open and interactive if the backend fails to start or crashes mid-session. It MUST display an error state in the chat area without crashing.

#### Scenario: Backend startup failure

- GIVEN `python -m jules.server` exits with a non-zero code before sending any message
- WHEN the IPC reader detects the closed pipe
- THEN the TUI MUST display a recoverable error in ChatLog and disable input

#### Scenario: Backend crash mid-session

- GIVEN the TUI is in a normal session
- WHEN the Python child process dies unexpectedly
- THEN the TUI MUST show a fatal error message and offer to restart or exit — it MUST NOT itself crash

### Requirement: Distributable Binary

`cargo build --release` MUST produce a single binary with no external runtime dependencies. The binary MUST be runnable on the target machine without Cargo or a Rust toolchain installed.

#### Scenario: Release binary is self-contained

- GIVEN `cargo build --release` completes
- WHEN the resulting binary is copied to a clean installation
- THEN it MUST run without requiring Cargo, Rust, or any `.so` linking to Rust runtime libraries
