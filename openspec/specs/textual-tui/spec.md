# Textual TUI Specification

## Purpose

Define the behavior of Jules's persistent Textual TUI — the primary user interface for interactive sessions.

## Requirements

### Requirement: TUI Launch

The system MUST open the Textual TUI when `jules` is invoked with no arguments. The system MUST preserve `jules doctor` as a classic CLI command that does NOT launch the TUI.

#### Scenario: No-arg launch opens TUI

- GIVEN Jules is installed and in PATH
- WHEN the user runs `jules` with no arguments
- THEN the Textual TUI MUST open and display the WelcomeScreen

#### Scenario: Doctor remains classic CLI

- GIVEN Jules is installed
- WHEN the user runs `jules doctor`
- THEN output MUST be plain text to stdout without launching the TUI

### Requirement: Welcome Screen

The WelcomeScreen MUST display: logo text, braille rose art, input box, available models indicator, key bindings, a rotating tip, and the status bar.

#### Scenario: Welcome elements visible

- GIVEN the TUI has launched
- WHEN the WelcomeScreen is displayed
- THEN the user MUST see the logo, braille rose, input box, model indicator, key bindings, rotating tip, and status bar

### Requirement: Chat Transition

The system MUST transition from WelcomeScreen to ChatScreen when the user submits their first message.

#### Scenario: First message triggers transition

- GIVEN the WelcomeScreen is displayed and input is focused
- WHEN the user types a message and presses Enter
- THEN ChatScreen MUST replace WelcomeScreen and display the submitted message in ChatLog

### Requirement: Streaming

ChatLog MUST display provider responses token-by-token. Input MUST be disabled during streaming. The status bar MUST show a generating indicator while streaming.

#### Scenario: Token-by-token display

- GIVEN a message has been submitted
- WHEN the provider streams tokens
- THEN each token MUST appear in ChatLog incrementally as received

#### Scenario: Input disabled during stream

- GIVEN a response is streaming
- WHEN the user attempts to type
- THEN the InputBar MUST reject input until streaming completes

#### Scenario: Status bar indicates generation

- GIVEN a response is streaming
- WHEN the user looks at the status bar
- THEN it MUST display a 'generating...' indicator

### Requirement: Sidebar Reactivity

Sidebar panels (model, memory, stats) MUST update reactively after each response and persistence cycle without blocking the UI thread.

#### Scenario: Model panel updates on route

- GIVEN the router selects a model for a query
- WHEN the selection is made
- THEN ModelPanel MUST reflect the active model and provider without user action

#### Scenario: Memory panel updates after persistence

- GIVEN post-processing persists a new episode in the background
- WHEN persistence completes
- THEN MemoryPanel counters MUST update without blocking ChatLog or InputBar

### Requirement: Model Cycling via TAB

The TAB key MUST cycle through all available models (configured + locally discovered Ollama manifests). The Agents panel is future scope (Phase 2+); TAB is reassigned to model cycling.

#### Scenario: TAB cycles models

- GIVEN the TUI is on ChatScreen or WelcomeScreen
- WHEN the user presses TAB
- THEN the active model MUST advance to the next available model and the ModelPanel MUST update

#### Scenario: TAB wraps around

- GIVEN the user has cycled to the last available model
- WHEN the user presses TAB again
- THEN the model MUST wrap back to the first available model

### Requirement: Slash Commands

The system MUST recognize and execute: `/exit`, `/memory`, `/status`, `/doctor`, `/clear`, `/model`, `/help`, `/sessions`.

#### Scenario: Known command executes

- GIVEN the InputBar is active
- WHEN the user submits `/status`
- THEN the system MUST execute the status command and display results in ChatLog

#### Scenario: Unknown command rejected

- GIVEN the InputBar is active
- WHEN the user submits `/nonexistent`
- THEN the system MUST display an error indicating the command is not recognized

### Requirement: Degraded Mode

The TUI MUST open even if Ollama, LanceDB, or SQLite are unavailable. Degraded state MUST be shown in sidebar panels. The TUI MUST NOT crash on startup due to unavailable services.

#### Scenario: TUI opens with Ollama down

- GIVEN Ollama is not running
- WHEN the user launches `jules`
- THEN the TUI MUST open and ModelPanel MUST show offline status

#### Scenario: TUI opens with LanceDB unavailable

- GIVEN LanceDB is unreachable
- WHEN the TUI starts
- THEN MemoryPanel MUST show a degraded indicator and the TUI MUST remain interactive

### Requirement: Startup Budget

The TUI MUST be interactive within 500ms when Ollama is warm. Doctor MUST run in the background without blocking startup.

#### Scenario: Interactive under budget

- GIVEN Ollama is warm and responsive
- WHEN the user launches `jules`
- THEN the WelcomeScreen input MUST accept keystrokes within 500ms of invocation

#### Scenario: Doctor non-blocking

- GIVEN doctor checks take >200ms
- WHEN the TUI starts
- THEN doctor results MUST appear in the status bar asynchronously without delaying input readiness

### Requirement: Zero Latency Response

The response MUST reach ChatLog before persistence completes. Post-processing (scoring, embedding, storing) MUST run in background via asyncio tasks.

#### Scenario: Response before persistence

- GIVEN a provider has finished streaming
- WHEN the response is finalized in ChatLog
- THEN persistence MUST still be in-flight or not yet started — never blocking response display
