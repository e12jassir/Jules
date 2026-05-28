# Module 5 — Quota-Aware Cognitive Router (Ruteador Cognitivo)

## Goal Description
Implement the core tactical brain of Jules: the **Quota-Aware Cognitive Router**. The router acts as the single unified entry point for all prompts, decoupling the core logic from specific commercial models. It dynamically selects the optimal provider (`Ollama`, `Antigravity`, or `OpenCode`) and model based on task complexity, available budget tiers, and provider health.

## User Review Required

> [!IMPORTANT]
> **Environmental Isolation for Antigravity**
> To allow Jules to use its own models for `agy` without interfering with your personal CLI usage, we will implement Environmental Isolation. The router/provider will inject `XDG_CONFIG_HOME=~/.jules/antigravity_config` exclusively into the subprocess environment. Do you approve this isolation strategy?

> [!CAUTION]
> **Fallback Chain Strategy**
> The planned fallback logic is: `Primary Model (from config)` -> `Ollama (Local)`. If the primary provider times out or fails (e.g. no internet), it instantly degrades to local execution to guarantee a response. Do you agree with this strict 2-step chain?

## Open Questions

> [!WARNING]
> 1. Do we want to store `config.toml` in the project root (`Jules/config.toml`) for development (Phase 1), or should it strictly reside in `~/.jules/config.toml` immediately? 
> 2. What should be the default `low_cost` and `high_cost` models for OpenCode in the initial configuration template?

## Proposed Changes

### Configuration Layer
The router must read tiers dynamically without hardcoding models in Python.

#### [NEW] [config.toml](file:///home/e12jassir/proyects/Jules/config.toml)
Create the baseline configuration file (or template) defining the tiers:
```toml
[routing]
default_tier = "low_cost"

[routing.tiers.low_cost]
antigravity = ["gemini-3.5-flash-low"]
opencode = ["opencode/deepseek-v4-flash-free"]

[routing.tiers.high_cost]
antigravity = ["gemini-3.5-pro"]
opencode = ["opencode/deepseek-r1-heavy"]
```

#### [NEW] [jules/core/config.py](file:///home/e12jassir/proyects/Jules/jules/core/config.py)
Implement a lightweight configuration parser (using standard library `tomllib` available in Python 3.11+) to load the routing rules into a dataclass schema.

---

### Core Routing Engine

#### [NEW] [jules/core/router.py](file:///home/e12jassir/proyects/Jules/jules/core/router.py)
Implement the central routing logic.
- **`TaskType` (Enum):** `IDENTITY`, `MEMORY_SCORING`, `QUICK`, `REASONING`, `CODING`, `CODING_HEAVY`, `ANALYSIS`, `OFFLINE`.
- **`route(task: TaskType, user_override: str | None = None) -> tuple[Provider, str]`**: Algorithm to select the provider instance and the model string based on `config.toml`.
- **`ask_with_fallback(prompt: str, context: SessionContext, task: TaskType) -> tuple[str, str, str]`**: Unified orchestrator method. Returns `(response, model_used, provider_used)`.

---

### Provider Refactoring (Environmental Isolation)

#### [MODIFY] [jules/providers/antigravity.py](file:///home/e12jassir/proyects/Jules/jules/providers/antigravity.py)
- Update `_run_cli` to inject a custom `env` dictionary to the subprocess `asyncio.create_subprocess_exec`, overriding `XDG_CONFIG_HOME` to point to a Jules-specific config directory (`~/.jules/antigravity_config`). This guarantees zero collision with the user's personal CLI configuration.

---

### Test Suite

#### [NEW] [tests/unit/test_router.py](file:///home/e12jassir/proyects/Jules/tests/unit/test_router.py)
Exhaustive unit tests using `pytest-mock` and `pytest-asyncio`.
- Verify `IDENTITY`, `MEMORY_SCORING`, and `OFFLINE` **always** route to Ollama.
- Verify `CODING` routes to OpenCode.
- Verify `QUICK` routes to Antigravity.
- Simulate a `ProviderUnavailableError` or `ProviderTimeoutError` on the primary provider and assert that the Router catches it and triggers a fallback call to Ollama.
- Verify `user_override` is strictly respected, bypassing normal routing.

## Verification Plan

### Automated Tests
The implementation agent (GPT 5.5 / Sonnet) will run:
```bash
.venv/bin/pytest tests/unit/test_router.py -v
```

### Manual Verification
We will update our interactive tester script (`test_provider.py` -> `test_router.py`) so the user can interact directly with the `Router` instead of manually selecting a provider. The user will type a prompt, and the script will output which provider and model the Router selected behind the scenes.
