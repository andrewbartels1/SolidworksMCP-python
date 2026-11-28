"""The appearance tools on the mock adapter (queue item 36). Spec: tools/appearance."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.appearance import (
    AppearanceTargetInput,
    SetAppearanceInput,
    register_appearance_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("appearance")
    assert await register_appearance_tools(mcp, adapter, {}) == 2
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def block() -> MockSolidWorksAdapter:
    """A mock 40 x 40 x 10 block."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Top")
    await adapter.add_rectangle(-20, -20, 20, 20)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=10))
    return adapter


@pytest.mark.asyncio
async def test_colour_a_face_then_reset_it(block: MockSolidWorksAdapter) -> None:
    tools = await _tools(block)

    whole = await tools["set_appearance"]({"color": [200, 0, 0]})
    face = await tools["set_appearance"](
        SetAppearanceInput(face_point=[0, 0, 10], color="#1f77b4")
    )
    reset = await tools["set_appearance"]({"face_point": [0, 0, 10], "reset": True})

    assert whole["message"] == "Coloured: #c80000 on the part"
    assert face["message"] == "Coloured: #1f77b4 on face [0.0, 0.0, 10.0]"
    assert reset["message"] == "Removed the face's colour; #c80000 from the part shows"


@pytest.mark.asyncio
async def test_read_the_part_and_a_face(block: MockSolidWorksAdapter) -> None:
    tools = await _tools(block)

    part = await tools["get_appearance"]()
    face = await tools["get_appearance"](AppearanceTargetInput(face_point=[0, 0, 10]))

    assert part["message"] == "#e4e4e4 on the part, from the part"
    assert face["appearance"]["level"] == "part"


@pytest.mark.asyncio
async def test_two_targets_are_an_error_reply(block: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(block))["set_appearance"](
        {"feature": "A", "body": "B", "color": "#000000"}
    )

    assert reply["status"] == "error"
    assert reply["error_type"] == "invalid_input"


@pytest.mark.parametrize(
    "values",
    [
        {"color": "#000000", "transparency": 2},
        {"color": "#000000", "face_point": [1, 2]},
        {"feature": ""},
    ],
)
def test_inputs_are_strict(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SetAppearanceInput(**values)
