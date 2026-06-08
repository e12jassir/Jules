# IPC Protocol Specification

## Purpose

Define the stdin/stdout newline-delimited JSON contract between the Rust TUI frontend and the Python backend server. This is the sole communication channel — no HTTP, no sockets.

## Requirements

### Requirement: Message Framing

Every message exchanged between TUI and server MUST be a single JSON object terminated by a newline (`\n`). Multi-line JSON MUST NOT be used.

#### Scenario: TUI sends well-formed request

- GIVEN the TUI wants to send a user message
- WHEN it writes to the server's stdin
- THEN it MUST write exactly one JSON object followed by `\n` with no embedded newlines

#### Scenario: Server rejects malformed frame

- GIVEN the server receives a line that is not valid JSON
- WHEN it attempts to parse it
- THEN it MUST write `{"type":"error","message":"parse error","recoverable":true}` to stdout and continue running

### Requirement: TUI → Server Message Types

The TUI MUST support these outbound message types: `init`, `message`, `command`, `model_set`, `model_list`, `status_get`, `cancel`, `quit`.

#### Scenario: Handshake init

- GIVEN the TUI starts
- WHEN it sends `{"type":"init","protocol_version":1}`
- THEN the server MUST respond with `{"type":"ready","protocol_version":1,"boot_ms":<ms>}`

#### Scenario: Send user message

- GIVEN the user submits text
- WHEN the TUI sends to the server
- THEN the payload MUST be `{"type":"message","content":"<text>"}` and the server runs it as a background task

#### Scenario: Send slash command

- GIVEN the user submits a slash command (e.g. `/status`)
- WHEN the TUI sends to the server
- THEN the payload MUST be `{"type":"command","name":"<cmd>","args":[]}` and server responds with `command_result`

#### Scenario: Cancel streaming

- GIVEN a message is streaming
- WHEN the user sends Ctrl+C
- THEN the TUI MUST send `{"type":"cancel"}` and the server MUST emit `{"type":"cancelled"}`

#### Scenario: Quit message triggers clean shutdown

- GIVEN the user closes the TUI
- WHEN the TUI sends `{"type":"quit"}`
- THEN the server MUST finish in-flight work and exit cleanly

### Requirement: Server → TUI Message Types

The server MUST emit these message types: `ready`, `token`, `thought`, `done`, `cancelled`, `command_result`, `model_changed`, `model_list`, `status`, `error`.

#### Scenario: Ready signal after init

- GIVEN the TUI sends `init` with protocol version
- WHEN the server starts
- THEN it MUST emit `{"type":"ready","protocol_version":1,"boot_ms":<ms>}` signaling readiness

#### Scenario: Streaming tokens arrive incrementally

- GIVEN the provider is streaming a response
- WHEN the server emits each chunk
- THEN each MUST be `{"type":"token","content":"<chunk>"}` on its own line

#### Scenario: Streaming thoughts emitted

- GIVEN the provider emits internal reasoning or CoT steps
- WHEN the server sees them
- THEN it MUST emit `{"type":"thought","content":"<reasoning>"}` before tokens

#### Scenario: Stream completion signaled

- GIVEN the provider has finished streaming
- WHEN the server finalizes
- THEN it MUST emit `{"type":"done","tokens":<N>}` exactly once

#### Scenario: Command result after dispatch

- GIVEN the TUI sends a `command`
- WHEN the server processes it
- THEN it MUST emit `{"type":"command_result","name":"<cmd>","ok":true/false,"data":<object>,"error":null or "<msg>"}`

#### Scenario: Cancellation acknowledged

- GIVEN the TUI sends `cancel` during streaming
- WHEN the server stops the task
- THEN it MUST emit `{"type":"cancelled"}` exactly once

#### Scenario: Error is recoverable or terminal

- GIVEN a provider is unavailable
- WHEN the server emits an error
- THEN `recoverable` MUST be `true` if the TUI can retry, `false` if it should show a fatal error state

### Requirement: Field Parity

Every field in `protocol.py` dataclasses MUST have a corresponding field in the Rust `serde` structs, and vice versa. Optional fields MUST be typed `Option<T>` in Rust and `Optional[X]` in Python.

#### Scenario: Rust deserializes Python-emitted JSON without data loss

- GIVEN the Python server emits a valid message
- WHEN the Rust IPC parser deserializes it
- THEN all fields MUST be present and correctly typed with no silent drops

#### Scenario: Missing optional field handled gracefully

- GIVEN a message has an absent optional field
- WHEN either side deserializes it
- THEN it MUST default to `None` / `null` without error
