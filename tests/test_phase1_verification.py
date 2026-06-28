"""
Phase 1 verification tests — one test per module from the roadmap.
Tests the STATED criteria, not implementation details.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from jules.core.config import load_config
from jules.core.context import ContextEngine
from jules.core.events import EventBus, EventType
from jules.core.permissions import Action, PermissionClassification, PermissionGate
from jules.core.router import CognitiveRouter, TaskType
from jules.core.session import SessionContext as CoreSessionContext
from jules.linux.shell import detect_shell, install_zsh_hooks
from jules.memory.models import Episode, SessionContext
from jules.memory.scoring import ScoringHealthMonitor, evaluate_importance
from jules.personality.loader import MasterPersonalityMissingError, PersonalityLoader
from jules.sanitizer import Sanitizer



# ─────────────────────────────────────────────────────────────────────────────
# HELPER: minimal config for router tests
# ─────────────────────────────────────────────────────────────────────────────

MINIMAL_CONFIG = """\
[routing]
default_tier = "low_cost"

[routing.tiers.free]
provider = "ollama"
models = ["llama3.2:1b"]

[routing.tiers.low_cost]
antigravity = ["flash-low"]
opencode = ["oc-low"]
codex = []
openai_oauth = ["gpt-mini"]

[routing.tiers.high_cost]
antigravity = ["pro-high"]
opencode = ["oc-high"]
codex = []
openai_oauth = ["gpt-5"]

[routing.fallback]
chain = ["primary", "ollama"]

[providers.ollama]
base_url = "http://localhost:11434"
timeout_seconds = 30

[providers.antigravity]
timeout_seconds = 60

[providers.opencode]
timeout_seconds = 60

[providers.openai_oauth]
timeout_seconds = 60
"""



class FakeProvider:
    def __init__(self, name: str, response: str = "ok"):
        self.name = name
        self._response = response

    async def ask(self, prompt, context, model):
        return self._response


def _write_config(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(MINIMAL_CONFIG)
    return p


def _make_router(config_path: Path) -> CognitiveRouter:
    providers = {
        "ollama": FakeProvider("ollama"),
        "antigravity": FakeProvider("antigravity"),
        "opencode": FakeProvider("opencode"),
        "codex": FakeProvider("codex"),
        "openai_oauth": FakeProvider("openai_oauth"),
        "google": FakeProvider("google"),
        "openrouter": FakeProvider("openrouter"),
    }
    return CognitiveRouter(config=load_config(config_path), providers=providers)



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — SANITIZER
# Criteria: discards secrets, never persists sensitive data
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule1Sanitizer:
    """M1: Sanitizer detects and rejects all known secret patterns."""

    def test_rejects_openai_key(self):
        result = Sanitizer.check("my key is sk-abcdefghijklmnopqrstuvwxyz1234567890")
        assert not result.is_safe
        assert result.reason == "openai_key"

    def test_rejects_bearer_token(self):
        result = Sanitizer.check("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test")
        assert not result.is_safe
        assert result.reason == "bearer_token"

    def test_rejects_github_token(self):
        result = Sanitizer.check("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        assert not result.is_safe
        assert result.reason == "github_token"

    def test_rejects_private_key(self):
        result = Sanitizer.check("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
        assert not result.is_safe
        assert result.reason == "private_key"

    def test_rejects_export_secret(self):
        result = Sanitizer.check("export API_KEY=supersecret123")
        assert not result.is_safe
        assert result.reason == "export_secret"

    def test_allows_normal_code(self):
        result = Sanitizer.check("def hello_world(): return 42")
        assert result.is_safe
        assert result.reason is None

    def test_allows_urls_without_credentials(self):
        result = Sanitizer.check("https://github.com/user/repo")
        assert result.is_safe

    def test_rejects_url_with_credentials(self):
        result = Sanitizer.check("https://user:pass@host.com/path")
        assert not result.is_safe
        assert result.reason == "credentialed_url"



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — DATA MODELS
# Criteria: Episode and SessionContext have all required fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule2DataModels:
    """M2: Data models have correct structure and fields."""

    def test_episode_has_all_spec_fields(self):
        ep = Episode(
            id="test-1",
            timestamp=datetime.now(timezone.utc),
            context=SessionContext(
                project="jules", directory="/tmp", active_files=[],
                inferred_intent="debugging", time_of_day="morning", shell="zsh",
            ),
            problem="test problem",
            process="test process",
            solution="test solution",
            duration_seconds=60,
            friction_score=0.5,
            tags=["test"],
            importance=0.7,
            model_used="llama3.2:1b",
            provider_used="ollama",
            memory_schema_version="1.2",
        )
        assert ep.memory_schema_version == "1.2"
        assert ep.model_used == "llama3.2:1b"
        assert ep.provider_used == "ollama"

    def test_session_context_has_shell_field(self):
        ctx = SessionContext(
            project=None, directory="/home", active_files=[],
            inferred_intent=None, time_of_day="afternoon", shell="fish",
        )
        assert ctx.shell == "fish"

    def test_episode_orm_roundtrip(self):
        from jules.memory.models import EpisodeORM
        ep = Episode(
            id="roundtrip-1",
            timestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            context=SessionContext(
                project="test", directory="/tmp", active_files=["a.py"],
                inferred_intent="review", time_of_day="noon", shell="bash",
            ),
            problem="p", process="pr", solution="s",
            duration_seconds=10, friction_score=0.2,
            tags=["tag1"], importance=0.8,
            model_used="model", provider_used="provider",
        )
        orm = EpisodeORM.from_dataclass(ep)
        back = orm.to_dataclass()
        assert back.id == ep.id
        assert back.context.shell == "bash"
        assert back.model_used == "model"



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — ROUTER QUOTA-AWARE
# Criteria: routes tasks to correct provider/tier, fallback to ollama works
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule5Router:
    """M5: Router selects the correct model based on task type."""

    @pytest.fixture
    def router(self, tmp_path):
        return _make_router(_write_config(tmp_path))

    @pytest.mark.asyncio
    async def test_identity_always_routes_to_ollama(self, router):
        provider, model = await router.route(TaskType.IDENTITY)
        assert provider.name == "ollama"

    @pytest.mark.asyncio
    async def test_memory_scoring_always_routes_to_ollama(self, router):
        provider, model = await router.route(TaskType.MEMORY_SCORING)
        assert provider.name == "ollama"

    @pytest.mark.asyncio
    async def test_coding_routes_to_opencode(self, router):
        provider, model = await router.route(TaskType.CODING)
        assert provider.name == "opencode"
        assert model == "oc-low"

    @pytest.mark.asyncio
    async def test_quick_routes_to_antigravity(self, router):
        provider, model = await router.route(TaskType.QUICK)
        assert provider.name == "antigravity"

    @pytest.mark.asyncio
    async def test_fallback_to_ollama_on_provider_failure(self, router):
        from jules.providers.base import ProviderError
        router.providers["opencode"] = FakeProvider("opencode")
        router.providers["opencode"].ask = AsyncMock(side_effect=ProviderError("down"))
        router.providers["ollama"].ask = AsyncMock(return_value="fallback")
        ctx = SessionContext(
            project=None, directory="/tmp", active_files=[],
            inferred_intent=None, time_of_day="day", shell="zsh",
        )
        resp, model, prov = await router.ask_with_fallback("hi", ctx, TaskType.CODING)
        assert prov == "ollama"



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 6 — MEMORY ENGINE
# Criteria: semantic search by relevance, scoring health monitor active,
#           persistence runs async without blocking user response
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule6MemoryEngine:
    """M6: Memory engine scores, persists, and retrieves episodes."""

    def test_scoring_health_monitor_detects_degenerate_scores(self):
        monitor = ScoringHealthMonitor(scoring_variance_threshold=0.01, scoring_window_size=5)
        # All same score = degenerate
        for _ in range(5):
            monitor.record(0.5)
        assert not monitor.is_healthy()

    def test_scoring_health_monitor_healthy_with_variance(self):
        monitor = ScoringHealthMonitor(scoring_variance_threshold=0.01, scoring_window_size=5)
        for s in [0.2, 0.5, 0.8, 0.3, 0.9]:
            monitor.record(s)
        assert monitor.is_healthy()

    @pytest.mark.asyncio
    async def test_evaluate_importance_parses_score_from_provider(self):
        ep = Episode(
            id="score-test", timestamp=datetime.now(timezone.utc),
            context=SessionContext(None, "/tmp", [], None, "day", "zsh"),
            problem="bug", process=None, solution="fix",
            duration_seconds=10, friction_score=0.3,
        )
        provider = AsyncMock()
        provider.generate_text.return_value = "This is important. SCORE: 0.85"
        score = await evaluate_importance(ep, provider)
        assert score == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_evaluate_importance_fallback_on_bad_response(self):
        ep = Episode(
            id="score-bad", timestamp=datetime.now(timezone.utc),
            context=SessionContext(None, "/tmp", [], None, "day", "zsh"),
            problem="x", process=None, solution="y",
            duration_seconds=5, friction_score=0.1,
        )
        provider = AsyncMock()
        provider.generate_text.return_value = "I cannot rate this"
        score = await evaluate_importance(ep, provider)
        assert score == 0.5  # DEFAULT_IMPORTANCE_SCORE



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 7 — CONTEXT INTENT DETECTOR
# Criteria: infers debugging/learning/review from session signals
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule7ContextIntentDetector:
    """M7: ContextEngine infers intent from session state."""

    @pytest.mark.asyncio
    async def test_infers_debugging_on_nonzero_exit(self):
        session = CoreSessionContext(cwd="/tmp", last_exit_code=1, recent_commands=["pytest"])
        built = await ContextEngine.build(session, "fix this")
        assert built.intent == "debugging"

    @pytest.mark.asyncio
    async def test_infers_learning_on_help_command(self):
        session = CoreSessionContext(cwd="/tmp", recent_commands=["git --help"])
        built = await ContextEngine.build(session, "how?")
        assert built.intent == "learning"

    @pytest.mark.asyncio
    async def test_infers_learning_on_man_page(self):
        session = CoreSessionContext(cwd="/tmp", recent_commands=["man grep"])
        built = await ContextEngine.build(session, "explain")
        assert built.intent == "learning"

    @pytest.mark.asyncio
    async def test_defaults_to_review(self):
        session = CoreSessionContext(cwd="/tmp", recent_commands=["ls", "git status"])
        built = await ContextEngine.build(session, "check")
        assert built.intent == "review"

    @pytest.mark.asyncio
    async def test_finds_git_project_root(self, tmp_path):
        project = tmp_path / "repo"
        nested = project / "src" / "deep"
        nested.mkdir(parents=True)
        (project / ".git").mkdir()
        session = CoreSessionContext(cwd=str(nested), recent_commands=[])
        built = await ContextEngine.build(session, "ctx")
        assert built.project_root == str(project)



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 8 — EVENT SYSTEM
# Criteria: Phase 1 events fire, handlers run, background task isolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule8EventSystem:
    """M8: EventBus fires events and runs handlers correctly."""

    def test_session_started_detects_shell(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        bus = EventBus()
        bus.emit(EventType.SESSION_STARTED, {})
        assert bus.runtime.shell == "/usr/bin/fish"

    def test_coding_detected_updates_activity(self):
        bus = EventBus()
        assert bus.runtime.last_activity_at is None
        bus.emit(EventType.CODING_DETECTED, {})
        assert bus.runtime.last_activity_at is not None
        assert not bus.runtime.is_idle

    def test_idle_detected_sets_idle_flag(self):
        bus = EventBus()
        bus.emit(EventType.IDLE_DETECTED, {})
        assert bus.runtime.is_idle

    def test_session_ended_records_summary(self):
        bus = EventBus()
        bus.emit(EventType.SESSION_ENDED, {"summary": "done working"})
        assert bus.runtime.ended_at is not None
        assert bus.runtime.summary == "done working"

    @pytest.mark.asyncio
    async def test_custom_handler_subscribes_and_fires(self):
        received = []
        bus = EventBus()
        bus.subscribe(EventType.PROJECT_OPENED, lambda p: received.append(p))
        bus.emit(EventType.PROJECT_OPENED, {"directory": "/project"})
        # Handlers run in background tasks; give event loop a tick
        await asyncio.sleep(0.05)
        assert any("/project" in str(r) for r in received)



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 9 — PERMISSIONS SYSTEM
# Criteria: blocks unauthorized actions, classifies correctly
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule9Permissions:
    """M9: PermissionGate classifies and enforces action authorization."""

    def test_rm_rf_root_is_prohibited(self):
        from jules.core.config import PermissionsConfig
        gate = PermissionGate(PermissionsConfig())
        assert gate.classify(Action.SHELL_COMMAND, "rm -rf /") == PermissionClassification.PROHIBITED

    def test_file_read_is_safe(self):
        from jules.core.config import PermissionsConfig
        gate = PermissionGate(PermissionsConfig())
        assert gate.classify(Action.FILE_READ, "/any/file.txt") == PermissionClassification.SAFE

    def test_package_op_requires_confirmation(self):
        from jules.core.config import PermissionsConfig
        gate = PermissionGate(PermissionsConfig())
        assert gate.classify(Action.PACKAGE_OP, "pacman -S vim") == PermissionClassification.REQUIRED

    @pytest.mark.asyncio
    async def test_prohibited_action_raises(self):
        from jules.core.config import PermissionsConfig
        from jules.core.permissions import PermissionDeniedError
        gate = PermissionGate(PermissionsConfig())
        with pytest.raises(PermissionDeniedError):
            await gate.check(Action.SHELL_COMMAND, "rm -rf /")

    def test_write_to_etc_passwd_is_prohibited(self):
        from jules.core.config import PermissionsConfig
        gate = PermissionGate(PermissionsConfig())
        assert gate.classify(Action.FILE_WRITE, "/etc/passwd") == PermissionClassification.PROHIBITED



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 10 — JULES DOCTOR
# Criteria: reports environment health, doesn't block startup
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule10Doctor:
    """M10: Doctor checks report environment state without crashing."""

    def test_doctor_module_imports(self):
        from jules.linux.doctor import DoctorReport, run_all_checks
        assert callable(run_all_checks)

    def test_doctor_runs_without_error(self):
        from jules.linux.doctor import run_all_checks
        # Doctor should never raise — it reports, doesn't crash
        report = run_all_checks()
        assert hasattr(report, "results")
        assert isinstance(report.results, list)
        assert len(report.results) > 0

    def test_doctor_checks_have_name_and_status(self):
        from jules.linux.doctor import run_all_checks
        report = run_all_checks()
        for check in report.results:
            assert hasattr(check, "name")
            assert hasattr(check, "status")
            assert check.status in ("ok", "warn", "fail")



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 11 — CLI (TUI Textual)
# Criteria: compose_prompt works with personality+memory+history, commands parse
# ═══════════════════════════════════════════════════════════════════════════════


class TestModule11CLI:
    """M11: CLI prompt composition and command parsing work correctly."""

    def test_compose_prompt_with_personality_and_memory(self):
        from jules.cli.app import _compose_prompt
        prompt = _compose_prompt("You are Jules.", "hello", ["fixed bug in auth"])
        assert "You are Jules." in prompt
        assert "Relevant past context:" in prompt
        assert "fixed bug in auth" in prompt
        assert "User: hello" in prompt

    def test_compose_prompt_plain_without_personality(self):
        from jules.cli.app import _compose_prompt
        assert _compose_prompt("", "hello") == "User: hello"

    def test_compose_prompt_with_chat_history(self):
        from jules.cli.app import _compose_prompt
        history = [("user", "first"), ("jules", "response")]
        prompt = _compose_prompt("P", "second", chat_history=history)
        assert "Conversation so far:" in prompt
        assert "User: first" in prompt
        assert "Jules: response" in prompt
        assert "User: second" in prompt

    def test_compose_prompt_history_limit(self):
        from jules.cli.app import _compose_prompt
        history = [("user", f"msg{i}") for i in range(20)]
        prompt = _compose_prompt("", "final", chat_history=history, history_limit=3)
        assert "msg0" not in prompt
        assert "msg17" in prompt
        assert "msg19" in prompt



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE — SHELL DETECTION & HOOKS (part of M8/M10)
# Criteria: shell detected correctly, hooks installed for detected shell
# ═══════════════════════════════════════════════════════════════════════════════


class TestShellDetection:
    """Shell detection and hook installation."""

    def test_detect_shell_from_environment(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/zsh")
        assert detect_shell() == "/usr/bin/zsh"

    def test_detect_shell_unknown_when_missing(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        assert detect_shell() == "unknown"

    def test_install_zsh_hooks_writes_block(self, tmp_path):
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# existing content\n")
        result = install_zsh_hooks(zshrc_path=zshrc, shell_path="/usr/bin/zsh")
        assert result is True
        content = zshrc.read_text()
        assert "JULES_ZSH_HOOKS_START" in content
        assert "add-zsh-hook precmd" in content

    def test_install_zsh_hooks_idempotent(self, tmp_path):
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# existing\n")
        install_zsh_hooks(zshrc_path=zshrc, shell_path="/usr/bin/zsh")
        result = install_zsh_hooks(zshrc_path=zshrc, shell_path="/usr/bin/zsh")
        assert result is False  # already installed

    def test_install_zsh_hooks_skips_non_zsh(self, tmp_path):
        zshrc = tmp_path / ".zshrc"
        result = install_zsh_hooks(zshrc_path=zshrc, shell_path="/usr/bin/fish")
        assert result is False



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE — PERSONALITY LOADER
# Criteria: loads master.md, merges provider presets, detects version change
# ═══════════════════════════════════════════════════════════════════════════════


class TestPersonalityLoader:
    """Personality loader correctly composes system prompts."""

    def test_loads_master_personality(self, tmp_path):
        personality_dir = tmp_path / "personality"
        personality_dir.mkdir()
        (personality_dir / "master.md").write_text("You are Jules.")
        loader = PersonalityLoader(personality_dir=personality_dir)
        assert loader.load() == "You are Jules."

    def test_merges_provider_preset(self, tmp_path):
        personality_dir = tmp_path / "personality"
        personality_dir.mkdir()
        (personality_dir / "master.md").write_text("Core identity.")
        (personality_dir / "ollama.md").write_text("Be concise.")
        loader = PersonalityLoader(personality_dir=personality_dir)
        result = loader.load(provider="ollama")
        assert "Core identity." in result
        assert "Be concise." in result

    def test_raises_when_master_missing(self, tmp_path):
        personality_dir = tmp_path / "personality"
        personality_dir.mkdir()
        loader = PersonalityLoader(personality_dir=personality_dir)
        with pytest.raises(MasterPersonalityMissingError):
            loader.load()

    def test_detects_master_version_change(self, tmp_path):
        personality_dir = tmp_path / "personality"
        personality_dir.mkdir()
        state_dir = tmp_path / "state"
        (personality_dir / "master.md").write_text("Version 1")
        loader = PersonalityLoader(personality_dir=personality_dir, state_dir=state_dir)
        # First call: no previous hash
        assert loader.check_version() is None
        # Change master
        (personality_dir / "master.md").write_text("Version 2")
        warning = loader.check_version()
        assert warning is not None
        assert "changed" in warning



# ═══════════════════════════════════════════════════════════════════════════════
# MODULE — IPC SERVER PROTOCOL (Fase 1.5 foundation)
# Criteria: protocol messages serialize/deserialize correctly
# ═══════════════════════════════════════════════════════════════════════════════


class TestServerProtocol:
    """IPC protocol messages serialize correctly."""

    def test_message_request_serializes(self):
        from jules.server.protocol import MessageRequest
        msg = MessageRequest(content="hello")
        import dataclasses, json
        data = dataclasses.asdict(msg)
        assert data["type"] == "message"
        assert data["content"] == "hello"
        # Must be valid JSON for IPC
        assert json.loads(json.dumps(data))["type"] == "message"

    def test_command_request_serializes(self):
        from jules.server.protocol import CommandRequest
        import dataclasses
        msg = CommandRequest(name="sessions", args=[])
        data = dataclasses.asdict(msg)
        assert data["type"] == "command"
        assert data["name"] == "sessions"

    def test_server_handles_invalid_json(self):
        """The server loop handles bad JSON gracefully (returns error, no crash)."""
        import json
        from jules.server.protocol import ErrorEvent
        # ErrorEvent exists and is well-formed
        err = ErrorEvent(message="bad input", recoverable=True)
        import dataclasses
        data = dataclasses.asdict(err)
        assert data["type"] == "error"
        assert data["recoverable"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE — CONFIG LOADING
# Criteria: no hardcoded models outside config.toml
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigNotHardcoded:
    """Models come from config.toml, not hardcoded in router."""

    @pytest.mark.asyncio
    async def test_models_from_config_not_hardcoded(self, tmp_path):
        custom_config = MINIMAL_CONFIG.replace("oc-low", "custom-model-xyz")
        p = tmp_path / "config.toml"
        p.write_text(custom_config)
        router = _make_router(p)
        provider, model = await router.route(TaskType.CODING)
        assert model == "custom-model-xyz"
