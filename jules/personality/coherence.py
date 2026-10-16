"""
jules.personality.coherence
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Identity coherence and persona verification for Jules.
Evaluates model outputs against Jules' non-servile, concise, analytical principles.
"""

from __future__ import annotations

import re

PROHIBITED_PATTERNS: list[str] = [
    r"\b(¡?claro que sí!?|por supuesto!?|estaré encantad[oa] de ayudarte|en qué te puedo colaborar|a tu disposición)\b",
    r"\b(as an ai language model|como modelo de lenguaje|como ia)\b",
    r"\b(disculpa las molestias|lamento mucho mi error anterior|perdóname la confusión)\b",
]

_COMPILED_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_PATTERNS]


def verify_identity_coherence(response: str) -> float:
    """Evaluate response identity coherence according to Jules' core principles.

    Returns a score between 0.0 (severely violates persona) and 1.0 (fully coherent).
    """
    if not response or not response.strip():
        return 1.0

    violations = 0
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(response):
            violations += 1

    if violations == 0:
        return 1.0
    return max(0.0, 1.0 - (violations * 0.35))
