# Spec: Event System and Shell Integration

## Requirement: Zero Latency Event Bus
The system MUST provide an `EventBus` that dispatches events to registered handlers without blocking the main event loop.
- **Scenario**: Emitting an event
  - **Given**: Handlers (sync and async) are registered for `shell_event`.
  - **When**: The event is emitted.
  - **Then**: Async handlers MUST execute directly, sync handlers MUST execute via `asyncio.to_thread`.
  - **Then**: The garbage collector MUST NOT kill background tasks prematurely.

## Requirement: Zsh Hooks Injection
The system MUST safely inject hooks into Zsh.
- **Scenario**: Injecting precmd and preexec
  - **Given**: A `.zshrc` file exists.
  - **When**: The shell logic applies hooks.
  - **Then**: It MUST use `autoload -Uz add-zsh-hook` and NOT overwrite raw `precmd()` functions.
  - **Then**: Permissions MUST be preserved using atomic writes (`shutil.copymode`).

## Requirement: File Watcher Performance
The file watcher MUST NOT flood the event bus on startup or drain CPU.
- **Scenario**: Initial startup
  - **Given**: A large project directory.
  - **When**: The watcher starts.
  - **Then**: It MUST perform a baseline scan without emitting events (`_baseline_initialized`).
  - **Then**: It MUST prune `.git`, `node_modules`, and `.venv` during `os.walk`.
  - **Then**: It MUST respect and check `inotify` max_user_watches limits, issuing warnings if below 65536.
