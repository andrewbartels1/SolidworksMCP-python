"""Standard A3 drawing generation for the PyWin32 adapter.

Implements an A3 ISO drafting standard on SolidWorks:

* **Sheet** - A3 landscape 420 x 297 mm with the SolidWorks ``a3 - iso``
  sheet format (zoned border, ISO title block). Working area x 15-405,
  y 15-282 mm; the title block area x 218-412, y 8-72 mm is kept clear.
* **Title block** - TITLE from the model's ``Description``, DWG NO. from the
  drawing file name (saved as the drawing number), MATERIAL / WEIGHT linked to
  the model's real material and mass, DRAWN by/date, revision and company from
  drawing properties; scale, sheet n of N and size are automatic.
* **Views** - third-angle front, plan and side view plus an isometric, each in
  its own cell, at the largest standard scale where the part, its dimension
  rows and its caption fit (cells sized from the part, so it fills the sheet).
  Each view gets a bold capital caption with its name, e.g. ``FRONT VIEW``.
* **Dimensions** - imported from the model, each shown once, laid out in rows
  (first 8 mm out, rows 7 mm, columns 9 mm), trailing zeros removed.
* **Notes** - a NOTES block in its own cell (material, units, projection, plus
  caller lines).
* **Title-block fields fit their boxes** - the DWG NO. (the drawing's file
  name) and TITLE notes of the sheet format are shrunk, down to 2 mm, until
  they fill at most 90% of the room before the next field in their row; one
  that still runs over is an overlap. ``title_block_text_height_mm`` caps
  their height for smaller text.
* **No overlap anywhere** - checked against the real read-back geometry.
  The scale is chosen once to fit the sheet and is never stepped down;
  overlaps are resolved by moving dimensions.

The drawing is built in separate COM steps (sheet, views, layout,
dimensions, notes, check), each through ``_handle_com_operation`` so each
gets its settle pause: one long burst of drawing calls is the pattern that
crashed SolidWorks 2026 in its idle-time refresh (COM pitfall #26).
"""

from __future__ import annotations

import glob
import ntpath
import os
from dataclasses import dataclass, field
from datetime import date as _date
from typing import TYPE_CHECKING, Any, cast

from ..base import AdapterResult, AdapterResultStatus
from . import dimension_layout as _layout
from .features import _null_callout
from .io import _as_com, _resolve_drawing_view, _sw_type_info, _view_names

if TYPE_CHECKING:
    from collections.abc import Callable

Box = tuple[float, float, float, float]

#: Standard scales from the drawing standard, largest first, as (num, den).
STANDARD_SCALES: list[tuple[float, float]] = [
    (5, 1), (4, 1), (3, 1), (2.5, 1), (2, 1), (1.5, 1), (1, 1),
    (1, 2), (1, 2.5), (1, 4), (1, 5), (1, 7.5), (1, 10), (1, 12.5),
    (1, 15), (1, 20), (1, 25), (1, 30), (1, 40), (1, 50), (1, 60),
    (1, 75), (1, 100),
]  # fmt: skip

SHEET_SIZE = (0.420, 0.297)
WORK_AREA: Box = (0.015, 0.015, 0.405, 0.282)
TITLE_BLOCK: Box = (0.218, 0.008, 0.412, 0.072)
#: Cells (x0, y0, x1, y1) in metres. Third-angle: plan above front, side right.
CELLS: dict[str, Box] = {
    "front": (0.015, 0.075, 0.215, 0.178),
    "side": (0.215, 0.075, 0.405, 0.178),
    "plan": (0.015, 0.178, 0.215, 0.282),
    "iso": (0.215, 0.178, 0.405, 0.282),
    "notes": (0.015, 0.015, 0.215, 0.075),
}
CAPTIONS = {
    "front": "FRONT VIEW",
    "plan": "TOP VIEW",
    "side": "SIDE VIEW",
    "iso": "ISOMETRIC VIEW",
}
#: Caption strip at the bottom of every view cell.
CAPTION_STRIP = 0.009
#: A BOM placed by the generator sits 5 mm inside its cell's top-right corner,
#: and the isometric below it keeps 5 mm clear of it.
BOM_GAP = 0.005
CAPTION_HEIGHT = 0.0032
NOTE_HEIGHT = 0.003

# swUserPreferenceToggle_e / IntegerValue_e / StringValue_e (swconst.tlb, SW 2025)
_SW_SHOW_SHEET_FORMAT_DIALOG = 353
_SW_DETAILING_DIM_TRAILING_ZERO = 15
_SW_DIM_REMOVE_TRAILING_ZEROES = 2
_SW_PREF_SHEET_FORMAT_FOLDER = 7
# swDwgPaperSizes_e / swDwgTemplates_e
_SW_PAPER_A3 = 8
_SW_TEMPLATE_CUSTOM = 12
# swUserPreferenceStringValue_e / swBomType_e / swBOMConfigurationAnchorType_e /
#: swDisplayMode_e.swHIDDEN_GREYED: "Hidden Lines Visible", drawn dashed on a
#: drawing (read from swconst.tlb, SW 2026).
_SW_HIDDEN_LINES_VISIBLE = 1

# swNumberingType_e (used by insert_bom_table)
_SW_PREF_BOM_TEMPLATES = 22
_SW_BOM_TYPES = {"parts_only": 1, "top_level_only": 2, "indented": 3}
# swBOMConfigurationAnchorType_e: the table corner that stays put
_SW_BOM_ANCHOR_TOP_LEFT = 1
_SW_BOM_ANCHOR_TOP_RIGHT = 2
_SW_BOM_ANCHOR_BOTTOM_LEFT = 3
_SW_BOM_ANCHOR_BOTTOM_RIGHT = 4
_SW_NUMBERING_NONE = 0
#: GD&T characteristic -> SolidWorks GTOL symbol code (IGtol::SetFrameSymbols2).
_GTOL_SYMBOLS = {
    "position": "<IGTOL-POSI>",
    "flatness": "<IGTOL-FLAT>",
    "perpendicularity": "<IGTOL-PERP>",
    "parallelism": "<IGTOL-PARA>",
    "profile_surface": "<IGTOL-SPROF>",
    "concentricity": "<IGTOL-CONC>",
}
#: Material condition -> modifier symbol code.
_GTOL_MODIFIERS = {"none": "", "mmc": "<MOD-MMC>", "lmc": "<MOD-LMC>"}


def gtol_problem(
    characteristic: str,
    tolerance: float,
    material_condition: str,
    datums: list[str] | None,
) -> str | None:
    """Why a feature control frame's inputs are invalid, or ``None`` when valid.

    Shared by the real and mock adapters so both refuse the same inputs.

    Args:
        characteristic: The GD&T characteristic name.
        tolerance: The tolerance value.
        material_condition: ``none``, ``mmc`` or ``lmc``.
        datums: Datum letters, primary first.

    Returns:
        str | None: The problem, in words.
    """
    letters = [d.strip() for d in datums or []]
    if characteristic not in _GTOL_SYMBOLS:
        return f"characteristic must be one of {', '.join(_GTOL_SYMBOLS)}"
    if material_condition not in _GTOL_MODIFIERS:
        return f"material_condition must be one of {', '.join(_GTOL_MODIFIERS)}"
    if tolerance <= 0:
        return "tolerance must be positive"
    if len(letters) > 3 or any(len(d) != 1 or not d.isalpha() for d in letters):
        return "at most three datums, each a single letter"
    return None


def _double_array(values: list[float]) -> Any:
    """``VARIANT(VT_ARRAY | VT_R8)`` for array-valued COM properties (tuple when pywin32 is absent)."""
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values]
        )
    except ImportError:  # non-Windows
        return tuple(values)


def _grow(box: tuple[float, ...], by: float) -> Box:
    """``box`` grown by ``by`` on every side."""
    return (box[0] - by, box[1] - by, box[2] + by, box[3] + by)


def scale_label(scale: tuple[float, float]) -> str:
    """``(1, 2)`` -> ``"1:2"``, ``(2.5, 1)`` -> ``"2.5:1"``."""
    return f"{scale[0]:g}:{scale[1]:g}"


def content_box(cell: Box) -> Box:
    """The part of a view cell left after the caption strip."""
    return (cell[0], cell[1] + CAPTION_STRIP, cell[2], cell[3])


#: Area for the four view cells: full width above the notes and title block.
VIEW_ZONE: Box = (0.015, 0.075, 0.405, 0.282)
#: Room for dimensions each side of a view when sizing cells: the first row
#: (8 mm) plus one more row/column. The scale is chosen once from this fit and
#: never stepped down; the real overlap check reports anything that remains.
FIT_H_MARGIN = _layout.FIRST_OFFSET + _layout.COLUMN_PITCH
FIT_V_MARGIN = _layout.FIRST_OFFSET + _layout.ROW_PITCH
ISO_MARGIN = 0.006


def plan_cells(
    sizes: dict[str, tuple[float, float]], scale: tuple[float, float]
) -> dict[str, Box] | None:
    """Size the four view cells for one part at one scale, or None if it won't fit.

    Third-angle grid: front bottom-left, side to its right, plan above the
    front, isometric top-right. Column widths follow the part's width and
    depth, row heights its height and depth; spare space is shared out evenly
    so every view is centred with room around it.

    Args:
        sizes: ``front`` (width, height), ``plan`` (width, depth) and/or
            ``side`` (depth, height), in model metres.
        scale: Sheet scale (num, den).
    """
    f = scale[0] / scale[1]
    front = sizes.get("front")
    if front is None:
        return None
    width, height = front
    depth = sizes["side"][0] if "side" in sizes else sizes.get("plan", (0.0, 0.0))[1]
    left = width * f + 2 * FIT_H_MARGIN
    right = depth * f + 2 * FIT_H_MARGIN
    low = height * f + 2 * FIT_V_MARGIN + CAPTION_STRIP
    high = depth * f + 2 * FIT_V_MARGIN + CAPTION_STRIP
    zx0, zy0, zx1, zy1 = VIEW_ZONE
    if left + right > zx1 - zx0 or low + high > zy1 - zy0:
        return None
    xm = zx0 + left + (zx1 - zx0 - left - right) / 2
    ym = zy0 + low + (zy1 - zy0 - low - high) / 2
    return {
        "front": (zx0, zy0, xm, ym),
        "side": (xm, zy0, zx1, ym),
        "plan": (zx0, ym, xm, zy1),
        "iso": (xm, ym, zx1, zy1),
        "notes": CELLS["notes"],
    }


def choose_layout(
    sizes: dict[str, tuple[float, float]],
) -> tuple[tuple[float, float], dict[str, Box]]:
    """Largest standard scale whose cells fit, with those cells.

    Args:
        sizes: Model-space view sizes, as for :func:`plan_cells`.

    Returns:
        tuple: The scale (num, den) and the cells; the smallest standard scale
        (with default cells if even that does not fit) as a last resort.
    """
    for scale in STANDARD_SCALES:
        cells = plan_cells(sizes, scale)
        if cells is not None:
            return scale, cells
    last = STANDARD_SCALES[-1]
    return last, plan_cells(sizes, last) or dict(CELLS)


def iso_fit_scale(size: tuple[float, float], cell: Box) -> tuple[float, float]:
    """Largest standard scale at which the isometric view fills its cell."""
    area = content_box(cell)
    for scale in STANDARD_SCALES:
        f = scale[0] / scale[1]
        if (
            size[0] * f + 2 * ISO_MARGIN <= area[2] - area[0]
            and size[1] * f + 2 * ISO_MARGIN <= area[3] - area[1]
        ):
            return scale
    return STANDARD_SCALES[-1]


def title_block_properties(
    *,
    model_file: str,
    title: str,
    author: str,
    drawn_date: str,
    revision: str,
    company: str,
    subtitle: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map the standard's title-block fields onto the ISO format's properties.

    The ``a3 - iso`` format reads TITLE, MATERIAL and WEIGHT from the model
    (``$PRPSHEET``) and DRAWN, REVISION and the company from the drawing
    (``$PRP``). Material and weight are links, so they always show the model's
    real values.

    Returns:
        tuple: (model properties, drawing properties).
    """
    # SolidWorks paths are Windows paths, whatever platform this runs on.
    base = ntpath.basename(model_file)
    description = title  # keep TITLE short so it fits the box (standard section 1)
    model_props = {
        "Description": description,
        "Material": f'"SW-Material@{base}"',
        "Weight": f'"SW-Mass@{base}"',
    }
    drawing_props = {
        "DrawnBy": author,
        "DrawnDate": drawn_date,
        "Revision": revision,
        "COMPANYNAME": company or (subtitle or ""),
    }
    return model_props, {k: v for k, v in drawing_props.items() if v}


def find_sheet_format(adapter: Any, name: str = "a3 - iso.slddrt") -> str | None:
    """Locate a sheet format file: SolidWorks' configured folder, then ProgramData."""
    app = getattr(adapter, "swApp", None)
    folders: list[str] = []
    if app is not None:
        raw = adapter._attempt(
            lambda: app.GetUserPreferenceStringValue(_SW_PREF_SHEET_FORMAT_FOLDER),
            default="",
        )
        folders.extend(f.strip() for f in str(raw or "").split(";") if f.strip())
    folders.extend(
        sorted(
            glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS *\lang\*\sheetformat"),
            reverse=True,
        )
    )
    for folder in folders:
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return candidate
    return None


#: The NOTES block holds at most this many numbered lines.
MAX_NOTE_LINES = 7

#: Title-block fields fitted to their boxes: linked property -> field name.
#: The ``a3 - iso`` format shows the drawing's file name as the DWG NO. and
#: the model's ``Description`` as the TITLE (measured live on SW 2026: a
#: default drawing number ran across the size box at the format's height).
TITLE_BLOCK_FIELDS = {"SW-File Name": "drawing number", "Description": "title"}

#: A fitted field's text is never made smaller than this.
MIN_FIELD_HEIGHT = 0.002

#: Clearance kept between a fitted field and the next field in its row.
FIELD_GAP = 0.002

#: A fitted field fills at most this share of its room, so it is not cramped.
FIELD_FILL = 0.9

#: What to tell a caller whose title-block field does not fit.
FIELD_HINT = (
    "pass title_block_text_height_mm (e.g. 3) for smaller title-block text, "
    "or a shorter drawing_number or title"
)

#: swTextFormat: the note uses its own format, not the document's.
_SW_NOTE_OWN_FORMAT = 0

#: Standard notes, after the material line.
STANDARD_NOTES = (
    "ALL DIMENSIONS IN MILLIMETRES",
    "THIRD ANGLE PROJECTION",
    "REMOVE ALL BURRS AND SHARP EDGES",
)

#: Where the isometric view is first dropped, before it is moved to its cell.
_ISO_DROP_POINT = (0.31, 0.23)


def note_lines(material: str | None, extra: list[str] | None) -> list[str]:
    """The NOTES block: a heading, then at most seven numbered lines.

    Args:
        material: The part's material, first when known.
        extra: The caller's lines, after the standard ones.

    Returns:
        list[str]: ``["NOTES", "1. ...", ...]`` in capitals.
    """
    body = [f"MATERIAL: {material.upper()}"] if material else []
    body += list(STANDARD_NOTES)
    body += [line.upper() for line in (extra or []) if line.strip()]
    numbered = [f"{i}. {line}" for i, line in enumerate(body[:MAX_NOTE_LINES], start=1)]
    return ["NOTES", *numbered]


def view_roles(
    views: dict[str, Any], outlines: dict[str, Box | None], orientations: dict[str, str]
) -> dict[str, str]:
    """Name each orthographic view's role: ``front``, ``plan`` or ``side``.

    The front is the view whose orientation says "front" (else the first);
    a view centred above the front is the plan, any other is the side.

    Args:
        views: View name -> ``IView``, in creation order.
        outlines: View name -> outline, ``None`` when unreadable.
        orientations: View name -> orientation name, e.g. ``*Front``.

    Returns:
        dict[str, str]: View name -> role; a view whose outline is unknown
        gets no role.
    """
    names = list(views)
    front = next(
        (n for n in names if "front" in orientations.get(n, "").lower()), names[0]
    )
    role = {front: "front"}
    fo = outlines.get(front)
    for name in names:
        o = outlines.get(name)
        if name == front or o is None or fo is None:
            continue
        above = (o[1] + o[3]) / 2 > (fo[1] + fo[3]) / 2 + 1e-4
        role[name] = "plan" if above else "side"
    return role


def field_room(box: Box, others: list[Box], limit: float) -> float:
    """How far right a title-block field may run: to the next note in its row.

    A note is in the field's row when its vertical centre lies within the
    field's height, and it is to the right when it starts more than 5 mm
    after the field does (the field's own label sits at about its start).

    Args:
        box: The field's text box.
        others: Every other note's box in the title block.
        limit: The title block's right edge.

    Returns:
        float: The x the field's text must end before.
    """
    right = limit
    for o in others:
        centre = (o[1] + o[3]) / 2
        if box[1] <= centre <= box[3] and o[0] > box[0] + 0.005:
            right = min(right, o[0] - FIELD_GAP)
    return right


@dataclass
class _Sheet:
    """What the generator's steps share while they build one drawing.

    Attributes:
        path: The model being drawn.
        sheet_format: The ``.slddrt`` applied to the sheet.
        include_isometric: Whether to add the isometric view.
        include_bom: Whether to put a BOM above the isometric.
        material: The part's material, for the notes.
        extra_notes: The caller's note lines.
        views: View name -> ``IView``, orthographic first.
        role: View name -> ``front``, ``plan``, ``side`` or ``iso``.
        ortho: The orthographic view names.
        iso_name: The isometric view's name, when one was made.
        scale: The sheet scale.
        cells: Role -> cell on the sheet.
        iso_scale: The isometric view's own scale.
        iso_size: The isometric's model size, for fitting it to a cell.
        bom_box: The BOM table's box on the sheet, once placed.
        captions: View name -> caption text.
        notes: ``(label, IAnnotation)`` for every caption and note line.
        note_lines: The NOTES block's text.
        title_block: Field name -> how it was fitted to its box.
        format_links: The property links the sheet format's notes show.
        field_height: The caller's cap on the fitted fields' text height.
    """

    path: str
    sheet_format: str
    include_isometric: bool = True
    include_bom: bool = False
    material: str | None = None
    extra_notes: list[str] = field(default_factory=list)
    views: dict[str, Any] = field(default_factory=dict)
    role: dict[str, str] = field(default_factory=dict)
    ortho: list[str] = field(default_factory=list)
    iso_name: str | None = None
    scale: tuple[float, float] = (1, 1)
    cells: dict[str, Box] = field(default_factory=dict)
    iso_scale: tuple[float, float] | None = None
    iso_size: tuple[float, float] | None = None
    bom_box: Box | None = None
    captions: dict[str, str] = field(default_factory=dict)
    notes: list[tuple[str, Any]] = field(default_factory=list)
    note_lines: list[str] = field(default_factory=list)
    title_block: dict[str, dict[str, Any]] = field(default_factory=dict)
    format_links: list[str] = field(default_factory=list)
    field_height: float | None = None


def _step(steps: list[dict[str, Any]], name: str, result: AdapterResult[Any]) -> None:
    """Record one step's outcome in the generator's ``steps`` list."""
    steps.append(
        {
            "step": name,
            "status": "success" if result.is_success else "error",
            "error": result.error,
        }
    )


class SolidWorksDrawingStandardMixin:
    """Create complete standard A3 drawings, BOM tables and the sheet scale."""

    if TYPE_CHECKING:
        currentModel: Any
        swApp: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], default: Any = None
        ) -> Any: ...

        def _require_drawing(self) -> AdapterResult[Any] | None: ...

        def _get_attr_or_call(self, obj: Any, attr_name: str) -> Any: ...

        def _dimension_annotations(self, view: Any) -> list[tuple[Any, str | None]]: ...

        def _select_display_dimension(self, model: Any, an: Any) -> bool: ...

        def _sheet_bounds(self, drawing: Any) -> Any: ...

        def _dimension_geometry(self, an: Any, key: str, view_name: str) -> Any: ...

        def _import_dimensions(
            self,
            view_name: str | None = None,
            include_hole_wizard: bool = True,
            only_views: list[str] | None = None,
        ) -> dict[str, Any]: ...

        def _arrange_layout(
            self,
            view_name: str | None = None,
            obstacles: dict[str, Any] | None = None,
            work_area: Any = None,
            move: bool = True,
            attached: dict[str, Any] | None = None,
        ) -> dict[str, Any]: ...

        def _collect_layout(
            self, drawing: Any, names: list[str]
        ) -> tuple[dict, list, dict]: ...

        async def open_model(self, file_path: str) -> AdapterResult[Any]: ...

        async def get_material(
            self, configuration: str | None = None
        ) -> AdapterResult[Any]: ...

        async def set_custom_property(
            self, name: str, value: str, configuration: str | None = None
        ) -> AdapterResult[Any]: ...

        async def save_file(
            self, file_path: str | None = None
        ) -> AdapterResult[Any]: ...

        async def create_drawing(
            self, name: str | None = None
        ) -> AdapterResult[Any]: ...

        async def set_units(self, unit_system: str) -> AdapterResult[Any]: ...

        async def export_file(
            self, file_path: str, format_type: str
        ) -> AdapterResult[Any]: ...

    # -- BOM and sheet scale -------------------------------------------

    def _table_box(self, table: Any) -> Box | None:
        """A table's box on the sheet, from its stationary corner and cell sizes.

        ``IAnnotation::GetPosition`` gives the stationary corner named by
        ``ITableAnnotation::AnchorType`` (measured live on SW 2026); the table
        spans the sum of its column widths and row heights from there.

        Args:
            table: The ``ITableAnnotation``.

        Returns:
            Box | None: ``(x0, y0, x1, y1)`` in sheet metres, or ``None`` when
            the table cannot be measured.
        """
        t = _sw_type_info.flagged(table, "ITableAnnotation")
        an = self._attempt(
            lambda: _sw_type_info.flagged(t.GetAnnotation(), "IAnnotation"),
            default=None,
        )
        pos = self._attempt(lambda: an.GetPosition(), default=None)
        rows = int(self._attempt(lambda: t.RowCount, default=0) or 0)
        cols = int(self._attempt(lambda: t.ColumnCount, default=0) or 0)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2 or not rows or not cols:
            return None
        height = sum(
            float(self._attempt(lambda i=i: t.GetRowHeight(i), default=0.0) or 0.0)
            for i in range(rows)
        )
        width = sum(
            float(self._attempt(lambda i=i: t.GetColumnWidth(i), default=0.0) or 0.0)
            for i in range(cols)
        )
        anchor = self._attempt(lambda: t.AnchorType, default=None)
        x, y = float(pos[0]), float(pos[1])
        right_anchored = anchor in (
            _SW_BOM_ANCHOR_TOP_RIGHT,
            _SW_BOM_ANCHOR_BOTTOM_RIGHT,
        )
        top_anchored = anchor in (_SW_BOM_ANCHOR_TOP_LEFT, _SW_BOM_ANCHOR_TOP_RIGHT)
        left = x - width if right_anchored else x
        bottom = y - height if top_anchored else y
        return (left, bottom, left + width, bottom + height)

    def _slide_onto_sheet(self, table: Any, box: Box, sheet: Box) -> bool:
        """Move a table by the least distance that puts its box on the sheet.

        The ISO A3 format's BOM anchor is at the top of the sheet, and a table
        grown up from it there runs off the top (measured live on SW 2026).

        Args:
            table: The ``ITableAnnotation``.
            box: Its box on the sheet, in metres.
            sheet: The sheet's box, in metres.

        Returns:
            bool: Whether the table was moved. ``False`` when it is larger
            than the sheet or its position cannot be read.
        """
        if (
            box[2] - box[0] > sheet[2] - sheet[0]
            or box[3] - box[1] > sheet[3] - sheet[1]
        ):
            return False
        dx = max(sheet[0] - box[0], 0.0) + min(sheet[2] - box[2], 0.0)
        dy = max(sheet[1] - box[1], 0.0) + min(sheet[3] - box[3], 0.0)
        t = _sw_type_info.flagged(table, "ITableAnnotation")
        an = self._attempt(
            lambda: _sw_type_info.flagged(t.GetAnnotation(), "IAnnotation"),
            default=None,
        )
        pos = self._attempt(lambda: an.GetPosition(), default=None)
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            return False
        x, y = float(pos[0]) + dx, float(pos[1]) + dy
        self._attempt(lambda: an.SetPosition(x, y, 0.0), default=None)
        return True

    async def insert_bom_table(
        self,
        view_name: str,
        template_path: str | None = None,
        bom_type: str = "top_level_only",
        x_mm: float | None = None,
        y_mm: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Insert a bill-of-materials table anchored to an assembly drawing view.

        Wraps ``IView::InsertBomTable4``. With no position the table snaps to
        the sheet format's BOM anchor, or to the sheet's bottom-left corner
        when the sheet has no format. Its stationary corner is the
        bottom-left, so the table grows up onto the sheet; with the top-left
        it hung below the sheet (measured live on SW 2026). The table's box is
        read back and must lie on the sheet. An anchor near the top of the
        sheet (the ISO A3 format's) makes it grow off the top, so a table
        placed by the anchor is slid back onto the sheet; one placed at a
        given ``x_mm``/``y_mm`` is never moved. With no template the library
        default ``bom-standard.sldbomtbt`` from the BOM templates folder is
        used.

        Args:
            view_name: A view of an assembly on the active drawing.
            template_path: ``.sldbomtbt`` table template.
            bom_type: ``top_level_only``, ``parts_only`` or ``indented``.
            x_mm: Optional table position on the sheet.
            y_mm: Optional table position on the sheet.

        Returns:
            AdapterResult[dict[str, Any]]: The view, BOM type, template, row
            count, ``table_box_mm`` and ``moved_onto_sheet``; an error naming
            the box when the table still runs off the sheet.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if bom_type not in _SW_BOM_TYPES:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="bom_type must be top_level_only, parts_only or indented",
            )

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation(
                "insert_bom_table",
                lambda: self._insert_bom(
                    view_name, template_path, bom_type, x_mm, y_mm
                )[1],
            ),
        )

    def _insert_bom(
        self,
        view_name: str,
        template_path: str | None,
        bom_type: str,
        x_mm: float | None,
        y_mm: float | None,
    ) -> tuple[Any, dict[str, Any]]:
        """Insert a BOM table on a view; insert_bom_table's body.

        Returns:
            tuple: The ``ITableAnnotation`` and what insert_bom_table reports.

        Raises:
            LookupError: No such view.
            RuntimeError: The table runs off the sheet.
        """
        drawing = _sw_type_info.flagged(self.currentModel, "IDrawingDoc")
        view = _resolve_drawing_view(self, drawing, view_name)
        if view is None:
            raise LookupError(
                f"No view named {view_name!r}. Views: "
                f"{', '.join(_view_names(self, drawing)) or 'none'}"
            )
        template = template_path
        if not template:
            folder = str(
                self._attempt(
                    lambda: self.swApp.GetUserPreferenceStringValue(
                        _SW_PREF_BOM_TEMPLATES
                    ),
                    default="",
                )
                or ""
            ).split(";")[0]
            candidate = os.path.join(folder, "bom-standard.sldbomtbt")
            template = candidate if os.path.exists(candidate) else ""
        use_anchor = x_mm is None or y_mm is None
        config = str(
            self._attempt(lambda: view.ReferencedConfiguration, default="") or ""
        )
        numbering = 1 if bom_type == "indented" else _SW_NUMBERING_NONE
        table = view.InsertBomTable4(
            use_anchor,
            (x_mm or 0.0) / 1000.0,
            (y_mm or 0.0) / 1000.0,
            _SW_BOM_ANCHOR_BOTTOM_LEFT,
            _SW_BOM_TYPES[bom_type],
            config,
            template,
            False,
            numbering,
            False,
        )
        if table is None:
            raise Exception(
                f"InsertBomTable4 returned nothing for view {view_name!r}. "
                "A BOM needs a view of an assembly"
                + ("" if template else " and a BOM template (none found)")
                + "."
            )
        rows = self._attempt(
            lambda: _sw_type_info.flagged(table, "ITableAnnotation").RowCount,
            default=None,
        )
        box = self._table_box(table)
        sheet = self._sheet_bounds(drawing)
        on_sheet = _grow(sheet, 1e-6) if sheet else None
        moved = False
        if (
            use_anchor
            and box
            and on_sheet
            and not _layout.inside(box, on_sheet)
            and self._slide_onto_sheet(table, box, sheet)
        ):
            moved = True
            box = self._table_box(table)
        box_mm = [round(c * 1000, 1) for c in box] if box else None
        if box and on_sheet and not _layout.inside(box, on_sheet):
            raise RuntimeError(
                f"The BOM table was inserted but runs off the sheet: table "
                f"{box_mm} mm, sheet {sheet[2] * 1000:g} x {sheet[3] * 1000:g} "
                "mm. Give x_mm and y_mm to place it on the sheet."
            )
        return table, {
            "view": view_name,
            "bom_type": bom_type,
            "template": template or None,
            "row_count": rows,
            "table_box_mm": box_mm,
            "moved_onto_sheet": moved,
        }

    async def set_sheet_scale(
        self, numerator: float, denominator: float
    ) -> AdapterResult[dict[str, Any]]:
        """Set the active drawing sheet's scale, e.g. 1:2 (``ISheet::SetScale``).

        Args:
            numerator: Scale numerator.
            denominator: Scale denominator.

        Returns:
            AdapterResult[dict[str, Any]]: The sheet name, the ``scale`` read
            back from the sheet and the ``requested`` one.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        if numerator <= 0 or denominator <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="Scale values must be positive"
            )

        def _scale() -> dict[str, Any]:
            drawing = _sw_type_info.flagged(self.currentModel, "IDrawingDoc")
            sheet = _sw_type_info.flagged(drawing.GetCurrentSheet(), "ISheet")
            if not sheet.SetScale(float(numerator), float(denominator), True, False):
                raise Exception("ISheet.SetScale returned False")
            self._attempt(lambda: self.currentModel.EditRebuild3(), default=None)
            name = self._attempt(lambda: sheet.GetName(), default=None)
            # GetProperties2: paper size, template, scale num, scale den, ...
            props = self._attempt(lambda: sheet.GetProperties2(), default=None)
            if not (isinstance(props, (list, tuple)) and len(props) >= 4):
                raise Exception("The sheet's scale could not be read back")
            return {
                "sheet": name,
                "scale": f"{float(props[2]):g}:{float(props[3]):g}",
                "requested": f"{numerator:g}:{denominator:g}",
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("set_sheet_scale", _scale),
        )

    # -- GD&T ------------------------------------------------------------

    def _select_edge_at(self, point_mm: tuple[float, float]) -> bool:
        """Select the drawing edge nearest a sheet point, given in mm."""
        model = self.currentModel
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        x, y = point_mm[0] / 1000.0, point_mm[1] / 1000.0
        return bool(
            self._attempt(
                lambda: model.Extension.SelectByID2(
                    "", "EDGE", x, y, 0.0, False, 0, _null_callout(), 0
                ),
                default=False,
            )
        )

    def _place_annotation(self, item: Any, x_mm: float, y_mm: float) -> None:
        """Move an annotation-owning object (frame, datum tag) to a sheet point."""
        an = self._attempt(lambda: self._get_attr_or_call(item, "GetAnnotation"))
        if an is not None:
            an = _sw_type_info.flagged(an, "IAnnotation")
            self._attempt(
                lambda: an.SetPosition(x_mm / 1000.0, y_mm / 1000.0, 0.0),
                default=None,
            )

    async def add_gtol(
        self,
        characteristic: str,
        tolerance: float,
        x_mm: float,
        y_mm: float,
        diameter_zone: bool = False,
        material_condition: str = "none",
        datums: list[str] | None = None,
        attach_at_mm: tuple[float, float] | None = None,
        dimension: tuple[str, str] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a feature control frame (GD&T) to the active drawing.

        ``IModelDoc2::InsertGtol`` creates the frame on whatever is selected:
        a drawing dimension (``dimension``; the frame sits under its text and
        moves with it, the usual place for a hole's position tolerance), the
        edge picked at ``attach_at_mm`` (with a leader), or nothing
        (free-standing);
        ``IGtol::SetFrameSymbols2`` sets the characteristic, the Ø zone and
        the material condition, and ``IGtol::SetFrameValues`` the tolerance
        and datums. The values are read back with ``GetFrameValues``, so a
        frame SolidWorks did not fill in is an error, not a success.

        Args:
            characteristic: ``position``, ``flatness``, ``perpendicularity``,
                ``parallelism``, ``profile_surface`` or ``concentricity``.
            tolerance: The tolerance value, in drawing units.
            x_mm: Where the frame goes on the sheet.
            y_mm: Where the frame goes on the sheet.
            diameter_zone: Prefix the tolerance with Ø (a cylindrical zone).
            material_condition: ``none``, ``mmc`` (Ⓜ) or ``lmc`` (Ⓛ).
            datums: Up to three datum letters, primary first.
            attach_at_mm: A sheet point on the edge the leader points to.
            dimension: ``(view name, model dimension name)``, e.g.
                ``("Drawing View2", "D3@Sketch1")``: attach the frame to that
                drawing dimension. ``x_mm``/``y_mm`` are then not used.

        Returns:
            AdapterResult[dict[str, Any]]: The frame as read back.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        problem = gtol_problem(characteristic, tolerance, material_condition, datums)
        if problem is not None:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=problem)
        symbol = _GTOL_SYMBOLS[characteristic]
        modifier = _GTOL_MODIFIERS[material_condition]
        letters = [d.strip().upper() for d in datums or []]

        def _insert() -> dict[str, Any]:
            model = self.currentModel
            target = None
            if dimension is not None:
                target = self._drawing_dimension(*dimension)
                if target is None or not self._select_display_dimension(model, target):
                    raise LookupError(
                        f"No dimension {dimension[1]!r} in view {dimension[0]!r}"
                    )
                attached: Any = dimension[1]
            elif attach_at_mm is not None:
                if not self._select_edge_at(attach_at_mm):
                    raise LookupError(
                        f"No drawing edge found at {list(attach_at_mm)} mm"
                    )
                attached = True
            else:
                attached = False
            gtol = self._get_attr_or_call(model, "InsertGtol")
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            if gtol is None:
                raise Exception("InsertGtol returned nothing; no frame was added")
            gtol = _sw_type_info.flagged(gtol, "IGtol")
            padded = [*letters, "", "", ""][:3]
            text = f"{tolerance:g}"
            gtol.SetFrameSymbols2(
                1, symbol, diameter_zone, modifier, False, "", "", "", ""
            )
            gtol.SetFrameValues(1, text, "", *padded)
            if dimension is None:
                self._place_annotation(gtol, x_mm, y_mm)
            self._attempt(lambda: model.GraphicsRedraw2(), default=None)
            values = self._attempt(lambda: gtol.GetFrameValues(1), default=None)
            read = [str(v) for v in values] if isinstance(values, (list, tuple)) else []
            if not read or read[0] != text or read[2:5] != padded:
                raise Exception(
                    f"The frame did not take its values: read back {read or None}, "
                    f"expected tolerance {text!r} and datums {padded}"
                )
            return {
                "characteristic": characteristic,
                "tolerance": text,
                "diameter_zone": diameter_zone,
                "material_condition": material_condition,
                "datums": letters,
                "attached": attached,
                "position_mm": None if dimension is not None else [x_mm, y_mm],
                "layout": (
                    None
                    if dimension is None
                    else self._clear_attached_frame(dimension[0], target, gtol)
                ),
            }

        result = cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("add_gtol", _insert),
        )
        layout = (result.data or {}).get("layout") if result.is_success else None
        if layout and layout["overlaps_after"]:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"The frame was added but {layout['overlaps_after']} overlap(s) "
                    "remain on the sheet - the no-overlap rule is not met; see layout"
                ),
                data=result.data,
                execution_time=result.execution_time,
            )
        return result

    def _drawing_dimension(self, view_name: str, name: str) -> Any:
        """The drawing dimension ``name`` (e.g. ``D3@Sketch1``) in a view, or None.

        On an assembly drawing a part's dimension can carry its component
        too (``D3@Sketch1@Demo Plate-1@Plate Stack``), so the part's own name
        followed by ``@`` matches as well.
        """
        drawing = _sw_type_info.flagged(self.currentModel, "IDrawingDoc")
        view = _resolve_drawing_view(self, drawing, view_name)
        if view is None:
            return None
        return next(
            (
                an
                for an, n in self._dimension_annotations(view)
                if n is not None and (n == name or n.startswith(f"{name}@"))
            ),
            None,
        )

    def _frame_box(self, gtol: Any) -> Box:
        """A frame's box on the sheet: its texts and its lines, as drawn.

        Raises:
            RuntimeError: SolidWorks gave no display data for the frame.
        """
        an = self._attempt(lambda: self._get_attr_or_call(gtol, "GetAnnotation"))
        geometry = (
            None
            if an is None
            else self._attempt(
                lambda: self._dimension_geometry(
                    _sw_type_info.flagged(an, "IAnnotation"), "frame", "sheet"
                )
            )
        )
        if geometry is None:
            raise RuntimeError("Cannot measure the frame, so it cannot be kept clear")
        tb = geometry.text_box
        xs = [tb[0], tb[2], *(p for seg in geometry.lines for p in (seg[0], seg[2]))]
        ys = [tb[1], tb[3], *(p for seg in geometry.lines for p in (seg[1], seg[3]))]
        return (min(xs), min(ys), max(xs), max(ys))

    def _clear_attached_frame(self, view_name: str, an: Any, gtol: Any) -> dict:
        """Lay the view out again with the frame counted as part of its dimension.

        SolidWorks hangs the frame under the dimension's text; the layout
        placed that dimension for its text alone, so the frame can land on
        its neighbours (seen live on SW 2026). The frame moves with the
        dimension, so its box is taken relative to the dimension's position.

        Args:
            view_name: The dimension's view.
            an: The dimension's ``IAnnotation``.
            gtol: The frame just attached to it.

        Returns:
            dict: The layout result; ``overlaps_after`` counts the frame.

        Raises:
            LookupError: The dimension is not among the view's read dimensions.
        """
        model = self.currentModel
        self._attempt(lambda: model.EditRebuild3(), default=None)
        frame = self._frame_box(gtol)
        x, y = (float(v) for v in an.GetPosition()[:2])
        drawing = self._drawing()
        _, geometries, _ = self._collect_layout(drawing, [view_name])
        key = next(
            (
                g.key
                for g in geometries
                if abs(g.position[0] - x) < 1e-6 and abs(g.position[1] - y) < 1e-6
            ),
            None,
        )
        if key is None:
            raise LookupError("The frame's dimension is not among the view's")
        rel = (frame[0] - x, frame[1] - y, frame[2] - x, frame[3] - y)
        obstacles = {"title block": TITLE_BLOCK, **self._sheet_note_boxes(drawing)}
        result = self._arrange_layout(
            view_name, obstacles, WORK_AREA, attached={key: rel}
        )
        result["frame_box_mm"] = [round(v * 1000, 1) for v in frame]
        result["obstacles"] = sorted(obstacles)
        return result

    async def add_datum_tag(
        self,
        label: str,
        attach_at_mm: tuple[float, float],
        x_mm: float,
        y_mm: float,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a datum feature symbol (a datum tag) on a drawing edge.

        ``IModelDoc2::InsertDatumTag2`` attaches the tag to the edge picked at
        ``attach_at_mm``; ``IDatumTag::SetLabel`` names it, and the label is
        read back with ``GetLabel``.

        Args:
            label: The datum letter, e.g. ``A``.
            attach_at_mm: A sheet point on the edge or face line it marks.
            x_mm: Where the tag goes on the sheet.
            y_mm: Where the tag goes on the sheet.

        Returns:
            AdapterResult[dict[str, Any]]: The label as read back.
        """
        guard = self._require_drawing()
        if guard is not None:
            return cast("AdapterResult[dict[str, Any]]", guard)
        letter = label.strip().upper()
        if len(letter) != 1 or not letter.isalpha():
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="label must be a single letter, e.g. 'A'",
            )

        def _insert() -> dict[str, Any]:
            model = self.currentModel
            if not self._select_edge_at(attach_at_mm):
                raise LookupError(f"No drawing edge found at {list(attach_at_mm)} mm")
            tag = self._get_attr_or_call(model, "InsertDatumTag2")
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            if tag is None:
                raise Exception("InsertDatumTag2 returned nothing; no tag was added")
            tag = _sw_type_info.flagged(tag, "IDatumTag")
            tag.SetLabel(letter)
            self._place_annotation(tag, x_mm, y_mm)
            read = str(
                self._attempt(lambda: self._get_attr_or_call(tag, "GetLabel")) or ""
            )
            if read != letter:
                raise Exception(f"The datum tag reads {read!r}, not {letter!r}")
            return {"label": letter, "position_mm": [x_mm, y_mm]}

        return cast(
            "AdapterResult[dict[str, Any]]",
            self._handle_com_operation("add_datum_tag", _insert),
        )

    # -- small COM helpers ---------------------------------------------

    def _set_view_position(self, view: Any, x: float, y: float) -> bool:
        """Move a view's centre to (x, y) and confirm by reading it back.

        A plain tuple is mis-marshalled under late binding (x arrives as
        ~1e-310 and the view stays off the sheet); an explicit
        ``VARIANT(VT_ARRAY | VT_R8)`` works (pitfall #31, measured live on
        SW 2025).

        Args:
            view: The ``IView``.
            x: Sheet x of the view's centre.
            y: Sheet y of the view's centre.

        Returns:
            bool: Whether the view reads back at (x, y).
        """
        self._attempt(
            lambda: setattr(view, "Position", _double_array([x, y])), default=None
        )
        pos = self._attempt(lambda: view.Position, default=None)
        return (
            isinstance(pos, (list, tuple))
            and len(pos) >= 2
            and abs(float(pos[0]) - x) < 1e-4
            and abs(float(pos[1]) - y) < 1e-4
        )

    def _use_open_document(self, path: str) -> bool:
        """Make an already-open copy of ``path`` the active model, if there is one.

        Args:
            path: The model's absolute path.

        Returns:
            bool: ``True`` when that exact file was open and is now active.
        """
        app = self.swApp
        doc = self._attempt(lambda: app.GetOpenDocumentByName(path), default=None)
        if doc is None:
            return False
        open_path = str(self._attempt(lambda: doc.GetPathName(), default="") or "")
        if os.path.normcase(os.path.abspath(open_path)) != os.path.normcase(path):
            return False
        title = self._attempt(lambda: doc.GetTitle(), default=None)
        if title:
            self._attempt(lambda: app.ActivateDoc3(title, False, 0, 0), default=None)
        self.currentModel = doc
        return True

    def _view_outline(self, view: Any) -> Box | None:
        """A view's outline on the sheet, or ``None`` when unreadable."""
        raw = self._attempt(lambda: view.GetOutline(), default=None)
        if isinstance(raw, (list, tuple)) and len(raw) >= 4:
            return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        return None

    def _insert_sheet_note(
        self, text: str, x: float, y: float, height: float, bold: bool
    ) -> Any:
        """Insert a sheet note at (x, y) in the given height and weight.

        Args:
            text: The note.
            x: Sheet x.
            y: Sheet y.
            height: Character height in metres.
            bold: Bold text.

        Returns:
            Any: The note's ``IAnnotation``, or ``None`` when it was not made.
        """
        model = self.currentModel
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        note = self._attempt(lambda: model.InsertNote(text), default=None)
        if note is None:
            return None
        an = self._attempt(
            lambda: _as_com(
                self, _as_com(self, note, "INote").GetAnnotation(), "IAnnotation"
            ),
            default=None,
        )
        if an is None:
            return None
        tf = self._attempt(lambda: an.GetTextFormat(0), default=None)
        if tf is not None:
            tf = _as_com(self, tf, "ITextFormat")
            self._attempt(lambda: setattr(tf, "CharHeight", height), default=None)
            self._attempt(lambda: setattr(tf, "Bold", bold), default=None)
            self._attempt(lambda: an.SetTextFormat(0, False, tf), default=None)
        self._attempt(lambda: an.SetPosition(x, y, 0.0), default=None)
        return an

    def _place_note(
        self,
        an: Any,
        text: str,
        *,
        left: float | None = None,
        top: float | None = None,
        centre_x: float | None = None,
        bottom: float | None = None,
    ) -> Box:
        """Shift a note so its measured box meets the given edges.

        Args:
            an: The note's ``IAnnotation``.
            text: Its text, for the fallback size estimate.
            left: Wanted left edge.
            top: Wanted top edge.
            centre_x: Wanted horizontal centre.
            bottom: Wanted bottom edge.

        Returns:
            Box: The note's box after the move.
        """
        box = self._note_box(an, text, 0.0, 0.0, NOTE_HEIGHT)
        dx = dy = 0.0
        if left is not None:
            dx = left - box[0]
        if centre_x is not None:
            dx = centre_x - (box[0] + box[2]) / 2
        if top is not None:
            dy = top - box[3]
        if bottom is not None:
            dy = bottom - box[1]
        if abs(dx) > 1e-5 or abs(dy) > 1e-5:
            pos = self._attempt(lambda: an.GetPosition(), default=None)
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                self._attempt(
                    lambda: an.SetPosition(float(pos[0]) + dx, float(pos[1]) + dy, 0.0),
                    default=None,
                )
                box = self._note_box(an, text, 0.0, 0.0, NOTE_HEIGHT)
        return box

    def _note_box(
        self, an: Any, fallback_text: str, x: float, y: float, height: float
    ) -> Box:
        """A note's measured box; estimated from its text when unreadable.

        Args:
            an: The note's ``IAnnotation``.
            fallback_text: Its text, for the estimate.
            x: Estimate's left edge.
            y: Estimate's top edge.
            height: Estimate's text height.

        Returns:
            Box: The note's box on the sheet.
        """
        geometry = self._attempt(
            lambda: self._dimension_geometry(an, "note", "sheet"), default=None
        )
        if geometry is not None:
            return geometry.text_box
        width = 0.62 * height * len(fallback_text)
        return (x, y - height, x + width, y)

    def _drawing(self) -> Any:
        """The active document as an ``IDrawingDoc``."""
        return _sw_type_info.flagged(self.currentModel, "IDrawingDoc")

    def _obstacles(self, s: _Sheet, captions: bool = True) -> dict[str, Box]:
        """What dimensions must keep clear of: title block, notes, captions.

        Args:
            s: The sheet plan.
            captions: Keep each view's whole caption strip clear. ``False``
                once the captions are on the sheet and measured instead.
        """
        result: dict[str, Box] = {"title block": TITLE_BLOCK, "notes": s.cells["notes"]}
        for r in s.role.values() if captions else ():
            c = s.cells[r]
            result[f"{r} caption"] = (c[0], c[1], c[2], c[1] + CAPTION_STRIP)
        return result

    # -- the generator's COM steps --------------------------------------

    def _setup_a3_sheet(self, s: _Sheet) -> dict[str, Any]:
        """Apply the A3 ISO sheet format and drop trailing zeros.

        Raises:
            RuntimeError: ``SetupSheet5`` refused the format.
        """
        model = self.currentModel
        drawing = self._drawing()
        sheet = _as_com(self, drawing.GetCurrentSheet(), "ISheet")
        sheet_name = self._attempt(lambda: sheet.GetName(), default="Sheet1")
        if not drawing.SetupSheet5(
            sheet_name,
            _SW_PAPER_A3,
            _SW_TEMPLATE_CUSTOM,
            1.0,
            1.0,
            False,
            s.sheet_format,
            SHEET_SIZE[0],
            SHEET_SIZE[1],
            "Default",
            True,
        ):
            raise RuntimeError(f"SetupSheet5 refused the sheet format {s.sheet_format}")
        self._attempt(
            lambda: model.SetUserPreferenceIntegerValue(
                _SW_DETAILING_DIM_TRAILING_ZERO, _SW_DIM_REMOVE_TRAILING_ZEROES
            ),
            default=None,
        )
        return {"sheet": sheet_name, "sheet_format": s.sheet_format}

    def _create_views(self, s: _Sheet) -> dict[str, Any]:
        """Create the third-angle views, name their roles, add the isometric.

        Raises:
            RuntimeError: No view could be made from the model.
        """
        drawing = self._drawing()
        before = set(_view_names(self, drawing))
        self._attempt(lambda: drawing.Create3rdAngleViews2(s.path), default=False)
        s.ortho = [n for n in _view_names(self, drawing) if n not in before]
        if not s.ortho:
            raise RuntimeError(f"No views could be created from {s.path}")
        s.views = {n: _resolve_drawing_view(self, drawing, n) for n in s.ortho}
        outlines = {n: self._view_outline(v) for n, v in s.views.items()}
        orientations = {
            n: str(self._attempt(lambda v=v: v.GetOrientationName(), default="") or "")
            for n, v in s.views.items()
        }
        s.role = view_roles(s.views, outlines, orientations)
        # Orthographic views show hidden edges dashed (a through hole in the
        # front and side views); the isometric stays as it is.
        hidden = {n: self._show_hidden_lines(v) for n, v in s.views.items()}
        if s.include_isometric:
            before_iso = set(_view_names(self, drawing))
            self._attempt(
                lambda: drawing.CreateDrawViewFromModelView3(
                    s.path, "*Isometric", *_ISO_DROP_POINT, 0.0
                ),
                default=None,
            )
            s.iso_name = next(
                (n for n in _view_names(self, drawing) if n not in before_iso), None
            )
            if s.iso_name:
                s.views[s.iso_name] = _resolve_drawing_view(self, drawing, s.iso_name)
                s.role[s.iso_name] = "iso"
        return {"views": dict(s.role), "hidden_lines_visible": hidden}

    def _show_hidden_lines(self, view: Any) -> bool | None:
        """Draw a view's hidden edges dashed (``IView::SetDisplayMode4``).

        Returns:
            bool | None: Whether the view reads back as hidden lines visible;
            ``None`` when its mode cannot be read.
        """
        self._attempt(
            lambda: view.SetDisplayMode4(
                False, _SW_HIDDEN_LINES_VISIBLE, False, False, False
            ),
            default=None,
        )
        mode = self._attempt(
            lambda: self._get_attr_or_call(view, "GetDisplayMode2"), default=None
        )
        return None if mode is None else mode == _SW_HIDDEN_LINES_VISIBLE

    def _view_sizes(self, s: _Sheet) -> dict[str, tuple[float, float]]:
        """Each view's size at 1:1 (outline / view scale), by role."""
        result = {}
        for n, v in s.views.items():
            o = self._view_outline(v)
            scale = float(self._attempt(lambda v=v: v.ScaleDecimal, default=1.0) or 1.0)
            if n in s.role and o is not None and scale > 0:
                result[s.role[n]] = ((o[2] - o[0]) / scale, (o[3] - o[1]) / scale)
        return result

    def _fit_views(self, s: _Sheet) -> dict[str, Any]:
        """Pick the scale, then centre each view in its cell.

        The plan follows the front's x and the side its y, so the views stay
        aligned for third-angle projection.
        """
        model = self.currentModel
        sizes = self._view_sizes(s)
        iso_size = sizes.pop("iso", None)
        s.scale, s.cells = choose_layout(sizes)
        sheet = _as_com(self, self._drawing().GetCurrentSheet(), "ISheet")
        sheet.SetScale(float(s.scale[0]), float(s.scale[1]), True, False)
        self._attempt(lambda: model.EditRebuild3(), default=None)
        s.iso_size = iso_size
        if s.iso_name and iso_size:
            self._fit_iso(s)
        fc = content_box(s.cells["front"])
        fcx, fcy = (fc[0] + fc[2]) / 2, (fc[1] + fc[3]) / 2
        placed = {}
        for n, r in sorted(s.role.items(), key=lambda item: item[1] != "front"):
            c = content_box(s.cells[r])
            x, y = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
            if r == "plan":
                x = fcx
            elif r == "side":
                y = fcy
            placed[n] = self._set_view_position(s.views[n], x, y)
        self._attempt(lambda: model.EditRebuild3(), default=None)
        return {
            "scale": scale_label(s.scale),
            "isometric_scale": scale_label(s.iso_scale) if s.iso_scale else None,
            "positioned": placed,
        }

    def _fit_iso(self, s: _Sheet) -> None:
        """Scale the isometric to the largest standard scale that fits its cell."""
        s.iso_scale = iso_fit_scale(s.iso_size, s.cells["iso"])
        iso = s.views[s.iso_name]
        ratio = _double_array([float(s.iso_scale[0]), float(s.iso_scale[1])])
        self._attempt(lambda: setattr(iso, "UseSheetScale", False), default=None)
        self._attempt(lambda: setattr(iso, "ScaleRatio", ratio), default=None)

    def _bom_above_iso(self, s: _Sheet) -> dict[str, Any] | None:
        """Put the BOM in the top of the isometric's cell; fit the isometric below.

        The table is inserted, measured, and moved so its top-right corner sits
        ``BOM_GAP`` inside the cell's. The cell then ends below the table, and
        the isometric is scaled and centred in what is left, so they never meet.

        Raises:
            RuntimeError: The table cannot be measured once inserted.
        """
        if not s.include_bom:
            return None
        cell = s.cells["iso"]
        front = next(n for n, r in s.role.items() if r == "front")
        table, info = self._insert_bom(
            front, None, "top_level_only", cell[0] * 1000 + 10, cell[1] * 1000 + 20
        )
        box = self._table_box(table)
        if box is None:
            raise RuntimeError("The BOM was inserted but cannot be measured")
        an = _sw_type_info.flagged(
            _sw_type_info.flagged(table, "ITableAnnotation").GetAnnotation(),
            "IAnnotation",
        )
        x, y = (float(v) for v in an.GetPosition()[:2])
        an.SetPosition(
            x + cell[2] - BOM_GAP - box[2], y + cell[3] - BOM_GAP - box[3], 0.0
        )
        box = self._table_box(table)
        if box is None:
            raise RuntimeError("The BOM was moved but cannot be measured")
        s.bom_box = box
        s.cells["iso"] = (cell[0], cell[1], cell[2], box[1] - BOM_GAP)
        if s.iso_name and s.iso_size:
            self._fit_iso(s)
            c = content_box(s.cells["iso"])
            self._set_view_position(
                s.views[s.iso_name], (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
            )
        self._attempt(lambda: self.currentModel.EditRebuild3(), default=None)
        info["table_box_mm"] = [round(v * 1000, 1) for v in box]
        return info

    def _dimension_views(self, s: _Sheet) -> dict[str, Any]:
        """Import the model dimensions and lay them out clear of everything."""
        dims = self._import_dimensions(None, True, only_views=list(s.ortho))
        dims["layout"] = self._arrange_layout(None, self._obstacles(s), WORK_AREA)
        return dims

    def _annotate(self, s: _Sheet) -> dict[str, Any]:
        """Add a bold caption under each view and the NOTES block.

        Each note is placed from its measured box, so lines cannot run into
        each other.
        """
        model = self.currentModel
        for n, r in s.role.items():
            text = CAPTIONS[r]
            c = s.cells[r]
            s.captions[n] = text
            an = self._insert_sheet_note(
                text, c[0] + 0.01, c[1] + CAPTION_STRIP, CAPTION_HEIGHT, True
            )
            if an is not None:
                self._place_note(
                    an, text, centre_x=(c[0] + c[2]) / 2, bottom=c[1] + 0.0015
                )
                s.notes.append((f"caption {r}", an))
        s.note_lines = note_lines(s.material, s.extra_notes)
        nc = CELLS["notes"]
        top = nc[3] - 0.003
        for i, line in enumerate(s.note_lines):
            height = CAPTION_HEIGHT if i == 0 else NOTE_HEIGHT
            an = self._insert_sheet_note(line, nc[0] + 0.010, top, height, i == 0)
            if an is None:
                continue
            box = self._place_note(an, line, left=nc[0] + 0.010, top=top)
            s.notes.append((f"note line {i}", an))
            top = box[1] - 0.0015
        self._attempt(lambda: model.ClearSelection2(True), default=None)
        self._attempt(lambda: model.EditRebuild3(), default=None)
        return {"captions": dict(s.captions), "notes": list(s.note_lines)}

    def _note_extent(self, note: Any) -> Box | None:
        """A note's box from ``INote::GetExtent`` (lower-left, upper-right)."""
        raw = self._attempt(lambda: note.GetExtent(), default=None)
        if isinstance(raw, (list, tuple)) and len(raw) >= 6:
            return (float(raw[0]), float(raw[1]), float(raw[3]), float(raw[4]))
        return None

    def _format_notes(self, drawing: Any) -> list[tuple[Any, str, Box | None]]:
        """The notes on the sheet's own view: ``(INote, linked text, box)``.

        While the sheet format is being edited, these are the format's notes:
        its title-block fields and labels.
        """
        sheet_view = self._attempt(
            lambda: _sw_type_info.flagged(drawing.GetFirstView(), "IView"),
            default=None,
        )
        found = []
        note = self._attempt(lambda: sheet_view.GetFirstNote(), default=None)
        while note is not None and len(found) < 500:
            n = _sw_type_info.flagged(note, "INote")
            linked = str(
                self._attempt(lambda n=n: n.PropertyLinkedText, default="") or ""
            )
            found.append((n, linked, self._note_extent(n)))
            note = self._attempt(lambda n=n: n.GetNext(), default=None)
        return found

    def _fit_field(
        self, note: Any, right: float, cap: float | None = None
    ) -> dict[str, Any]:
        """Shrink one note's text until it fills at most 90% of its room.

        Args:
            note: The field's ``INote``.
            right: The x its text must end before.
            cap: The caller's largest text height in metres, applied first.

        Returns:
            dict[str, Any]: ``fits``, the text height before and after (mm)
            and the final box (mm).
        """
        model = self.currentModel
        box = self._note_extent(note)
        tf = self._attempt(
            lambda: _as_com(self, note.GetTextFormat(), "ITextFormat"), default=None
        )
        before = float(self._attempt(lambda: tf.CharHeight, default=0.0) or 0.0)
        height = before

        def apply(h: float) -> Box | None:
            self._attempt(lambda: setattr(tf, "CharHeight", h), default=None)
            self._attempt(
                lambda: note.SetTextFormat(_SW_NOTE_OWN_FORMAT, tf), default=None
            )
            self._attempt(lambda: model.EditRebuild3(), default=None)
            return self._note_extent(note)

        if cap is not None and height > cap:
            height = max(MIN_FIELD_HEIGHT, cap)
            box = apply(height)
        for _ in range(4):
            if box is None or height <= MIN_FIELD_HEIGHT:
                break
            room = max(right - box[0], 0.0)
            if box[2] - box[0] <= room * FIELD_FILL:
                break
            height = max(
                MIN_FIELD_HEIGHT, height * room * FIELD_FILL / (box[2] - box[0])
            )
            box = apply(height)
        return {
            "fits": box is not None and box[2] <= right + 1e-6,
            "height_mm_before": round(before * 1000, 2),
            "height_mm": round(height * 1000, 2),
            "box_mm": [round(c * 1000, 1) for c in box] if box else None,
            "room_ends_mm": round(right * 1000, 1),
        }

    def _fit_title_block(self, s: _Sheet) -> dict[str, dict[str, Any]]:
        """Fit the DWG NO. and TITLE fields of the sheet format to their boxes.

        Edits the sheet format (``EditTemplate``), always returning to the
        sheet (``EditSheet``). Run after the drawing is saved: the DWG NO.
        shows the file name, which is ``Draw1`` until then.
        """
        model = self.currentModel
        drawing = self._drawing()
        self._attempt(lambda: drawing.EditTemplate(), default=None)
        try:
            notes = self._format_notes(drawing)
            # The properties the format shows, e.g. $PRPSHEET:"SW-Material":
            # which model property each title-block field reads.
            s.format_links = sorted({n[1] for n in notes if n[1]})
            for prop, name in TITLE_BLOCK_FIELDS.items():
                match = next((n for n in notes if f'"{prop}"' in n[1]), None)
                if match is None or match[2] is None:
                    s.title_block[name] = {"found": match is not None, "fits": None}
                    continue
                others = [n[2] for n in notes if n is not match and n[2] is not None]
                right = field_room(match[2], others, TITLE_BLOCK[2])
                s.title_block[name] = {
                    "found": True,
                    **self._fit_field(match[0], right, s.field_height),
                }
        finally:
            self._attempt(lambda: drawing.EditSheet(), default=None)
            self._attempt(lambda: model.EditRebuild3(), default=None)
        return dict(s.title_block)

    def _sheet_note_boxes(self, drawing: Any) -> dict[str, Box]:
        """Every note on the sheet (view captions, the NOTES block) by its box.

        A note inserted with nothing selected goes into whichever view is
        active, not onto the sheet, so the notes of the sheet and of every
        view are read. Each is measured from its display data, as dimensions
        are, so dimensions keep clear of the text as SolidWorks placed it.
        """
        boxes: dict[str, Box] = {}
        view = self._attempt(lambda: drawing.GetFirstView(), default=None)
        while view is not None:
            v = _sw_type_info.flagged(view, "IView")
            note = self._attempt(lambda v=v: v.GetFirstNote(), default=None)
            while note is not None and len(boxes) < 500:
                n = _sw_type_info.flagged(note, "INote")
                box = self._measured_note(n)
                if box is not None:
                    boxes[f"note {len(boxes)}"] = box
                note = self._attempt(lambda n=n: n.GetNext(), default=None)
            view = self._attempt(lambda v=v: v.GetNextView(), default=None)
        return boxes

    def _measured_note(self, note: Any) -> Box | None:
        """A note's box from its display data; its extent when that is unreadable."""
        an = self._attempt(lambda: note.GetAnnotation(), default=None)
        geometry = (
            None
            if an is None
            else self._attempt(
                lambda: self._dimension_geometry(
                    _sw_type_info.flagged(an, "IAnnotation"), "note", "sheet"
                )
            )
        )
        return geometry.text_box if geometry is not None else self._note_extent(note)

    def _check_sheet(self, s: _Sheet) -> dict[str, Any]:
        """Lay the dimensions out on the finished sheet, then check it, read back.

        The layout runs again here: the steps after the first layout (captions,
        notes, the title block, the save) can leave dimensions where they were
        imported (seen live on SW 2026), and only now is every note on the sheet,
        so each caption is kept clear as measured, not its whole strip.
        """
        drawing = self._drawing()
        obstacles = {**self._obstacles(s, False), **self._sheet_note_boxes(drawing)}
        if s.bom_box is not None:
            obstacles["bom"] = s.bom_box
        final = self._arrange_layout(None, obstacles, WORK_AREA)
        outlines, dims, _ = self._collect_layout(drawing, _view_names(self, drawing))
        boxes = {
            label: self._note_box(an, label, 0.0, 0.0, NOTE_HEIGHT)
            for label, an in s.notes
        }
        if s.bom_box is not None:
            boxes["bom"] = s.bom_box
        problems = _layout.find_annotation_overlaps(
            boxes, dims, outlines, WORK_AREA, {"title block": TITLE_BLOCK}
        )
        final["annotation_overlaps"] = problems
        final["overlaps_after"] = final.get("overlaps_after", 0) + len(problems)
        return final

    # -- the generator ----------------------------------------------------

    def _new_drawing_without_dialog(self) -> bool | None:
        """Read and turn off the Sheet Format/Size prompt (pitfall #32).

        Returns:
            bool | None: The toggle's previous value, ``None`` when unreadable.
        """
        app = self.swApp
        previous = self._attempt(
            lambda: app.GetUserPreferenceToggle(_SW_SHOW_SHEET_FORMAT_DIALOG),
            default=None,
        )
        self._attempt(
            lambda: app.SetUserPreferenceToggle(_SW_SHOW_SHEET_FORMAT_DIALOG, False),
            default=None,
        )
        return None if previous is None else bool(previous)

    def _restore_dialog(self, previous: bool | None) -> None:
        """Put the Sheet Format/Size prompt back as it was."""
        if previous is not None:
            app = self.swApp
            self._attempt(
                lambda: app.SetUserPreferenceToggle(
                    _SW_SHOW_SHEET_FORMAT_DIALOG, previous
                ),
                default=None,
            )

    async def create_standard_drawing(
        self,
        model_path: str,
        output_dir: str | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        drawing_number: str | None = None,
        author: str = "",
        revision: str = "A",
        company: str = "",
        drawn_date: str | None = None,
        notes: list[str] | None = None,
        include_isometric: bool = True,
        write_model_properties: bool = True,
        title_block_text_height_mm: float | None = None,
        include_bom: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Create a complete A3 drawing that follows the drawing standard.

        Opens the model (or uses its open copy), writes the title-block
        properties into it, makes a drawing on the A3 ISO format, builds the
        sheet in separate COM steps, writes the drawing properties, saves
        ``<drawing_number>.SLDDRW`` and exports a PDF.

        Args:
            model_path: Part (.SLDPRT) or assembly (.SLDASM) to draw.
            output_dir: Folder for the .SLDDRW and PDF; the model's folder by default.
            title: Title block TITLE; the model file name by default.
            subtitle: Company field when ``company`` is empty.
            drawing_number: DWG NO.; also the drawing file name. Default
                ``<MODEL>-Rev<revision>-01``.
            author: DRAWN name.
            revision: Revision letter.
            company: Company name field.
            drawn_date: DRAWN date; today (e.g. "17 Oct 2026") by default.
            notes: Extra note lines (at most seven lines in total are shown).
            include_isometric: Add the isometric view in its cell.
            write_model_properties: Write Description/Material/Weight custom
                properties into the model (the format reads them from there)
                and save the model.
            title_block_text_height_mm: Largest text height for the DWG NO.
                and TITLE fields, e.g. 3 for smaller text; they are shrunk
                further when they still do not fit.
            include_bom: Assemblies only: a top-level BOM in the top of the
                isometric's cell, the isometric fitted below it.

        Returns:
            AdapterResult[dict[str, Any]]: Files, scale, views, dimension
            counts, the overlap check, every property written and each step's
            outcome. ERROR, with that data, when a step fails, the drawing or
            PDF could not be saved, or any overlap remains.
        """
        path = os.path.abspath(model_path)
        if not os.path.isfile(path):
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Model file not found: {path}"
            )
        ext = os.path.splitext(path)[1].lower()
        if ext not in {".sldprt", ".sldasm"}:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"model_path must be a .SLDPRT or .SLDASM, not {ext or 'no extension'}",
            )
        if include_bom and ext != ".sldasm":
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="include_bom needs an assembly (.SLDASM); a part has no BOM",
            )
        stem = os.path.splitext(os.path.basename(path))[0]
        rev = (revision or "A").strip()
        number = drawing_number or f"{stem.upper().replace(' ', '-')}-Rev{rev}-01"
        out_dir = os.path.abspath(output_dir or os.path.dirname(path))
        drawing_path = os.path.join(out_dir, f"{number}.SLDDRW")
        pdf_path = os.path.join(out_dir, f"{number}.pdf")
        steps: list[dict[str, Any]] = []
        written: dict[str, dict[str, str]] = {}
        data: dict[str, Any] = {"drawing_number": number, "steps": steps}

        def failed(error: str) -> AdapterResult[dict[str, Any]]:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=error, data=data
            )

        # 1. The model: open it, read its material, write the title-block properties.
        active = self._handle_com_operation(
            "activate_document", lambda: self._use_open_document(path)
        )
        if not (active.is_success and active.data):
            opened = await self.open_model(path)
            if not opened.is_success:
                return failed(
                    f"Could not open model: {opened.error}. If a different file "
                    "with the same name is open in SolidWorks, close it first."
                )
        material = None
        if ext == ".sldprt":
            mat = await self.get_material()
            material = (mat.data or {}).get("material") if mat.is_success else None
        model_props, drawing_props = title_block_properties(
            model_file=path,
            title=title or stem,
            subtitle=subtitle,
            author=author,
            drawn_date=drawn_date or _date.today().strftime("%d %b %Y"),
            revision=rev,
            company=company,
        )
        if ext == ".sldasm":
            # An assembly has no material of its own: a link to it shows
            # "<not specified>". Its own Material property is left as set.
            model_props.pop("Material")
        if write_model_properties:
            for name, value in model_props.items():
                _step(
                    steps,
                    f"model_property:{name}",
                    await self.set_custom_property(name, value),
                )
            _step(steps, "save_model", await self.save_file())
            written["model"] = model_props

        # 2. A drawing on the A3 ISO format, without the Sheet Format/Size prompt.
        found = self._handle_com_operation(
            "standard_drawing_format", lambda: find_sheet_format(self)
        )
        if not (found.is_success and found.data):
            return failed(
                "Sheet format 'a3 - iso.slddrt' not found in SolidWorks' sheet "
                "format folders or under C:\\ProgramData\\SOLIDWORKS"
            )
        prompt = self._handle_com_operation(
            "standard_drawing_dialog", self._new_drawing_without_dialog
        )
        try:
            created = await self.create_drawing()
        finally:
            self._handle_com_operation(
                "standard_drawing_dialog",
                lambda: self._restore_dialog(
                    prompt.data if prompt.is_success else None
                ),
            )
        if not created.is_success:
            return failed(f"Could not create drawing: {created.error}")
        _step(steps, "drawing_units_mm", await self.set_units("mm"))

        # 3. The sheet, one COM step at a time.
        s = _Sheet(
            path=path,
            sheet_format=str(found.data),
            include_isometric=include_isometric,
            include_bom=include_bom,
            material=material,
            extra_notes=list(notes or []),
            field_height=(
                title_block_text_height_mm / 1000.0
                if title_block_text_height_mm
                else None
            ),
        )
        for name, build in (
            ("sheet", self._setup_a3_sheet),
            ("views", self._create_views),
            ("layout", self._fit_views),
            ("bom", self._bom_above_iso),
            ("dimensions", self._dimension_views),
            ("notes", self._annotate),
            ("check", self._check_sheet),
        ):
            done = self._handle_com_operation(
                f"standard_drawing_{name}", lambda build=build: build(s)
            )
            _step(steps, f"build_{name}", done)
            if not done.is_success:
                return failed(f"Drawing step '{name}' failed: {done.error}")
            if name == "dimensions":
                data["dimensions"] = done.data
            if name == "bom":
                data["bom"] = done.data
            if name == "views":
                data["hidden_lines_visible"] = done.data["hidden_lines_visible"]
            if name == "check":
                data["overlap_check"] = done.data
        data.update(
            {
                "scale": scale_label(s.scale),
                "isometric_scale": scale_label(s.iso_scale) if s.iso_scale else None,
                "views": {
                    n: {"role": s.role.get(n), "caption": s.captions.get(n)}
                    for n in s.views
                },
                "sheet_format": s.sheet_format,
                "notes": s.note_lines,
            }
        )

        # 4. Drawing properties, then the files.
        for name, value in drawing_props.items():
            _step(
                steps,
                f"drawing_property:{name}",
                await self.set_custom_property(name, value),
            )
        written["drawing"] = drawing_props
        data["properties_written"] = written
        os.makedirs(out_dir, exist_ok=True)
        saved = await self.save_file(drawing_path)
        _step(steps, "save_drawing", saved)
        data["drawing_path"] = drawing_path if saved.is_success else None
        if not saved.is_success:
            return failed(
                f"Drawing built but not saved to {drawing_path}: {saved.error}"
            )

        # 5. The title block, now that the DWG NO. shows the saved file name.
        fitted = self._handle_com_operation(
            "standard_drawing_title_block", lambda: self._fit_title_block(s)
        )
        _step(steps, "fit_title_block", fitted)
        data["title_block"] = fitted.data if fitted.is_success else None
        data["format_links"] = s.format_links
        check = data["overlap_check"]
        for name, field_fit in (data["title_block"] or {}).items():
            if field_fit.get("fits") is False:
                check["annotation_overlaps"].append(
                    {
                        "dimension": f"title block {name}",
                        "conflicts_with": "the next title-block field",
                        "kind": "field_overflow",
                    }
                )
                check["overlaps_after"] = check.get("overlaps_after", 0) + 1
        _step(steps, "save_drawing_again", await self.save_file(drawing_path))
        pdf = await self.export_file(pdf_path, "pdf")
        _step(steps, "export_pdf", pdf)
        data["pdf_path"] = pdf_path if pdf.is_success else None
        if not pdf.is_success:
            return failed(
                f"Drawing saved to {drawing_path} but the PDF export failed: {pdf.error}"
            )

        overlaps = data["overlap_check"].get("overlaps_after", 0)
        overflowing = any(
            f.get("fits") is False for f in (data.get("title_block") or {}).values()
        )
        if overlaps:
            check = data["overlap_check"]
            found = [
                *check.get("remaining_overlaps", []),
                *check.get("annotation_overlaps", []),
            ]
            named = "; ".join(
                f"{o['dimension']} vs {o['conflicts_with']} ({o['kind']})"
                for o in found[:5]
            )
            return failed(
                f"Drawing saved but {overlaps} overlap(s) remain - the no-overlap "
                "rule is not met; see overlap_check"
                + (f": {named}" if named else "")
                + (f". For a title-block field, {FIELD_HINT}" if overflowing else "")
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)
