from __future__ import annotations

import asyncio
import re
import shutil
from typing import AsyncIterator

from jules.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

# Strip ANSI escape sequences (colors, cursor movements, etc.)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

# Lines emitted by opencode before the actual response — skip them.
# Format: "> build · <model-name>"  or  "> build ▷ <model-name>"
_HEADER_RE = re.compile(r"^>\s*build\s")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class OpenCodeProvider:
    name = "opencode"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.executable = "opencode"
        self.timeout_seconds = timeout_seconds

    async def ask(self, prompt: str, context: list[dict], model: str) -> str:
        del context
        if prompt.startswith("-"):
            raise ProviderError("Invalid prompt: must not start with '-' to prevent argument injection.")
        if not re.match(r"^[a-zA-Z0-9_.\-]+(/[a-zA-Z0-9_.\-]+)?$", model):
            raise ProviderError(
                f"Invalid model identifier: '{model}'. Expected format: 'provider/model-name'."
            )
        return await self._run_cli(
            [self.executable, "--pure", "--variant", "minimal", "run", "-m", model],
            prompt=prompt,
            timeout=self.timeout_seconds,
        )

    async def stream(
        self,
        prompt: str,
        context: list[dict],
        model: str,
    ) -> AsyncIterator[str]:
        del context
        if prompt.startswith("-"):
            raise ProviderError("Invalid prompt: must not start with '-' to prevent argument injection.")
        if not re.match(r"^[a-zA-Z0-9_.\-]+(/[a-zA-Z0-9_.\-]+)?$", model):
            raise ProviderError(
                f"Invalid model identifier: '{model}'. Expected format: 'provider/model-name'."
            )

        args = [self.executable, "--pure", "--variant", "minimal", "run", "-m", model]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if proc.stdin:
                proc.stdin.write(prompt.encode())
                proc.stdin.close()
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"OpenCode CLI executable not found: {self.executable}"
            ) from exc

        try:
            assert proc.stdout is not None
            # Read line-by-line: faster than 4-byte chunks, avoids splitting ANSI codes
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace")
                clean = _strip_ansi(line)

                # Skip the header line opencode emits before the response
                if _HEADER_RE.match(clean.strip()):
                    continue

                if clean:
                    yield clean

        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except (ProcessLookupError, asyncio.TimeoutError):
                    pass

    async def embed(self, text: str) -> list[float]:
        del text
        raise NotImplementedError(
            "OpenCode CLI does not support embeddings in this phase."
        )

    async def health_check(self) -> bool:
        return shutil.which(self.executable) is not None

    async def close(self) -> None:
        pass

    async def _run_cli(self, args: list[str], prompt: str, timeout: float) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"OpenCode CLI executable not found: {self.executable}"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(input=prompt.encode()), timeout=timeout)
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            raise ProviderTimeoutError(f"OpenCode CLI timeout after {timeout}s") from exc

        stdout_text = _strip_ansi(stdout.decode(errors="replace")).strip()
        stderr_text = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            raise ProviderError(
                "OpenCode CLI exited "
                f"{proc.returncode}: stderr={stderr_text!r} stdout={stdout_text!r}"
            )

        # Strip the header line from non-streaming output too
        lines = [l for l in stdout_text.splitlines() if not _HEADER_RE.match(l.strip())]
        return "\n".join(lines).strip()
