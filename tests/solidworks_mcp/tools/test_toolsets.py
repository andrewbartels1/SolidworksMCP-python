"""Toolsets and the search mode, on the real tools (queue item 14).

Specs: setup/toolsets, setup/tool-search-mode.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.tool_boundary import tool_family
from solidworks_mcp.tools.toolsets import (
    ALWAYS_VISIBLE,
    TOOLSETS,
    apply_tool_visibility,
    families_for,
    parse_toolsets,
)


async def _server(toolsets: tuple[str, ...] = ("all",), mode: str = "list") -> Any:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    mcp = FastMCP("toolsets")
    await register_tools(mcp, adapter, {})
    apply_tool_visibility(mcp, toolsets, mode)
    return mcp


async def _listed(mcp: Any) -> set[str]:
    async with Client(mcp) as client:
        return {t.name for t in await client.list_tools()}


@pytest.fixture(scope="module")
def families() -> dict[str, str]:
    """Every registered tool's family."""
    import asyncio

    async def collect() -> dict[str, str]:
        mcp = FastMCP("families")
        await register_tools(mcp, MockSolidWorksAdapter({}), {})
        return {t.name: tool_family(t.fn) for t in await mcp.list_tools()}

    return asyncio.run(collect())


def test_every_family_is_in_exactly_one_toolset(families: dict[str, str]) -> None:
    placed = [family for members in TOOLSETS.values() for family in members]

    assert sorted(placed) == sorted(set(families.values()))


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("all", ("all",)),
        (" Drawing , core ", ("core", "drawing")),
        ("core,all", ("all",)),
    ],
)
def test_parse_toolsets(text: str, parsed: tuple[str, ...]) -> None:
    assert parse_toolsets(text) == parsed


@pytest.mark.parametrize(
    ("text", "error"),
    [("core,drawng", "Unknown toolset(s) drawng"), (" , ", "toolsets is empty")],
)
def test_a_typo_or_nothing_is_refused(text: str, error: str) -> None:
    with pytest.raises(ValueError, match=re.escape(error)) as raised:
        parse_toolsets(text)

    assert "core, drawing, automation, vba, docs, all" in str(raised.value)


def test_families_for() -> None:
    assert families_for(("all",)) is None
    assert families_for(("vba", "docs")) == {"vba_generation", "docs_discovery"}


@pytest.mark.asyncio
async def test_the_toolsets_list_their_families_only(families: dict[str, str]) -> None:
    everything = await _listed(await _server())
    core = await _listed(await _server(("core",)))
    core_drawing = await _listed(await _server(("core", "drawing")))

    assert everything == set(families)
    assert core == {n for n, f in families.items() if f in TOOLSETS["core"]}
    assert core_drawing == {
        n for n, f in families.items() if f in TOOLSETS["core"] | TOOLSETS["drawing"]
    }


@pytest.mark.asyncio
async def test_search_mode_finds_and_calls_the_same_tools() -> None:
    mcp = await _server(("core",), "search")

    async with Client(mcp) as client:
        listed = {t.name for t in await client.list_tools()}
        found = await client.call_tool("search_tools", {"query": "fillet edges"})
        called = await client.call_tool(
            "call_tool",
            {"name": "create_part", "arguments": {"input_data": {"name": "Plate"}}},
        )
        hidden = await client.call_tool(
            "call_tool",
            {"name": "generate_vba_extrusion", "arguments": {}},
            raise_on_error=False,
        )

    assert listed == {*ALWAYS_VISIBLE, "search_tools", "call_tool"}
    assert json.loads(found.content[0].text)[0]["name"] == "add_fillet"
    assert called.structured_content["message"] == "Created new part: Plate"
    assert hidden.is_error


@pytest.mark.asyncio
async def test_search_mode_leaves_deprecated_tools_out() -> None:
    searched = await _server(("all",), "search")
    listed = await _server(("all",), "list")

    async with Client(searched) as client:
        found = await client.call_tool(
            "search_tools", {"query": "mass properties volume"}
        )
        old = await client.call_tool(
            "call_tool",
            {"name": "calculate_mass_properties", "arguments": {}},
            raise_on_error=False,
        )

    names = [t["name"] for t in json.loads(found.content[0].text)]
    assert "get_mass_properties" in names
    assert "calculate_mass_properties" not in names
    assert old.is_error
    assert "calculate_mass_properties" in await _listed(listed)


@pytest.mark.asyncio
async def test_core_descriptions_only_point_inside_core_or_say_where(
    families: dict[str, str],
) -> None:
    """With only core on, a pointer to a hidden tool names its toolset."""
    mcp = FastMCP("pointers")
    await register_tools(mcp, MockSolidWorksAdapter({}), {})
    stray = []
    for tool in await mcp.list_tools():
        if families[tool.name] not in TOOLSETS["core"]:
            continue
        text = tool.description or ""
        for name in re.findall(r"`([a-z_]+)`", text):
            outside = name in families and families[name] not in TOOLSETS["core"]
            if outside and "toolset" not in text:
                stray.append((tool.name, name))

    assert stray == []
