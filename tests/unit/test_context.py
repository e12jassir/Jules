from __future__ import annotations

import time
from datetime import datetime

import pytest

from jules.core.context import ContextEngine
from jules.core.session import SessionContext


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        del tz
        return cls(2026, 5, 29, 9, 0, 0)


def test_build_returns_debugging_when_last_command_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    monkeypatch.setenv("SHELL", "/bin/zsh")
    session = SessionContext(cwd="/tmp", last_exit_code=1, recent_commands=["pytest"])

    built = ContextEngine.build(session, "fix this")

    assert built.intent == "debugging"
    assert built.project_root is None
    assert built.time_of_day == 9
    assert built.shell == "/bin/zsh"


@pytest.mark.parametrize(
    "recent_commands",
    [
        ["git status", "uv run pytest --help"],
        ["man"],
        ["cat docs/architecture.md"],
    ],
)
def test_build_returns_learning_when_recent_commands_include_learning_signal(
    monkeypatch: pytest.MonkeyPatch,
    recent_commands: list[str],
) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    session = SessionContext(cwd="/tmp", recent_commands=recent_commands)

    built = ContextEngine.build(session, "how does this work?")

    assert built.intent == "learning"


@pytest.mark.parametrize("recent_commands", [["git status"], ["ls", "pytest tests/unit/test_context.py"]])
def test_build_defaults_to_review_when_no_debugging_or_learning_signals(
    monkeypatch: pytest.MonkeyPatch,
    recent_commands: list[str],
) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    session = SessionContext(cwd="/tmp", recent_commands=recent_commands)

    built = ContextEngine.build(session, "review this")

    assert built.intent == "review"


def test_build_finds_nearest_git_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    project_root = tmp_path / "workspace"
    nested = project_root / "src" / "jules"
    nested.mkdir(parents=True)
    (project_root / ".git").mkdir()
    session = SessionContext(cwd=str(nested), recent_commands=["git diff"])

    built = ContextEngine.build(session, "check context")

    assert built.project_root == str(project_root)


def test_build_uses_unknown_shell_when_environment_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    monkeypatch.delenv("SHELL", raising=False)
    session = SessionContext(cwd="/tmp", recent_commands=[])

    built = ContextEngine.build(session, "context")

    assert built.shell == "unknown"


def test_build_completes_under_ten_milliseconds(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("jules.core.context.datetime", FixedDateTime)
    project_root = tmp_path / "repo"
    nested = project_root / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (project_root / ".git").mkdir()
    session = SessionContext(cwd=str(nested), recent_commands=["cat README.md"])

    iterations = 200
    start = time.perf_counter()
    built = None
    for _ in range(iterations):
        built = ContextEngine.build(session, "context")
    elapsed_ms = ((time.perf_counter() - start) * 1000) / iterations

    assert built is not None
    assert built.intent == "learning"
    assert elapsed_ms < 10
