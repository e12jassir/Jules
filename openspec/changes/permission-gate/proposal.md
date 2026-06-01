# Proposal: Permission Gate (Módulo 9)

## Intent
Implement a secure, non-blocking permission system (`PermissionGate`) to authorize agent actions. This prevents unintended destructive operations while maintaining zero-latency responsiveness and background task stability.

## Scope
- Creation of `PermissionGate` for action classification and authorization.
- Integration with foreground Rich prompts for interactive approval.
- Integration with EventBus/async task handlers for fail-safe background execution.

## Capabilities

### New Capabilities
- **Action Classification**: Categorize actions into *Safe*, *Required*, and *Prohibited*.
- **Interactive Authorization**: Prompt users via Rich for *Required* actions in the foreground.
- **Background Fail-Safe**: Silently deny *Required* actions in background threads, logging the attempt and notifying the user to retry in the foreground.

### Modified Capabilities
- **Agent Execution Flow**: Intercept tool/action execution to enforce ephemeral permission checks without blocking.
- **EventBus / Task Runner**: Handle denied async tasks gracefully, ensuring no event loop blocking for authorization.

## Approach
1. **Core Logic**: Define a `PermissionGate` class evaluating actions against a predefined registry.
2. **Classification**:
   - *Safe*: Auto-approve (e.g., read state, search files).
   - *Required*: Pause and prompt in foreground; in background, send a desktop notification and `await` user approval asynchronously without blocking the event loop (Async Pause).
   - *Prohibited*: Always deny (e.g., `rm -rf /`, modifying core OS config files directly without package manager).
 3. **Async Handling**: Detect execution context. If a background task (e.g., `asyncio.create_task`) requests a *Required* action, it fires a DBus/desktop notification and goes into an `await asyncio.Future()` state. The event loop remains unblocked. The task resumes only when the user approves via voice or CLI.
 4. **Persistence**: Ephemeral (one-time approval per action). Approvals do not persist across executions.

## Affected Areas
- `PermissionGate` module (New)
- Tool execution / action dispatch pipeline
- EventBus / background task runners
- Rich terminal output handlers

## Risks
| Risk | Mitigation |
|------|------------|
| Background tasks blocked by prompts | Strict execution context detection to fail-safe deny *Required* background actions. |
| Overly restrictive permissions | Clear definition of *Safe* actions and a seamless foreground retry loop for denied tasks. |

## Rollback Plan
1. Disable `PermissionGate` middleware/interceptor.
2. Revert tool dispatch pipeline to pre-gate state.
3. Remove authorization checks from background task executors.

## Dependencies
- Rich library (interactive prompts)
- EventBus / asyncio infrastructure

## Success Criteria
- [ ] *Safe* actions execute without interruption.
- [ ] *Required* actions prompt the user via Rich in the foreground.
- [ ] *Required* actions in background tasks are silently denied, logged, and do not block the event loop.
- [ ] *Prohibited* actions are strictly denied.
- [ ] Approvals are strictly ephemeral (one-time).
