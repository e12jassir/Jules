from __future__ import annotations

import asyncio
import logging

from jules.core.events import EventBus, EventType
from jules.core.session import SessionContext
from jules.linux import watcher as watcher_module
from jules.linux.watcher import LinuxWatcher


def test_watcher_initialize_warns_on_low_inotify_limit(tmp_path, caplog, monkeypatch) -> None:
    limit_file = tmp_path / "max_user_watches"
    limit_file.write_text("8192", encoding="utf-8")
    monkeypatch.setattr(watcher_module, "INOTIFY_MAX_USER_WATCHES_PATH", limit_file)
    bus = EventBus(session=SessionContext(cwd="/project"))
    watcher = LinuxWatcher(
        event_bus=bus,
        current_directory=str(tmp_path),
    )

    with caplog.at_level(logging.WARNING):
        watcher.initialize()

    assert "Low inotify limit: 8192 watches" in caplog.text
    assert "echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf" in caplog.text


def test_watcher_emits_project_and_coding_events(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd="/old"))
    watcher = LinuxWatcher(event_bus=bus, current_directory="/old")

    watcher.on_directory_changed("/new")
    watcher.on_file_modified("/new/main.py")

    assert bus.session.cwd == "/new"
    assert bus.runtime.last_activity_at is not None


async def test_watcher_detects_file_modification(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    watched_file = tmp_path / "main.py"
    watched_file.write_text("print('before')", encoding="utf-8")
    bus = EventBus(session=SessionContext(cwd=str(tmp_path)))
    observed: list[dict] = []
    bus.subscribe(EventType.CODING_DETECTED, observed.append)
    watcher = LinuxWatcher(
        event_bus=bus,
        current_directory=str(tmp_path),
    )
    watcher.initialize()

    import time
    time.sleep(0.01)  # Ensure filesystem mtime resolution barrier

    watched_file.write_text("print('after')", encoding="utf-8")
    await watcher.scan_once()

    # Wait for the background thread (from asyncio.to_thread) to complete
    for _ in range(10):
        if {"file_path": str(watched_file)} in observed:
            break
        await asyncio.sleep(0.05)
    
    assert {"file_path": str(watched_file)} in observed


async def test_watcher_detects_first_file_after_empty_baseline(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd=str(tmp_path)))
    observed: list[dict] = []
    bus.subscribe(EventType.CODING_DETECTED, observed.append)
    watcher = LinuxWatcher(
        event_bus=bus,
        current_directory=str(tmp_path),
    )
    watcher.initialize()

    watched_file = tmp_path / "main.py"
    watched_file.write_text("print('created')", encoding="utf-8")
    await watcher.scan_once()

    # Wait for the async dispatch to complete
    for _ in range(20):
        if {"file_path": str(watched_file)} in observed:
            break
        await asyncio.sleep(0.01)

    assert {"file_path": str(watched_file)} in observed


def test_watcher_excludes_large_generated_directories(tmp_path) -> None:
    node_file = tmp_path / "node_modules" / "pkg" / "index.js"
    node_file.parent.mkdir(parents=True)
    node_file.write_text("generated", encoding="utf-8")
    source_file = tmp_path / "main.py"
    source_file.write_text("print('ok')", encoding="utf-8")
    watcher = LinuxWatcher(event_bus=EventBus(), current_directory=str(tmp_path))

    snapshot = watcher._take_snapshot(tmp_path)

    assert source_file in snapshot
    assert node_file not in snapshot


def test_watcher_caps_polling_snapshot_size(tmp_path, caplog) -> None:
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text("print('ok')", encoding="utf-8")
    watcher = LinuxWatcher(
        event_bus=EventBus(),
        current_directory=str(tmp_path),
        max_snapshot_files=2,
    )

    snapshot = watcher._take_snapshot(tmp_path)

    assert len(snapshot) == 2
    assert "max_snapshot_files=2" in caplog.text
