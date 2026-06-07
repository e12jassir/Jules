"""Load Jules personality prompts for provider calls."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MasterPersonalityMissingError(FileNotFoundError):
    """Raised when the required master personality file does not exist."""


class PersonalityLoader:
    """Load master personality plus optional provider-specific preset."""

    def __init__(self, personality_dir: Path | None = None, state_dir: Path | None = None) -> None:
        self.personality_dir = personality_dir or Path.home() / ".jules" / "personality"
        self.state_dir = state_dir or Path.home() / ".jules" / "state"

    def load(self, provider: str | None = None) -> str:
        """Return master.md plus `{provider}.md` when present.

        Raises:
            MasterPersonalityMissingError: If master.md does not exist.
        """
        master_path = self.personality_dir / "master.md"
        try:
            master = master_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise MasterPersonalityMissingError(
                f"Master personality file is required: {master_path}"
            ) from exc
        preset = self._read_optional(self.personality_dir / f"{provider}.md") if provider else ""
        return "\n\n".join(part for part in (master, preset) if part).strip()

    def check_version(self) -> str | None:
        """Persist and compare the current master.md hash; return warning on change."""
        master_path = self.personality_dir / "master.md"
        master = self._read_optional(master_path)
        if not master:
            return None

        current_hash = sha256(master.encode("utf-8")).hexdigest()
        state_path = self.state_dir / "personality_version"
        previous_hash = self._read_optional(state_path)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(current_hash, encoding="utf-8")

        if previous_hash and previous_hash != current_hash:
            warning = "Personality master.md changed since last Jules session."
            logger.warning(warning)
            return warning
        return None

    @staticmethod
    def _read_optional(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""
