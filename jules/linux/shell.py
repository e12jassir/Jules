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


def detect_shell() -> str:
    return os.environ.get("SHELL", "unknown")


def install_zsh_hooks(
    zshrc_path: Path | None = None,
    shell_path: str | None = None,
) -> bool:
    shell = shell_path or detect_shell()
    if Path(shell).name != "zsh":
        return False

    target = zshrc_path or (Path.home() / ".zshrc")
    if target.exists():
        current = target.read_text(encoding="utf-8")
    else:
        current = ""

    if ZSH_HOOKS_START in current:
        return False

    if current and not current.endswith("\n"):
        current = f"{current}\n"
    updated = f"{current}{ZSH_HOOKS_BLOCK}"
    real_target = target.resolve()
    tmp_target = real_target.with_name(f"{real_target.name}.tmp")
    tmp_target.write_text(updated, encoding="utf-8")
    if real_target.exists():
        shutil.copymode(real_target, tmp_target)
    os.replace(tmp_target, real_target)
    return True
