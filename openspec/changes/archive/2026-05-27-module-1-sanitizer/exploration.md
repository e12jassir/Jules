## Exploration: Module 1 Sanitizer

### Current State
Jules defines sanitizer-first privacy guarantees in `AGENT.md`, `JULES.md`, and `ROADMAP.md`, including explicit regex patterns and the rule that secrets must never reach memory persistence. However, implementation is not started yet: `jules/sanitizer/sanitizer.py` and `tests/unit/test_sanitizer.py` are both TODO stubs.

Canonical requirements confirmed from docs:
- `Sanitizer.check(text) -> SanitizeResult` with `is_safe` and categorized `reason`
- Detect secrets using specific patterns (API key/token/password assignment, Bearer tokens, OpenAI/Google/GitHub/Slack tokens, `export ...=`, credentialed URLs, private keys)
- Explicitly exclude generic `[A-Za-z0-9]{20,}` due to false positives
- Log discard category without logging secret value
- Behavior must support both first-pass input sanitization and second-pass candidate-episode sanitization
- Module 1 done criteria requires exhaustive positive/negative/edge tests

### Affected Areas
- `jules/sanitizer/sanitizer.py` — primary sanitizer implementation module (currently stub)
- `tests/unit/test_sanitizer.py` — required exhaustive test suite (currently stub)
- `AGENT.md` — canonical regex list and `SanitizeResult` contract to mirror in code
- `JULES.md` — architecture and policy constraints: sanitizer-first and privacy-by-design
- `ROADMAP.md` — Module 1 scope, done criteria, and explicit false-positive guardrail
- `openspec/config.yaml` — strict TDD mode (`strict_tdd: true`) constrains next phases

### Approaches
1. **Spec-Locked Regex Sanitizer (single-pass API + reusable matcher)** — Implement exact documented patterns as compiled regex entries and expose one deterministic `check()` API used by both flow passes.
   - Pros: Maximum alignment with canonical docs; easiest to audit; low ambiguity for tests.
   - Cons: Regex-only approach may miss novel secret formats not listed.
   - Effort: Low

2. **Spec-Locked Core + Extensible Rule Registry** — Implement exact documented patterns now, but structure internals as categorized rule objects to allow future extension without API break.
   - Pros: Keeps Module 1 compliant while reducing refactor risk for future secret classes.
   - Cons: Slight upfront complexity beyond strict minimum for Phase 1.
   - Effort: Medium

### Recommendation
Use **Approach 2** with a hard boundary: no additional detection behavior beyond docs for Module 1. This preserves strict conformance now while avoiding redesign in later modules. Keep public API minimal (`SanitizeResult`, `Sanitizer.check`) and place extensibility only in private internals.

### Risks
- **False positives** if implementation drifts from explicit exclusions (especially generic long alphanumeric patterns).
- **False negatives** from regex mistakes (escaping, boundaries, multiline behavior) if tests are not exhaustive.
- **Policy drift** if logs accidentally include raw sensitive fragments.
- **TDD violation risk** because repository currently has stub tests; implementation must start RED-first to satisfy strict TDD mode.
- **Requirement ambiguity**: “descartar input” can mean reject whole message vs redact-and-continue; docs currently indicate reject, but this should be confirmed explicitly for CLI UX messaging.

### Ready for Proposal
Yes — with one clarification to carry into proposal/spec: confirm that detection action is always **hard reject** (never partial redact) in Phase 1 synchronous flow.
