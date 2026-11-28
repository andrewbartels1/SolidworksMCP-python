"""The multi-body tools on the mock adapter (queue item 35).

Spec: tools/body-listing and tools/body-operations.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.bodies import (
    CombineBodiesInput,
    MoveCopyBodyInput,
    ScaleBodyInput,
    register_body_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("bodies")
    assert await register_body_tools(mcp, adapter, {}) == 6
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    """A mock part: a 40 x 40 x 10 block and, unmerged, a 10 x 10 x 20 post."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    for corners, depth in (((-20, -20, 20, 20), 10), ((-5, -5, 5, 5), 20)):
        await adapter.create_sketch("Top")
        await adapter.add_rectangle(*corners)
        await adapter.exit_sketch()
        await adapter.create_extrusion(
            ExtrusionParameters(depth=depth, merge_result=False)
        )
    return adapter


@pytest.mark.asyncio
async def test_list_bodies(part: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(part))["list_bodies"]()

    assert reply["message"] == "2 solid bodies"
    assert reply["count"] == 2
    assert [b["name"] for b in reply["bodies"]] == ["Boss-Extrude1", "Boss-Extrude2"]


@pytest.mark.asyncio
async def test_a_mould_core(part: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(part))["combine_bodies"](
        CombineBodiesInput(
            operation="subtract",
            main_body="Boss-Extrude1",
            tool_bodies=["Boss-Extrude2"],
        )
    )

    assert reply["message"] == (
        "Subtract: 2 bodies, 18,000.0 mm³ -> 1 body, 15,000.0 mm³"
    )
    assert reply["combine"]["name"] == "Combine1"


@pytest.mark.asyncio
async def test_split_move_copy_scale_and_keep(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    split = await tools["split_body"]({"tool": "Right Plane"})
    moved = await tools["move_copy_body"](
        {"bodies": ["Split1[1]"], "translate": [0, 0, 30]}
    )
    copied = await tools["move_copy_body"](
        MoveCopyBodyInput(
            bodies=["Split1[2]"], translate=[60, 0, 0], as_copy=True, copies=2
        )
    )
    scaled = await tools["scale_body"](ScaleBodyInput(scale=2, bodies=["Split1[2]"]))
    kept = await tools["delete_bodies"]({"bodies": ["Split1[2]"], "keep": True})

    assert split["message"].startswith("Split at Right Plane: 2 bodies")
    assert split["split"]["made"] == [
        "Split1[1]",
        "Split1[2]",
        "Split1[3]",
        "Split1[4]",
    ]
    assert moved["message"].startswith("Moved: ")
    assert copied["message"].startswith("Copied 2x: ")
    assert copied["move"]["body_count_after"] == 6
    assert scaled["message"].startswith("Scaled: ")
    # 18,000 split in four, 8,000 copied twice (34,000), that half scaled x2
    # (8,000 -> 64,000): 90,000, of which the scaled half is kept.
    assert kept["message"] == "Kept: 6 bodies, 90,000.0 mm³ -> 1 body, 64,000.0 mm³"
    assert kept["delete"]["keep"] is True


@pytest.mark.asyncio
async def test_delete_one(part: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(part))["delete_bodies"]({"bodies": ["Boss-Extrude2"]})

    assert reply["message"].startswith("Deleted: 2 bodies")
    assert reply["delete"]["removed"] == ["Boss-Extrude2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments", "error_type", "words"),
    [
        (
            "combine_bodies",
            {"operation": "add", "main_body": "Nope", "tool_bodies": ["Boss-Extrude2"]},
            "invalid_input",
            "No body named 'Nope'",
        ),
        (
            "move_copy_body",
            {"bodies": ["Boss-Extrude1"], "translate": [1, 0, 0], "rotate": [0, 0, 90]},
            "invalid_input",
            "not both",
        ),
        (
            "delete_bodies",
            {"bodies": ["Boss-Extrude1", "Boss-Extrude2"]},
            "invalid_input",
            "delete every body",
        ),
        ("scale_body", {"scale": 1}, "invalid_input", "does nothing"),
        (
            "split_body",
            {"tool": "Front Plane"},
            "feature_not_built",
            "should make more bodies",
        ),
    ],
)
async def test_refusals_are_error_replies(
    part: MockSolidWorksAdapter,
    tool: str,
    arguments: dict[str, Any],
    error_type: str,
    words: str,
) -> None:
    reply = await (await _tools(part))[tool](arguments)

    assert reply["status"] == "error"
    assert reply["error_type"] == error_type
    assert words in reply["message"]


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            CombineBodiesInput,
            {"operation": "merge", "main_body": "A", "tool_bodies": ["B"]},
        ),
        (CombineBodiesInput, {"operation": "add", "main_body": "A", "tool_bodies": []}),
        (MoveCopyBodyInput, {"bodies": ["A"], "translate": [1, 0]}),
        (MoveCopyBodyInput, {"bodies": ["A"], "as_copy": True, "copies": 51}),
        (ScaleBodyInput, {"scale": 0}),
        (ScaleBodyInput, {"scale_xyz": [1, 2]}),
    ],
)
def test_inputs_are_strict(model: type, values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model(**values)
