import asyncio
import shutil
from typing import AsyncIterator

from jules.memory.models import SessionContext
from jules.providers.base import (
    ProviderError,
    ProviderUnavailableError,
)

# `codex exec <prompt>` writes ONLY the model response to stdout.
# All headers, metadata, and logs go to stderr. No parsing needed.


class CodexProvider:
    name = "codex"
    default_model = "openai/gpt-5.4-mini"

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self.executable = "codex"
        self.timeout_seconds = timeout_seconds
        self._prepared_models = [self.default_model]

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        chunks: list[str] = []
        async for chunk in self.stream(prompt, context, model):
            chunks.append(chunk)
        return "".join(chunks).strip()

    async def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        del context, model  # codex exec uses config-baked model; -m is not supported

        if prompt.startswith("-"):
            raise ProviderError(
                "Invalid prompt: must not start with '-' to prevent argument injection."
            )

        args = [self.executable, "exec", prompt]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"Codex CLI executable not found: {self.executable}"
            ) from exc

        try:
            assert proc.stdout is not None
            # stdout is the clean response only — no header, no metadata.
            async for raw_line in proc.stdout:
                text = raw_line.decode(errors="replace")
                if text:
                    yield text
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except (ProcessLookupError, asyncio.TimeoutError):
                    pass

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Codex CLI does not support embeddings.")

    async def health_check(self) -> bool:
        return shutil.which(self.executable) is not None

    async def close(self) -> None:
        pass
