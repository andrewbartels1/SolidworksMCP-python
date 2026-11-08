"""``solidworks-mcp-python selftest``: options, the precheck and exit codes.

Exit 0 when every area passes, 1 when any fails or is skipped, 2 when the
selftest can't run at all.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from ..config import SolidWorksMCPConfig, load_config
from ..setup.solidworks import installed_versions
from .areas import AREAS, Context
from .documents import DocumentGuard
from .environment import read_environment
from .report import render, summary_markdown
from .results import Outcome, ToolCaller
from .runner import run_areas

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN = 0, 1, 2

NOT_RUNNING = (
    "SolidWorks isn't running. Start SolidWorks, wait for it to finish "
    "loading, then run this again."
)

app = typer.Typer(add_completion=False, no_args_is_help=False)


def solidworks_running() -> bool:
    """Whether an ``SLDWORKS.exe`` process is running, without touching COM.

    Returns:
        bool: True when ``tasklist`` lists one.
    """
    listed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "sldworks.exe" in listed.stdout.lower()


def precheck(
    system: Callable[[], str] = platform.system,
    versions: Callable[[], list[int]] = installed_versions,
    running: Callable[[], bool] = solidworks_running,
) -> str | None:
    """Why the selftest can't run here, or ``None`` when it can.

    Args:
        system: Returns the OS name.
        versions: Returns the installed SolidWorks years.
        running: Whether SolidWorks is running.

    Returns:
        str | None: What to do next, or ``None``.
    """
    if system() != "Windows":
        return "The selftest needs Windows with SolidWorks installed."
    if not versions():
        return (
            "No SolidWorks install was found. Install SolidWorks, then run this again."
        )
    if not running():
        return NOT_RUNNING
    return None


async def _start_server(config: SolidWorksMCPConfig) -> Any:
    """Build and connect the same server the CLI runs.

    Args:
        config: The selftest's configuration.

    Returns:
        Any: The set-up ``SolidWorksMCPServer``, its adapter connected.
    """
    from ..server import SolidWorksMCPServer

    server = SolidWorksMCPServer(config)
    await server.setup()
    await server.adapter.connect()
    return server


async def run_selftest(
    config: SolidWorksMCPConfig,
    report_path: Path | None,
    start_server: Callable[[SolidWorksMCPConfig], Any] = _start_server,
) -> int:
    """Run every area against SolidWorks, print the report, return the exit code.

    Args:
        config: The configuration, its ``solidworks_year`` set.
        report_path: Where to also write the Markdown summary, if anywhere.
        start_server: Builds and connects the server (tests pass a stub).

    Returns:
        int: ``EXIT_PASS``, ``EXIT_FAIL`` or ``EXIT_CANNOT_RUN``.
    """
    from fastmcp import Client

    try:
        server = await start_server(config)
    except Exception as exc:  # noqa: BLE001 - any connect failure means "can't run"
        typer.echo(f"Could not connect to SolidWorks: {exc}")
        return EXIT_CANNOT_RUN
    try:
        async with Client(server.mcp) as client:
            call = ToolCaller(client)
            environment = await read_environment(server.adapter, config.solidworks_year)
            guard = DocumentGuard(call)
            async with guard:
                results = await run_areas(AREAS, Context(call, guard.folder))
    finally:
        await server.adapter.disconnect()
    typer.echo(render(environment, results, guard.problems))
    if report_path is not None:
        report_path.write_text(summary_markdown(environment, results), encoding="utf-8")
        typer.echo(f"Summary written to {report_path}")
    passed = all(r.outcome is Outcome.PASS for r in results)
    return EXIT_PASS if passed else EXIT_FAIL


@app.command()
def selftest(
    year: int | None = typer.Option(
        None,
        "--year",
        min=1995,
        max=2100,
        help="The installed SolidWorks release to test, e.g. 2026. "
        "Default: the newest installed.",
    ),
    report: Path | None = typer.Option(
        None, "--report", help="Also write the Markdown summary to this file."
    ),
    config: str | None = typer.Option(
        None, "--config", help="Configuration file path."
    ),
) -> None:
    """Check this SolidWorks setup through the MCP tools and print a report.

    With SolidWorks running, it builds a small part, an assembly, a drawing
    view and a STEP export, checks each against a hand calculation, and
    prints a summary to send with a compatibility report. It opens and
    closes a few documents of its own, and never saves, closes or changes
    one you had open.

    \f
    Args:
        year: The SolidWorks release year.
        report: A file to write the Markdown summary to.
        config: Path to a configuration file.

    Raises:
        typer.Exit: Always, with the exit code.
    """
    problem = precheck()
    if problem:
        typer.echo(problem)
        raise typer.Exit(EXIT_CANNOT_RUN)
    loaded = load_config(config)
    loaded.mock_solidworks = False
    loaded.log_level = "WARNING"
    loaded.solidworks_year = year or installed_versions()[0]
    if not loaded.can_use_solidworks:
        typer.echo(
            "The configuration asks for the mock adapter; the selftest needs SolidWorks."
        )
        raise typer.Exit(EXIT_CANNOT_RUN)
    from .. import utils

    utils.setup_logging(loaded)
    typer.echo(
        f"Testing SolidWorks {loaded.solidworks_year}: this opens and closes a "
        "few documents of its own and leaves yours alone. About three minutes."
    )
    raise typer.Exit(asyncio.run(run_selftest(loaded, report)))
