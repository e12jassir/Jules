# Spec: Action Authorization

## Requirement: Action Classification
The system MUST categorize all requested actions into *Safe*, *Required*, or *Prohibited* through a `PermissionGate`.
- `yay` and `pacman` operations MUST be classified as *Required*.
- Destructive commands like `rm -rf /` or modifying core OS files directly MUST be classified as *Prohibited*.

**Scenario**: Classifying an action
- **Given** an action request is submitted to the `PermissionGate`
- **When** the action matches a known read-only pattern (e.g., reading state, searching files)
- **Then** the gate MUST classify it as *Safe*.
- **When** the action matches a system package modification (`yay`, `pacman`)
- **Then** the gate MUST classify it as *Required*.
- **When** the action matches a destructive pattern (`rm -rf /` or core OS modification without package manager)
- **Then** the gate MUST classify it as *Prohibited*.

## Requirement: Interactive Authorization
The system MUST prompt the user for explicit approval via Rich for *Required* actions executed in the foreground. Approvals MUST be ephemeral.

**Scenario**: Requesting foreground approval
- **Given** a *Required* action is requested in a foreground context
- **When** the `PermissionGate` evaluates the action
- **Then** it MUST pause execution and display an interactive Rich prompt.
- **When** the user approves
- **Then** the action MUST execute.
- **Then** subsequent requests for the identical action MUST NOT reuse the approval and MUST prompt the user again.

## Requirement: Background Async Pause & Notification
The system MUST suspend *Required* actions requested within a background execution context, dispatch a desktop notification, and wait asynchronously for user approval without blocking the event loop.

**Scenario**: Handling background *Required* actions
- **Given** an action is classified as *Required*
- **When** the action is invoked from a background task or thread
- **Then** the `PermissionGate` MUST dispatch a DBus desktop notification.
- **Then** it MUST suspend the task via an asynchronous `await` (e.g., `asyncio.Future`).
- **Then** the event loop MUST remain unblocked and process other events.
- **When** the user approves via voice or CLI
- **Then** the suspended task MUST resume and execute the action.

## Requirement: Agent Execution Flow Interception
The tool execution and action dispatch pipeline MUST be intercepted to enforce permission checks without blocking safe operations.

**Scenario**: Intercepting a tool execution
- **Given** the agent attempts to execute a tool
- **When** the tool is invoked
- **Then** the execution pipeline MUST pass the request to the `PermissionGate`.
- **When** the action is *Prohibited*
- **Then** the system MUST deny it immediately and MUST NOT trigger any user prompt.

## Requirement: EventBus Task Runner Graceful Degradation
The EventBus and task runners MUST gracefully handle tasks that are denied by the `PermissionGate` and avoid crashing.

**Scenario**: Denied async tasks
- **Given** the EventBus dispatches an event triggering an async task
- **When** the task attempts a *Required* or *Prohibited* action and is denied
- **Then** the task runner MUST capture the denial exception or return state.
- **Then** it MUST ensure the EventBus remains healthy and continues processing other events.
