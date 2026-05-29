# Specification: Context Intent Detector

## 1. Intent Detection

The system MUST infer the user's operational intent using a stateless `ContextEngine` that complies with zero-latency requirements (<10ms). The intent MUST be one of: `debugging`, `learning`, or `review`.

### 1.1 Project Root Detection

The `ContextEngine` MUST determine the project root by resolving the nearest `.git` directory traversing parent directories. 

**Scenario: Resolving project root**
- **Given** the user is inside a nested project directory `/project/src/components`
- **And** the `.git` folder exists at `/project/.git`
- **When** `ContextEngine.build(session, input)` is invoked
- **Then** the engine SHALL resolve and store `/project` as the project root

### 1.2 Debugging Intent

The engine MUST map the intent to `debugging` if the last command executed in the session failed.

**Scenario: Detecting debugging intent**
- **Given** a `session` where `session.last_exit_code != 0`
- **When** the `ContextEngine` processes the session state
- **Then** the intent SHALL be classified as `debugging`

### 1.3 Learning Intent

The engine MUST map the intent to `learning` if the most recent commands indicate documentation lookups or learning activities.

**Scenario: Detecting learning intent**
- **Given** a `session` where `session.last_exit_code == 0`
- **And** the recent command history includes `man`, `--help`, or markdown (`.md`) file operations
- **When** the `ContextEngine` processes the session state
- **Then** the intent SHALL be classified as `learning`

### 1.4 Review Intent (Default)

The engine MUST map the intent to `review` as a fallback if no other intent criteria are met.

**Scenario: Defaulting to review intent**
- **Given** a `session` where `session.last_exit_code == 0`
- **And** the recent command history does NOT include learning operations
- **When** the `ContextEngine` processes the session state
- **Then** the intent SHALL be classified as `review`

## 2. Time of Day Mapping

The `ContextEngine` SHOULD incorporate the current time of day (`datetime.now().hour`) into the built context state to contextualize the intent.

**Scenario: Registering time of day**
- **Given** the current local time is 10:00 AM
- **When** `ContextEngine.build` executes
- **Then** the output context SHALL include the time of day as part of its state

## 3. Performance Constraint

The `ContextEngine` MUST operate without remote state lookups or LLM calls.

**Scenario: Zero-latency context building**
- **Given** a valid `session` object and user `input`
- **When** `ContextEngine.build(session, input)` is called
- **Then** the operation MUST complete in under 10ms
