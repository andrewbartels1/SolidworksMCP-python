"""The command a client config runs to start this server.

It is always an absolute path, so the config works no matter where the
client starts it or what its PATH is. Usually it is the launcher in the
environment setup itself runs from. When that environment is a temporary
one in uv's cache (``uvx solidworks-mcp-python setup``), it is ``uvx``
instead, because the cache folder disappears when uv cleans it.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

# The PyPI name; `uvx solidworks-mcp` would install a different project.
PACKAGE = "solidworks-mcp-python"

# uvx runs a tool from `<uv cache>/archive-v<n>/<hash>/`.
_UV_ARCHIVE = re.compile(r"archive-v\d+", re.IGNORECASE)


def in_uv_cache(python: str) -> bool:
    """Whether an interpreter lives in a temporary environment in uv's cache.

    ``uv tool install`` environments (under ``uv\\tools``) and project
    ``.venv`` folders are persistent and don't count.

    Args:
        python: The interpreter's path.

    Returns:
        True when a ``cache`` folder holds an ``archive-v<n>`` folder on the
        path to it.
    """
    parts = [part.lower() for part in Path(python).parts]
    return any(
        _UV_ARCHIVE.fullmatch(part) and "cache" in parts[:index]
        for index, part in enumerate(parts)
    )


def find_uvx(
    uv: str | None = None, which: Callable[[str], str | None] = shutil.which
) -> str | None:
    """Find the ``uvx`` launcher, by absolute path.

    Args:
        uv: The uv executable; defaults to the ``UV`` variable uv sets for
            the programs it runs.
        which: PATH lookup, replaceable in tests.

    Returns:
        ``uvx`` beside uv if it is there, else on the PATH, else ``None``.
    """
    uv = uv if uv is not None else os.environ.get("UV")
    if uv:
        for name in ("uvx.exe", "uvx"):
            beside = Path(uv).parent / name
            if beside.is_file():
                return str(beside)
    return which("uvx")


def server_command(
    mock: bool = False,
    python: str | None = None,
    lasting: bool = True,
    uvx_finder: Callable[[], str | None] = find_uvx,
) -> tuple[str, list[str]]:
    """The command and arguments that start this server.

    Args:
        mock: Add ``--mock``, so the server answers without SolidWorks.
        python: The interpreter to look beside; defaults to ``sys.executable``.
        lasting: Return a command that outlives a temporary uv environment.
            ``False`` gives the launcher that runs right now, which is what
            the start-up check needs.
        uvx_finder: Finds ``uvx``, replaceable in tests.

    Returns:
        ``(command, args)``: ``uvx`` running this package when ``lasting`` and
        the interpreter is in uv's cache; otherwise the ``solidworks-mcp``
        console script in the environment's scripts folder or, without one,
        this Python running the server module.
    """
    python = python or sys.executable
    flags = ["--mock"] if mock else []
    if lasting and in_uv_cache(python):
        uvx = uvx_finder()
        if uvx:
            return uvx, [PACKAGE, *flags]
    scripts = Path(python).parent
    # `.exe` on Windows; the bare name elsewhere.
    for name in ("solidworks-mcp.exe", "solidworks-mcp"):
        launcher = scripts / name
        if launcher.is_file():
            return str(launcher), flags
    return python, ["-m", "solidworks_mcp.server", *flags]
