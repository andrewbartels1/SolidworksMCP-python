"""The rules for drawing sheets (queue item 37). Spec: tools/drawing-sheets."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters import sheet_rules as rules
from solidworks_mcp.exceptions import InputRefused


def test_an_entry_from_the_sheet_properties() -> None:
    props = (8.0, 12.0, 1.0, 2.0, 1.0, 0.42, 0.297, 1.0)

    assert rules.sheet_entry("Details", props, True) == {
        "name": "Details",
        "active": True,
        "paper_mm": [420.0, 297.0],
        "scale": "1:2",
        "projection": "first",
    }


def test_an_unreadable_sheet_gives_its_name_only() -> None:
    assert rules.sheet_entry("Sheet1", None, False) == {
        "name": "Sheet1",
        "active": False,
    }


def test_a_sheet_found_ignoring_case() -> None:
    assert rules.resolve_sheet(["Sheet1", "Details"], " details ") == "Details"


def test_an_unknown_sheet_lists_them() -> None:
    with pytest.raises(InputRefused, match="has Sheet1, Details"):
        rules.resolve_sheet(["Sheet1", "Details"], "Nope")
    with pytest.raises(InputRefused, match="has none"):
        rules.resolve_sheet([], "Nope")


@pytest.mark.parametrize(
    ("name", "projection", "words"),
    [
        (" ", None, "needs a name"),
        ("SHEET1", None, "has a sheet named 'SHEET1' already"),
        ("Details", "second", "projection must be"),
    ],
)
def test_bad_new_sheets_are_refused(
    name: str, projection: str | None, words: str
) -> None:
    with pytest.raises(InputRefused, match=words):
        rules.check_new_sheet(["Sheet1"], name, projection)


def test_a_good_new_sheet_passes() -> None:
    rules.check_new_sheet(["Sheet1"], "Details", "third")
