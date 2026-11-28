"""The mock adapter's bodies, as boxes, judged by the real adapter's rules (queue item 35).

Spec: tools/body-listing and tools/body-operations, "Mock adapter".
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from solidworks_mcp.adapters.base import (
    CombineBodiesParameters,
    DeleteBodiesParameters,
    ExtrusionParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SplitBodyParameters,
)
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


async def _extrude(
    adapter: MockSolidWorksAdapter,
    shape: tuple[Any, ...],
    depth: float,
    merge: bool = False,
    named: bool = False,
) -> None:
    sketch = await adapter.create_sketch("Top")
    if shape[0] == "circle":
        await adapter.add_circle(*shape[1:])
    else:
        await adapter.add_rectangle(*shape[1:])
    await adapter.exit_sketch()
    name = sketch.data["name"] if named else None
    await adapter.create_extrusion(
        ExtrusionParameters(depth=depth, merge_result=merge, sketch_name=name)
    )


async def _part(*bodies: tuple[tuple[Any, ...], float]) -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    for shape, depth in bodies:
        await _extrude(adapter, shape, depth)
    return adapter


BLOCK = (("rect", -20, -20, 20, 20), 10)
PIN = (("circle", 0, 0, 5), 20)
FAR = (("rect", 60, 60, 70, 70), 10)


async def _names(adapter: MockSolidWorksAdapter) -> list[str]:
    return [b["name"] for b in (await adapter.list_bodies()).data["bodies"]]


@pytest.mark.asyncio
async def test_unmerged_extrusions_are_bodies_and_merged_ones_grow_the_last() -> None:
    adapter = await _part(BLOCK, PIN)
    await _extrude(adapter, ("rect", 0, 0, 10, 10, True), 10, merge=True, named=True)

    listing = (await adapter.list_bodies()).data

    assert [b["name"] for b in listing["bodies"]] == ["Boss-Extrude1", "Boss-Extrude2"]
    pin = listing["bodies"][1]
    assert pin["volume_mm3"] == pytest.approx(math.pi * 25 * 20 + 4000)
    assert pin["bounding_box_mm"]["max"] == [10.0, 10.0, 20.0]


@pytest.mark.asyncio
async def test_an_extrusion_of_nothing_drawn_makes_no_body() -> None:
    adapter = await _part()
    await adapter.create_sketch("Top")
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=5))
    adapter._note_shape(None, ("circle", 0, 0, 1))

    assert (await adapter.list_bodies()).data["count"] == 0


@pytest.mark.asyncio
async def test_no_active_model() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    listed = await adapter.list_bodies()
    scaled = await adapter.scale_body(ScaleBodyParameters(scale=2))

    assert listed.error == scaled.error == "No active model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "volume", "count"),
    [
        ("add", 16000 + 1000 * math.pi * 2 - 1000, 1),
        ("subtract", 15000, 1),
        ("common", 1000, 1),
    ],
)
async def test_a_combine(operation: str, volume: float, count: int) -> None:
    # The pin's box overlaps the block by 10 x 10 x 10.
    adapter = await _part(BLOCK, PIN)

    result = await adapter.combine_bodies(
        CombineBodiesParameters(
            operation=operation,
            main_body="boss-extrude1",
            tool_bodies=["Boss-Extrude2"],
        )
    )

    assert result.is_success, result.error
    assert result.data["name"] == "Combine1"
    assert result.data["operation"] == operation
    assert result.data["body_count_after"] == count
    assert result.data["volume_after_mm3"] == pytest.approx(
        16000 + 500 * math.pi - 1000 if operation == "add" else volume
    )


@pytest.mark.asyncio
async def test_a_subtract_that_removes_nothing_fails_and_changes_nothing() -> None:
    adapter = await _part(BLOCK, FAR)

    result = await adapter.combine_bodies(
        CombineBodiesParameters(
            operation="subtract",
            main_body="Boss-Extrude1",
            tool_bodies=["Boss-Extrude2"],
        )
    )

    assert "combine_bodies should leave the main body smaller" in (result.error or "")
    assert await _names(adapter) == ["Boss-Extrude1", "Boss-Extrude2"]


@pytest.mark.asyncio
async def test_an_unknown_body_is_refused() -> None:
    adapter = await _part(BLOCK)

    result = await adapter.delete_bodies(DeleteBodiesParameters(bodies=["Nope"]))

    assert result.error == "No body named 'Nope'. Bodies in the part: Boss-Extrude1."


@pytest.mark.asyncio
async def test_a_split_at_the_right_plane_halves_the_block() -> None:
    adapter = await _part(BLOCK, FAR)

    result = await adapter.split_body(SplitBodyParameters(tool="right plane"))

    assert result.data["made"] == ["Split1[1]", "Split1[2]"]
    assert result.data["bodies_after"] == ["Split1[1]", "Split1[2]", "Boss-Extrude2"]
    assert result.data["volume_change_mm3"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "message"),
    [
        ("Sketch1", "No plane or sketch named 'Sketch1' to split with"),
        ("Front Plane", "split_body should make more bodies"),
    ],
)
async def test_a_split_refused_or_making_nothing(tool: str, message: str) -> None:
    adapter = await _part(BLOCK)

    result = await adapter.split_body(SplitBodyParameters(tool=tool))

    assert message in (result.error or "")


@pytest.mark.asyncio
async def test_a_move_and_copies() -> None:
    adapter = await _part(BLOCK)

    moved = await adapter.move_copy_body(
        MoveCopyBodyParameters(bodies=["Boss-Extrude1"], translate=[50, 0, 0])
    )
    copied = await adapter.move_copy_body(
        MoveCopyBodyParameters(
            bodies=["Boss-Extrude1"], translate=[0, 50, 0], as_copy=True, copies=2
        )
    )

    assert moved.data["name"] == "Body-Move/Copy1"
    assert (moved.data["as_copy"], moved.data["copies"]) == (False, 0)
    assert copied.data["bodies_after"][1:] == [
        "Body-Move/Copy2[1]",
        "Body-Move/Copy2[2]",
    ]
    assert copied.data["volume_after_mm3"] == 48000
    assert (copied.data["as_copy"], copied.data["copies"]) == (True, 2)


@pytest.mark.asyncio
async def test_a_rotation_alone_moves_nothing_on_the_mock() -> None:
    adapter = await _part(BLOCK)

    result = await adapter.move_copy_body(
        MoveCopyBodyParameters(bodies=["Boss-Extrude1"], rotate=[0, 0, 90])
    )

    assert "move_copy_body should move the bodies" in (result.error or "")


@pytest.mark.asyncio
async def test_keep_one_of_two() -> None:
    adapter = await _part(BLOCK, FAR)

    result = await adapter.delete_bodies(
        DeleteBodiesParameters(bodies=["Boss-Extrude2"], keep=True)
    )

    assert result.data["removed"] == ["Boss-Extrude1"]
    assert result.data["keep"] is True
    assert await _names(adapter) == ["Boss-Extrude2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "box"),
    [
        (
            ScaleBodyParameters(scale=2),
            {"min": [-40.0, -40.0, -5.0], "max": [40.0, 40.0, 15.0]},
        ),
        (
            ScaleBodyParameters(
                scale_xyz=[1, 1, 2], about="origin", bodies=["boss-extrude1"]
            ),
            {"min": [-20.0, -20.0, 0.0], "max": [20.0, 20.0, 20.0]},
        ),
    ],
)
async def test_a_scale(
    params: ScaleBodyParameters, box: dict[str, list[float]]
) -> None:
    adapter = await _part(BLOCK)

    result = await adapter.scale_body(params)
    after = (await adapter.list_bodies()).data["bodies"][0]["bounding_box_mm"]

    assert result.is_success, result.error
    assert {"min": after["min"], "max": after["max"]} == box


@pytest.mark.asyncio
async def test_a_scale_leaves_other_bodies() -> None:
    adapter = await _part(BLOCK, FAR)

    result = await adapter.scale_body(
        ScaleBodyParameters(scale=2, bodies=["Boss-Extrude2"])
    )

    assert result.data["volume_after_mm3"] == 16000 + 8000
    assert result.data["factors"] == [2.0, 2.0, 2.0]
    assert result.data["about"] == "centroid"
