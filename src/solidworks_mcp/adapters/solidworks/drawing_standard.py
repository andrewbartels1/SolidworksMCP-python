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
* **No overlap anywhere** - checked against the real read-back geometry.
  The scale is chosen once to fit the sheet and is never stepped down;
  overlaps are resolved by moving dimensions.
"""

from __future__ import annotations

import glob
import os
from datetime import date as _date
from typing import TYPE_CHECKING, Any, cast

from ..base import AdapterResult, AdapterResultStatus
from . import dimension_layout as _layout
from .io import _as_com, _resolve_drawing_view, _sw_type_info, _view_names

if TYPE_CHECKING:  # pragma: no cover
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

# swUserPreferenceToggle_e / IntegerValue_e / StringValue_e (swconst.tlb, SW 2025)
_SW_SHOW_SHEET_FORMAT_DIALOG = 353
_SW_DETAILING_DIM_TRAILING_ZERO = 15
_SW_DIM_REMOVE_TRAILING_ZEROES = 2
_SW_PREF_SHEET_FORMAT_FOLDER = 7
# swDwgPaperSizes_e / swDwgTemplates_e
_SW_PAPER_A3 = 8
_SW_TEMPLATE_CUSTOM = 12


def _double_array(values: list[float]) -> Any:
    """``VARIANT(VT_ARRAY | VT_R8)`` for array-valued COM properties (tuple when pywin32 is absent)."""
    try:
        import pythoncom
        import win32com.client as w32

        return w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values]
        )
    except ImportError:  # pragma: no cover - non-Windows
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
#: decides, and a failed check falls back to the next smaller scale.
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
    start_after: tuple[float, float] | None = None,
) -> tuple[tuple[float, float], dict[str, Box]]:
    """Largest standard scale whose cells fit, with those cells."""
    scales = STANDARD_SCALES
    if start_after is not None and start_after in scales:
        scales = scales[scales.index(start_after) + 1 :]
    for scale in scales:
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
    base = os.path.basename(model_file)
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


class SolidWorksDrawingStandardMixin:
    """Create complete standard A3 drawings."""

    if TYPE_CHECKING:  # pragma: no cover
        currentModel: Any
        swApp: Any

        def _handle_com_operation(
            self, operation_name: str, operation: Callable[..., Any], *args: Any
        ) -> AdapterResult[Any]: ...

        def _attempt(
            self, operation: Callable[[], Any], default: Any = None
        ) -> Any: ...

    # -- small COM helpers ---------------------------------------------

    def _set_view_position(self, view: Any, x: float, y: float) -> bool:
        """Move a view's centre to (x, y) and confirm by reading it back.

        A plain tuple is mis-marshalled under late binding (x arrives as
        ~1e-310 and the view stays off the sheet); an explicit
        ``VARIANT(VT_ARRAY | VT_R8)`` works - measured live on SW 2025.
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
        """Make an already-open copy of ``path`` the active model, if there is one."""
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
        raw = self._attempt(lambda: view.GetOutline(), default=None)
        if isinstance(raw, (list, tuple)) and len(raw) >= 4:
            return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        return None

    def _insert_sheet_note(
        self, text: str, x: float, y: float, height: float, bold: bool
    ) -> Any:
        """Insert a sheet note with its top-left at (x, y); returns the IAnnotation."""
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
        """Shift a note so its measured box meets the given edges; return the box."""
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
        geometry = self._attempt(
            lambda: self._dimension_geometry(an, "note", "sheet"), default=None
        )
        if geometry is not None:
            return geometry.text_box
        width = 0.62 * height * len(fallback_text)
        return (x, y - height, x + width, y)

    # -- the generator --------------------------------------------------

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
    ) -> AdapterResult[dict[str, Any]]:
        """Create a complete A3 drawing that follows the drawing standard.

        Args:
            model_path: Part (.SLDPRT) or assembly (.SLDASM) to draw.
            output_dir: Folder for the .SLDDRW and PDF; the model's folder by default.
            title: Title block TITLE; the model file name by default.
            subtitle: Sheet title appended to the TITLE, e.g. "Base support".
            drawing_number: DWG NO.; also the drawing file name. Default
                ``<MODEL>-Rev<revision>-01``.
            author: DRAWN name.
            revision: Revision letter.
            company: Company name field.
            drawn_date: DRAWN date; today (e.g. "17 Oct 2026") by default.
            notes: Extra note lines (3-7 lines in total are expected).
            include_isometric: Add the isometric view in its cell.
            write_model_properties: Write Description/Material/Weight custom
                properties into the model (the format reads them from there)
                and save the model.

        Returns:
            AdapterResult[dict[str, Any]]: Files, scale, views, dimension
            counts, the overlap check and every property written.
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
                error="model_path must be a .SLDPRT or .SLDASM",
            )
        stem = os.path.splitext(os.path.basename(path))[0]
        rev = (revision or "A").strip()
        number = drawing_number or f"{stem.upper().replace(' ', '-')}-Rev{rev}-01"
        out_dir = os.path.abspath(output_dir or os.path.dirname(path))
        drawing_path = os.path.join(out_dir, f"{number}.SLDDRW")
        pdf_path = os.path.join(out_dir, f"{number}.pdf")
        today = drawn_date or _date.today().strftime("%d %b %Y")
        steps: list[dict[str, Any]] = []
        written: dict[str, dict[str, str]] = {}

        # 1. Model: properties the title block reads, and the material name.
        if not self._use_open_document(path):
            opened = await self.open_model(path)  # type: ignore[attr-defined]
            if not opened.is_success:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error=(
                        f"Could not open model: {opened.error}. If a different file "
                        "with the same name is open in SolidWorks, close it first."
                    ),
                )
        material = None
        if ext == ".sldprt":
            mat = await self.get_material()  # type: ignore[attr-defined]
            material = (mat.data or {}).get("material") if mat.is_success else None
        model_props, drawing_props = title_block_properties(
            model_file=path,
            title=title or stem,
            subtitle=subtitle,
            author=author,
            drawn_date=today,
            revision=rev,
            company=company,
        )
        if write_model_properties:
            for name, value in model_props.items():
                r = await self.set_custom_property(name, value)  # type: ignore[attr-defined]
                steps.append(
                    {
                        "step": f"model_property:{name}",
                        "status": "success" if r.is_success else "error",
                        "error": r.error,
                    }
                )
            saved_model = await self.save_file()  # type: ignore[attr-defined]
            steps.append(
                {
                    "step": "save_model",
                    "status": "success" if saved_model.is_success else "error",
                    "error": saved_model.error,
                }
            )
            written["model"] = model_props

        # 2. Drawing on the A3 ISO format, without the sheet-format prompt.
        fmt = find_sheet_format(self)
        if fmt is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="Sheet format 'a3 - iso.slddrt' not found",
            )
        app = self.swApp
        previous = self._attempt(
            lambda: app.GetUserPreferenceToggle(_SW_SHOW_SHEET_FORMAT_DIALOG),
            default=None,
        )
        self._attempt(
            lambda: app.SetUserPreferenceToggle(_SW_SHOW_SHEET_FORMAT_DIALOG, False),
            default=None,
        )
        try:
            created = await self.create_drawing()  # type: ignore[attr-defined]
        finally:
            if previous is not None:
                self._attempt(
                    lambda: app.SetUserPreferenceToggle(
                        _SW_SHOW_SHEET_FORMAT_DIALOG, bool(previous)
                    ),
                    default=None,
                )
        if not created.is_success:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Could not create drawing: {created.error}",
            )
        units = await self.set_units("mm")  # type: ignore[attr-defined]
        steps.append(
            {
                "step": "drawing_units_mm",
                "status": "success" if units.is_success else "error",
                "error": units.error,
            }
        )

        def _build() -> dict[str, Any]:
            model = self.currentModel
            drawing = _sw_type_info.flagged(model, "IDrawingDoc")
            sheet = _as_com(self, drawing.GetCurrentSheet(), "ISheet")
            sheet_name = self._attempt(lambda: sheet.GetName(), default="Sheet1")
            if not drawing.SetupSheet5(
                sheet_name,
                _SW_PAPER_A3,
                _SW_TEMPLATE_CUSTOM,
                1.0,
                1.0,
                False,
                fmt,
                SHEET_SIZE[0],
                SHEET_SIZE[1],
                "Default",
                True,
            ):
                raise Exception(f"SetupSheet5 failed for {fmt}")
            self._attempt(
                lambda: model.SetUserPreferenceIntegerValue(
                    _SW_DETAILING_DIM_TRAILING_ZERO, _SW_DIM_REMOVE_TRAILING_ZEROES
                ),
                default=None,
            )
            before = set(_view_names(self, drawing))
            if not self._attempt(
                lambda: drawing.Create3rdAngleViews2(path), default=False
            ):
                new = [n for n in _view_names(self, drawing) if n not in before]
                if not new:
                    raise Exception(f"No views could be created from {path}")
            ortho = [n for n in _view_names(self, drawing) if n not in before]
            views = {n: _resolve_drawing_view(self, drawing, n) for n in ortho}
            outlines = {n: self._view_outline(v) for n, v in views.items()}
            front = next(
                (
                    n
                    for n, v in views.items()
                    if "front"
                    in str(
                        self._attempt(lambda v=v: v.GetOrientationName(), default="")
                    ).lower()
                ),
                ortho[0],
            )
            fo = outlines[front]
            role: dict[str, str] = {front: "front"}
            for n in ortho:
                if n == front or outlines.get(n) is None or fo is None:
                    continue
                o = outlines[n]
                role[n] = (
                    "plan" if (o[1] + o[3]) / 2 > (fo[1] + fo[3]) / 2 + 1e-4 else "side"
                )
            iso_name = None
            if include_isometric:
                before_iso = set(_view_names(self, drawing))
                self._attempt(
                    lambda: drawing.CreateDrawViewFromModelView3(
                        path, "*Isometric", 0.31, 0.23, 0.0
                    ),
                    default=None,
                )
                iso_name = next(
                    (n for n in _view_names(self, drawing) if n not in before_iso), None
                )
                if iso_name:
                    views[iso_name] = _resolve_drawing_view(self, drawing, iso_name)
                    role[iso_name] = "iso"

            def sizes_now() -> dict[str, tuple[float, float]]:
                result = {}
                for n, v in views.items():
                    o = self._view_outline(v)
                    s = float(
                        self._attempt(lambda v=v: v.ScaleDecimal, default=1.0) or 1.0
                    )
                    if o is not None and s > 0:
                        result[role[n]] = ((o[2] - o[0]) / s, (o[3] - o[1]) / s)
                return result

            model_sizes = sizes_now()
            ortho_sizes = {k: v for k, v in model_sizes.items() if k != "iso"}
            # Isometric size at 1:1 (outline / view scale), for its own fit.
            iso_size = model_sizes.get("iso")

            def apply_layout(
                scale: tuple[float, float], cells: dict[str, Box]
            ) -> tuple[float, float] | None:
                sheet.SetScale(float(scale[0]), float(scale[1]), True, False)
                self._attempt(lambda: model.EditRebuild3(), default=None)
                iso_scale = None
                if iso_name and iso_size:
                    iso_scale = iso_fit_scale(iso_size, cells["iso"])
                    iv = views[iso_name]
                    self._attempt(
                        lambda: setattr(iv, "UseSheetScale", False), default=None
                    )
                    self._attempt(
                        lambda: setattr(
                            iv,
                            "ScaleRatio",
                            _double_array([float(iso_scale[0]), float(iso_scale[1])]),
                        ),
                        default=None,
                    )
                # Centre each view in its cell's content area (front first:
                # plan and side follow its alignment along one axis).
                fc = content_box(cells["front"])
                fcx, fcy = (fc[0] + fc[2]) / 2, (fc[1] + fc[3]) / 2
                for n, r in sorted(role.items(), key=lambda item: item[1] != "front"):
                    c = content_box(cells[r])
                    x, y = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
                    if r == "plan":
                        x = fcx
                    elif r == "side":
                        y = fcy
                    self._set_view_position(views[n], x, y)
                self._attempt(lambda: model.EditRebuild3(), default=None)
                return iso_scale

            def obstacles_for(cells: dict[str, Box]) -> dict[str, Box]:
                result: dict[str, Box] = {
                    "title block": TITLE_BLOCK,
                    "notes": cells["notes"],
                }
                for r in role.values():
                    c = cells[r]
                    result[f"{r} caption"] = (c[0], c[1], c[2], c[1] + CAPTION_STRIP)
                return result

            scale, cells = choose_layout(ortho_sizes)
            iso_scale = apply_layout(scale, cells)
            dims = self._insert_dimensions_sync(drawing, model, list(ortho))

            # The scale is chosen once, to fit the sheet, and never stepped down:
            # overlaps are resolved by moving dimensions, not by shrinking views.
            obstacles = obstacles_for(cells)
            self._arrange_sync(drawing, model, ortho, obstacles, WORK_AREA)

            # Captions (view name only) and notes. Each note is placed from
            # its measured box, so lines cannot run into each other.
            labels: dict[str, str] = {}
            sheet_notes: list[tuple[str, Any]] = []
            for n, r in role.items():
                text = CAPTIONS[r]
                c = cells[r]
                an = self._insert_sheet_note(
                    text, c[0] + 0.01, c[1] + CAPTION_STRIP, CAPTION_HEIGHT, True
                )
                labels[n] = text
                if an is not None:
                    self._place_note(
                        an, text, centre_x=(c[0] + c[2]) / 2, bottom=c[1] + 0.0015
                    )
                    sheet_notes.append((f"caption {r}", an))
            body = []
            if material:
                body.append(f"MATERIAL: {material.upper()}")
            body += [
                "ALL DIMENSIONS IN MILLIMETRES",
                "THIRD ANGLE PROJECTION",
                "REMOVE ALL BURRS AND SHARP EDGES",
            ]
            body += [line.upper() for line in (notes or []) if line.strip()]
            note_lines = ["NOTES"] + [
                f"{i}. {line}" for i, line in enumerate(body[:7], start=1)
            ]
            nc = CELLS["notes"]
            top = nc[3] - 0.003
            for i, line in enumerate(note_lines):
                height = CAPTION_HEIGHT if i == 0 else NOTE_HEIGHT
                an = self._insert_sheet_note(line, nc[0] + 0.010, top, height, i == 0)
                if an is None:
                    continue
                box = self._place_note(an, line, left=nc[0] + 0.010, top=top)
                sheet_notes.append((f"note line {i}", an))
                top = box[1] - 0.0015
            self._attempt(lambda: model.ClearSelection2(True), default=None)
            self._attempt(lambda: model.EditRebuild3(), default=None)

            final = self._arrange_sync(
                drawing, model, ortho, obstacles, WORK_AREA, move=False
            )
            outlines_now, dims_now, _ = self._collect_layout(
                drawing, _view_names(self, drawing)
            )
            note_boxes = {
                label: self._note_box(an, label, 0.0, 0.0, NOTE_HEIGHT)
                for label, an in sheet_notes
            }
            annotation_problems = _layout.find_annotation_overlaps(
                note_boxes,
                dims_now,
                outlines_now,
                WORK_AREA,
                {"title block": TITLE_BLOCK},
            )
            final["annotation_overlaps"] = annotation_problems
            final["overlaps_after"] = final.get("overlaps_after", 0) + len(
                annotation_problems
            )
            return {
                "scale": scale_label(scale),
                "isometric_scale": scale_label(iso_scale) if iso_scale else None,
                "views": {
                    n: {"role": role[n], "caption": labels.get(n)} for n in views
                },
                "dimensions": dims,
                "overlap_check": final,
                "sheet_format": fmt,
                "notes": note_lines,
            }

        built = self._handle_com_operation("create_standard_drawing", _build)
        if not built.is_success:
            return cast("AdapterResult[dict[str, Any]]", built)
        data = dict(built.data or {})

        for name, value in drawing_props.items():
            r = await self.set_custom_property(name, value)  # type: ignore[attr-defined]
            steps.append(
                {
                    "step": f"drawing_property:{name}",
                    "status": "success" if r.is_success else "error",
                    "error": r.error,
                }
            )
        written["drawing"] = drawing_props

        os.makedirs(out_dir, exist_ok=True)
        saved = await self.save_file(drawing_path)  # type: ignore[attr-defined]
        steps.append(
            {
                "step": "save_drawing",
                "status": "success" if saved.is_success else "error",
                "error": saved.error,
            }
        )
        pdf = await self.export_file(pdf_path, "pdf")  # type: ignore[attr-defined]
        steps.append(
            {
                "step": "export_pdf",
                "status": "success" if pdf.is_success else "error",
                "error": pdf.error,
            }
        )

        overlaps = (data.get("overlap_check") or {}).get("overlaps_after", 0)
        data.update(
            {
                "drawing_path": drawing_path if saved.is_success else None,
                "pdf_path": pdf_path if pdf.is_success else None,
                "drawing_number": number,
                "properties_written": written,
                "steps": steps,
            }
        )
        if overlaps:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"Drawing saved but {overlaps} overlap(s) remain - the no-overlap rule is not met",
                data=data,
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)
