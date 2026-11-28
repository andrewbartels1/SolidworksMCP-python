"""Colours on fake COM objects shaped like SolidWorks 2026's (queue item 36).

Spec: tools/appearance. The calls are the ones the probes of 2026-11-28
measured (design.md of the appearance-and-reference-tools change).
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters import sw_type_info
from solidworks_mcp.adapters.base import AppearanceParameters, AppearanceTarget
from solidworks_mcp.adapters.solidworks import appearance

from .appearance_fakes import Body, Coloured, Face, Harness, Model

GREEN = [31 / 255, 204 / 255, 51 / 255, 1.0, 1.0, 0.5, 0.3125, 0.0, 0.0]


@pytest.fixture(autouse=True)
def plain_com(monkeypatch: pytest.MonkeyPatch) -> None:
    """No flagging; arrays as lists."""
    monkeypatch.setattr(sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(appearance, "double_array", list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "holder"),
    [
        (AppearanceParameters(color="#1fcc33"), lambda m: m),
        (
            AppearanceParameters(feature="Boss-Extrude1", color="#1fcc33"),
            lambda m: m.feature,
        ),
        (
            AppearanceParameters(body="boss-extrude1", color="#1fcc33"),
            lambda m: m.bodies[0],
        ),
        (
            AppearanceParameters(face_point=[0, 10, 0], color="#1fcc33"),
            lambda m: m.face,
        ),
    ],
)
async def test_each_level_is_coloured_and_read_back(
    call: AppearanceParameters, holder: Any
) -> None:
    model = Model()

    result = await Harness(model).set_appearance(call)

    assert result.is_success, result.error
    assert result.data["hex"] == "#1fcc33"
    assert holder(model).values == pytest.approx(GREEN)


@pytest.mark.asyncio
async def test_a_face_reads_the_nearest_level() -> None:
    model = Model()
    model.feature.values = GREEN
    model.bodies[0].values = [0.9, 0.5, 0.1, 1, 1, 0.5, 0.3125, 0, 0]

    face = await Harness(model).get_appearance(AppearanceTarget(face_point=[0, 10, 0]))
    body = await Harness(model).get_appearance(AppearanceTarget(body="Boss-Extrude1"))
    part = await Harness(model).get_appearance(AppearanceTarget())

    assert (face.data["level"], face.data["hex"]) == ("feature", "#1fcc33")
    assert body.data["level"] == "body"
    assert part.data["level"] == "part"
    assert face.data["face_point"] == [0, 10, 0]


@pytest.mark.asyncio
async def test_a_face_with_nothing_above_it_reads_nothing() -> None:
    model = Model()
    model.values = None
    model.face = Face(None, None)
    model.faces[(0.0, 0.01, 0.0)] = model.face

    result = await Harness(model).get_appearance(
        AppearanceTarget(face_point=[0, 10, 0])
    )

    assert result.data["level"] is None and result.data["color"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "holder"),
    [
        (AppearanceParameters(feature="Boss-Extrude1", reset=True), "feature"),
        (AppearanceParameters(body="Boss-Extrude1", reset=True), "body"),
        (AppearanceParameters(face_point=[0, 10, 0], reset=True), "face"),
    ],
)
async def test_a_reset_removes_the_level_and_shows_the_next(
    call: AppearanceParameters, holder: str
) -> None:
    model = Model()
    target: Coloured = {
        "feature": model.feature,
        "body": model.bodies[0],
        "face": model.face,
    }[holder]
    target.values = GREEN

    result = await Harness(model).set_appearance(call)

    assert target.removed == 1
    assert result.data["reset"] is True
    assert result.data["showing"]["level"] == "part"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "words"),
    [
        (AppearanceParameters(feature="Nope", color="#000000"), "No feature named"),
        (AppearanceParameters(body="Nope", color="#000000"), "No body named"),
        (AppearanceParameters(face_point=[5, 5, 5], color="#000000"), "No face at"),
        (AppearanceParameters(reset=True), "the part's colour is the base"),
        (
            AppearanceParameters(feature="Boss-Extrude1", body="B", color="#000000"),
            "Give one target",
        ),
    ],
)
async def test_refusals(call: AppearanceParameters, words: str) -> None:
    result = await Harness(Model()).set_appearance(call)

    assert not result.is_success
    assert words in str(result.error)


@pytest.mark.asyncio
async def test_a_colour_solidworks_drops_fails() -> None:
    model = Model()

    class Forgetful(Coloured):
        def SetMaterialPropertyValues2(self, values: Any, *rest: Any) -> None:
            return None

    model.feature = Forgetful("Boss-Extrude1")

    result = await Harness(model).set_appearance(
        AppearanceParameters(feature="Boss-Extrude1", color="#000000")
    )

    assert "did not keep the colour on the feature" in str(result.error)


@pytest.mark.asyncio
async def test_no_document() -> None:
    harness = Harness(None)

    set_result = await harness.set_appearance(AppearanceParameters(color="#000000"))
    get_result = await harness.get_appearance(AppearanceTarget())

    assert set_result.error == get_result.error == "No active model"


def test_a_face_found_by_point_is_left_unselected() -> None:
    model = Model()

    face = Harness(model)._face_at([0, 10, 0])

    assert face is model.face
    assert model.selected is None


def test_a_body_found_by_name_ignores_case() -> None:
    body = Body("Block")

    assert Harness(Model([body]))._body_named("BLOCK") is body
