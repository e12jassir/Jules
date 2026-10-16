"""Contextual Initiative Engine ('El Fantasma en la Shell').

Monitors user actions (shell commands, file edits, project resumes)
and proactively offers assistance when high friction is detected,
strictly adhering to the Golden Rule: Jules never interrupts twice
for the same reason in the same session.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import inspect
import logging
from pathlib import Path
import shutil
import time
from typing import Any, Awaitable, Callable

from jules.core.events import EventBus, EventType
from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Episode
from jules.memory.persistent import PersistentMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and Models
# ---------------------------------------------------------------------------


class InitiativeTriggerType(str, Enum):
    SHELL_FRICTION = "shell_friction"
    PROJECT_RESUMED = "project_resumed"
    STALL_DETECTED = "stall_detected"


@dataclass(slots=True)
class InitiativeIntervention:
    """Proactive intervention suggested by Jules."""

    trigger_type: InitiativeTriggerType
    reason: str
    message: str
    prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type.value,
            "reason": self.reason,
            "message": self.message,
            "prompt": self.prompt,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class InitiativeEvent:
    """Event emitted on EventBus when an initiative is triggered."""

    intervention: InitiativeIntervention
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention": self.intervention.to_dict(),
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Cooldown Registry (The Golden Rule)
# ---------------------------------------------------------------------------


class CooldownRegistry:
    """Strictly enforces the Golden Rule:
    'Jules tiene estrictamente prohibido interrumpir dos veces por la misma
    razón en una misma sesión.'
    """

    def __init__(self) -> None:
        self._interventions: set[tuple[str, str]] = set()

    def can_trigger(self, session_id: str, trigger_reason: str) -> bool:
        """Return True if (session_id, trigger_reason) has not been triggered yet in this session."""
        return (session_id, trigger_reason) not in self._interventions

    def record(self, session_id: str, trigger_reason: str) -> None:
        """Record an intervention to prevent future duplicate triggers in the same session."""
        self._interventions.add((session_id, trigger_reason))

    def check_and_record(self, session_id: str, trigger_reason: str) -> bool:
        """Atomic check and record. Returns True if allowed (and records it), False if on cooldown."""
        if not self.can_trigger(session_id, trigger_reason):
            return False
        self.record(session_id, trigger_reason)
        return True

    def reset(self, session_id: str | None = None) -> None:
        """Reset records for a specific session or all sessions."""
        if session_id is None:
            self._interventions.clear()
        else:
            self._interventions = {item for item in self._interventions if item[0] != session_id}


# ---------------------------------------------------------------------------
# Initiative Engine
# ---------------------------------------------------------------------------


class InitiativeEngine:
    """Contextual Initiative Engine ('El Fantasma en la Shell').

    Detects shell errors, project resumes, and prolonged stalls, consulting
    memory to offer helpful suggestions without being intrusive.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        episodic_memory: EpisodicMemory | None = None,
        persistent_memory: PersistentMemory | None = None,
        memory_engine: Any | None = None,
        cooldown_registry: CooldownRegistry | None = None,
        desktop_notifier: Callable[[str, str], Awaitable[bool] | bool] | None = None,
        voice_hook: Callable[[str], Awaitable[None] | None] | None = None,
        friction_window_seconds: float = 180.0,  # 3 minutes
        project_resumed_threshold_days: float = 14.0,  # 14 days
        stall_threshold_seconds: float = 7200.0,  # 2 hours
    ) -> None:
        self.event_bus = event_bus
        self.episodic_memory = episodic_memory
        self.persistent_memory = persistent_memory
        self.memory_engine = memory_engine
        self.cooldown_registry = cooldown_registry or CooldownRegistry()
        self.desktop_notifier = desktop_notifier
        self.voice_hook = voice_hook

        self.friction_window_seconds = friction_window_seconds
        self.project_resumed_threshold_days = project_resumed_threshold_days
        self.stall_threshold_seconds = stall_threshold_seconds

        # Internal state tracking
        self._shell_failures_by_session: dict[str, list[dict[str, Any]]] = {}
        self._file_modifications: dict[str, dict[str, Any]] = {}
        self._recent_failures: list[dict[str, Any]] = []

        if self.event_bus is not None:
            self.event_bus.subscribe(EventType.PROJECT_OPENED, self._handle_bus_project_opened)
            self.event_bus.subscribe(EventType.CODING_DETECTED, self._handle_bus_coding_detected)

    # -----------------------------------------------------------------------
    # Trigger 1: Shell Friction
    # -----------------------------------------------------------------------

    async def on_shell_event(
        self,
        cmd: str,
        exit_code: int,
        cwd: str,
        session_id: str = "default",
        timestamp: float | None = None,
    ) -> InitiativeIntervention | None:
        """Process shell command completion event.

        Triggers initiative check if 2 consecutive non-zero exit codes occur within 3 minutes.
        """
        now_ts = timestamp if timestamp is not None else time.time()
        cmd_clean = cmd.strip()

        if exit_code == 0:
            # Command succeeded; reset failure streak for this session
            self._shell_failures_by_session[session_id] = []
            return None

        # Record failure
        session_failures = self._shell_failures_by_session.setdefault(session_id, [])
        # Prune old failures
        cutoff = now_ts - self.friction_window_seconds
        session_failures = [f for f in session_failures if f["timestamp"] >= cutoff]
        session_failures.append({
            "cmd": cmd_clean,
            "exit_code": exit_code,
            "cwd": cwd,
            "timestamp": now_ts,
        })
        self._shell_failures_by_session[session_id] = session_failures
        self._recent_failures.append({"cmd": cmd_clean, "timestamp": now_ts})

        # Check consecutive failure condition: at least 2 failures within window
        if len(session_failures) < 2:
            return None

        # Enforce Golden Rule
        reason = f"shell_friction:{cmd_clean}"
        if not self.cooldown_registry.can_trigger(session_id, reason):
            logger.debug("Silenced shell friction for '%s' due to CooldownRegistry", reason)
            return None

        self.cooldown_registry.record(session_id, reason)

        # Query episodic/persistent memory for past troubleshooting
        past_episode = await self._retrieve_past_troubleshooting(cmd_clean)

        if past_episode is not None and past_episode.solution:
            proj_name = getattr(getattr(past_episode, "context", None), "project", None) or Path(cwd).name
            message = (
                f"Esteban, ese comando acaba de fallar igual que cuando configuramos {proj_name}. "
                f"En esa ocasión lo resolvimos con: {past_episode.solution}. ¿Quieres que te ayude a aplicarlo?"
            )
            prompt = (
                f"El comando '{cmd_clean}' falló dos veces seguidas con código {exit_code}. "
                f"Episodio previo ({past_episode.id}): problema '{past_episode.problem}', solución '{past_episode.solution}'."
            )
        else:
            message = (
                f"Esteban, el comando '{cmd_clean}' ha fallado {len(session_failures)} veces seguidas. "
                "¿Quieres que analicemos el error juntos?"
            )
            prompt = f"El comando '{cmd_clean}' falló {len(session_failures)} veces seguidas con código {exit_code}."

        intervention = InitiativeIntervention(
            trigger_type=InitiativeTriggerType.SHELL_FRICTION,
            reason=reason,
            message=message,
            prompt=prompt,
            metadata={
                "cmd": cmd_clean,
                "exit_code": exit_code,
                "cwd": cwd,
                "failures_count": len(session_failures),
                "past_episode_id": past_episode.id if past_episode else None,
            },
        )

        await self._dispatch_intervention(intervention)
        return intervention

    # -----------------------------------------------------------------------
    # Trigger 2: Project Resumed
    # -----------------------------------------------------------------------

    async def on_project_opened(
        self,
        directory: str,
        project: str | None = None,
        session_id: str = "default",
        current_time: datetime | None = None,
    ) -> InitiativeIntervention | None:
        """Process project opened event.

        If last episode for this project is > 14 days old, offer an executive 1-line recap.
        """
        now = current_time or datetime.now(timezone.utc)
        proj_name = project or Path(directory).name
        reason = f"project_resumed:{proj_name}"

        if not self.cooldown_registry.can_trigger(session_id, reason):
            return None

        latest_episode = await self._get_latest_episode_for_project(proj_name, directory)
        if latest_episode is None:
            return None

        # Calculate age in days
        ep_timestamp = getattr(latest_episode, "timestamp", None)
        if not isinstance(ep_timestamp, datetime):
            return None

        if ep_timestamp.tzinfo is None:
            ep_timestamp = ep_timestamp.replace(tzinfo=timezone.utc)
        age_days = (now - ep_timestamp).total_seconds() / 86400.0

        if age_days <= self.project_resumed_threshold_days:
            return None

        self.cooldown_registry.record(session_id, reason)

        status = latest_episode.solution or latest_episode.problem or latest_episode.process or "última sesión registrada"
        message = f"Retomando {proj_name}: la última sesión ({int(age_days)} días atrás) quedó en: {status}."
        prompt = (
            f"El usuario retomó el proyecto {proj_name} después de {age_days:.1f} días. "
            f"Último episodio: {latest_episode.problem} -> {latest_episode.solution}"
        )

        intervention = InitiativeIntervention(
            trigger_type=InitiativeTriggerType.PROJECT_RESUMED,
            reason=reason,
            message=message,
            prompt=prompt,
            metadata={
                "project": proj_name,
                "directory": directory,
                "age_days": age_days,
                "last_episode_id": latest_episode.id,
            },
        )

        await self._dispatch_intervention(intervention)
        return intervention

    # -----------------------------------------------------------------------
    # Trigger 3: Prolonged Stall Detection
    # -----------------------------------------------------------------------

    def on_file_modified(self, file_path: str, timestamp: float | None = None) -> None:
        """Record file modification timestamp for stall detection."""
        now_ts = timestamp if timestamp is not None else time.time()
        if file_path not in self._file_modifications:
            self._file_modifications[file_path] = {
                "first_modified_at": now_ts,
                "last_modified_at": now_ts,
                "count": 1,
            }
        else:
            rec = self._file_modifications[file_path]
            rec["last_modified_at"] = now_ts
            rec["count"] += 1

    async def check_stall(
        self,
        session_id: str = "default",
        current_time: float | None = None,
    ) -> InitiativeIntervention | None:
        """Check if any file has been modified for longer than the stall threshold with test failures."""
        now_ts = current_time if current_time is not None else time.time()

        for file_path, rec in list(self._file_modifications.items()):
            elapsed = now_ts - rec["first_modified_at"]
            if elapsed < self.stall_threshold_seconds:
                continue

            # Check if there have been failures during this edit cycle
            failures_during_stall = [
                f for f in self._recent_failures if f["timestamp"] >= rec["first_modified_at"]
            ]
            if not failures_during_stall:
                continue

            reason = f"stall_detected:{file_path}"
            if not self.cooldown_registry.can_trigger(session_id, reason):
                continue

            self.cooldown_registry.record(session_id, reason)
            filename = Path(file_path).name
            minutes = max(1, int(elapsed // 60))
            message = (
                f"Llevas más de {minutes} minutos trabajando en {filename} con varios fallos de prueba. "
                "¿Quieres que analicemos el problema juntos para desbloquearlo?"
            )
            prompt = (
                f"Atasco prolongado detectado en {file_path} durante {elapsed:.0f}s "
                f"con {len(failures_during_stall)} errores de terminal/test."
            )

            intervention = InitiativeIntervention(
                trigger_type=InitiativeTriggerType.STALL_DETECTED,
                reason=reason,
                message=message,
                prompt=prompt,
                metadata={
                    "file_path": file_path,
                    "elapsed_seconds": elapsed,
                    "failure_count": len(failures_during_stall),
                },
            )

            await self._dispatch_intervention(intervention)
            return intervention

        return None

    # -----------------------------------------------------------------------
    # Notification & Dispatching
    # -----------------------------------------------------------------------

    async def notify_desktop(self, title: str, message: str) -> bool:
        """Gracefully send a desktop notification using notify-send if available."""
        if self.desktop_notifier is not None:
            try:
                res = self.desktop_notifier(title, message)
                if inspect.isawaitable(res):
                    return bool(await res)
                return bool(res)
            except Exception as exc:
                logger.warning("Custom desktop notifier failed: %s", exc)
                return False

        notify_send_bin = shutil.which("notify-send")
        if not notify_send_bin:
            logger.debug("notify-send not found on system; desktop notification skipped.")
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                notify_send_bin,
                title,
                message,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            returncode = await proc.wait()
            if isinstance(returncode, int):
                return returncode == 0
            return getattr(proc, "returncode", 1) == 0
        except Exception as exc:
            logger.warning("Failed executing notify-send: %s", exc)
            return False

    async def _dispatch_intervention(self, intervention: InitiativeIntervention) -> None:
        """Emit initiative event to EventBus, send desktop notification, and trigger voice hook."""
        # 1. Emit to EventBus
        if self.event_bus is not None:
            try:
                self.event_bus.emit(EventType.INITIATIVE_TRIGGERED, intervention.to_dict())
                await asyncio.sleep(0.01)
            except Exception as exc:
                logger.warning("Failed emitting INITIATIVE_TRIGGERED to EventBus: %s", exc)

        # 2. Desktop notification
        try:
            await self.notify_desktop("Jules Proactive", intervention.message)
        except Exception as exc:
            logger.warning("Failed sending desktop notification: %s", exc)

        # 3. Voice hook (if configured)
        if self.voice_hook is not None:
            try:
                res = self.voice_hook(intervention.message)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                logger.warning("Failed calling voice hook: %s", exc)

    # -----------------------------------------------------------------------
    # Memory Retrieval Helpers
    # -----------------------------------------------------------------------

    async def _retrieve_past_troubleshooting(self, cmd: str) -> Episode | None:
        """Query memory subsystems for past troubleshooting episodes related to the command."""
        # 1. Try MemoryEngine if available
        if self.memory_engine is not None and hasattr(self.memory_engine, "retrieve_async"):
            try:
                res = self.memory_engine.retrieve_async(cmd, limit=1)
                episodes = await res if inspect.isawaitable(res) else res
                if episodes:
                    return episodes[0]
            except Exception as exc:
                logger.debug("MemoryEngine retrieve_async failed: %s", exc)

        # 2. Try EpisodicMemory + PersistentMemory
        if self.episodic_memory is not None and hasattr(self.episodic_memory, "retrieve_async"):
            try:
                # If vector_dimension is present, dummy or mock
                if hasattr(self.episodic_memory, "vector_dimension"):
                    vector = [0.0] * self.episodic_memory.vector_dimension
                    res = self.episodic_memory.retrieve_async(vector, limit=1)
                else:
                    res = self.episodic_memory.retrieve_async(cmd, limit=1)

                episode_ids = await res if inspect.isawaitable(res) else res
                if episode_ids and self.persistent_memory is not None:
                    get_res = self.persistent_memory.get_many_async(episode_ids)
                    episodes = await get_res if inspect.isawaitable(get_res) else get_res
                    if episodes:
                        return episodes[0]
            except Exception as exc:
                logger.debug("EpisodicMemory retrieve_async failed: %s", exc)

        # 3. Fallback to PersistentMemory search
        if self.persistent_memory is not None and hasattr(self.persistent_memory, "list_all_episodes_async"):
            try:
                res = self.persistent_memory.list_all_episodes_async()
                all_eps = await res if inspect.isawaitable(res) else res
                if isinstance(all_eps, list):
                    first_word = cmd.split()[0] if cmd else ""
                    for ep in reversed(all_eps):
                        prob = getattr(ep, "problem", "") or ""
                        sol = getattr(ep, "solution", "") or ""
                        if sol and (first_word in prob or first_word in sol or cmd in prob):
                            return ep
            except Exception as exc:
                logger.debug("PersistentMemory fallback search failed: %s", exc)

        return None

    async def _get_latest_episode_for_project(
        self,
        project: str,
        directory: str,
    ) -> Episode | None:
        """Find the most recent episode for a given project or directory."""
        if self.persistent_memory is None:
            return None

        # 1. Fallback to listing episodes (supports mocks and memory lists)
        if hasattr(self.persistent_memory, "list_all_episodes_async"):
            try:
                res = self.persistent_memory.list_all_episodes_async()
                all_eps = await res if inspect.isawaitable(res) else res
                if isinstance(all_eps, list):
                    matching = [
                        ep for ep in all_eps
                        if hasattr(ep, "context") and ep.context and (
                            getattr(ep.context, "project", None) == project
                            or getattr(ep.context, "directory", None) == directory
                            or Path(getattr(ep.context, "directory", "")).name == project
                        )
                    ]
                    if matching:
                        matching.sort(key=lambda ep: getattr(ep, "timestamp", 0), reverse=True)
                        return matching[0]
            except Exception as exc:
                logger.debug("PersistentMemory.list_all_episodes_async failed: %s", exc)

        # 2. Check dedicated query method if available
        if hasattr(self.persistent_memory, "get_latest_episode_for_project"):
            try:
                res = self.persistent_memory.get_latest_episode_for_project(project)
                ep = await res if inspect.isawaitable(res) else res
                if isinstance(ep, Episode):
                    return ep
            except Exception as exc:
                logger.debug("PersistentMemory.get_latest_episode_for_project failed: %s", exc)

        return None

    # -----------------------------------------------------------------------
    # EventBus Handlers
    # -----------------------------------------------------------------------

    async def _handle_bus_project_opened(self, payload: dict[str, Any]) -> None:
        directory = payload.get("directory")
        if directory:
            project = payload.get("project")
            await self.on_project_opened(directory=directory, project=project)

    def _handle_bus_coding_detected(self, payload: dict[str, Any]) -> None:
        file_path = payload.get("file_path")
        if file_path:
            self.on_file_modified(file_path=file_path)
