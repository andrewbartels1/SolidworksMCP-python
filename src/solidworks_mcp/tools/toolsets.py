"""Which tools a client sees: toolsets, and the search mode (queue item 14).

Every tool is registered; these settings only change what ``tools/list``
shows. ``SOLIDWORKS_MCP_TOOLSETS`` picks groups of families (each tool is
tagged with its family by ``ToolRegistrar``), and
``SOLIDWORKS_MCP_TOOL_MODE=search`` replaces the list with FastMCP's
``search_tools`` and ``call_tool``.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.transforms.search import BM25SearchTransform

#: Each toolset's families (the modules that define the tools).
TOOLSETS: dict[str, frozenset[str]] = {
    "core": frozenset(
        {
            "modeling",
            "sketching",
            "file_management",
            "analysis",
            "engineering_data",
            "export",
            "server_admin",
        }
    ),
    "drawing": frozenset({"drawing", "drawing_automation", "drawing_analysis"}),
    "automation": frozenset({"macro_recording", "automation", "template_management"}),
    "vba": frozenset({"vba_generation"}),
    "docs": frozenset({"docs_discovery"}),
}
#: The setting's value for every toolset (the default).
ALL = "all"
#: The two tool modes; ``list`` is the default.
TOOL_MODES = ("list", "search")
#: Tools listed beside ``search_tools`` and ``call_tool`` in search mode.
ALWAYS_VISIBLE = ("get_model_info", "reset_circuit_breaker")
#: The tag ``ToolRegistrar`` gives deprecated tools.
DEPRECATED_TAG = "level:deprecated"
#: How many tools one search returns.
SEARCH_RESULTS = 5


def parse_toolsets(text: str) -> tuple[str, ...]:
    """The toolsets a ``SOLIDWORKS_MCP_TOOLSETS`` value names, in table order.

    Args:
        text: Comma-separated toolset names, or ``all``; case and spaces
            don't matter.

    Returns:
        tuple[str, ...]: The names, or ``("all",)``.

    Raises:
        ValueError: When the value is empty or names an unknown toolset.
    """
    names = {part.strip().lower() for part in text.split(",") if part.strip()}
    valid = ", ".join([*TOOLSETS, ALL])
    if not names:
        raise ValueError(f"toolsets is empty; give one or more of {valid}")
    unknown = sorted(names - set(TOOLSETS) - {ALL})
    if unknown:
        raise ValueError(
            f"Unknown toolset(s) {', '.join(unknown)}; the toolsets are {valid}"
        )
    if ALL in names:
        return (ALL,)
    return tuple(name for name in TOOLSETS if name in names)


def families_for(toolsets: tuple[str, ...]) -> frozenset[str] | None:
    """The families the chosen toolsets show.

    Args:
        toolsets: Names from :func:`parse_toolsets`.

    Returns:
        frozenset[str] | None: The families, or ``None`` for every one.
    """
    if ALL in toolsets:
        return None
    return frozenset().union(*(TOOLSETS[name] for name in toolsets))


def apply_tool_visibility(mcp: Any, toolsets: tuple[str, ...], mode: str) -> None:
    """Show only the chosen toolsets, and in search mode only search and call.

    Call it after every tool is registered. The toolset filter comes first,
    so a search finds only tools in the chosen toolsets. Search mode also
    leaves deprecated tools out, so a search returns their replacements.

    Args:
        mcp: The FastMCP server.
        toolsets: Names from :func:`parse_toolsets`.
        mode: ``list`` or ``search``.
    """
    families = families_for(toolsets)
    if families is not None:
        mcp.enable(tags=set(families), only=True)
    if mode == "search":
        mcp.disable(tags={DEPRECATED_TAG})
        mcp.add_transform(
            BM25SearchTransform(
                max_results=SEARCH_RESULTS, always_visible=list(ALWAYS_VISIBLE)
            )
        )
