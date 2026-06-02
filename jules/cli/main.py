import sys
import asyncio

try:
    import click  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class _ClickStub:
        @staticmethod
        def group():
            def decorator(func):
                return func

            return decorator

    click = _ClickStub()  # type: ignore[assignment]

from jules.core.config import load_config, PermissionsConfig
from jules.core.permissions import PermissionGate, Action, PermissionDeniedError

try:
    config = load_config()
    gate = PermissionGate(config.permissions)
except Exception:
    gate = PermissionGate(PermissionsConfig())


@click.group()
def cli() -> None:
    """Jules CLI."""
    target = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    action = Action.PACKAGE_OP if any(pkg in target for pkg in ("pacman", "yay")) else Action.SHELL_COMMAND
    try:
        asyncio.run(gate.check(action, target))
    except PermissionDeniedError as e:
        if hasattr(click, "echo"):
            click.echo(str(e), err=True)
        else:
            print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
