# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false
import json
import sys
from dataclasses import dataclass

try:
    import click  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class _Context:
        invoked_subcommand: str | None = None

    class _Group:
        def __init__(self, callback):
            self.callback = callback
            self.commands = {}

        def command(self, *_args, **_kwargs):
            def register(func):
                self.commands[func.__name__] = func
                return func
            return register

        def __call__(self):
            args = sys.argv[1:]
            if args[:1] == ["doctor"]:
                self.commands["doctor"]("--json" in args)
                return
            self.callback(_Context())

    class _ClickStub:
        @staticmethod
        def group(*_args, **_kwargs):
            return lambda func: _Group(func)

        @staticmethod
        def option(*_args, **_kwargs):
            return lambda func: func

        @staticmethod
        def pass_context(func):
            return func

        @staticmethod
        def echo(message, *args, **kwargs):
            print(message, file=sys.stderr if kwargs.get("err") else sys.stdout)

    click = _ClickStub()  # type: ignore[assignment]


@dataclass
class _FallbackCheck:
    name: str
    status: str
    message: str


@dataclass
class _FallbackReport:
    results: list[_FallbackCheck]
    exit_code: int


def _run_doctor_checks():
    return _FallbackReport(
        results=[_FallbackCheck("doctor", "fail", "Módulo jules.linux.doctor no disponible")],
        exit_code=1
    )


# Module-level aliases so tests can monkeypatch cli_main.run_all_checks and cli_main.gate
try:
    from jules.linux.doctor import run_all_checks  # type: ignore[assignment]
except Exception:
    run_all_checks = _run_doctor_checks  # type: ignore[assignment]

try:
    from jules.core.config import PermissionsConfig, load_config
    from jules.core.permissions import PermissionGate
    gate = PermissionGate(load_config().permissions)
except Exception:
    class _NoopGate:
        async def check(self, *_args, **_kwargs) -> None:
            pass
    gate = _NoopGate()  # type: ignore[assignment]


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    """Jules — capa cognitiva persistente."""
    if ctx.invoked_subcommand is not None:
        return
    from jules.cli.app import JulesApp  # type: ignore[import-not-found]

    JulesApp().run(inline=False)


@cli.command()  # type: ignore[attr-defined]
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def doctor(as_json: bool) -> None:
    """Diagnóstico de salud del entorno."""
    report = run_all_checks()
    if as_json:
        click.echo(json.dumps({
            "results": [
                {"name": r.name, "status": r.status, "message": r.message}
                for r in report.results
            ],
            "exit_code": report.exit_code,
        }, indent=2))
        sys.exit(report.exit_code)

    from rich.console import Console  # type: ignore[import-not-found]
    from rich.table import Table  # type: ignore[import-not-found]

    console = Console()
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1, 0, 0))
    table.add_column("status", width=2)
    table.add_column("name", style="bold", width=15)
    table.add_column("message")
    for result in report.results:
        if result.status == "ok":
            symbol = "[green]✓[/green]"
        elif result.status == "fail":
            symbol = "[red]✗[/red]"
        else:
            symbol = "[yellow]⚠[/yellow]"
        table.add_row(symbol, result.name, result.message)

    console.print("──────────────────────────────────────")
    console.print(table)
    console.print("──────────────────────────────────────")
    problems = sum(1 for result in report.results if result.status in ("fail", "warn"))
    if problems == 0:
        console.print("[green]Entorno sano. Todos los chequeos pasaron con éxito.[/green]")
    else:
        console.print(f"[yellow]{problems} problema(s) detectado(s). Jules opera en modo parcialmente degradado.[/yellow]")
    sys.exit(report.exit_code)


if __name__ == "__main__":
    cli()  # type: ignore[call-arg]
