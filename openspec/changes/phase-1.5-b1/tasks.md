# Tasks: Phase 1.5 Batch 1 — IPC Server (Python)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450–520 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR — cohesive greenfield module |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

> Rationale: All files are new, tightly coupled (protocol ↔ handlers ↔ server), and meaningless in isolation. Splitting would create unverifiable intermediate PRs.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Complete IPC server + tests | PR 1 | Single cohesive feature; all-or-nothing |

## Phase 1: Protocol Layer

- [ ] 1.1 Create `jules/server/__init__.py` — expose public names (`IpcMessage`, `from_json`)
- [ ] 1.2 Create `jules/server/protocol.py` — base `IpcMessage` dataclass with `type: str` field
- [ ] 1.3 Add inbound message types: `InitRequest`, `MessageRequest`, `CommandRequest`, `ModelSetRequest`, `ModelListRequest`, `StatusGetRequest`, `CancelRequest`, `QuitRequest`
- [ ] 1.4 Add outbound event types: `ReadyEvent`, `TokenEvent`, `ThoughtEvent`, `DoneEvent`, `CancelledEvent`, `CommandResultEvent`, `ModelChangedEvent`, `ModelListEvent`, `StatusEvent`, `ErrorEvent`
- [ ] 1.5 Implement `to_json()` on each type and `from_json(raw: str) -> IpcMessage` dispatcher
- [ ] 1.6 Add unit tests in `tests/unit/test_ipc_protocol.py` — round-trip serialization for every type, unknown type → `ErrorEvent`

## Phase 2: Handlers

- [ ] 2.1 Create `jules/server/handlers.py` — `handle_init(protocol_version)` returning `ReadyEvent` with real `boot_ms`
- [ ] 2.2 Implement `handle_message(req)` as async generator yielding `TokenEvent`/`ThoughtEvent`/`DoneEvent`, wiring to `CognitiveRouter`
- [ ] 2.3 Implement `handle_cancel()` — sets cancellation flag, emits `CancelledEvent`; silently ignored when no generation active
- [ ] 2.4 Implement `handle_model_list()` → `ModelListEvent` from provider registry
- [ ] 2.5 Implement `handle_model_set(provider, model)` → `ModelChangedEvent`
- [ ] 2.6 Implement `handle_status_get()` → `StatusEvent` with online/episodes/scoring data
- [ ] 2.7 Implement `handle_command(name, args)` → `CommandResultEvent` (ok/error)
- [ ] 2.8 Implement `handle_quit()` — clean process exit via `asyncio` shutdown

## Phase 3: Server Loop

- [ ] 3.1 Create `jules/server/server.py` — `main()` coroutine: stdin `asyncio.StreamReader`, line-by-line JSON parsing
- [ ] 3.2 Implement dispatch table mapping `msg.type` → handler coroutine
- [ ] 3.3 Write responses to stdout with immediate flush; logs to stderr only
- [ ] 3.4 Add SIGTERM handler: flush pending events, clean exit
- [ ] 3.5 Add `__main__.py` or `if __name__` block so `python -m jules.server` works

## Phase 4: Integration Tests

- [ ] 4.1 Create `tests/integration/test_server_ipc.py` — helper to spawn subprocess and send/receive JSON lines
- [ ] 4.2 Test: `message` → stream of `token` events → `done` event
- [ ] 4.3 Test: `model_list` → valid `ModelListEvent` with provider data
- [ ] 4.4 Test: `quit` → process exits with code 0
- [ ] 4.5 Test: malformed JSON → `error` event, server stays alive
- [ ] 4.6 Verify: `echo '{"type":"model_list"}' | python -m jules.server` prints valid JSON
