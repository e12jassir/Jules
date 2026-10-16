from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from jules.core.permissions import Action
from jules.platform.os_tools import (
    execute_action,
    get_system_status,
    media_control,
    open_app,
    set_volume,
)


@pytest.mark.asyncio
async def test_get_system_status_mocked() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    meminfo_content = (
        "MemTotal:       24283616 kB\n"
        "MemFree:        12681212 kB\n"
        "MemAvailable:   18572152 kB\n"
        "Buffers:            2908 kB\n"
    )
    loadavg_content = "1.23 1.06 1.14 2/1282 30598\n"

    mock_wpctl_proc = AsyncMock()
    mock_wpctl_proc.communicate.return_value = (b"Volume: 0.75\n", b"")
    mock_wpctl_proc.returncode = 0

    mock_player_proc = AsyncMock()
    mock_player_proc.communicate.return_value = (b"Daft Punk - One More Time\n", b"")
    mock_player_proc.returncode = 0

    mock_hypr_proc = AsyncMock()
    mock_hypr_proc.communicate.return_value = (
        json.dumps({"title": "Alacritty", "class": "alacritty"}).encode("utf-8"),
        b"",
    )
    mock_hypr_proc.returncode = 0

    async def fake_subprocess_exec(*args, **kwargs):
        cmd = args[0]
        if cmd == "wpctl":
            return mock_wpctl_proc
        elif cmd == "playerctl":
            return mock_player_proc
        elif cmd == "hyprctl":
            return mock_hypr_proc
        raise ValueError(f"Unexpected command: {cmd}")

    with patch("builtins.open") as mock_open, \
         patch("asyncio.create_subprocess_exec", side_effect=fake_subprocess_exec):

        def fake_open_side_effect(path, *args, **kwargs):
            m = MagicMock()
            if path == "/proc/meminfo":
                m.__enter__.return_value = meminfo_content.splitlines(keepends=True)
            elif path == "/proc/loadavg":
                m.__enter__.return_value.read.return_value = loadavg_content
            else:
                m.__enter__.return_value.read.return_value = ""
            return m

        mock_open.side_effect = fake_open_side_effect

        status = await get_system_status(gate=mock_gate)

    mock_gate.check.assert_awaited_once_with(Action.SYSTEM_QUERY, "get_system_status")

    assert status["ram"]["total_kb"] == 24283616
    assert status["ram"]["available_kb"] == 18572152
    assert status["ram"]["used_kb"] == 24283616 - 18572152
    assert "GB" in status["ram"]["summary"]
    assert status["cpu"]["load_1m"] == 1.23
    assert status["cpu"]["load_5m"] == 1.06
    assert status["volume"] == "75%"
    assert status["volume_percent"] == 75
    assert status["is_muted"] is False
    assert status["media_track"] == "Daft Punk - One More Time"
    assert status["active_window"] == {"title": "Alacritty", "class": "alacritty"}


@pytest.mark.asyncio
async def test_set_volume_int_and_str() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        res = await set_volume(30, gate=mock_gate)
        assert "30%" in res
        mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "wpctl set-volume @DEFAULT_AUDIO_SINK@ 30%")
        mock_exec.assert_called_with(
            "wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "30%",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    mock_gate.check.reset_mock()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        res = await set_volume("50%", gate=mock_gate)
        assert "50%" in res
        mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "wpctl set-volume @DEFAULT_AUDIO_SINK@ 50%")
        mock_exec.assert_called_with(
            "wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "50%",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_set_volume_mute() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        res = await set_volume("mute", gate=mock_gate)
        assert "Silencio" in res
        mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
        mock_exec.assert_called_with(
            "wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_media_control_valid_actions() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    for action in ["play", "pause", "play-pause", "next", "previous", "stop"]:
        mock_gate.check.reset_mock()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            res = await media_control(action, gate=mock_gate)
            assert "Error" not in res
            mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, f"playerctl {action}")
            mock_exec.assert_called_with(
                "playerctl", action,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )


@pytest.mark.asyncio
async def test_media_control_invalid_action() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    res = await media_control("invalid_action", gate=mock_gate)
    assert "no válida" in res
    mock_gate.check.assert_not_called()


@pytest.mark.asyncio
async def test_open_app_hyprctl() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with patch("shutil.which", return_value="/usr/bin/hyprctl"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        res = await open_app("firefox", gate=mock_gate)
        assert "iniciada" in res
        mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "hyprctl dispatch exec firefox")
        mock_exec.assert_called_with(
            "hyprctl", "dispatch", "exec", "firefox",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_open_app_xdg_open_fallback() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    with patch("shutil.which", return_value=None), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        res = await open_app("https://example.com", gate=mock_gate)
        assert "iniciada" in res
        mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "xdg-open https://example.com")
        mock_exec.assert_called_with(
            "xdg-open", "https://example.com",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_execute_action_dispatch() -> None:
    with patch("jules.platform.os_tools.set_volume", new_callable=AsyncMock) as mock_vol, \
         patch("jules.platform.os_tools.media_control", new_callable=AsyncMock) as mock_media, \
         patch("jules.platform.os_tools.open_app", new_callable=AsyncMock) as mock_open:

        mock_vol.return_value = "Volumen ok"
        mock_media.return_value = "Media ok"
        mock_open.return_value = "App ok"

        res1 = await execute_action("set_volume(30)")
        mock_vol.assert_awaited_once_with("30", gate=None)
        assert res1 == "Volumen ok"

        res2 = await execute_action('media_control("next")')
        mock_media.assert_awaited_once_with("next", gate=None)
        assert res2 == "Media ok"

        res3 = await execute_action('open_app("spotify")')
        mock_open.assert_awaited_once_with("spotify", gate=None)
        assert res3 == "App ok"

        res4 = await execute_action("unknown_func(123)")
        assert "desconocida" in res4
