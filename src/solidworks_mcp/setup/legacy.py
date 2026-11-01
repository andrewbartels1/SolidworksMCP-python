"""Recognise older, hand-made config entries that start this same server.

Before ``solidworks-mcp setup`` existed, the README had people add entries
under names of their choosing, launched through ``run-mcp.ps1``,
``start_local_server_claude.py`` and similar. Left in place beside the new
``solidworks`` entry, they load every tool twice, and the PowerShell ones
can break the stdio connection.

The rule reads only an entry's ``command`` and ``args``. Secrets live in
``env`` and ``headers``, which are never looked at. It matches this
project's own launcher names exactly, so another vendor's SolidWorks server
is never mistaken for this one.
"""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Any

from .clients import SERVER_NAME

# Script files that only this project ships.
_OLD_SCRIPTS = frozenset(
    {
        "run-mcp.ps1",
        "run-mcp-claude.ps1",
        "start_local_server.py",
        "start_local_server_claude.py",
    }
)
# This package's console scripts, with or without `.exe`.
_OUR_LAUNCHERS = frozenset(
    {
        "solidworks-mcp",
        "solidworks-mcp.exe",
        "solidworks-mcp-python",
        "solidworks-mcp-python.exe",
    }
)
# `python -m <module>` forms that start this server.
_OUR_MODULES = frozenset({"solidworks_mcp.server", "solidworks_mcp"})


def launcher_name(entry: Any) -> str:
    """The program file an entry starts, for showing to the user.

    Args:
        entry: A server entry from a client config.

    Returns:
        The file name of its ``command`` (e.g. ``powershell.exe``), without the
        folder; ``?`` if it has none.
    """
    command = entry.get("command") if isinstance(entry, dict) else None
    return (
        PureWindowsPath(command).name if isinstance(command, str) and command else "?"
    )


def starts_this_server(entry: Any) -> bool:
    """Whether a config entry launches this project's server.

    Args:
        entry: A server entry from a client config.

    Returns:
        True when its command is one of this package's launchers, or its
        arguments name one of this project's launch scripts or modules.
    """
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    args = entry.get("args")
    words = [command] if isinstance(command, str) else []
    if isinstance(args, list):
        words += [a for a in args if isinstance(a, str)]

    # PureWindowsPath splits on both / and \, whatever OS this runs on.
    names = {PureWindowsPath(word).name.lower() for word in words}
    if names & _OLD_SCRIPTS or names & _OUR_LAUNCHERS:
        return True
    # `-m solidworks_mcp.server`: the word after each -m is a module name.
    modules = {words[i + 1] for i, word in enumerate(words[:-1]) if word == "-m"}
    return bool(modules & _OUR_MODULES)


def old_entries(servers: dict[str, Any]) -> list[str]:
    """Name every entry, besides ``solidworks``, that starts this server.

    Args:
        servers: A config's server entries (``mcpServers`` or ``servers``).

    Returns:
        Their names, in the config's order.
    """
    return [
        name
        for name, entry in servers.items()
        if name != SERVER_NAME and starts_this_server(entry)
    ]
