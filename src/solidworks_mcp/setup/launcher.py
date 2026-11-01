"""The command a client config runs to start this server.

It is always an absolute path in the environment setup itself runs from, so
the config works no matter where the client starts it or what its PATH is.
"""

from __future__ import annotations

import sys
from pathlib import Path


def server_command(
    mock: bool = False, python: str | None = None
) -> tuple[str, list[str]]:
    """Find the launcher beside this Python, and its arguments.

    Args:
        mock: Add ``--mock``, so the server answers without SolidWorks.
        python: The interpreter to look beside; defaults to ``sys.executable``.

    Returns:
        ``(command, args)``: the ``solidworks-mcp`` console script in the
        environment's scripts folder or, without one, this Python running the
        server module.
    """
    python = python or sys.executable
    flags = ["--mock"] if mock else []
    scripts = Path(python).parent
    # `.exe` on Windows; the bare name elsewhere.
    for name in ("solidworks-mcp.exe", "solidworks-mcp"):
        launcher = scripts / name
        if launcher.is_file():
            return str(launcher), flags
    return python, ["-m", "solidworks_mcp.server", *flags]
