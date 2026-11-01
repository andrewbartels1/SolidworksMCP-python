"""Change one server entry in an MCP client's JSON config, and nothing else.

Client config files often hold other servers' secrets (API keys, OAuth
tokens). Everything here works on the parsed JSON: no function returns,
prints or logs the file's text or any entry other than the one it was asked
to change, and an error names only the file, line and column.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class ConfigFileError(Exception):
    """A client config file can't be read or safely changed."""


@dataclass(frozen=True)
class EntryChange:
    """What happened to the server entry in one client's config.

    Attributes:
        location: Where the entry lives (a file path, or a description).
        action: ``added``, ``updated``, ``removed`` or ``unchanged``.
        backup: The copy made before writing, if a file was overwritten.
        previous: For an ``updated`` entry, the ``command`` it ran before,
            so the user can see which copy it pointed at. Only the command
            is kept, never the rest of the entry.
    """

    location: str
    action: str
    backup: Path | None = None
    previous: str | None = None


def read_config(path: Path) -> dict[str, Any]:
    """Parse a client config file.

    Args:
        path: The JSON config file.

    Returns:
        The parsed object; ``{}`` for a missing or empty file.

    Raises:
        ConfigFileError: The file can't be read, isn't valid JSON, or isn't a
            JSON object. The message never quotes the file's content.
    """
    if not path.exists():
        return {}
    try:
        # utf-8-sig accepts a byte-order mark, which some editors add.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigFileError(f"Can't read {path}: {type(exc).__name__}.") from None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # `from None`: the original exception carries the document text.
        raise ConfigFileError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}). "
            "It was left untouched: fix it, or move it aside, and run solidworks-mcp setup again."
        ) from None
    if not isinstance(data, dict):
        raise ConfigFileError(f"{path} does not hold a JSON object; left untouched.")
    return data


def server_entries(path: Path, section: str) -> dict[str, Any]:
    """Read every server entry in a config, for inspection in code only.

    Callers must not print the entries: they may hold other servers' secrets.

    Args:
        path: The JSON config file.
        section: The object that holds the servers (``mcpServers``/``servers``).

    Returns:
        The entries by name; ``{}`` when the file or section is absent or the
        section isn't an object.
    """
    servers = read_config(path).get(section)
    return servers if isinstance(servers, dict) else {}


def current_entry(path: Path, section: str, name: str) -> Any:
    """Read one server entry.

    Args:
        path: The JSON config file.
        section: The object that holds the servers (``mcpServers``/``servers``).
        name: The server's key in that object.

    Returns:
        The entry, or ``None`` when the file, section or key is absent.
    """
    return server_entries(path, section).get(name)


def set_entry(
    path: Path,
    section: str,
    name: str,
    entry: dict[str, Any] | None,
    *,
    dry_run: bool = False,
) -> EntryChange:
    """Set ``section.name`` to ``entry``, or delete it when ``entry`` is None.

    Every other key in the file keeps its value and order. Before writing,
    the file is backed up; it is then written atomically as UTF-8 without a
    BOM, and read back to confirm it parses and holds the new entry.

    Args:
        path: The JSON config file; created, with its folder, if missing.
        section: The object that holds the servers.
        name: The server's key in that object.
        entry: The new entry, or ``None`` to remove it.
        dry_run: Work out the action but write nothing.

    Returns:
        What happened (or, with ``dry_run``, what would happen).

    Raises:
        ConfigFileError: The file can't be parsed, the section isn't an
            object, or the written file doesn't hold the entry.
    """
    data = read_config(path)
    servers = data.get(section, {})
    if not isinstance(servers, dict):
        raise ConfigFileError(
            f'"{section}" in {path} is not an object; left untouched.'
        )

    action = _action(servers, name, entry)
    previous = _command_of(servers.get(name)) if action == "updated" else None
    if action == "unchanged" or dry_run:
        return EntryChange(str(path), action, previous=previous)

    if entry is None:
        del servers[name]
    else:
        servers[name] = entry
    data[section] = servers

    backup = _backup(path)
    _write_atomically(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if current_entry(path, section, name) != entry:
        raise ConfigFileError(
            f"{path} did not hold the new entry after writing; "
            f"restore it from {backup}."
        )
    return EntryChange(str(path), action, backup, previous)


def _command_of(entry: Any) -> str | None:
    """An entry's ``command``, if it is a string.

    Args:
        entry: A server entry.

    Returns:
        The command, or ``None``.
    """
    command = entry.get("command") if isinstance(entry, dict) else None
    return command if isinstance(command, str) else None


def _action(servers: dict[str, Any], name: str, entry: dict[str, Any] | None) -> str:
    """Name the change that setting ``servers[name] = entry`` would make.

    Args:
        servers: The current server entries.
        name: The server's key.
        entry: The new entry, or ``None`` for a removal.

    Returns:
        ``added``, ``updated``, ``removed`` or ``unchanged``.
    """
    if entry is None:
        return "removed" if name in servers else "unchanged"
    if servers.get(name) == entry:
        return "unchanged"
    return "updated" if name in servers else "added"


def _backup(path: Path) -> Path | None:
    """Copy ``path`` byte for byte to a timestamped file beside it.

    The timestamp means a second run never overwrites the first backup,
    which holds the user's original file.

    Args:
        path: The file about to be overwritten.

    Returns:
        The backup's path, or ``None`` if there was no file to back up.
    """
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return backup


def _write_atomically(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` so a reader never sees half a file.

    Args:
        path: The file to write; its folder is created if missing.
        text: The new content, written as UTF-8 without a BOM.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        # os.replace is atomic on one volume: the old file or the new, never neither.
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
