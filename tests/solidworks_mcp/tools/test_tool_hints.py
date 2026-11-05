"""Tests for the tool hints table (spec: tools/tool-descriptions)."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from solidworks_mcp.tools import register_tools
from solidworks_mcp.tools.tool_hints import TOOL_HINTS, ToolHints


async def _registered(mock_adapter) -> dict[str, object]:
    mcp = FastMCP("all-tools")
    await register_tools(mcp, mock_adapter, {})
    return {tool.name: tool for tool in await mcp.list_tools()}


@pytest.mark.asyncio
async def test_the_table_matches_the_registered_tools_exactly(mock_adapter) -> None:
    tools = await _registered(mock_adapter)

    assert sorted(set(TOOL_HINTS) - set(tools)) == []
    assert sorted(set(tools) - set(TOOL_HINTS)) == []


@pytest.mark.asyncio
async def test_every_tool_carries_its_hints_and_family(mock_adapter) -> None:
    tools = await _registered(mock_adapter)

    for name, tool in tools.items():
        hints = TOOL_HINTS[name]
        assert tool.title == hints.title, name
        assert tool.annotations == hints.annotations(), name
        assert tool.tags == {tool.fn.__module__.rsplit(".", 1)[-1]}, name


@pytest.mark.asyncio
async def test_spot_checks(mock_adapter) -> None:
    tools = await _registered(mock_adapter)

    assert tools["list_features"].annotations.readOnlyHint is True
    assert tools["delete_feature"].annotations.destructiveHint is True
    assert tools["create_extrusion"].annotations.readOnlyHint is False
    assert tools["create_extrusion"].tags == {"modeling"}
    assert tools["save_file"].annotations.destructiveHint is True


@pytest.mark.parametrize(("destructive", "idempotent"), [(True, True), (False, False)])
def test_a_read_only_tool_must_be_harmless_and_idempotent(
    destructive: bool, idempotent: bool
) -> None:
    with pytest.raises(ValueError, match="never destructive"):
        ToolHints("X", read_only=True, destructive=destructive, idempotent=idempotent)


def test_annotations_carry_the_title_and_hints() -> None:
    annotations = ToolHints(
        "Delete", read_only=False, destructive=True, idempotent=False
    ).annotations()

    assert annotations.title == "Delete"
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is True
    assert annotations.idempotentHint is False
