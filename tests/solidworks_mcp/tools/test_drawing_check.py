"""The drawing check's rules, on plain reports. Spec: tools/drawing-check."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.tools.drawing_check import check


def _report(**changes: Any) -> dict[str, Any]:
    report = {
        "sheet_mm": (0.0, 0.0, 420.0, 297.0),
        "views": [
            {
                "name": "Front",
                "type": "standard",
                "pictorial": False,
                "outline_mm": (20.0, 150.0, 120.0, 230.0),
                "dimensions": 3,
            },
            {
                "name": "Iso",
                "type": "named",
                "pictorial": True,
                "outline_mm": (250.0, 150.0, 350.0, 230.0),
                "dimensions": 0,
            },
            {
                "name": "Detail View A (2 : 1)",
                "type": "detail",
                "pictorial": False,
                "outline_mm": None,
                "dimensions": 0,
            },
        ],
        "title_block": {"title": "Plate", "drawn_by": "AB", "revision": "A"},
        "model_type": "part",
        "bom": False,
        "dangling": 0,
    }
    report.update(changes)
    return report


def test_a_finished_drawing_passes_with_no_findings() -> None:
    verdict = check(_report())

    assert verdict == {
        "passed": True,
        "errors": 0,
        "warnings": 0,
        "findings": [],
        "views": ["Front", "Iso", "Detail View A (2 : 1)"],
    }


def test_a_view_off_the_sheet_fails() -> None:
    report = _report()
    report["views"][0]["outline_mm"] = (380.0, 150.0, 480.0, 230.0)

    verdict = check(report)

    assert verdict["passed"] is False
    assert verdict["findings"][0]["rule"] == "view_off_sheet"
    assert verdict["findings"][0]["view"] == "Front"


def test_warnings_do_not_fail_the_drawing() -> None:
    report = _report(model_type="assembly", title_block={"title": "Plate"})
    report["views"][0]["dimensions"] = 0

    verdict = check(report)

    assert verdict["passed"] is True
    assert [f["rule"] for f in verdict["findings"]] == [
        "view_not_dimensioned",
        "title_block_field_empty",
        "title_block_field_empty",
        "bom_missing",
    ]
    assert verdict["warnings"] == 4


def test_dangling_annotations_fail() -> None:
    verdict = check(_report(dangling=2))

    assert verdict["passed"] is False
    assert "2 annotation(s) lost their reference" in verdict["findings"][0]["message"]


def test_an_assembly_with_a_bom_and_no_sheet_size() -> None:
    verdict = check(_report(model_type="assembly", bom=True, sheet_mm=None))

    assert verdict["findings"] == []
