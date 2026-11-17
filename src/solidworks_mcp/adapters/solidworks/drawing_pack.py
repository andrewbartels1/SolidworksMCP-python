"""The drawing pack (queue item 12): section and detail views, title block and
sheet format edits, drawing dimensions, and the facts ``check_drawing`` reads.

Every position is in sheet millimetres, as in the other drawing tools. COM
calls (argument lists from the installed type library):

- ``IDrawingDoc.ActivateView(Name)``; ``ISketchManager.CreateLine`` and
  ``CreateCircleByRadius`` in the active view's sketch;
- ``IDrawingDoc.CreateSectionViewAt5(X, Y, Z, SectionLabel, Options,
  ExcludedComponents, SectionDepth)`` and ``CreateDetailViewAt4(X, Y, Z,
  Style, Scale1, Scale2, LabelIn, Showtype, FullOutline, JaggedOutline,
  NoOutline, ShapeIntensity)`` on the selected line or circle;
- ``IModelDoc2.AddHorizontalDimension2`` / ``AddVerticalDimension2`` /
  ``AddDimension2`` / ``AddRadialDimension2`` / ``AddDiameterDimension2``
  after picking edges by sheet point (``SelectByID2`` with the null callout);
- ``IDrawingDoc.AutoDimension(Entities, HScheme, HPlacement, VScheme,
  VPlacement)`` on the active view;
- ``IDrawingDoc.SetupSheet5`` for a new format and paper size (the call
  ``generate_drawing_package`` already makes);
- ``IView.GetSketch().ModelToSketchTransform`` (sheet to view sketch space);
- ``IView.GetOutline``, ``GetDisplayDimensionCount``,
  ``IAnnotation.IsDangling`` for the drawing report.

Enum values were read from ``swconst.tlb`` (SolidWorks 2026).
"""

from __future__ import annotations

import math
import ntpath
import os
import re
from typing import Any, cast

from ...exceptions import InputRefused
from .. import sw_type_info
from ..base import AdapterResult
from .com_utils import as_list
from .documentation import _read_custom_property
from .drawing_standard import find_sheet_format
from .features import _null_callout
from .io import _as_com, _resolve_drawing_view, _view_names
from .part_features import _to_sketch

#: ``swAutodimEntities_e``, ``swAutodimScheme_e`` and placements.
AUTODIM_ENTITIES_ALL = 1
AUTODIM_SCHEMES = {"baseline": 1, "chain": 3}
AUTODIM_ABOVE, AUTODIM_RIGHT = 1, 1
#: ``swDetViewStyle_e.swDetViewSTANDARD``, ``swDetCircleShowType_e.swDetCircleCIRCLE``.
DETAIL_STANDARD, DETAIL_SHOW_CIRCLE = 0, 1
#: ``swDrawingViewTypes_e``.
VIEW_TYPES = {
    1: "sheet",
    2: "section",
    3: "detail",
    4: "projected",
    5: "auxiliary",
    6: "standard",
    7: "named",
    8: "relative",
    9: "detached",
    10: "alternate position",
}
#: ``swAnnotationType_e``.
ANNOTATION_TABLE = 14
#: ``swTableAnnotationType_e.swTableAnnotation_BillOfMaterials``.
TABLE_BOM = 2
#: ``swDwgPaperSizes_e`` and the ISO sizes, landscape, in mm.
PAPER_SIZES: dict[str, tuple[int, float, float]] = {
    "a4": (6, 297.0, 210.0),
    "a3": (8, 420.0, 297.0),
    "a2": (9, 594.0, 420.0),
    "a1": (10, 841.0, 594.0),
    "a0": (11, 1189.0, 841.0),
}
#: ``swDwgTemplates_e.swDwgTemplateCustom``: the format file is given.
TEMPLATE_CUSTOM = 12

#: Title-block field -> (whose property, property name). ``title`` is the
#: model's Description, which the ISO format reads with ``$PRPSHEET``; the
#: others are the drawing's own (see ``drawing_standard.title_block_properties``).
TITLE_BLOCK_FIELDS: dict[str, tuple[str, str]] = {
    "title": ("model", "Description"),
    "drawing_number": ("drawing", "DrawingNo"),
    "drawn_by": ("drawing", "DrawnBy"),
    "drawn_date": ("drawing", "DrawnDate"),
    "revision": ("drawing", "Revision"),
    "company": ("drawing", "COMPANYNAME"),
}

Box = tuple[float, float, float, float]


# ---- pure helpers -------------------------------------------------------------


def parse_scale(scale: str) -> tuple[float, float]:
    """``"3:1"`` -> ``(3.0, 1.0)``.

    Raises:
        ValueError: For anything but two positive numbers around a colon.
    """
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", scale)
    if not match or float(match.group(1)) <= 0 or float(match.group(2)) <= 0:
        raise ValueError(f"scale '{scale}' must look like '2:1' or '1:2'.")
    return float(match.group(1)), float(match.group(2))


def segment_crosses_box(start: list[float], end: list[float], box: Box) -> bool:
    """Whether the segment from ``start`` to ``end`` touches the box (Liang-Barsky)."""
    (x0, y0), (x1, y1) = start[:2], end[:2]
    dx, dy = x1 - x0, y1 - y0
    low, high = 0.0, 1.0
    for p, q in (
        (-dx, x0 - box[0]),
        (dx, box[2] - x0),
        (-dy, y0 - box[1]),
        (dy, box[3] - y0),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


def inside(point: list[float], box: Box) -> bool:
    """Whether ``point`` lies in ``box`` (edges included)."""
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def next_label(view_names: list[str]) -> str:
    """The first letter no section or detail view uses yet ("A" when none)."""
    used = {
        m.group(1)
        for name in view_names
        if (m := re.search(r"(?:Section|Detail) View ([A-Z])\b", name))
    }
    return next(c for c in "ABCDEFGHJKLMNPRSTUVWXYZ" if c not in used)


def paper_for(sheet_format: str, paper_size: str | None) -> str:
    """The paper size: given, else the format name's (``a2 - iso`` -> ``a2``).

    Raises:
        ValueError: When neither names one of :data:`PAPER_SIZES`.
    """
    if paper_size:
        size = paper_size.strip().lower()
    else:
        stem = ntpath.basename(sheet_format).lower()  # a Windows path, on any OS
        size = next((s for s in PAPER_SIZES if stem.startswith(s)), "")
    if size not in PAPER_SIZES:
        raise InputRefused(
            f"paper_size must be one of {', '.join(PAPER_SIZES)}; it can't be "
            f"read from the format name '{sheet_format}'."
        )
    return size


def _mm(box: Any) -> Box | None:
    """A COM outline in metres -> mm, or ``None`` when unreadable."""
    values = as_list(box)
    if len(values) < 4 or not all(isinstance(v, (int, float)) for v in values[:4]):
        return None
    return cast(Box, tuple(round(float(v) * 1000.0, 3) for v in values[:4]))


# ---- the adapter mixin --------------------------------------------------------


class SolidWorksDrawingPackMixin:
    """Section and detail views, title block and format, dimensions, report."""

    def _pack_run(self, operation: str, build: Any) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` on the COM thread when the active document is a drawing."""
        adapter: Any = self
        guard = adapter._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        return cast(
            "AdapterResult[dict[str, Any]]",
            adapter._handle_com_operation(operation, build),
        )

    def _pack_drawing(self) -> Any:
        """The active document as an ``IDrawingDoc``."""
        adapter: Any = self
        return sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")

    def _pack_view(self, drawing: Any, name: str) -> Any:
        """The view called ``name``.

        Raises:
            LookupError: Listing the drawing's views.
        """
        view = _resolve_drawing_view(self, drawing, name)
        if view is None:
            names = _view_names(self, drawing)
            raise LookupError(
                f"No view named '{name}' on the sheet; it has "
                f"{', '.join(names) or 'no views'}."
            )
        return view

    def _pack_sheet_mm(self, drawing: Any) -> Box | None:
        """The sheet's rectangle in mm."""
        adapter: Any = self
        return _mm(adapter._sheet_bounds(drawing))

    def _pack_outline(self, view: Any) -> Box | None:
        """A view's outline on the sheet, mm."""
        adapter: Any = self
        return _mm(adapter._attempt(lambda: view.GetOutline(), default=None))

    def _pack_on_sheet(self, drawing: Any, position: list[float]) -> None:
        """Refuse a position off the sheet.

        Raises:
            ValueError: Naming the sheet's size.
        """
        sheet = self._pack_sheet_mm(drawing)
        if sheet is not None and not inside(position, sheet):
            raise InputRefused(
                f"position {list(position)} mm is off the sheet "
                f"({sheet[2]:g} x {sheet[3]:g} mm)."
            )

    def _pack_to_view(self, view: Any, point: list[float]) -> tuple[float, float]:
        """A sheet point (mm) in the view's sketch space (m).

        A drawing's document space is the sheet, and the view's sketch maps it
        into its own space (``ISketch.ModelToSketchTransform``), scale and
        offset included: the same mapping the hole positions use. (The first
        live run used ``IView.GetXform`` instead and put the detail circle in
        empty space, 2026-11-16.)

        Raises:
            RuntimeError: When the view's sketch can't be read.
        """
        adapter: Any = self
        sketch = adapter._attempt(lambda: view.GetSketch(), default=None)
        if sketch is None:
            raise RuntimeError(
                "The view's sketch couldn't be read to place the entity."
            )
        sketch = sw_type_info.flagged(sketch, "ISketch")
        x, y, _ = _to_sketch(
            adapter, sketch, [point[0] / 1000.0, point[1] / 1000.0, 0.0]
        )
        return x, y

    def _pack_radius(self, view: Any, center: list[float], radius: float) -> float:
        """A radius on the sheet (mm) as a length in the view's sketch (m)."""
        cx, cy = self._pack_to_view(view, center)
        ex, ey = self._pack_to_view(view, [center[0] + radius, center[1]])
        return math.hypot(ex - cx, ey - cy)

    def _pack_new_view(self, created: Any, before: list[str]) -> dict[str, Any]:
        """The created view's name and outline."""
        adapter: Any = self
        view = _as_com(adapter, created, "IView")
        name = adapter._attempt(lambda: view.GetName2(), default=None)
        drawing = self._pack_drawing()
        return {
            "name": str(name) if name else None,
            "outline_mm": self._pack_outline(view),
            "views_before": len(before),
            "views_after": len(_view_names(adapter, drawing)),
        }

    def _pack_discard(self, entity: Any) -> None:
        """Delete a sketch line or circle left over from a failed view."""
        adapter: Any = self
        model = adapter.currentModel
        adapter._attempt(lambda: model.ClearSelection2(True), default=None)
        if adapter._select_sketch_entity(entity, append=False):
            adapter._attempt(lambda: model.EditDelete(), default=None)

    async def create_section_view(
        self,
        view: str,
        line_start: list[float],
        line_end: list[float],
        position: list[float],
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """A section view cut along a line across ``view``.

        Args:
            view: The parent view's name.
            line_start: ``[x, y]`` sheet mm where the section line starts.
            line_end: ``[x, y]`` sheet mm where it ends.
            position: ``[x, y]`` sheet mm for the new view's centre.
            label: The section's letter; the next free one when ``None``.

        Returns:
            The new view's name, label and outline.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = self._pack_drawing()
            parent = self._pack_view(drawing, view)
            outline = self._pack_outline(parent)
            if outline is not None and not segment_crosses_box(
                line_start, line_end, outline
            ):
                raise InputRefused(
                    f"The section line {list(line_start)} - {list(line_end)} mm "
                    f"doesn't cross view '{view}' (its outline is {list(outline)} mm)."
                )
            self._pack_on_sheet(drawing, position)
            before = _view_names(adapter, drawing)
            letter = label or next_label(before)
            drawing.ActivateView(view)
            start = self._pack_to_view(parent, line_start)
            end = self._pack_to_view(parent, line_end)
            line = adapter.currentModel.SketchManager.CreateLine(*start, 0.0, *end, 0.0)
            if line is None:
                raise RuntimeError(f"The section line couldn't be drawn in '{view}'.")
            adapter._attempt(lambda: adapter.currentModel.ClearSelection2(True), None)
            adapter._select_sketch_entity(line, append=False)
            created = drawing.CreateSectionViewAt5(
                position[0] / 1000.0, position[1] / 1000.0, 0.0, letter, 0, None, 0.0
            )
            if created is None:
                self._pack_discard(line)
                raise RuntimeError(
                    f"CreateSectionViewAt5 made no section view of '{view}'."
                )
            return {
                "label": letter,
                "parent": view,
                **self._pack_new_view(created, before),
            }

        return self._pack_run("create_section_view", build)

    async def create_detail_view(
        self,
        view: str,
        center: list[float],
        radius: float,
        position: list[float],
        scale: str = "2:1",
        label: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """A detail view of the circle at ``center`` in ``view``.

        Args:
            view: The parent view's name.
            center: ``[x, y]`` sheet mm, inside the view.
            radius: The circle's radius on the sheet, mm.
            position: ``[x, y]`` sheet mm for the new view's centre.
            scale: The detail's scale, e.g. ``"3:1"``.
            label: The detail's letter; the next free one when ``None``.

        Returns:
            The new view's name, label, scale and outline.
        """
        adapter: Any = self
        top, bottom = parse_scale(scale)

        def build() -> dict[str, Any]:
            drawing = self._pack_drawing()
            parent = self._pack_view(drawing, view)
            outline = self._pack_outline(parent)
            if outline is not None and not inside(center, outline):
                raise InputRefused(
                    f"The detail centre {list(center)} mm isn't inside view "
                    f"'{view}' (its outline is {list(outline)} mm)."
                )
            self._pack_on_sheet(drawing, position)
            before = _view_names(adapter, drawing)
            letter = label or next_label(before)
            drawing.ActivateView(view)
            cx, cy = self._pack_to_view(parent, center)
            r = self._pack_radius(parent, center, radius)
            circle = adapter.currentModel.SketchManager.CreateCircleByRadius(
                cx, cy, 0.0, r
            )
            if circle is None:
                raise RuntimeError(f"The detail circle couldn't be drawn in '{view}'.")
            adapter._attempt(lambda: adapter.currentModel.ClearSelection2(True), None)
            adapter._select_sketch_entity(circle, append=False)
            created = drawing.CreateDetailViewAt4(
                position[0] / 1000.0,
                position[1] / 1000.0,
                0.0,
                DETAIL_STANDARD,
                top,
                bottom,
                letter,
                DETAIL_SHOW_CIRCLE,
                False,
                False,
                False,
                0,
            )
            if created is None:
                self._pack_discard(circle)
                raise RuntimeError(f"CreateDetailViewAt4 made no detail of '{view}'.")
            return {
                "label": letter,
                "parent": view,
                "scale": f"{top:g}:{bottom:g}",
                **self._pack_new_view(created, before),
            }

        return self._pack_run("create_detail_view", build)

    async def add_dimension(
        self,
        dimension_type: str,
        entity1_point: list[float],
        position: list[float],
        entity2_point: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """One dimension on the entities picked at sheet points.

        Args:
            dimension_type: horizontal, vertical, aligned, radial, diameter
                or angular.
            entity1_point: ``[x, y]`` sheet mm on the first edge or vertex.
            position: ``[x, y]`` sheet mm for the dimension's text.
            entity2_point: The second entity, for linear and angular types.

        Returns:
            The dimension's name and value (mm, degrees for angular).
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            self._pack_on_sheet(self._pack_drawing(), position)
            adapter._attempt(lambda: model.ClearSelection2(True), None)
            for index, point in enumerate([entity1_point, entity2_point]):
                if point is None:
                    continue
                if not self._pack_pick(point, append=index > 0):
                    raise InputRefused(
                        f"Nothing to dimension at {list(point)} mm on the sheet; "
                        "give a point on a view's edge or vertex."
                    )
            x, y = position[0] / 1000.0, position[1] / 1000.0
            create = {
                "horizontal": model.AddHorizontalDimension2,
                "vertical": model.AddVerticalDimension2,
                "aligned": model.AddDimension2,
                "angular": model.AddDimension2,
                "radial": model.AddRadialDimension2,
                "diameter": model.AddDiameterDimension2,
            }[dimension_type]
            display = create(x, y, 0.0)
            adapter._attempt(lambda: model.ClearSelection2(True), None)
            if display is None:
                raise RuntimeError(
                    f"SolidWorks added no {dimension_type} dimension to the picked "
                    "entities; check they suit that type."
                )
            disp = sw_type_info.flagged(display, "IDisplayDimension")
            dimension = sw_type_info.flagged(disp.GetDimension2(0), "IDimension")
            raw = float(dimension.SystemValue)
            angular = dimension_type == "angular"
            value = raw * 180.0 / math.pi if angular else raw * 1000.0
            return {
                "name": adapter._attempt(lambda: dimension.FullName, default=None),
                "dimension_type": dimension_type,
                "value": round(value, 4),
                "units": "deg" if angular else "mm",
            }

        return self._pack_run("add_dimension", build)

    def _pack_pick(self, point: list[float], append: bool) -> bool:
        """Select the edge (else the vertex) at a sheet point."""
        adapter: Any = self
        model = adapter.currentModel
        x, y = point[0] / 1000.0, point[1] / 1000.0
        for kind in ("EDGE", "VERTEX"):
            picked = adapter._attempt(
                lambda k=kind: model.Extension.SelectByID2(
                    "", k, x, y, 0.0, append, 0, _null_callout(), 0
                ),
                default=False,
            )
            if picked:
                return True
        return False

    async def auto_dimension_view(
        self, view: str, scheme: str = "baseline"
    ) -> AdapterResult[dict[str, Any]]:
        """SolidWorks' auto-dimension on one view, counted before and after.

        Args:
            view: The view's name.
            scheme: ``baseline`` or ``chain``, both directions.

        Returns:
            The view, the scheme, and the dimensions before, after and added.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = self._pack_drawing()
            target = self._pack_view(drawing, view)
            before = adapter._view_dimension_count(target)
            drawing.ActivateView(view)
            model = adapter.currentModel
            adapter._attempt(lambda: model.ClearSelection2(True), None)
            adapter._attempt(
                lambda: model.Extension.SelectByID2(
                    view, "DRAWINGVIEW", 0.0, 0.0, 0.0, False, 0, _null_callout(), 0
                ),
                None,
            )
            code = AUTODIM_SCHEMES[scheme]
            status = drawing.AutoDimension(
                AUTODIM_ENTITIES_ALL, code, AUTODIM_ABOVE, code, AUTODIM_RIGHT
            )
            adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), None)
            after = adapter._view_dimension_count(self._pack_view(drawing, view))
            if after <= before:
                raise RuntimeError(
                    f"AutoDimension added no dimension to '{view}' (status {status})."
                )
            return {
                "view": view,
                "scheme": scheme,
                "dimensions_before": before,
                "dimensions_after": after,
                "added": after - before,
            }

        return self._pack_run("auto_dimension_view", build)

    async def update_sheet_format(
        self, sheet_format: str, paper_size: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        """Change the active sheet's format and paper size, keeping its views.

        Args:
            sheet_format: A format name (``a2 - iso``) or a ``.slddrt`` path.
            paper_size: a4 to a0; read from the format name when ``None``.

        Returns:
            The format's path, the paper size and the views before and after.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            size = paper_for(sheet_format, paper_size)
            path = self._pack_format_path(sheet_format)
            drawing = self._pack_drawing()
            before = _view_names(adapter, drawing)
            sheet = _as_com(adapter, drawing.GetCurrentSheet(), "ISheet")
            props = as_list(adapter._attempt(lambda: sheet.GetProperties2(), None))
            scale = (props[2], props[3]) if len(props) >= 5 else (1.0, 1.0)
            first_angle = bool(props[4]) if len(props) >= 5 else False
            name = adapter._attempt(lambda: sheet.GetName(), default="Sheet1")
            code, width, height = PAPER_SIZES[size]
            if not drawing.SetupSheet5(
                name,
                code,
                TEMPLATE_CUSTOM,
                scale[0],
                scale[1],
                first_angle,
                path,
                width / 1000.0,
                height / 1000.0,
                "Default",
                True,
            ):
                raise RuntimeError(f"SetupSheet5 refused the sheet format {path}.")
            adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), None)
            after = _view_names(adapter, drawing)
            if sorted(after) != sorted(before):
                raise RuntimeError(
                    f"The views changed with the format: {before} became {after}."
                )
            return {
                "sheet_format": path,
                "paper_size": size,
                "sheet_mm": self._pack_sheet_mm(drawing),
                "views": after,
            }

        return self._pack_run("update_sheet_format", build)

    def _pack_format_path(self, sheet_format: str) -> str:
        """A format name or path -> an existing ``.slddrt`` path.

        Raises:
            LookupError: When no format of that name is found.
        """
        if os.path.isfile(sheet_format):
            return sheet_format
        name = (
            sheet_format
            if sheet_format.lower().endswith(".slddrt")
            else (f"{sheet_format}.slddrt")
        )
        found = find_sheet_format(self, name)
        if not found:
            raise LookupError(
                f"No sheet format '{name}' in SolidWorks' sheet format folders "
                r"or under C:\ProgramData\SOLIDWORKS; give a .slddrt path."
            )
        return found

    async def update_title_block(
        self, fields: dict[str, str]
    ) -> AdapterResult[dict[str, Any]]:
        """Write title-block fields to the properties the sheet format reads.

        ``title`` goes to the drawn model's Description (the ISO format reads
        it with ``$PRPSHEET``); the rest are the drawing's own properties.
        Fields not given keep their values.

        Args:
            fields: Field name (a key of :data:`TITLE_BLOCK_FIELDS`) -> value.

        Returns:
            Each field with the property it was written to.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = self._pack_drawing()
            written: dict[str, dict[str, str]] = {}
            for field, value in fields.items():
                owner, prop = TITLE_BLOCK_FIELDS[field]
                doc = (
                    adapter.currentModel
                    if owner == "drawing"
                    else self._pack_model(drawing)
                )
                manager = doc.Extension.CustomPropertyManager("")
                manager.Add3(prop, 30, value, 2)  # text, replace the value
                written[field] = {"property": prop, "on": owner, "value": value}
            adapter._attempt(lambda: adapter.currentModel.ForceRebuild3(False), None)
            return {"fields": written}

        return self._pack_run("update_title_block", build)

    def _pack_model(self, drawing: Any) -> Any:
        """The model the drawing's first view shows.

        Raises:
            LookupError: When the drawing has no model view.
        """
        adapter: Any = self
        for name in _view_names(adapter, drawing):
            view = _resolve_drawing_view(adapter, drawing, name)
            doc = adapter._attempt(lambda v=view: v.ReferencedDocument, default=None)
            if doc is not None:
                return doc
        raise LookupError("The drawing has no view of a model to take the title from.")

    async def drawing_report(self) -> AdapterResult[dict[str, Any]]:
        """What ``check_drawing`` judges: views, sheet, title block, BOM, dangling.

        Returns:
            ``sheet_mm``; ``views`` (name, type, outline, dimensions);
            ``title_block`` (title, drawn_by, revision); ``model_type``;
            ``bom``; ``dangling``.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            drawing = self._pack_drawing()
            views = []
            for name in _view_names(adapter, drawing):
                view = _resolve_drawing_view(adapter, drawing, name)
                kind = adapter._attempt(lambda v=view: v.Type, default=None)
                views.append(
                    {
                        "name": name,
                        "type": VIEW_TYPES.get(kind, "unknown"),
                        "pictorial": adapter._pictorial(view),
                        "outline_mm": self._pack_outline(view),
                        "dimensions": adapter._view_dimension_count(view),
                    }
                )
            bom, dangling = self._pack_annotations(drawing)
            model = adapter._attempt(lambda: self._pack_model(drawing), default=None)
            model_type = adapter._attempt(lambda: model.GetType(), default=None)
            return {
                "sheet_mm": self._pack_sheet_mm(drawing),
                "views": views,
                "title_block": self._pack_title_values(model),
                "model_type": {1: "part", 2: "assembly"}.get(model_type),
                "bom": bom,
                "dangling": dangling,
            }

        return self._pack_run("drawing_report", build)

    def _pack_annotations(self, drawing: Any) -> tuple[bool, int]:
        """Whether a BOM table is on the sheet, and how many annotations dangle."""
        adapter: Any = self
        bom, dangling = False, 0
        view = adapter._attempt(lambda: drawing.GetFirstView(), default=None)
        while view is not None:
            v = sw_type_info.flagged(view, "IView")
            ann = adapter._attempt(lambda v=v: v.GetFirstAnnotation3(), default=None)
            guard = 0
            while ann is not None and guard < 5000:
                guard += 1
                an = sw_type_info.flagged(ann, "IAnnotation")
                if adapter._attempt(lambda a=an: a.IsDangling(), default=False):
                    dangling += 1
                if adapter._attempt(lambda a=an: a.GetType(), None) == ANNOTATION_TABLE:
                    table = adapter._attempt(
                        lambda a=an: a.GetSpecificAnnotation(), None
                    )
                    kind = adapter._attempt(lambda t=table: t.Type, default=None)
                    bom = bom or kind == TABLE_BOM
                ann = adapter._attempt(lambda a=an: a.GetNext3(), default=None)
            view = adapter._attempt(lambda v=v: v.GetNextView(), default=None)
        return bom, dangling

    def _pack_title_values(self, model: Any) -> dict[str, str | None]:
        """The title block's title, drawn by and revision, as written."""
        adapter: Any = self

        def read(doc: Any, prop: str) -> str | None:
            manager = adapter._attempt(
                lambda: doc.Extension.CustomPropertyManager(""), default=None
            )
            if manager is None:
                return None
            return _read_custom_property(adapter, manager, prop)[0] or None

        drawing = adapter.currentModel
        return {
            "title": read(model, "Description") if model is not None else None,
            "drawn_by": read(drawing, "DrawnBy"),
            "revision": read(drawing, "Revision"),
        }
