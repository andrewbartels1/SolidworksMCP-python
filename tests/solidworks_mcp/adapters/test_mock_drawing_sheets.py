"""The mock adapter's drawing sheets (queue item 37). Spec: tools/drawing-sheets."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AddSheetParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


async def _drawing() -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_drawing()
    return adapter


@pytest.mark.asyncio
async def test_add_list_and_activate() -> None:
    adapter = await _drawing()

    first = await adapter.list_sheets()
    added = await adapter.add_sheet(
        AddSheetParameters(name="Details", sheet_format="a2 - iso", scale="2:1")
    )
    back = await adapter.activate_sheet("sheet1")

    assert first.data["active"] == "Sheet1"
    assert added.data["active"] == "Details"
    assert added.data["sheets"][1] == {
        "name": "Details",
        "active": True,
        "paper_mm": [594.0, 420.0],
        "scale": "2:1",
        "projection": "third",
    }
    assert back.data["active"] == "Sheet1"


@pytest.mark.asyncio
async def test_a_given_projection() -> None:
    adapter = await _drawing()

    added = await adapter.add_sheet(AddSheetParameters(name="D", projection="first"))

    assert added.data["sheets"][1]["projection"] == "first"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "words"),
    [
        (AddSheetParameters(name="sheet1"), "already"),
        (AddSheetParameters(name="D", scale="big"), "scale 'big'"),
    ],
)
async def test_refused_sheets(params: AddSheetParameters, words: str) -> None:
    adapter = await _drawing()

    result = await adapter.add_sheet(params)

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_an_unknown_sheet() -> None:
    result = await (await _drawing()).activate_sheet("Nope")

    assert "No sheet named 'Nope'" in str(result.error)


@pytest.mark.asyncio
async def test_a_part_is_not_a_drawing() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()

    results = [
        await adapter.list_sheets(),
        await adapter.add_sheet(AddSheetParameters(name="D")),
        await adapter.activate_sheet("Sheet1"),
    ]

    assert all(not r.is_success for r in results)
