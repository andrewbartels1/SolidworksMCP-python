"""The mock adapter's colours (queue item 36). Spec: tools/appearance."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import (
    AppearanceParameters,
    AppearanceTarget,
    ExtrusionParameters,
)
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.mock_appearance import face_of
from solidworks_mcp.exceptions import InputRefused


@pytest.fixture
async def block() -> MockSolidWorksAdapter:
    """A mock 40 x 40 x 10 block, its box from z 0 to 10."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Top")
    await adapter.add_rectangle(-20, -20, 20, 20)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=10))
    return adapter


@pytest.mark.asyncio
async def test_a_new_part_shows_its_default_colour(
    block: MockSolidWorksAdapter,
) -> None:
    result = await block.get_appearance(AppearanceTarget())

    assert result.data["level"] == "part"
    assert result.data["hex"] == "#e4e4e4"


@pytest.mark.asyncio
async def test_a_face_over_its_feature_over_its_body(
    block: MockSolidWorksAdapter,
) -> None:
    feature = (await block.list_bodies()).data["bodies"][0]["name"]
    await block.set_appearance(AppearanceParameters(body=feature, color="#f28c1a"))
    await block.set_appearance(AppearanceParameters(feature=feature, color="#1fcc33"))
    top = await block.set_appearance(
        AppearanceParameters(face_point=[0, 0, 10], color=[25, 76, 242])
    )

    side = await block.get_appearance(AppearanceTarget(face_point=[20, 0, 5]))
    face = await block.get_appearance(AppearanceTarget(face_point=[0, 0, 10]))
    body = await block.get_appearance(AppearanceTarget(body=feature))

    assert top.data == {
        "target": "face",
        "face_point": [0, 0, 10],
        "color": [25, 76, 242],
        "hex": "#194cf2",
        "transparency": 0.0,
    }
    assert (side.data["level"], side.data["hex"]) == ("feature", "#1fcc33")
    assert (face.data["level"], face.data["hex"]) == ("face", "#194cf2")
    assert (body.data["level"], body.data["hex"]) == ("body", "#f28c1a")


@pytest.mark.asyncio
async def test_a_reset_shows_the_level_above(block: MockSolidWorksAdapter) -> None:
    feature = (await block.list_bodies()).data["bodies"][0]["name"]
    await block.set_appearance(AppearanceParameters(feature=feature, color="#1fcc33"))
    await block.set_appearance(
        AppearanceParameters(face_point=[0, 0, 10], color="#000000")
    )

    result = await block.set_appearance(
        AppearanceParameters(face_point=[0, 0, 10], reset=True)
    )

    assert result.data["reset"] is True
    assert result.data["showing"]["level"] == "feature"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "words"),
    [
        (AppearanceParameters(feature="Nope", color="#000000"), "No feature named"),
        (AppearanceParameters(body="Nope", color="#000000"), "No body named"),
        (AppearanceParameters(face_point=[99, 0, 0], color="#000000"), "No face at"),
        (AppearanceParameters(reset=True), "the part's colour is the base"),
    ],
)
async def test_refusals(
    block: MockSolidWorksAdapter, call: AppearanceParameters, words: str
) -> None:
    result = await block.set_appearance(call)

    assert not result.is_success
    assert words in str(result.error)


@pytest.mark.asyncio
async def test_a_bad_target_is_refused_on_read(block: MockSolidWorksAdapter) -> None:
    result = await block.get_appearance(AppearanceTarget(feature="F", body="B"))

    assert "Give one target" in str(result.error)


@pytest.mark.asyncio
async def test_no_document() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    set_result = await adapter.set_appearance(AppearanceParameters(color="#000000"))
    get_result = await adapter.get_appearance(AppearanceTarget())

    assert set_result.error == get_result.error == "No active model"


def test_a_point_inside_a_box_is_on_no_face() -> None:
    from solidworks_mcp.adapters.body_rules import BodyState

    box = BodyState("B", 1000.0, (0, 0, 0), (10, 10, 10))

    assert face_of([box], [10, 5, 5])[1:] == (0, 1)
    with pytest.raises(InputRefused):
        face_of([box], [5, 5, 5])
