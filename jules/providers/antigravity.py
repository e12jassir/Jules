from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import tomllib
from typing import AsyncIterator

from jules.memory.models import SessionContext
from jules.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class AntigravityProvider:
    name = "antigravity"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.executable = "agy"
        self.timeout_seconds = timeout_seconds

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        del context
        if prompt.startswith("-"):
            raise ProviderError("Invalid prompt: must not start with '-' to prevent argument injection.")
        return await self._run_cli(
            [self.executable, "--print", prompt],
            timeout=self.timeout_seconds,
            model=model,
        )

    def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        del prompt, context, model
        raise NotImplementedError(
            "Antigravity CLI does not support streaming/embeddings in this phase."
        )

    async def embed(self, text: str) -> list[float]:
        del text
        raise NotImplementedError(
            "Antigravity CLI does not support streaming/embeddings in this phase."
        )

    async def health_check(self) -> bool:
        return shutil.which(self.executable) is not None

    async def close(self) -> None:
        pass

    async def _run_cli(self, args: list[str], timeout: float, model: str | None = None) -> str:
        config_home = Path.home() / ".jules" / "antigravity_config"
        config_home.mkdir(parents=True, exist_ok=True)
        if model:
            self._write_model_config(config_home, model)
        env = {**os.environ, "XDG_CONFIG_HOME": str(config_home)}

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ProviderUnavailableError(
                f"Antigravity CLI executable not found: {self.executable}"
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
            raise ProviderTimeoutError(
                f"Antigravity CLI timeout after {timeout}s"
            ) from exc

        stdout_text = stdout.decode(errors="replace").strip()
        stderr_text = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            raise ProviderError(
                "Antigravity CLI exited "
                f"{proc.returncode}: stderr={stderr_text!r} stdout={stdout_text!r}"
            )

        return stdout_text

    def _write_model_config(self, config_home: Path, model: str) -> None:
        config_path = config_home / "antigravity" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._read_existing_config(config_path)
        existing["model"] = model
        config_path.write_text(self._render_toml(existing), encoding="utf-8")

    def _read_existing_config(self, config_path: Path) -> dict[str, str]:
        if not config_path.exists():
            return {}
        try:
            with config_path.open("rb") as config_file:
                raw = tomllib.load(config_file)
        except tomllib.TOMLDecodeError as exc:
            raise ProviderError(f"Invalid Antigravity isolated config: {config_path}") from exc
        return {key: value for key, value in raw.items() if isinstance(value, str)}

    def _render_toml(self, values: dict[str, str]) -> str:
        return "".join(f'{key} = "{self._escape_toml(value)}"\n' for key, value in sorted(values.items()))

    @staticmethod
    def _escape_toml(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
