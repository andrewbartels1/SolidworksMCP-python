"""The sheet-metal tools on the mock adapter (queue item 15).

Spec: tools/sheet-metal.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.mock_sheet_metal import bend_deduction
from solidworks_mcp.tools.modeling import (
    AddEdgeFlangeInput,
    CreateBaseFlangeInput,
    register_modeling_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("sheet-metal")
    await register_modeling_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part("Bracket")
    return adapter


def test_the_bend_deduction_matches_solidworks() -> None:
    """2 mm sheet, 2 mm radius, K 0.5: SolidWorks flattened 60 + 22 to 78.7124."""
    assert 60 + 22 - bend_deduction(2.0, 2.0, 0.5) == pytest.approx(78.7124, abs=1e-3)


@pytest.mark.asyncio
async def test_plate_flange_flat_and_folded(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    base = await tools["create_base_flange"](
        CreateBaseFlangeInput(thickness=2, bend_radius=2)
    )
    flange = await tools["add_edge_flange"](
        AddEdgeFlangeInput(edge_point=[0, 0, 30], length=20)
    )
    flat = await tools["set_flat_pattern"]({})
    folded = await tools["set_flat_pattern"]({"flat": False})

    assert base["message"] == "Made a 2 mm sheet-metal base flange from Sketch1"
    assert base["flange"]["k_factor"] == 0.5
    assert flange["message"] == "Added a 20 mm edge flange at 90° on the 100.0 mm edge"
    assert flat["bounding_box_mm"]["size"][2] == pytest.approx(78.7124, abs=1e-3)
    assert flat["message"].startswith("Flattened: the blank is")
    assert folded["message"] == "Folded: the part is [100.0, 22.0, 60.0] mm"


@pytest.mark.asyncio
async def test_a_sketched_bend_reports_its_box(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)
    await tools["create_base_flange"]({"thickness": 2, "bend_radius": 2})

    bend = await tools["create_sketched_bend"]()

    assert bend["message"] == "Bent the sheet 90° along Sketch2"
    assert bend["bend"]["bounding_box_mm"]["size"] == [50.0, 52.0, 60.0]


@pytest.mark.asyncio
async def test_refusals(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    not_sheet = [
        await tools["add_edge_flange"]({"edge_point": [0, 0, 30], "length": 20}),
        await tools["create_sketched_bend"]({}),
        await tools["set_flat_pattern"]({"flat": True}),
    ]
    await tools["create_base_flange"]({"thickness": 2, "bend_radius": 2})
    no_edge = await tools["add_edge_flange"]({"edge_point": [0, 0, 0], "length": 20})

    for result in not_sheet:
        assert "Start with create_base_flange" in result["message"], result
    assert "No sheet edge at [0.0, 0.0, 0.0] mm" in no_edge["message"]


@pytest.mark.asyncio
async def test_no_document_and_a_drawing() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    tools = await _tools(adapter)

    empty = await tools["set_flat_pattern"]({})
    await adapter.create_drawing()
    drawing = await tools["create_base_flange"]({"thickness": 2, "bend_radius": 2})

    assert empty["error_type"] == "no_active_document"
    assert drawing["error_type"] == "wrong_document_type"


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"thickness": 0, "bend_radius": 2}, "thickness"),
        ({"thickness": 2, "bend_radius": 2, "k_factor": 1.2}, "k_factor"),
    ],
)
def test_base_flange_inputs(data: dict[str, Any], field: str) -> None:
    with pytest.raises(ValueError, match=field):
        CreateBaseFlangeInput(**data)


def test_an_edge_point_has_three_coordinates() -> None:
    with pytest.raises(ValueError, match="edge_point"):
        AddEdgeFlangeInput(edge_point=[0, 0], length=20)
