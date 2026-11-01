"""Tests for the one-entry JSON config editor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.setup import config_file
from solidworks_mcp.setup.config_file import (
    ConfigFileError,
    current_entry,
    read_config,
    set_entry,
)

SECRET = "sk-very-secret-token"
ENTRY = {"command": r"C:\venv\Scripts\solidworks-mcp.exe", "args": []}


def _config_with_a_secret(path: Path) -> dict:
    data = {
        "mcpServers": {
            "todo": {"command": "todo.exe", "env": {"CLIENT_SECRET": SECRET}},
        },
        "preferences": {"theme": "dark"},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_other_entries_survive_and_the_secret_never_leaks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "claude_desktop_config.json"
    original = _config_with_a_secret(path)

    change = set_entry(path, "mcpServers", "solidworks", ENTRY)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["todo"] == original["mcpServers"]["todo"]
    assert data["preferences"] == original["preferences"]
    assert data["mcpServers"]["solidworks"] == ENTRY
    assert change.action == "added"
    assert SECRET not in repr(change)
    assert change.location == str(path)
    assert SECRET not in capsys.readouterr().out


def test_the_backup_is_the_original_bytes(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    _config_with_a_secret(path)
    before = path.read_bytes()

    change = set_entry(path, "mcpServers", "solidworks", ENTRY)

    assert change.backup is not None
    assert change.backup.read_bytes() == before
    assert change.backup.name.startswith("c.json.bak-")


def test_written_without_a_bom_and_no_temp_file_left(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_bytes(b'\xef\xbb\xbf{"mcpServers": {}}')

    set_entry(path, "mcpServers", "solidworks", ENTRY)

    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not (tmp_path / "c.json.tmp").exists()


def test_a_missing_file_and_folder_are_created_without_a_backup(tmp_path: Path) -> None:
    path = tmp_path / "new" / "mcp.json"

    change = set_entry(path, "servers", "solidworks", ENTRY)

    assert change.action == "added"
    assert change.backup is None
    assert json.loads(path.read_text())["servers"]["solidworks"] == ENTRY


@pytest.mark.parametrize(
    ("existing", "entry", "action"),
    [
        (ENTRY, ENTRY, "unchanged"),
        ({"command": "old.exe", "args": []}, ENTRY, "updated"),
        (ENTRY, None, "removed"),
        (None, None, "unchanged"),
    ],
)
def test_actions(
    tmp_path: Path,
    existing: dict[str, Any] | None,
    entry: dict[str, Any] | None,
    action: str,
) -> None:
    path = tmp_path / "c.json"
    servers = {"other": {"command": "x"}}
    if existing is not None:
        servers["solidworks"] = existing
    path.write_text(json.dumps({"mcpServers": servers}))

    change = set_entry(path, "mcpServers", "solidworks", entry)

    assert change.action == action
    after = json.loads(path.read_text())["mcpServers"]
    assert after["other"] == {"command": "x"}
    assert after.get("solidworks") == (entry if action != "unchanged" else existing)
    assert (change.backup is None) == (action == "unchanged")


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    _config_with_a_secret(path)
    before = path.read_bytes()

    change = set_entry(path, "mcpServers", "solidworks", ENTRY, dry_run=True)

    assert change.action == "added"
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_json_is_untouched_and_the_error_has_no_content(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text('{\n  "mcpServers": {"todo": {"key": "' + SECRET + '"}},,\n}')
    before = path.read_bytes()

    with pytest.raises(ConfigFileError) as caught:
        set_entry(path, "mcpServers", "solidworks", ENTRY)

    message = str(caught.value)
    assert "line 2" in message and "column" in message
    assert SECRET not in message
    assert caught.value.__cause__ is None
    assert path.read_bytes() == before


def test_a_file_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("[1, 2]")

    with pytest.raises(ConfigFileError, match="does not hold a JSON object"):
        read_config(path)


def test_a_section_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text('{"mcpServers": []}')

    with pytest.raises(ConfigFileError, match='"mcpServers" .* is not an object'):
        set_entry(path, "mcpServers", "solidworks", ENTRY)
    assert current_entry(path, "mcpServers", "solidworks") is None


def test_an_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(ConfigFileError, match="Can't read .*UnicodeDecodeError"):
        read_config(path)


def test_empty_and_missing_files_are_empty_configs(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("  \n")

    assert read_config(empty) == {}
    assert read_config(tmp_path / "missing.json") == {}


def test_a_write_that_does_not_stick_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "c.json"
    path.write_text("{}")
    monkeypatch.setattr(config_file, "_write_atomically", lambda p, text: None)

    with pytest.raises(ConfigFileError, match="did not hold the new entry"):
        set_entry(path, "mcpServers", "solidworks", ENTRY)


@pytest.mark.parametrize(
    ("old", "previous"),
    [
        ({"command": "old.exe", "args": []}, "old.exe"),
        ("not an entry", None),
        ({"args": []}, None),
    ],
)
def test_an_update_names_the_previous_command_only(
    tmp_path: Path, old: Any, previous: str | None
) -> None:
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"mcpServers": {"solidworks": old}}))

    dry = set_entry(path, "mcpServers", "solidworks", ENTRY, dry_run=True)
    change = set_entry(path, "mcpServers", "solidworks", ENTRY)

    assert dry.previous == change.previous == previous
    assert set_entry(path, "mcpServers", "solidworks", None).previous is None
