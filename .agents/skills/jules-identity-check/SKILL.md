---
name: jules-identity-check
description: "Trigger: adding new providers, personality tweaks, coherence test. Verify that Jules' identity remains stable across different models."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Run this skill when implementing a new Provider, changing `config.toml` routing tiers, or modifying personality presets in `~/.jules/personality/`.

## Hard Rules

- A new provider MUST NOT be activated in production without passing the coherence test.
- Jules is a persistent AI, not a human, and must not be sycophantic or cringe.

## Execution Steps

1. Run the coherence integration tests: `pytest tests/integration/test_provider_coherence.py`
2. Verify that the new provider responds directly, calmly, and without unnecessary apologies.
3. If the test fails, update the provider's system prompt preset, do NOT change the global `master.md` identity file.
