from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re

from jules.core.session import SessionContext


@dataclass(slots=True)
class BuiltContext:
    project_root: str | None
    intent: str
    time_of_day: int


class ContextEngine:
    @staticmethod
    def build(session: SessionContext, user_input: str) -> BuiltContext:
        del user_input
        project_root = ContextEngine._find_project_root(session.cwd)
        intent = ContextEngine._infer_intent(session)
        time_of_day = datetime.now().hour
        return BuiltContext(
            project_root=project_root,
            intent=intent,
            time_of_day=time_of_day,
        )

    @staticmethod
    def _find_project_root(cwd: str) -> str | None:
        current = Path(os.path.abspath(os.path.expanduser(cwd)))
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                return str(candidate)
        return None

    @staticmethod
    def _infer_intent(session: SessionContext) -> str:
        if session.last_exit_code != 0:
            return "debugging"

        for command in session.recent_commands:
            tokens = command.strip().lower().split()
            if not tokens:
                continue
            if tokens[0] == "man":
                return "learning"
            if any(t in ("help", "--help") or t.endswith(".md") for t in tokens):
                return "learning"

        return "review"
