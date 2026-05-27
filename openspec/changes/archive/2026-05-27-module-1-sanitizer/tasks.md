# Tasks: Module 1 Sanitizer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 360-520 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (core contract + canonical detection) → PR 2 (edge/perf/logging guardrails) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Deliver contract + canonical category detection with RED→GREEN→REFACTOR tests | PR 1 | Base: main (or feature tracker if chosen); include tests + impl + exports |
| 2 | Deliver leakage, multiline/final-line, multi-secret, and 1 MB <100 ms guardrail checks | PR 2 | Depends on PR 1; include tests + impl refinements + docs note |

## Phase 1: Foundation / Test Harness

- [x] 1.1 RED: Replace TODOs in `tests/unit/test_sanitizer.py` with failing tests for `SanitizeResult` contract (`is_safe`, `reason=None|category`) and `Sanitizer.check(text)` API.
- [x] 1.2 RED: Add parametrized failing fixtures for all canonical categories from spec (`assignment_secret`, `bearer_token`, `openai_key`, `google_key`, `github_token`, `slack_token`, `export_secret`, `credentialed_url`, `private_key`).
- [x] 1.3 RED: Add failing false-positive tests in `tests/unit/test_sanitizer.py` (hashes, UUIDs, benign base64, long identifiers, imports, git commands stay safe).

## Phase 2: Core Implementation (GREEN)

- [x] 2.1 GREEN: Implement `SanitizeResult` and private `_PatternRule` in `jules/sanitizer/sanitizer.py`; compile canonical `SENSITIVE_PATTERNS` at import time.
- [x] 2.2 GREEN: Implement `Sanitizer.check(text)` in `jules/sanitizer/sanitizer.py` with deterministic first-match hard reject and category-only reason.
- [x] 2.3 GREEN: Update `jules/sanitizer/__init__.py` exports for stable imports used by tests and callers.
- [x] 2.4 REFACTOR: Ensure no generic `[A-Za-z0-9]{20,}` detector exists; keep rule order explicit and comments minimal/safety-focused.

## Phase 3: Safety Guarantees, Edge Cases, Performance

- [x] 3.1 RED→GREEN: Add `caplog` tests in `tests/unit/test_sanitizer.py` proving logs/messages include category only and never matched secret substrings.
- [x] 3.2 RED→GREEN: Add multiline private-key, final-line-without-newline, and multiple-secrets tests with deterministic category assertions.
- [x] 3.3 RED→GREEN: Add guardrail test/harness in `tests/unit/test_sanitizer.py` using `time.perf_counter()` for 1 MB input; enforce <100 ms locally with CI tolerance/skip marker guidance.

## Phase 4: Verification and Work-Unit Readiness

- [x] 4.1 Run `python -m pytest tests/unit/test_sanitizer.py` after each RED→GREEN cycle; capture failing-first then passing evidence in task notes/PR body.
- [x] 4.2 Verify each work unit is reviewable: tests and implementation in same unit, rollback-safe boundaries, and independent acceptance checks per PR.
- [x] 4.3 Acceptance check: unsafe samples halt with `is_safe=False` + category-only reason; safe samples return `is_safe=True` + `reason=None`; no secret leakage in logs.
