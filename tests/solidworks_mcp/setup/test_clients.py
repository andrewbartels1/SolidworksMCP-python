"""Tests for finding MCP clients and their config files."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.setup.clients import Client, claude_desktop_config, find_clients


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "LOCALAPPDATA": str(tmp_path / "Local"),
        "APPDATA": str(tmp_path / "Roaming"),
        "USERPROFILE": str(tmp_path / "home"),
    }


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    return path


def test_claude_data_config_wins(tmp_path: Path) -> None:
    env = _env(tmp_path)
    newest = _touch(
        tmp_path / "Local/Claude-Data/claude_abc/claude_desktop_config.json"
    )
    _touch(tmp_path / "Roaming/Claude/claude_desktop_config.json")

    assert claude_desktop_config(env) == (newest, True)


def test_packaged_config_beats_classic(tmp_path: Path) -> None:
    env = _env(tmp_path)
    packaged = _touch(
        tmp_path
        / "Local/Packages/Claude_xyz/LocalCache/Roaming/Claude/claude_desktop_config.json"
    )
    _touch(tmp_path / "Roaming/Claude/claude_desktop_config.json")

    assert claude_desktop_config(env) == (packaged, True)


def test_an_existing_file_beats_a_newer_empty_folder(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (tmp_path / "Local/Claude-Data/claude_abc").mkdir(parents=True)
    classic = _touch(tmp_path / "Roaming/Claude/claude_desktop_config.json")

    assert claude_desktop_config(env) == (classic, True)


def test_no_file_goes_in_the_newest_existing_folder(tmp_path: Path) -> None:
    env = _env(tmp_path)
    folder = tmp_path / "Local/Claude-Data/claude_abc"
    folder.mkdir(parents=True)
    (tmp_path / "Roaming/Claude").mkdir(parents=True)

    assert claude_desktop_config(env) == (folder / "claude_desktop_config.json", True)


def test_claude_desktop_not_installed(tmp_path: Path) -> None:
    path, found = claude_desktop_config(_env(tmp_path))

    assert not found
    assert path == tmp_path / "Roaming/Claude/claude_desktop_config.json"


def test_find_clients(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (tmp_path / "Roaming/Code/User").mkdir(parents=True)
    (tmp_path / "home/.lmstudio").mkdir(parents=True)

    clients = {c.key: c for c in find_clients(env, which=lambda name: None)}

    assert list(clients) == [
        "claude-desktop",
        "claude-code",
        "vscode",
        "cursor",
        "lmstudio",
    ]
    assert [k for k, c in clients.items() if c.found] == ["vscode", "lmstudio"]
    assert clients["vscode"].config_path == tmp_path / "Roaming/Code/User/mcp.json"
    assert clients["vscode"].section == "servers"
    assert clients["claude-code"].config_path is None
    assert all(c.restart_hint for c in clients.values())


def test_claude_code_found_on_the_path(tmp_path: Path) -> None:
    clients = find_clients(_env(tmp_path), which=lambda name: "/bin/claude")

    assert next(c for c in clients if c.key == "claude-code").found


def test_find_clients_defaults_to_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, value in _env(tmp_path).items():
        monkeypatch.setenv(name, value)

    clients = find_clients()

    assert (
        clients[0].config_path == tmp_path / "Roaming/Claude/claude_desktop_config.json"
    )


def test_entries() -> None:
    plain = Client("c", "C", True, None)
    vscode = Client("v", "V", True, None, section="servers", stdio_type=True)

    assert plain.entry("x.exe", ["--mock"]) == {"command": "x.exe", "args": ["--mock"]}
    assert vscode.entry("x.exe", []) == {
        "type": "stdio",
        "command": "x.exe",
        "args": [],
    }
