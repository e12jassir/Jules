Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

# Tasks: Permission Gate

## 1. Foundation
- [ ] Create `jules/core/permissions.py`.
- [ ] Define `Action` and `ActionClass` enums (`SAFE`, `REQUIRED`, `PROHIBITED`).
- [ ] Define the `PermissionDeniedError` exception.
- [ ] Create the `PermissionGate` class.
- [ ] Implement `PermissionGate.check(action: Action, target: str) -> None` as an `async def` method that throws `PermissionDeniedError` upon denial.
- [ ] Ensure `yay` and `pacman` commands are classified as `Required`.
- [ ] Implement context detection in `PermissionGate` to distinguish foreground from background tasks.
- [ ] Add interactive Rich prompt for foreground `Required` actions, making approvals ephemeral (one-time approval per action).
- [ ] Implement Async Pause for background `Required` actions: call `notify-send` via DBus, create an `asyncio.Future()`, and `await` it so the event loop remains unblocked.
- [ ] Add CLI hook `jules approve` and voice input handlers to resolve the pending `asyncio.Future()` and resume the background task.

## 2. Implementation
- [ ] Modify `jules/core/events.py` (specifically `EventBus._run_handler`).
- [ ] Add an explicit `try/except PermissionDeniedError` block in `EventBus` to catch and log the denial gracefully, preventing the event loop from blocking or crashing.
- [ ] Integrate `await PermissionGate.check(...)` into the tool execution and action dispatch pipeline right before command execution.
- [ ] Map appropriate system actions to `ActionClass` via the `PermissionGate` logic.

## 3. Testing
- [ ] Write unit tests for `PermissionGate` classification, ensuring `yay` and `pacman` return `Required`.
- [ ] Write unit tests for the explicit try/except `PermissionDeniedError` handling in `EventBus._run_handler`.
- [ ] Write tests verifying the background deny fail-safe, ensuring `Required` actions throw `PermissionDeniedError` without prompting when invoked from a background execution context.
