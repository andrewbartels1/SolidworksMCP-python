"""How big the tool list is that a client receives, per toolset and mode.

Every tool's name, description and input schema is sent to the model on
every turn, so the list's size is a cost the user pays all session. This
module lists the tools exactly as a client would (an in-process client on
the server, with the mock adapter) and measures the ``tools/list`` reply::

    python -m solidworks_mcp.progress.tool_list_size

It writes ``docs/assets/progress/tool-list-size.md``, the table the
installation guide includes; ``python -m solidworks_mcp.progress.generate``
writes it too, and ``tests/integration/test_progress_up_to_date.py`` fails
when it is out of date. Tokens are an estimate: bytes divided by 4.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client, FastMCP

from ..adapters.mock_adapter import MockSolidWorksAdapter
from ..tools import register_tools
from ..tools.toolsets import ALL, TOOLSETS, apply_tool_visibility

#: The generated table, relative to the repository root.
OUTPUT = Path("docs/assets/progress/tool-list-size.md")
#: Bytes per token, for the estimate.
BYTES_PER_TOKEN = 4

#: The settings the table measures: (toolsets, mode).
CHOICES: tuple[tuple[tuple[str, ...], str], ...] = (
    ((ALL,), "list"),
    *(((name,), "list") for name in TOOLSETS),
    (("core", "drawing"), "list"),
    ((ALL,), "search"),
    (("core",), "search"),
)


@dataclass(frozen=True)
class Listing:
    """What one choice of settings lists.

    Attributes:
        toolsets: The toolsets shown.
        mode: ``list`` or ``search``.
        tools: How many tools are listed.
        size_bytes: The ``tools/list`` reply's tools, as JSON, in bytes.
    """

    toolsets: tuple[str, ...]
    mode: str
    tools: int
    size_bytes: int

    @property
    def tokens(self) -> int:
        """An estimate of the tokens the list costs on every turn."""
        return round(self.size_bytes / BYTES_PER_TOKEN)


async def listed_tools(toolsets: tuple[str, ...], mode: str) -> list[Any]:
    """The tools a client is sent for these settings.

    Args:
        toolsets: Names from ``parse_toolsets``.
        mode: ``list`` or ``search``.

    Returns:
        list[Any]: The MCP ``Tool`` objects of the ``tools/list`` reply.
    """
    mcp = FastMCP("tool-list-size")
    await register_tools(mcp, MockSolidWorksAdapter({}), {})
    apply_tool_visibility(mcp, toolsets, mode)
    async with Client(mcp) as client:
        return list(await client.list_tools())


async def measure(toolsets: tuple[str, ...], mode: str) -> Listing:
    """Measure the list for one choice of settings.

    Args:
        toolsets: Names from ``parse_toolsets``.
        mode: ``list`` or ``search``.

    Returns:
        Listing: The count and size.
    """
    tools = await listed_tools(toolsets, mode)
    size = sum(
        len(tool.model_dump_json(exclude_none=True).encode("utf-8")) for tool in tools
    )
    return Listing(toolsets, mode, len(tools), size)


def table(listings: list[Listing]) -> str:
    """The Markdown table of the measured choices.

    Args:
        listings: One per choice, the first being every tool listed.

    Returns:
        str: The table, ending in a newline.
    """
    full = listings[0].size_bytes
    lines = [
        "| `SOLIDWORKS_MCP_TOOLSETS` | `SOLIDWORKS_MCP_TOOL_MODE` | Tools listed "
        "| Size | Tokens (estimate) | Of the full list |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in listings:
        lines.append(
            f"| `{','.join(item.toolsets)}` | `{item.mode}` | {item.tools} "
            f"| {item.size_bytes / 1024:.0f} KB | {item.tokens:,} "
            f"| {100 * item.size_bytes / full:.0f}% |"
        )
    return "\n".join(lines) + "\n"


async def _measure_all() -> list[Listing]:
    """Every choice in :data:`CHOICES`, measured."""
    return [await measure(toolsets, mode) for toolsets, mode in CHOICES]


def build() -> str:
    """The generated table's content.

    Returns:
        str: The Markdown table.
    """
    return table(asyncio.run(_measure_all()))


def main(root: Path | None = None) -> Path:
    """Write the table under ``root``.

    Args:
        root: The repository root; the current directory when omitted.

    Returns:
        Path: The file written.
    """
    path = (root or Path.cwd()) / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(), encoding="utf-8", newline="\n")
    return path


if __name__ == "__main__":
    print(main())
