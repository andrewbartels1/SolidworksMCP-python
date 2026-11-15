"""The support-level table and its entries (spec: tools/support-levels)."""

from __future__ import annotations

import pytest

from solidworks_mcp.tools.support_levels import (
    SUPPORT_LEVELS,
    Support,
    SupportLevel,
    deprecation_problems,
    planned_problems,
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


def test_a_deprecated_tool_warns_with_its_replacement() -> None:
    support = Support(SupportLevel.DEPRECATED, "use `open_model`.", since="2.1.0")

    assert support.warning() == "Deprecated: use `open_model`."
    assert support.replacement() == "open_model"


def test_a_deprecated_tool_without_a_replacement() -> None:
    support = Support(SupportLevel.DEPRECATED, "no replacement.", since="2.1.0")

    assert support.warning() == "Deprecated: no replacement."
    assert support.replacement() is None


def test_only_a_deprecated_tool_has_a_since() -> None:
    with pytest.raises(ValueError, match="needs `since`"):
        Support(SupportLevel.DEPRECATED, "no replacement.")
    with pytest.raises(ValueError, match="needs `since`"):
        Support(SupportLevel.BETA, "one input is ignored.", since="2.1.0")


def test_other_levels_name_no_replacement() -> None:
    assert Support(SupportLevel.BETA, "use `open_model`.").replacement() is None


def _deprecated(reason: str) -> Support:
    return Support(SupportLevel.DEPRECATED, reason, since="2.1.0")


def test_deprecation_problems_pass_a_good_table() -> None:
    levels = {
        "load_part": _deprecated("use `open_model`."),
        "old_example": _deprecated("no replacement."),
        "open_model": Support(SupportLevel.STABLE),
    }

    assert deprecation_problems(levels, set(levels), "2.1.0") == []


def test_deprecation_problems_need_a_registered_replacement() -> None:
    levels = {"load_part": _deprecated("use `load_anything`.")}

    assert deprecation_problems(levels, {"load_part"}, "2.1.0") == [
        "load_part: its replacement 'load_anything' is not a tool"
    ]


def test_deprecation_problems_need_a_known_reason_form() -> None:
    levels = {"load_part": _deprecated("superseded.")}

    assert deprecation_problems(levels, {"load_part"}, "2.1.0") == [
        "load_part: the reason must be 'use `<tool>`.' or 'no replacement.'"
    ]


def test_deprecation_problems_fail_at_the_next_major_release() -> None:
    levels = {
        "load_part": _deprecated("use `open_model`."),
        "open_model": Support(SupportLevel.STABLE),
    }

    assert deprecation_problems(levels, set(levels), "2.9.0") == []
    assert deprecation_problems(levels, set(levels), "3.0.0") == [
        "load_part: deprecated in 2.1.0, so remove it before 3.0.0"
    ]
    # Once it is no longer registered, the entry no longer fails.
    assert deprecation_problems(levels, {"open_model"}, "3.0.0") == []


def test_planned_problems_need_a_queue_item() -> None:
    levels = {
        "add_dimension": Support(
            SupportLevel.PLANNED, "planned in queue item 12 (the drawing pack)."
        ),
        "orphan": Support(SupportLevel.PLANNED, "no adapter implements it yet."),
        "open_model": Support(SupportLevel.STABLE),
    }

    assert planned_problems(levels) == [
        "orphan: a planned tool's reason names its queue item"
    ]
