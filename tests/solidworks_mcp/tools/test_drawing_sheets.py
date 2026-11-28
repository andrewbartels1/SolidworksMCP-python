"""The drawing sheet tools on the mock adapter (queue item 37).

Spec: tools/drawing-sheets.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.drawing_sheets import (
    ActivateSheetInput,
    AddSheetInput,
    register_drawing_sheet_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("sheets")
    assert await register_drawing_sheet_tools(mcp, adapter, {}) == 3
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def drawing() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()
    return adapter


@pytest.mark.asyncio
async def test_two_sheets(drawing: MockSolidWorksAdapter) -> None:
    tools = await _tools(drawing)

    listed = await tools["list_sheets"]()
    added = await tools["add_sheet"](AddSheetInput(name="Details", scale="2:1"))
    back = await tools["activate_sheet"](ActivateSheetInput(name="Sheet1"))

    assert listed["message"] == "1 sheet(s); active: Sheet1"
    assert added["message"] == "Added and activated Details; 2 sheet(s)"
    assert back["message"] == "Active sheet: Sheet1"


@pytest.mark.asyncio
async def test_an_unknown_sheet_is_an_error_reply(
    drawing: MockSolidWorksAdapter,
) -> None:
    reply = await (await _tools(drawing))["activate_sheet"]({"name": "Nope"})

    assert reply["status"] == "error"
    assert reply["error_type"] == "invalid_input"


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": "D", "paper_size": "letter"},
        {"name": "D", "projection": "x"},
    ],
)
def test_inputs_are_strict(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AddSheetInput(**values)
