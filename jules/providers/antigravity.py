from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import shutil
from typing import AsyncIterator

from jules.memory.models import SessionContext
from jules.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class AntigravityProvider:
    name = "antigravity"

    def __init__(self, timeout_seconds: float = 60.0, models: tuple[str, ...] = ()) -> None:
        self.executable = "agy"
        self.timeout_seconds = timeout_seconds
        self.profile_root = Path.home() / ".jules" / "agy_profiles"
        self.source_config = Path.home() / ".config" / "antigravity"
        self._prepared_models: set[str] = set()
        self.prepare_profiles(models)

    def prepare_profiles(self, models: tuple[str, ...]) -> None:
        for model in models:
            self._ensure_profile(model)

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        del context
        if model not in self._prepared_models:
            raise ProviderError(f"Antigravity profile for model {model!r} was not prepared")
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
        return await asyncio.to_thread(shutil.which, self.executable) is not None

    async def close(self) -> None:
        pass

    def _ensure_profile(self, model: str) -> Path:
        if model in self._prepared_models:
            return self._profile_path(model)

        profile_path = self._profile_path(model)
        config_dir = profile_path / "antigravity"
        if self.source_config.is_dir():
            self._copy_config(self.source_config, config_dir)
        else:
            config_dir.mkdir(parents=True, exist_ok=True)

        self._write_model_config(profile_path, model)
        self._prepared_models.add(model)
        return profile_path

    def _copy_config(self, src: Path, dest: Path) -> None:
        shutil.copytree(src, dest, dirs_exist_ok=True, symlinks=False)

    def _profile_path(self, model: str) -> Path:
        return self.profile_root / self._safe_profile_name(model)

    async def _run_cli(self, args: list[str], timeout: float, model: str | None = None) -> str:
        config_home = self._profile_path(model) if model else self.profile_root
        env = {**os.environ, "XDG_CONFIG_HOME": str(config_home)}

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            raise ProviderUnavailableError(
                f"Antigravity CLI executable not found or not executable: {self.executable}"
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

        if config_path.is_symlink():
            current = config_path.read_text(encoding="utf-8")
            config_path.unlink()
        else:
            current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

        model_line = f'model = "{self._escape_toml(model)}"'

        if re.search(r'^\s*model\s*=', current, flags=re.MULTILINE):
            updated = re.sub(r'^\s*model\s*=.*', model_line, current, count=1, flags=re.MULTILINE)
        else:
            updated = model_line + "\n" + current if current else model_line + "\n"

        config_path.write_text(updated, encoding="utf-8")

    @staticmethod
    def _safe_profile_name(model: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
        model_hash = hashlib.md5(model.encode("utf-8")).hexdigest()[:6]
        return f"{safe_name}_{model_hash}"

    @staticmethod
    def _escape_toml(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
