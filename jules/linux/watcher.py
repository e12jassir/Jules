from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
from pathlib import Path

from jules.core.events import EventBus, EventType

logger = logging.getLogger(__name__)

EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
INOTIFY_MAX_USER_WATCHES_PATH = Path("/proc/sys/fs/inotify/max_user_watches")
INOTIFY_MIN_WATCHES = 65536
INOTIFY_FIX_COMMAND = (
    "echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf"
)


@dataclass(slots=True)
class LinuxWatcher:
    """Conservative polling watcher for Phase 1.

    This is not an inotify watcher; snapshots are capped to avoid scanning large
    projects indefinitely during normal terminal use.
    """

    event_bus: EventBus
    current_directory: str
    poll_interval_seconds: float = 1.0
    max_snapshot_files: int = 5000
    _snapshot: dict[Path, int] | None = None
    _baseline_initialized: bool = False
    _running: bool = False

    def initialize(self) -> None:
        self._validate_inotify_limit()
        self._snapshot = self._take_snapshot(Path(self.current_directory))
        self._baseline_initialized = True

    async def start(self) -> None:
        self._validate_inotify_limit()
        self._snapshot = await asyncio.to_thread(
            self._take_snapshot,
            Path(self.current_directory),
        )
        self._baseline_initialized = True
        self._running = True
        while self._running:
            await self.scan_once()
            await asyncio.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def scan_once(self) -> None:
        previous = self._snapshot or {}
        current = await asyncio.to_thread(
            self._take_snapshot,
            Path(self.current_directory),
        )
        self._snapshot = current

        if not self._baseline_initialized:
            self._baseline_initialized = True
            return  # Skip emitting events on the initial baseline scan

        for file_path, modified_at in current.items():
            if previous.get(file_path) != modified_at:
                self.on_file_modified(str(file_path))

        deleted = previous.keys() - current.keys()
        for file_path in deleted:
            self.on_file_modified(str(file_path))

    def on_directory_changed(self, directory: str) -> None:
        if directory == self.current_directory:
            return
        self.current_directory = directory
        self._snapshot = None
        self._baseline_initialized = False
        self.event_bus.emit(EventType.PROJECT_OPENED, {"directory": directory})

    def on_file_modified(self, file_path: str) -> None:
        self.event_bus.emit(EventType.CODING_DETECTED, {"file_path": file_path})

    def _validate_inotify_limit(self) -> None:
        try:
            max_watches = int(
                INOTIFY_MAX_USER_WATCHES_PATH.read_text(encoding="utf-8").strip()
            )
        except (OSError, ValueError):
            logger.warning("Could not read inotify limit from %s", INOTIFY_MAX_USER_WATCHES_PATH)
            return

        if max_watches < INOTIFY_MIN_WATCHES:
            logger.warning(
                "Low inotify limit: %s watches; recommended >=%s. Increase with: %s",
                max_watches,
                INOTIFY_MIN_WATCHES,
                INOTIFY_FIX_COMMAND,
            )

    def _take_snapshot(self, directory: Path) -> dict[Path, int]:
        if not directory.exists() or not directory.is_dir():
            return {}

        snapshot: dict[Path, int] = {}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRECTORIES]
            root_path = Path(root)
            for f in files:
                if len(snapshot) >= self.max_snapshot_files:
                    logger.warning(
                        "Polling snapshot for %s reached max_snapshot_files=%s; remaining files skipped",
                        directory,
                        self.max_snapshot_files,
                    )
                    return snapshot
                path = root_path / f
                try:
                    snapshot[path] = path.stat().st_mtime_ns
                except OSError:
                    logger.warning("Could not stat watched file %s", path)
        return snapshot
