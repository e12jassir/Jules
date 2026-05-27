# Sanitizer Specification

## Purpose

Define Phase 1 input-safety behavior that blocks sensitive content before any downstream processing.

## Requirements

### Requirement: SanitizeResult Contract

The system MUST expose `Sanitizer.check(text) -> SanitizeResult` where `SanitizeResult` contains `is_safe: bool` and `reason: str | None`. `reason` MUST be a category label only and MUST be `None` when `is_safe` is true.

#### Scenario: Safe input returns safe result
- GIVEN input without sensitive matches
- WHEN `Sanitizer.check` is executed
- THEN result `is_safe` is `true`
- AND result `reason` is `None`

#### Scenario: Unsafe input returns categorized result
- GIVEN input containing a sensitive match
- WHEN `Sanitizer.check` is executed
- THEN result `is_safe` is `false`
- AND result `reason` is a category label only

### Requirement: Canonical Pattern Categories

The system MUST detect these categories using canonical regex rules: assignment secret (`(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*\S+`), bearer token (`Bearer\s+[A-Za-z0-9\-._~+/]+=*`), OpenAI key (`sk-[A-Za-z0-9]{20,}`), Google key (`AIza[0-9A-Za-z\-_]{35}`), GitHub token (`ghp_[A-Za-z0-9]{36}`), Slack token (`xox[baprs]-[A-Za-z0-9\-]+`), export secret (`(?i)export\s+\w*(key|token|secret|pass)\w*\s*=`), credentialed URL (`https?://[^@\s]+:[^@\s]+@`), private key header (`-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----`). The system MUST NOT use generic `[A-Za-z0-9]{20,}` detection.

#### Scenario: Positive detection coverage
- GIVEN inputs matching each canonical category
- WHEN each input is checked
- THEN each returns `is_safe=false`
- AND each returns the matching category reason

#### Scenario: False-positive guards on generic tokens
- GIVEN hashes, UUIDs, benign base64, long function names, imports, and git commands
- WHEN each input is checked
- THEN each returns `is_safe=true`

### Requirement: Hard Reject and Isolation

On any sensitive match, the system MUST hard reject the entire input, MUST NOT redact-and-continue, and MUST NOT pass original text to context, memory, router, providers, or prompt assembly.

#### Scenario: Synchronous flow halt
- GIVEN unsafe user input
- WHEN sanitizer detects a category
- THEN processing stops before context build and routing
- AND user-facing rejection includes category-only reason

#### Scenario: Background persistence halt
- GIVEN candidate episodes containing sensitive content
- WHEN second-pass sanitizer detects a category
- THEN candidate is rejected entirely
- AND no persistence action is executed

### Requirement: Safe Reporting and Logging

The system MUST report only category/reason and MUST NOT expose matched secret values in logs, errors, metrics, or user-visible messages.

#### Scenario: No leakage in observability
- GIVEN unsafe input with a concrete secret value
- WHEN rejection is logged or surfaced
- THEN only category and non-sensitive metadata are emitted
- AND raw secret substrings are absent

### Requirement: Edge-Case Detection Robustness

The system MUST detect multiline private keys, unusual capitalization in keyword/export matches, multiple secrets in one payload, and secrets on final line without trailing newline. The system MUST avoid catastrophic regex backtracking behavior. As a ReDoS/performance guardrail, `Sanitizer.check` MUST process 1 MB of input using canonical patterns in under 100 ms on a normal local machine.

#### Scenario: Multiline and terminal-line matches
- GIVEN text containing a multiline private key block or final-line secret
- WHEN sanitizer checks the text
- THEN detection returns `is_safe=false`
- AND reason maps to the correct category

#### Scenario: Multiple secrets and large payload
- GIVEN input containing multiple secret categories and large non-secret spans
- WHEN sanitizer checks the text
- THEN result is unsafe with category-only reason
- AND evaluation completes within the 1 MB under 100 ms guardrail on a normal local machine

#### Scenario: Guardrail interpretation for test environments
- GIVEN local and CI environments with small runtime variance
- WHEN performance guardrail checks are executed
- THEN the 1 MB under 100 ms threshold is treated as a ReDoS guardrail, not a fragile microbenchmark
- AND minor environmental variance MAY be handled by tolerance guidance in design/tasks and test harness configuration

### Requirement: Strict TDD Verification

Verification MUST follow strict TDD with pytest: tests are written first and fail before implementation; tests MUST cover positive, negative, and edge cases listed in this spec.

#### Scenario: RED before GREEN evidence
- GIVEN the sanitizer module is unimplemented
- WHEN the new sanitizer test suite is executed first
- THEN tests fail for missing behavior
- AND subsequent implementation is accepted only after all tests pass
