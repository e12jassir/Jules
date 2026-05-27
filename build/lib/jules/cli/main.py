try:
    import click  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class _ClickStub:
        @staticmethod
        def group():
            def decorator(func):
                return func

            return decorator

    click = _ClickStub()


@click.group()
def cli() -> None:
    """Jules CLI."""
    pass


if __name__ == "__main__":
    cli()
