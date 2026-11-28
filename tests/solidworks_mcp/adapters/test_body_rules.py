"""The rules every multi-body operation is held to (queue item 35).

Spec: tools/body-listing and tools/body-operations.
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters import body_rules as rules
from solidworks_mcp.adapters.base import (
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
)
from solidworks_mcp.adapters.body_rules import BodyState
from solidworks_mcp.exceptions import InputRefused

BLOCK = BodyState("Block", 16000.0, (-20.0, -20.0, 0.0), (20.0, 20.0, 10.0))
PIN = BodyState("Pin", 1000.0, (-5.0, -5.0, 0.0), (5.0, 5.0, 20.0))
PART = [BLOCK, PIN]


def _moved(body: BodyState, dx: float, name: str | None = None) -> BodyState:
    return BodyState(
        name or body.name,
        body.volume,
        (body.box_min[0] + dx, body.box_min[1], body.box_min[2]),
        (body.box_max[0] + dx, body.box_max[1], body.box_max[2]),
    )


def test_a_listing_names_each_body_with_its_volume_and_box() -> None:
    listing = rules.listing(PART)

    assert listing["count"] == 2
    assert listing["total_volume_mm3"] == 17000.0
    assert listing["bodies"][0] == {
        "name": "Block",
        "volume_mm3": 16000.0,
        "bounding_box_mm": {
            "min": [-20.0, -20.0, 0.0],
            "max": [20.0, 20.0, 10.0],
            "size": [40.0, 40.0, 10.0],
        },
    }
    assert rules.listing([]) == {"bodies": [], "count": 0, "total_volume_mm3": 0}


def test_bodies_are_found_without_regard_to_case_once_each() -> None:
    assert rules.resolve_bodies(PART, ["pin", "BLOCK", "Pin"]) == ["Pin", "Block"]


@pytest.mark.parametrize(
    ("bodies", "wanted", "message"),
    [
        (PART, [], "Name at least one body. Bodies in the part: Block, Pin."),
        (PART, ["Nope"], "No body named 'Nope'. Bodies in the part: Block, Pin."),
        ([], ["Nope"], "Bodies in the part: none."),
    ],
)
def test_an_unknown_or_missing_body_is_refused(
    bodies: list[BodyState], wanted: list[str], message: str
) -> None:
    with pytest.raises(InputRefused, match=message.replace(".", r"\.")):
        rules.resolve_bodies(bodies, wanted)


def test_a_combine_gives_the_real_names() -> None:
    params = CombineBodiesParameters(
        operation="subtract", main_body="block", tool_bodies=["pin"]
    )

    assert rules.check_combine(params, PART) == ("Block", ["Pin"])


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"operation": "merge"}, "operation must be one of add, subtract, common"),
        ({"tool_bodies": []}, "Name at least one tool body to subtract with 'Block'"),
        ({"tool_bodies": ["Pin", "Block"]}, "can't also be a tool body"),
    ],
)
def test_a_combine_is_refused(values: dict[str, Any], message: str) -> None:
    params = CombineBodiesParameters(
        **{
            "operation": "subtract",
            "main_body": "Block",
            "tool_bodies": ["Pin"],
            **values,
        }
    )

    with pytest.raises(InputRefused, match=message):
        rules.check_combine(params, PART)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"translate": [1, 0]}, r"translate must be \[x, y, z\]"),
        ({}, "a move by"),
        ({"translate": [1, 0, 0], "rotate": [0, 90, 0]}, "not both"),
        (
            {"translate": [1, 0, 0], "as_copy": True, "copies": 51},
            "copies must be 1 to 50",
        ),
        (
            {"translate": [1, 0, 0], "as_copy": True, "copies": 0},
            "copies must be 1 to 50",
        ),
    ],
)
def test_a_move_is_refused(values: dict[str, Any], message: str) -> None:
    with pytest.raises(InputRefused, match=message):
        rules.check_move(MoveCopyBodyParameters(bodies=["Block"], **values))


@pytest.mark.parametrize(
    "values",
    [
        {"translate": [1, 0, 0]},
        {"rotate": [0, 0, 90]},
        {"translate": [1, 0, 0], "copies": 99},
    ],
)
def test_a_move_by_one_thing_passes(values: dict[str, Any]) -> None:
    rules.check_move(MoveCopyBodyParameters(bodies=["Block"], **values))


def test_a_delete_or_keep_gives_what_goes() -> None:
    assert rules.check_delete(DeleteBodiesParameters(bodies=["pin"]), PART) == ["Pin"]
    assert rules.check_delete(
        DeleteBodiesParameters(bodies=["pin"], keep=True), PART
    ) == ["Block"]


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (DeleteBodiesParameters(bodies=["Block", "Pin"]), "delete every body"),
        (DeleteBodiesParameters(bodies=["Block", "Pin"], keep=True), "deletes nothing"),
    ],
)
def test_a_delete_of_all_or_none_is_refused(
    params: DeleteBodiesParameters, message: str
) -> None:
    with pytest.raises(InputRefused, match=message):
        rules.check_delete(params, PART)


@pytest.mark.parametrize(
    ("params", "factors"),
    [
        (ScaleBodyParameters(scale=2), (2, 2, 2)),
        (ScaleBodyParameters(scale_xyz=[1, 2, 3], about="origin"), (1, 2, 3)),
    ],
)
def test_scale_factors(params: ScaleBodyParameters, factors: tuple[float, ...]) -> None:
    assert rules.scale_factors(params) == factors


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (ScaleBodyParameters(), "Give scale"),
        (ScaleBodyParameters(scale=2, scale_xyz=[1, 1, 2]), "Give scale"),
        (ScaleBodyParameters(scale=2, about="corner"), "about must be one of"),
        (ScaleBodyParameters(scale_xyz=[1, 2]), r"scale_xyz must be \[x, y, z\]"),
        (ScaleBodyParameters(scale_xyz=[1, 0, 2]), "greater than 0"),
        (ScaleBodyParameters(scale=1), "does nothing"),
    ],
)
def test_a_scale_is_refused(params: ScaleBodyParameters, message: str) -> None:
    with pytest.raises(InputRefused, match=message):
        rules.scale_factors(params)


def test_judge_words_a_broken_rule() -> None:
    assert rules.judge("split_body", "split", PART, PART, ok=True) is None
    assert rules.judge("split_body", "make more bodies", PART, [BLOCK], ok=False) == (
        "split_body should make more bodies but the part went from 2 bodies, "
        "17000.0 mm³ to 1 bodies, 16000.0 mm³; the feature was removed."
    )


def test_combine_rules() -> None:
    merged = [BodyState("Combine1", 16500.0, BLOCK.box_min, PIN.box_max)]
    holed = [BodyState("Combine1", 15500.0, BLOCK.box_min, BLOCK.box_max)]

    far = BodyState("Far", 500.0, (60.0, 60.0, 0.0), (70.0, 70.0, 5.0))
    consumed = [BLOCK, far]

    assert rules.combine_ok("add", "Block", ["Pin"], PART, merged)[1] is True
    assert rules.combine_ok("add", "Block", ["Pin"], PART, PART)[1] is False
    assert rules.combine_ok("subtract", "Block", ["Pin"], PART, holed) == (
        "leave the main body smaller",
        True,
    )
    # The tool lay elsewhere: it is gone but the block is whole.
    assert (
        rules.combine_ok("subtract", "Block", ["Pin"], [*PART, far], consumed)[1]
        is False
    )
    assert rules.combine_ok("common", "Block", ["Pin"], PART, PART)[1] is False


def test_split_rule() -> None:
    halves = [
        BodyState("Split1[1]", 8000.0, BLOCK.box_min, BLOCK.box_max),
        BodyState("Split1[2]", 8000.0, BLOCK.box_min, BLOCK.box_max),
    ]

    assert rules.split_ok([BLOCK], halves)[1] is True
    assert rules.split_ok([BLOCK], [BLOCK])[1] is False


def test_move_and_copy_rules() -> None:
    move = MoveCopyBodyParameters(bodies=["Block"], translate=[50, 0, 0])
    copy = MoveCopyBodyParameters(
        bodies=["Block"], translate=[50, 0, 0], as_copy=True, copies=2
    )
    copies = [_moved(BLOCK, 50, "C[1]"), _moved(BLOCK, 100, "C[2]")]

    assert rules.move_ok(move, ["Block"], PART, [_moved(BLOCK, 50), PIN])[1] is True
    assert rules.move_ok(move, ["Block"], PART, PART)[1] is False
    assert rules.move_ok(copy, ["Block"], PART, [*PART, *copies]) == (
        "add 2 bodies and their volume",
        True,
    )
    assert rules.move_ok(copy, ["Block"], PART, PART)[1] is False


def test_delete_and_scale_rules() -> None:
    assert rules.delete_ok(["Pin"], PART, [BLOCK])[1] is True
    assert rules.delete_ok(["Pin"], PART, PART)[1] is False
    doubled = BodyState("Scale1", 8000.0, PIN.box_min, PIN.box_max)

    assert rules.scale_ok((2, 2, 2), ["Pin"], PART, [BLOCK, doubled]) == (
        "multiply the scaled volume by 8",
        True,
    )
    assert rules.scale_ok((2, 2, 2), ["Pin"], PART, PART)[1] is False


def test_the_measured_reply() -> None:
    reply = rules.measured_reply("Combine1", PART, [BLOCK])

    assert reply == {
        "name": "Combine1",
        "bodies_before": ["Block", "Pin"],
        "bodies_after": ["Block"],
        "body_count_before": 2,
        "body_count_after": 1,
        "volume_before_mm3": 17000.0,
        "volume_after_mm3": 16000.0,
        "volume_change_mm3": -1000.0,
    }
