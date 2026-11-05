"""``solidworks-mcp skill install``: copy the usage skill into an agent's skills folder.

It writes only ``<skills folder>/solidworks-mcp/``, overwriting the files the
package ships and leaving any other file there alone. It reads nothing but the
packaged skill (no client config, no other skill) and needs no network.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from . import SKILL_DIR, SKILL_NAME

app = typer.Typer(
    add_completion=False,
    help="Install the SolidWorks MCP usage skill into an agent.",
)


def skills_folder(project: bool, directory: Path | None, home: Path, cwd: Path) -> Path:
    """Choose the skills folder the skill goes into.

    Args:
        project: Use the current project's ``.claude/skills``.
        directory: Any other skills folder; wins over ``project``.
        home: The user's home folder.
        cwd: The current working folder.

    Returns:
        Path: The skills folder (the skill goes in a ``solidworks-mcp``
        folder inside it).
    """
    if directory is not None:
        return directory
    return (cwd if project else home) / ".claude" / "skills"


def packaged_files() -> list[Path]:
    """List the skill's files, relative to the packaged skill folder.

    Returns:
        list[Path]: Every file of the skill, sorted.
    """
    return sorted(p.relative_to(SKILL_DIR) for p in SKILL_DIR.rglob("*") if p.is_file())


def install_skill(folder: Path, dry_run: bool = False) -> list[Path]:
    """Copy the packaged skill into ``folder/solidworks-mcp/``.

    Args:
        folder: The skills folder.
        dry_run: Report the files without writing them.

    Returns:
        list[Path]: The files written (or that would be written).

    Raises:
        OSError: When a folder can't be created or a file can't be written.
        ValueError: When a target would land outside the skill's folder.
    """
    target = folder / SKILL_NAME
    root = target.resolve()
    written: list[Path] = []
    for relative in packaged_files():
        destination = target / relative
        if not destination.resolve().is_relative_to(root):
            raise ValueError(f"Refusing to write outside {target}: {destination}")
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SKILL_DIR / relative, destination)
        written.append(destination)
    return written


@app.callback()
def main() -> None:
    """Install the SolidWorks MCP usage skill into an agent."""


@app.command()
def install(
    project: bool = typer.Option(
        False, "--project", help="Install into this project's .claude/skills."
    ),
    directory: Path | None = typer.Option(
        None,
        "--dir",
        help="Install into this skills folder (for agents other than Claude Code).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be written, write nothing."
    ),
) -> None:
    """Copy the skill into ~/.claude/skills (default), a project, or a folder."""
    folder = skills_folder(project, directory, Path.home(), Path.cwd())
    try:
        written = install_skill(folder, dry_run=dry_run)
    except (OSError, ValueError) as exc:
        typer.echo(f"Could not install the skill into {folder / SKILL_NAME}: {exc}")
        raise typer.Exit(code=1) from exc
    verb = "Would write" if dry_run else "Installed"
    typer.echo(f"{verb} the {SKILL_NAME} skill in {folder / SKILL_NAME}:")
    for path in written:
        typer.echo(f"  {path}")
