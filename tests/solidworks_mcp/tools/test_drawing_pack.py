"""The drawing pack's tools on the mock adapter (queue item 12).

Spec: tools/drawing-section-detail, drawing-title-block, drawing-dimensions,
drawing-check.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.drawing import (
    AddDimensionInput,
    AutoDimensionViewInput,
    CreateDetailViewInput,
    CreateSectionViewInput,
    UpdateSheetFormatInput,
    UpdateTitleBlockInput,
    register_drawing_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("drawing-pack")
    await register_drawing_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def drawing() -> MockSolidWorksAdapter:
    """A mock drawing with a front view at (20, 150)-(120, 230) mm."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()
    adapter._drawing_views.append("Drawing View1")
    return adapter


@pytest.mark.asyncio
async def test_a_section_then_a_detail(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    section = await tools["create_section_view"](
        CreateSectionViewInput(
            view="Drawing View1",
            line_start=[10, 190],
            line_end=[130, 190],
            position=[250, 190],
        )
    )
    detail = await tools["create_detail_view"](
        CreateDetailViewInput(
            view="Drawing View1",
            center=[25, 155],
            radius=8,
            position=[300, 80],
            scale="3:1",
        )
    )

    assert section["message"] == "Added section view A of Drawing View1"
    assert section["view"]["name"] == "Section View A-A"
    assert detail["message"] == "Added detail view B of Drawing View1 at 3:1"
    assert drawing._drawing_views[-1] == "Detail View B (3:1)"


@pytest.mark.asyncio
async def test_view_refusals_are_invalid_input(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    off_sheet = await tools["create_section_view"](
        CreateSectionViewInput(
            view="Drawing View1",
            line_start=[10, 190],
            line_end=[130, 190],
            position=[500, 190],
        )
    )
    unknown = await tools["create_detail_view"](
        CreateDetailViewInput(
            view="Top", center=[25, 155], radius=8, position=[300, 80]
        )
    )
    off_detail = await tools["create_detail_view"](
        CreateDetailViewInput(
            view="Drawing View1", center=[25, 155], radius=8, position=[300, 900]
        )
    )

    assert (off_sheet["error_type"], off_detail["error_type"]) == (
        "invalid_input",
        "invalid_input",
    )
    assert unknown["error_type"] == "not_found"
    assert "it has Drawing View1" in unknown["message"]


def test_a_detail_scale_must_be_a_ratio() -> None:
    with pytest.raises(ValueError, match="must look like '2:1'"):
        CreateDetailViewInput(
            view="V", center=[0, 0], radius=1, position=[0, 0], scale="2"
        )


@pytest.mark.asyncio
async def test_dimensions_by_hand_and_auto(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    width = await tools["add_dimension"](
        AddDimensionInput(
            dimension_type="horizontal",
            entity1_point=[20, 160],
            entity2_point=[80, 160],
            position=[50, 240],
        )
    )
    hole = await tools["add_dimension"](
        {
            "dimension_type": "diameter",
            "entity1_point": [60, 190],
            "position": [70, 245],
        }
    )
    nothing = await tools["add_dimension"](
        AddDimensionInput(
            dimension_type="vertical", entity1_point=[5, 5], position=[50, 240]
        )
    )
    auto = await tools["auto_dimension_view"](
        AutoDimensionViewInput(view="Drawing View1")
    )

    assert width["message"] == "Added a horizontal dimension: 60 mm"
    assert hole["dimension"]["value"] == 6.0
    assert nothing["error_type"] == "invalid_input"
    assert auto["message"] == "Added 2 dimension(s) to Drawing View1"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (
            {"dimension_type": "angular", "entity1_point": [1, 1], "position": [2, 2]},
            "an angular dimension needs entity2_point",
        ),
        (
            {
                "dimension_type": "radial",
                "entity1_point": [1, 1],
                "entity2_point": [3, 3],
                "position": [2, 2],
            },
            "a radial dimension takes one circle",
        ),
        (
            {
                "dimension_type": "aligned",
                "entity1_point": [1, 1],
                "entity2_point": [3],
                "position": [2, 2],
            },
            "entity2_point is",
        ),
    ],
)
def test_the_entity_rules(data: dict[str, Any], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        AddDimensionInput(**data)


@pytest.mark.asyncio
async def test_format_and_title_block(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    a2 = await tools["update_sheet_format"](
        UpdateSheetFormatInput(sheet_format="a2 - iso")
    )
    missing = await tools["update_sheet_format"](
        {"sheet_format": "b9 - odd", "paper_size": "a3"}
    )
    no_size = await tools["update_sheet_format"]({"sheet_format": "custom"})
    title = await tools["update_title_block"](
        UpdateTitleBlockInput(revision="B", drawn_by="AB")
    )
    checked = await tools["check_drawing"]()

    assert a2["message"] == "Sheet is now A2 (a2 - iso)"
    assert a2["sheet"]["sheet_mm"] == (0.0, 0.0, 594.0, 420.0)
    assert (missing["error_type"], no_size["error_type"]) == (
        "invalid_input",
        "invalid_input",
    )
    assert title["message"] == "Title block: drawn_by = AB, revision = B"
    assert title["fields"]["revision"]["property"] == "Revision"
    assert checked["message"] == "The drawing passed, 2 warning(s)"
    assert [f["rule"] for f in checked["findings"]] == [
        "view_not_dimensioned",
        "title_block_field_empty",
    ]


def test_a_title_block_update_needs_a_field() -> None:
    with pytest.raises(ValueError, match="give at least one of title"):
        UpdateTitleBlockInput()


@pytest.mark.asyncio
async def test_on_a_part_every_tool_says_to_open_a_drawing() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    tools = await _tools(adapter)

    calls = [
        tools["check_drawing"](),
        tools["auto_dimension_view"]({"view": "V"}),
        tools["update_title_block"]({"revision": "B"}),
        tools["update_sheet_format"]({"sheet_format": "a3 - iso"}),
        tools["add_dimension"](
            {"dimension_type": "diameter", "entity1_point": [1, 1], "position": [2, 2]}
        ),
    ]
    for call in calls:
        result = await call
        assert result["error_type"] == "wrong_document_type", result


@pytest.mark.asyncio
async def test_an_adapter_without_the_pack_refuses() -> None:
    tools = await _tools(object())

    result = await tools["check_drawing"]()

    assert result["error_type"] == "not_supported"


@pytest.mark.asyncio
async def test_a_section_of_an_unknown_view(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    result = await tools["create_section_view"](
        {"view": "Top", "line_start": [0, 0], "line_end": [1, 1], "position": [5, 5]}
    )

    assert result["error_type"] == "not_found"
