"""OS Action Tools ('Brazos y Manos') for Jules.

Provides zero-overhead system queries and action reflexes for Linux
(Arch Linux, Hyprland, PipeWire/WirePlumber, playerctl, xdg-open),
governed by PermissionGate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from typing import TYPE_CHECKING, Any

from jules.core.permissions import Action

if TYPE_CHECKING:
    from jules.core.permissions import PermissionGate

logger = logging.getLogger(__name__)

VALID_MEDIA_ACTIONS: frozenset[str] = frozenset(
    {"play", "pause", "play-pause", "next", "previous", "stop"}
)


def _read_proc_meminfo() -> dict[str, int]:
    """Parse /proc/meminfo into a dict of kB values."""
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_str = parts[1].strip().split()[0]
                    if val_str.isdigit():
                        info[key] = int(val_str)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed reading /proc/meminfo: %s", exc)
    return info


def _read_proc_loadavg() -> tuple[float, float, float]:
    """Parse /proc/loadavg into (1min, 5min, 15min) load averages."""
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            parts = f.read().split()
            if len(parts) >= 3:
                return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed reading /proc/loadavg: %s", exc)
    return (0.0, 0.0, 0.0)


async def _get_wpctl_volume() -> dict[str, Any]:
    """Query current audio sink volume via wpctl."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "wpctl",
            "get-volume",
            "@DEFAULT_AUDIO_SINK@",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=0.5)
        out = stdout.decode("utf-8").strip()
        muted = "[MUTED]" in out
        match = re.search(r"Volume:\s+([0-9.]+)", out)
        if match:
            vol_val = float(match.group(1))
            pct = int(round(vol_val * 100))
            vol_str = f"{pct}%"
            if muted:
                vol_str += " [MUTED]"
            return {"volume": vol_str, "percent": pct, "muted": muted, "raw": out}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed querying wpctl volume: %s", exc)
    return {"volume": "desconocido", "percent": 0, "muted": False, "raw": ""}


async def _get_playerctl_track() -> str:
    """Query active media track via playerctl metadata."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "playerctl",
            "metadata",
            "--format",
            "{{ artist }} - {{ title }}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=0.5)
        track = stdout.decode("utf-8").strip()
        if track and track != "-":
            return track
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed querying playerctl: %s", exc)
    return ""


async def _get_hyprctl_window() -> dict[str, str]:
    """Query active window information via hyprctl."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "hyprctl",
            "activewindow",
            "-j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=0.5)
        raw = stdout.decode("utf-8").strip()
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {
                    "title": data.get("title", "") or "",
                    "class": data.get("class", "") or "",
                }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed querying hyprctl activewindow: %s", exc)
    return {"title": "", "class": ""}


async def get_system_status(gate: PermissionGate | None = None) -> dict[str, Any]:
    """Inspect current system resources, volume, media playback, and active window.

    Governed by PermissionGate under Action.SYSTEM_QUERY.
    """
    if gate is not None:
        await gate.check(Action.SYSTEM_QUERY, "get_system_status")

    mem_info = await asyncio.to_thread(_read_proc_meminfo)
    load_avg = await asyncio.to_thread(_read_proc_loadavg)

    vol_info, media_track, active_win = await asyncio.gather(
        _get_wpctl_volume(),
        _get_playerctl_track(),
        _get_hyprctl_window(),
    )

    total_kb = mem_info.get("MemTotal", 0)
    avail_kb = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb)
    pct = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0.0
    total_gb = round(total_kb / 1024 / 1024, 1)
    used_gb = round(used_kb / 1024 / 1024, 1)
    ram_summary = f"{used_gb}GB / {total_gb}GB ({pct}%)" if total_kb > 0 else "desconocido"

    return {
        "ram": {
            "total_kb": total_kb,
            "available_kb": avail_kb,
            "used_kb": used_kb,
            "percent_used": pct,
            "summary": ram_summary,
        },
        "cpu": {
            "load_1m": load_avg[0],
            "load_5m": load_avg[1],
            "load_15m": load_avg[2],
        },
        "volume": vol_info["volume"],
        "volume_percent": vol_info["percent"],
        "is_muted": vol_info["muted"],
        "media_track": media_track,
        "active_window": active_win,
    }


async def set_volume(level: str | int, gate: PermissionGate | None = None) -> str:
    """Set sink volume percentage or toggle mute via wpctl.

    Args:
        level: Percentage (e.g. 30, "30", "30%") or "mute" to toggle mute.
        gate: Optional PermissionGate instance to verify execution permissions.
    """
    level_str = str(level).strip().lower()

    if level_str in ("mute", "toggle"):
        cmd = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
        cmd_str = "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
        confirm = "Silencio de audio conmutado"
    else:
        clean_level = level_str.rstrip("%")
        cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{clean_level}%"]
        cmd_str = f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {clean_level}%"
        confirm = f"Volumen ajustado al {clean_level}%"

    if gate is not None:
        await gate.check(Action.SHELL_COMMAND, cmd_str)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or stdout).decode("utf-8").strip()
            logger.warning("wpctl execution failed (code %d): %s", proc.returncode, err)
            return f"Error ajustando volumen: {err}"
        return confirm
    except Exception as exc:
        logger.warning("wpctl invocation error: %s", exc)
        return f"Error ejecutando wpctl: {exc}"


async def media_control(action: str, gate: PermissionGate | None = None) -> str:
    """Control media playback via playerctl.

    Supports: play, pause, play-pause, next, previous, stop.
    """
    act = action.strip().lower()
    if act not in VALID_MEDIA_ACTIONS:
        return f"Acción multimedia no válida: '{action}'. Soportadas: {', '.join(sorted(VALID_MEDIA_ACTIONS))}"

    cmd = ["playerctl", act]
    cmd_str = f"playerctl {act}"

    if gate is not None:
        await gate.check(Action.SHELL_COMMAND, cmd_str)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or stdout).decode("utf-8").strip()
            logger.warning("playerctl %s failed (code %d): %s", act, proc.returncode, err)
            return f"Error en control multimedia: {err}"

        messages = {
            "play": "Reproducción reanudada",
            "pause": "Reproducción pausada",
            "play-pause": "Reproducción conmutada",
            "next": "Siguiente pista",
            "previous": "Pista anterior",
            "stop": "Reproducción detenida",
        }
        return messages.get(act, f"Acción '{act}' ejecutada")
    except Exception as exc:
        logger.warning("playerctl invocation error: %s", exc)
        return f"Error ejecutando playerctl: {exc}"


_DANGEROUS_TARGET_CHARS: frozenset[str] = frozenset({";", "&", "|", "`", "$", "\n", "<", ">"})
_SHELL_INTERPRETER_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:sh|bash)\s+-c\b|\beval\b", re.IGNORECASE
)


def _is_unsafe_target(target: str) -> bool:
    """Detect shell injection characters, control characters, or shell interpreter calls."""
    if any(c in _DANGEROUS_TARGET_CHARS for c in target):
        return True
    if any(ord(c) < 32 for c in target):
        return True
    if _SHELL_INTERPRETER_PATTERN.search(target):
        return True
    return False


async def open_app(target: str, gate: PermissionGate | None = None) -> str:
    """Launch an application or URL via hyprctl dispatch exec or xdg-open."""
    app = target.strip()
    if not app:
        return "Objetivo de aplicación vacío"

    if _is_unsafe_target(target):
        return f"Objetivo de aplicación inválido o inseguro: '{target}'"

    if shutil.which("hyprctl"):
        cmd = ["hyprctl", "dispatch", "exec", app]
        cmd_str = f"hyprctl dispatch exec {app}"
    else:
        cmd = ["xdg-open", app]
        cmd_str = f"xdg-open {app}"

    if gate is not None:
        await gate.check(Action.SHELL_COMMAND, cmd_str)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or stdout).decode("utf-8").strip()
            logger.warning("open_app failed (code %d): %s", proc.returncode, err)
            return f"Error al abrir {app}: {err}"
        return f"Aplicación '{app}' iniciada"
    except Exception as exc:
        logger.warning("open_app invocation error: %s", exc)
        return f"Error ejecutando {cmd[0]}: {exc}"


async def execute_action(action_str: str, gate: PermissionGate | None = None) -> str:
    """Parse and execute a string action like `set_volume(30)` or `media_control('pause')`."""
    pattern = re.compile(r"^([a-zA-Z_0-9]+)\s*\((.*?)\)$")
    match = pattern.match(action_str.strip())
    if not match:
        return f"Formato de acción no reconocido: '{action_str}'"

    func_name = match.group(1)
    raw_args = match.group(2).strip().strip("'\"")

    if func_name == "set_volume":
        return await set_volume(raw_args, gate=gate)
    elif func_name == "media_control":
        return await media_control(raw_args, gate=gate)
    elif func_name == "open_app":
        return await open_app(raw_args, gate=gate)
    elif func_name == "get_system_status":
        status = await get_system_status(gate=gate)
        return json.dumps(status, ensure_ascii=False)
    else:
        return f"Acción desconocida: '{func_name}'"
