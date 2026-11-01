"""Add or remove the server entry for one client, by that client's own means.

Most clients read a JSON file (:class:`JsonFileRegistrar`); Claude Code is
configured through its ``claude mcp`` command (:class:`ClaudeCliRegistrar`).
:func:`registrar_for` picks one, so the setup wizard never needs to know
which kind of client it is talking to.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from .clients import SERVER_NAME, Client
from .config_file import ConfigFileError, EntryChange, server_entries, set_entry
from .legacy import launcher_name, old_entries

# subprocess.run's shape, so tests can pass a fake runner.
Runner = Callable[..., subprocess.CompletedProcess[str]]


class Registrar(Protocol):
    """Changes a client's ``solidworks`` entry."""

    def apply(self, entry: dict[str, Any] | None, *, dry_run: bool) -> EntryChange:
        """Add or update ``entry``, or remove the entry when it is None.

        Args:
            entry: The entry to write, or ``None`` to remove it.
            dry_run: Report what would change, and change nothing.

        Returns:
            What happened.
        """
        ...


@runtime_checkable
class OldEntryCleaner(Protocol):
    """Finds and removes older entries that start this same server.

    Only registrars that can read their client's entries implement this.
    Claude Code's are held by its CLI, so it doesn't.
    """

    def old_entries(self) -> list[tuple[str, str]]:
        """List the older entries for this server.

        Returns:
            ``(name, launcher file name)`` for each, safe to print.
        """
        ...

    def remove_entry(self, name: str, *, dry_run: bool) -> EntryChange:
        """Remove one entry by name.

        Args:
            name: The entry's key.
            dry_run: Report what would change, and change nothing.

        Returns:
            What happened.
        """
        ...


class JsonFileRegistrar:
    """Edits the ``solidworks`` entry in the client's JSON config file.

    It also implements :class:`OldEntryCleaner`, since it can read the file.
    """

    def __init__(self, client: Client) -> None:
        """Bind to a file-configured client.

        Args:
            client: A client whose ``config_path`` is set.
        """
        assert client.config_path is not None
        self._path = client.config_path
        self._section = client.section

    def apply(self, entry: dict[str, Any] | None, *, dry_run: bool) -> EntryChange:
        """Set or remove the entry in the file (see :func:`set_entry`).

        Args:
            entry: The entry to write, or ``None`` to remove it.
            dry_run: Report what would change, and change nothing.

        Returns:
            What happened, with the backup made before writing.
        """
        return set_entry(self._path, self._section, SERVER_NAME, entry, dry_run=dry_run)

    def old_entries(self) -> list[tuple[str, str]]:
        """List the file's older entries that start this server.

        Returns:
            ``(name, launcher file name)`` for each (see :mod:`.legacy`).
        """
        servers = server_entries(self._path, self._section)
        return [(name, launcher_name(servers[name])) for name in old_entries(servers)]

    def remove_entry(self, name: str, *, dry_run: bool) -> EntryChange:
        """Remove one entry from the file, with the same care as :meth:`apply`.

        Args:
            name: The entry's key.
            dry_run: Report what would change, and change nothing.

        Returns:
            What happened, with the backup made before writing.
        """
        return set_entry(self._path, self._section, name, None, dry_run=dry_run)


class ClaudeCliRegistrar:
    """Registers the server with ``claude mcp add --scope user``."""

    def __init__(self, client: Client, run: Runner = subprocess.run) -> None:
        """Bind to Claude Code.

        Args:
            client: The Claude Code client; ``found`` says if ``claude`` is on the PATH.
            run: How to run a command (``subprocess.run``, or a fake in tests).
        """
        self._found = client.found
        self._run = run

    def apply(self, entry: dict[str, Any] | None, *, dry_run: bool) -> EntryChange:
        """Run ``claude mcp`` to add or remove the server.

        Without ``claude`` on the PATH, or with ``dry_run``, nothing runs and
        the change reports the command for the user to run.

        Args:
            entry: The entry to register, or ``None`` to remove it.
            dry_run: Report the command, and run nothing.

        Returns:
            What happened; ``location`` is the command line.

        Raises:
            ConfigFileError: ``claude mcp add`` failed.
        """
        remove = ["claude", "mcp", "remove", "--scope", "user", SERVER_NAME]
        command = remove if entry is None else self._add_command(entry)
        shown = subprocess.list2cmdline(command)
        action = "removed" if entry is None else "added"
        if dry_run or not self._found:
            return EntryChange(shown, "not run" if not self._found else action)

        # `add` fails if the name exists, so clear any old entry first; a
        # failed remove only means there was nothing to remove.
        self._run(remove, capture_output=True, text=True)
        if entry is None:
            return EntryChange(shown, action)
        result = self._run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise ConfigFileError(
                f"'claude mcp add' failed (exit {result.returncode}); run it yourself: {shown}"
            )
        return EntryChange(shown, action)

    @staticmethod
    def _add_command(entry: dict[str, Any]) -> list[str]:
        """The ``claude mcp add`` command line for ``entry``.

        Args:
            entry: A ``{"command": ..., "args": [...]}`` server entry.

        Returns:
            The command, with the server's own command after ``--``.
        """
        return [
            "claude", "mcp", "add", "--scope", "user", SERVER_NAME,
            "--", entry["command"], *entry["args"],
        ]  # fmt: skip


def registrar_for(client: Client) -> Registrar:
    """The registrar that knows how to configure ``client``.

    Args:
        client: A client from :func:`~.clients.find_clients`.

    Returns:
        A file registrar for file-configured clients, else the Claude CLI one.
    """
    if client.config_path is None:
        return ClaudeCliRegistrar(client)
    return JsonFileRegistrar(client)
