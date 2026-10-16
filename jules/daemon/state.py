"""Real-time state publisher for the Jules daemon.

Writes runtime state atomically to /run/user/$UID/jules.state (or fallback)
so external tools (Waybar, Polybar, Hyprpanel, scripts) can monitor Jules
without polling or waking up the main process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import time
from typing import Any


class DaemonState(str, Enum):
    """Execution state of the Jules daemon."""

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    AWAITING_PERMISSION = "AWAITING_PERMISSION"
    DEGRADED = "DEGRADED"

    @property
    def icon(self) -> str:
        """Representative visual icon for status bars and desktop notifications."""
        return DEFAULT_STATE_ICONS[self]


DEFAULT_STATE_ICONS: dict[DaemonState, str] = {
    DaemonState.IDLE: "🌹",
    DaemonState.LISTENING: "👂",
    DaemonState.THINKING: "🧠",
    DaemonState.SPEAKING: "🗣️",
    DaemonState.AWAITING_PERMISSION: "⚠️",
    DaemonState.DEGRADED: "🥀",
}


@dataclass(slots=True)
class DaemonStateSnapshot:
    """Serializable snapshot of the current Jules daemon state."""

    state: DaemonState = DaemonState.IDLE
    icon: str | None = None
    active_model: str = ""
    active_project: str = ""
    last_event: str = ""
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if isinstance(self.state, str) and not isinstance(self.state, DaemonState):
            try:
                self.state = DaemonState(self.state)
            except ValueError:
                pass

        if self.icon is None:
            if isinstance(self.state, DaemonState):
                self.icon = self.state.icon
            else:
                self.icon = DEFAULT_STATE_ICONS.get(DaemonState.IDLE, "🌹")

    def to_dict(self) -> dict[str, Any]:
        """Convert state snapshot to a dictionary."""
        return {
            "state": self.state.value if isinstance(self.state, DaemonState) else str(self.state),
            "icon": self.icon or "🌹",
            "active_model": self.active_model,
            "active_project": self.active_project,
            "last_event": self.last_event,
            "updated_at": self.updated_at,
        }

    def to_json(self) -> str:
        """Serialize state snapshot to JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaemonStateSnapshot:
        """Create a DaemonStateSnapshot from a dictionary."""
        raw_state = data.get("state", DaemonState.IDLE.value)
        try:
            state = DaemonState(raw_state)
        except ValueError:
            state = DaemonState.IDLE

        return cls(
            state=state,
            icon=data.get("icon"),
            active_model=data.get("active_model", ""),
            active_project=data.get("active_project", ""),
            last_event=data.get("last_event", ""),
            updated_at=float(data.get("updated_at", time.time())),
        )

    @classmethod
    def from_json(cls, json_str: str) -> DaemonStateSnapshot:
        """Create a DaemonStateSnapshot from a JSON string."""
        return cls.from_dict(json.loads(json_str))


def resolve_state_path(target_path: Path | str | None = None) -> Path:
    """Resolve the path for the jules.state file.

    1. If target_path is explicitly provided, use it.
    2. If XDG_RUNTIME_DIR is set and is an accessible directory, use $XDG_RUNTIME_DIR/jules.state.
    3. Fallback to ~/.jules/run/jules.state.
    """
    if target_path is not None:
        return Path(target_path).expanduser().resolve()

    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        p = Path(xdg_runtime).expanduser()
        if p.is_dir() and os.access(p, os.W_OK):
            return p / "jules.state"

    return Path.home() / ".jules" / "run" / "jules.state"


class StatePublisher:
    """Atomic state publisher for the Jules daemon."""

    def __init__(
        self,
        target_path: Path | str | None = None,
        initial_state: DaemonState = DaemonState.IDLE,
        active_model: str = "",
        active_project: str = "",
        last_event: str = "initialized",
    ) -> None:
        self.target_path = resolve_state_path(target_path)
        self._current_state = DaemonStateSnapshot(
            state=initial_state,
            active_model=active_model,
            active_project=active_project,
            last_event=last_event,
            updated_at=time.time(),
        )

    def get_current_state(self) -> DaemonStateSnapshot:
        """Return the current daemon state snapshot."""
        return self._current_state

    def publish(self, snapshot: DaemonStateSnapshot | None = None) -> DaemonStateSnapshot:
        """Atomically write the state snapshot to disk."""
        if snapshot is not None:
            self._current_state = snapshot

        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.target_path.with_name(
            f"{self.target_path.name}.tmp.{os.getpid()}.{time.time_ns()}"
        )

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(self._current_state.to_json())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return self._current_state

    def update(
        self,
        state: DaemonState | None = None,
        icon: str | None = None,
        active_model: str | None = None,
        active_project: str | None = None,
        last_event: str | None = None,
    ) -> DaemonStateSnapshot:
        """Update fields and atomically publish the new state."""
        new_state = state if state is not None else self._current_state.state

        if icon is not None:
            new_icon = icon
        elif state is not None:
            new_icon = state.icon if isinstance(state, DaemonState) else DEFAULT_STATE_ICONS.get(DaemonState(state), self._current_state.icon)
        else:
            new_icon = self._current_state.icon

        new_model = active_model if active_model is not None else self._current_state.active_model
        new_project = active_project if active_project is not None else self._current_state.active_project
        new_event = last_event if last_event is not None else self._current_state.last_event

        self._current_state = DaemonStateSnapshot(
            state=new_state,
            icon=new_icon,
            active_model=new_model,
            active_project=new_project,
            last_event=new_event,
            updated_at=time.time(),
        )
        return self.publish()

    def update_state(
        self,
        state: DaemonState,
        icon: str | None = None,
        last_event: str | None = None,
    ) -> DaemonStateSnapshot:
        """Convenience method to transition state."""
        return self.update(state=state, icon=icon, last_event=last_event)

    def set_active_model(self, model_name: str) -> DaemonStateSnapshot:
        """Update active model and publish."""
        return self.update(active_model=model_name)

    def set_active_project(self, project_name: str) -> DaemonStateSnapshot:
        """Update active project and publish."""
        return self.update(active_project=project_name)

    def record_event(self, event_name: str) -> DaemonStateSnapshot:
        """Record the latest event name and publish."""
        return self.update(last_event=event_name)

    def cleanup(self) -> None:
        """Remove state file when shutting down daemon."""
        try:
            if self.target_path.exists():
                self.target_path.unlink()
        except OSError:
            pass
