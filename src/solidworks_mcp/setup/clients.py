"""The MCP clients setup knows, where each keeps its config, and if it's installed.

Detection only looks at whether folders and files exist; it never reads a
config file (see :mod:`.config_file` for that).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The key the server is registered under in every client.
SERVER_NAME = "solidworks"


@dataclass(frozen=True)
class Client:
    """One MCP client and how to register a server with it.

    Attributes:
        key: The name used with ``--client`` (e.g. ``claude-desktop``).
        name: The name shown to the user.
        found: Whether the client looks installed.
        config_path: Its JSON config file; ``None`` for a client configured
            through its own CLI (Claude Code).
        section: The object in the config that holds the servers.
        stdio_type: Whether entries need ``"type": "stdio"`` (VS Code).
        restart_hint: What to do after setup so the client loads the server.
    """

    key: str
    name: str
    found: bool
    config_path: Path | None
    section: str = "mcpServers"
    stdio_type: bool = False
    restart_hint: str = ""

    def entry(self, command: str, args: list[str]) -> dict[str, Any]:
        """Build the server entry in the shape this client expects.

        Args:
            command: The absolute launcher path.
            args: The launcher's arguments.

        Returns:
            The JSON entry for the config file.
        """
        entry: dict[str, Any] = {"command": command, "args": args}
        return {"type": "stdio", **entry} if self.stdio_type else entry


def claude_desktop_config(env: Mapping[str, str]) -> tuple[Path, bool]:
    """Find Claude Desktop's config file.

    Claude Desktop has kept its config in three places across releases:
    ``%LOCALAPPDATA%\\Claude-Data\\claude_<id>`` (newest), the MSIX package's
    ``LocalCache\\Roaming\\Claude``, and ``%APPDATA%\\Claude`` (classic). An
    existing file wins, newest location first, since that is the one the app
    is reading. With no file, it goes in the newest location whose folder
    exists, i.e. the install that is present.

    Args:
        env: The environment (for ``LOCALAPPDATA`` and ``APPDATA``).

    Returns:
        The config file's path, and whether Claude Desktop was found.
    """
    local = Path(env.get("LOCALAPPDATA", ""))
    roaming = Path(env.get("APPDATA", ""))
    folders = [
        *sorted(local.glob("Claude-Data/claude_*")),
        *(
            p / "LocalCache/Roaming/Claude"
            for p in sorted(local.glob("Packages/Claude_*"))
        ),
        roaming / "Claude",
    ]
    files = [folder / "claude_desktop_config.json" for folder in folders]
    for file in files:
        if file.is_file():
            return file, True
    for file in files:
        if file.parent.is_dir():
            return file, True
    return files[-1], False


def find_clients(
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> list[Client]:
    """List every supported client, found or not, in the order they are offered.

    Args:
        env: The environment; defaults to ``os.environ``.
        which: How to look up a command on the PATH (for ``claude``).

    Returns:
        The clients, with ``found`` and ``config_path`` filled in.
    """
    env = os.environ if env is None else env
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    roaming = Path(env.get("APPDATA", ""))

    desktop_file, desktop_found = claude_desktop_config(env)
    vscode_file = roaming / "Code/User/mcp.json"
    cursor_file = home / ".cursor/mcp.json"
    lmstudio_file = home / ".lmstudio/mcp.json"
    return [
        Client(
            "claude-desktop",
            "Claude Desktop",
            desktop_found,
            desktop_file,
            # Claude Desktop also saves its preferences to this file, so a copy
            # still running in the tray may write over the entry; quitting it
            # fully before rerunning setup avoids that.
            restart_hint="Quit Claude Desktop from the system tray, then reopen it; "
            "Settings > Developer then shows solidworks as running. If the entry "
            "is gone, quit Claude Desktop fully and run solidworks-mcp setup again.",
        ),
        Client(
            "claude-code",
            "Claude Code",
            which("claude") is not None,
            None,
            restart_hint="Run /mcp in a new Claude Code session.",
        ),
        Client(
            "vscode",
            "VS Code",
            vscode_file.parent.is_dir(),
            vscode_file,
            section="servers",
            stdio_type=True,
            restart_hint="Run 'MCP: List Servers' from the Command Palette and start solidworks.",
        ),
        Client(
            "cursor",
            "Cursor",
            cursor_file.parent.is_dir(),
            cursor_file,
            restart_hint="Restart Cursor and check solidworks is enabled in its MCP settings.",
        ),
        Client(
            "lmstudio",
            "LM Studio",
            lmstudio_file.parent.is_dir(),
            lmstudio_file,
            restart_hint="Restart LM Studio and enable solidworks in the Program tab.",
        ),
    ]
