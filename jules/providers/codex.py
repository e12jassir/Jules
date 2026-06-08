import asyncio
import importlib
import os
import shutil
from typing import AsyncIterator

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

    async def ask(self, prompt: str, context: list[dict], model: str) -> str:
        chunks: list[str] = []
        async for chunk in self.stream(prompt, context, model):
            chunks.append(chunk)
        return "".join(chunks).strip()

    async def stream(
        self,
        prompt: str,
        context: list[dict],
        model: str,
    ) -> AsyncIterator[str]:
        del context  # codex exec uses config-baked model; -m is not supported

        if prompt.startswith("-"):
            raise ProviderError(
                "Invalid prompt: must not start with '-' to prevent argument injection."
            )

        args = [self.executable, "exec"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=await self._build_env(model),
            )
            if proc.stdin:
                proc.stdin.write(prompt.encode())
                proc.stdin.close()
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"Codex CLI executable not found: {self.executable}"
            ) from exc

        try:
            assert proc.stdout is not None
            assert proc.stderr is not None
            # stdout is the clean response only — no header, no metadata.
            async for raw_line in proc.stdout:
                text = raw_line.decode(errors="replace")
                if text:
                    yield text
            stderr_text = (await proc.stderr.read()).decode(errors="replace").strip()
            returncode = await proc.wait()
            if returncode != 0:
                raise ProviderError(
                    f"Codex CLI exited {returncode}: stderr={stderr_text!r}"
                )
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

    async def _build_env(self, model: str) -> dict[str, str]:
        auth_pkce = importlib.import_module("jules.core.auth_pkce")
        cli_environment_for_runtime = auth_pkce.cli_environment_for_runtime

        env = dict(os.environ)
        env.update(await cli_environment_for_runtime(self.name, model))
        return env
