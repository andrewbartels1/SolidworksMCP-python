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
  Each view gets a bold capital caption with its name, e.g. ``FRONT ELEVATION``.
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
import os
from dataclasses import dataclass, field
from datetime import date as _date
from typing import TYPE_CHECKING, Any

from ..base import AdapterResult, AdapterResultStatus
from . import dimension_layout as _layout
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
    "front": "FRONT ELEVATION",
    "plan": "PLAN",
    "side": "SIDE ELEVATION",
    "iso": "ISOMETRIC",
}
#: Caption strip at the bottom of every view cell.
CAPTION_STRIP = 0.009
CAPTION_HEIGHT = 0.0032
NOTE_HEIGHT = 0.003
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

# swUserPreferenceToggle_e / IntegerValue_e / StringValue_e (swconst.tlb,
# SW 2025; unchanged on SW 2026)
_SW_SHOW_SHEET_FORMAT_DIALOG = 353
_SW_DETAILING_DIM_TRAILING_ZERO = 15
_SW_DIM_REMOVE_TRAILING_ZEROES = 2
_SW_PREF_SHEET_FORMAT_FOLDER = 7
# swDwgPaperSizes_e / swDwgTemplates_e
_SW_PAPER_A3 = 8
_SW_TEMPLATE_CUSTOM = 12
#: Where the isometric view is first dropped, before it is moved to its cell.
_ISO_DROP_POINT = (0.31, 0.23)


def _double_array(values: list[float]) -> Any:
    """``VARIANT(VT_ARRAY | VT_R8)`` for array-valued COM properties.

    Falls back to a plain tuple when pywin32 is not installed.
    """
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values]
        )
    except ImportError:
        return tuple(values)


def scale_label(scale: tuple[float, float]) -> str:
    """``(1, 2)`` -> ``"1:2"``, ``(2.5, 1)`` -> ``"2.5:1"``."""
    return f"{scale[0]:g}:{scale[1]:g}"


def content_box(cell: Box) -> Box:
    """The part of a view cell left after the caption strip."""
    return (cell[0], cell[1] + CAPTION_STRIP, cell[2], cell[3])


#: Area for the four view cells: full width above the notes and title block.
VIEW_ZONE: Box = (0.015, 0.075, 0.405, 0.282)
#: Room for dimensions each side of a view when sizing cells: the first row
#: (8 mm) plus one more row/column. Tight on purpose - the real overlap check
#: decides.
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

    Returns:
        dict[str, Box] | None: Cells for ``front``, ``side``, ``plan``,
        ``iso`` and ``notes``; ``None`` without a front view or when the
        part does not fit at this scale.
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
        sizes: View sizes at 1:1, as for :func:`plan_cells`.

    Returns:
        tuple: The scale and its cells. A part too big for every standard
        scale gets the smallest one and the fixed :data:`CELLS`.
    """
    for scale in STANDARD_SCALES:
        cells = plan_cells(sizes, scale)
        if cells is not None:
            return scale, cells
    return STANDARD_SCALES[-1], dict(CELLS)


def iso_fit_scale(size: tuple[float, float], cell: Box) -> tuple[float, float]:
    """Largest standard scale at which the isometric view fills its cell.

    Args:
        size: The isometric view's size at 1:1.
        cell: Its cell.

    Returns:
        tuple[float, float]: A scale from :data:`STANDARD_SCALES`.
    """
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
    real values. TITLE stays short so it fits its box; ``subtitle`` fills the
    company field when no company is given.

    Args:
        model_file: The model's path.
        title: TITLE.
        author: DRAWN name.
        drawn_date: DRAWN date.
        revision: Revision letter.
        company: Company name.
        subtitle: Second line, used when ``company`` is empty.

    Returns:
        tuple: (model properties, drawing properties); empty drawing
        properties are left out.
    """
    base = os.path.basename(model_file)
    model_props = {
        "Description": title,
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


def find_sheet_format(adapter: Any, name: str = "a3 - iso.slddrt") -> str | None:
    """Locate a sheet format file: SolidWorks' configured folder, then ProgramData.

    Args:
        adapter: The adapter; its ``swApp`` gives the configured folders.
        name: The sheet format file.

    Returns:
        str | None: The file's path, or ``None`` when no folder has it.
    """
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


@dataclass
class _Sheet:
    """What the generator's steps share while they build one drawing.

    Attributes:
        path: The model being drawn.
        sheet_format: The ``.slddrt`` applied to the sheet.
        include_isometric: Whether to add the isometric view.
        material: The part's material, for the notes.
        extra_notes: The caller's note lines.
        views: View name -> ``IView``, orthographic first.
        role: View name -> ``front``, ``plan``, ``side`` or ``iso``.
        ortho: The orthographic view names.
        iso_name: The isometric view's name, when one was made.
        scale: The sheet scale.
        cells: Role -> cell on the sheet.
        iso_scale: The isometric view's own scale.
        captions: View name -> caption text.
        notes: ``(label, IAnnotation)`` for every caption and note line.
        note_lines: The NOTES block's text.
        title_block: Field name -> how it was fitted to its box.
        field_height: The caller's cap on the fitted fields' text height.
    """

    path: str
    sheet_format: str
    include_isometric: bool = True
    material: str | None = None
    extra_notes: list[str] = field(default_factory=list)
    views: dict[str, Any] = field(default_factory=dict)
    role: dict[str, str] = field(default_factory=dict)
    ortho: list[str] = field(default_factory=list)
    iso_name: str | None = None
    scale: tuple[float, float] = (1, 1)
    cells: dict[str, Box] = field(default_factory=dict)
    iso_scale: tuple[float, float] | None = None
    captions: dict[str, str] = field(default_factory=dict)
    notes: list[tuple[str, Any]] = field(default_factory=list)
    note_lines: list[str] = field(default_factory=list)
    title_block: dict[str, dict[str, Any]] = field(default_factory=dict)
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
    """Create complete standard A3 drawings."""

    if TYPE_CHECKING:
        currentModel: Any
        swApp: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], default: Any = None
        ) -> Any: ...

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

    def _obstacles(self, s: _Sheet) -> dict[str, Box]:
        """What dimensions must keep clear of: title block, notes, captions."""
        result: dict[str, Box] = {"title block": TITLE_BLOCK, "notes": s.cells["notes"]}
        for r in s.role.values():
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
        return {"views": dict(s.role)}

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
        if s.iso_name and iso_size:
            s.iso_scale = iso_fit_scale(iso_size, s.cells["iso"])
            iso = s.views[s.iso_name]
            ratio = _double_array([float(s.iso_scale[0]), float(s.iso_scale[1])])
            self._attempt(lambda: setattr(iso, "UseSheetScale", False), default=None)
            self._attempt(lambda: setattr(iso, "ScaleRatio", ratio), default=None)
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

    def _dimension_views(self, s: _Sheet) -> dict[str, Any]:
        """Import the model dimensions and lay them out clear of everything."""
        dims = self._import_dimensions(None, True, only_views=list(s.ortho))
        self._arrange_layout(None, self._obstacles(s), WORK_AREA)
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

    def _check_sheet(self, s: _Sheet) -> dict[str, Any]:
        """Check the finished sheet: dimensions, captions and notes, read back."""
        final = self._arrange_layout(None, self._obstacles(s), WORK_AREA, move=False)
        drawing = self._drawing()
        outlines, dims, _ = self._collect_layout(drawing, _view_names(self, drawing))
        boxes = {
            label: self._note_box(an, label, 0.0, 0.0, NOTE_HEIGHT)
            for label, an in s.notes
        }
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
            return failed(
                f"Drawing saved but {overlaps} overlap(s) remain - the no-overlap "
                "rule is not met; see overlap_check"
                + (f". For a title-block field, {FIELD_HINT}" if overflowing else "")
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)
