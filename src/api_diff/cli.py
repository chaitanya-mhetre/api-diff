"""``api-diff OLD NEW`` and ``api-diff rules``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer

from api_diff import diff
from api_diff.ignore import apply_ignores, load_ignore
from api_diff.loader import SpecError
from api_diff.reporters import RENDERERS
from api_diff.rules import RULES

app = typer.Typer(help="Detect breaking changes between two OpenAPI 3.x specs.", no_args_is_help=True)

Format = Literal["text", "json", "markdown", "github"]
FailOn = Literal["breaking", "warning", "info", "never"]


@app.command("diff")
def diff_cmd(
    old: Annotated[str, typer.Argument(help="old spec: file path or http(s) URL")],
    new: Annotated[str, typer.Argument(help="new spec: file path or http(s) URL")],
    fmt: Annotated[Format, typer.Option("--format", "-f")] = "text",
    fail_on: Annotated[
        FailOn, typer.Option("--fail-on", help="exit 1 at this severity or worse")
    ] = "breaking",
    ignore: Annotated[Path | None, typer.Option("--ignore", help="YAML file of accepted changes")] = None,
) -> None:
    """Compare OLD and NEW. Exit codes: 0 ok, 1 changes at --fail-on level, 2 input error."""
    try:
        report = diff(old, new)
        if ignore is not None:
            report = apply_ignores(report, load_ignore(ignore))
    except (SpecError, OSError) as exc:
        typer.echo(f"api-diff: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(RENDERERS[fmt](report))
    if fail_on != "never" and report.fails(fail_on):
        raise typer.Exit(1)


@app.command("rules")
def rules_cmd() -> None:
    """List every rule with its severity and rationale."""
    for rule in RULES.values():
        typer.echo(f"{rule.id:36} {rule.severity:9} {rule.description}")
        typer.echo(f"{'':36} {'':9} why: {rule.rationale}")


def main() -> None:
    """Entry point: ``api-diff old new`` is shorthand for ``api-diff diff old new``."""
    args = sys.argv[1:]
    if args and args[0] not in ("diff", "rules") and not args[0].startswith("-"):
        sys.argv.insert(1, "diff")
    app()
