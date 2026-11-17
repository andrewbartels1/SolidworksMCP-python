"""The report's environment section: SolidWorks, Python and this package."""

from __future__ import annotations

import platform
from importlib import metadata
from typing import Any

from ..version import __version__


def _package_version(name: str) -> str | None:
    """An installed distribution's version, or ``None`` when it isn't installed."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


async def read_environment(
    adapter: Any,
    year: int | None,
    toolsets: tuple[str, ...] = ("all",),
    mode: str = "list",
) -> dict[str, Any]:
    """Describe the setup the selftest ran on.

    A value that can't be read is ``None``; nothing here stops the run.

    Args:
        adapter: The connected adapter.
        year: The SolidWorks year the server was started with.
        toolsets: The toolsets the user's settings show.
        mode: The user's tool mode.

    Returns:
        dict[str, Any]: ``solidworks`` (``revision``, ``language``,
        ``templates``, ``year``), ``tools`` (``toolsets``, ``mode`` and how
        many tools those settings list), ``os``, ``python``, ``pywin32`` and
        ``solidworks_mcp`` versions.
    """
    from ..progress.tool_list_size import listed_tools

    info = await adapter.get_application_info()
    data = info.data if info.is_success and info.data else {}
    return {
        "solidworks": {
            "revision": data.get("revision"),
            "language": data.get("language"),
            "year": year,
            "templates": data.get("templates") or {},
        },
        "tools": {
            "toolsets": ",".join(toolsets),
            "mode": mode,
            "listed": len(await listed_tools(toolsets, mode)),
        },
        "os": platform.platform(),
        "python": platform.python_version(),
        "pywin32": _package_version("pywin32"),
        "solidworks_mcp": __version__,
    }
