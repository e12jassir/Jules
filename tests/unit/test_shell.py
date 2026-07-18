from __future__ import annotations

from jules.platform.shell import (
    BASH_HOOKS_END,
    BASH_HOOKS_START,
    FISH_HOOKS_END,
    FISH_HOOKS_START,
    ZSH_HOOKS_END,
    ZSH_HOOKS_START,
    detect_shell,
    install_bash_hooks,
    install_fish_hooks,
    install_shell_hooks,
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


def test_install_bash_hooks_is_idempotent(tmp_path) -> None:
    bashrc = tmp_path / ".bashrc"

    first = install_bash_hooks(bashrc, shell_path="/bin/bash")
    second = install_bash_hooks(bashrc, shell_path="/bin/bash")

    content = bashrc.read_text(encoding="utf-8")
    assert first is True
    assert second is False
    assert content.count(BASH_HOOKS_START) == 1
    assert content.count(BASH_HOOKS_END) == 1


def test_install_bash_hooks_skips_non_bash_shell(tmp_path) -> None:
    bashrc = tmp_path / ".bashrc"

    installed = install_bash_hooks(bashrc, shell_path="/usr/bin/zsh")

    assert installed is False
    assert not bashrc.exists()


def test_install_fish_hooks_is_idempotent(tmp_path) -> None:
    config = tmp_path / "config.fish"

    first = install_fish_hooks(config, shell_path="/usr/bin/fish")
    second = install_fish_hooks(config, shell_path="/usr/bin/fish")

    content = config.read_text(encoding="utf-8")
    assert first is True
    assert second is False
    assert content.count(FISH_HOOKS_START) == 1
    assert content.count(FISH_HOOKS_END) == 1


def test_install_fish_hooks_creates_parent_directories(tmp_path) -> None:
    config = tmp_path / "fish" / "config.fish"

    installed = install_fish_hooks(config, shell_path="/usr/bin/fish")

    assert installed is True
    assert config.exists()


def test_install_fish_hooks_skips_non_fish_shell(tmp_path) -> None:
    config = tmp_path / "config.fish"

    installed = install_fish_hooks(config, shell_path="/bin/bash")

    assert installed is False
    assert not config.exists()


def test_install_shell_hooks_dispatches_by_detected_shell(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "jules.platform.shell.FISH_DEFAULT_CONFIG_PATH", tmp_path / "config.fish"
    )
    installed = install_shell_hooks(shell_path="/usr/bin/fish")
    assert installed is True
    assert (tmp_path / "config.fish").exists()


def test_install_shell_hooks_returns_false_for_unsupported_shell() -> None:
    assert install_shell_hooks(shell_path="/bin/dash") is False
