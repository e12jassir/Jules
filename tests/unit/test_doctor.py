import importlib
import json
import os
import types
import shutil
from typing import Any
import subprocess
import sys
import sqlite3
import tomllib
from pathlib import Path

import pytest

from jules.linux.doctor import (
    CheckResult,
    DoctorReport,
    check_ollama,
    check_antigravity,
    check_opencode,
    check_lancedb,
    check_sqlite,
    check_inotify,
    check_virtualenv,
    check_permissions,
    check_scoring,
    check_shell,
    run_all_checks,
)


def test_check_ollama_ok(monkeypatch):
    monkeypatch.setenv("JULES_OLLAMA_USER", "esteban")

    def mock_run(args, **kwargs):
        class MockCompletedProcess:
            def __init__(self, stdout, returncode=0):
                self.stdout = stdout
                self.returncode = returncode

        if args == ["systemctl", "is-active", "ollama"]:
            return MockCompletedProcess("active\n")
        elif args == ["systemctl", "show", "ollama.service", "--property=User"]:
            return MockCompletedProcess("User=esteban\n")
        elif args == ["ollama", "list"]:
            return MockCompletedProcess(
                "NAME               ID           SIZE      MODIFIED\n"
                "llama3.2:1b        d3790172e276 2.0 GB    3 weeks ago\n"
            )
        return MockCompletedProcess("")

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = check_ollama()
    assert res.status == "ok"
    assert "llama3.2:1b" in res.message
    assert "esteban" in res.message


def test_check_ollama_user_mismatch_warns(monkeypatch):
    monkeypatch.setenv("JULES_OLLAMA_USER", "esteban")

    def mock_run(args, **kwargs):
        class MockCompletedProcess:
            def __init__(self, stdout, returncode=0):
                self.stdout = stdout
                self.returncode = returncode

        if args == ["systemctl", "is-active", "ollama"]:
            return MockCompletedProcess("active\n")
        elif args == ["systemctl", "show", "ollama.service", "--property=User"]:
            return MockCompletedProcess("User=root\n")
        elif args == ["ollama", "list"]:
            return MockCompletedProcess(
                "NAME               ID           SIZE      MODIFIED\n"
                "llama3.2:1b        d3790172e276 2.0 GB    3 weeks ago\n"
            )
        return MockCompletedProcess("")

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = check_ollama()
    assert res.status == "warn"
    assert "root" in res.message
    assert "esteban" in res.message


def test_check_ollama_inactive(monkeypatch):
    def mock_run(args, **kwargs):
        class MockCompletedProcess:
            def __init__(self, stdout, returncode=0):
                self.stdout = stdout
                self.returncode = returncode

        if args == ["systemctl", "is-active", "ollama"]:
            return MockCompletedProcess("inactive\n")
        return MockCompletedProcess("")

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = check_ollama()
    assert res.status == "fail"
    assert "not active" in res.message


def test_check_antigravity_ok(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/antigravity")

    def mock_run(args, **kwargs):
        class MockCompletedProcess:
            returncode = 0
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = check_antigravity()
    assert res.status == "ok"


def test_check_antigravity_fail(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    res = check_antigravity()
    assert res.status == "fail"


def test_check_opencode_ok(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/opencode")

    def mock_run(args, **kwargs):
        class MockCompletedProcess:
            returncode = 0
        return MockCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = check_opencode()
    assert res.status == "ok"


def test_check_opencode_fail(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    res = check_opencode()
    assert res.status == "fail"


def test_check_lancedb(monkeypatch):
    # Case 1: not a dir
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    res = check_lancedb()
    assert res.status == "fail"

    # Case 2: is a dir, connect succeeds
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    class MockDB:
        def list_tables(self):
            return []

    fake_lancedb = types.SimpleNamespace(connect=lambda path: MockDB())
    monkeypatch.setitem(sys.modules, "lancedb", fake_lancedb)
    res = check_lancedb()
    assert res.status == "ok"

    # Case 3: connect fails
    def mock_connect_fail(path):
        raise RuntimeError("db error")

    fake_lancedb.connect = mock_connect_fail
    res = check_lancedb()
    assert res.status == "fail"


def test_check_sqlite(monkeypatch):
    # Mock file checks and sqlite connection
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    class MockCursor:
        def execute(self, query):
            pass

    class MockConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def execute(self, query):
            return MockCursor()

    monkeypatch.setattr(sqlite3, "connect", lambda path: MockConn())

    # Case 1: current matches head
    def mock_run_ok(args, **kwargs):
        class MockCompletedProcess:
            def __init__(self, stdout, returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        if "current" in args:
            return MockCompletedProcess("fed68f886721 (head)\n")
        elif "heads" in args:
            return MockCompletedProcess("fed68f886721\n")
        return MockCompletedProcess("")

    seen_args = []

    def mock_run_ok_capture(args, **kwargs):
        seen_args.append(args)
        return mock_run_ok(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_ok_capture)
    res = check_sqlite()
    assert res.status == "ok"
    assert "fed68f886721" in res.message
    assert seen_args[0][:3] == [sys.executable, "-m", "alembic"]
    assert seen_args[1][:3] == [sys.executable, "-m", "alembic"]

    # Case 2: current is behind head
    def mock_run_behind(args, **kwargs):
        class MockCompletedProcess:
            def __init__(self, stdout, returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        if "current" in args:
            return MockCompletedProcess("db91a0ae1c2b\n")
        elif "heads" in args:
            return MockCompletedProcess("fed68f886721\n")
        return MockCompletedProcess("")

    monkeypatch.setattr(subprocess, "run", mock_run_behind)
    res = check_sqlite()
    assert res.status == "fail"
    assert "behind" in res.message


def test_check_sqlite_reports_alembic_failure(monkeypatch):
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    class MockConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def execute(self, query):
            pass

    monkeypatch.setattr(sqlite3, "connect", lambda path: MockConn())

    class MockCompletedProcess:
        stdout = ""
        stderr = "missing config"
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockCompletedProcess())

    res = check_sqlite()
    assert res.status == "fail"
    assert "Alembic current failed" in res.message
    assert "missing config" in res.message


def test_check_inotify(monkeypatch, tmp_path):
    tmp_file = tmp_path / "max_user_watches"
    import jules.linux.doctor
    monkeypatch.setattr(jules.linux.doctor, "INOTIFY_MAX_USER_WATCHES_PATH", tmp_file)

    # Case 1: low value
    tmp_file.write_text("8192", encoding="utf-8")
    res = check_inotify()
    assert res.status == "warn"
    assert "8192" in res.message
    assert "fs.inotify.max_user_watches" in res.message

    # Case 2: high value for default threshold
    tmp_file.write_text("65536", encoding="utf-8")
    res = check_inotify()
    assert res.status == "ok"
    assert "65536" in res.message

    # Case 3: config can raise the threshold
    res = check_inotify(min_watches=131072)
    assert res.status == "warn"
    assert "131072" in res.message


def test_check_virtualenv(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "/foo")
    monkeypatch.setattr(sys, "base_prefix", "/foo")
    res = check_virtualenv()
    assert res.status == "fail"

    monkeypatch.setattr(sys, "prefix", "/foo/bar")
    monkeypatch.setattr(sys, "base_prefix", "/foo")
    res = check_virtualenv()
    assert res.status == "ok"


def test_check_permissions(monkeypatch, tmp_path):
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    jules_dir = fake_home / ".jules"
    jules_dir.mkdir()

    sub1 = jules_dir / "memory"
    sub1.mkdir()

    sub2 = jules_dir / "logs"
    sub2.mkdir()

    res = check_permissions()
    assert res.status == "ok"

    # Mock access to make sub2 non-writable
    orig_access = os.access

    def mock_access(path, mode):
        if str(path) == str(sub2) and mode == os.W_OK:
            return False
        return orig_access(path, mode)

    monkeypatch.setattr(os, "access", mock_access)

    res = check_permissions()
    assert res.status == "fail"
    assert str(sub2) in res.message


def test_check_scoring(monkeypatch, tmp_path):
    fake_home = tmp_path / "fake_home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    log_dir = fake_home / ".jules" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "scoring.log"

    # Case 1: absent
    res = check_scoring()
    assert res.status == "warn"

    # Case 2: empty
    log_file.write_text("", encoding="utf-8")
    res = check_scoring()
    assert res.status == "warn"

    # Case 3: healthy
    log_file.write_text("info: system ok\nscoring status: healthy\n", encoding="utf-8")
    res = check_scoring()
    assert res.status == "ok"

    # Case 4: degenerate
    log_file.write_text("info: system ok\nscoring status: degenerate\n", encoding="utf-8")
    res = check_scoring()
    assert res.status == "fail"


def test_check_shell(monkeypatch):
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    res = check_shell()
    assert res.status == "ok"
    assert "fish" in res.message


def test_run_all_checks(monkeypatch):
    import jules.linux.doctor

    monkeypatch.setattr(
        jules.linux.doctor,
        "load_config",
        lambda: types.SimpleNamespace(doctor=types.SimpleNamespace(inotify_min_watches=65536)),
    )

    for check_name in [
        "check_ollama",
        "check_antigravity",
        "check_opencode",
        "check_lancedb",
        "check_sqlite",
        "check_inotify",
        "check_virtualenv",
        "check_permissions",
        "check_scoring",
        "check_shell",
    ]:
        monkeypatch.setattr(
            jules.linux.doctor,
            check_name,
            lambda *args, name=check_name: CheckResult(name=name, status="ok", message="ok")
        )

    report = run_all_checks()
    assert report.exit_code == 0

    # Mock one to fail
    monkeypatch.setattr(
        jules.linux.doctor,
        "check_ollama",
        lambda: CheckResult(name="Ollama", status="fail", message="fail")
    )
    report = run_all_checks()
    assert report.exit_code == 1


def test_run_all_checks_reports_config_load_failure(monkeypatch):
    import jules.linux.doctor

    monkeypatch.setattr(jules.linux.doctor, "load_config", lambda: (_ for _ in ()).throw(ValueError("bad config")))

    for check_name in [
        "check_ollama",
        "check_antigravity",
        "check_opencode",
        "check_lancedb",
        "check_sqlite",
        "check_virtualenv",
        "check_permissions",
        "check_scoring",
        "check_shell",
    ]:
        monkeypatch.setattr(
            jules.linux.doctor,
            check_name,
            lambda *args, name=check_name: CheckResult(name=name, status="ok", message="ok"),
        )
    monkeypatch.setattr(
        jules.linux.doctor,
        "check_inotify",
        lambda min_watches: CheckResult(name="inotify", status="ok", message=f"threshold {min_watches}"),
    )

    report = run_all_checks()

    assert report.exit_code == 1
    assert report.results[0].name == "Config"
    assert report.results[0].status == "warn"
    assert "bad config" in report.results[0].message
    assert any(result.message == "threshold 65536" for result in report.results)


def test_pyproject_exposes_jules_console_script():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["jules"] == "jules.cli.main:cli"


def _cli_runner() -> Any:
    return importlib.import_module("click.testing").CliRunner()


def test_doctor_json_cli_invokes_real_command_without_permission_gate(monkeypatch):
    import jules.cli.main as cli_main

    async def deny_if_called(action, target):
        raise AssertionError("doctor should bypass PermissionGate")

    monkeypatch.setattr(cli_main.gate, "check", deny_if_called)
    monkeypatch.setattr(
        cli_main,
        "run_all_checks",
        lambda: DoctorReport(
            results=[CheckResult(name="Shell", status="ok", message="fish detectado")],
            exit_code=0,
        ),
    )

    result = _cli_runner().invoke(cli_main.cli, ["doctor", "--json"])

    assert result.exit_code == 0
    loaded = json.loads(result.output)
    assert loaded == {
        "results": [{"name": "Shell", "status": "ok", "message": "fish detectado"}],
        "exit_code": 0,
    }


def test_doctor_cli_returns_report_exit_code(monkeypatch):
    import jules.cli.main as cli_main

    monkeypatch.setattr(
        cli_main,
        "run_all_checks",
        lambda: DoctorReport(
            results=[CheckResult(name="SQLite", status="fail", message="missing")],
            exit_code=1,
        ),
    )

    result = _cli_runner().invoke(cli_main.cli, ["doctor", "--json"])

    assert result.exit_code == 1
    loaded = json.loads(result.output)
    assert loaded["exit_code"] == 1
    assert loaded["results"][0]["status"] == "fail"


def test_json_output_serialization(monkeypatch):
    import jules.linux.doctor

    names = [
        "Ollama",
        "Antigravity",
        "OpenCode",
        "LanceDB",
        "SQLite",
        "inotify",
        "Virtualenv",
        "~/.jules/",
        "Scoring",
        "Shell",
    ]
    for i, check_name in enumerate([
        "check_ollama",
        "check_antigravity",
        "check_opencode",
        "check_lancedb",
        "check_sqlite",
        "check_inotify",
        "check_virtualenv",
        "check_permissions",
        "check_scoring",
        "check_shell",
    ]):
        monkeypatch.setattr(
            jules.linux.doctor,
            check_name,
            lambda *args, n=names[i]: CheckResult(name=n, status="ok", message="ok")
        )

    report = run_all_checks()
    report_dict = {
        "results": [
            {
                "name": r.name,
                "status": r.status,
                "message": r.message,
            }
            for r in report.results
        ],
        "exit_code": report.exit_code,
    }

    json_str = json.dumps(report_dict)
    loaded = json.loads(json_str)

    assert loaded["exit_code"] == 0
    assert len(loaded["results"]) == 10

    loaded_names = [r["name"] for r in loaded["results"]]
    for expected_name in names:
        assert expected_name in loaded_names
