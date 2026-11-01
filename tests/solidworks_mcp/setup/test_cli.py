"""Tests for the ``solidworks-mcp setup`` wizard, with every outside effect faked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from solidworks_mcp.setup import cli
from solidworks_mcp.setup.clients import Client
from solidworks_mcp.setup.handshake import HandshakeResult
from solidworks_mcp.setup.registration import JsonFileRegistrar

SECRET = "sk-other-servers-secret"
LAUNCHER = r"C:\venv\Scripts\solidworks-mcp.exe"
runner = CliRunner()


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A machine with SolidWorks 2026, Claude Desktop (with another server) and VS Code."""
    desktop = tmp_path / "claude_desktop_config.json"
    desktop.write_text(json.dumps({"mcpServers": {"todo": {"env": {"KEY": SECRET}}}}))
    clients = [
        Client("claude-desktop", "Claude Desktop", True, desktop, restart_hint="Restart Claude."),
        Client("claude-code", "Claude Code", False, None, restart_hint="Run /mcp."),
        Client("vscode", "VS Code", True, tmp_path / "Code/mcp.json", section="servers",
               stdio_type=True, restart_hint="List servers."),
    ]  # fmt: skip
    checks: list[list[str]] = []

    def check(command: str, args: list[str]) -> HandshakeResult:
        """Record the check's arguments and pass."""
        checks.append(args)
        return HandshakeResult(True, 154, "The server started and listed 154 tools.")

    monkeypatch.setattr(cli, "find_clients", lambda: clients)
    monkeypatch.setattr(cli, "installed_versions", lambda: [2026])
    monkeypatch.setattr(
        cli, "server_command", lambda mock: (LAUNCHER, ["--mock"] if mock else [])
    )
    monkeypatch.setattr(cli, "check_server", check)
    return {"desktop": desktop, "vscode": clients[2].config_path, "checks": checks}


def _run(*args: str, answers: str = "") -> Result:
    """Run ``solidworks-mcp setup`` with ``args``, typing ``answers`` at the prompts."""
    return runner.invoke(cli.app, list(args), input=answers)


def _text(result: Result) -> str:
    """The output with rich's line wrapping undone, for phrase checks."""
    return " ".join(result.output.split())


def _servers(path: Path, section: str = "mcpServers") -> dict[str, Any]:
    """The servers object in a written config."""
    servers: dict[str, Any] = json.loads(path.read_text())[section]
    return servers


def test_yes_configures_every_client_found(machine: dict[str, Any]) -> None:
    result = _run("--yes")

    assert result.exit_code == 0, result.output
    assert _servers(machine["desktop"])["solidworks"] == {
        "command": LAUNCHER,
        "args": [],
    }
    assert _servers(machine["desktop"])["todo"] == {"env": {"KEY": SECRET}}
    assert _servers(machine["vscode"], "servers")["solidworks"]["type"] == "stdio"
    assert machine["checks"] == [["--mock"]]  # checked in mock mode
    assert "Found SOLIDWORKS 2026" in result.output
    assert "Restart Claude." in result.output and "List servers." in result.output
    assert SECRET not in result.output


def test_choosing_by_number(machine: dict[str, Any]) -> None:
    result = _run(answers="1\n")

    assert result.exit_code == 0, result.output
    assert "solidworks" in _servers(machine["desktop"])
    assert not machine["vscode"].exists()


def test_choosing_all_includes_clients_not_found(machine: dict[str, Any]) -> None:
    result = _run(answers="all\n")

    assert result.exit_code == 0, result.output
    assert "'claude' is not on the PATH; run: claude mcp add" in result.output


def test_a_bad_number_is_refused(machine: dict[str, Any]) -> None:
    result = _run(answers="1,9\n")

    assert result.exit_code != 0
    assert "'9' is not a client number" in result.output
    assert "solidworks" not in _servers(machine["desktop"])


def test_client_option(machine: dict[str, Any]) -> None:
    result = _run("--client", "vscode")

    assert result.exit_code == 0, result.output
    assert "solidworks" in _servers(machine["vscode"], "servers")
    assert "solidworks" not in _servers(machine["desktop"])


def test_unknown_client_option(machine: dict[str, Any]) -> None:
    result = _run("--client", "notepad")

    assert result.exit_code != 0
    assert "Unknown client notepad" in result.output


def test_dry_run_changes_nothing(machine: dict[str, Any]) -> None:
    before = machine["desktop"].read_bytes()

    result = _run("--yes", "--dry-run")

    assert result.exit_code == 0, result.output
    assert machine["desktop"].read_bytes() == before
    assert "would be added" in result.output
    assert "Dry run: nothing was changed." in result.output


def test_a_failed_check_writes_nothing(
    machine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "check_server",
        lambda c, a: HandshakeResult(False, 0, "The server did not answer."),
    )

    result = _run("--yes")

    assert result.exit_code == 1
    assert "No config was changed." in result.output
    assert "solidworks" not in _servers(machine["desktop"])


def test_skip_check(machine: dict[str, Any]) -> None:
    result = _run("--yes", "--skip-check")

    assert result.exit_code == 0, result.output
    assert machine["checks"] == []


def test_remove_then_unchanged(machine: dict[str, Any]) -> None:
    _run("--yes")

    removed = _run("--yes", "--remove")
    again = _run("--yes", "--remove")

    assert removed.exit_code == 0 and again.exit_code == 0
    assert "solidworks" not in _servers(machine["desktop"])
    assert "todo" in _servers(machine["desktop"])
    assert "entry removed" in removed.output and "entry unchanged" in again.output
    assert machine["checks"] == [["--mock"]]  # remove never starts the server
    assert "Next" not in removed.output


def test_a_rerun_is_unchanged_and_backs_up_once(machine: dict[str, Any]) -> None:
    _run("--yes")
    second = _run("--yes")

    assert "entry unchanged" in second.output
    assert len(list(machine["desktop"].parent.glob("*.bak-*"))) == 1


def test_an_invalid_config_fails_that_client_only(machine: dict[str, Any]) -> None:
    machine["desktop"].write_text('{"mcpServers": {"todo": "' + SECRET + '"},}')

    result = _run("--yes")

    assert result.exit_code == 1
    assert "config is not valid JSON" in result.output
    assert "Claude Desktop:" in result.output and "line 1" in result.output
    assert "solidworks" in _servers(machine["vscode"], "servers")
    assert SECRET not in result.output


def test_status_lines(machine: dict[str, Any]) -> None:
    _run("--client", "claude-desktop")

    result = _run("--dry-run", answers="\n")

    assert "has a solidworks entry" in result.output
    assert "will create" in result.output  # VS Code's file doesn't exist yet
    assert "not found" in result.output


def test_status_for_a_found_claude_code() -> None:
    assert cli._status(Client("claude-code", "Claude Code", True, None), LAUNCHER) == (
        "found (uses the claude command)"
    )


def test_no_clients_chosen(
    machine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "find_clients", lambda: [])

    result = _run("--yes")

    assert result.exit_code == 0
    assert "No clients chosen; nothing to do." in result.output


def test_mock_option(machine: dict[str, Any]) -> None:
    result = _run("--yes", "--mock")

    assert "Mock mode" in result.output
    assert _servers(machine["desktop"])["solidworks"]["args"] == ["--mock"]
    assert machine["checks"] == [["--mock"]]


@pytest.mark.parametrize(("answer", "args"), [("y", ["--mock"]), ("n", [])])
def test_no_solidworks_offers_mock_mode(
    machine: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    args: list[str],
) -> None:
    monkeypatch.setattr(cli, "installed_versions", lambda: [])

    result = _run("--client", "claude-desktop", answers=f"{answer}\n")

    assert "No SolidWorks install was found" in result.output
    assert _servers(machine["desktop"])["solidworks"]["args"] == args


def test_no_solidworks_with_yes_writes_a_real_entry(
    machine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "installed_versions", lambda: [])

    result = _run("--yes")

    assert _servers(machine["desktop"])["solidworks"]["args"] == []
    assert "Set up mock mode" not in result.output


def test_parse_choice() -> None:
    clients = [Client(k, k, True, None) for k in "abc"]

    assert cli._parse_choice(" 3, 1,3, ", clients) == [clients[2], clients[0]]
    assert cli._parse_choice("ALL", clients) == clients
    with pytest.raises(typer.BadParameter):
        cli._parse_choice("x", clients)


def test_default_answer_with_nothing_found(
    machine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "find_clients", lambda: [Client("cursor", "Cursor", False, None)]
    )

    result = _run("--dry-run", answers="\n")

    assert "(all)" in result.output


OLD_ENTRY = {"type": "stdio", "command": "powershell", "args": ["-File", "run-mcp.ps1"]}


def _with_old_vscode_entry(machine: dict[str, Any]) -> Path:
    """Give VS Code a hand-made PowerShell entry, plus another server with a secret."""
    path: Path = machine["vscode"]
    path.parent.mkdir(parents=True)
    servers = {"github": {"type": "http", "headers": {"Authorization": SECRET}},
               "solidworks-mcp-server": OLD_ENTRY}  # fmt: skip
    path.write_text(json.dumps({"servers": servers}))
    return path


@pytest.mark.parametrize(("answer", "removed"), [("y", True), ("n", False)])
def test_old_entries_are_offered_for_removal(
    machine: dict[str, Any], answer: str, removed: bool
) -> None:
    path = _with_old_vscode_entry(machine)

    result = _run("--client", "vscode", answers=f"{answer}\n")

    assert result.exit_code == 0, result.output
    assert (
        "older entries that start this server: solidworks-mcp-server (powershell)"
        in _text(result)
    )
    servers = _servers(path, "servers")
    assert ("solidworks-mcp-server" not in servers) is removed
    assert servers["github"] == {"type": "http", "headers": {"Authorization": SECRET}}
    assert "solidworks" in servers
    assert SECRET not in result.output


def test_yes_keeps_old_entries_and_says_how_to_remove_them(
    machine: dict[str, Any],
) -> None:
    path = _with_old_vscode_entry(machine)

    result = _run("--client", "vscode", "--yes")

    assert "solidworks-mcp-server" in _servers(path, "servers")
    assert "--replace-old" in _text(result)


def test_replace_old_removes_without_asking(machine: dict[str, Any]) -> None:
    path = _with_old_vscode_entry(machine)

    result = _run("--client", "vscode", "--yes", "--replace-old")

    assert result.exit_code == 0, result.output
    assert "solidworks-mcp-server entry removed" in _text(result)
    assert "solidworks-mcp-server" not in _servers(path, "servers")


def test_replace_old_on_a_dry_run_changes_nothing(machine: dict[str, Any]) -> None:
    path = _with_old_vscode_entry(machine)
    before = path.read_bytes()

    result = _run("--client", "vscode", "--dry-run", "--replace-old")

    assert "solidworks-mcp-server entry would be removed" in _text(result)
    assert path.read_bytes() == before


def test_a_failed_old_entry_removal_fails_that_client(
    machine: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_old_vscode_entry(machine)

    def fail(self: Any, name: str, *, dry_run: bool) -> Any:
        raise cli.ConfigFileError("disk full")

    monkeypatch.setattr(JsonFileRegistrar, "remove_entry", fail)

    result = _run("--client", "vscode", "--replace-old")

    assert result.exit_code == 1
    assert "VS Code: disk full" in _text(result)


@pytest.mark.parametrize(
    ("replace_old", "yes", "choice"),
    [(True, True, cli.OldEntryChoice.REMOVE), (True, False, cli.OldEntryChoice.REMOVE),
     (False, True, cli.OldEntryChoice.KEEP), (False, False, cli.OldEntryChoice.ASK)],
)  # fmt: skip
def test_old_entry_choice_from_flags(
    replace_old: bool, yes: bool, choice: cli.OldEntryChoice
) -> None:
    assert cli.OldEntryChoice.from_flags(replace_old=replace_old, yes=yes) is choice


OTHER_COPY = r"C:\old-copy\.venv\Scripts\solidworks-mcp.exe"


def test_an_entry_for_another_copy_is_flagged_and_named_when_replaced(
    machine: dict[str, Any],
) -> None:
    desktop: Path = machine["desktop"]
    desktop.write_text(
        json.dumps({"mcpServers": {"solidworks": {"command": OTHER_COPY, "args": []}}})
    )

    listed = _run("--dry-run", answers="1\n")
    replaced = _run("--client", "claude-desktop", "--yes")

    # The table wraps cells, so the phrase and the path are checked apart.
    assert "it runs another copy:" in _text(listed)
    assert OTHER_COPY in _text(listed)
    assert "solidworks entry updated" in _text(replaced)
    assert f"it ran {OTHER_COPY} before" in _text(replaced)
    assert _servers(desktop)["solidworks"]["command"] == LAUNCHER


def test_an_entry_for_this_copy_is_not_flagged(machine: dict[str, Any]) -> None:
    _run("--client", "claude-desktop", "--yes")

    result = _run("--dry-run", answers="1\n")

    assert "has a solidworks entry" in _text(result)
    assert "another copy" not in _text(result)


def test_a_malformed_entry_is_just_reported_as_present(machine: dict[str, Any]) -> None:
    machine["desktop"].write_text(json.dumps({"mcpServers": {"solidworks": "odd"}}))

    result = _run("--dry-run", answers="1\n")

    assert "has a solidworks entry" in _text(result)
    assert "another copy" not in _text(result)
