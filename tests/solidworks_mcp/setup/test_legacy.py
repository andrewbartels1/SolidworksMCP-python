"""Tests for recognising older entries that start this server."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.setup.legacy import launcher_name, old_entries, starts_this_server

REPO = r"C:\Users\me\dev\SolidworksMCP-python"


@pytest.mark.parametrize(
    "entry",
    [
        # The README's PowerShell launchers.
        {"command": "powershell", "args": ["-NoProfile", "-File", rf"{REPO}\deployment\run-mcp.ps1"]},
        {"command": "pwsh.exe", "args": ["-File", f"{REPO}/deployment/run-mcp-claude.ps1"]},
        # The Python launcher scripts.
        {"command": rf"{REPO}\.venv\Scripts\python.exe",
         "args": [rf"{REPO}\src\utils\start_local_server_claude.py", "--real"]},
        {"command": "python", "args": ["src/utils/START_LOCAL_SERVER.py"]},
        # The module and the console scripts.
        {"command": "python", "args": ["-m", "solidworks_mcp.server"]},
        {"command": rf"{REPO}\.venv\Scripts\solidworks-mcp.exe", "args": []},
        {"command": "uvx", "args": ["solidworks-mcp-python"]},
    ],
)  # fmt: skip
def test_old_launchers_are_recognised(entry: dict[str, Any]) -> None:
    assert starts_this_server(entry)


@pytest.mark.parametrize(
    "entry",
    [
        # Other vendors' SolidWorks servers.
        {"command": "npx", "args": ["-y", "solidworks-mcp-server"]},
        {"command": "node", "args": [r"C:\tools\solidworks-mcp\dist\index.js"]},
        {"command": "python", "args": ["-m", "solidworks_mcp_other.server"]},
        # Unrelated servers, and malformed entries.
        {"command": "cmd", "args": ["/c", "npx", "@playwright/mcp"]},
        {"type": "http", "url": "https://api.githubcopilot.com/mcp/"},
        {"command": "python", "args": ["-m"]},
        {"command": 5, "args": "run-mcp.ps1"},
        "run-mcp.ps1",
    ],
)
def test_other_servers_are_not(entry: Any) -> None:
    assert not starts_this_server(entry)


def test_old_entries_skip_the_current_one_and_never_read_env() -> None:
    class Untouchable(dict[str, Any]):
        """An env block that fails the test if anything reads it."""

        def __getitem__(self, key: str) -> Any:
            raise AssertionError("env was read")

        def get(self, key: str, default: Any = None) -> Any:
            raise AssertionError("env was read")

    servers = {
        "todo": {"command": "todo.exe", "env": Untouchable(SECRET="x")},
        "solidworks-mcp-server": {
            "command": "powershell",
            "args": ["-File", "run-mcp.ps1"],
        },
        "solidworks": {"command": "solidworks-mcp.exe", "args": []},
    }

    assert old_entries(servers) == ["solidworks-mcp-server"]


@pytest.mark.parametrize(
    ("entry", "name"),
    [
        ({"command": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"}, "powershell.exe"),
        ({"command": "/usr/bin/python3"}, "python3"),
        ({"url": "https://example.com"}, "?"),
        ({"command": ""}, "?"),
        ("not an entry", "?"),
    ],
)  # fmt: skip
def test_launcher_name(entry: Any, name: str) -> None:
    assert launcher_name(entry) == name
