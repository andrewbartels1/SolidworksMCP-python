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
    InsertModelDimensionsInput,
    register_drawing_automation_tools,
)

_TOOLS = ("insert_model_dimensions", "arrange_dimensions")
_REGISTERED = (*_TOOLS, "insert_bom_table", "set_sheet_scale", "generate_drawing_package")


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
        assert count == len(names) == len(_REGISTERED)
        assert names == set(_REGISTERED)

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
@pytest.mark.parametrize(
    ("tool", "payload", "setup", "error_type"),
    [
        ("insert_model_dimensions", {}, "create_part", "wrong_document_type"),
        ("insert_model_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("insert_model_dimensions", {}, "create_drawing", "not_found"),
        ("arrange_dimensions", {}, "create_assembly", "wrong_document_type"),
        ("arrange_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("arrange_dimensions", {"view_name": 7}, "views", "invalid_input"),
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


# --- slice C tests from #117 ---

from solidworks_mcp.tools.drawing_automation import (
    ArrangeDimensionsInput,
    GenerateDrawingPackageInput,
    InsertBomTableInput,
    InsertModelDimensionsInput,
    SetSheetScaleInput,
    register_drawing_automation_tools,
)

async def _tool(mcp_server: Any, name: str) -> Any:
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


class TestDrawingPackageTools:
    @pytest.mark.asyncio
    async def test_dimensions_arrange_bom_and_scale(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        model = tmp_path / "bracket.SLDPRT"
        model.write_bytes(b"")
        await mock_adapter.create_drawing()
        await mock_adapter.create_technical_drawing({"model_path": str(model)})

        dims = await (await _tool(mcp_server, "insert_model_dimensions"))(
            input_data=InsertModelDimensionsInput()
        )
        assert dims["status"] == "success"
        assert dims["data"]["dimensions_added"] > 0
        again = await (await _tool(mcp_server, "insert_model_dimensions"))(
            input_data=InsertModelDimensionsInput()
        )
        assert again["data"]["dimensions_added"] == 0  # no duplicates on a re-run

        arranged = await (await _tool(mcp_server, "arrange_dimensions"))(
            input_data=ArrangeDimensionsInput()
        )
        assert arranged["status"] == "success"
        assert arranged["data"]["overlaps_after"] == 0

        bom = await (await _tool(mcp_server, "insert_bom_table"))(
            input_data=InsertBomTableInput(view_name="Drawing View1")
        )
        assert bom["status"] == "success"
        ghost = await (await _tool(mcp_server, "insert_bom_table"))(
            input_data=InsertBomTableInput(view_name="Ghost")
        )
        assert ghost["status"] == "error"

        scale = await (await _tool(mcp_server, "set_sheet_scale"))(
            input_data=SetSheetScaleInput(numerator=1, denominator=2)
        )
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
                title="Mounting Plate - Rev A",
                drawing_number="MP-RevA-01",
                author="J. Smith",
                notes=["Laser cut from 10 mm plate"],
            )
        )
        assert result["status"] == "success"
        data = result["data"]
        assert data["drawing_path"].endswith("MP-RevA-01.SLDDRW")
        assert data["overlap_check"]["overlaps_after"] == 0
        captions = [v["caption"] for v in data["views"].values()]
        assert "FRONT ELEVATION" in captions
        assert all(":" not in c for c in captions)  # view names only, no scale

    @pytest.mark.asyncio
    async def test_generate_package_missing_model(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        result = await (await _tool(mcp_server, "generate_drawing_package"))(
            input_data=GenerateDrawingPackageInput(model_path="C:/nope/missing.SLDPRT")
        )
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_dict_input_is_accepted(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        result = await (await _tool(mcp_server, "generate_drawing_package"))({})
        assert (
            result["status"] == "error"
        )  # model_path missing -> error, never an exception
