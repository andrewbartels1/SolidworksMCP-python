"""The mock adapter's drawing pack: the real adapter's refusals and replies.

Views get an outline on an A3 sheet, so positions, section lines and picks
are checked the way the real adapter checks them; the rules themselves come
from :mod:`.solidworks.drawing_pack`.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .base import AdapterResult, AdapterResultStatus
from .solidworks.drawing_pack import (
    PAPER_SIZES,
    TITLE_BLOCK_FIELDS,
    Box,
    inside,
    next_label,
    paper_for,
    parse_scale,
    segment_crosses_box,
)


def _error(message: str) -> AdapterResult[dict[str, Any]]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _ok(data: dict[str, Any]) -> AdapterResult[dict[str, Any]]:
    """A success result."""
    return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


class MockDrawingPackMixin:
    """Section and detail views, dimensions, format, title block, report."""

    _drawing_views: list[str]

    def _pack_state(self) -> dict[str, Any]:
        """The mock drawing's sheet, outlines, title block and dimensions."""
        if not hasattr(self, "_pack"):
            self._pack: dict[str, Any] = {
                "paper": "a3",
                "format": "a3 - iso.slddrt",
                "outlines": {},
                "title_block": {},
            }
        return self._pack

    def _pack_guard(self, operation: str) -> AdapterResult[dict[str, Any]] | None:
        """An error unless a drawing is active."""
        guard = self._mock_doc_error({"Drawing"}, operation)  # type: ignore[attr-defined]
        return guard

    def _pack_outline(self, name: str) -> Box:
        """A view's outline: a 100 x 80 mm box per view, left to right."""
        outlines = self._pack_state()["outlines"]
        if name not in outlines:
            index = (
                self._drawing_views.index(name) if name in self._drawing_views else 0
            )
            left = 20.0 + 110.0 * (index % 3)
            bottom = 150.0 - 100.0 * (index // 3)
            outlines[name] = (left, bottom, left + 100.0, bottom + 80.0)
        return outlines[name]

    def _pack_sheet(self) -> Box:
        """The sheet's rectangle, mm."""
        _, width, height = PAPER_SIZES[self._pack_state()["paper"]]
        return (0.0, 0.0, width, height)

    def _pack_unknown(self, view: str) -> AdapterResult[dict[str, Any]] | None:
        """An error naming the views when ``view`` isn't one."""
        if view in self._drawing_views:
            return None
        return _error(
            f"No view named '{view}' on the sheet; it has "
            f"{', '.join(self._drawing_views) or 'no views'}."
        )

    def _pack_off_sheet(self, position: list[float]) -> AdapterResult[Any] | None:
        """An error when ``position`` is off the sheet."""
        sheet = self._pack_sheet()
        if inside(position, sheet):
            return None
        return _error(
            f"position {list(position)} mm is off the sheet "
            f"({sheet[2]:g} x {sheet[3]:g} mm)."
        )

    def _pack_add_view(self, name: str, position: list[float]) -> Box:
        """Append a derived view, centred at ``position``."""
        self._drawing_views.append(name)
        box = (position[0] - 40, position[1] - 30, position[0] + 40, position[1] + 30)
        self._pack_state()["outlines"][name] = box
        return box

    async def create_section_view(
        self,
        view: str,
        line_start: list[float],
        line_end: list[float],
        position: list[float],
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock section view: a new view named ``Section View X-X``."""
        refused = self._pack_guard("create_section_view") or self._pack_unknown(view)
        if refused:
            return refused
        outline = self._pack_outline(view)
        if not segment_crosses_box(line_start, line_end, outline):
            return _error(
                f"The section line {list(line_start)} - {list(line_end)} mm "
                f"doesn't cross view '{view}' (its outline is {list(outline)} mm)."
            )
        off = self._pack_off_sheet(position)
        if off:
            return off
        before = len(self._drawing_views)
        letter = label or next_label(self._drawing_views)
        name = f"Section View {letter}-{letter}"
        box = self._pack_add_view(name, position)
        return _ok(
            {
                "label": letter,
                "parent": view,
                "name": name,
                "outline_mm": box,
                "views_before": before,
                "views_after": len(self._drawing_views),
            }
        )

    async def create_detail_view(
        self,
        view: str,
        center: list[float],
        radius: float,
        position: list[float],
        scale: str = "2:1",
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock detail view: a new view named ``Detail View X (s:s)``."""
        top, bottom = parse_scale(scale)
        refused = self._pack_guard("create_detail_view") or self._pack_unknown(view)
        if refused:
            return refused
        outline = self._pack_outline(view)
        if not inside(center, outline):
            return _error(
                f"The detail centre {list(center)} mm isn't inside view "
                f"'{view}' (its outline is {list(outline)} mm)."
            )
        off = self._pack_off_sheet(position)
        if off:
            return off
        before = len(self._drawing_views)
        letter = label or next_label(self._drawing_views)
        ratio = f"{top:g}:{bottom:g}"
        name = f"Detail View {letter} ({ratio})"
        box = self._pack_add_view(name, position)
        return _ok(
            {
                "label": letter,
                "parent": view,
                "scale": ratio,
                "name": name,
                "outline_mm": box,
                "views_before": before,
                "views_after": len(self._drawing_views),
            }
        )

    async def add_dimension(
        self,
        dimension_type: str,
        entity1_point: list[float],
        position: list[float],
        entity2_point: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Mock dimension, measured between the points (fixed for circles)."""
        refused = self._pack_guard("add_dimension") or self._pack_off_sheet(position)
        if refused:
            return refused
        points = [p for p in (entity1_point, entity2_point) if p is not None]
        owner = None
        for point in points:
            owner = next(
                (
                    v
                    for v in self._drawing_views
                    if inside(point, self._pack_outline(v))
                ),
                None,
            )
            if owner is None:
                return _error(
                    f"Nothing to dimension at {list(point)} mm on the sheet; "
                    "give a point on a view's edge or vertex."
                )
        first, second = points[0], points[-1]
        values = {
            "horizontal": abs(second[0] - first[0]),
            "vertical": abs(second[1] - first[1]),
            "aligned": math.dist(first, second),
            "angular": 90.0,
            "radial": 3.0,
            "diameter": 6.0,
        }
        counts = self.__dict__.setdefault("_view_dimensions", {})
        counts[owner] = counts.get(owner, 0) + 1
        return _ok(
            {
                "name": f"RD{sum(counts.values())}@{owner}",
                "dimension_type": dimension_type,
                "value": round(values[dimension_type], 4),
                "units": "deg" if dimension_type == "angular" else "mm",
            }
        )

    async def auto_dimension_view(
        self, view: str, scheme: str = "baseline"
    ) -> AdapterResult[dict[str, Any]]:
        """Mock auto-dimension: two more dimensions on the view."""
        refused = self._pack_guard("auto_dimension_view") or self._pack_unknown(view)
        if refused:
            return refused
        counts = self.__dict__.setdefault("_view_dimensions", {})
        before = counts.get(view, 0)
        counts[view] = before + 2
        return _ok(
            {
                "view": view,
                "scheme": scheme,
                "dimensions_before": before,
                "dimensions_after": before + 2,
                "added": 2,
            }
        )

    async def update_sheet_format(
        self, sheet_format: str, paper_size: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Mock format change: ``a0`` to ``a4`` ISO or ANSI names exist."""
        refused = self._pack_guard("update_sheet_format")
        if refused:
            return refused
        try:
            size = paper_for(sheet_format, paper_size)
        except ValueError as exc:
            return _error(str(exc))
        name = (
            sheet_format
            if sheet_format.endswith(".slddrt")
            else (f"{sheet_format}.slddrt")
        )
        if not re.fullmatch(r"a[0-4] - (iso|ansi)\.slddrt", name.lower()):
            return _error(
                f"No sheet format '{name}' in SolidWorks' sheet format folders "
                r"or under C:\ProgramData\SOLIDWORKS; give a .slddrt path."
            )
        state = self._pack_state()
        state.update(paper=size, format=name)
        return _ok(
            {
                "sheet_format": name,
                "paper_size": size,
                "sheet_mm": self._pack_sheet(),
                "views": list(self._drawing_views),
            }
        )

    async def update_title_block(
        self, fields: dict[str, str]
    ) -> AdapterResult[dict[str, Any]]:
        """Mock title block: the fields are kept for ``drawing_report``."""
        refused = self._pack_guard("update_title_block")
        if refused:
            return refused
        self._pack_state()["title_block"].update(fields)
        return _ok(
            {
                "fields": {
                    field: {
                        "property": TITLE_BLOCK_FIELDS[field][1],
                        "on": TITLE_BLOCK_FIELDS[field][0],
                        "value": value,
                    }
                    for field, value in fields.items()
                }
            }
        )

    async def drawing_report(self) -> AdapterResult[dict[str, Any]]:
        """Mock report from the drawing's state."""
        refused = self._pack_guard("drawing_report")
        if refused:
            return refused
        counts = self.__dict__.get("_view_dimensions", {})
        title = self._pack_state()["title_block"]
        return _ok(
            {
                "sheet_mm": self._pack_sheet(),
                "views": [
                    {
                        "name": name,
                        "type": "detail" if name.startswith("Detail") else "standard",
                        "pictorial": "iso" in name.lower(),
                        "outline_mm": self._pack_outline(name),
                        "dimensions": counts.get(name, 0),
                    }
                    for name in self._drawing_views
                ],
                "title_block": {
                    key: title.get(key) for key in ("title", "drawn_by", "revision")
                },
                "model_type": "part",
                "bom": False,
                "dangling": 0,
            }
        )
