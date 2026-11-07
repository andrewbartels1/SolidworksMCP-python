"""``solidworks-mcp setup``: connect MCP clients to this server, step by step.

This module is only the conversation with the user: it asks, reports and
decides the order. Finding clients (:mod:`.clients`), editing their configs
(:mod:`.registration`) and checking the server (:mod:`.handshake`) live in
their own modules.
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .clients import SERVER_NAME, Client, find_clients
from .config_file import ConfigFileError, EntryChange, current_entry
from .handshake import HandshakeResult, check_server
from .launcher import PACKAGE, in_uv_cache, server_command
from .registration import OldEntryCleaner, registrar_for
from .solidworks import installed_versions

console = Console()
app = typer.Typer(add_completion=False)


class OldEntryChoice(Enum):
    """What to do with older entries that start this same server."""

    ASK = "ask"
    REMOVE = "remove"
    KEEP = "keep"

    @classmethod
    def from_flags(cls, *, replace_old: bool, yes: bool) -> OldEntryChoice:
        """Pick from the command-line flags.

        ``--replace-old`` removes them. ``--yes`` alone keeps them, since
        removing someone's entries is never done without being asked.

        Args:
            replace_old: ``--replace-old`` was given.
            yes: ``--yes`` was given.

        Returns:
            The choice.
        """
        if replace_old:
            return cls.REMOVE
        return cls.KEEP if yes else cls.ASK


@app.command()
def setup(
    client: list[str] | None = typer.Option(
        None,
        "--client",
        help="Client to configure: claude-desktop, claude-code, vscode, cursor, "
        "lmstudio. Repeat for several. Default: choose from a list.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Don't ask; configure every client found."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change, and change nothing."
    ),
    remove: bool = typer.Option(
        False, "--remove", help="Remove the solidworks entry instead of adding it."
    ),
    mock: bool = typer.Option(
        False, "--mock", help="Configure mock mode, which needs no SolidWorks."
    ),
    skip_check: bool = typer.Option(
        False, "--skip-check", help="Don't start the server to check it first."
    ),
    replace_old: bool = typer.Option(
        False,
        "--replace-old",
        help="Remove older hand-made entries that start this server "
        "(run-mcp.ps1 and the like) without asking.",
    ),
    year: int | None = typer.Option(
        None,
        "--year",
        min=1995,
        max=2100,
        help="SolidWorks year the server works with, e.g. 2026. "
        "Default: the newest installed.",
    ),
) -> None:
    """Find your SolidWorks and MCP clients, and add this server to them.

    Only the solidworks entry of each client's config is changed. The file is
    backed up first, and no other entry is ever printed.

    Args:
        client: Client keys to configure; ``None`` to choose from a list.
        yes: Configure every client found, without asking.
        dry_run: Report what would change, and change nothing.
        remove: Remove the entry instead of adding it.
        mock: Write a mock-mode entry.
        skip_check: Skip the start-up check.
        replace_old: Remove older entries for this server without asking.
        year: The SolidWorks year to start the server with; the newest
            installed when ``None``.

    Raises:
        typer.Exit: With code 1 if the check failed or a client couldn't be
            configured.
    """
    console.print("[bold]SolidWorks MCP setup[/bold]\n")
    if not remove:
        mock = _choose_mode(mock, yes)
        year = None if mock else _choose_year(year)
    command, args = server_command(mock=mock, year=year)
    if in_uv_cache(sys.executable) and args[:1] != [PACKAGE]:
        console.print(
            "[yellow]Running from uv's cache, and uvx was not found: the entry "
            "will stop working when uv cleans its cache. Install uv so uvx is on "
            "the PATH, then run setup again.[/yellow]"
        )

    chosen = _choose_clients(find_clients(), client, yes, command)
    if not chosen:
        console.print("No clients chosen; nothing to do.")
        return

    # Check before writing, so a broken launcher never reaches a config.
    if not (remove or skip_check):
        console.print(
            "\nChecking that the server starts (mock mode, SolidWorks is not touched)..."
        )
        # The launcher running now: a `uvx` entry would fetch from PyPI instead.
        result = _run_check(*server_command(mock=mock, year=year, lasting=False))
        if not result.ok:
            console.print(f"[red]{result.message}[/red] No config was changed.")
            raise typer.Exit(1)
        console.print(f"[green]{result.message}[/green]")

    console.print()
    # One client's failure doesn't stop the others; it sets the exit code.
    choice = OldEntryChoice.from_flags(replace_old=replace_old, yes=yes)
    failures = sum(
        not _configure(target, command, args, remove, dry_run, choice)
        for target in chosen
    )

    if dry_run:
        console.print("\nDry run: nothing was changed.")
    elif not remove:
        console.print("\n[bold]Next[/bold]")
        for target in chosen:
            console.print(f"  {target.name}: {target.restart_hint}")
        console.print(
            "  To teach your agent how to use these tools: solidworks-mcp skill install"
        )
    if failures:
        raise typer.Exit(1)


def _choose_mode(mock: bool, yes: bool) -> bool:
    """Decide between a real and a mock-mode entry.

    Args:
        mock: ``--mock`` was given.
        yes: Don't ask; with no SolidWorks found, still write a real entry.

    Returns:
        Whether to write a mock-mode entry.
    """
    if mock:
        console.print("Mock mode: the server answers without SolidWorks.")
        return True
    years = installed_versions()
    if years:
        found = ", ".join(f"SOLIDWORKS {year}" for year in years)
        console.print(f"Found {found}. The server connects to the running SolidWorks.")
        return False
    console.print("[yellow]No SolidWorks install was found in the registry.[/yellow]")
    if yes:
        return False
    return Confirm.ask(
        "Set up mock mode instead (for trying the tools without SolidWorks)?"
    )


def _choose_year(requested: int | None) -> int | None:
    """Decide the SolidWorks year a real entry starts the server with.

    Args:
        requested: ``--year``, if given.

    Returns:
        The requested year, else the newest installed one; ``None`` when no
        install is found and none was requested (the server then warns and
        uses the newest it finds).

    Raises:
        typer.Exit: With code 1, before anything is written, when the
            requested year isn't installed.
    """
    years = installed_versions()
    if requested is None:
        if years:
            console.print(
                f"The server will work with SOLIDWORKS {years[0]} (--year {years[0]})."
            )
            return years[0]
        return None
    if years and requested not in years:
        installed = ", ".join(str(found) for found in years)
        console.print(
            f"[red]SOLIDWORKS {requested} isn't installed here; installed: "
            f"{installed}.[/red] No config was changed."
        )
        raise typer.Exit(1)
    return requested


def _choose_clients(
    clients: list[Client], keys: list[str] | None, yes: bool, command: str
) -> list[Client]:
    """Pick the clients to configure: by ``--client``, ``--yes`` or a prompt.

    Args:
        clients: Every supported client.
        keys: Keys from ``--client``, if any.
        yes: Take every client found, without asking.
        command: The launcher this run will write, for the status column.

    Returns:
        The chosen clients, in the order offered.

    Raises:
        typer.BadParameter: An unknown key, or an answer that isn't a client number.
    """
    if keys:
        by_key = {c.key: c for c in clients}
        unknown = [k for k in keys if k not in by_key]
        if unknown:
            raise typer.BadParameter(
                f"Unknown client {', '.join(unknown)}; choose from {', '.join(by_key)}.",
                param_hint="--client",
            )
        return [by_key[k] for k in keys]

    table = Table(show_header=True, header_style="bold")
    for column in ("#", "Client", "Status"):
        table.add_column(column)
    for number, target in enumerate(clients, 1):
        table.add_row(str(number), target.name, _status(target, command))
    console.print(table)

    if yes:
        return [c for c in clients if c.found]
    found = [str(n) for n, c in enumerate(clients, 1) if c.found]
    answer = Prompt.ask(
        "Which clients? Numbers separated by commas, or 'all'",
        default=",".join(found) or "all",
    )
    return _parse_choice(answer, clients)


def _parse_choice(answer: str, clients: list[Client]) -> list[Client]:
    """Turn an answer like ``1, 3`` or ``all`` into clients.

    Args:
        answer: What the user typed.
        clients: The numbered clients (numbered from 1).

    Returns:
        The chosen clients, each once, in the order typed.

    Raises:
        typer.BadParameter: A part that isn't a listed number.
    """
    if answer.strip().lower() == "all":
        return list(clients)
    chosen: list[Client] = []
    for part in answer.replace(" ", "").split(","):
        if not part:
            continue
        if not (part.isdigit() and 1 <= int(part) <= len(clients)):
            raise typer.BadParameter(f"'{part}' is not a client number.")
        target = clients[int(part) - 1]
        if target not in chosen:
            chosen.append(target)
    return chosen


def _status(target: Client, command: str) -> str:
    """Describe a client for the table: found or not, and its config state.

    The only value shown from the file is the ``solidworks`` entry's own
    command, and only when it runs a different copy than ``command``.

    Args:
        target: The client.
        command: The launcher this setup run will write.

    Returns:
        One rich-formatted line.
    """
    if not target.found:
        return "[dim]not found[/dim]"
    if target.config_path is None:
        return "found (uses the claude command)"
    where = escape(str(target.config_path))
    if not target.config_path.exists():
        return f"found; will create {where}"
    try:
        entry = current_entry(target.config_path, target.section, SERVER_NAME)
    except ConfigFileError:
        return f"[red]config is not valid JSON[/red]: {where}"
    if entry is None:
        return f"config found: {where}"
    current = entry.get("command") if isinstance(entry, dict) else None
    if isinstance(current, str) and current != command:
        # e.g. a test copy's .venv: deleting that folder would break the client.
        return (
            f"has a solidworks entry: {where}\n"
            f"[yellow]it runs another copy: {escape(current)}[/yellow]"
        )
    return f"has a solidworks entry: {where}"


def _run_check(command: str, args: list[str]) -> HandshakeResult:
    """Run the start-up check in mock mode, whatever mode is being configured.

    Mock mode proves the launcher and the stdio handshake without starting
    or touching SolidWorks.

    Args:
        command: The launcher.
        args: The arguments being written to the configs.

    Returns:
        The check's outcome.
    """
    check_args = args if "--mock" in args else [*args, "--mock"]
    return check_server(command, check_args)


def _configure(
    target: Client,
    command: str,
    args: list[str],
    remove: bool,
    dry_run: bool,
    choice: OldEntryChoice,
) -> bool:
    """Add or remove the entry for one client, then deal with older entries.

    Args:
        target: The client.
        command: The launcher.
        args: Its arguments.
        remove: Remove the entry instead of adding it.
        dry_run: Report what would change, and change nothing.
        choice: What to do about older entries for this server.

    Returns:
        Whether it succeeded.
    """
    entry: dict[str, Any] | None = None if remove else target.entry(command, args)
    registrar = registrar_for(target)
    try:
        change = registrar.apply(entry, dry_run=dry_run)
    except ConfigFileError as exc:
        console.print(f"[red]{target.name}: {exc}[/red]")
        return False
    console.print(f"{target.name}: {_describe(change, dry_run)}")
    if isinstance(registrar, OldEntryCleaner):
        return _clean_old_entries(target, registrar, choice, dry_run)
    return True


def _clean_old_entries(
    target: Client, cleaner: OldEntryCleaner, choice: OldEntryChoice, dry_run: bool
) -> bool:
    """Offer to remove older entries that start this same server.

    Only each entry's name and launcher file name are shown; nothing else
    from the file is.

    Args:
        target: The client.
        cleaner: Its registrar, which can read and remove entries.
        choice: Whether to ask, remove without asking, or only report.
        dry_run: Report what would change, and change nothing.

    Returns:
        Whether every removal that was attempted succeeded.
    """
    old = cleaner.old_entries()
    if not old:
        return True
    listed = ", ".join(f"{name} ({launcher})" for name, launcher in old)
    console.print(
        f"  {target.name} also has older entries that start this server: {listed}. "
        "With both, every tool loads twice."
    )
    if choice is OldEntryChoice.KEEP:
        console.print(
            "  Kept. Run solidworks-mcp setup again with --replace-old to remove them."
        )
        return True
    if choice is OldEntryChoice.ASK and not Confirm.ask("  Remove them?", default=True):
        return True
    for name, _ in old:
        try:
            change = cleaner.remove_entry(name, dry_run=dry_run)
        except ConfigFileError as exc:
            console.print(f"[red]  {target.name}: {exc}[/red]")
            return False
        console.print(f"  {_describe(change, dry_run, label=name)}")
    return True


def _describe(change: EntryChange, dry_run: bool, label: str = SERVER_NAME) -> str:
    """Say what happened to the entry, in one line.

    Args:
        change: The registrar's result.
        dry_run: Whether nothing was actually changed.
        label: The entry's name.

    Returns:
        The line, naming the backup if one was made.
    """
    if change.action == "not run":
        return f"'claude' is not on the PATH; run: {change.location}"
    verb = change.action
    if dry_run and verb != "unchanged":
        verb = f"would be {verb}"
    line = f"{label} entry {verb} ({escape(change.location)})"
    if change.previous:
        line += f"; it ran {escape(change.previous)} before"
    if change.backup:
        line += f"; backup: {change.backup.name}"
    return line
