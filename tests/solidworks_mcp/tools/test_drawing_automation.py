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

#: Each tool with the smallest valid input and the adapter method it needs.
_TOOLS = {
    "insert_model_dimensions": ({}, "insert_model_dimensions"),
    "arrange_dimensions": ({}, "arrange_dimensions"),
    "insert_bom_table": ({"view_name": "Drawing View1"}, "insert_bom_table"),
    "set_sheet_scale": ({"numerator": 1, "denominator": 2}, "set_sheet_scale"),
    "generate_drawing_package": (
        {"model_path": "C:/parts/block.SLDPRT"},
        "create_standard_drawing",
    ),
}


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

    @pytest.mark.asyncio
    async def test_bom_and_sheet_scale(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)

        bom = await (await _tool(mcp_server, "insert_bom_table"))(
            input_data=InsertBomTableInput(
                view_name="Drawing View1", bom_type="indented"
            )
        )
        scale = await (await _tool(mcp_server, "set_sheet_scale"))(
            input_data=SetSheetScaleInput(numerator=1, denominator=2)
        )

        assert bom["message"] == (
            "Inserted a BOM for Drawing View1 (indented, 3 row(s) including the header)"
        )
        assert bom["data"]["template"] == "bom-standard.sldbomtbt"
        assert scale["message"] == "Sheet Sheet1 is now at 1:2"
        assert scale["data"]["scale"] == "1:2"

    @pytest.mark.asyncio
    async def test_generate_package_follows_the_standard(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        model = tmp_path / "Mounting Plate.SLDPRT"
        model.write_bytes(b"")

        result = await (await _tool(mcp_server, "generate_drawing_package"))(
            input_data=GenerateDrawingPackageInput(
                model_path=str(model),
                output_dir=str(tmp_path / "out"),
                title="Mounting Plate",
                drawing_number="MP-RevA-01",
                author="J. Smith",
                notes=["Laser cut from 10 mm plate"],
            )
        )

        data = result["data"]
        assert result["message"] == (
            f"Saved {data['drawing_path']} and its PDF at 1:1, with no overlaps"
        )
        assert data["drawing_path"].endswith("MP-RevA-01.SLDDRW")
        assert data["overlap_check"]["overlaps_after"] == 0
        captions = [v["caption"] for v in data["views"].values()]
        assert "FRONT ELEVATION" in captions
        assert all(":" not in c for c in captions)  # view names only, no scale


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
        (
            "insert_bom_table",
            {"view_name": "Drawing View1"},
            "create_part",
            "wrong_document_type",
        ),
        ("insert_bom_table", {}, "views", "invalid_input"),
        ("insert_bom_table", {"view_name": "V", "x_mm": 5.0}, "views", "invalid_input"),
        (
            "insert_bom_table",
            {"view_name": "V", "bom_type": "flat"},
            "views",
            "invalid_input",
        ),
        (
            "set_sheet_scale",
            {"numerator": 0, "denominator": 2},
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
            {"model_path": "C:/nope/missing.SLDPRT"},
            "views",
            "not_found",
        ),
        (
            "generate_drawing_package",
            {"model_path": "C:/parts/block.step"},
            "views",
            "invalid_input",
        ),
        ("generate_drawing_package", {}, "views", "invalid_input"),
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
async def test_a_package_with_overlaps_keeps_its_data(mcp_server, mock_config) -> None:
    check = {"overlaps_after": 2, "annotation_overlaps": []}

    async def create_standard_drawing(*_args):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Drawing saved but 2 overlap(s) remain - the no-overlap rule is not met",
            data={"drawing_path": "C:/out/B.SLDDRW", "overlap_check": check},
        )

    adapter = SimpleNamespace(create_standard_drawing=create_standard_drawing)
    await register_drawing_automation_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "generate_drawing_package"))(
        {"model_path": "C:/parts/b.SLDPRT"}
    )

    assert result["status"] == "error"
    assert result["message"].startswith("Failed to generate the drawing package: ")
    assert result["data"]["overlap_check"] == check


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
    payload, method = _TOOLS[tool]
    await register_drawing_automation_tools(mcp_server, object(), mock_config)

    result = await (await _tool(mcp_server, tool))(payload)

    assert result["error_type"] == "not_supported"
    assert f"does not support {method}" in result["message"]


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
