"""``sketch_convert_entities`` (spec: tools/sketch-convert-entities)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from solidworks_mcp.tools.sketching import (
    SketchConvertEntitiesInput,
    register_sketching_tools,
)


async def _tool(mcp_server: Any, adapter: Any, config: Any) -> Any:
    await register_sketching_tools(mcp_server, adapter, config)
    return next(
        t.fn
        for t in await mcp_server.list_tools()
        if t.name == "sketch_convert_entities"
    )


@pytest.mark.asyncio
async def test_a_face_outline_becomes_four_entities(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    await mock_adapter.create_part()
    await mock_adapter.create_sketch("Top")
    tool = await _tool(mcp_server, mock_adapter, mock_config)

    result = await tool(SketchConvertEntitiesInput(face_point=[0, 0, 20]))

    assert result["status"] == "success", result
    assert result["converted"]["count"] == 4
    assert result["message"] == "Copied 4 edge(s) into the sketch"


@pytest.mark.asyncio
async def test_no_open_sketch_is_an_error(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    tool = await _tool(mcp_server, mock_adapter, mock_config)

    result = await tool(SketchConvertEntitiesInput(edge_points=[[0, 0, 20]]))

    assert result["status"] == "error"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({}, "give edge_points or face_point"),
        ({"edge_points": [[0, 0]]}, r"each point must be \[x, y, z\]"),
        ({"face_point": [0, 0, 0, 0]}, r"each point must be \[x, y, z\]"),
    ],
)
def test_input_refuses_bad_points(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises((ValueError, ValidationError), match=match):
        SketchConvertEntitiesInput(**kwargs)
