# Design: Permission Gate

## Overview
This document details the technical design for the `PermissionGate` module, implementing secure action classification and authorization without blocking the async event loop.

## 1. Action Classification
We introduce `Action` to represent the semantic operation and `ActionClass` to represent the security tier.

```python
from enum import Enum

class Action(Enum):
    READ_STATE = "read_state"
    SEARCH_FILES = "search_files"
    MODIFY_SYSTEM = "modify_system"
    DESTRUCTIVE = "destructive"

class ActionClass(Enum):
    SAFE = "safe"
    REQUIRED = "required"
    PROHIBITED = "prohibited"

class PermissionDeniedError(Exception):
    pass
```

## 2. Architecture Decisions

### Decision 1: Async `check` Method
**Choice**: `PermissionGate.check(action: Action, target: str) -> None` MUST be `async def`.
**Alternatives**: A synchronous boolean-returning method.
**Rationale**: Interactive terminal prompts via Rich require `asyncio` to await user input. Blocking the main thread with a synchronous `input()` call would freeze all background tasks on the event loop.

### Decision 2: Explicit Call at the Point of Action
**Choice**: `PermissionGate.check(...)` MUST be called explicitly directly before the action is executed.
**Alternatives**: Implement an abstract middleware pipeline or decorator.
**Rationale**: Middleware hides the execution flow and obscures the `target` parameter context. Calling it explicitly ensures the authorization check is tightly bound to the specific operation, making the code much easier to trace and reason about. 

### Decision 3: Exceptions over Booleans
**Choice**: The gate MUST raise `PermissionDeniedError` on denied actions. The caller (e.g. `EventBus`) MUST explicitly catch `except PermissionDeniedError:`.
**Alternatives**: Return `True`/`False` or swallow the exception silently.
**Rationale**: Silent boolean returns are easily forgotten and ignored by the caller, leading to unauthorized actions proceeding or unpredictable states. Forcing an exception guarantees the denial is handled. Background task runners like `EventBus` MUST catch this specific exception to prevent silent crashes and avoid blocking the event loop.

## 3. Data Flow
1. **Invocation**: A tool executor attempts to run `yay -S neovim`. It explicitly calls `await PermissionGate.check(Action.MODIFY_SYSTEM, "yay -S neovim")`.
2. **Classification**: `PermissionGate` maps `Action.MODIFY_SYSTEM` to `ActionClass.REQUIRED`.
3. **Context Evaluation**: 
   - `PermissionGate` determines if it is running in a foreground or background context.
   - If **Background**: Calls `notify-send` (or DBus equivalent) with the prompt and creates an `asyncio.Future()`. The task `await`s this Future, suspending itself. The EventBus continues running perfectly.
   - If **Foreground**: Displays a `rich` prompt.
4. **Resolution**: The user responds (via voice command or a `jules approve` CLI command). This resolves the `Future` in the `PermissionGate`, and the original task resumes execution seamlessly.

## 4. File Changes

### `jules/core/permissions.py` (New)
Defines the enums, the exception, and the `PermissionGate` class containing the `check` method and prompt logic.

### `jules/core/events.py` (Modified)
Update `EventBus._run_handler` to catch the denial exception explicitly:
```python
try:
    if inspect.iscoroutinefunction(h):
        await h(p)
    else:
        await asyncio.to_thread(h, p)
except PermissionDeniedError as e:
    logging.getLogger(__name__).warning("Task denied: %s", e)
except Exception:
    logging.getLogger(__name__).exception("Error in handler for %s", e_type)
```

### Execution Points (e.g., `jules/tools/...` or `jules/providers/...`)
Insert `await PermissionGate.check(...)` right before invoking destructive commands or modifying system state.
