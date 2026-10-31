"""Tests for the drawing-dimension methods of SolidWorksDocumentationMixin.

A fake drawing stands in for SolidWorks: ``InsertModelAnnotations3`` and
``AutoDimension`` add display dimensions to the active view, selection by
name plus ``DeleteSelection2`` removes one, and ``SetPosition`` moves a
dimension's text and lines the way the real geometry read-back sees them.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import documentation as doc
from solidworks_mcp.adapters.solidworks.documentation import (
    SolidWorksDocumentationMixin,
    _overlap_summary,
)

OUTLINE = (0.05, 0.10, 0.17, 0.17)  # a 120 x 70 mm view on an A3 sheet


@pytest.fixture(autouse=True)
def _plain_com(monkeypatch) -> None:
    """Fake objects need no flagging or wrapping; views come from the fake."""
    monkeypatch.setattr(
        doc, "_sw_type_info", SimpleNamespace(flagged=lambda obj, *_: obj)
    )
    monkeypatch.setattr(doc, "_as_com", lambda _adapter, obj, _iface: obj)
    monkeypatch.setattr(doc, "_null_callout", lambda: None)
    monkeypatch.setattr(doc, "_view_names", lambda _a, drawing: list(drawing.views))
    monkeypatch.setattr(
        doc,
        "_resolve_drawing_view",
        lambda _a, drawing, name: drawing.views.get(name),
    )


class _Harness(SolidWorksDocumentationMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any = None) -> None:
        self.currentModel = model
        self.swApp = None

    def _handle_com_operation(self, name, operation, *args):
        try:
            data = operation(*args)
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=data, execution_time=0.5
        )

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, name):
        value = getattr(obj, name)
        return value() if callable(value) else value

    def _require_drawing(self):
        if getattr(self.currentModel, "GetType", lambda: 0)() != 3:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="This operation requires a drawing document",
            )
        return None


# ---- fake drawing ---------------------------------------------------------------


class _Data:
    """``IDisplayData`` of one dimension: a single text and its lines."""

    def __init__(self, ann: _Ann) -> None:
        self._ann = ann

    def GetTextCount(self) -> int:  # noqa: N802
        return 1

    def GetTextPositionAtIndex(self, _i: int):  # noqa: N802
        return (self._ann.x, self._ann.y)

    def GetTextAtIndex(self, _i: int) -> str:  # noqa: N802
        return "30"

    def GetTextHeightAtIndex(self, _i: int) -> float:  # noqa: N802
        return 0.0025

    def GetTextInBoxWidthAtIndex(self, _i: int) -> float:  # noqa: N802
        return 0.0

    def GetLineCount(self) -> int:  # noqa: N802
        return len(self._ann.lines)

    def GetLineAtIndex3(self, i: int):  # noqa: N802
        x0, y0, x1, y1 = self._ann.lines[i]
        return (0, 0, 0, 0, x0, y0, 0, x1, y1)


class _Ann:
    """A horizontal display dimension's ``IAnnotation``.

    Like SolidWorks, moving it redraws the extension lines from the part's
    edge out to the new dimension line rather than shifting them.
    """

    def __init__(self, view: _View, name: str | None, x0: float, x1: float) -> None:
        self.view, self.name = view, name
        self.ends, self.anchor = (x0, x1), view.outline[1]  # on the part's edge
        # Imported where the sketch had it: inside the view, on the part.
        self.x, self.y = (x0 + x1) / 2, 0.12

    @property
    def lines(self) -> list[tuple[float, float, float, float]]:
        """Extension lines from the part's edge to the dimension line."""
        (x0, x1), y = self.ends, self.y
        return [
            (x0, self.anchor, x0, y),
            (x1, self.anchor, x1, y),
            (x0, y, x1, y),
        ]

    def GetType(self) -> int:  # noqa: N802
        return doc._SW_ANNOTATION_DISPLAY_DIMENSION

    def GetSpecificAnnotation(self):  # noqa: N802
        dimension = SimpleNamespace(FullName=f"{self.name}@Part1.Part")
        return SimpleNamespace(
            GetDimension2=lambda _i: dimension if self.name else None,
            GetNameForSelection=lambda: f"{self.name}@{self.view.name}",
        )

    def GetNext3(self):  # noqa: N802
        items = self.view.items
        i = items.index(self)
        return items[i + 1] if i + 1 < len(items) else None

    def GetPosition(self):  # noqa: N802
        return (self.x, self.y, 0.0)

    def GetDisplayData(self) -> _Data:  # noqa: N802
        return _Data(self)

    def SetPosition(self, x: float, y: float, _z: float) -> bool:  # noqa: N802
        if not self.view.movable:
            return False
        self.x, self.y = x, y
        return True


class _Note:
    """A non-dimension annotation (skipped by the dimension readers)."""

    def __init__(self, view: _View) -> None:
        self.view = view

    def GetType(self) -> int:  # noqa: N802
        return 6

    def GetNext3(self):  # noqa: N802
        return _Ann.GetNext3(self)  # type: ignore[arg-type]


class _View:
    def __init__(self, name: str, orientation: str = "*Front") -> None:
        self.name, self.orientation = name, orientation
        self.outline = OUTLINE
        self.items: list[Any] = []
        self.movable = True

    @property
    def dims(self) -> list[_Ann]:
        return [a for a in self.items if isinstance(a, _Ann)]

    def add(self, name: str | None, x0: float = 0.06, x1: float = 0.16) -> _Ann:
        ann = _Ann(self, name, x0, x1)
        self.items.append(ann)
        return ann

    def GetDisplayDimensionCount(self) -> int:  # noqa: N802
        return len(self.dims)

    def GetOrientationName(self) -> str:  # noqa: N802
        return self.orientation

    def GetFirstAnnotation3(self):  # noqa: N802
        return self.items[0] if self.items else None

    def GetOutline(self):  # noqa: N802
        return self.outline


class _Drawing:
    """The active ``IDrawingDoc``."""

    def __init__(
        self,
        views: list[_View],
        imports: dict[str, list[str]] | None = None,
        autodim: dict[str, list[str]] | None = None,
    ) -> None:
        self.views = {v.name: v for v in views}
        self.imports = imports or {}
        self.autodim = autodim or {}
        self.active: str | None = None
        self.selected: _Ann | None = None
        self.import_types: list[int] = []
        self.Extension = SimpleNamespace(
            SelectByID2=self._select, DeleteSelection2=self._delete
        )

    def GetType(self) -> int:  # noqa: N802
        return 3

    def ActivateView(self, name: str) -> bool:  # noqa: N802
        self.active = name
        return True

    def ClearSelection2(self, _all: bool) -> None:  # noqa: N802
        self.selected = None

    def _select(self, name, kind, *_args) -> bool:
        if kind == "DRAWINGVIEW":
            self.active = name
            return True
        for view in self.views.values():
            for ann in view.dims:
                if f"{ann.name}@{view.name}" == name:
                    self.selected = ann
                    return True
        return False

    def _delete(self, _options: int) -> bool:
        if self.selected is None:
            return False
        self.selected.view.items.remove(self.selected)
        return True

    def InsertModelAnnotations3(self, _source, types, *_flags):  # noqa: N802
        self.import_types.append(types)
        for name in self.imports.get(self.active, []):
            self.views[self.active].add(name)
        return None

    def AutoDimension(self, *_args) -> int:  # noqa: N802
        for name in self.autodim.get(self.active, []):
            self.views[self.active].add(name)
        return 0

    def EditRebuild3(self) -> bool:  # noqa: N802
        return True

    def GraphicsRedraw2(self) -> None:  # noqa: N802
        return None

    def GetCurrentSheet(self):  # noqa: N802
        return SimpleNamespace(GetProperties2=lambda: (0, 0, 0, 0, 0, 0.42, 0.297, 0))


def _three_views(**kwargs: Any) -> _Drawing:
    return _Drawing(
        [_View("Front"), _View("Top", "*Top"), _View("Iso", "*Isometric")], **kwargs
    )


# ---- insert_model_dimensions ----------------------------------------------------


@pytest.mark.asyncio
async def test_insert_needs_a_drawing() -> None:
    result = await _Harness(
        SimpleNamespace(GetType=lambda: 1)
    ).insert_model_dimensions()
    assert result.error == "This operation requires a drawing document"


@pytest.mark.asyncio
async def test_insert_unknown_view_lists_the_views() -> None:
    result = await _Harness(_three_views()).insert_model_dimensions("Side")
    assert result.error == (
        "Error in insert_model_dimensions: No view named 'Side'. Views: Front, Top, Iso"
    )


@pytest.mark.asyncio
async def test_insert_shows_each_dimension_once() -> None:
    drawing = _three_views(
        imports={
            "Front": ["D1@Sketch1", "D2@Sketch1"],
            "Top": ["D1@Sketch1", "D1@Boss-Extrude1"],
        }
    )

    result = await _Harness(drawing).insert_model_dimensions()

    assert result.data == {
        "views": [
            {
                "view": "Front",
                "dimensions_before": 0,
                "dimensions_after": 2,
                "dimensions_added": 2,
                "duplicates_removed": 0,
            },
            {
                "view": "Top",
                "dimensions_before": 0,
                "dimensions_after": 1,
                "dimensions_added": 1,
                "duplicates_removed": 1,
            },
        ],
        "dimensions_added": 3,
        "unique_dimensions": 3,
        "skipped_pictorial_views": ["Iso"],
        "method": "insert_model_annotations",
        "autodimension_status": None,
    }
    assert drawing.import_types == [32768 | 131072] * 2


@pytest.mark.asyncio
async def test_a_dimension_stays_in_the_view_that_took_the_most() -> None:
    # A plate sketched on Top: the plan view shows every sketch dimension;
    # the front view sees the holes edge-on, where their dimensions stack up.
    drawing = _three_views(
        imports={
            "Front": ["D1@Sketch1", "D3@Sketch1", "D1@Boss-Extrude1"],
            "Top": ["D1@Sketch1", "D2@Sketch1", "D3@Sketch1", "D4@Sketch1"],
        }
    )

    result = await _Harness(drawing).insert_model_dimensions()

    assert [a.name for a in drawing.views["Top"].dims] == [
        "D1@Sketch1",
        "D2@Sketch1",
        "D3@Sketch1",
        "D4@Sketch1",
    ]
    assert [a.name for a in drawing.views["Front"].dims] == ["D1@Boss-Extrude1"]
    removed = {v["view"]: v["duplicates_removed"] for v in result.data["views"]}
    assert removed == {"Front": 2, "Top": 0}


@pytest.mark.asyncio
async def test_insert_one_view_skips_what_another_view_shows() -> None:
    drawing = _three_views(imports={"Top": ["D1@Sketch1", "D3@Sketch1"]})
    drawing.views["Front"].add("D1@Sketch1")
    drawing.views["Iso"].add(None)  # a dimension whose name cannot be read

    result = await _Harness(drawing).insert_model_dimensions("Top", False)

    assert [a.name for a in drawing.views["Top"].dims] == ["D3@Sketch1"]
    assert result.data["views"][0]["duplicates_removed"] == 1
    assert result.data["skipped_pictorial_views"] == []
    assert drawing.import_types == [32768]


def test_import_can_target_an_exact_set_of_views() -> None:
    drawing = _three_views(imports={"Top": ["D1@Sketch1"]})

    result = _Harness(drawing)._import_dimensions(only_views=["Top", "Ghost"])

    assert [v["view"] for v in result["views"]] == ["Top"]


@pytest.mark.asyncio
async def test_insert_with_only_pictorial_views_says_to_add_views() -> None:
    drawing = _Drawing([_View("Iso", "*Isometric")])

    result = await _Harness(drawing).insert_model_dimensions()

    assert "No drawing views found to dimension" in (result.error or "")
    assert "create_technical_drawing" in (result.error or "")


@pytest.mark.asyncio
async def test_insert_falls_back_to_autodimension() -> None:
    drawing = _three_views(autodim={"Front": ["RD1"], "Top": ["RD2"]})

    result = await _Harness(drawing).insert_model_dimensions()

    assert result.data["method"] == "auto_dimension"
    assert result.data["autodimension_status"] == 0
    assert result.data["dimensions_added"] == 2


@pytest.mark.asyncio
async def test_insert_that_adds_nothing_is_an_error() -> None:
    result = await _Harness(_three_views()).insert_model_dimensions()
    assert "No dimensions were added to any view" in (result.error or "")
    assert "AutoDimension returned 0" in (result.error or "")


def test_a_dimension_without_a_selection_name_is_not_deleted() -> None:
    harness = _Harness()
    no_specific = SimpleNamespace(GetSpecificAnnotation=lambda: None)
    assert harness._delete_display_dimension(_three_views(), no_specific) is False


def test_dimension_names_skip_other_annotations() -> None:
    view = _View("Front")
    view.items.append(_Note(view))
    view.add(None)
    view.add("D1@Sketch1")

    found = _Harness()._dimension_annotations(view)

    assert [name for _, name in found] == [None, "D1@Sketch1"]


def test_an_unreadable_dimension_count_is_zero() -> None:
    view = SimpleNamespace(GetDisplayDimensionCount=lambda: None)
    assert _Harness()._view_dimension_count(view) == 0


# ---- arrange_dimensions ---------------------------------------------------------


def _crowded() -> _Drawing:
    """Two views whose imported dimensions sit on the part."""
    drawing = _Drawing([_View("Front"), _View("Top", "*Top")])
    drawing.views["Top"].outline = (0.22, 0.10, 0.34, 0.17)
    drawing.views["Front"].add("D1@Sketch1", 0.06, 0.16)
    drawing.views["Front"].add("D2@Sketch1", 0.07, 0.11)
    drawing.views["Top"].add("D3@Sketch1", 0.23, 0.33)
    return drawing


@pytest.mark.asyncio
async def test_arrange_needs_a_drawing() -> None:
    result = await _Harness(SimpleNamespace(GetType=lambda: 2)).arrange_dimensions()
    assert result.error == "This operation requires a drawing document"


@pytest.mark.asyncio
async def test_arrange_unknown_view_lists_the_views() -> None:
    result = await _Harness(_crowded()).arrange_dimensions("Side")
    assert "No view named 'Side'. Views: Front, Top" in (result.error or "")


@pytest.mark.asyncio
async def test_arrange_moves_dimensions_off_the_views() -> None:
    drawing = _crowded()

    result = await _Harness(drawing).arrange_dimensions()

    assert result.is_success, result.error
    assert result.data["dimensions"] == 3
    assert result.data["moved"] == 3
    assert result.data["overlaps_before"] > 0
    assert result.data["overlaps_after"] == 0
    assert result.data["sheet_size_m"] == [0.42, 0.297]
    assert all(
        a.y < OUTLINE[1] or a.y > OUTLINE[3] for a in drawing.views["Front"].dims
    )


@pytest.mark.asyncio
async def test_arrange_one_view_leaves_the_others_alone() -> None:
    drawing = _crowded()
    top = drawing.views["Top"].dims[0]

    result = await _Harness(drawing).arrange_dimensions("Front")

    assert result.data["moved"] == 2
    assert (top.x, top.y) == (0.28, 0.12)
    # Top's dimension still sits on its view, so the sheet-wide check reports it.
    assert result.is_error


@pytest.mark.asyncio
async def test_overlaps_that_remain_are_an_error_with_the_list() -> None:
    drawing = _crowded()
    for view in drawing.views.values():
        view.movable = False

    result = await _Harness(drawing).arrange_dimensions()

    assert result.is_error
    assert result.data["moved"] == 0
    assert result.data["overlaps_after"] == len(result.data["remaining_overlaps"])
    assert result.error == _overlap_summary(result.data)
    assert result.execution_time == 0.5


def test_overlap_summary_names_the_first_five() -> None:
    overlaps = [
        {
            "dimension": f"Front#{i}",
            "conflicts_with": "Front",
            "kind": "on_view_geometry",
        }
        for i in range(7)
    ]
    summary = _overlap_summary(
        {"overlaps_after": 7, "dimensions": 7, "remaining_overlaps": overlaps}
    )
    assert summary.startswith(
        "7 dimension overlap(s) remain after arranging 7 dimension(s) "
        "(on_view_geometry): Front#0 vs Front (on_view_geometry)"
    )
    assert "Front#4" in summary and "Front#5" not in summary
    assert summary.endswith("so the views have room.")


def test_layout_can_check_without_moving() -> None:
    drawing = _crowded()
    result = _Harness(drawing)._arrange_layout(move=False)
    assert result["moved"] == 0
    assert result["overlaps_after"] == result["overlaps_before"] > 0


class _Unreadable:
    """An annotation whose display data is partly or wholly missing."""

    def __init__(self, position: Any = (0.1, 0.1, 0.0), data: Any = None) -> None:
        self._position, self._data = position, data

    def GetPosition(self):  # noqa: N802
        return self._position

    def GetDisplayData(self):  # noqa: N802
        return self._data


def test_dimension_geometry_needs_a_position_and_text() -> None:
    harness = _Harness()
    no_text = SimpleNamespace(
        GetTextCount=lambda: 1, GetTextPositionAtIndex=lambda _i: None
    )

    assert harness._dimension_geometry(_Unreadable(None), "k", "Front") is None
    assert harness._dimension_geometry(_Unreadable(data=no_text), "k", "Front") is None


def test_dimension_geometry_skips_short_line_records() -> None:
    data = SimpleNamespace(
        GetTextCount=lambda: 1,
        GetTextPositionAtIndex=lambda _i: (0.1, 0.2),
        GetTextAtIndex=lambda _i: "",
        GetTextHeightAtIndex=lambda _i: 0.0,
        GetTextInBoxWidthAtIndex=lambda _i: 0.004,
        GetLineCount=lambda: 2,
        GetLineAtIndex3=lambda i: (0, 0, 0, 0, 0.1, 0.2, 0, 0.15, 0.2) if i else (1, 2),
    )

    geometry = _Harness()._dimension_geometry(_Unreadable(data=data), "k", "Front")

    assert geometry.text_box == pytest.approx((0.1, 0.2, 0.104, 0.201))
    assert geometry.lines == [(0.1, 0.2, 0.15, 0.2)]


@pytest.mark.parametrize(
    "sheet",
    [
        None,
        SimpleNamespace(GetProperties2=lambda: (0, 0, 0)),
        SimpleNamespace(GetProperties2=lambda: (0, 0, 0, 0, 0, 0, 0.297)),
    ],
)
def test_sheet_bounds_are_none_when_unreadable(sheet) -> None:
    drawing = SimpleNamespace(GetCurrentSheet=lambda: sheet)
    assert _Harness()._sheet_bounds(drawing) is None


def test_collect_layout_skips_missing_views_and_outlines() -> None:
    drawing = _crowded()
    drawing.views["Top"].outline = None

    outlines, geometries, annotations = _Harness()._collect_layout(
        drawing, ["Front", "Top", "Ghost"]
    )

    assert list(outlines) == ["Front"]
    assert len(geometries) == len(annotations) == 3
