from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import sys
import termios
import tty
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jules.core.config import PermissionsConfig

# Discriminates background context (set to True inside EventBus, default False)
IS_BACKGROUND_TASK: ContextVar[bool] = ContextVar("IS_BACKGROUND_TASK", default=False)


class Action(str, Enum):
    """The category of system operation requested. The concrete operand is `target`."""
    SHELL_COMMAND = "shell_command"   # arbitrary shell invocation
    PACKAGE_OP = "package_op"         # pacman / yay package mutation
    FILE_READ = "file_read"           # read-only filesystem access
    FILE_WRITE = "file_write"         # filesystem mutation
    SYSTEM_QUERY = "system_query"     # status / listing / search


class PermissionClassification(str, Enum):
    """Result of classifying an (action, target) pair."""
    SAFE = "safe"
    REQUIRED = "required"
    PROHIBITED = "prohibited"


class PermissionDeniedError(Exception):
    """Raised when an action is denied (Prohibited, user-deny, or headless fail-safe)."""

    def __init__(
        self,
        action: Action,
        target: str,
        classification: PermissionClassification,
        reason: str,
    ) -> None:
        self.action: Action = action
        self.target: str = target
        self.classification: PermissionClassification = classification
        self.reason: str = reason  # e.g. "prohibited_pattern", "user_denied", "no_display_environment"
        super().__init__(f"Permission denied [{classification.value}/{reason}]: {action.value} -> {target}")


# Predefined baseline prohibited/required patterns
_PROHIBITED_DEFAULTS: tuple[str, ...] = (
    r"\bdd\s+.*of=/dev/",
)

_CORE_OS_ROOTS: tuple[str, ...] = ("/boot", "/dev", "/etc", "/lib", "/usr", "/bin", "/sbin", "/var")

_REQUIRED_DEFAULTS: tuple[str, ...] = (
    r"^(?:pacman|yay)",
)


def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Precompiles regular expression strings into Pattern objects."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.DOTALL))
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {p}") from e
    return tuple(compiled)


def _has_display() -> bool:
    """Checks if a graphical display environment is present."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _normalize_shell_operand(path: str) -> str:
    """Normalizes shell/file operands before protected path checks.

    Fail-closed policy: expand known user/env prefixes and collapse repeated
    leading slashes so shell-equivalent protected paths stay protected.
    """
    stripped = path.rstrip(";&|")
    expanded = os.path.expandvars(os.path.expanduser(stripped))
    if expanded.startswith("/"):
        expanded = re.sub(r"^/+", "/", expanded)
        return os.path.normpath(expanded)
    return expanded


def _is_core_os_path(path: str) -> bool:
    """Returns True for direct core OS paths that must not be mutated."""
    normalized = _normalize_shell_operand(path)
    return any(normalized == root or normalized.startswith(f"{root}/") for root in _CORE_OS_ROOTS)


def _is_root_wide_path(path: str) -> bool:
    """Returns True for root itself or root-level globs/hidden entries, not scoped paths like /tmp."""
    normalized = _normalize_shell_operand(path)
    return normalized == "/" or (normalized.startswith("/") and len(normalized) > 1 and normalized[1] in "*?[.{")


def _is_assignment(token: str) -> bool:
    """Returns True for shell-style NAME=value environment assignments."""
    name, separator, _ = token.partition("=")
    return bool(separator and name and (name[0].isalpha() or name[0] == "_") and name.replace("_", "").isalnum())


def _effective_command_tokens(tokens: list[str]) -> list[str]:
    """Skips common shell command wrappers to expose the effective argv."""
    index = 0
    while index < len(tokens):
        if _is_assignment(tokens[index]):
            index += 1
            continue

        command = os.path.basename(tokens[index])

        if command == "command":
            index += 1
            continue

        if command == "sudo":
            index += 1
            while index < len(tokens):
                token = tokens[index]
                if _is_assignment(token):
                    index += 1
                    continue
                if token in {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-T", "--command-timeout"}:
                    index += 2
                    continue
                if token.startswith(("--user=", "--group=", "--host=", "--prompt=", "--close-from=", "--command-timeout=")):
                    index += 1
                    continue
                if token.startswith("-"):
                    index += 1
                    continue
                break
            continue

        if command == "env":
            index += 1
            while index < len(tokens):
                token = tokens[index]
                if token == "--":
                    index += 1
                    break
                if token in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if token in {"-S", "--split-string"}:
                    return _effective_command_tokens(["env", *shlex.split(tokens[index + 1])]) if index + 1 < len(tokens) else []
                if token.startswith("--split-string="):
                    return _effective_command_tokens(["env", *shlex.split(token.split("=", 1)[1])])
                if token.startswith(("--unset=", "--chdir=")):
                    index += 1
                    continue
                if token.startswith("-") or _is_assignment(token):
                    index += 1
                    continue
                break
            continue

        return tokens[index:]

    return []


def _shell_segments(target: str) -> list[list[str]]:
    """Splits a shell string into simple-command token segments at top-level separators."""
    try:
        lexer = shlex.shlex(target, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except ValueError:
        tokens = target.split()

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token and all(ch in ";&|\n" for ch in token):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _is_prohibited_rm_tokens(tokens: list[str], depth: int) -> bool:
    tokens = _effective_command_tokens(tokens)
    if not tokens:
        return False

    raw_command = tokens[0]
    if "$" in raw_command and "rm" in raw_command:
        return True

    command = os.path.basename(raw_command)

    if command in {"sh", "bash"}:
        for offset, token in enumerate(tokens[1:], start=1):
            if token == "-c" or (token.startswith("-") and not token.startswith("--") and "c" in token[1:]):
                command_index = offset + 1
                if command_index < len(tokens):
                    return _is_prohibited_rm_command(tokens[command_index], depth + 1)
                return False

    if command != "rm":
        return False

    flags = ""
    operands: list[str] = []
    flag_tokens: list[str] = []
    for offset, token in enumerate(tokens[1:], start=1):
        if token == "--":
            operands.extend(t for t in tokens[offset + 1:] if t)
            break
        if token.startswith("-"):
            flag_tokens.append(token)
            flags += token.lstrip("-")
            continue
        operands.append(token)

    normalized_flags = flags.lower()
    if "recursive" in normalized_flags:
        normalized_flags += "r"
    is_recursive = "r" in normalized_flags

    if any("$" in token for token in flag_tokens) and is_recursive:
        return True

    return any(
        _is_root_wide_path(path)
        or _is_core_os_path(path)
        or (is_recursive and "$" in path)
        for path in operands
    )


def _is_prohibited_rm_command(target: str, depth: int = 0) -> bool:
    """Detects forced recursive rm against root/core OS paths with shell-token awareness."""
    if depth > 3:
        return False
    substitutions = [*re.findall(r"\$\(([^()]*)\)", target), *re.findall(r"`([^`]*)`", target)]
    if any(_is_prohibited_rm_command(payload, depth + 1) for payload in substitutions):
        return True
    return any(_is_prohibited_rm_tokens(segment, depth) for segment in _shell_segments(target))


def _is_prohibited_dd_command(target: str, depth: int = 0) -> bool:
    """Detects direct dd writes to block devices after shell quote removal."""
    if depth > 3:
        return False
    if "$" in target and "dd" in target and "of=" in target:
        return True
    if any(_is_core_os_path(match) for match in re.findall(r"\bdd\b[^;&|]*(?:^|\s)of=(?:['\"])?([^'\"\s;&|]+)", target)):
        return True
    for segment in _shell_segments(target):
        tokens = _effective_command_tokens(segment)
        if not tokens:
            continue
        raw_command = tokens[0]
        if "$" in raw_command and "dd" in raw_command:
            return True

        command = os.path.basename(raw_command)
        if command in {"sh", "bash"}:
            for offset, token in enumerate(tokens[1:], start=1):
                if token == "-c" or (token.startswith("-") and not token.startswith("--") and "c" in token[1:]):
                    command_index = offset + 1
                    if command_index < len(tokens) and _is_prohibited_dd_command(tokens[command_index], depth + 1):
                        return True
        if command == "dd":
            for token in tokens[1:]:
                if token.startswith("of=") and ("$" in token[3:] or _is_core_os_path(token[3:])):
                    return True
    return False


async def _read_single_key() -> str:
    """Reads one terminal key without echo; fail-closed to denial on errors."""
    if not sys.stdin.isatty():
        return "n"

    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    fd = sys.stdin.fileno()

    try:
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
    except Exception:
        return "n"

    def _on_key() -> None:
        try:
            ch = sys.stdin.read(1)
            if not future.done():
                future.set_result(ch)
        except Exception:
            if not future.done():
                future.set_result("n")

    try:
        loop.add_reader(fd, _on_key)
        return await future
    finally:
        loop.remove_reader(fd)
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


class PermissionGate:
    """Deterministic, stateless authorization gate with zero latency overhead for safe actions."""

    def __init__(self, config: PermissionsConfig) -> None:
        self._config: PermissionsConfig = config
        self._prohibited: tuple[re.Pattern[str], ...] = _compile((*_PROHIBITED_DEFAULTS, *config.prohibited_patterns))
        
        required_patterns = (*_REQUIRED_DEFAULTS, *config.required_patterns) if config.require_confirmation_packages else tuple(config.required_patterns)
        self._required: tuple[re.Pattern[str], ...] = _compile(required_patterns)
        
        self._safe: tuple[re.Pattern[str], ...] = _compile(tuple(config.safe_patterns))

    def classify(self, action: Action, target: str) -> PermissionClassification:
        """Pure, side-effect-free action classification. Precedence: Prohibited > Required > Safe."""
        if action is Action.SHELL_COMMAND and (
            _is_prohibited_rm_command(target) or _is_prohibited_dd_command(target)
        ):
            return PermissionClassification.PROHIBITED

        if action is Action.FILE_WRITE and _is_core_os_path(target):
            return PermissionClassification.PROHIBITED

        for pattern in self._prohibited:
            if pattern.search(target):
                return PermissionClassification.PROHIBITED

        # Check required configuration writes
        if action is Action.FILE_WRITE and self._config.require_confirmation_config_writes:
            # Writable application configuration: target contains 'config' or ends with .toml/.yaml/.json
            if "config" in target or target.endswith((".toml", ".yaml", ".json")):
                return PermissionClassification.REQUIRED

        # Check required package operations
        if action is Action.PACKAGE_OP and self._config.require_confirmation_packages:
            return PermissionClassification.REQUIRED

        for pattern in self._required:
            if pattern.search(target):
                return PermissionClassification.REQUIRED

        # Check safe classifications
        if action in (Action.FILE_READ, Action.SYSTEM_QUERY):
            return PermissionClassification.SAFE

        for pattern in self._safe:
            if pattern.search(target):
                return PermissionClassification.SAFE

        # Default fallback
        return PermissionClassification.REQUIRED

    async def _prompt_foreground(self, action: Action, target: str) -> bool:
        """Renders an ephemeral interactive authorization prompt in the terminal."""
        from rich.console import Console
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text

        console = Console()
        body = Text.assemble(
            ("Action: ", "bold"), (f"{action.value}\n", "cyan"),
            ("Target: ", "bold"), (f"{target}\n", "yellow"),
            ("Class:  ", "bold"), ("REQUIRED\n\n", "magenta"),
            ("[y] Approve   [n] Deny", "dim"),
        )
        panel = Panel(body, title="Jules — Authorization Required", border_style="red")

        with Live(panel, console=console, transient=True, auto_refresh=False, screen=False) as live:
            live.refresh()
            key = await _read_single_key()

        return key.lower() == "y"

    async def _prompt_background(self, action: Action, target: str) -> bool:
        """Dispatches a KDE Plasma desktop notification with action buttons and suspends task."""
        has_notify = await asyncio.to_thread(shutil.which, "notify-send")
        if not _has_display() or has_notify is None:
            self._log_denial(action, target, PermissionClassification.REQUIRED, "no_display_environment")
            raise PermissionDeniedError(action, target, PermissionClassification.REQUIRED, "no_display_environment")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        import html
        escaped_target = html.escape(target)

        try:
            proc = await asyncio.create_subprocess_exec(
                "notify-send",
                "--app-name=Jules",
                "--urgency=critical",
                "--action=approve=Approve",
                "--action=deny=Deny",
                "--wait",
                "Jules — Authorization Required",
                f"{action.value}: {escaped_target}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            self._log_denial(action, target, PermissionClassification.REQUIRED, "no_display_environment")
            raise PermissionDeniedError(action, target, PermissionClassification.REQUIRED, "no_display_environment") from e
        except Exception as e:
            self._log_denial(action, target, PermissionClassification.REQUIRED, "notification_execution_failed")
            raise PermissionDeniedError(action, target, PermissionClassification.REQUIRED, "notification_execution_failed") from e

        async def _reader() -> None:
            try:
                stdout, _ = await proc.communicate()
                if future.done():
                    return
                choice = stdout.decode().strip()
                future.set_result(choice if choice in ("approve", "deny") else "deny")
            except Exception:
                if not future.done():
                    future.set_result("deny")

        reader_task = loop.create_task(_reader())
        try:
            choice = await asyncio.wait_for(future, timeout=self._config.notify_timeout_seconds)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            choice = "deny"
        finally:
            reader_task.cancel()
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await proc.wait()
                except Exception:
                    pass

        return choice == "approve"

    def _log_denial(self, action: Action, target: str, classification: PermissionClassification, reason: str) -> None:
        """Structured warning logging for denied operations."""
        logging.getLogger(__name__).warning(
            "permission_denied",
            extra={"denial": {
                "action": action.value,
                "target": target,
                "classification": classification.value,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }},
        )

    async def check(self, action: Action, target: str) -> None:
        """Checks permission for an action, raising PermissionDeniedError if unauthorized."""
        classification = self.classify(action, target)

        if classification is PermissionClassification.SAFE:
            return

        if classification is PermissionClassification.PROHIBITED:
            self._log_denial(action, target, classification, "prohibited_pattern")
            raise PermissionDeniedError(action, target, classification, "prohibited_pattern")

        if IS_BACKGROUND_TASK.get():
            approved = await self._prompt_background(action, target)
        else:
            approved = await self._prompt_foreground(action, target)

        if not approved:
            self._log_denial(action, target, classification, "user_denied")
            raise PermissionDeniedError(action, target, classification, "user_denied")
