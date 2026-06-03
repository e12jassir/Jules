import sys
import asyncio
import json

try:
    import click  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class _ClickStub:
        @staticmethod
        def group():
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def command():
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def option(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def pass_context(func):
            return func

        @staticmethod
        def echo(message, *args, **kwargs):
            print(message)

    click = _ClickStub()  # type: ignore[assignment]

from jules.core.config import load_config, PermissionsConfig
from jules.core.permissions import PermissionGate, Action, PermissionDeniedError
from jules.linux.doctor import run_all_checks

try:
    config = load_config()
    gate = PermissionGate(config.permissions)
except Exception:
    gate = PermissionGate(PermissionsConfig())


@click.group()
@click.pass_context
def cli(ctx) -> None:
    """Jules CLI."""
    if ctx.invoked_subcommand == "doctor":
        return

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


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def doctor(as_json: bool) -> None:
    """Diagnóstico de salud del entorno."""
    report = run_all_checks()
    if as_json:
        report_dict = {
            "results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "message": r.message
                }
                for r in report.results
            ],
            "exit_code": report.exit_code
        }
        click.echo(json.dumps(report_dict, indent=2))
        sys.exit(report.exit_code)
    else:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1, 0, 0))
        table.add_column("status", width=2)
        table.add_column("name", style="bold", width=15)
        table.add_column("message")

        for r in report.results:
            if r.status == "ok":
                status_symbol = "[green]✓[/green]"
            elif r.status == "fail":
                status_symbol = "[red]✗[/red]"
            else:  # warn
                status_symbol = "[yellow]⚠[/yellow]"
            table.add_row(status_symbol, r.name, r.message)

        console.print("──────────────────────────────────────")
        console.print(table)
        console.print("──────────────────────────────────────")

        problems = sum(1 for r in report.results if r.status in ("fail", "warn"))
        if problems == 0:
            console.print("[green]Entorno sano. Todos los chequeos pasaron con éxito.[/green]")
        elif problems == 1:
            console.print("[yellow]1 problema detectado. Jules opera en modo parcialmente degradado.[/yellow]")
        else:
            console.print(f"[yellow]{problems} problemas detectados. Jules opera en modo parcialmente degradado.[/yellow]")

        sys.exit(report.exit_code)


if __name__ == "__main__":
    cli()
