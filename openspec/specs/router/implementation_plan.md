# Module 5 — Quota-Aware Cognitive Router (V2 Redesign)

## Goal Description
Implement the Quota-Aware Cognitive Router, but fixing the critical flaws discovered during Judgment Day. We must achieve zero-latency I/O, eliminate race conditions during concurrent Antigravity CLI calls, and securely prevent local tasks from leaking to cloud providers during fallbacks.

## User Review Required

> [!IMPORTANT]
> **Static Multi-Profile Architecture for Antigravity**
> Instead of dynamically creating temporary directories and writing TOML files on *every* request (which causes race conditions and blocks the async loop), we will generate static config directories for each configured model *once* during initialization.
>
> Example: `~/.jules/antigravity_profiles/gemini-3.5-flash-low/config.toml`.
> When routing, Jules will simply point `XDG_CONFIG_HOME` to the pre-generated static path. No disk I/O occurs during the critical `ask()` path. Do you approve this static caching approach?

## Proposed Changes (Fixes to be applied)

### 1. Fix Antigravity Isolation (No more TempDirs per request)
#### [MODIFY] [jules/providers/antigravity.py](file:///home/e12jassir/proyects/Jules/jules/providers/antigravity.py)
- **Init Phase:** Create a synchronous `_ensure_profile(model: str)` method that runs *once* when the provider is initialized or the first time a model is requested.
- **Profile Generation:** This method uses `shutil.copytree` to copy `~/.config/antigravity` to a stable cache path like `~/.jules/agy_profiles/<model_name>`. It then updates the `config.toml` inside safely (using regex or string replacement to avoid wiping out integers/booleans).
- **Execution Phase:** In `_run_cli()`, simply set `env["XDG_CONFIG_HOME"] = str(Path("~/.jules/agy_profiles") / model)`. **Remove all tempfile context managers and sync I/O from the async path.**

### 2. Fix the Fallback Security Leak
#### [MODIFY] [jules/core/router.py](file:///home/e12jassir/proyects/Jules/jules/core/router.py)
- In the `ask_with_fallback` fallback loop, add a strict boundary check to prevent offline tasks from ever touching a cloud provider:
  ```python
  if task in LOCAL_ONLY_TASKS and fallback_provider_name != "ollama":
      continue
  ```

### 3. Fix Router Crashes on Bad Configs
#### [MODIFY] [jules/core/router.py](file:///home/e12jassir/proyects/Jules/jules/core/router.py)
- Move the primary `self.route(task, user_override)` call *inside* the `try` block.
- Update the exception handler to catch both routing and execution errors: `except (ProviderError, ValueError) as exc:`.

### 4. Fix Prompt Injection
#### [MODIFY] [jules/providers/antigravity.py](file:///home/e12jassir/proyects/Jules/jules/providers/antigravity.py)
- Drop the `.startswith("-")` string check entirely. Use standard POSIX conventions in `_run_cli`:
  `args = [self.executable, "--print", "--", prompt]`

## Verification Plan
1. GPT 5.5 will apply these precise surgical changes.
2. It will update `tests/unit/test_router.py` to assert the new `~/.jules/agy_profiles/<model_name>` behavior.
3. We will run `.venv/bin/pytest tests/unit/test_router.py` to ensure all 73 tests pass again.
4. We will trigger Judgment Day (Round 4) to get the final `VERDICT: CLEAN`.
