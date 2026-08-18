"""Tests for the CAD-generation skill-router tool (issue #42)."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import SolidWorksAdapter
from solidworks_mcp.tools.skill_router import (
    SkillRouteInput,
    filter_to_adapter_capabilities,
    register_skill_router_tools,
)


async def _find_tool(mcp_server, name: str):
    for tool in await mcp_server.list_tools():
        if tool.name == name:
            return tool.fn
    raise AssertionError(f"tool '{name}' not registered")


# ---------------------------------------------------------------------------
# Adapter-capability validation
# ---------------------------------------------------------------------------


def test_filter_to_adapter_capabilities_passes_through_real_method() -> None:
    """A real SolidWorksAdapter method name passes through unchanged."""
    assert filter_to_adapter_capabilities(["list_features"]) == ["list_features"]


def test_filter_to_adapter_capabilities_excludes_made_up_name() -> None:
    """A made-up tool name is silently excluded, never raises."""
    assert filter_to_adapter_capabilities(["definitely_not_a_real_tool"]) == []


def test_filter_to_adapter_capabilities_mixed_list() -> None:
    """Mixed real/fake names: only the real ones survive, order preserved."""
    result = filter_to_adapter_capabilities(
        ["create_extrusion", "not_real", "get_mass_properties"]
    )
    assert result == ["create_extrusion", "get_mass_properties"]


# ---------------------------------------------------------------------------
# Tool registration + invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_skill_router_tools(mcp_server, mock_adapter, mock_config):
    """Registers exactly one tool."""
    tool_count = await register_skill_router_tools(mcp_server, mock_adapter, mock_config)
    assert tool_count == 1

    tool_names = {tool.name for tool in await mcp_server.list_tools()}
    assert "get_skill_route" in tool_names


@pytest.mark.asyncio
async def test_get_skill_route_solidworks_native(mcp_server, mock_adapter, mock_config):
    """solidworks-native returns the full adapter capability set, no fallback."""
    await register_skill_router_tools(mcp_server, mock_adapter, mock_config)
    tool_func = await _find_tool(mcp_server, "get_skill_route")

    result = await tool_func(input_data=SkillRouteInput(family="solidworks-native"))

    assert result["status"] == "success"
    data = result["data"]
    assert data["family"] == "solidworks-native"
    assert data["fallback"] is None
    assert "list_features" in data["allowed_tools"]
    assert "create_extrusion" in data["allowed_tools"]
    assert data["validation_steps"]
    assert data["expected_outputs"]

    # No internal LLM call and no invented capability: every returned name
    # is a real, live SolidWorksAdapter method.
    expected = sorted(
        name
        for name in dir(SolidWorksAdapter)
        if not name.startswith("_") and callable(getattr(SolidWorksAdapter, name))
    )
    assert data["allowed_tools"] == expected


@pytest.mark.asyncio
async def test_get_skill_route_text_to_cad_stub(mcp_server, mock_adapter, mock_config):
    """text-to-cad returns a clearly-flagged stub route referencing issue #43."""
    await register_skill_router_tools(mcp_server, mock_adapter, mock_config)
    tool_func = await _find_tool(mcp_server, "get_skill_route")

    result = await tool_func(input_data=SkillRouteInput(family="text-to-cad"))

    assert result["status"] == "success"
    data = result["data"]
    assert data["family"] == "text-to-cad"
    assert data["allowed_tools"] == []
    assert data["fallback"] is not None
    assert "#43" in data["fallback"]


@pytest.mark.asyncio
async def test_get_skill_route_mesh_concept_stub(mcp_server, mock_adapter, mock_config):
    """mesh-concept returns a clearly-flagged stub route."""
    await register_skill_router_tools(mcp_server, mock_adapter, mock_config)
    tool_func = await _find_tool(mcp_server, "get_skill_route")

    result = await tool_func(input_data=SkillRouteInput(family="mesh-concept"))

    assert result["status"] == "success"
    data = result["data"]
    assert data["family"] == "mesh-concept"
    assert data["allowed_tools"] == []
    assert data["fallback"] is not None
