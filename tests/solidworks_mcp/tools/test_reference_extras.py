"""The reference and analysis extras on the mock adapter (queue item 39).

Spec: tools/reference-extras.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.reference_extras import (
    BoundingBoxInput,
    CoordinateSystemInput,
    SectionPropertiesInput,
    register_reference_extras_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("reference")
    assert await register_reference_extras_tools(mcp, adapter, {}) == 4
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def block() -> MockSolidWorksAdapter:
    """A mock 40 x 40 x 10 block, its box from z 0 to 10."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Top")
    await adapter.add_rectangle(-20, -20, 20, 20)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=10))
    return adapter


@pytest.mark.asyncio
async def test_each_extra_on_a_block(block: MockSolidWorksAdapter) -> None:
    tools = await _tools(block)

    frame = await tools["create_coordinate_system"](
        CoordinateSystemInput(origin=[20, 10, 20])
    )
    com = await tools["create_center_of_mass_point"]()
    box = await tools["create_bounding_box"](BoundingBoxInput())
    default_box = await tools["create_bounding_box"]()
    section = await tools["get_section_properties"](
        SectionPropertiesInput(face_point=[0, 0, 10])
    )

    assert frame["message"] == "Coordinate System1 at (20, 10, 20) mm"
    assert com["message"] == "Center of Mass at (0, 0, 5) mm"
    assert box["message"] == "Bounding Box: 40 x 40 x 10 mm"
    assert default_box["error_type"] == "invalid_input"
    assert section["message"] == "Area 1,600.00 mm², centroid (0, 0, 10) mm"


@pytest.mark.asyncio
async def test_a_point_on_no_face_is_an_error_reply(
    block: MockSolidWorksAdapter,
) -> None:
    reply = await (await _tools(block))["get_section_properties"](
        {"face_point": [0, 0, 5]}
    )

    assert reply["status"] == "error"
    assert reply["error_type"] == "invalid_input"


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (CoordinateSystemInput, {"origin": [1, 2]}),
        (SectionPropertiesInput, {"face_point": [1, 2, 3, 4]}),
    ],
)
def test_inputs_are_strict(model: type, values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model(**values)
