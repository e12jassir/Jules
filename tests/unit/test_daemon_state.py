"""Unit tests for daemon state management and real-time state publisher."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from jules.daemon.state import (
    DEFAULT_STATE_ICONS,
    DaemonState,
    DaemonStateSnapshot,
    StatePublisher,
    resolve_state_path,
)


def test_daemon_state_enum_variants_and_icons() -> None:
    """Test DaemonState enum variants and their representative icons."""
    expected_variants = {
        DaemonState.IDLE: "🌹",
        DaemonState.LISTENING: "👂",
        DaemonState.THINKING: "🧠",
        DaemonState.SPEAKING: "🗣️",
        DaemonState.AWAITING_PERMISSION: "⚠️",
        DaemonState.DEGRADED: "🥀",
    }

    # Verify all expected variants exist in enum
    assert set(DaemonState) == set(expected_variants.keys())

    # Verify string values match variant names
    for state in DaemonState:
        assert state.value == state.name

    # Verify icons match
    for state, icon in expected_variants.items():
        assert state.icon == icon
        assert DEFAULT_STATE_ICONS[state] == icon


def test_daemon_state_snapshot_schema() -> None:
    """Test DaemonStateSnapshot serialization format and schema."""
    snapshot = DaemonStateSnapshot(
        state=DaemonState.THINKING,
        icon="🧠",
        active_model="llama3.2:3b",
        active_project="Jules",
        last_event="user_query",
        updated_at=1760000000.123,
    )

    data = snapshot.to_dict()
    assert set(data.keys()) == {
        "state",
        "icon",
        "active_model",
        "active_project",
        "last_event",
        "updated_at",
    }
    assert data["state"] == "THINKING"
    assert data["icon"] == "🧠"
    assert data["active_model"] == "llama3.2:3b"
    assert data["active_project"] == "Jules"
    assert data["last_event"] == "user_query"
    assert data["updated_at"] == 1760000000.123

    # Check JSON string serialization
    json_str = snapshot.to_json()
    parsed = json.loads(json_str)
    assert parsed == data

    # Check from_dict deserialization
    recreated = DaemonStateSnapshot.from_dict(parsed)
    assert recreated.state == DaemonState.THINKING
    assert recreated.icon == "🧠"
    assert recreated.active_model == "llama3.2:3b"
    assert recreated.active_project == "Jules"
    assert recreated.last_event == "user_query"
    assert recreated.updated_at == 1760000000.123


def test_daemon_state_snapshot_default_icon() -> None:
    """Test that DaemonStateSnapshot assigns the state's icon by default."""
    snapshot = DaemonStateSnapshot(state=DaemonState.AWAITING_PERMISSION)
    assert snapshot.icon == "⚠️"
    assert snapshot.state == DaemonState.AWAITING_PERMISSION


def test_resolve_state_path_with_explicit_override(tmp_path: Path) -> None:
    """Test that explicit target_path overrides any environment variable."""
    custom_path = tmp_path / "custom.state"
    resolved = resolve_state_path(target_path=custom_path)
    assert resolved == custom_path.resolve()


def test_resolve_state_path_with_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test path resolution when XDG_RUNTIME_DIR is set and accessible."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    resolved = resolve_state_path()
    assert resolved == tmp_path / "jules.state"

    publisher = StatePublisher()
    assert publisher.target_path == tmp_path / "jules.state"


def test_resolve_state_path_fallback_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fallback to ~/.jules/run/jules.state when XDG_RUNTIME_DIR is unset."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    resolved = resolve_state_path()
    assert resolved == Path.home() / ".jules" / "run" / "jules.state"

    publisher = StatePublisher()
    assert publisher.target_path == Path.home() / ".jules" / "run" / "jules.state"


def test_resolve_state_path_fallback_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fallback when XDG_RUNTIME_DIR is set to an inaccessible directory."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/non/existent/runtime/dir/999999")
    resolved = resolve_state_path()
    assert resolved == Path.home() / ".jules" / "run" / "jules.state"

    publisher = StatePublisher()
    assert publisher.target_path == Path.home() / ".jules" / "run" / "jules.state"


def test_state_publisher_atomic_write(tmp_path: Path) -> None:
    """Test atomic file writing using temporary file and os.replace."""
    state_file = tmp_path / "subdir" / "jules.state"
    publisher = StatePublisher(target_path=state_file)

    # Ensure parent dir did not exist beforehand
    assert not state_file.parent.exists()

    with patch("os.replace", wraps=os.replace) as mock_replace:
        published_snapshot = publisher.publish()

        assert mock_replace.called
        src_path, dst_path = mock_replace.call_args[0]
        # src_path is the temporary file in the same directory
        assert Path(src_path).parent == state_file.parent
        assert Path(src_path).name.startswith(f"{state_file.name}.tmp.")
        # dst_path is the final target path
        assert Path(dst_path) == state_file

    # Verify content on disk
    assert state_file.exists()
    content = json.loads(state_file.read_text(encoding="utf-8"))
    assert content["state"] == DaemonState.IDLE.value
    assert content["icon"] == "🌹"
    assert content["updated_at"] == published_snapshot.updated_at


def test_state_publisher_state_transitions_and_updates(tmp_path: Path) -> None:
    """Test update_state, set_active_model, record_event, and generic update."""
    state_file = tmp_path / "jules.state"
    publisher = StatePublisher(
        target_path=state_file,
        initial_state=DaemonState.IDLE,
        active_model="ollama/llama3.2",
        active_project="JulesCore",
    )

    # Initial state
    current = publisher.get_current_state()
    assert current.state == DaemonState.IDLE
    assert current.active_model == "ollama/llama3.2"
    assert current.active_project == "JulesCore"

    # Transition to LISTENING
    s1 = publisher.update_state(DaemonState.LISTENING, last_event="voice_detected")
    assert s1.state == DaemonState.LISTENING
    assert s1.icon == "👂"
    assert s1.last_event == "voice_detected"
    assert s1.active_model == "ollama/llama3.2"

    # Check file on disk
    disk_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert disk_data["state"] == "LISTENING"
    assert disk_data["icon"] == "👂"
    assert disk_data["last_event"] == "voice_detected"

    # Transition to THINKING
    s2 = publisher.update_state(DaemonState.THINKING, last_event="query_processing")
    assert s2.state == DaemonState.THINKING
    assert s2.icon == "🧠"
    assert s2.last_event == "query_processing"

    # Set active model
    s3 = publisher.set_active_model("claude-3-5-sonnet")
    assert s3.active_model == "claude-3-5-sonnet"
    assert publisher.get_current_state().active_model == "claude-3-5-sonnet"

    # Set active project
    s4 = publisher.set_active_project("NewProject")
    assert s4.active_project == "NewProject"
    assert publisher.get_current_state().active_project == "NewProject"

    # Record event
    s5 = publisher.record_event("permission_requested")
    assert s5.last_event == "permission_requested"

    # Transition to AWAITING_PERMISSION
    s6 = publisher.update_state(DaemonState.AWAITING_PERMISSION)
    assert s6.state == DaemonState.AWAITING_PERMISSION
    assert s6.icon == "⚠️"

    # Generic update
    s7 = publisher.update(
        state=DaemonState.DEGRADED,
        icon="🥀",
        last_event="network_error",
    )
    assert s7.state == DaemonState.DEGRADED
    assert s7.icon == "🥀"
    assert s7.last_event == "network_error"

    # Verify latest content on disk matches s7
    final_disk = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_disk["state"] == "DEGRADED"
    assert final_disk["icon"] == "🥀"
    assert final_disk["active_model"] == "claude-3-5-sonnet"
    assert final_disk["active_project"] == "NewProject"
    assert final_disk["last_event"] == "network_error"
    assert final_disk["updated_at"] == s7.updated_at


def test_state_publisher_cleanup(tmp_path: Path) -> None:
    """Test publisher.cleanup() removes the state file safely."""
    state_file = tmp_path / "jules.state"
    publisher = StatePublisher(target_path=state_file)
    publisher.publish()
    assert state_file.exists()

    publisher.cleanup()
    assert not state_file.exists()

    # Calling cleanup again should not raise
    publisher.cleanup()
