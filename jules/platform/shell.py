from __future__ import annotations

import os
import shutil
from pathlib import Path

ZSH_HOOKS_START = "# JULES_ZSH_HOOKS_START"
ZSH_HOOKS_END = "# JULES_ZSH_HOOKS_END"
ZSH_HOOKS_BLOCK = """# JULES_ZSH_HOOKS_START
autoload -Uz add-zsh-hook

_jules_precmd() {
    # TODO: IPC hacia Jules
}
add-zsh-hook precmd _jules_precmd

_jules_preexec() {
    # TODO: IPC hacia Jules
}
add-zsh-hook preexec _jules_preexec
# JULES_ZSH_HOOKS_END
"""

BASH_HOOKS_START = "# JULES_BASH_HOOKS_START"
BASH_HOOKS_END = "# JULES_BASH_HOOKS_END"
# Bash has no native preexec/precmd hooks (unlike zsh). We rely on the
# widely-used bash-preexec shim (https://github.com/rcaloras/bash-preexec)
# which the user must have sourced already; if it is not present, our hooks
# simply never fire — no error, no crash, degraded gracefully.
BASH_HOOKS_BLOCK = """# JULES_BASH_HOOKS_START
# Requires bash-preexec (https://github.com/rcaloras/bash-preexec) to be
# sourced beforehand. Hooks are no-ops if preexec_functions is undefined.
_jules_precmd() {
    # TODO: IPC hacia Jules
}
_jules_preexec() {
    # TODO: IPC hacia Jules
}
if [[ -n "${preexec_functions+x}" ]]; then
    precmd_functions+=(_jules_precmd)
    preexec_functions+=(_jules_preexec)
fi
# JULES_BASH_HOOKS_END
"""

FISH_HOOKS_START = "# JULES_FISH_HOOKS_START"
FISH_HOOKS_END = "# JULES_FISH_HOOKS_END"
FISH_HOOKS_BLOCK = """# JULES_FISH_HOOKS_START
function _jules_precmd --on-event fish_prompt
    # TODO: IPC hacia Jules
end

function _jules_preexec --on-event fish_preexec
    # TODO: IPC hacia Jules
end
# JULES_FISH_HOOKS_END
"""

# fish config lives under a subdirectory, not a single dotfile like bash/zsh.
FISH_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "fish" / "config.fish"


def detect_shell() -> str:
    return os.environ.get("SHELL", "unknown")


def _install_hooks_block(
    target: Path,
    start_marker: str,
    block: str,
) -> bool:
    """Shared idempotent append-block logic used by all shell installers."""
    if target.exists():
        current = target.read_text(encoding="utf-8")
    else:
        current = ""
        target.parent.mkdir(parents=True, exist_ok=True)

    if start_marker in current:
        return False

    if current and not current.endswith("\n"):
        current = f"{current}\n"
    updated = f"{current}{block}"
    real_target = target.resolve() if target.exists() else target
    tmp_target = real_target.with_name(f"{real_target.name}.tmp")
    tmp_target.write_text(updated, encoding="utf-8")
    if real_target.exists():
        shutil.copymode(real_target, tmp_target)
    os.replace(tmp_target, real_target)
    return True


def install_zsh_hooks(
    zshrc_path: Path | None = None,
    shell_path: str | None = None,
) -> bool:
    shell = shell_path or detect_shell()
    if Path(shell).name != "zsh":
        return False

    target = zshrc_path or (Path.home() / ".zshrc")
    return _install_hooks_block(target, ZSH_HOOKS_START, ZSH_HOOKS_BLOCK)


def install_bash_hooks(
    bashrc_path: Path | None = None,
    shell_path: str | None = None,
) -> bool:
    shell = shell_path or detect_shell()
    if Path(shell).name != "bash":
        return False

    target = bashrc_path or (Path.home() / ".bashrc")
    return _install_hooks_block(target, BASH_HOOKS_START, BASH_HOOKS_BLOCK)


def install_fish_hooks(
    config_path: Path | None = None,
    shell_path: str | None = None,
) -> bool:
    shell = shell_path or detect_shell()
    if Path(shell).name != "fish":
        return False

    target = config_path or FISH_DEFAULT_CONFIG_PATH
    return _install_hooks_block(target, FISH_HOOKS_START, FISH_HOOKS_BLOCK)


def install_shell_hooks(shell_path: str | None = None) -> bool:
    """Detects the current shell and installs the matching hook block.

    Returns False (no-op) for shells without an installer (e.g. sh, dash,
    ksh) instead of raising — an unsupported shell is not a fatal error.
    """
    shell = shell_path or detect_shell()
    name = Path(shell).name
    if name == "zsh":
        return install_zsh_hooks(shell_path=shell)
    if name == "bash":
        return install_bash_hooks(shell_path=shell)
    if name == "fish":
        return install_fish_hooks(shell_path=shell)
    return False
