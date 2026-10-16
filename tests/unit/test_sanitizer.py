from __future__ import annotations

import logging
import os
import time

import pytest

from jules.sanitizer import SanitizeResult, Sanitizer


def test_check_returns_safe_contract_for_benign_text() -> None:
    result = Sanitizer.check("hello team, nothing sensitive here")

    assert isinstance(result, SanitizeResult)
    assert result.is_safe is True
    assert result.reason is None


@pytest.mark.parametrize(
    ("text", "expected_reason"),
    [
        ("api_key=abc123", "assignment_secret"),
        ("db_password=supersecret", "assignment_secret"),  # regression R2-1: _ prefix must match
        ("Authorization: Bearer abcDEF123._-+/==", "bearer_token"),
        ("sk-abcdefghijklmnopqrstuvwxyzABCDE", "openai_key"),
        ("sk-proj-abc123DEF456ghi789jkl012_XYZ-foo", "openai_key"),
        ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "openai_key"),
        ("sk-admin-abcdefghijklmnopqrstuvwxyz123", "openai_key"),
        ("AIza" + "A" * 35, "google_key"),
        ("ghp_" + "A" * 36, "github_token"),
        ("xoxb-1234567890-abcde", "slack_token"),
        ("AKIAIOSFODNN7EXAMPLE", "aws_key"),
        ("ASIAIOSFODNN7EXAMPLE", "aws_key"),
        ("ABIA1234567890ABCDEF", "aws_key"),
        ("ACCA1234567890ABCDEF", "aws_key"),
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "jwt_token",
        ),
        ("export SECRET_TOKEN=my-secret", "export_secret"),
        ("https://user:pass@example.com/path", "credentialed_url"),
        ("-----BEGIN PRIVATE KEY-----", "private_key"),
        ("-----BEGIN RSA PRIVATE KEY-----", "private_key"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----", "private_key"),
        ("-----BEGIN EC PRIVATE KEY-----", "private_key"),
        ("bearer abcDEF123._-+/==", "bearer_token"),
    ],
)
def test_check_detects_canonical_sensitive_patterns(
    text: str, expected_reason: str
) -> None:
    result = Sanitizer.check(text)

    assert result.is_safe is False
    assert result.reason == expected_reason


# NOTE: 'next_token=page2' matches assignment_secret since 'token' preceded by '_' is allowed
# by the (?<![A-Za-z]) lookbehind. This is an accepted tradeoff: the pattern prioritises
# catching real secrets (db_password, app_token) over ambiguous pagination cursors.
# Document, do not suppress.
@pytest.mark.parametrize(
    "text",
    [
        "d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2",  # hash-like
        "123e4567-e89b-12d3-a456-426614174000",  # UUID
        "QmFzZTY0RW5jb2RlZEJ1dE5vdEFTZWNyZXQ=",  # benign base64-like
        "THIS_IS_A_REALLY_LONG_FUNCTION_IDENTIFIER_1234567890",
        "from mymodule import very_long_identifier_name",
        "git commit -m 'refactor parser and clean imports'",
        "A" * 32,  # generic long token should remain allowed in PR1
        "tokenize=true",
    ],
)
def test_check_avoids_false_positives_for_generic_tokens(text: str) -> None:
    result = Sanitizer.check(text)

    assert result.is_safe is True
    assert result.reason is None


def test_check_logs_category_only_without_secret_leakage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_value = "super-sensitive-value-123"
    text = f"please use api_key={secret_value} for this request"

    with caplog.at_level(logging.INFO, logger="jules.sanitizer.sanitizer"):
        result = Sanitizer.check(text)

    assert result.is_safe is False
    assert result.reason == "assignment_secret"
    assert caplog.records
    assert "assignment_secret" in caplog.text
    assert secret_value not in caplog.text
    assert "api_key=" not in caplog.text
    assert text not in caplog.text


@pytest.mark.parametrize(
    ("text", "expected_reason"),
    [
        (
            "metadata before key\n"
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvAIBADANBgkqhkiG9w0BAQEFAASC\n"
            "-----END PRIVATE KEY-----",
            "private_key",
        ),
        (
            "first line\nsecond line\npassword=correct-horse-battery-staple",
            "assignment_secret",
        ),
    ],
)
def test_check_detects_multiline_and_final_line_secrets(
    text: str, expected_reason: str
) -> None:
    result = Sanitizer.check(text)

    assert result.is_safe is False
    assert result.reason == expected_reason


def test_check_reports_deterministic_category_for_multiple_secrets() -> None:
    text = "Authorization: Bearer abcDEF123._-+/==\napi_key=secret-value"

    result = Sanitizer.check(text)

    assert result.is_safe is False
    assert result.reason == "assignment_secret"


def test_check_processes_one_megabyte_input_under_local_guardrail() -> None:
    payload = ("safe payload line with ordinary words and numbers 12345\n" * 20_000)[
        : 1_048_576
    ]
    threshold_seconds = 0.50 if os.environ.get("CI") else 0.10

    result = Sanitizer.check(payload)
    timings = []
    for _ in range(3):
        start = time.perf_counter()
        result = Sanitizer.check(payload)
        timings.append(time.perf_counter() - start)

    assert result.is_safe is True
    assert result.reason is None
    assert min(timings) < threshold_seconds


def test_check_detects_secret_embedded_at_end_of_large_input_within_threshold() -> None:
    safe_padding = "safe payload line with ordinary words and numbers 12345\n" * 18_600
    secret_line = "sk-" + "A" * 24  # valid openai_key pattern
    payload = (safe_padding + secret_line)[:1_048_576]
    assert secret_line in payload  # guard: secret must survive the slice
    threshold_seconds = 0.50 if os.environ.get("CI") else 0.10

    timings = []
    for _ in range(3):
        start = time.perf_counter()
        result = Sanitizer.check(payload)
        timings.append(time.perf_counter() - start)

    assert result.is_safe is False
    assert result.reason == "openai_key"
    assert min(timings) < threshold_seconds


def test_check_processes_near_miss_slack_prefix_under_threshold() -> None:
    # Near-miss: starts with slack prefix but never completes a valid token.
    # Exercises regex engine on a pattern that partially matches then fails.
    # Newline separator ensures no cross-iteration boundary matches.
    near_miss = ("xoxb-" + "A" * 50 + "\n") * 1_000
    threshold_seconds = 0.50 if os.environ.get("CI") else 0.10

    timings = []
    for _ in range(3):
        start = time.perf_counter()
        result = Sanitizer.check(near_miss)
        timings.append(time.perf_counter() - start)

    assert result.is_safe is True  # no second dash-separated segment: pattern requires xox?-{10,}-{1,}
    assert min(timings) < threshold_seconds


def test_check_detects_modern_openai_and_anthropic_tokens() -> None:
    tokens = [
        "sk-proj-abcDEF1234567890_-xyzABCDEF123456",
        "sk-ant-api03-abcdefgHIJKLMN1234567890_-xyz",
        "sk-admin-AbCdEfGhIjKlMnOpQrStUvWxYz123456",
    ]
    for token in tokens:
        res = Sanitizer.check(f"Here is my key: {token}")
        assert res.is_safe is False
        assert res.reason == "openai_key"


def test_check_detects_various_private_key_headers() -> None:
    headers = [
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN ENCRYPTED PRIVATE KEY-----",
    ]
    for h in headers:
        text = f"{h}\nProc-Type: 4,ENCRYPTED\nDEK-Info: AES-128-CBC,...\n"
        res = Sanitizer.check(text)
        assert res.is_safe is False
        assert res.reason == "private_key"


def test_check_detects_aws_key_prefixes() -> None:
    keys = [
        "AKIAIOSFODNN7EXAMPLE",
        "ABIA1234567890ABCDEF",
        "ACCA1234567890ABCDEF",
        "ASIAIOSFODNN7EXAMPLE",
    ]
    for k in keys:
        res = Sanitizer.check(f"AWS credentials: access_key={k}")
        assert res.is_safe is False
        # If in access_key= it can match assignment_secret or aws_key depending on prefix.
        # But standalone or in text without assignment keyword:
        res_standalone = Sanitizer.check(f"connect with {k} to S3")
        assert res_standalone.is_safe is False
        assert res_standalone.reason == "aws_key"


def test_check_detects_jwt_tokens() -> None:
    jwts = [
        # Full standard 3-part JWT
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        # Unsigned 2-part with trailing dot
        "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.",
    ]
    for token in jwts:
        res = Sanitizer.check(f"user session: {token}")
        assert res.is_safe is False
        assert res.reason == "jwt_token"
