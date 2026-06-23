from jules.cli.commands import COMMANDS, parse_slash_command


def test_parse_known_slash_commands() -> None:
    for command in ("exit", "sessions", "memory", "status", "doctor", "model", "login", "logout", "auth", "clear", "help"):
        parsed = parse_slash_command(f"/{command}")
        assert parsed is not None
        assert parsed.name == command
        assert parsed.known is True
        assert command in COMMANDS


def test_parse_model_args() -> None:
    parsed = parse_slash_command("/model gpt-5")
    assert parsed is not None
    assert parsed.name == "model"
    assert parsed.args == ("gpt-5",)
    assert parsed.known is True


def test_parse_login_args() -> None:
    parsed = parse_slash_command("/login claude device")
    assert parsed is not None
    assert parsed.name == "login"
    assert parsed.args == ("claude", "device")
    assert parsed.known is True


def test_unknown_and_non_command() -> None:
    unknown = parse_slash_command("/wat")
    assert unknown is not None
    assert unknown.name == "wat"
    assert unknown.known is False
    assert parse_slash_command("hello") is None


def test_handle_help_returns_all_commands() -> None:
    from jules.cli.commands import handle_help

    result = handle_help()
    for name in COMMANDS:
        assert f"/{name}" in result


import unittest


class TestAsyncCommandHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_handle_sessions_returns_string_on_db_error(self) -> None:
        from jules.cli.commands import handle_sessions

        result = await handle_sessions()
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_handle_status_returns_string(self) -> None:
        from jules.cli.commands import handle_status

        result = await handle_status()
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_handle_auth_reports_default_provider_state(self) -> None:
        from jules.cli.commands import handle_auth

        result = await handle_auth(())
        assert "openai" in result
        assert "claude" in result
