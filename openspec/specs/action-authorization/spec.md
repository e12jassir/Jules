# Spec: Action Authorization — Module 9 (Permission Gate)

**Capability**: `action-authorization`
**Change**: `permission-gate`
**Status**: Draft
**Created**: 2026-06-02
**RFC Keywords**: This document uses keywords defined in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119): MUST, MUST NOT, SHALL, SHALL NOT, SHOULD, SHOULD NOT, MAY, RECOMMENDED, OPTIONAL.

---

## Overview

This specification formalizes the behavioral requirements for the `PermissionGate` — a deterministic, zero-latency authorization layer that intercepts all system actions before execution. The gate classifies every action as *Safe*, *Required*, or *Prohibited*, and applies the corresponding policy: execute uninterrupted, prompt for approval, or deny silently.

---

## Affected Files

| File | Change |
|------|--------|
| `jules/core/permissions.py` | New — `PermissionGate`, `PermissionClassification`, `PermissionDeniedError` |
| `jules/core/config.py` | Modified — parse new `[permissions]` TOML table |
| `config.toml` | Modified — add `require_confirmation_*` flags |
| `jules/core/events.py` | Modified — `ContextVar` flagging in async task runners |
| `jules/cli/main.py` | Modified — Click entrypoint intercept and approval handler |

---

## Requirement 1 — Action Classification

The `PermissionGate` MUST classify every incoming action into exactly one of three categories before any execution occurs: **Safe**, **Required**, or **Prohibited**.

Classification MUST be performed via a deterministic, rule-based regex engine. The classifier MUST resolve in near-zero latency and MUST NOT rely on any external model or network call.

### 1.1 Safe Actions

Actions that are read-only and do not mutate system or persistent application state MUST be classified as *Safe*.

Examples (non-exhaustive): reading file contents, searching installed packages, querying system status, listing directories.

**Scenario 1.1 — Safe action executes uninterrupted**

```gherkin
Given an action request arrives at the PermissionGate
When the action matches a read-only pattern (e.g., state search, file read, system status query)
Then the gate MUST classify the action as Safe
And the gate MUST allow execution to proceed immediately
And the gate MUST NOT display any prompt or notification to the user
And the gate MUST NOT log any denial or warning event
```

### 1.2 Required Actions

Actions that modify system state via an approved package manager (`pacman`, `yay`) or that alter writable application configuration MUST be classified as *Required*.

**Scenario 1.2 — Required action matched by package manager pattern**

```gherkin
Given an action request arrives at the PermissionGate
When the action string matches the pattern for a system package operation (pacman, yay)
Then the gate MUST classify the action as Required
And the gate MUST NOT execute the action immediately
And the gate MUST initiate the approval flow appropriate to the execution context (§ Req. 2 or § Req. 3)
```

### 1.3 Prohibited Actions

Actions that directly destroy system data, modify core OS files without using a package manager, or match any pattern defined in the `prohibited_patterns` ruleset MUST be classified as *Prohibited*.

Examples: `rm -rf /`, `dd if=/dev/zero of=/dev/sda`, direct writes to `/boot`, `/etc/passwd`, or `/lib`.

**Scenario 1.3 — Prohibited action is silently denied**

```gherkin
Given an action request arrives at the PermissionGate
When the action matches a destructive pattern (e.g., rm -rf /, direct core OS write without package manager)
Then the gate MUST classify the action as Prohibited
And the gate MUST raise a PermissionDeniedError immediately
And the gate MUST NOT display any interactive prompt or confirmation dialog
And the gate MUST NOT execute any part of the action
And the system MUST log a structured denial event at WARNING level
```

> **CRITICAL**: The denial for *Prohibited* actions MUST be silent and unconditional. There MUST be no user-facing prompt, bypass option, or override mechanism.

---

## Requirement 2 — Foreground Ephemeral Prompting

When a *Required* action is invoked from a foreground CLI context (i.e., within a Click command handler on the main thread), the `PermissionGate` MUST display an interactive approval prompt using a **Rich Panel live display**.

### 2.1 Ephemeral Buffer Clearing

The prompt MUST be ephemeral: upon receiving any user response (approval or denial), the gate MUST completely clear the console buffer used by the prompt display, leaving no scrollback trace of the authorization dialog.

**Scenario 2.1 — Foreground prompt clears buffer on confirmation**

```gherkin
Given a Required action is invoked from a foreground CLI context
When the PermissionGate evaluates the action
Then it MUST pause execution and render an interactive Rich Panel live display prompt
And the panel MUST display the action description, classification, and approval options
When the user submits any response (approve or deny)
Then the gate MUST clear the Rich console buffer used by the live display
And the terminal scrollback MUST contain no trace of the authorization panel
And if approved, the action MUST execute exactly once
And if denied, a PermissionDeniedError MUST be raised
```

### 2.2 Strict Approval Ephemerality

Approvals MUST be strictly one-time and scoped to the exact invocation that triggered the prompt.

**Scenario 2.2 — Approval does not carry over to subsequent invocations**

```gherkin
Given a Required action was approved and executed in invocation N
When the identical action is requested again in invocation N+1
Then the gate MUST NOT reuse or cache the approval from invocation N
And the gate MUST display the Rich Panel prompt again for invocation N+1
And the approval MUST be re-evaluated independently
```

> **Note**: There SHALL be no persistent approval store, session-level token, or database of granted approvals. Every execution is evaluated from scratch.

---

## Requirement 3 — Background Async Suspension via Desktop Notification

When a *Required* action is invoked from a background execution context (i.e., within an async event handler task created by `EventBus`), the `PermissionGate` MUST NOT use any interactive CLI prompt. Instead, it MUST suspend the task asynchronously and dispatch a KDE Plasma desktop notification with action buttons.

### 3.1 Context Identification via `contextvars`

The execution context MUST be identified using Python's standard library `contextvars.ContextVar`. The `EventBus` task runner MUST set this variable to `"background"` before launching any async handler task.

**Scenario 3.1 — Background context is correctly identified**

```gherkin
Given the EventBus dispatches an event to an async handler
When the EventBus creates the handler task via loop.create_task()
Then the task runner MUST set the IS_BACKGROUND_TASK ContextVar to True
And the ContextVar value MUST be inherited by all coroutines within that task's execution context
And the PermissionGate MUST read this ContextVar to determine the execution context before initiating any approval flow
```

### 3.2 Async Subprocess Notification with `--wait`

When in a background context and a *Required* action requires approval, the gate MUST call `notify-send` as an async subprocess.

**Scenario 3.2 — Background gate dispatches notify-send and suspends**

```gherkin
Given a Required action is invoked from a background task context
When the PermissionGate detects the IS_BACKGROUND_TASK ContextVar is True
Then the gate MUST NOT render any Rich CLI prompt or block the main thread
And the gate MUST create an asyncio.Future to hold the pending approval result
And the gate MUST launch an async subprocess call to notify-send with the following mandatory flags:
  - --action=approve=Approve
  - --action=deny=Deny
  - --wait
And the coroutine MUST await the Future, yielding control back to the event loop
And the event loop MUST remain fully responsive and process other events while the Future is pending
```

> **CRITICAL — `--wait` flag**: The `notify-send` subprocess call MUST include the `--wait` flag. This keeps the subprocess process alive until the user clicks a button, preventing the subprocess from exiting before emitting the action result to stdout. Without `--wait`, the stdout pipe closes immediately and the Future will never resolve.

### 3.3 Future Resolution from Subprocess stdout

**Scenario 3.3 — Subprocess stdout resolves the Future**

```gherkin
Given the notify-send subprocess is running with --wait
When the user clicks the Approve button on the desktop notification
Then the subprocess MUST print "approve" to stdout
And the async subprocess reader MUST call future.set_result("approve")
And the awaiting coroutine MUST resume with the approval result
And the Required action MUST execute
When the user clicks the Deny button on the desktop notification
Then the subprocess MUST print "deny" to stdout
And the async subprocess reader MUST call future.set_result("deny")
And the awaiting coroutine MUST resume and raise a PermissionDeniedError
And the Required action MUST NOT execute
```

---

## Requirement 4 — Non-GUI / SSH Fail-Safe Deny

When the execution environment does not have a graphical display available (i.e., no `DISPLAY` or `WAYLAND_DISPLAY` environment variable is set), the `PermissionGate` MUST NOT attempt to spawn a `notify-send` subprocess or any interactive GUI prompt.

**Scenario 4.1 — Headless environment triggers fail-safe deny**

```gherkin
Given the PermissionGate is about to initiate background desktop approval for a Required action
When both the DISPLAY and WAYLAND_DISPLAY environment variables are absent or empty
Then the gate MUST NOT call notify-send or any subprocess relying on a display server
And the gate MUST silently raise a PermissionDeniedError (fail-safe deny)
And the gate MUST log a structured event at WARNING level containing:
  - action description
  - classification (Required)
  - denial reason ("no_display_environment")
  - timestamp
And the system MUST output a clean system log alert (not a stack trace) describing the headless denial
And the Required action MUST NOT execute
```

> **SHOULD**: In headless/SSH environments, operators SHOULD review logs to confirm the expected fail-safe behavior is occurring. Future phases MAY introduce a socket-based fallback for headless approvals, but this is explicitly **out of scope** for this module.

---

## Requirement 5 — EventBus Graceful Degradation

The `EventBus` async task runner MUST handle `PermissionDeniedError` exceptions raised by the `PermissionGate` without crashing the event bus or leaving the system in an inconsistent state.

**Scenario 5.1 — PermissionDeniedError is captured and bus remains healthy**

```gherkin
Given the EventBus dispatches an event that triggers an async task
When the async task invokes a Required or Prohibited action
And the PermissionGate raises a PermissionDeniedError
Then the EventBus task runner MUST catch the PermissionDeniedError at the task boundary
And the task runner MUST log the denial event at WARNING level with the action context
And the task runner MUST NOT propagate the exception to the EventBus dispatch loop
And the EventBus MUST remain in a healthy state and continue processing subsequent events
And no application crash or unhandled exception MUST occur
```

**Scenario 5.2 — Denied task does not affect sibling tasks**

```gherkin
Given the EventBus has dispatched multiple concurrent async tasks for a single event
When one task raises a PermissionDeniedError
Then that task MUST be terminated cleanly without affecting other running tasks
And sibling tasks MUST continue to run to completion normally
```

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | The rule-based classifier MUST resolve in < 1ms for any input string. |
| NFR-2 | The gate MUST add zero latency to *Safe* actions. |
| NFR-3 | The `IS_BACKGROUND_TASK` ContextVar MUST be set before any awaitable yields in the task runner to ensure it is visible to all coroutines within the task. |
| NFR-4 | All denial events MUST be logged as structured data (dict/JSON-serializable), not free-form strings. |
| NFR-5 | The `PermissionGate` MUST be stateless across invocations; no instance-level approval cache SHALL exist. |

---

## Out of Scope

- Unix socket IPC daemon for cross-process approvals.
- Network-based API approval endpoints.
- Persistent approval database or session-level approval tokens.
- LLM-based classification or semantic intent analysis.
- Headless socket fallback (deferred to a future phase).

---

## Success Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| SC-1 | *Safe* actions execute with zero prompts and zero latency overhead. | Unit test: gate returns `None` for all safe patterns without calling any prompt function. |
| SC-2 | *Prohibited* actions are always denied with no prompt. | Unit test: gate raises `PermissionDeniedError` for all prohibited patterns without invoking any UI. |
| SC-3 | *Required* foreground actions render an ephemeral Rich Panel and clear the buffer on response. | Integration test: capture console output before/after confirmation; assert buffer is clean. |
| SC-4 | Approvals are strictly one-time; identical re-invocations prompt again. | Unit test: call gate twice with same action; assert prompt is shown twice. |
| SC-5 | Background tasks use `notify-send --wait` and suspend via `asyncio.Future`. | Integration test: mock subprocess; assert `--wait` in argv; assert event loop remains unblocked during await. |
| SC-6 | Headless environments trigger fail-safe deny with structured log and no subprocess spawn. | Unit test: unset DISPLAY and WAYLAND_DISPLAY; assert denial + log entry, assert no subprocess call. |
| SC-7 | EventBus catches `PermissionDeniedError` and remains healthy. | Integration test: dispatch event that raises `PermissionDeniedError`; assert bus processes next event normally. |
