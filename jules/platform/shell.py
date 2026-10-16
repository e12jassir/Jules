from __future__ import annotations

import os
import shutil
from pathlib import Path

ZSH_HOOKS_START = "# JULES_ZSH_HOOKS_START"
ZSH_HOOKS_END = "# JULES_ZSH_HOOKS_END"
ZSH_HOOKS_BLOCK = r"""# JULES_ZSH_HOOKS_START
autoload -Uz add-zsh-hook

_jules_emit() {
    local phase="$1"
    local exit_code="${2:-0}"
    local cmd="$3"
    local sock="${XDG_RUNTIME_DIR:-/run/user/${UID:-$(id -u)}}/jules.sock"
    [ -S "$sock" ] || sock="$HOME/.jules/run/jules.sock"
    [ -S "$sock" ] || return 0

    (
        local esc_cmd="${cmd//\\/\\\\}"
        esc_cmd="${esc_cmd//\"/\\\"}"
        esc_cmd="${esc_cmd//$'\n'/\\n}"
        esc_cmd="${esc_cmd//$'\r'/\\r}"
        esc_cmd="${esc_cmd//$'\t'/\\t}"
        local esc_cwd="${PWD//\\/\\\\}"
        esc_cwd="${esc_cwd//\"/\\\"}"
        local payload="{\"op\":\"shell_event\",\"phase\":\"$phase\",\"cmd\":\"$esc_cmd\",\"exit_code\":$exit_code,\"cwd\":\"$esc_cwd\"}"
        if command -v nc >/dev/null 2>&1; then
            printf '%s\n' "$payload" | nc -U -w 1 "$sock"
        elif command -v socat >/dev/null 2>&1; then
            printf '%s\n' "$payload" | socat - UNIX-CONNECT:"$sock"
        elif command -v python3 >/dev/null 2>&1; then
            python3 -c "import socket, sys; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(0.5); s.connect(sys.argv[1]); s.sendall(sys.argv[2].encode('utf-8') + b'\n'); s.close()" "$sock" "$payload"
        fi &
    ) >/dev/null 2>&1
}

_jules_precmd() {
    local ec=$?
    _jules_emit "precmd" "$ec" ""
}
add-zsh-hook precmd _jules_precmd

_jules_preexec() {
    _jules_emit "preexec" 0 "$1"
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
BASH_HOOKS_BLOCK = r"""# JULES_BASH_HOOKS_START
# Requires bash-preexec (https://github.com/rcaloras/bash-preexec) to be
# sourced beforehand. Hooks are no-ops if preexec_functions is undefined.
_jules_emit() {
    local phase="$1"
    local exit_code="${2:-0}"
    local cmd="$3"
    local sock="${XDG_RUNTIME_DIR:-/run/user/${UID:-$(id -u)}}/jules.sock"
    [ -S "$sock" ] || sock="$HOME/.jules/run/jules.sock"
    [ -S "$sock" ] || return 0

    (
        local esc_cmd="${cmd//\\/\\\\}"
        esc_cmd="${esc_cmd//\"/\\\"}"
        esc_cmd="${esc_cmd//$'\n'/\\n}"
        esc_cmd="${esc_cmd//$'\r'/\\r}"
        esc_cmd="${esc_cmd//$'\t'/\\t}"
        local esc_cwd="${PWD//\\/\\\\}"
        esc_cwd="${esc_cwd//\"/\\\"}"
        local payload="{\"op\":\"shell_event\",\"phase\":\"$phase\",\"cmd\":\"$esc_cmd\",\"exit_code\":$exit_code,\"cwd\":\"$esc_cwd\"}"
        if command -v nc >/dev/null 2>&1; then
            printf '%s\n' "$payload" | nc -U -w 1 "$sock"
        elif command -v socat >/dev/null 2>&1; then
            printf '%s\n' "$payload" | socat - UNIX-CONNECT:"$sock"
        elif command -v python3 >/dev/null 2>&1; then
            python3 -c "import socket, sys; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(0.5); s.connect(sys.argv[1]); s.sendall(sys.argv[2].encode('utf-8') + b'\n'); s.close()" "$sock" "$payload"
        fi &
    ) >/dev/null 2>&1
}

_jules_precmd() {
    local ec=$?
    _jules_emit "precmd" "$ec" ""
}
_jules_preexec() {
    _jules_emit "preexec" 0 "$1"
}
if [[ -n "${preexec_functions+x}" ]]; then
    precmd_functions+=(_jules_precmd)
    preexec_functions+=(_jules_preexec)
fi
# JULES_BASH_HOOKS_END
"""

FISH_HOOKS_START = "# JULES_FISH_HOOKS_START"
FISH_HOOKS_END = "# JULES_FISH_HOOKS_END"
FISH_HOOKS_BLOCK = r"""# JULES_FISH_HOOKS_START
function _jules_emit
    set -l phase $argv[1]
    set -l exit_code 0
    if test (count $argv) -ge 2
        set exit_code $argv[2]
    end
    set -l cmd ""
    if test (count $argv) -ge 3
        set cmd $argv[3]
    end

    set -l uid (id -u 2>/dev/null; or echo 1000)
    set -l sock "$XDG_RUNTIME_DIR/jules.sock"
    if test -z "$XDG_RUNTIME_DIR"
        set sock "/run/user/$uid/jules.sock"
    end
    if not test -S "$sock"
        set sock "$HOME/.jules/run/jules.sock"
    end
    if not test -S "$sock"
        return 0
    end

    begin
        set -l esc_cmd (string replace -a '\\' '\\\\' -- "$cmd")
        set -l esc_cmd (string replace -a '"' '\\"' -- "$esc_cmd")
        set -l esc_cwd (string replace -a '\\' '\\\\' -- "$PWD")
        set -l esc_cwd (string replace -a '"' '\\"' -- "$esc_cwd")
        set -l payload "{\"op\":\"shell_event\",\"phase\":\"$phase\",\"cmd\":\"$esc_cmd\",\"exit_code\":$exit_code,\"cwd\":\"$esc_cwd\"}"
        if type -q nc
            printf '%s\n' "$payload" | nc -U -w 1 "$sock"
        else if type -q socat
            printf '%s\n' "$payload" | socat - UNIX-CONNECT:"$sock"
        else if type -q python3
            python3 -c "import socket, sys; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(0.5); s.connect(sys.argv[1]); s.sendall(sys.argv[2].encode('utf-8') + b'\n'); s.close()" "$sock" "$payload"
        end
    end >/dev/null 2>&1 &
end

function _jules_precmd --on-event fish_prompt
    set -l ec $status
    _jules_emit "precmd" "$ec" ""
end

function _jules_preexec --on-event fish_preexec
    _jules_emit "preexec" 0 "$argv[1]"
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
