from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SessionContext:
    cwd: str
    last_exit_code: int = 0
    recent_commands: list[str] = field(default_factory=list)
