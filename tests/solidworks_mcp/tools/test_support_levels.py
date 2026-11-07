"""The support-level table and its entries (spec: tools/support-levels)."""

from __future__ import annotations

import pytest

from solidworks_mcp.tools.support_levels import (
    SUPPORT_LEVELS,
    Support,
    SupportLevel,
)


def test_a_level_below_stable_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="reason is required"):
        Support(SupportLevel.BETA)


def test_a_stable_tool_has_no_reason() -> None:
    with pytest.raises(ValueError, match="reason is required"):
        Support(SupportLevel.STABLE, "works")


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (SupportLevel.BETA, "Beta: one input is ignored."),
        (SupportLevel.EXPERIMENTAL, "Experimental: one input is ignored."),
        (SupportLevel.PLANNED, None),
    ],
)
def test_the_warning_names_the_level_and_reason(
    level: SupportLevel, expected: str | None
) -> None:
    assert Support(level, "one input is ignored.").warning() == expected


def test_a_stable_tool_has_no_warning() -> None:
    assert Support(SupportLevel.STABLE).warning() is None


def test_every_reason_is_one_sentence() -> None:
    for name, support in SUPPORT_LEVELS.items():
        if support.reason:
            assert support.reason.endswith("."), name
            assert "\n" not in support.reason, name
