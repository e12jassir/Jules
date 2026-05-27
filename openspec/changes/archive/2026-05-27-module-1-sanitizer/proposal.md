# Proposal: Module 1 Sanitizer

## Intent

Implement Jules’ first safety boundary: a deterministic sanitizer that rejects sensitive input before context, memory, routing, providers, or logs can see secret values.

## Scope

### In Scope
- `Sanitizer.check(text) -> SanitizeResult` with `is_safe` and category-only `reason`.
- Hard reject semantics: any sensitive match blocks the entire input; no redaction-and-continue.
- Spec-locked detection for documented API keys, bearer tokens, provider tokens, exports, credentialed URLs, and private keys.
- Safety logging that records category/count only, never the matched value or full prompt.
- Exhaustive RED-GREEN-REFACTOR pytest coverage for positive, negative, multiline, and edge cases.

### Out of Scope
- Fuzzy/ML secret detection and generic `[A-Za-z0-9]{20,}` matching.
- CLI UX beyond returning category/reason for rejected input.
- Memory engine, provider, router, or persistence implementation.

## Capabilities

### New Capabilities
- `sanitizer`: Detects documented secret patterns and enforces category-only hard rejection before downstream processing.

### Modified Capabilities
- None

## Behavior Contract

- On sensitive match, Jules MUST reject the whole input and stop the flow.
- Rejected text MUST NOT reach context building, memory retrieval/persistence, router, providers, or prompt assembly.
- `reason` MUST expose only a category such as `bearer_token` or `private_key`; it MUST NOT expose the secret value.
- The same sanitizer API MUST support first-pass user input and second-pass candidate episode checks.

## Approach

Use a spec-locked regex core with private categorized rule entries. Keep the public API minimal while allowing future rules without changing callers. Start from failing tests, then implement only documented patterns.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `jules/sanitizer/sanitizer.py` | Modified | Replace TODO with `SanitizeResult`, rules, and `Sanitizer.check`. |
| `tests/unit/test_sanitizer.py` | Modified | Add strict TDD security tests and false-positive guards. |
| `openspec/specs/sanitizer/spec.md` | New | Future canonical sanitizer capability spec. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Secret logged by mistake | Med | Test logs and never log input/match text. |
| False positives block normal code | Med | Explicit negative tests for hashes, UUIDs, base64, git commands, imports. |
| Regex misses documented cases | Med | Parametrize tests for every canonical pattern. |

## Rollback Plan

Revert `jules/sanitizer/sanitizer.py`, `tests/unit/test_sanitizer.py`, and the sanitizer spec delta/proposal artifacts. No migrations or persisted user data are affected.

## Dependencies

- Module 0 project structure.
- `python -m pytest` available for strict TDD verification.

## Success Criteria

- [ ] Tests are written first and fail before implementation.
- [ ] All sanitizer tests pass with documented positive, negative, and edge cases.
- [ ] Hard reject prevents downstream access to unsafe input by contract.
- [ ] Logs and user-visible rejection expose category only, never secret values.

## Open Questions

None blocking.
