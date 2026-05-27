# Design: Module 1 Sanitizer

## Technical Approach

Implement a deterministic, synchronous regex-based safety boundary in `jules/sanitizer/sanitizer.py`. The public API stays minimal: `Sanitizer.check(text) -> SanitizeResult`. It hard-rejects on first sensitive match and returns only a stable category label. No redaction, fuzzy detection, ML, downstream calls, or generic `[A-Za-z0-9]{20,}` rule.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Rejection semantics | Hard reject whole input | Redact-and-continue | Safer for Phase 1; avoids partial leaks into context, memory, router, providers, or logs. |
| Rule model | Private categorized rule table with precompiled regex | Raw pattern list plus reverse lookup | Category mapping is explicit, testable, and never requires exposing matched values. |
| API shape | `Sanitizer.check` remains sync/static | Async service object | Regex scan is CPU-local and low-latency; async adds no value and complicates first-step flow. |
| Detection scope | Canonical credential patterns only | Generic long-token detector, entropy/fuzzy scanners | Preserves normal code/hash/base64 workflows and matches the accepted false-positive tradeoff. |
| Logging | Category-only structured log | Log prompt, match, or redacted value | Redaction can fail; logging only category/count avoids secret exposure. |

## Data Flow

    user/candidate text
          ↓
    Sanitizer.check(text)
          ↓
    iterate PRECOMPILED_RULES in canonical order
          ├─ first match → log category only → SanitizeResult(False, category)
          └─ no match    → SanitizeResult(True, None)

Callers must halt on unsafe results; Module 1 only provides the result contract.

## File Changes

| File | Action | Description |
|---|---|---|
| `jules/sanitizer/sanitizer.py` | Modify | Replace TODO with `SanitizeResult`, private `_PatternRule`, precompiled `SENSITIVE_PATTERNS`, logger, and `Sanitizer.check`. |
| `jules/sanitizer/__init__.py` | Modify | Optionally export `Sanitizer` and `SanitizeResult` for stable imports. |
| `tests/unit/test_sanitizer.py` | Modify | RED-first pytest coverage for positives, false-positive guards, logging, edge cases, and performance guardrail. |

## Interfaces / Contracts

```python
@dataclass(frozen=True, slots=True)
class SanitizeResult:
    is_safe: bool
    reason: str | None

@dataclass(frozen=True, slots=True)
class _PatternRule:
    category: str
    pattern: re.Pattern[str]
```

Categories: `assignment_secret`, `bearer_token`, `openai_key`, `google_key`, `github_token`, `slack_token`, `export_secret`, `credentialed_url`, `private_key`.

`SENSITIVE_PATTERNS` should be a tuple of `_PatternRule` objects compiled once at import time. Inline case-insensitive flags may remain in pattern strings where already canonical.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Contract and all canonical categories | Parametrized pytest; first run must fail against current TODO module. |
| Unit | False positives | Hashes, UUIDs, benign base64, imports, git commands, long identifiers MUST be safe. |
| Unit | Safe logging | Use `caplog`; assert category appears and concrete secret does not. |
| Unit | Edge/performance | Multiline private key, final-line secret, multiple secrets, 1 MB benign payload. |
| Integration/E2E | Not in Module 1 | Later CLI/memory tasks prove downstream halt behavior. |

Performance measurement: use `time.perf_counter()` around repeated `Sanitizer.check` calls on a deterministic 1 MB benign string plus one worst-case non-match sample. Warm up once, measure best/median of 3–5 runs locally. The product guardrail is <100 ms for one 1 MB check on a normal local machine; CI tests may mark this as a guardrail with tolerance/skip-on-slow-host metadata rather than a brittle microbenchmark. Any result far above threshold or superlinear growth is a blocker.

## Migration / Rollout

No migration required. This is a Phase 1 local module change with no persisted data impact.

## Open Questions

None blocking.
