from __future__ import annotations

import asyncio
import os
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jules.core.config import PermissionsConfig
from jules.core.permissions import (
    PermissionGate,
    Action,
    PermissionClassification,
    PermissionDeniedError,
    IS_BACKGROUND_TASK,
)


def test_classify_safe() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)
    assert gate.classify(Action.FILE_READ, "/some/file.txt") == PermissionClassification.SAFE
    assert gate.classify(Action.SYSTEM_QUERY, "ps aux") == PermissionClassification.SAFE


def test_classify_prohibited_defaults() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf '/'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, 'rm -rf "/"') == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /?*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /[!.]*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /.[!.]*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -r -f /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -Rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -R -f /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf --no-preserve-root /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo -u root rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo --user root rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo FOO=bar rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "/bin/rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "command rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env -u PATH rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env -S 'rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env --split-string='rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env -S '-i rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "env -C /tmp rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -lc 'rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sh -ec 'rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo sh -c 'rm -rf /etc/*'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /; true") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "true; rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "true\nrm -rf /etc") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "echo ok\nrm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "echo ok && rm -rf /") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'rm -rf /; true'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'true; rm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'echo ok\nrm -rf /'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'true\nrm -rf /etc'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo rm -rf /etc/*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /etc/*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -r /etc") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm --recursive /var/lib/pacman") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /tmp/../*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /usr/lib") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /usr") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf //usr") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf //etc/*") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /dev") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /var/lib/pacman") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf ~/../../etc") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "sudo rm -rf ~/../../etc") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "bash -c 'rm -rf $HOME/../../etc'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "TARGET=/etc rm -rf $TARGET") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf$IFS/") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm${IFS}-rf${IFS}/") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm '$TMPFILE'") == PermissionClassification.REQUIRED
    assert gate.classify(Action.SHELL_COMMAND, "rm -f $TMPFILE") == PermissionClassification.REQUIRED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /bin") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /{*,.*}") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "echo $(rm -rf /)") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "echo `rm -rf /`") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "rm -rf /tmp") == PermissionClassification.REQUIRED
    assert gate.classify(Action.SHELL_COMMAND, "dd if=/dev/zero of=/dev/sda") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "dd if=/dev/zero of='/dev/sda'") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "dd if=/dev/zero of=//dev/sda") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, 'bash -c \'dd if=/dev/zero of="/dev/sda"\'') == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "TARGET=/dev/sda dd if=/dev/zero of=$TARGET") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "dd${IFS}if=/dev/zero${IFS}of=/dev/sda") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/etc/passwd") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/etc/shadow") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/tmp/../etc/passwd") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "//etc/passwd") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "~/../../etc/passwd") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/dev/sda") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/var/lib/pacman/local") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/bin/sh") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/usr/share/foo") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/boot/grub") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_WRITE, "/lib/modules") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.FILE_READ, "/etc/passwd") == PermissionClassification.SAFE
    assert gate.classify(Action.SYSTEM_QUERY, "ls /boot") == PermissionClassification.SAFE


def test_classify_required_defaults() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)
    assert gate.classify(Action.PACKAGE_OP, "pacman -Syu") == PermissionClassification.REQUIRED
    assert gate.classify(Action.PACKAGE_OP, "yay -S python") == PermissionClassification.REQUIRED


def test_classify_custom_patterns() -> None:
    config = PermissionsConfig(
        prohibited_patterns=(r"naughty",),
        required_patterns=(r"must_ask",),
        safe_patterns=(r"always_ok",),
    )
    gate = PermissionGate(config)
    assert gate.classify(Action.SHELL_COMMAND, "naughty command") == PermissionClassification.PROHIBITED
    assert gate.classify(Action.SHELL_COMMAND, "must_ask command") == PermissionClassification.REQUIRED
    assert gate.classify(Action.SHELL_COMMAND, "always_ok command") == PermissionClassification.SAFE


@pytest.mark.asyncio
async def test_check_safe_does_not_prompt_or_log() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    with patch.object(gate, "_prompt_foreground", new_callable=AsyncMock) as mock_fore, \
         patch.object(gate, "_log_denial", new_callable=MagicMock) as mock_log:

        await gate.check(Action.FILE_READ, "/some/file.txt")
        mock_fore.assert_not_called()
        mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_check_prohibited_raises_denied_and_logs() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    with patch.object(gate, "_prompt_foreground", new_callable=AsyncMock) as mock_fore, \
         patch.object(gate, "_log_denial", new_callable=MagicMock) as mock_log:

        with pytest.raises(PermissionDeniedError) as exc_info:
            await gate.check(Action.SHELL_COMMAND, "rm -rf /")

        assert exc_info.value.classification == PermissionClassification.PROHIBITED
        assert exc_info.value.reason == "prohibited_pattern"
        mock_fore.assert_not_called()
        mock_log.assert_called_once_with(Action.SHELL_COMMAND, "rm -rf /", PermissionClassification.PROHIBITED, "prohibited_pattern")


@pytest.mark.asyncio
async def test_check_required_stateless_invokes_prompt_twice() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    with patch.object(gate, "_prompt_foreground", new_callable=AsyncMock) as mock_fore:
        mock_fore.return_value = True

        # Invocations should not cache approval
        await gate.check(Action.PACKAGE_OP, "pacman -Syu")
        await gate.check(Action.PACKAGE_OP, "pacman -Syu")

        assert mock_fore.call_count == 2


@pytest.mark.asyncio
async def test_check_required_headless_failsafe_denies() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    token = IS_BACKGROUND_TASK.set(True)
    try:
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(gate, "_log_denial", new_callable=MagicMock) as mock_log:

            with pytest.raises(PermissionDeniedError) as exc_info:
                await gate.check(Action.PACKAGE_OP, "pacman -Syu")

            assert exc_info.value.reason == "no_display_environment"
            mock_log.assert_called_once_with(Action.PACKAGE_OP, "/pacman -Syu", PermissionClassification.REQUIRED, "no_display_environment")
    finally:
        IS_BACKGROUND_TASK.reset(token)
