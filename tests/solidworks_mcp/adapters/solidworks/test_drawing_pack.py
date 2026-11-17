"""The drawing pack's real-adapter methods, against fake COM objects.

Spec: tools/drawing-section-detail, drawing-title-block, drawing-dimensions,
drawing-check.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import drawing_pack as dp
from solidworks_mcp.adapters.solidworks.drawing_pack import SolidWorksDrawingPackMixin

# ---- pure helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "parsed"), [("2:1", (2.0, 1.0)), (" 1 : 2.5 ", (1.0, 2.5))]
)
def test_parse_scale(text: str, parsed: tuple[float, float]) -> None:
    assert dp.parse_scale(text) == parsed


@pytest.mark.parametrize("text", ["2", "0:1", "1:0", "a:b"])
def test_parse_scale_refuses(text: str) -> None:
    with pytest.raises(ValueError, match="must look like '2:1'"):
        dp.parse_scale(text)


@pytest.mark.parametrize(
    ("start", "end", "crosses"),
    [
        ([0, 50], [200, 50], True),  # straight across
        ([50, 50], [60, 60], True),  # wholly inside
        ([0, 0], [5, 200], False),  # passes left of the box
        ([0, 150], [200, 150], False),  # above it
        ([10, 0], [10, 200], False),  # vertical, left of it
        ([20, 0], [20, 200], True),  # vertical, on its left edge
        ([0, 0], [200, 200], True),  # diagonal through it
    ],
)
def test_segment_crosses_box(
    start: list[float], end: list[float], crosses: bool
) -> None:
    assert dp.segment_crosses_box(start, end, (20.0, 20.0, 120.0, 100.0)) is crosses


def test_next_label_skips_used_letters_and_i_o_q() -> None:
    assert dp.next_label([]) == "A"
    names = ["Drawing View1", "Section View A-A", "Detail View B (2 : 1)"]
    assert dp.next_label(names) == "C"
    used = [f"Section View {c}-{c}" for c in "ABCDEFGH"]
    assert dp.next_label(used) == "J"


@pytest.mark.parametrize(
    ("fmt", "size", "paper"),
    [
        ("a2 - iso", None, "a2"),
        (r"C:\x\A1 - ISO.slddrt", None, "a1"),
        ("custom", "A4", "a4"),
    ],
)
def test_paper_for(fmt: str, size: str | None, paper: str) -> None:
    assert dp.paper_for(fmt, size) == paper


def test_paper_for_refuses_an_unknown_size() -> None:
    with pytest.raises(ValueError, match="paper_size must be one of"):
        dp.paper_for("custom", None)


def test_mm_reads_an_outline_or_nothing() -> None:
    assert dp._mm((0.01, 0.02, 0.1, 0.2)) == (10.0, 20.0, 100.0, 200.0)
    assert dp._mm(None) is None
    assert dp._mm(("a", 1, 2, 3)) is None


# ---- a fake adapter ----------------------------------------------------------


class FakeView(SimpleNamespace):
    """A drawing view: outline (m), transform, annotations."""


class FakeAdapter(SolidWorksDrawingPackMixin):
    """The adapter surface the mixin uses, with a fake drawing."""

    def __init__(self, views: dict[str, Any], drawing: bool = True) -> None:
        self.views = views
        self.is_drawing = drawing
        self.currentModel = MagicMock()
        self.selected: list[tuple[Any, bool]] = []
        self.dimension_counts = dict.fromkeys(views, 0)

    def _require_drawing(self) -> AdapterResult[Any] | None:
        if self.is_drawing:
            return None
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="This operation requires a drawing document",
        )

    def _handle_com_operation(self, operation: str, fn: Any) -> AdapterResult[Any]:
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=fn())
        except Exception as exc:  # noqa: BLE001 - the real one does the same
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))

    def _attempt(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default

    def _sheet_bounds(self, drawing: Any) -> Any:
        return (0.0, 0.0, 0.42, 0.297)

    def _select_sketch_entity(self, entity: Any, append: bool) -> bool:
        self.selected.append((entity, append))
        return True

    def _view_dimension_count(self, view: Any) -> int:
        return self.dimension_counts[view.name]

    def _pictorial(self, view: Any) -> bool:
        return view.name == "Iso"


@pytest.fixture
def views() -> dict[str, Any]:
    """A front view at (20, 150)-(120, 230) mm, drawn at 1:2 from (70, 190)."""
    return {
        "Front": FakeView(
            name="Front",
            GetOutline=lambda: (0.02, 0.15, 0.12, 0.23),
            GetSketch=lambda: "front sketch",
            Type=6,
            GetFirstAnnotation3=lambda: None,
            ReferencedDocument=None,
        )
    }


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch, views: dict[str, Any]) -> FakeAdapter:
    made = FakeAdapter(views)
    monkeypatch.setattr(dp, "_view_names", lambda a, d: list(a.views))
    monkeypatch.setattr(dp, "_resolve_drawing_view", lambda a, d, n: a.views.get(n))
    monkeypatch.setattr(dp, "_as_com", lambda a, obj, i: obj)
    monkeypatch.setattr(dp.sw_type_info, "flagged", lambda obj, *i: obj)
    # The front view's sketch: drawn at 1:2 about (70, 190) mm on the sheet.
    monkeypatch.setattr(
        dp,
        "_to_sketch",
        lambda a, sketch, p: [(p[0] - 0.07) / 0.5, (p[1] - 0.19) / 0.5, 0.0],
    )
    return made


# ---- section and detail views ------------------------------------------------


@pytest.mark.asyncio
async def test_a_section_view_is_cut_along_the_line(adapter: FakeAdapter) -> None:
    drawing = adapter.currentModel
    line = object()
    drawing.SketchManager.CreateLine.return_value = line

    def make_section(*args: Any) -> Any:
        adapter.views["Section View A-A"] = FakeView(
            name="Section View A-A",
            GetName2=lambda: "Section View A-A",
            GetOutline=lambda: (0.2, 0.15, 0.3, 0.23),
        )
        return adapter.views["Section View A-A"]

    drawing.CreateSectionViewAt5.side_effect = make_section

    result = await adapter.create_section_view(
        "Front", [10, 190], [130, 190], [250, 190]
    )

    # Sheet (10, 190) mm is view sketch ((0.010 - 0.070) / 0.5, 0) m.
    drawing.SketchManager.CreateLine.assert_called_once_with(
        pytest.approx(-0.12),
        pytest.approx(0.0),
        0.0,
        pytest.approx(0.12),
        pytest.approx(0.0),
        0.0,
    )
    drawing.ActivateView.assert_called_once_with("Front")
    drawing.CreateSectionViewAt5.assert_called_once_with(
        0.25, 0.19, 0.0, "A", 0, None, 0.0
    )
    assert adapter.selected == [(line, False)]
    assert result.data == {
        "label": "A",
        "parent": "Front",
        "name": "Section View A-A",
        "outline_mm": (200.0, 150.0, 300.0, 230.0),
        "views_before": 1,
        "views_after": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start", "end", "position", "error"),
    [
        ([200, 10], [300, 10], [250, 190], "doesn't cross view 'Front'"),
        ([10, 190], [130, 190], [500, 190], "is off the sheet (420 x 297 mm)"),
    ],
)
async def test_a_section_is_refused_before_any_change(
    adapter: FakeAdapter, start: Any, end: Any, position: Any, error: str
) -> None:
    result = await adapter.create_section_view("Front", start, end, position)

    assert error in (result.error or "")
    adapter.currentModel.SketchManager.CreateLine.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_section_leaves_no_line(adapter: FakeAdapter) -> None:
    drawing = adapter.currentModel
    drawing.SketchManager.CreateLine.return_value = "line"
    drawing.CreateSectionViewAt5.return_value = None

    result = await adapter.create_section_view(
        "Front", [10, 190], [130, 190], [250, 190], label="Z"
    )

    assert result.error == "CreateSectionViewAt5 made no section view of 'Front'."
    drawing.EditDelete.assert_called_once()
    drawing.CreateSectionViewAt5.assert_called_once_with(
        0.25, 0.19, 0.0, "Z", 0, None, 0.0
    )


@pytest.mark.asyncio
async def test_no_line_drawn_is_an_error(adapter: FakeAdapter) -> None:
    adapter.currentModel.SketchManager.CreateLine.return_value = None

    result = await adapter.create_section_view(
        "Front", [10, 190], [130, 190], [250, 190]
    )

    assert result.error == "The section line couldn't be drawn in 'Front'."


@pytest.mark.asyncio
async def test_an_unknown_view_lists_the_views(adapter: FakeAdapter) -> None:
    result = await adapter.create_section_view("Top", [0, 0], [1, 1], [5, 5])

    assert result.error == "No view named 'Top' on the sheet; it has Front."


@pytest.mark.asyncio
async def test_a_detail_view_at_a_scale(adapter: FakeAdapter) -> None:
    drawing = adapter.currentModel
    drawing.SketchManager.CreateCircleByRadius.return_value = "circle"
    drawing.CreateDetailViewAt4.return_value = FakeView(
        GetName2=lambda: "Detail View A (3 : 1)", GetOutline=lambda: None
    )

    result = await adapter.create_detail_view("Front", [30, 160], 5, [300, 80], "3:1")

    drawing.SketchManager.CreateCircleByRadius.assert_called_once_with(
        pytest.approx(-0.08), pytest.approx(-0.06), 0.0, pytest.approx(0.01)
    )
    drawing.CreateDetailViewAt4.assert_called_once_with(
        0.3, 0.08, 0.0, 0, 3.0, 1.0, "A", 1, False, False, False, 0
    )
    assert result.data["scale"] == "3:1"
    assert result.data["name"] == "Detail View A (3 : 1)"


@pytest.mark.asyncio
async def test_detail_refusals(adapter: FakeAdapter) -> None:
    drawing = adapter.currentModel
    outside = await adapter.create_detail_view("Front", [300, 10], 5, [300, 80])
    drawing.SketchManager.CreateCircleByRadius.return_value = None
    no_circle = await adapter.create_detail_view("Front", [30, 160], 5, [300, 80])
    drawing.SketchManager.CreateCircleByRadius.return_value = "circle"
    drawing.CreateDetailViewAt4.return_value = None
    no_view = await adapter.create_detail_view("Front", [30, 160], 5, [300, 80])

    assert "isn't inside view 'Front'" in (outside.error or "")
    assert no_circle.error == "The detail circle couldn't be drawn in 'Front'."
    assert no_view.error == "CreateDetailViewAt4 made no detail of 'Front'."


@pytest.mark.asyncio
async def test_a_view_without_a_sketch_is_an_error(adapter: FakeAdapter) -> None:
    adapter.views["Front"].GetSketch = lambda: None

    result = await adapter.create_detail_view("Front", [30, 160], 5, [300, 80])

    assert result.error == "The view's sketch couldn't be read to place the entity."
    adapter.currentModel.SketchManager.CreateCircleByRadius.assert_not_called()


@pytest.mark.asyncio
async def test_no_outline_skips_the_view_checks(adapter: FakeAdapter) -> None:
    adapter.views["Front"].GetOutline = lambda: None
    adapter.currentModel.SketchManager.CreateLine.return_value = "line"
    adapter.currentModel.CreateSectionViewAt5.return_value = FakeView(
        GetName2=lambda: "S", GetOutline=lambda: None
    )
    adapter._sheet_bounds = lambda drawing: None  # type: ignore[method-assign]

    result = await adapter.create_section_view("Front", [0, 0], [1, 1], [900, 900])

    assert result.is_success, result.error


@pytest.mark.asyncio
async def test_a_part_is_refused(views: dict[str, Any]) -> None:
    result = await FakeAdapter(views, drawing=False).drawing_report()

    assert "requires a drawing document" in (result.error or "")


# ---- dimensions --------------------------------------------------------------


def _picks(adapter: FakeAdapter, hits: dict[tuple[str, float], bool]) -> list[Any]:
    calls: list[Any] = []

    def select(name: str, kind: str, x: float, *rest: Any) -> bool:
        calls.append((kind, round(x, 4), rest[2]))
        return hits.get((kind, round(x, 4)), False)

    adapter.currentModel.Extension.SelectByID2.side_effect = select
    return calls


@pytest.mark.asyncio
async def test_a_horizontal_dimension_between_two_edges(adapter: FakeAdapter) -> None:
    calls = _picks(adapter, {("EDGE", 0.02): True, ("VERTEX", 0.12): True})
    dimension = SimpleNamespace(SystemValue=0.06, FullName="RD1@Drawing View1")
    adapter.currentModel.AddHorizontalDimension2.return_value = SimpleNamespace(
        GetDimension2=lambda i: dimension
    )

    result = await adapter.add_dimension("horizontal", [20, 160], [70, 240], [120, 160])

    assert calls == [
        ("EDGE", 0.02, False),
        ("EDGE", 0.12, True),
        ("VERTEX", 0.12, True),
    ]
    adapter.currentModel.AddHorizontalDimension2.assert_called_once_with(
        0.07, 0.24, 0.0
    )
    assert result.data == {
        "name": "RD1@Drawing View1",
        "dimension_type": "horizontal",
        "value": 60.0,
        "units": "mm",
    }


@pytest.mark.asyncio
async def test_an_angle_is_in_degrees(adapter: FakeAdapter) -> None:
    _picks(adapter, {("EDGE", 0.02): True, ("EDGE", 0.03): True})
    adapter.currentModel.AddDimension2.return_value = SimpleNamespace(
        GetDimension2=lambda i: SimpleNamespace(SystemValue=1.5707963267948966)
    )

    result = await adapter.add_dimension("angular", [20, 160], [70, 240], [30, 160])

    assert (result.data["value"], result.data["units"]) == (90.0, "deg")


@pytest.mark.asyncio
async def test_dimension_refusals(adapter: FakeAdapter) -> None:
    _picks(adapter, {("EDGE", 0.02): True})
    off = await adapter.add_dimension("diameter", [20, 160], [900, 10])
    nothing = await adapter.add_dimension("diameter", [5, 5], [70, 240])
    adapter.currentModel.AddDiameterDimension2.return_value = None
    refused = await adapter.add_dimension("diameter", [20, 160], [70, 240])

    assert "is off the sheet" in (off.error or "")
    assert "Nothing to dimension at [5, 5] mm" in (nothing.error or "")
    assert "added no diameter dimension" in (refused.error or "")


@pytest.mark.asyncio
async def test_auto_dimension_counts_what_it_added(adapter: FakeAdapter) -> None:
    counts = iter([1, 5])
    adapter._view_dimension_count = lambda view: next(counts)  # type: ignore[method-assign]
    adapter.currentModel.AutoDimension.return_value = 0

    result = await adapter.auto_dimension_view("Front", "chain")

    adapter.currentModel.AutoDimension.assert_called_once_with(1, 3, 1, 3, 1)
    picked = adapter.currentModel.Extension.SelectByID2.call_args.args
    assert picked[:2] == ("Front", "DRAWINGVIEW")
    assert result.data == {
        "view": "Front",
        "scheme": "chain",
        "dimensions_before": 1,
        "dimensions_after": 5,
        "added": 4,
    }


@pytest.mark.asyncio
async def test_auto_dimension_that_adds_nothing_fails(adapter: FakeAdapter) -> None:
    adapter.currentModel.AutoDimension.return_value = 8

    result = await adapter.auto_dimension_view("Front")

    assert result.error == "AutoDimension added no dimension to 'Front' (status 8)."


# ---- sheet format and title block -------------------------------------------


@pytest.mark.asyncio
async def test_a_new_format_keeps_the_views(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dp, "find_sheet_format", lambda a, name: rf"C:\fmt\{name}")
    sheet = SimpleNamespace(
        GetProperties2=lambda: (8, 12, 1.0, 2.0, True, 0.42, 0.297),
        GetName=lambda: "Sheet1",
    )
    adapter.currentModel.GetCurrentSheet.return_value = sheet
    adapter.currentModel.SetupSheet5.return_value = True

    result = await adapter.update_sheet_format("a2 - iso")

    adapter.currentModel.SetupSheet5.assert_called_once_with(
        "Sheet1",
        9,
        12,
        1.0,
        2.0,
        True,
        r"C:\fmt\a2 - iso.slddrt",
        0.594,
        0.42,
        "Default",
        True,
    )
    assert result.data["paper_size"] == "a2"
    assert result.data["views"] == ["Front"]


@pytest.mark.asyncio
async def test_format_refusals(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(dp, "find_sheet_format", lambda a, name: None)
    missing = await adapter.update_sheet_format("b9 - odd", "a3")
    own = tmp_path / "mine.slddrt"
    own.write_text("", encoding="utf-8")
    adapter.currentModel.GetCurrentSheet.return_value = SimpleNamespace(
        GetProperties2=lambda: None, GetName=lambda: "Sheet1"
    )
    adapter.currentModel.SetupSheet5.return_value = False
    refused = await adapter.update_sheet_format(str(own), "a3")

    assert "No sheet format 'b9 - odd.slddrt'" in (missing.error or "")
    adapter.currentModel.SetupSheet5.assert_called_once_with(
        "Sheet1", 8, 12, 1.0, 1.0, False, str(own), 0.42, 0.297, "Default", True
    )
    assert "SetupSheet5 refused" in (refused.error or "")


@pytest.mark.asyncio
async def test_views_lost_with_the_format_are_reported(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dp, "find_sheet_format", lambda a, name: "x.slddrt")
    adapter.currentModel.SetupSheet5.side_effect = lambda *a: (
        adapter.views.clear() or True
    )

    result = await adapter.update_sheet_format("a3 - iso.slddrt")

    assert "The views changed with the format" in (result.error or "")


@pytest.mark.asyncio
async def test_title_block_fields_go_to_their_owners(adapter: FakeAdapter) -> None:
    model = MagicMock()
    adapter.views["Front"].ReferencedDocument = model

    result = await adapter.update_title_block({"title": "Plate", "revision": "B"})

    model.Extension.CustomPropertyManager("").Add3.assert_called_once_with(
        "Description", 30, "Plate", 2
    )
    adapter.currentModel.Extension.CustomPropertyManager("").Add3.assert_called_with(
        "Revision", 30, "B", 2
    )
    assert result.data["fields"]["title"] == {
        "property": "Description",
        "on": "model",
        "value": "Plate",
    }


@pytest.mark.asyncio
async def test_a_title_needs_a_model_view(adapter: FakeAdapter) -> None:
    result = await adapter.update_title_block({"title": "Plate"})

    assert result.error == "The drawing has no view of a model to take the title from."


# ---- the drawing report -------------------------------------------------------


def _annotation(kind: int, dangling: bool = False, table: int | None = None) -> Any:
    return SimpleNamespace(
        IsDangling=lambda: dangling,
        GetType=lambda: kind,
        GetSpecificAnnotation=lambda: SimpleNamespace(Type=table),
        next=None,
    )


@pytest.mark.asyncio
async def test_the_report(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = SimpleNamespace(
        GetType=lambda: 2,
        Extension=SimpleNamespace(CustomPropertyManager=lambda config: object()),
    )
    adapter.views["Front"].ReferencedDocument = model
    adapter.views["Iso"] = FakeView(
        name="Iso", GetOutline=lambda: None, Type=7, ReferencedDocument=None
    )
    adapter.dimension_counts.update(Front=3, Iso=0)
    bom, dim, loose = _annotation(14, table=2), _annotation(4), _annotation(6, True)
    bom.GetNext3, dim.GetNext3, loose.GetNext3 = (
        (lambda: dim),
        (lambda: None),
        lambda: None,
    )
    sheet_view = SimpleNamespace(
        GetFirstAnnotation3=lambda: bom, GetNextView=lambda: view2
    )
    view2 = SimpleNamespace(GetFirstAnnotation3=lambda: loose, GetNextView=lambda: None)
    adapter.currentModel.GetFirstView.return_value = sheet_view
    monkeypatch.setattr(
        dp,
        "_read_custom_property",
        lambda a, manager, prop: (
            {"Description": "Plate", "DrawnBy": "AB"}.get(prop, ""),
            "",
        ),
    )

    result = await adapter.drawing_report()

    assert result.data == {
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
                "outline_mm": None,
                "dimensions": 0,
            },
        ],
        "title_block": {"title": "Plate", "drawn_by": "AB", "revision": None},
        "model_type": "assembly",
        "bom": True,
        "dangling": 1,
    }


@pytest.mark.asyncio
async def test_a_report_with_no_model_or_manager(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter.currentModel.GetFirstView.return_value = None
    adapter.currentModel.Extension.CustomPropertyManager.side_effect = RuntimeError

    result = await adapter.drawing_report()

    assert result.data["title_block"] == {
        "title": None,
        "drawn_by": None,
        "revision": None,
    }
    assert (result.data["model_type"], result.data["bom"]) == (None, False)
