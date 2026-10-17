"""Tests for drawing-automation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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


class TestDrawingAutomationTools:
    """Tools exercised end to end against the mock adapter."""

    @pytest.mark.asyncio
    async def test_register_count(self, mcp_server, mock_adapter, mock_config) -> None:
        count = await register_drawing_automation_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert count == len(await mcp_server.list_tools()) == 5

    @pytest.mark.asyncio
    async def test_dimensions_need_a_drawing(
        self, mcp_server, mock_adapter, mock_config
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await mock_adapter.create_part()
        result = await (await _tool(mcp_server, "insert_model_dimensions"))(
            input_data=InsertModelDimensionsInput()
        )
        assert result["status"] == "error"

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
