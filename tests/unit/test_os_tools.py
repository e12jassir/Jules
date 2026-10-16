from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from jules.core.permissions import Action
from jules.platform.os_tools import (
    capture_screen_tool,
    execute_action,
    get_system_status,
    media_control,
    open_app,
    read_clipboard_tool,
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
         patch("jules.platform.os_tools.open_app", new_callable=AsyncMock) as mock_open, \
         patch("jules.platform.os_tools.capture_screen_tool", new_callable=AsyncMock) as mock_cap, \
         patch("jules.platform.os_tools.read_clipboard_tool", new_callable=AsyncMock) as mock_clip:

        mock_vol.return_value = "Volumen ok"
        mock_media.return_value = "Media ok"
        mock_open.return_value = "App ok"
        mock_cap.return_value = "Capture ok"
        mock_clip.return_value = "Clipboard ok"

        res1 = await execute_action("set_volume(30)")
        mock_vol.assert_awaited_once_with("30", gate=None)
        assert res1 == "Volumen ok"

        res2 = await execute_action('media_control("next")')
        mock_media.assert_awaited_once_with("next", gate=None)
        assert res2 == "Media ok"

        res3 = await execute_action('open_app("spotify")')
        mock_open.assert_awaited_once_with("spotify", gate=None)
        assert res3 == "App ok"

        res_cap = await execute_action("capture_screen()")
        mock_cap.assert_awaited_once_with(gate=None)
        assert res_cap == "Capture ok"

        res_clip = await execute_action("read_clipboard()")
        mock_clip.assert_awaited_once_with(gate=None)
        assert res_clip == "Clipboard ok"

        res4 = await execute_action("unknown_func(123)")
        assert "desconocida" in res4


@pytest.mark.asyncio
async def test_open_app_rejects_unsafe_targets() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    unsafe_payloads = [
        "firefox; rm -rf /",
        "app & evil",
        "app | cat",
        "app `id`",
        "app $(whoami)",
        "firefox\nmalicious",
        "app < /dev/null",
        "app > /tmp/out",
        "sh -c 'curl evil.com'",
        "bash -c 'rm -rf /'",
        "eval 'dangerous()'",
        "eval evil",
    ]

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        for payload in unsafe_payloads:
            mock_gate.check.reset_mock()
            mock_exec.reset_mock()

            result = await open_app(payload, gate=mock_gate)
            assert result == f"Objetivo de aplicación inválido o inseguro: '{payload}'"
            mock_gate.check.assert_not_called()
            mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_open_app_empty_target() -> None:
    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        result = await open_app("   ", gate=mock_gate)
        assert result == "Objetivo de aplicación vacío"
        mock_gate.check.assert_not_called()
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_capture_screen_tool_with_gate() -> None:
    from jules.perception.vision import VisionCaptureResult

    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_result = VisionCaptureResult(
        data=b"\x89PNG\r\n\x1a\nfakeimagebytes",
        format="png",
        width=1920,
        height=1080,
    )

    with patch("jules.perception.vision.capture_screen", new_callable=AsyncMock) as mock_capture:
        mock_capture.return_value = mock_result
        output = await capture_screen_tool(gate=mock_gate)

    mock_gate.check.assert_awaited_once_with(Action.SHELL_COMMAND, "grim -")
    assert "Captura de pantalla realizada en memoria" in output
    assert f"{mock_result.size_bytes} bytes" in output
    assert "1920x1080" in output


@pytest.mark.asyncio
async def test_capture_screen_tool_without_gate() -> None:
    from jules.perception.vision import VisionCaptureResult

    mock_result = VisionCaptureResult(
        data=b"rawbytes",
        format="png",
        width=800,
        height=600,
    )

    with patch("jules.perception.vision.capture_screen", new_callable=AsyncMock) as mock_capture:
        mock_capture.return_value = mock_result
        output = await capture_screen_tool(gate=None)

    assert output == "Captura de pantalla realizada en memoria (8 bytes, 800x600)"


@pytest.mark.asyncio
async def test_read_clipboard_tool_with_and_without_gate() -> None:
    from jules.perception.clipboard import ClipboardResult

    mock_gate = MagicMock()
    mock_gate.check = AsyncMock()

    mock_result = ClipboardResult(
        text="git status --short",
        is_safe=True,
    )

    with patch("jules.perception.clipboard.get_clipboard_text", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        output = await read_clipboard_tool(gate=mock_gate)
        mock_get.assert_awaited_once_with(gate=mock_gate)

    assert output == "Contenido del portapapeles: git status --short"

    with patch("jules.perception.clipboard.get_clipboard_text", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        output_nogate = await read_clipboard_tool(gate=None)
        mock_get.assert_awaited_once_with(gate=None)

    assert output_nogate == "Contenido del portapapeles: git status --short"

