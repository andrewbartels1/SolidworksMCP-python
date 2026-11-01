"""Tests for the launcher command written into client configs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from solidworks_mcp.setup.launcher import server_command


@pytest.mark.parametrize("name", ["solidworks-mcp.exe", "solidworks-mcp"])
def test_the_console_script_beside_python(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("")
    python = str(tmp_path / "python.exe")

    assert server_command(python=python) == (str(tmp_path / name), [])
    assert server_command(mock=True, python=python) == (
        str(tmp_path / name),
        ["--mock"],
    )


def test_falls_back_to_the_module(tmp_path: Path) -> None:
    python = str(tmp_path / "python.exe")

    assert server_command(mock=True, python=python) == (
        python,
        ["-m", "solidworks_mcp.server", "--mock"],
    )


def test_defaults_to_this_python() -> None:
    command, _ = server_command()

    assert command.startswith(str(Path(sys.executable).parent))
