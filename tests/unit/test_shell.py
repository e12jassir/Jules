from __future__ import annotations

from jules.linux.shell import (
    ZSH_HOOKS_END,
    ZSH_HOOKS_START,
    detect_shell,
    install_zsh_hooks,
)


def test_detect_shell_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    assert detect_shell() == "/usr/bin/zsh"


def test_install_zsh_hooks_is_idempotent(tmp_path) -> None:
    zshrc = tmp_path / ".zshrc"

    first = install_zsh_hooks(zshrc, shell_path="/usr/bin/zsh")
    second = install_zsh_hooks(zshrc, shell_path="/usr/bin/zsh")
    third = install_zsh_hooks(zshrc, shell_path="/usr/bin/zsh")

    content = zshrc.read_text(encoding="utf-8")
    assert first is True
    assert second is False
    assert third is False
    assert content.count(ZSH_HOOKS_START) == 1
    assert content.count(ZSH_HOOKS_END) == 1
    assert content.count("precmd()") == 1
    assert content.count("preexec()") == 1


def test_install_zsh_hooks_skips_non_zsh_shell(tmp_path) -> None:
    zshrc = tmp_path / ".zshrc"

    installed = install_zsh_hooks(zshrc, shell_path="/bin/bash")

    assert installed is False
    assert not zshrc.exists()
