# Tasks — Module 5 Cognitive Router

## Implementation

- [x] Move Antigravity prompt transport to argv separator form: `agy --print -- <prompt>`.
- [x] Prepare Antigravity static profiles before `ask()` / `_run_cli()` so the critical provider path performs no profile disk I/O.
- [x] Copy the Antigravity config tree into per-model Jules profiles and patch only the copied `config.toml` model setting.
- [x] Resolve exact configured model override strings before parsing `provider:model`, including Ollama model names containing `:`.
- [x] Preserve local-only routing boundary so identity, memory scoring, and offline tasks never leak to cloud fallbacks.
- [x] Implement same-tier secondary model fallback before configured provider fallback chain.
- [x] Move singleton router construction/profile preparation off the event loop with `asyncio.to_thread`.
- [x] Update router unit tests for V2 behavior.
- [x] Update external provider integration tests to prepare Antigravity test models before `ask()`.
- [x] Clean implementation-plan trailing whitespace.

## Verification

- [x] Router unit tests pass: `./.venv/bin/python -m pytest tests/unit/test_router.py`.
- [x] Focused router/provider tests pass: `./.venv/bin/python -m pytest -q tests/unit/test_router.py tests/integration/test_external_providers.py`.
- [x] Full suite passes: `./.venv/bin/python -m pytest -q`.
- [x] Compile check passes: `./.venv/bin/python -m compileall jules`.
- [x] Whitespace check passes: `git diff --check`.
- [x] Judgment Day final review completed with no confirmed blocking findings.

## Review Workload Forecast

- Forecast: Medium risk; actual changed lines exceed the 400-line review budget.
- Delivery strategy: `size:exception` accepted for one cohesive Module 5 work unit because splitting would separate behavior from tests and make review/rollback less coherent.
