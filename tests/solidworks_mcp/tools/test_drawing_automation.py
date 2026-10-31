"""Tests for the drawing-automation tools (``tools/drawing_automation.py``).

Every tool has a success case against the mock adapter, its failures with an
actionable ``error_type``, and the missing-capability refusal.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.tools.drawing_automation import (
    ArrangeDimensionsInput,
    GenerateDrawingPackageInput,
    InsertBomTableInput,
    InsertModelDimensionsInput,
    SetSheetScaleInput,
    register_drawing_automation_tools,
)

_TOOLS = (
    "insert_model_dimensions",
    "arrange_dimensions",
    "insert_bom_table",
    "set_sheet_scale",
    "generate_drawing_package",
    "add_gtol",
    "add_datum_tag",
)


async def _tool(mcp_server: Any, name: str) -> Any:
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


async def _drawing_with_views(mock_adapter: Any, tmp_path: Path) -> None:
    model = tmp_path / "bracket.SLDPRT"
    model.write_bytes(b"")
    await mock_adapter.create_drawing()
    await mock_adapter.create_technical_drawing({"model_path": str(model)})


class TestDrawingAutomationTools:
    """Tools exercised end to end against the mock adapter."""

    @pytest.mark.asyncio
    async def test_register_count(self, mcp_server, mock_adapter, mock_config) -> None:
        count = await register_drawing_automation_tools(
            mcp_server, mock_adapter, mock_config
        )
        names = {t.name for t in await mcp_server.list_tools()}
        assert count == len(names) == len(_TOOLS)
        assert names == set(_TOOLS)

    @pytest.mark.asyncio
    async def test_insert_then_arrange(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)

        dims = await (await _tool(mcp_server, "insert_model_dimensions"))(
            input_data=InsertModelDimensionsInput()
        )
        views = len(dims["data"]["views"])
        assert dims["status"] == "success"
        assert dims["message"] == (
            f"Added {3 * views} dimension(s) to {views} view(s) "
            "(insert_model_annotations)"
        )
        again = await (await _tool(mcp_server, "insert_model_dimensions"))({})
        assert again["data"]["dimensions_added"] == 0  # no duplicates on a re-run

        arranged = await (await _tool(mcp_server, "arrange_dimensions"))(
            input_data=ArrangeDimensionsInput()
        )
        assert arranged["status"] == "success"
        assert arranged["message"] == (
            f"Arranged {3 * views} dimension(s): {3 * views} overlap(s) before, 0 after"
        )


class TestGdtTools:
    """Feature control frames and datum tags against the mock adapter."""

    @pytest.mark.asyncio
    async def test_frame_and_datum_tags(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)

        frame = await (await _tool(mcp_server, "add_gtol"))(
            {
                "characteristic": "position",
                "tolerance": 0.2,
                "diameter_zone": True,
                "material_condition": "mmc",
                "datums": ["A", "B", "C"],
                "x_mm": 60,
                "y_mm": 250,
                "attach_x_mm": 62,
                "attach_y_mm": 218,
            }
        )
        flat = await (await _tool(mcp_server, "add_gtol"))(
            {"characteristic": "flatness", "tolerance": 0.05, "x_mm": 1, "y_mm": 2}
        )
        half = await (await _tool(mcp_server, "add_gtol"))(
            {
                "characteristic": "flatness",
                "tolerance": 0.05,
                "x_mm": 1,
                "y_mm": 2,
                "attach_x_mm": 5,
            }
        )
        tag = await (await _tool(mcp_server, "add_datum_tag"))(
            {"label": "a", "attach_x_mm": 1, "attach_y_mm": 2, "x_mm": 3, "y_mm": 4}
        )
        on_dimension = await (await _tool(mcp_server, "add_gtol"))(
            {
                "characteristic": "position",
                "tolerance": 0.2,
                "datums": ["A"],
                "dimension_view": "Drawing View2",
                "dimension_name": "D3@Sketch1",
            }
        )
        view_only = await (await _tool(mcp_server, "add_gtol"))(
            {
                "characteristic": "position",
                "tolerance": 0.2,
                "dimension_view": "Drawing View2",
            }
        )

        assert on_dimension["data"]["attached"] == "D3@Sketch1"
        assert on_dimension["data"]["position_mm"] is None
        assert view_only["data"]["attached"] is False  # a view alone is no dimension
        assert frame["message"] == "Added a position frame (0.2 to A|B|C)"
        assert frame["data"]["attached"] is True
        assert flat["message"] == "Added a flatness frame (0.05)"
        assert half["data"]["attached"] is False  # one coordinate is no point
        assert tag["message"] == "Added datum A"

    @pytest.mark.asyncio
    async def test_bad_inputs_are_invalid_input(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)

        frame = await (await _tool(mcp_server, "add_gtol"))(
            {"characteristic": "wobble", "tolerance": 0.2, "x_mm": 0, "y_mm": 0}
        )
        tag = await (await _tool(mcp_server, "add_datum_tag"))(
            {"label": "AB", "attach_x_mm": 0, "attach_y_mm": 0, "x_mm": 0, "y_mm": 0}
        )

        assert frame["error_type"] == "invalid_input"
        assert tag["error_type"] == "invalid_input"


class TestDrawingPackageTools:
    """BOM, sheet scale and the A3 package against the mock adapter."""

    @pytest.mark.asyncio
    async def test_bom_and_scale(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)
        view = mock_adapter._drawing_views[0]

        bom = await (await _tool(mcp_server, "insert_bom_table"))(
            input_data=InsertBomTableInput(view_name=view, bom_type="parts_only")
        )
        scale = await (await _tool(mcp_server, "set_sheet_scale"))(
            input_data=SetSheetScaleInput(numerator=1, denominator=2)
        )

        assert bom["status"] == "success"
        assert bom["message"] == f"Inserted a parts_only BOM on {view}"
        assert bom["data"]["row_count"] == 2
        assert scale["message"] == "Sheet scale set to 1:2"
        assert scale["data"] == {"sheet": "Sheet1", "scale": "1:2", "requested": "1:2"}

    @pytest.mark.asyncio
    async def test_generate_drawing_package(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        model = tmp_path / "block.SLDPRT"
        model.write_bytes(b"")

        result = await (await _tool(mcp_server, "generate_drawing_package"))(
            input_data=GenerateDrawingPackageInput(
                model_path=str(model), drawing_number="BLK-01"
            )
        )

        drawing = str(tmp_path / "BLK-01.SLDDRW")
        pdf = str(tmp_path / "BLK-01.pdf")
        assert result["status"] == "success"
        assert result["message"] == f"Created {drawing} at 1:1 with PDF {pdf}"
        assert result["data"]["overlap_check"]["overlaps_after"] == 0

    @pytest.mark.asyncio
    async def test_remaining_overlaps_fail_the_package_with_data(
        self, mcp_server, mock_config
    ) -> None:
        async def create_standard_drawing(*_args):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="Drawing saved but 1 overlap(s) remain",
                data={"overlap_check": {"overlaps_after": 1}},
            )

        adapter = SimpleNamespace(create_standard_drawing=create_standard_drawing)
        await register_drawing_automation_tools(mcp_server, adapter, mock_config)

        result = await (await _tool(mcp_server, "generate_drawing_package"))(
            {"model_path": "C:/parts/block.SLDPRT"}
        )

        assert result["status"] == "error"
        assert result["message"].startswith("Failed to create the standard drawing")
        assert result["data"]["overlap_check"]["overlaps_after"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "setup", "error_type"),
    [
        ("insert_model_dimensions", {}, "create_part", "wrong_document_type"),
        ("insert_model_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("insert_model_dimensions", {}, "create_drawing", "not_found"),
        ("arrange_dimensions", {}, "create_assembly", "wrong_document_type"),
        ("arrange_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("arrange_dimensions", {"view_name": 7}, "views", "invalid_input"),
        ("insert_bom_table", {"view_name": "Side"}, "views", "not_found"),
        ("insert_bom_table", {"view_name": "V1"}, "create_part", "wrong_document_type"),
        ("insert_bom_table", {}, "views", "invalid_input"),
        (
            "set_sheet_scale",
            {"numerator": 0, "denominator": 2},
            "views",
            "invalid_input",
        ),
        (
            "set_sheet_scale",
            {"numerator": -1, "denominator": 2},
            "views",
            "invalid_input",
        ),
        (
            "set_sheet_scale",
            {"numerator": 1, "denominator": 2},
            "create_part",
            "wrong_document_type",
        ),
        (
            "generate_drawing_package",
            {"model_path": "C:/no/such/part.SLDPRT"},
            "views",
            "not_found",
        ),
        (
            "generate_drawing_package",
            {"model_path": "C:/parts/drawing.SLDDRW"},
            "views",
            "invalid_input",
        ),
        (
            "generate_drawing_package",
            {"model_path": "C:/parts/b.SLDPRT", "title_block_text_height_mm": 0},
            "views",
            "invalid_input",
        ),
    ],
)
async def test_failures_carry_an_actionable_error_type(
    mcp_server, mock_adapter, mock_config, tmp_path, tool, payload, setup, error_type
) -> None:
    await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
    if setup == "views":
        await _drawing_with_views(mock_adapter, tmp_path)
    else:
        await getattr(mock_adapter, setup)()

    result = await (await _tool(mcp_server, tool))(payload)

    assert result["status"] == "error"
    assert result["error_type"] == error_type, result
    assert result["hint"]
    assert isinstance(result["execution_time"], float)


@pytest.mark.asyncio
async def test_remaining_overlaps_come_back_with_the_error(
    mcp_server, mock_config
) -> None:
    overlaps = [{"dimension": "Front#0", "conflicts_with": "Front", "kind": "x"}]

    async def arrange_dimensions(_view):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="1 dimension overlap(s) remain after arranging 2 dimension(s)",
            data={"overlaps_after": 1, "remaining_overlaps": overlaps},
        )

    adapter = SimpleNamespace(arrange_dimensions=arrange_dimensions)
    await register_drawing_automation_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "arrange_dimensions"))({})

    assert result["status"] == "error"
    assert result["message"].startswith("Failed to arrange dimensions: 1 dimension")
    assert result["data"]["remaining_overlaps"] == overlaps


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_missing_adapter_method_is_reported(
    mcp_server, mock_config, tool
) -> None:
    await register_drawing_automation_tools(mcp_server, object(), mock_config)

    result = await (await _tool(mcp_server, tool))({})

    assert result["error_type"] == "not_supported"
    assert f"does not support {tool}" in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_docstrings_follow_the_tool_standard(
    mcp_server, mock_adapter, mock_config, tool
) -> None:
    """Every tool documents Args, Returns and an Example, as the others do."""
    await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
    doc = (await _tool(mcp_server, tool)).__doc__ or ""
    for section in ("Args:", "Returns:", "Example:"):
        assert section in doc, (tool, section)
