"""Tests for the A3 drawing generator: its COM steps and the title-block fit.

The sheet maths, BOM and scale methods are in ``test_drawing_standard.py``.

The generator runs against a fake SolidWorks: ``Create3rdAngleViews2`` adds
a front, plan and side view, notes report a box from where they sit, and the
app keeps the Sheet Format/Size prompt toggle so the test can see it restored.
The adapter methods the generator borrows from other mixins (open, material,
properties, save, export, dimensions, layout) are recorded stand-ins; they
have their own tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import dimension_layout as lay
from solidworks_mcp.adapters.solidworks import drawing_standard as std

OK = AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)


def _error(message: str) -> AdapterResult[Any]:
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


# ---- layout maths -----------------------------------------------------------------


class TestNotes:
    def test_note_overlaps_are_reported(self) -> None:
        notes = {
            "NOTES": (0.02, 0.06, 0.05, 0.065),
            "line 1": (0.02, 0.062, 0.09, 0.066),
        }
        problems = lay.find_annotation_overlaps(
            notes, [], {}, None, {"title block": std.TITLE_BLOCK}
        )
        assert [p["kind"] for p in problems] == ["note_on_note"]

    def test_notes_start_with_the_material_and_stop_at_seven_lines(self) -> None:
        lines = std.note_lines("aisi 1020", ["laser cut", " ", *"abcde"])

        assert lines[:3] == [
            "NOTES",
            "1. MATERIAL: AISI 1020",
            "2. ALL DIMENSIONS IN MILLIMETRES",
        ]
        assert lines[5] == "5. LASER CUT"
        assert len(lines) == 1 + std.MAX_NOTE_LINES

    def test_notes_without_a_material(self) -> None:
        assert std.note_lines(None, None)[1] == "1. ALL DIMENSIONS IN MILLIMETRES"


class TestViewRoles:
    FRONT = (0.1, 0.1, 0.16, 0.13)

    def test_front_by_orientation_plan_above_side_beside(self) -> None:
        views = {"V1": 1, "V2": 2, "V3": 3, "V4": 4}
        outlines = {
            "V1": (0.1, 0.17, 0.16, 0.2),
            "V2": self.FRONT,
            "V3": (0.2, 0.1, 0.23, 0.13),
            "V4": None,
        }
        orientations = {"V2": "*Front"}

        assert std.view_roles(views, outlines, orientations) == {
            "V2": "front",
            "V1": "plan",
            "V3": "side",
        }

    def test_the_first_view_is_the_front_when_none_says_so(self) -> None:
        roles = std.view_roles({"A": 1, "B": 2}, {"A": None, "B": self.FRONT}, {})
        assert roles == {"A": "front"}


# ---- fake SolidWorks ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _plain_com(monkeypatch) -> None:
    """Fake objects need no flagging; views come from the fake drawing."""
    monkeypatch.setattr(
        std, "_sw_type_info", SimpleNamespace(flagged=lambda obj, *_: obj)
    )
    monkeypatch.setattr(std, "_as_com", lambda _adapter, obj, _iface: obj)
    monkeypatch.setattr(std, "_view_names", lambda _a, drawing: list(drawing.views))
    monkeypatch.setattr(
        std, "_resolve_drawing_view", lambda _a, drawing, name: drawing.views.get(name)
    )


class _View:
    def __init__(
        self, outline: Any, orientation: str = "", garble: bool = False
    ) -> None:
        self.outline = outline
        self.orientation = orientation
        self.garble = garble
        self.ScaleDecimal = 1.0
        self.UseSheetScale = True
        self.ScaleRatio = None
        self._position: Any = None
        self.display_mode = 2  # hidden lines removed, SolidWorks' default here

    def SetDisplayMode4(self, _use_parent, mode, *_flags):  # noqa: N802
        if self.orientation != "*Locked":
            self.display_mode = mode
        return True

    def GetDisplayMode2(self):  # noqa: N802
        return self.display_mode

    def GetOutline(self):  # noqa: N802
        return self.outline

    def GetOrientationName(self):  # noqa: N802
        return self.orientation

    @property
    def Position(self):  # noqa: N802
        return self._position

    @Position.setter
    def Position(self, value):  # noqa: N802
        x, y = getattr(value, "value", value)
        self._position = (1e-310, y) if self.garble else (x, y)


class _Annotation:
    def __init__(self, text: str) -> None:
        self.text = text
        self.position = (0.0, 0.0, 0.0)
        self.format = SimpleNamespace(CharHeight=0.0, Bold=False)

    def GetTextFormat(self, _index):  # noqa: N802
        return self.format

    def SetTextFormat(self, *_args):  # noqa: N802
        return True

    def SetPosition(self, x, y, z):  # noqa: N802
        self.position = (x, y, z)
        return True

    def GetPosition(self):  # noqa: N802
        return self.position


class _Sheet:
    def __init__(self) -> None:
        self.scale = None

    def GetName(self):  # noqa: N802
        return "Sheet1"

    def SetScale(self, num, den, *_args):  # noqa: N802
        self.scale = (num, den)
        return True


class _FormatNote:
    """A sheet-format note whose width grows with its text height."""

    def __init__(
        self, text: str, linked: str, x: float, y: float, height: float
    ) -> None:
        self.text = text
        self.PropertyLinkedText = linked
        self.x, self.y = x, y
        self.format = SimpleNamespace(CharHeight=height)
        self.next: Any = None

    def GetExtent(self):  # noqa: N802
        height = self.format.CharHeight
        return (
            self.x,
            self.y,
            0.0,
            self.x + 0.8 * height * len(self.text),
            self.y + height,
            0.0,
        )

    def GetTextFormat(self):  # noqa: N802
        return self.format

    def SetTextFormat(self, _kind, text_format):  # noqa: N802
        self.format = text_format
        return True

    def GetNext(self):  # noqa: N802
        return self.next


def _title_block(drawing_number: str = "MOUNTING-PLATE-RevA-01") -> list[_FormatNote]:
    """The ISO title block's notes: DWG NO. runs into the size box at 7 mm."""
    return [
        _FormatNote("DWG NO.", "", 0.249, 0.028, 0.002),  # the label above
        _FormatNote(drawing_number, '$PRP:"SW-File Name"', 0.25, 0.02, 0.007),
        _FormatNote("A3", "", 0.33, 0.021, 0.005),  # the size box
        _FormatNote("Mounting Plate", '$PRPSHEET:"Description"', 0.23, 0.045, 0.005),
    ]


class _Drawing:
    """A drawing: views are added by the view-creation calls."""

    def __init__(
        self,
        *,
        accepts_format: bool = True,
        views: str = "three",
        format_notes: list[_FormatNote] | None = None,
    ) -> None:
        self.accepts_format = accepts_format
        self.make = views
        self.views: dict[str, _View] = {}
        self.sheet = _Sheet()
        self.notes: list[_Annotation] = []
        self.preferences: dict[int, Any] = {}
        self.format_notes = _title_block() if format_notes is None else format_notes
        for note, after in zip(self.format_notes, self.format_notes[1:], strict=False):
            note.next = after
        self.editing = "sheet"

    def EditTemplate(self):  # noqa: N802
        self.editing = "format"

    def EditSheet(self):  # noqa: N802
        self.editing = "sheet"

    def GetFirstView(self):  # noqa: N802
        first = self.format_notes[0] if self.format_notes else None
        return SimpleNamespace(GetFirstNote=lambda: first)

    def GetType(self):  # noqa: N802
        return 3

    def GetCurrentSheet(self):  # noqa: N802
        return self.sheet

    def SetupSheet5(self, *args):  # noqa: N802
        self.setup = args
        return self.accepts_format

    def SetUserPreferenceIntegerValue(self, pref, value):  # noqa: N802
        self.preferences[pref] = value

    def Create3rdAngleViews2(self, _path):  # noqa: N802
        if self.make == "none":
            return False
        self.views["Drawing View1"] = _View((0.1, 0.1, 0.16, 0.13), "*Front")
        self.views["Drawing View2"] = _View((0.1, 0.17, 0.16, 0.2), "*Top")
        self.views["Drawing View3"] = _View((0.2, 0.1, 0.23, 0.13), "*Right")
        return True

    def CreateDrawViewFromModelView3(self, *_args):  # noqa: N802
        if self.make != "no iso":
            self.views["Drawing View4"] = _View((0.28, 0.2, 0.34, 0.25), "*Isometric")

    def InsertNote(self, text):  # noqa: N802
        if self.make == "no notes":
            return None
        an = _Annotation(text)
        self.notes.append(an)
        return SimpleNamespace(GetAnnotation=lambda: an)

    def ClearSelection2(self, _all):  # noqa: N802
        return None

    def EditRebuild3(self):  # noqa: N802
        return True


class _App:
    def __init__(self, folder: str, open_doc: Any = None) -> None:
        self.folder = folder
        self.open_doc = open_doc
        self.prompt = True
        self.activated: list[str] = []

    def GetUserPreferenceStringValue(self, _pref):  # noqa: N802
        return self.folder

    def GetUserPreferenceToggle(self, _pref):  # noqa: N802
        return self.prompt

    def SetUserPreferenceToggle(self, _pref, value):  # noqa: N802
        self.prompt = value

    def GetOpenDocumentByName(self, _path):  # noqa: N802
        return self.open_doc

    def ActivateDoc3(self, title, *_args):  # noqa: N802
        self.activated.append(title)


class _Harness(std.SolidWorksDrawingStandardMixin):
    """The mixin plus recorded stand-ins for what it borrows from other mixins."""

    def __init__(self, app: _App, drawing: _Drawing, **results: Any) -> None:
        self.swApp = app
        self.currentModel = None
        self.drawing = drawing
        self.results = results
        self.calls: list[tuple[Any, ...]] = []
        self.overlaps = results.get("overlaps", 0)
        self.operations: list[str] = []

    def _handle_com_operation(self, name, operation, *args):
        self.operations.append(name)
        try:
            data = operation(*args)
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return _error(f"Error in {name}: {e}")
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, attr_name):
        value = getattr(obj, attr_name)
        return value() if callable(value) else value

    def _result(self, name: str, *args: Any) -> AdapterResult[Any]:
        self.calls.append((name, *args))
        return self.results.get(name, OK)

    def _dimension_geometry(self, an, _key, _view):
        if self.results.get("unmeasurable"):
            raise RuntimeError("no display data")
        x, y, _ = an.position
        return SimpleNamespace(text_box=(x, y - 0.003, x + 0.0019 * len(an.text), y))

    def _import_dimensions(
        self, view_name=None, include_hole_wizard=True, only_views=None
    ):
        self.calls.append(("import_dimensions", tuple(only_views or ())))
        return {"dimensions_added": 3}

    def _arrange_layout(
        self, view_name=None, obstacles=None, work_area=None, move=True
    ):
        self.calls.append(("arrange", move, tuple(sorted(obstacles or {}))))
        return {"overlaps_after": self.overlaps, "moved": 3}

    def _collect_layout(self, _drawing, _names):
        return {}, [], {}

    async def open_model(self, file_path):
        self.currentModel = SimpleNamespace(path=file_path)
        return self._result("open_model", file_path)

    async def get_material(self, configuration=None):
        self.calls.append(("get_material",))
        return self.results.get(
            "get_material",
            AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={"material": "AISI 1020"}
            ),
        )

    async def set_custom_property(self, name, value, configuration=None):
        return self._result("set_custom_property", name, value)

    async def save_file(self, file_path=None):
        return self._result(
            f"save_file:{'drawing' if file_path else 'model'}", file_path
        )

    async def create_drawing(self, name=None):
        self.calls.append(("create_drawing", self.swApp.prompt))
        result = self.results.get("create_drawing", OK)
        if result.is_success:
            self.currentModel = self.drawing
        return result

    async def set_units(self, unit_system):
        return self._result("set_units", unit_system)

    async def export_file(self, file_path, format_type):
        return self._result("export_file", file_path, format_type)


@pytest.fixture
def files(tmp_path):
    """A part, an assembly and a sheet-format folder on disk."""
    formats = tmp_path / "formats"
    formats.mkdir()
    (formats / "a3 - iso.slddrt").write_bytes(b"")
    part = tmp_path / "Mounting Plate.SLDPRT"
    part.write_bytes(b"")
    assembly = tmp_path / "Frame.SLDASM"
    assembly.write_bytes(b"")
    return SimpleNamespace(
        formats=str(formats),
        part=str(part),
        assembly=str(assembly),
        out=tmp_path / "out",
    )


def _adapter(
    files, drawing: _Drawing | None = None, open_doc=None, **results
) -> _Harness:
    return _Harness(_App(files.formats, open_doc), drawing or _Drawing(), **results)


# ---- the generator ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_part_becomes_a_complete_a3_drawing(files) -> None:
    adapter = _adapter(files)

    result = await adapter.create_standard_drawing(
        files.part,
        output_dir=str(files.out),
        author="J. Smith",
        drawn_date="23 Oct 2026",
        notes=["Laser cut"],
    )

    data = result.data
    assert result.is_success, result.error
    assert data["drawing_number"] == "MOUNTING-PLATE-RevA-01"
    assert data["drawing_path"] == str(files.out / "MOUNTING-PLATE-RevA-01.SLDDRW")
    assert data["pdf_path"] == str(files.out / "MOUNTING-PLATE-RevA-01.pdf")
    assert data["views"] == {
        "Drawing View1": {"role": "front", "caption": "FRONT VIEW"},
        "Drawing View2": {"role": "plan", "caption": "TOP VIEW"},
        "Drawing View3": {"role": "side", "caption": "SIDE VIEW"},
        "Drawing View4": {"role": "iso", "caption": "ISOMETRIC VIEW"},
    }
    assert data["notes"][1] == "1. MATERIAL: AISI 1020"
    assert data["notes"][-1] == "5. LASER CUT"
    assert data["dimensions"] == {
        "dimensions_added": 3,
        "layout": {"overlaps_after": 0, "moved": 3},
    }
    assert data["overlap_check"]["overlaps_after"] == 0
    assert data["overlap_check"]["annotation_overlaps"] == []
    assert data["format_links"] == [
        '$PRP:"SW-File Name"',
        '$PRPSHEET:"Description"',
    ]
    assert data["properties_written"]["drawing"]["DrawnBy"] == "J. Smith"
    assert all(step["status"] == "success" for step in data["steps"])
    assert [s["step"] for s in data["steps"] if s["step"].startswith("build_")] == [
        "build_sheet",
        "build_views",
        "build_layout",
        "build_bom",
        "build_dimensions",
        "build_notes",
        "build_check",
    ]
    # Each build step is its own COM operation, so each gets a settle pause.
    assert [op for op in adapter.operations if op.startswith("standard_drawing_")] == [
        "standard_drawing_format",
        "standard_drawing_dialog",
        "standard_drawing_dialog",
        "standard_drawing_sheet",
        "standard_drawing_views",
        "standard_drawing_layout",
        "standard_drawing_bom",
        "standard_drawing_dimensions",
        "standard_drawing_notes",
        "standard_drawing_check",
        "standard_drawing_title_block",
    ]


@pytest.mark.asyncio
async def test_the_drawing_number_is_shrunk_to_fit_its_box(files) -> None:
    drawing = _Drawing()
    adapter = _adapter(files, drawing)

    result = await adapter.create_standard_drawing(files.part)

    number = result.data["title_block"]["drawing number"]
    assert number["found"] is True and number["fits"] is True
    assert number["height_mm_before"] == 7.0
    assert std.MIN_FIELD_HEIGHT * 1000 < number["height_mm"] < 7.0
    assert number["box_mm"][2] <= number["room_ends_mm"]  # clear of the A3 box
    assert result.data["title_block"]["title"]["height_mm"] == 5.0  # fitted already
    assert drawing.editing == "sheet"  # back from editing the sheet format
    steps = [step["step"] for step in result.data["steps"]]
    assert steps.index("save_drawing") < steps.index("fit_title_block")
    assert steps.index("fit_title_block") < steps.index("save_drawing_again")


@pytest.mark.asyncio
async def test_a_field_too_long_for_its_box_is_an_overlap(files) -> None:
    drawing = _Drawing(format_notes=_title_block("X" * 60))

    result = await _adapter(files, drawing).create_standard_drawing(files.part)

    number = result.data["title_block"]["drawing number"]
    assert number["fits"] is False
    assert number["height_mm"] == std.MIN_FIELD_HEIGHT * 1000
    assert {
        "dimension": "title block drawing number",
        "conflicts_with": "the next title-block field",
        "kind": "field_overflow",
    } in result.data["overlap_check"]["annotation_overlaps"]
    assert "1 overlap(s) remain" in result.error


@pytest.mark.asyncio
async def test_a_format_without_the_fields_says_they_were_not_found(files) -> None:
    unmeasurable = _FormatNote("TITLE", '$PRPSHEET:"Description"', 0.23, 0.045, 0.005)
    unmeasurable.GetExtent = lambda: None
    drawing = _Drawing(format_notes=[unmeasurable])

    result = await _adapter(files, drawing).create_standard_drawing(files.part)

    assert result.is_success, result.error
    assert result.data["title_block"] == {
        "drawing number": {"found": False, "fits": None},
        "title": {"found": True, "fits": None},
    }


@pytest.mark.asyncio
async def test_a_failed_fit_is_recorded_and_the_drawing_still_saved(files) -> None:
    adapter = _adapter(files)

    def fail(_s):
        raise RuntimeError("EditTemplate refused")

    adapter._fit_title_block = fail

    result = await adapter.create_standard_drawing(files.part)

    assert result.is_success, result.error
    assert result.data["title_block"] is None
    step = next(s for s in result.data["steps"] if s["step"] == "fit_title_block")
    assert step["status"] == "error"


@pytest.mark.asyncio
async def test_a_caller_can_ask_for_smaller_title_block_text(files) -> None:
    result = await _adapter(files).create_standard_drawing(
        files.part, title_block_text_height_mm=3
    )

    title_block = result.data["title_block"]
    assert title_block["title"]["height_mm"] == 3.0  # capped though it fitted
    assert title_block["drawing number"]["height_mm"] == 3.0  # fits at 3 mm
    assert title_block["drawing number"]["fits"] is True


@pytest.mark.asyncio
async def test_a_field_too_long_even_at_the_cap_is_shrunk_further(files) -> None:
    drawing = _Drawing(format_notes=_title_block("X" * 30))

    result = await _adapter(files, drawing).create_standard_drawing(
        files.part, title_block_text_height_mm=5
    )

    number = result.data["title_block"]["drawing number"]
    assert std.MIN_FIELD_HEIGHT * 1000 < number["height_mm"] < 5.0
    assert number["fits"] is True


@pytest.mark.asyncio
async def test_an_overflow_says_how_to_make_the_text_smaller(files) -> None:
    drawing = _Drawing(format_notes=_title_block("X" * 60))

    result = await _adapter(files, drawing).create_standard_drawing(files.part)

    assert result.error.endswith(f". For a title-block field, {std.FIELD_HINT}")
    assert "title_block_text_height_mm" in std.FIELD_HINT


def test_field_room_stops_at_the_next_field_in_the_row() -> None:
    field = (0.25, 0.02, 0.37, 0.027)
    others = [
        (0.249, 0.028, 0.26, 0.030),  # its label, above
        (0.33, 0.021, 0.34, 0.026),  # the size box, in the row
        (0.30, 0.05, 0.31, 0.055),  # another row
        (0.252, 0.02, 0.26, 0.027),  # starts with the field
    ]
    assert std.field_room(field, others, 0.412) == pytest.approx(0.328)
    assert std.field_room(field, [], 0.412) == 0.412


@pytest.mark.asyncio
async def test_the_sheet_format_prompt_is_off_while_drawing_and_restored(files) -> None:
    adapter = _adapter(files)

    await adapter.create_standard_drawing(files.part)

    assert ("create_drawing", False) in adapter.calls
    assert adapter.swApp.prompt is True


@pytest.mark.asyncio
async def test_the_sheet_and_views_follow_the_standard(files) -> None:
    drawing = _Drawing()
    adapter = _adapter(files, drawing)

    result = await adapter.create_standard_drawing(files.part)

    assert drawing.setup[1:3] == (std._SW_PAPER_A3, std._SW_TEMPLATE_CUSTOM)
    assert drawing.setup[7:9] == std.SHEET_SIZE
    assert drawing.preferences == {
        std._SW_DETAILING_DIM_TRAILING_ZERO: std._SW_DIM_REMOVE_TRAILING_ZEROES
    }
    assert drawing.sheet.scale is not None
    assert result.data["scale"] == std.scale_label(drawing.sheet.scale)
    front, plan, side = (drawing.views[f"Drawing View{i}"]._position for i in (1, 2, 3))
    assert plan[0] == pytest.approx(front[0])  # plan above the front
    assert side[1] == pytest.approx(front[1])  # side beside it
    iso = drawing.views["Drawing View4"]
    assert iso.UseSheetScale is False
    assert result.data["isometric_scale"] is not None
    captions = [n for n in drawing.notes if n.text in std.CAPTIONS.values()]
    assert {n.format.Bold for n in captions} == {True}
    assert (
        "arrange",
        True,
        (
            "front caption",
            "iso caption",
            "notes",
            "plan caption",
            "side caption",
            "title block",
        ),
    ) in adapter.calls


@pytest.mark.asyncio
async def test_model_properties_are_written_and_saved(files) -> None:
    adapter = _adapter(files)

    result = await adapter.create_standard_drawing(files.part, title="Plate")

    names = [c[1] for c in adapter.calls if c[0] == "set_custom_property"]
    assert names[:3] == ["Description", "Material", "Weight"]
    assert ("save_file:model", None) in adapter.calls
    assert result.data["properties_written"]["model"]["Description"] == "Plate"


@pytest.mark.asyncio
async def test_an_assembly_without_model_properties_or_isometric(files) -> None:
    adapter = _adapter(files)

    result = await adapter.create_standard_drawing(
        files.assembly, include_isometric=False, write_model_properties=False
    )

    assert result.is_success, result.error
    assert ("get_material",) not in adapter.calls
    assert "model" not in result.data["properties_written"]
    assert "Drawing View4" not in result.data["views"]
    assert result.data["isometric_scale"] is None
    assert result.data["notes"][1] == "1. ALL DIMENSIONS IN MILLIMETRES"


@pytest.mark.asyncio
async def test_an_isometric_that_is_not_made_is_left_out(files) -> None:
    result = await _adapter(files, _Drawing(views="no iso")).create_standard_drawing(
        files.part
    )

    assert set(result.data["views"]) == {
        "Drawing View1",
        "Drawing View2",
        "Drawing View3",
    }


@pytest.mark.asyncio
async def test_notes_solidworks_does_not_make_are_skipped(files) -> None:
    result = await _adapter(files, _Drawing(views="no notes")).create_standard_drawing(
        files.part
    )

    assert result.is_success, result.error
    assert result.data["notes"][0] == "NOTES"  # the text is still reported


@pytest.mark.asyncio
async def test_an_unreadable_material_leaves_it_out_of_the_notes(files) -> None:
    adapter = _adapter(files, get_material=_error("no material"))

    result = await adapter.create_standard_drawing(files.part)

    assert result.data["notes"][1] == "1. ALL DIMENSIONS IN MILLIMETRES"


@pytest.mark.asyncio
async def test_an_open_copy_of_the_model_is_used(files) -> None:
    doc = SimpleNamespace(GetPathName=lambda: files.part, GetTitle=lambda: "Plate")
    adapter = _adapter(files, open_doc=doc)

    await adapter.create_standard_drawing(files.part)

    assert not any(c[0] == "open_model" for c in adapter.calls)
    assert adapter.swApp.activated == ["Plate"]


@pytest.mark.asyncio
async def test_an_open_file_with_another_path_is_not_used(files) -> None:
    doc = SimpleNamespace(GetPathName=lambda: "C:/other/Mounting Plate.SLDPRT")
    adapter = _adapter(files, open_doc=doc)

    await adapter.create_standard_drawing(files.part)

    assert ("open_model", files.part) in adapter.calls


@pytest.mark.asyncio
async def test_an_untitled_open_copy_is_used_without_activating(files) -> None:
    doc = SimpleNamespace(GetPathName=lambda: files.part, GetTitle=lambda: "")
    adapter = _adapter(files, open_doc=doc)

    await adapter.create_standard_drawing(files.part)

    assert adapter.swApp.activated == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (
            {"open_model": _error("locked")},
            "Could not open model: locked. If a different file with the same name "
            "is open in SolidWorks, close it first.",
        ),
        (
            {"create_drawing": _error("no template")},
            "Could not create drawing: no template",
        ),
    ],
)
async def test_the_model_and_drawing_must_open(files, setup, message) -> None:
    adapter = _adapter(files, **setup)

    result = await adapter.create_standard_drawing(files.part)

    assert result.error == message
    assert adapter.swApp.prompt is True


@pytest.mark.asyncio
async def test_a_missing_sheet_format_is_named(files, monkeypatch) -> None:
    monkeypatch.setattr(std.glob, "glob", lambda _pattern: [])
    adapter = _Harness(_App("C:/none"), _Drawing())

    result = await adapter.create_standard_drawing(files.part)

    assert result.error.startswith("Sheet format 'a3 - iso.slddrt' not found")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("drawing", "message"),
    [
        (
            _Drawing(accepts_format=False),
            "Drawing step 'sheet' failed: Error in standard_drawing_sheet: "
            "SetupSheet5 refused the sheet format",
        ),
        (
            _Drawing(views="none"),
            "Drawing step 'views' failed: Error in standard_drawing_views: "
            "No views could be created from",
        ),
    ],
)
async def test_a_failed_step_stops_the_build(files, drawing, message) -> None:
    result = await _adapter(files, drawing).create_standard_drawing(files.part)

    assert result.error.startswith(message)
    assert result.data["steps"][-1]["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "message", "kept"),
    [
        (
            {"save_file:drawing": _error("read-only")},
            "Drawing built but not saved to",
            "drawing_path",
        ),
        (
            {"export_file": _error("no printer")},
            "but the PDF export failed: no printer",
            "pdf_path",
        ),
    ],
)
async def test_files_that_were_not_written_are_errors(
    files, setup, message, kept
) -> None:
    result = await _adapter(files, **setup).create_standard_drawing(files.part)

    assert message in result.error
    assert result.data[kept] is None
    assert result.data["scale"]


def _with_bom(adapter: _Harness, boxes: list[Any] | None = None) -> list[Any]:
    """Give the harness a 100 x 20 mm BOM table; return what was inserted."""
    table_an = _Annotation("bom")
    table = SimpleNamespace(GetAnnotation=lambda: table_an)
    inserted: list[Any] = []

    def insert(view, template, kind, x_mm, y_mm):
        table_an.position = (x_mm / 1000, y_mm / 1000, 0.0)
        inserted.append((view, template, kind))
        return table, {"view": view, "bom_type": kind, "row_count": 3}

    def measure(_table):
        if boxes:
            return boxes.pop(0)
        x, y, _ = table_an.position
        return (x, y, x + 0.1, y + 0.02)

    adapter._insert_bom = insert
    adapter._table_box = measure
    return inserted


@pytest.mark.asyncio
async def test_an_assembly_gets_its_bom_above_the_isometric(files) -> None:
    adapter = _adapter(files)
    inserted = _with_bom(adapter)
    cells: list[Any] = []
    place = adapter._bom_above_iso
    adapter._bom_above_iso = lambda s: cells.append(s.cells["iso"]) or place(s)

    result = await adapter.create_standard_drawing(
        files.assembly, write_model_properties=False, include_bom=True
    )

    assert result.is_success, result.error
    assert inserted == [("Drawing View1", None, "top_level_only")]
    box = [v / 1000 for v in result.data["bom"]["table_box_mm"]]
    # Its top-right corner sits BOM_GAP inside the top-right of the iso cell,
    # and the isometric is centred below it.
    iso_cell = cells[0]
    assert box[2] == pytest.approx(iso_cell[2] - std.BOM_GAP, abs=1e-4)
    assert box[3] == pytest.approx(iso_cell[3] - std.BOM_GAP, abs=1e-4)
    iso_y = adapter.drawing.views["Drawing View4"]._position[1]
    assert iso_y < box[1] - std.BOM_GAP
    final = [c for c in adapter.calls if c[0] == "arrange"][-1]
    assert "bom" in final[2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("boxes", "message"),
    [
        ([None], "The BOM was inserted but cannot be measured"),
        ([(0.3, 0.2, 0.4, 0.22), None], "The BOM was moved but cannot be measured"),
    ],
    ids=["after inserting", "after moving"],
)
async def test_a_bom_that_cannot_be_measured_stops_the_build(
    files, boxes, message
) -> None:
    adapter = _adapter(files)
    _with_bom(adapter, boxes)

    result = await adapter.create_standard_drawing(
        files.assembly, write_model_properties=False, include_bom=True
    )

    assert (
        result.error
        == f"Drawing step 'bom' failed: Error in standard_drawing_bom: {message}"
    )


@pytest.mark.asyncio
async def test_an_assemblys_own_material_is_left_as_set(files) -> None:
    # A link to an assembly's material shows "<not specified>", so its own
    # Material property (set by the caller) is not overwritten.
    adapter = _adapter(files)

    result = await adapter.create_standard_drawing(files.assembly)

    assert result.is_success, result.error
    written = [c[1] for c in adapter.calls if c[0] == "set_custom_property"]
    assert "Material" not in written
    assert written[:2] == ["Description", "Weight"]


@pytest.mark.asyncio
async def test_a_part_has_no_bom(files) -> None:
    result = await _adapter(files).create_standard_drawing(files.part, include_bom=True)

    assert result.error == "include_bom needs an assembly (.SLDASM); a part has no BOM"


@pytest.mark.asyncio
async def test_orthographic_views_show_hidden_lines(files) -> None:
    drawing = _Drawing()
    adapter = _adapter(files, drawing)

    result = await adapter.create_standard_drawing(files.part)

    assert result.is_success, result.error
    views = drawing.views
    assert {n: views[n].display_mode for n in views} == {
        "Drawing View1": 1,
        "Drawing View2": 1,
        "Drawing View3": 1,
        "Drawing View4": 2,  # the isometric is left as it was
    }
    assert result.data["hidden_lines_visible"] == {
        "Drawing View1": True,
        "Drawing View2": True,
        "Drawing View3": True,
    }


def test_a_view_that_keeps_its_mode_or_cannot_say_is_reported(files) -> None:
    adapter = _adapter(files)
    locked = _View((0, 0, 1, 1), "*Locked")
    silent = SimpleNamespace(SetDisplayMode4=lambda *a: True)

    assert adapter._show_hidden_lines(locked) is False
    assert adapter._show_hidden_lines(silent) is None


def test_notes_inside_views_are_obstacles_too(files) -> None:
    # A caption inserted with nothing selected lands in the active view, so
    # the notes of every view are read, measured from their display data.
    adapter = _adapter(files)
    caption = _Annotation("TOP VIEW")
    caption.position = (0.1, 0.15, 0.0)
    in_view = SimpleNamespace(GetAnnotation=lambda: caption, GetNext=lambda: None)
    plan = SimpleNamespace(GetFirstNote=lambda: in_view, GetNextView=lambda: None)
    on_sheet = _FormatNote("DWG NO.", "", 0.249, 0.028, 0.002)
    sheet = SimpleNamespace(GetFirstNote=lambda: on_sheet, GetNextView=lambda: plan)

    boxes = adapter._sheet_note_boxes(SimpleNamespace(GetFirstView=lambda: sheet))

    assert boxes == {
        "note 0": pytest.approx((0.249, 0.028, 0.249 + 0.0016 * 7, 0.030)),
        "note 1": pytest.approx((0.1, 0.147, 0.1 + 0.0019 * 8, 0.15)),
    }


@pytest.mark.asyncio
async def test_the_finished_sheet_is_laid_out_clear_of_every_note(files) -> None:
    adapter = _adapter(files)

    await adapter.create_standard_drawing(files.part)

    final = [c for c in adapter.calls if c[0] == "arrange"][-1]
    assert final[1] is True
    # The captions are measured now: kept clear as drawn, not as whole strips.
    assert {"note 0", "note 3", "title block", "notes"} <= set(final[2])
    assert "plan caption" not in final[2]


@pytest.mark.asyncio
async def test_remaining_overlaps_fail_the_no_overlap_rule(files) -> None:
    result = await _adapter(files, overlaps=2).create_standard_drawing(files.part)

    assert result.error == (
        "Drawing saved but 2 overlap(s) remain - the no-overlap rule is not met; "
        "see overlap_check"
    )
    assert result.data["drawing_path"]


@pytest.mark.asyncio
async def test_the_overlaps_left_are_named_in_the_error(files) -> None:
    adapter = _adapter(files, overlaps=1)
    found = {
        "dimension": "Drawing View2#2",
        "conflicts_with": "bom",
        "kind": "on_obstacle",
    }
    arrange = adapter._arrange_layout
    adapter._arrange_layout = lambda *a, **k: {
        **arrange(*a, **k),
        "remaining_overlaps": [found],
    }

    result = await adapter.create_standard_drawing(files.part)

    assert result.error.endswith(
        "see overlap_check: Drawing View2#2 vs bom (on_obstacle)"
    )


@pytest.mark.asyncio
async def test_notes_that_cannot_be_measured_overlap_and_say_so(files) -> None:
    result = await _adapter(files, unmeasurable=True).create_standard_drawing(
        files.part
    )

    assert result.data["overlap_check"]["annotation_overlaps"]
    assert "overlap(s) remain" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("missing.SLDPRT", "Model file not found: "),
        ("Mounting Plate.step", "model_path must be a .SLDPRT or .SLDASM, not .step"),
        ("Mounting Plate", "model_path must be a .SLDPRT or .SLDASM, not no extension"),
    ],
)
async def test_the_model_must_be_a_part_or_assembly_on_disk(
    files, tmp_path, path, error
) -> None:
    target = tmp_path / path
    if not path.startswith("missing"):
        target.write_bytes(b"")

    result = await _adapter(files).create_standard_drawing(str(target))

    assert result.error.startswith(error)


# ---- helpers ------------------------------------------------------------------------


def test_a_garbled_view_position_is_reported(files) -> None:
    adapter = _adapter(files)

    assert adapter._set_view_position(_View(None, garble=True), 0.1, 0.2) is False
    assert adapter._set_view_position(_View(None), 0.1, 0.2) is True


def test_an_unreadable_outline_is_none(files) -> None:
    assert _adapter(files)._view_outline(_View(None)) is None


def test_a_view_without_an_outline_has_no_size(files) -> None:
    s = std._Sheet(
        path="p", sheet_format="f", views={"V": _View(None)}, role={"V": "front"}
    )
    assert _adapter(files)._view_sizes(s) == {}


@pytest.mark.parametrize(
    ("note", "annotation", "text_format", "made"),
    [
        (None, None, None, False),
        ("note", None, None, False),
        ("note", "an", None, True),
    ],
)
def test_notes_that_solidworks_does_not_make(
    files, note, annotation, text_format, made
) -> None:
    an = _Annotation("X")
    an.GetTextFormat = lambda _i: text_format
    adapter = _adapter(files)
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda _a: None,
        InsertNote=lambda _t: (
            None
            if note is None
            else SimpleNamespace(GetAnnotation=lambda: an if annotation else None)
        ),
    )

    result = adapter._insert_sheet_note("X", 0.1, 0.1, 0.003, False)

    assert (result is an) is made


def test_a_note_already_in_place_is_not_moved(files) -> None:
    adapter = _adapter(files)
    an = _Annotation("NOTES")
    an.position = (0.02, 0.07, 0.0)

    box = adapter._place_note(an, "NOTES", left=0.02, top=0.07)

    assert box[:2] == (0.02, 0.067)
    assert an.position == (0.02, 0.07, 0.0)


def test_a_note_without_a_position_keeps_its_box(files) -> None:
    adapter = _adapter(files)
    an = _Annotation("NOTES")
    an.GetPosition = lambda: None

    box = adapter._place_note(an, "NOTES", centre_x=0.3, bottom=0.2)

    assert box == (0.0, -0.003, 0.0019 * 5, 0.0)


def test_an_unmeasurable_note_is_estimated_from_its_text(files) -> None:
    adapter = _adapter(files, unmeasurable=True)

    box = adapter._note_box(_Annotation("AB"), "AB", 0.1, 0.2, 0.003)

    assert box == pytest.approx((0.1, 0.197, 0.1 + 0.62 * 0.003 * 2, 0.2))


def test_an_unreadable_prompt_toggle_is_left_alone(files) -> None:
    app = _App(files.formats)
    app.GetUserPreferenceToggle = lambda _p: (_ for _ in ()).throw(RuntimeError())
    adapter = _Harness(app, _Drawing())

    assert adapter._new_drawing_without_dialog() is None
    app.prompt = "unchanged"
    adapter._restore_dialog(None)
    assert app.prompt == "unchanged"
