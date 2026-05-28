# Proposal — Module 5 Cognitive Router

## Goal
Ship the Module 5 Quota-Aware Cognitive Router V2 fixes so routing stays local-first, zero-latency, and safe under fallback.

## Scope
- Fix Antigravity static profile handling and CLI invocation.
- Fix router fallback order and local-only cloud leak prevention.
- Fix exact configured-model overrides, including Ollama model names containing `:`.
- Update unit and integration coverage.
- Verify under strict TDD evidence and Judgment Day.

## Non-Goals
- Introduce new providers.
- Rework unrelated modules.
- Change canonical router behavior beyond the approved Module 5 V2 redesign.
