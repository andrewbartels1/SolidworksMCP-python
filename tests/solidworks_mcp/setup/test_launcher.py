"""Tests for the launcher command written into client configs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from solidworks_mcp.setup.launcher import find_uvx, in_uv_cache, server_command


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


def _cached_python(root: Path) -> str:
    """An interpreter in a uvx environment, with its launcher beside it."""
    scripts = root / "uv" / "cache" / "archive-v0" / "AbC123" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "solidworks-mcp.exe").write_text("")
    return str(scripts / "python.exe")


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("uv/cache/archive-v0/AbC123/Scripts/python.exe", True),
        ("UV/Cache/Archive-V12/x/Scripts/python.exe", True),
        ("uv/tools/solidworks-mcp-python/Scripts/python.exe", False),
        ("project/.venv/Scripts/python.exe", False),
        ("archive-v0/x/Scripts/python.exe", False),  # no cache folder above it
    ],
)
def test_in_uv_cache(tmp_path: Path, relative: str, expected: bool) -> None:
    assert in_uv_cache(str(tmp_path / relative)) is expected


def test_a_uvx_environment_writes_uvx(tmp_path: Path) -> None:
    python = _cached_python(tmp_path)
    uvx = r"C:\Users\me\.local\bin\uvx.exe"

    assert server_command(mock=True, python=python, uvx_finder=lambda: uvx) == (
        uvx,
        ["solidworks-mcp-python", "--mock"],
    )


def test_not_lasting_gives_the_launcher_running_now(tmp_path: Path) -> None:
    python = _cached_python(tmp_path)

    command, args = server_command(
        python=python, lasting=False, uvx_finder=lambda: "uvx.exe"
    )

    assert command == str(Path(python).parent / "solidworks-mcp.exe")
    assert args == []


def test_without_uvx_falls_back_to_the_cached_launcher(tmp_path: Path) -> None:
    python = _cached_python(tmp_path)

    command, _ = server_command(python=python, uvx_finder=lambda: None)

    assert command == str(Path(python).parent / "solidworks-mcp.exe")


@pytest.mark.parametrize("name", ["uvx.exe", "uvx"])
def test_find_uvx_beside_uv(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("")

    found = find_uvx(uv=str(tmp_path / "uv.exe"), which=lambda _: "elsewhere")

    assert found == str(tmp_path / name)


def test_find_uvx_on_the_path(tmp_path: Path) -> None:
    # uv is known but has no uvx beside it, so the PATH is asked.
    assert find_uvx(uv=str(tmp_path / "uv.exe"), which=lambda _: "C:/bin/uvx.exe") == (
        "C:/bin/uvx.exe"
    )


def test_find_uvx_reads_the_uv_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "uvx.exe").write_text("")
    monkeypatch.setenv("UV", str(tmp_path / "uv.exe"))

    assert find_uvx(which=lambda _: None) == str(tmp_path / "uvx.exe")


def test_find_uvx_without_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UV", raising=False)

    assert find_uvx(which=lambda _: None) is None


def test_a_real_entry_carries_its_year_and_a_mock_one_does_not(tmp_path: Path) -> None:
    python = str(tmp_path / "python.exe")

    assert server_command(year=2026, python=python) == (
        python,
        ["-m", "solidworks_mcp.server", "--year", "2026"],
    )
    assert server_command(mock=True, year=2026, python=python) == (
        python,
        ["-m", "solidworks_mcp.server", "--mock"],
    )
