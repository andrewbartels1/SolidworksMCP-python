"""A helix's numbers (spec tools/helix): two values define it, the third is worked out."""

from __future__ import annotations

import math
import re

import pytest

from solidworks_mcp.adapters.helix_geometry import helix_length, helix_values
from solidworks_mcp.exceptions import InputRefused


@pytest.mark.parametrize(
    ("defined_by", "given", "expected"),
    [
        ("height_and_pitch", (48, 6, None), (48, 6, 8)),
        ("height_and_revolutions", (30, None, 5), (30, 6, 5)),
        ("pitch_and_revolutions", (None, 2, 4.5), (9, 2, 4.5)),
        ("spiral", (None, 5, 3), (0, 5, 3)),
    ],
)
def test_the_third_value_is_worked_out(
    defined_by: str, given: tuple[float | None, ...], expected: tuple[float, ...]
) -> None:
    assert helix_values(defined_by, *given) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("defined_by", "given", "message"),
    [
        ("by_magic", (1, 1, 1), "is not one of"),
        ("height_and_pitch", (48, None, None), "needs pitch"),
        ("spiral", (None, 5, 0), "revolutions must be greater than 0 (got 0)"),
        ("height_and_revolutions", (-1, None, 3), "height must be greater than 0"),
    ],
)
def test_a_missing_or_impossible_value_is_refused(
    defined_by: str, given: tuple[float | None, ...], message: str
) -> None:
    with pytest.raises(InputRefused, match=re.escape(message)):
        helix_values(defined_by, *given)


def test_a_straight_helix_is_its_turns_unrolled() -> None:
    # The probe read 504.924 mm for 8 turns of a 20 mm helix at pitch 6; the
    # formula is within 0.01% of it (504.941).
    assert helix_length(20, 6, 8) == pytest.approx(504.924, rel=1e-4)


def test_a_tapered_helix_uses_its_mean_diameter() -> None:
    narrow = 20 - 30 * math.tan(math.radians(5))
    assert helix_length(20, 6, 5, height=30, taper_angle=5) == pytest.approx(
        5 * math.hypot(math.pi * narrow, 6)
    )
    wide = helix_length(20, 6, 5, height=30, taper_angle=5, taper_outward=True)
    assert wide > helix_length(20, 6, 5)


def test_a_spiral_grows_by_its_pitch_each_turn() -> None:
    assert helix_length(20, 5, 3, spiral=True) == pytest.approx(math.pi * 3 * 35)
