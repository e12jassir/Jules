# Apply Progress: TUI Migration to Rust + Ratatui

## Status
In progress — Batch 2/3/4 apply advanced and buildable; validation exposed unrelated pre-existing Python test failures outside the Rust TUI change.

## Completed in this apply slice

- Added `jules-tui/src/main.rs` with:
  - Python child spawn via `python -m jules.server`
  - stdout JSONL reader task
  - stdin writer task
  - terminal event reader thread
  - central event loop over `AppEvent`
  - init/ready handshake, status/model bootstrap, graceful terminal restore
- Updated `jules-tui/src/app.rs` terminal event handling to accept full `crossterm::event::Event`.
- Updated `jules-tui/src/ui.rs` with modal overlays for connecting, backend error, and model picker.
- Routed `jules/cli/main.py` so default `jules` launches the Rust binary when present and `--legacy` keeps the Textual TUI.
- Added Rust state-transition tests in `jules-tui/src/main.rs` for ready/message/command flows.
- Fixed small Python-side typing/test seams discovered during validation:
  - `jules/cli/app.py` memory retrieval blocking helper for degraded-mode patching
  - `jules/cli/screens/chat.py` attribute access via runtime lookup
  - `jules/cli/screens/model_picker.py` sequence typing for option building

## Validation evidence

### Passed
- `cd jules-tui && cargo build --release`
- `cd jules-tui && cargo test` → 33 passed
- `python -m py_compile jules/cli/main.py jules/cli/app.py jules/cli/screens/chat.py jules/cli/screens/model_picker.py`
- `./.venv/bin/pytest tests/integration/test_server_ipc.py tests/integration/test_tui_chat.py tests/integration/test_tui_commands.py tests/integration/test_tui_degraded.py tests/integration/test_tui_welcome.py` → 20 passed
- `lsp_diagnostics` on edited Rust/Python files → 0 errors

### Blocked by unrelated existing failures
- `./.venv/bin/pytest tests/unit tests/integration`
- Current failing areas:
  - `tests/unit/test_openai_oauth_provider.py` (JWT/account-id expectations and list-model behavior)
  - `tests/integration/test_provider_coherence.py::test_ollama_embed_returns_vector` (local Ollama lacks embeddings support)

## Files changed in this apply slice

- `jules-tui/src/main.rs`
- `jules-tui/src/app.rs`
- `jules-tui/src/ui.rs`
- `jules/cli/main.py`
- `jules/cli/app.py`
- `jules/cli/screens/chat.py`
- `jules/cli/screens/model_picker.py`

## Next actions

1. Re-run the isolated degraded TUI integration test to confirm the new blocking helper fixed it.
2. Decide whether to treat OpenAI OAuth + Ollama embedding failures as out-of-scope pre-existing blockers or fix them before verify.
3. If accepted as out-of-scope, proceed to `sdd-verify` with explicit residual-risk notes.
