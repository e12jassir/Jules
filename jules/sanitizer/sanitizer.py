from __future__ import annotations

from dataclasses import dataclass
import logging
import re


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SanitizeResult:
    is_safe: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class _PatternRule:
    category: str
    pattern: re.Pattern[str]


# Pattern evaluation order is intentional and MUST NOT be changed without updating tests.
# Rules are evaluated in declaration order; the FIRST matching rule determines `reason`.
# Order rationale:
#   1. export_secret  — shell export statements (most explicit, check first)
#   2. assignment_secret — generic key=value assignments
#   3. bearer_token   — HTTP Authorization headers
#   4-9. provider-specific prefixes (OpenAI, Google, GitHub, Slack)
#   10. credentialed_url, private_key — structural formats
SENSITIVE_PATTERNS: tuple[_PatternRule, ...] = (
    _PatternRule(
        category="export_secret",
        pattern=re.compile(r"(?i)export\s+\w*(key|token|secret|pass)\w*\s*="),
    ),
    _PatternRule(
        category="assignment_secret",
        pattern=re.compile(
            r"(?i)(?<![A-Za-z])(api[_-]?key|token|secret|password|passwd|pwd)\b\s*[=:]\s*\S+"
        ),
    ),
    _PatternRule(
        category="bearer_token",
        pattern=re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    ),
    _PatternRule(
        category="openai_key",
        pattern=re.compile(r"sk-[A-Za-z0-9]{20,}"),
    ),
    _PatternRule(
        category="google_key",
        pattern=re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    ),
    _PatternRule(
        category="github_token",
        pattern=re.compile(r"ghp_[A-Za-z0-9]{36}"),
    ),
    _PatternRule(
        category="slack_token",
        pattern=re.compile(r"xox[baprs]-[A-Za-z0-9]{10,}-[A-Za-z0-9\-]+"),
    ),
    _PatternRule(
        category="credentialed_url",
        pattern=re.compile(r"https?://[^@\s]+:[^@\s]+@"),
    ),
    _PatternRule(
        category="private_key",
        pattern=re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----"),
    ),
)


class Sanitizer:
    @staticmethod
    def check(text: str) -> SanitizeResult:
        for rule in SENSITIVE_PATTERNS:
            if rule.pattern.search(text):
                logger.info("sanitizer rejected input category=%s", rule.category)
                return SanitizeResult(is_safe=False, reason=rule.category)
        return SanitizeResult(is_safe=True, reason=None)
