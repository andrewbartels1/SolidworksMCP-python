"""The rules ``check_drawing`` applies, as plain functions on a drawing report.

The report comes from the adapter's ``drawing_report``: the sheet's size,
each view's name, type, outline and dimension count, the title block's
values, the model type, whether a BOM is on the sheet and how many
annotations dangle. Each rule returns findings with ``rule``, ``severity``
(``error`` or ``warning``), ``message`` and, where it applies, ``view``.
A drawing passes when no finding is an error.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Finding = dict[str, Any]

#: Title-block fields the drawing standard fills, with their labels.
TITLE_BLOCK_REQUIRED = {
    "title": "title",
    "drawn_by": "drawn by",
    "revision": "revision",
}

#: Views that need no dimensions of their own.
UNDIMENSIONED_TYPES = {"detail", "sheet"}


def views_on_sheet(report: dict[str, Any]) -> list[Finding]:
    """Every view's outline lies within the sheet."""
    sheet = report.get("sheet_mm")
    if not sheet:
        return []
    found = []
    for view in report.get("views", []):
        box = view.get("outline_mm")
        if box and (
            box[0] < sheet[0]
            or box[1] < sheet[1]
            or box[2] > sheet[2]
            or box[3] > sheet[3]
        ):
            found.append(
                {
                    "rule": "view_off_sheet",
                    "severity": "error",
                    "view": view["name"],
                    "message": f"View '{view['name']}' ({list(box)} mm) runs past "
                    f"the {sheet[2]:g} x {sheet[3]:g} mm sheet; move it or rescale.",
                }
            )
    return found


def views_dimensioned(report: dict[str, Any]) -> list[Finding]:
    """Every view but isometrics and details has a dimension."""
    return [
        {
            "rule": "view_not_dimensioned",
            "severity": "warning",
            "view": view["name"],
            "message": f"View '{view['name']}' has no dimensions; use "
            "insert_model_dimensions, auto_dimension_view or add_dimension.",
        }
        for view in report.get("views", [])
        if not view.get("pictorial")
        and view.get("type") not in UNDIMENSIONED_TYPES
        and not view.get("dimensions")
    ]


def title_block_filled(report: dict[str, Any]) -> list[Finding]:
    """The title, drawn-by and revision fields have values."""
    values = report.get("title_block") or {}
    return [
        {
            "rule": "title_block_field_empty",
            "severity": "warning",
            "message": f"The title block's {label} is empty; set it with "
            f"update_title_block ({field}).",
        }
        for field, label in TITLE_BLOCK_REQUIRED.items()
        if not values.get(field)
    ]


def no_dangling(report: dict[str, Any]) -> list[Finding]:
    """No annotation has lost the geometry it was attached to."""
    count = int(report.get("dangling") or 0)
    if not count:
        return []
    return [
        {
            "rule": "dangling_annotation",
            "severity": "error",
            "message": f"{count} annotation(s) lost their reference (shown in "
            "SolidWorks' dangling colour); delete or reattach them.",
        }
    ]


def bom_present(report: dict[str, Any]) -> list[Finding]:
    """An assembly's drawing has a BOM table."""
    if report.get("model_type") != "assembly" or report.get("bom"):
        return []
    return [
        {
            "rule": "bom_missing",
            "severity": "warning",
            "message": "The drawing shows an assembly but has no BOM table; add "
            "one with insert_bom_table.",
        }
    ]


RULES: tuple[Callable[[dict[str, Any]], list[Finding]], ...] = (
    views_on_sheet,
    views_dimensioned,
    title_block_filled,
    no_dangling,
    bom_present,
)


def check(report: dict[str, Any]) -> dict[str, Any]:
    """Apply every rule: ``passed`` (no errors), ``findings`` and counts."""
    findings = [finding for rule in RULES for finding in rule(report)]
    errors = sum(1 for f in findings if f["severity"] == "error")
    return {
        "passed": errors == 0,
        "errors": errors,
        "warnings": len(findings) - errors,
        "findings": findings,
        "views": [v["name"] for v in report.get("views", [])],
    }
