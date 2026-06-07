"""Environment diagnostic commands for Jules.

Refer to JULES.md section `COMANDO jules doctor` for more details.
"""

from __future__ import annotations

import getpass
import importlib
import os
import shutil
import subprocess
import sys
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jules.core.config import load_config
from jules.linux.watcher import INOTIFY_MAX_USER_WATCHES_PATH, INOTIFY_MIN_WATCHES, INOTIFY_FIX_COMMAND
from jules.memory.persistent import DEFAULT_SQLITE_PATH

# EpisodicMemory receives its DB path from callers; doctor uses Jules' current default vector store.
DEFAULT_LANCEDB_PATH = Path.home() / ".jules" / "vectors"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = PROJECT_ROOT / "alembic.ini"


@dataclass(slots=True)
class CheckResult:
    name: str
    status: Literal["ok", "fail", "warn"]
    message: str


@dataclass(slots=True)
class DoctorReport:
    results: list[CheckResult]
    exit_code: int


def _expected_ollama_user() -> str:
    return os.environ.get("JULES_OLLAMA_USER") or os.environ.get("SUDO_USER") or getpass.getuser()


def check_ollama() -> CheckResult:
    # Check if systemctl is active
    try:
        res = subprocess.run(
            ["systemctl", "is-active", "ollama"],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_active = res.stdout.strip() == "active"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        is_active = False

    if not is_active:
        return CheckResult(
            name="Ollama",
            status="fail",
            message="Ollama service is not active."
        )

    # Get running user
    user = "unknown"
    try:
        res = subprocess.run(
            ["systemctl", "show", "ollama.service", "--property=User"],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in res.stdout.splitlines():
            if line.startswith("User="):
                user = line.split("=", 1)[1].strip() or "root"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass

    # Verify ollama list returns >=1 model
    try:
        res = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode != 0:
            return CheckResult(
                name="Ollama",
                status="fail",
                message="Failed to list Ollama models."
            )
        # Parse models
        models = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or "NAME" in line:
                continue
            parts = line.split()
            if parts:
                models.append(parts[0])
        if not models:
            return CheckResult(
                name="Ollama",
                status="fail",
                message="Ollama is active but no models are downloaded."
            )
        first_model = models[0]
        expected_user = _expected_ollama_user()
        if user != expected_user:
            return CheckResult(
                name="Ollama",
                status="warn",
                message=f"activo, {first_model} disponible, pero usuario {user} != esperado {expected_user}"
            )
        return CheckResult(
            name="Ollama",
            status="ok",
            message=f"activo, {first_model} disponible (usuario: {user})"
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
        return CheckResult(
            name="Ollama",
            status="fail",
            message=f"Ollama execution failed: {e}"
        )


def check_antigravity() -> CheckResult:
    path = shutil.which("agy") or shutil.which("antigravity")
    if not path:
        return CheckResult(
            name="Antigravity",
            status="fail",
            message="agy/antigravity no encontrado en PATH"
        )
    return CheckResult(
        name="Antigravity",
        status="ok",
        message="disponible en PATH"
    )


def check_opencode() -> CheckResult:
    path = shutil.which("opencode")
    if not path:
        return CheckResult(
            name="OpenCode",
            status="fail",
            message="opencode not found in PATH"
        )
    try:
        res = subprocess.run(
            ["opencode", "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return CheckResult(
                name="OpenCode",
                status="ok",
                message="disponible en PATH"
            )
        else:
            return CheckResult(
                name="OpenCode",
                status="fail",
                message="opencode exists but --help failed."
            )
    except (OSError, subprocess.SubprocessError) as e:
        return CheckResult(
            name="OpenCode",
            status="fail",
            message=f"Execution failed: {e}"
        )


def check_lancedb() -> CheckResult:
    path = DEFAULT_LANCEDB_PATH
    if not path.is_dir():
        return CheckResult(
            name="LanceDB",
            status="fail",
            message=f"Directory {path} does not exist or is not a directory."
        )
    try:
        lancedb = importlib.import_module("lancedb")
    except ImportError as e:
        return CheckResult(
            name="LanceDB",
            status="fail",
            message=f"LanceDB dependency is not available: {e}"
        )
    try:
        db = lancedb.connect(str(path))
        db.list_tables()
        return CheckResult(
            name="LanceDB",
            status="ok",
            message="vectores OK"
        )
    except Exception as e:
        return CheckResult(
            name="LanceDB",
            status="fail",
            message=f"LanceDB is corrupt or failed to open: {e}"
        )


def check_sqlite() -> CheckResult:
    db_path = DEFAULT_SQLITE_PATH
    if not db_path.is_file():
        return CheckResult(
            name="SQLite",
            status="fail",
            message=f"SQLite database file {db_path} does not exist."
        )
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        return CheckResult(
            name="SQLite",
            status="fail",
            message=f"SQLite database is not readable or corrupt: {e}"
        )

    # Run alembic current and heads
    env = os.environ.copy()
    env["JULES_DATABASE_PATH"] = str(db_path)

    try:
        curr_res = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG_PATH), "current"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
            timeout=5
        )
        if curr_res.returncode != 0:
            return CheckResult(
                name="SQLite",
                status="fail",
                message=f"Alembic current failed: {curr_res.stderr.strip() or curr_res.stdout.strip()}"
            )
        heads_res = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG_PATH), "heads"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
            timeout=5
        )
        if heads_res.returncode != 0:
            return CheckResult(
                name="SQLite",
                status="fail",
                message=f"Alembic heads failed: {heads_res.stderr.strip() or heads_res.stdout.strip()}"
            )

        def extract_revision(output: str) -> str | None:
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                words = line.split()
                if words:
                    return words[0]
            return None

        curr_rev = extract_revision(curr_res.stdout)
        head_rev = extract_revision(heads_res.stdout)

        if curr_rev is None:
            return CheckResult(
                name="SQLite",
                status="fail",
                message="No migrations applied."
            )
        elif curr_rev == head_rev:
            return CheckResult(
                name="SQLite",
                status="ok",
                message=f"migraciones al día (rev: {curr_rev})"
            )
        else:
            return CheckResult(
                name="SQLite",
                status="fail",
                message=f"Database is behind head revision (current: {curr_rev}, head: {head_rev})"
            )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
        return CheckResult(
            name="SQLite",
            status="fail",
            message=f"Alembic checks failed: {e}"
        )


def check_inotify(min_watches: int = INOTIFY_MIN_WATCHES) -> CheckResult:
    try:
        if not INOTIFY_MAX_USER_WATCHES_PATH.exists():
            return CheckResult(
                name="inotify",
                status="warn",
                message=f"Could not read inotify limit from {INOTIFY_MAX_USER_WATCHES_PATH} (file does not exist)"
            )
        val_str = INOTIFY_MAX_USER_WATCHES_PATH.read_text(encoding="utf-8").strip()
        max_watches = int(val_str)
    except (OSError, ValueError) as e:
        return CheckResult(
            name="inotify",
            status="warn",
            message=f"Could not read inotify limit: {e}"
        )

    if max_watches < min_watches:
        return CheckResult(
            name="inotify",
            status="warn",
            message=f"{max_watches} watches (recomendado: \u2265{min_watches}) \u2014 aumentar con: {INOTIFY_FIX_COMMAND}"
        )
    else:
        return CheckResult(
            name="inotify",
            status="ok",
            message=f"{max_watches} watches"
        )


def check_virtualenv() -> CheckResult:
    if sys.prefix != sys.base_prefix:
        return CheckResult(
            name="Virtualenv",
            status="ok",
            message="activo (.venv)"
        )
    else:
        return CheckResult(
            name="Virtualenv",
            status="fail",
            message="Running outside virtual environment."
        )


def check_permissions() -> CheckResult:
    jules_home = Path.home() / ".jules"
    if not jules_home.exists():
        parent = jules_home.parent
        if os.access(parent, os.W_OK):
            return CheckResult(
                name="~/.jules/",
                status="ok",
                message="permisos OK"
            )
        else:
            return CheckResult(
                name="~/.jules/",
                status="fail",
                message=f"Parent directory {parent} is not writable."
            )

    non_writable = []
    if not os.access(jules_home, os.W_OK):
        non_writable.append(str(jules_home))

    try:
        for p in jules_home.rglob("*"):
            if p.is_dir():
                if not os.access(p, os.W_OK):
                    non_writable.append(str(p))
    except Exception as e:
        return CheckResult(
            name="~/.jules/",
            status="fail",
            message=f"Error listing subdirectories: {e}"
        )

    if non_writable:
        return CheckResult(
            name="~/.jules/",
            status="fail",
            message=f"Non-writable directories: {', '.join(non_writable)}"
        )
    return CheckResult(
        name="~/.jules/",
        status="ok",
        message="permisos OK"
    )


def check_scoring() -> CheckResult:
    log_path = Path.home() / ".jules" / "logs" / "scoring.log"
    if not log_path.is_file():
        return CheckResult(
            name="Scoring",
            status="warn",
            message="sin datos suficientes para evaluar salud"
        )
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        last_line = ""
        for line in reversed(lines):
            line = line.strip()
            if line:
                last_line = line
                break
        if not last_line:
            return CheckResult(
                name="Scoring",
                status="warn",
                message="sin datos suficientes para evaluar salud"
            )

        last_line_lower = last_line.lower()
        if "healthy" in last_line_lower or "saludable" in last_line_lower:
            return CheckResult(
                name="Scoring",
                status="ok",
                message="healthy"
            )
        elif any(x in last_line_lower for x in ("degenerate", "degraded", "degradado", "fail")):
            return CheckResult(
                name="Scoring",
                status="fail",
                message="scoring en modo degradado"
            )
        else:
            return CheckResult(
                name="Scoring",
                status="warn",
                message="sin datos suficientes para evaluar salud"
            )
    except Exception as e:
        return CheckResult(
            name="Scoring",
            status="warn",
            message=f"Error reading scoring log: {e}"
        )


def check_shell() -> CheckResult:
    shell_path = os.environ.get("SHELL", "unknown")
    shell_name = os.path.basename(shell_path)
    return CheckResult(
        name="Shell",
        status="ok",
        message=f"{shell_name} detectado"
    )


def _configured_inotify_min_watches() -> tuple[int, CheckResult | None]:
    try:
        return load_config().doctor.inotify_min_watches, None
    except Exception as e:
        return INOTIFY_MIN_WATCHES, CheckResult(
            name="Config",
            status="warn",
            message=f"Could not load config.toml ({e}); using default doctor.inotify_min_watches={INOTIFY_MIN_WATCHES}",
        )


def run_all_checks() -> DoctorReport:
    inotify_min_watches, config_result = _configured_inotify_min_watches()
    results = [
        check_ollama(),
        check_antigravity(),
        check_opencode(),
        check_lancedb(),
        check_sqlite(),
        check_inotify(inotify_min_watches),
        check_virtualenv(),
        check_permissions(),
        check_scoring(),
        check_shell(),
    ]
    if config_result is not None:
        results.insert(0, config_result)
    exit_code = 0
    for r in results:
        if r.status in ("fail", "warn"):
            exit_code = 1
            break
    return DoctorReport(results=results, exit_code=exit_code)
