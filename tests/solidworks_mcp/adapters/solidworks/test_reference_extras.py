"""Reference and analysis extras on fake COM objects shaped like SolidWorks 2026's.

Spec: tools/reference-extras (queue item 39). The calls are the ones the
probes of 2026-11-28 measured.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters import sw_type_info
from solidworks_mcp.adapters.base import (
    BoundingBoxParameters,
    CoordinateSystemParameters,
    SectionPropertiesParameters,
)
from solidworks_mcp.adapters.solidworks import reference_extras

from .appearance_fakes import Harness, Model, TreeFeature


@pytest.fixture(autouse=True)
def plain_com(monkeypatch: pytest.MonkeyPatch) -> None:
    """No flagging; the by-reference status as a namespace."""
    monkeypatch.setattr(sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(
        reference_extras, "long_ref", lambda value=0: SimpleNamespace(value=7)
    )


@pytest.mark.asyncio
async def test_a_coordinate_system_at_a_sketch_point() -> None:
    model = Model()

    result = await Harness(model).create_coordinate_system(
        CoordinateSystemParameters(origin=[20, 10, 20])
    )

    assert result.data == {
        "name": "Coordinate System1",
        "sketch": "3DSketch1",
        "origin_mm": [20.0, 10.0, 20.0],
        "x_axis": [1.0, 0.0, 0.0],
        "y_axis": [0.0, 1.0, 0.0],
        "z_axis": [0.0, 0.0, 1.0],
    }
    select = next(args for what, args in model.inserted if what == "select")
    assert select[:2] == ("Point1@3DSketch1", "EXTSKETCHPOINT")
    assert select[6] == 1  # the origin's mark
    assert ("coordinate", (False, False, False)) in model.inserted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"origin": [0, 0]}, "origin must be"),
        ({"point": None}, "drew no origin point"),
        ({"made": None}, "made no coordinate system"),
    ],
)
async def test_coordinate_system_failures(change: dict, words: str) -> None:
    model = Model()
    origin = change.pop("origin", [0, 0, 0])
    if "point" in change:
        model.point = None
    if "made" in change:
        model.made["coordinate"] = None

    result = await Harness(model).create_coordinate_system(
        CoordinateSystemParameters(origin=origin)
    )

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_the_centre_of_mass_point() -> None:
    result = await Harness(Model()).create_center_of_mass_point()

    assert result.data == {
        "name": "Center of Mass",
        "center_of_mass_mm": [0.0, 5.0, 0.0],
    }


@pytest.mark.asyncio
async def test_an_unreadable_centre_is_none() -> None:
    model = Model()
    model.centre = None

    result = await Harness(model).create_center_of_mass_point()

    assert result.data["center_of_mass_mm"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "words"),
    [
        ("no body", "no solid body"),
        ("one already", "has a Center of Mass point already ('Center of Mass')"),
        ("not made", "made no Center of Mass point"),
    ],
)
async def test_centre_of_mass_failures(setup: str, words: str) -> None:
    model = Model([] if setup == "no body" else None)
    if setup == "one already":
        model.tree = TreeFeature(
            "Origin",
            "OriginProfileFeature",
            TreeFeature("Center of Mass", "CenterOfMass"),
        )
    if setup == "not made":
        model.made["com"] = None

    result = await Harness(model).create_center_of_mass_point()

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_the_bounding_box() -> None:
    model = Model()

    result = await Harness(model).create_bounding_box(
        BoundingBoxParameters(include_hidden=True)
    )

    assert result.data["size_mm"] == [40.0, 10.0, 40.0]
    assert result.data["min_mm"] == [-20.0, 0.0, -20.0]
    box_call = next(args for what, args in model.inserted if what == "box")
    assert box_call[:3] == (0, True, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "words"),
    [
        ("no body", "no solid body to box"),
        ("one already", "has a bounding box already ('Bounding Box')"),
        ("not made", "made no bounding box (status 7)"),
    ],
)
async def test_bounding_box_failures(setup: str, words: str) -> None:
    model = Model([] if setup == "no body" else None)
    if setup == "one already":
        model.tree = TreeFeature("Bounding Box", "BoundingBoxProfileFeat")
    if setup == "not made":
        model.made["box"] = None

    result = await Harness(model).create_bounding_box(BoundingBoxParameters())

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_a_face_section() -> None:
    model = Model()

    result = await Harness(model).get_section_properties(
        SectionPropertiesParameters(face_point=[0, 10, 0])
    )

    assert result.data["area_mm2"] == pytest.approx(1600)
    assert result.data["face_point"] == [0, 10, 0]
    assert model.selected is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("point", "section", "words"),
    [
        ([0, 0], None, "face_point must be"),
        ([5, 5, 5], None, "No face at"),
        ([0, 10, 0], [1.0] + [0.0] * 23, "couldn't take a section"),
    ],
)
async def test_section_failures(point: list, section: list | None, words: str) -> None:
    model = Model()
    if section is not None:
        model.section = section

    result = await Harness(model).get_section_properties(
        SectionPropertiesParameters(face_point=point)
    )

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_no_document() -> None:
    harness = Harness(None)

    results = [
        await harness.create_coordinate_system(
            CoordinateSystemParameters(origin=[0, 0, 0])
        ),
        await harness.create_center_of_mass_point(),
        await harness.create_bounding_box(BoundingBoxParameters()),
        await harness.get_section_properties(
            SectionPropertiesParameters(face_point=[0, 0, 0])
        ),
    ]

    assert {r.error for r in results} == {"No active model"}
