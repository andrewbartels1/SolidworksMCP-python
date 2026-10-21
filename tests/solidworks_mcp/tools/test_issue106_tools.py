"""MCP tool tests for list_drawing_views / rebuild_model / select_feature /
select_face_edges (#106), through the server's real adapter wiring (mock).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
)
from solidworks_mcp.tools.drawing import register_drawing_tools
from solidworks_mcp.tools.modeling import (
    SelectFaceEdgesInput,
    SelectFeatureInput,
    register_modeling_tools,
)


async def _tool(mcp_server, name: str):  # noqa: ANN001, ANN202
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


async def _box(adapter: Any) -> None:
    await adapter.create_part()
    await adapter.create_sketch("Front")
    await adapter.add_rectangle(0, 0, 40, 25)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=10))


# ---- input schemas ----------------------------------------------------------


def test_select_feature_input_strips_and_rejects_blank() -> None:
    """feature_name is stripped; blank is refused before any adapter call."""
    assert SelectFeatureInput(feature_name="  Sketch1 ").feature_name == "Sketch1"
    with pytest.raises(ValueError, match="feature_name is required"):
        SelectFeatureInput(feature_name="   ")


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({}, "exactly one"),
        ({"side": "top", "point": [0, 0, 0]}, "exactly one"),
        ({"side": "upward"}, "Unknown side"),
        ({"side": "top", "edge_type": "spline"}, "edge_type"),
    ],
)
def test_select_face_edges_input_validation(kwargs: dict, fragment: str) -> None:
    """The schema enforces exactly-one identifier and known tokens."""
    with pytest.raises(ValueError, match=fragment):
        SelectFaceEdgesInput(**kwargs)


def test_select_face_edges_input_normalises_edge_type() -> None:
    """edge_type is case-insensitive."""
    assert (
        SelectFaceEdgesInput(side="top", edge_type="Circular").edge_type == "circular"
    )


# ---- select_feature -----------------------------------------------------


@pytest.mark.asyncio
async def test_select_feature_tool_success_and_unknown(
    mcp_server, mock_adapter, mock_config
) -> None:
    """Known name -> success with count; unknown -> error naming it."""
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    await _box(mock_adapter)
    select = await _tool(mcp_server, "select_feature")

    ok = await select({"feature_name": "Sketch1"})
    assert ok["status"] == "success"
    assert ok["data"]["selection_count"] == 1
    assert "Selected Sketch1" in ok["message"]

    appended = await select({"feature_name": "Front Plane", "append": True})
    assert appended["data"]["selection_count"] == 2

    missing = await select({"feature_name": "NoSuchFeature"})
    assert missing["status"] == "error"
    assert "NoSuchFeature" in missing["message"]
    assert "execution_time" in missing  # review #10: stable payload shape

    blank = await select({"feature_name": " "})
    assert blank["status"] == "error" and blank["message"].startswith("Invalid input")


# ---- select_face_edges -------------------------------------------------------


@pytest.mark.asyncio
async def test_select_face_edges_tool_paths(
    mcp_server, mock_adapter, mock_config
) -> None:
    """Side selection succeeds; impossible filters and bad input are errors."""
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    await _box(mock_adapter)
    tool = await _tool(mcp_server, "select_face_edges")

    ok = await tool({"side": "top"})
    assert ok["status"] == "success"
    assert ok["data"]["selected_edges"] == 4
    assert "4 edge(s) (linear)" in ok["message"]

    none = await tool({"side": "top", "edge_type": "circular"})
    assert none["status"] == "error" and "no circular edges" in none["message"]

    bad = await tool({"side": "top", "plane": "Front Plane"})
    assert bad["status"] == "error" and bad["message"].startswith("Invalid input")


@pytest.mark.asyncio
async def test_select_face_edges_then_chamfer_uses_live_selection(
    mcp_server, mock_adapter, mock_config
) -> None:
    """The documented chain: select edges, then add_chamfer with no edge names."""
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    await _box(mock_adapter)
    selected = await (await _tool(mcp_server, "select_face_edges"))({"side": "+Z"})
    assert selected["status"] == "success"
    chamfer = await (await _tool(mcp_server, "add_chamfer"))(
        {"distance": 0.5, "edge_names": []}
    )
    assert chamfer["status"] == "success"


# ---- rebuild_model ----------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_model_tool_clean(mcp_server, mock_adapter, mock_config) -> None:
    """A clean rebuild succeeds with no errors and works with no input."""
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    await _box(mock_adapter)
    rebuild = await _tool(mcp_server, "rebuild_model")
    result = await rebuild()
    assert result["status"] == "success"
    assert result["data"]["error_count"] == 0
    assert result["message"] == "Rebuilt cleanly; no rebuild errors."


@pytest.mark.asyncio
async def test_rebuild_model_tool_error_passes_data_through(
    mcp_server, mock_adapter, mock_config
) -> None:
    """An ERROR result still hands the per-feature diagnostics to the caller."""
    data = {
        "rebuilt": True,
        "top_level_only": False,
        "errors": [{"feature": "Fillet1", "severity": "error", "hint": "Reduce it"}],
        "error_count": 1,
        "warning_count": 0,
        "summary": "Rebuild left 1 feature error(s): Fillet1.",
    }
    mock_adapter.rebuild_model = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.ERROR, data=data, error=data["summary"]
        )
    )
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    result = await (await _tool(mcp_server, "rebuild_model"))({"top_level_only": True})
    assert result["status"] == "error"
    assert result["message"] == data["summary"]
    assert result["data"]["errors"][0]["hint"] == "Reduce it"
    mock_adapter.rebuild_model.assert_awaited_once_with(True)


@pytest.mark.asyncio
async def test_rebuild_model_tool_no_model(
    mcp_server, mock_adapter, mock_config
) -> None:
    """No active model -> error without data."""
    await register_modeling_tools(mcp_server, mock_adapter, mock_config)
    result = await (await _tool(mcp_server, "rebuild_model"))({})
    assert result["status"] == "error"
    assert "No active model" in result["message"]
    assert "data" not in result


# ---- list_drawing_views -------------------------------------------------------


@pytest.mark.asyncio
async def test_list_drawing_views_tool(mcp_server, mock_adapter, mock_config) -> None:
    """Views are listed with a count; adapter errors are reported."""
    await register_drawing_tools(mcp_server, mock_adapter, mock_config)
    tool = await _tool(mcp_server, "list_drawing_views")

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=["Drawing View1", "Drawing View2"]
        )
    )
    ok = await tool()
    assert ok["status"] == "success"
    assert ok["count"] == 2 and ok["views"] == ["Drawing View1", "Drawing View2"]

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data=[])
    )
    assert (await tool())["message"] == "The drawing has no views"

    mock_adapter.list_drawing_views = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="This operation requires a drawing document",
        )
    )
    err = await tool()
    assert err["status"] == "error" and "drawing document" in err["message"]

    mock_adapter.list_drawing_views = AsyncMock(side_effect=RuntimeError("boom"))
    crashed = await tool()
    assert crashed["error_type"] == "internal"
    assert crashed["message"] == "list_drawing_views failed: RuntimeError: boom"


# ---- local-LLM prompt catalog -------------------------------------------------


@pytest.mark.asyncio
async def test_llm_prompt_tool_catalog_only_names_registered_tools(
    mcp_server, mock_adapter
) -> None:
    """Every tool the local-LLM system prompt advertises must really exist (#106)."""
    import re
    from pathlib import Path

    import solidworks_mcp.ui.services.llm_service as llm_service
    from solidworks_mcp.tools import register_tools

    await register_tools(mcp_server, mock_adapter, None)
    registered = {t.name for t in await mcp_server.list_tools()}

    source = Path(llm_service.__file__).read_text(encoding="utf-8")
    block = source[source.index("mcp_tool_catalog = (") :]
    block = block[block.index("rationale fields:") : block.index("Prefer tools")]
    advertised = re.findall(r"\b([a-z][a-z0-9_]+)(?:\([^)]*\))?(?=,|\n)", block)
    assert advertised, "catalog parse found no tool names"
    assert sorted(set(advertised) - registered) == []
