"""The mock adapter's reference and analysis extras (queue item 39).

Spec: tools/reference-extras.
"""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import (
    BoundingBoxParameters,
    CoordinateSystemParameters,
    ExtrusionParameters,
    SectionPropertiesParameters,
)
from solidworks_mcp.adapters.body_rules import BodyState
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.mock_reference_extras import rectangle_section


async def _part(boxes: int) -> MockSolidWorksAdapter:
    """A mock part with ``boxes`` 40 x 40 x 10 blocks (0 for none)."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    for _ in range(boxes):
        await adapter.create_sketch("Top")
        await adapter.add_rectangle(-20, -20, 20, 20)
        await adapter.exit_sketch()
        await adapter.create_extrusion(ExtrusionParameters(depth=10))
    return adapter


@pytest.mark.asyncio
async def test_a_coordinate_system_counts_up() -> None:
    adapter = await _part(1)

    first = await adapter.create_coordinate_system(
        CoordinateSystemParameters(origin=[20, 10, 20])
    )
    second = await adapter.create_coordinate_system(
        CoordinateSystemParameters(origin=[0, 0, 0])
    )

    assert first.data["name"] == "Coordinate System1"
    assert first.data["origin_mm"] == [20.0, 10.0, 20.0]
    assert first.data["x_axis"] == [1.0, 0.0, 0.0]
    assert second.data["sketch"] == "3DSketch2"


@pytest.mark.asyncio
async def test_the_centre_of_mass_once() -> None:
    adapter = await _part(1)

    first = await adapter.create_center_of_mass_point()
    second = await adapter.create_center_of_mass_point()

    assert first.data == {"name": "Center of Mass", "center_of_mass_mm": [0, 0, 5]}
    assert "already" in str(second.error)


@pytest.mark.asyncio
async def test_the_bounding_box_once() -> None:
    adapter = await _part(1)

    first = await adapter.create_bounding_box(BoundingBoxParameters())
    second = await adapter.create_bounding_box(BoundingBoxParameters())

    assert first.data["size_mm"] == [40, 40, 10]
    assert "already" in str(second.error)


@pytest.mark.asyncio
async def test_a_top_face_section() -> None:
    adapter = await _part(1)

    result = await adapter.get_section_properties(
        SectionPropertiesParameters(face_point=[0, 0, 10])
    )

    assert result.data["area_mm2"] == 1600
    assert result.data["centroid_mm"] == [0, 0, 10]
    assert result.data["ixx"] == pytest.approx(40**4 / 12, abs=0.01)
    assert result.data["polar_moment_mm4"] == pytest.approx(40**4 / 6, abs=0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("point", "words"),
    [([0, 0], "face_point must be"), ([0, 0, 5], "No face at")],
)
async def test_a_bad_section_point(point: list[float], words: str) -> None:
    adapter = await _part(1)

    result = await adapter.get_section_properties(
        SectionPropertiesParameters(face_point=point)
    )

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_no_body() -> None:
    adapter = await _part(0)

    com = await adapter.create_center_of_mass_point()
    box = await adapter.create_bounding_box(BoundingBoxParameters())
    cs = await adapter.create_coordinate_system(
        CoordinateSystemParameters(origin=[0, 0])
    )

    assert "no solid body" in str(com.error)
    assert "no solid body" in str(box.error)
    assert "origin must be" in str(cs.error)


@pytest.mark.asyncio
async def test_no_document() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    results = [
        await adapter.create_coordinate_system(
            CoordinateSystemParameters(origin=[0, 0, 0])
        ),
        await adapter.create_center_of_mass_point(),
        await adapter.create_bounding_box(BoundingBoxParameters()),
        await adapter.get_section_properties(
            SectionPropertiesParameters(face_point=[0, 0, 0])
        ),
    ]

    assert {r.error for r in results} == {"No active model"}


def test_a_side_face_section() -> None:
    box = BodyState("B", 4000.0, (0, 0, 0), (20, 10, 20))

    reply = rectangle_section(box, 0, 0)

    assert reply["area_mm2"] == 200
    assert reply["centroid_mm"] == [0, 5, 10]
    assert reply["principal_moments_mm4"] == pytest.approx(
        [200 * 10**2 / 12, 200 * 20**2 / 12], abs=0.01
    )
