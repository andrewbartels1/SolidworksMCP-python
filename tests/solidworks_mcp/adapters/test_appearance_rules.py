"""The rules the appearance and reference-extras adapters share (queue items 36, 39).

Spec: tools/appearance and tools/reference-extras.
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters import appearance_rules as rules
from solidworks_mcp.adapters.base import AppearanceParameters, AppearanceTarget
from solidworks_mcp.exceptions import InputRefused


@pytest.mark.parametrize(
    ("target", "kind"),
    [
        (AppearanceTarget(), "part"),
        (AppearanceTarget(feature="Boss-Extrude1"), "feature"),
        (AppearanceTarget(body="Body1"), "body"),
        (AppearanceTarget(face_point=[0, 10, 0]), "face"),
    ],
)
def test_one_target(target: AppearanceTarget, kind: str) -> None:
    assert rules.target_kind(target) == kind


@pytest.mark.parametrize(
    ("target", "words"),
    [
        (AppearanceTarget(feature="F", body="B"), "not feature and body"),
        (AppearanceTarget(face_point=[1, 2]), "face_point must be [x, y, z]"),
    ],
)
def test_bad_targets_are_refused(target: AppearanceTarget, words: str) -> None:
    with pytest.raises(InputRefused, match=words.replace("[", r"\[")):
        rules.target_kind(target)


@pytest.mark.parametrize(
    ("value", "rgb"),
    [
        ("#1fcc33", (31, 204, 51)),
        ("1FCC33", (31, 204, 51)),
        ([25, 76, 242], (25, 76, 242)),
    ],
)
def test_colours_parse(value: Any, rgb: tuple[int, int, int]) -> None:
    assert rules.parse_color(value) == rgb


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (None, "Give a color"),
        ("#12", "is not '#rrggbb'"),
        ([1, 2], r"must be \[r, g, b\]"),
        ([0, 0, 256], r"must be \[r, g, b\]"),
    ],
)
def test_bad_colours_are_refused(value: Any, words: str) -> None:
    with pytest.raises(InputRefused, match=words):
        rules.parse_color(value)


def test_a_set_call_returns_its_target() -> None:
    assert rules.check_set(AppearanceParameters(color="#000000")) == "part"
    assert rules.check_set(AppearanceParameters(feature="F", reset=True)) == "feature"


@pytest.mark.parametrize(
    ("params", "words"),
    [
        (AppearanceParameters(reset=True), "the part's colour is the base"),
        (
            AppearanceParameters(feature="F", reset=True, color="#000000"),
            "not both",
        ),
        (AppearanceParameters(color="#000000", transparency=1.5), "transparency"),
        (AppearanceParameters(), "Give a color"),
    ],
)
def test_bad_set_calls_are_refused(params: AppearanceParameters, words: str) -> None:
    with pytest.raises(InputRefused, match=words):
        rules.check_set(params)


def test_material_values_keep_solidworks_shading() -> None:
    values = rules.material_values((255, 0, 51), 0.25)

    assert values == [1.0, 0.0, 0.2, 1.0, 1.0, 0.5, 0.3125, 0.25, 0.0]


@pytest.mark.parametrize(
    ("values", "reply"),
    [
        (None, None),
        ([-1.0] * 9, None),
        ([1, 2], None),
        (
            [0.1, 0.8, 0.2, 1, 1, 0.5, 0.3125, 0.4, 0],
            {"color": [26, 204, 51], "hex": "#1acc33", "transparency": 0.4},
        ),
    ],
)
def test_colours_read_back(values: Any, reply: dict[str, Any] | None) -> None:
    assert rules.color_reply(values) == reply


def test_a_section_in_mm() -> None:
    # A 40 mm square at y = 10, as SolidWorks 2026 gave it.
    values = [0.0, 0.0016, 0.0, 0.01, 0.0]
    values += [2.1333e-7, 4.2667e-7, 2.1333e-7, 0.0, 0.0, 0.0, 4.2667e-7, 0.0]
    values += [2.1333e-7, 2.1333e-7] + [0.0] * 9

    reply = rules.section_reply(values)

    assert reply["area_mm2"] == pytest.approx(1600)
    assert reply["centroid_mm"] == pytest.approx([0, 10, 0])
    assert reply["ixx"] == pytest.approx(213330)
    assert reply["polar_moment_mm4"] == pytest.approx(426670)
    assert reply["principal_moments_mm4"] == pytest.approx([213330, 213330])


@pytest.mark.parametrize(
    ("values", "words"),
    [(None, "gave no section properties"), ([1.0] + [0.0] * 23, "status 1")],
)
def test_a_failed_section_is_refused(values: Any, words: str) -> None:
    with pytest.raises(InputRefused, match=words):
        rules.section_reply(values)


def test_a_transform_in_mm() -> None:
    array = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0.02, 0.01, -0.005, 1, 0, 0, 0]

    reply = rules.transform_reply(array)

    assert reply == {
        "origin_mm": [20.0, 10.0, -5.0],
        "x_axis": [1.0, 0.0, 0.0],
        "y_axis": [0.0, 1.0, 0.0],
        "z_axis": [0.0, 0.0, 1.0],
    }


def test_an_unreadable_transform_fails() -> None:
    with pytest.raises(RuntimeError, match="transform"):
        rules.transform_reply(None)


def test_model_axes() -> None:
    assert rules.model_axes()["z_axis"] == [0.0, 0.0, 1.0]
