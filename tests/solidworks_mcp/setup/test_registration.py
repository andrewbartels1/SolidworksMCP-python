"""Tests for registering the server with a client's own means."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.setup.clients import Client
from solidworks_mcp.setup.config_file import ConfigFileError
from solidworks_mcp.setup.registration import (
    ClaudeCliRegistrar,
    JsonFileRegistrar,
    OldEntryCleaner,
    registrar_for,
)

ENTRY = {"command": r"C:\v\solidworks-mcp.exe", "args": ["--mock"]}


class FakeRunner:
    """Records commands and answers each with a fixed exit code."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(
        self, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        return subprocess.CompletedProcess(command, self.returncode, "", "")


def _claude_code(found: bool = True) -> Client:
    return Client("claude-code", "Claude Code", found, None)


def test_registrar_for_picks_by_config_kind(tmp_path: Path) -> None:
    file_client = Client(
        "vscode", "VS Code", True, tmp_path / "mcp.json", section="servers"
    )

    assert isinstance(registrar_for(file_client), JsonFileRegistrar)
    assert isinstance(registrar_for(_claude_code()), ClaudeCliRegistrar)


def test_json_file_registrar_writes_its_section(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    client = Client("vscode", "VS Code", True, path, section="servers")

    change = JsonFileRegistrar(client).apply(ENTRY, dry_run=False)

    assert change.action == "added"
    assert json.loads(path.read_text())["servers"]["solidworks"] == ENTRY


def test_json_file_registrar_finds_and_removes_old_entries(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    old = {"type": "stdio", "command": "powershell", "args": ["-File", "run-mcp.ps1"]}
    other = {"command": "todo.exe", "env": {"KEY": "secret"}}
    path.write_text(
        json.dumps({"servers": {"todo": other, "solidworks-mcp-server": old}})
    )
    registrar = JsonFileRegistrar(
        Client("vscode", "VS Code", True, path, section="servers")
    )

    assert isinstance(registrar, OldEntryCleaner)
    assert registrar.old_entries() == [("solidworks-mcp-server", "powershell")]
    assert (
        registrar.remove_entry("solidworks-mcp-server", dry_run=True).action
        == "removed"
    )
    assert "solidworks-mcp-server" in json.loads(path.read_text())["servers"]

    change = registrar.remove_entry("solidworks-mcp-server", dry_run=False)

    assert change.action == "removed" and change.backup is not None
    assert json.loads(path.read_text())["servers"] == {"todo": other}
    assert registrar.old_entries() == []


def test_claude_cli_registrar_has_no_old_entry_cleanup() -> None:
    assert not isinstance(ClaudeCliRegistrar(_claude_code()), OldEntryCleaner)


def test_claude_cli_add_clears_the_old_entry_first() -> None:
    run = FakeRunner()

    change = ClaudeCliRegistrar(_claude_code(), run).apply(ENTRY, dry_run=False)

    assert run.calls == [
        ["claude", "mcp", "remove", "--scope", "user", "solidworks"],
        [
            "claude",
            "mcp",
            "add",
            "--scope",
            "user",
            "solidworks",
            "--",
            ENTRY["command"],
            "--mock",
        ],
    ]
    assert change.action == "added"
    assert change.location.startswith("claude mcp add")


def test_claude_cli_remove() -> None:
    run = FakeRunner()

    change = ClaudeCliRegistrar(_claude_code(), run).apply(None, dry_run=False)

    assert run.calls == [["claude", "mcp", "remove", "--scope", "user", "solidworks"]]
    assert change.action == "removed"


def test_claude_cli_add_failure_names_the_command() -> None:
    with pytest.raises(
        ConfigFileError,
        match="'claude mcp add' failed .*run it yourself: claude mcp add",
    ):
        ClaudeCliRegistrar(_claude_code(), FakeRunner(returncode=1)).apply(
            ENTRY, dry_run=False
        )


def test_claude_cli_dry_run_runs_nothing() -> None:
    run = FakeRunner()

    change = ClaudeCliRegistrar(_claude_code(), run).apply(ENTRY, dry_run=True)

    assert run.calls == []
    assert change.action == "added"


def test_claude_cli_without_claude_is_not_run() -> None:
    run = FakeRunner()

    change = ClaudeCliRegistrar(_claude_code(found=False), run).apply(
        ENTRY, dry_run=False
    )

    assert run.calls == []
    assert change.action == "not run"
