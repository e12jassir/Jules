from pathlib import Path

import pytest

from jules.personality.loader import MasterPersonalityMissingError, PersonalityLoader


def test_load_master_and_provider_preset(tmp_path: Path) -> None:
    personality = tmp_path / "personality"
    state = tmp_path / "state"
    personality.mkdir()
    (personality / "master.md").write_text("MASTER", encoding="utf-8")
    (personality / "antigravity.md").write_text("PRESET", encoding="utf-8")

    loader = PersonalityLoader(personality, state)

    assert loader.load("antigravity") == "MASTER\n\nPRESET"
    assert loader.load("missing") == "MASTER"


def test_missing_master_raises_and_check_version_returns_none(tmp_path: Path) -> None:
    loader = PersonalityLoader(tmp_path / "missing", tmp_path / "state")
    with pytest.raises(MasterPersonalityMissingError):
        loader.load("antigravity")
    assert loader.check_version() is None


def test_check_version_warns_on_master_change(tmp_path: Path) -> None:
    personality = tmp_path / "personality"
    state = tmp_path / "state"
    personality.mkdir()
    master = personality / "master.md"
    master.write_text("v1", encoding="utf-8")
    loader = PersonalityLoader(personality, state)

    assert loader.check_version() is None
    master.write_text("v2", encoding="utf-8")

    assert loader.check_version() == "Personality master.md changed since last Jules session."


def test_verify_identity_coherence_clean() -> None:
    from jules.personality.coherence import verify_identity_coherence

    clean_response = "El archivo se encuentra en /etc/hosts y la configuración está correcta."
    assert verify_identity_coherence(clean_response) == 1.0


def test_verify_identity_coherence_penalizes_servility() -> None:
    from jules.personality.coherence import verify_identity_coherence

    servile_response = "¡Claro que sí! Estaré encantado de ayudarte en todo lo que necesites."
    score = verify_identity_coherence(servile_response)
    assert score < 1.0

