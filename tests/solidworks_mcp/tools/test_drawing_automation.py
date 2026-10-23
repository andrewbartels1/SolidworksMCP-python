"""Tests for drawing-automation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.tools.drawing_automation import (
    ArrangeDimensionsInput,
    InsertModelDimensionsInput,
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
        assert count == len(await mcp_server.list_tools()) == 2

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
    async def test_dimensions_and_arrange(
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
