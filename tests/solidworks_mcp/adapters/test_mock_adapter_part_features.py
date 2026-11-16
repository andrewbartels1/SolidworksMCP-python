"""The mock adapter's part features: self-consistent volumes.

Spec: tools/measured-feature-change.
"""

from __future__ import annotations

import math

import pytest

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
def mock() -> MockSolidWorksAdapter:
    return MockSolidWorksAdapter({})


@pytest.mark.asyncio
async def test_volumes_chain_from_feature_to_feature(
    mock: MockSolidWorksAdapter,
) -> None:
    hole = await mock.create_hole([0, 0, 20], "simple", "iso", "M6", "blind", 10)
    shell = await mock.create_shell(2, [[0, 0, 20]], outward=True)

    assert hole.data["volume_before"] == 64000.0
    assert hole.data["volume_change"] == pytest.approx(-math.pi * 9 * 10)
    assert shell.data["volume_before"] == hole.data["volume_after"]
    assert shell.data["volume_change"] == -(36.0**3)
    assert shell.data["name"].startswith("Shell")


@pytest.mark.asyncio
async def test_a_hole_that_is_not_metric_is_6_mm_through(
    mock: MockSolidWorksAdapter,
) -> None:
    hole = await mock.create_hole([0, 0, 20], "tapped", "ansi_inch", "1/4-20")

    assert hole.data["volume_change"] == pytest.approx(-math.pi * 9 * 40)


@pytest.mark.asyncio
async def test_pattern_rib_draft_and_thread(mock: MockSolidWorksAdapter) -> None:
    one_row = await mock.pattern_linear(["Hole1"], "Edge1", 3, 10)
    grid = await mock.pattern_linear(["Hole1"], [0, 0, 0], 3, 10, [1, 0, 0], 2, 5)
    rib = await mock.create_rib("Sketch2", 2)
    draft = await mock.add_draft(5, [[20, 0, 10], [-20, 0, 10]], [0, 0, 0])
    thread = await mock.add_cosmetic_thread([3, 0, 20], "M6x1.0", 6, depth=8)

    assert (one_row.data["volume_change"], one_row.data["count2"]) == (2000.0, None)
    assert (grid.data["volume_change"], grid.data["spacing2_mm"]) == (5000.0, 5.0)
    assert rib.data["volume_change"] == 1600.0
    assert draft.data["volume_change"] < 0
    assert thread.data["volume_change"] == 0.0


@pytest.mark.asyncio
async def test_convert_entities_needs_an_open_sketch(
    mock: MockSolidWorksAdapter,
) -> None:
    refused = await mock.sketch_convert_entities([[0, 0, 20]])
    mock._current_sketch = "Sketch1"
    made = await mock.sketch_convert_entities(
        [[0, 0, 20]], [0, 0, 20], construction=True
    )

    assert refused.error == "No active sketch"
    assert made.data["count"] == 5
    assert set(made.data["entities"]) <= mock._sketch_entity_ids
