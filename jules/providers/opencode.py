from __future__ import annotations

import asyncio
import re
import shutil
from typing import AsyncIterator

from jules.memory.models import SessionContext
from jules.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class OpenCodeProvider:
    name = "opencode"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.executable = "opencode"
        self.timeout_seconds = timeout_seconds

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        del context
        if prompt.startswith("-"):
            raise ProviderError("Invalid prompt: must not start with '-' to prevent argument injection.")
        if not re.match(r'^[a-zA-Z0-9_.\-]+(/[a-zA-Z0-9_.\-]+)?$', model):
            raise ProviderError(
                f"Invalid model identifier: '{model}'. Expected format: 'provider/model-name'."
            )
        return await self._run_cli(
            [self.executable, "run", prompt, "-m", model],
            timeout=self.timeout_seconds,
        )

    def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        del prompt, context, model
        raise NotImplementedError(
            "OpenCode CLI does not support streaming/embeddings in this phase."
        )

    async def embed(self, text: str) -> list[float]:
        del text
        raise NotImplementedError(
            "OpenCode CLI does not support streaming/embeddings in this phase."
        )

    async def health_check(self) -> bool:
        return shutil.which(self.executable) is not None

    async def close(self) -> None:
        pass

    async def _run_cli(self, args: list[str], timeout: float) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"OpenCode CLI executable not found: {self.executable}"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass  # drain timed out — process is dead, pipes abandoned safely
            raise ProviderTimeoutError(f"OpenCode CLI timeout after {timeout}s") from exc

        stdout_text = stdout.decode(errors="replace").strip()
        stderr_text = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            raise ProviderError(
                "OpenCode CLI exited "
                f"{proc.returncode}: stderr={stderr_text!r} stdout={stdout_text!r}"
            )

        return stdout_text
