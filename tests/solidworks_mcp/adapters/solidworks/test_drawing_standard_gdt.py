"""Tests for the GD&T annotations (``add_gtol``, ``add_datum_tag``) against a fake drawing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.drawing_standard import (
    SolidWorksDrawingStandardMixin,
)


class _Annotation:
    def __init__(self) -> None:
        self.position: tuple[float, float, float] | None = None

    def SetPosition(self, x, y, z):  # noqa: N802
        self.position = (x, y, z)
        return True


class _Gtol:
    """A frame that stores what it is given and reads it back."""

    def __init__(self, read_back: Any = "stored") -> None:
        self.symbols: tuple | None = None
        self.values: tuple | None = None
        self.read_back = read_back
        self.annotation = _Annotation()

    def SetFrameSymbols2(self, *args):  # noqa: N802
        self.symbols = args
        return True

    def SetFrameValues(self, *args):  # noqa: N802
        self.values = args
        return True

    def GetFrameValues(self, _frame):  # noqa: N802
        return self.values[1:] if self.read_back == "stored" else self.read_back

    def GetAnnotation(self):  # noqa: N802
        return self.annotation


class _DatumTag:
    def __init__(self, read_back: str | None = None) -> None:
        self.label = ""
        self.read_back = read_back
        self.annotation = _Annotation()

    def SetLabel(self, label):  # noqa: N802
        self.label = label
        return True

    def GetLabel(self):  # noqa: N802
        return self.label if self.read_back is None else self.read_back

    def GetAnnotation(self):  # noqa: N802
        return self.annotation


class _Model:
    """A drawing that records edge picks and hands out frames and tags."""

    def __init__(self, *, edge: bool = True, gtol=None, tag=None) -> None:
        self.picks: list[tuple[float, float]] = []
        self.edge = edge
        self.gtol = gtol
        self.tag = tag
        self.Extension = SimpleNamespace(SelectByID2=self._select)

    def _select(self, _name, kind, x, y, *_rest):
        assert kind == "EDGE"
        self.picks.append((x, y))
        return self.edge

    def GetType(self):  # noqa: N802
        return 3

    def ClearSelection2(self, _all):  # noqa: N802
        return True

    def GraphicsRedraw2(self):  # noqa: N802
        return None

    def InsertGtol(self):  # noqa: N802
        return self.gtol

    def InsertDatumTag2(self):  # noqa: N802
        return self.tag


class _Harness(SolidWorksDrawingStandardMixin):
    def __init__(self, model: Any) -> None:
        self.currentModel = model

    def _require_drawing(self):
        if self.currentModel.GetType() != 3:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="This operation requires a drawing document",
            )
        return None

    def _handle_com_operation(self, name, operation, *args):
        try:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=operation(*args)
            )
        except Exception as exc:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {exc}"
            )

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, attr_name):
        value = getattr(obj, attr_name)
        return value() if callable(value) else value


# ---- add_gtol ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_position_frame_with_a_leader_to_a_hole() -> None:
    gtol = _Gtol()
    model = _Model(gtol=gtol)

    result = await _Harness(model).add_gtol(
        "position", 0.2, 60.0, 250.0, True, "mmc", ["a", "B", "c"], (62.0, 218.0)
    )

    assert result.is_success, result.error
    assert model.picks == [pytest.approx((0.062, 0.218))]
    assert gtol.symbols == (1, "<IGTOL-POSI>", True, "<MOD-MMC>", False, "", "", "", "")
    assert gtol.values == (1, "0.2", "", "A", "B", "C")
    assert gtol.annotation.position == pytest.approx((0.06, 0.25, 0.0))
    assert result.data == {
        "characteristic": "position",
        "tolerance": "0.2",
        "diameter_zone": True,
        "material_condition": "mmc",
        "datums": ["A", "B", "C"],
        "attached": True,
        "position_mm": [60.0, 250.0],
        "layout": None,
    }


@pytest.mark.asyncio
async def test_a_free_standing_flatness_frame() -> None:
    gtol = _Gtol()
    model = _Model(gtol=gtol)

    result = await _Harness(model).add_gtol("flatness", 0.05, 30.0, 40.0)

    assert result.data["attached"] is False and model.picks == []
    assert gtol.values == (1, "0.05", "", "", "", "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "attach", "error"),
    [
        (_Model(edge=False, gtol=_Gtol()), (1.0, 2.0), "No drawing edge found"),
        (_Model(gtol=None), None, "InsertGtol returned nothing"),
        (_Model(gtol=_Gtol(read_back=("0.3", "", "A", "", ""))), None, "did not take"),
        (_Model(gtol=_Gtol(read_back=None)), None, "read back None"),
    ],
    ids=["no edge", "no frame", "wrong values", "unreadable"],
)
async def test_a_frame_that_is_not_made_as_asked_is_an_error(
    model, attach, error
) -> None:
    result = await _Harness(model).add_gtol(
        "position", 0.2, 0.0, 0.0, datums=["A"], attach_at_mm=attach
    )

    assert error in (result.error or "")


@pytest.mark.asyncio
async def test_bad_frame_inputs_and_a_part_are_refused() -> None:
    harness = _Harness(_Model(gtol=_Gtol()))
    bad = await harness.add_gtol("wobble", 0.2, 0.0, 0.0)
    harness.currentModel.GetType = lambda: 1
    on_part = await harness.add_gtol("position", 0.2, 0.0, 0.0)

    assert "characteristic must be one of" in bad.error
    assert on_part.error == "This operation requires a drawing document"


# ---- add_datum_tag ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_datum_tag_on_an_edge() -> None:
    tag = _DatumTag()
    model = _Model(tag=tag)

    result = await _Harness(model).add_datum_tag(" a ", (120.0, 95.0), 120.0, 85.0)

    assert result.data == {"label": "A", "position_mm": [120.0, 85.0]}
    assert model.picks == [pytest.approx((0.12, 0.095))]
    assert tag.annotation.position == pytest.approx((0.12, 0.085, 0.0))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "error"),
    [
        (_Model(edge=False, tag=_DatumTag()), "No drawing edge found"),
        (_Model(tag=None), "InsertDatumTag2 returned nothing"),
        (_Model(tag=_DatumTag(read_back="Z")), "reads 'Z', not 'A'"),
    ],
    ids=["no edge", "no tag", "wrong label"],
)
async def test_a_datum_tag_not_made_as_asked_is_an_error(model, error) -> None:
    result = await _Harness(model).add_datum_tag("A", (0.0, 0.0), 0.0, 0.0)

    assert error in (result.error or "")


@pytest.mark.asyncio
async def test_a_datum_tag_without_an_annotation_still_reads_back() -> None:
    tag = SimpleNamespace(label="", SetLabel=None, GetLabel=lambda: "B")
    tag.SetLabel = lambda label: setattr(tag, "label", label)

    result = await _Harness(_Model(tag=tag)).add_datum_tag("B", (0.0, 0.0), 1.0, 2.0)

    assert result.is_success, result.error


@pytest.mark.asyncio
async def test_bad_labels_and_a_part_are_refused() -> None:
    harness = _Harness(_Model(tag=_DatumTag()))
    bad = await harness.add_datum_tag("AB", (0.0, 0.0), 0.0, 0.0)
    harness.currentModel.GetType = lambda: 1
    on_part = await harness.add_datum_tag("A", (0.0, 0.0), 0.0, 0.0)

    assert "single letter" in bad.error
    assert on_part.error == "This operation requires a drawing document"


# ---- a frame on a drawing dimension -------------------------------------------


@pytest.fixture
def on_plan(monkeypatch):
    """A drawing whose plan view holds two dimensions; selections are recorded."""
    import solidworks_mcp.adapters.solidworks.drawing_standard as std

    views = {"Drawing View2": object()}
    monkeypatch.setattr(
        std, "_resolve_drawing_view", lambda _a, _d, name: views.get(name)
    )
    gtol = _Gtol()
    harness = _Harness(_Model(gtol=gtol))
    first = object()
    hole = SimpleNamespace(GetPosition=lambda: (0.03, 0.16, 0.0))
    harness._dimension_annotations = lambda _view: [
        (first, "D1@Sketch1"),
        (hole, "D3@Sketch1"),
    ]
    harness.selected = []
    harness._select_display_dimension = lambda _model, an: (
        harness.selected.append(an) or True
    )
    # The frame hangs under the Ø text: its texts, and a line wider than them.
    harness.frame = SimpleNamespace(
        text_box=(0.031, 0.150, 0.050, 0.155), lines=[(0.028, 0.149, 0.052, 0.149)]
    )
    harness._dimension_geometry = lambda _an, _key, _view: harness.frame
    harness._drawing = lambda: "drawing"
    harness._sheet_note_boxes = lambda _drawing: {"note 0": (0.1, 0.1, 0.12, 0.11)}
    harness._collect_layout = lambda _d, names: (
        {},
        [SimpleNamespace(key=f"{names[0]}#2", position=(0.03, 0.16))],
        {},
    )
    harness.remaining = 0
    harness.laid_out = []

    def _arrange(view_name, obstacles, work_area=None, attached=None):
        harness.laid_out.append((view_name, sorted(obstacles), attached))
        assert work_area == std.WORK_AREA
        return {"overlaps_after": harness.remaining, "remaining_overlaps": []}

    harness._arrange_layout = _arrange
    return harness, gtol, hole


@pytest.mark.asyncio
async def test_a_position_frame_on_the_hole_dimension(on_plan) -> None:
    harness, gtol, hole = on_plan

    result = await harness.add_gtol(
        "position",
        0.2,
        0.0,
        0.0,
        True,
        "mmc",
        ["A", "B", "C"],
        dimension=("Drawing View2", "D3@Sketch1"),
    )

    assert result.is_success, result.error
    assert harness.selected == [hole]
    assert result.data["attached"] == "D3@Sketch1"
    assert result.data["position_mm"] is None
    assert gtol.annotation.position is None  # SolidWorks keeps it under the text
    # The view is laid out again with the frame counted as part of the Ø
    # dimension, relative to where that dimension sits.
    ((view, obstacles, attached),) = harness.laid_out
    assert view == "Drawing View2"
    assert obstacles == ["note 0", "title block"]
    assert attached == {
        "Drawing View2#2": pytest.approx((-0.002, -0.011, 0.022, -0.005))
    }
    assert result.data["layout"]["overlaps_after"] == 0
    # What the layout used is reported, so a frame placed badly can be traced.
    assert result.data["layout"]["frame_box_mm"] == pytest.approx(
        [28.0, 149.0, 52.0, 155.0]
    )
    assert result.data["layout"]["obstacles"] == ["note 0", "title block"]


@pytest.mark.asyncio
async def test_a_frame_that_leaves_an_overlap_is_an_error(on_plan) -> None:
    harness, _gtol, _hole = on_plan
    harness.remaining = 2

    result = await harness.add_gtol(
        "position", 0.2, 0.0, 0.0, dimension=("Drawing View2", "D3@Sketch1")
    )

    assert result.error == (
        "The frame was added but 2 overlap(s) remain on the sheet - the "
        "no-overlap rule is not met; see layout"
    )
    assert result.data["layout"]["overlaps_after"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (
            lambda h, g: setattr(h, "frame", None),
            "Cannot measure the frame, so it cannot be kept clear",
        ),
        (
            lambda h, g: setattr(g, "annotation", None),
            "Cannot measure the frame, so it cannot be kept clear",
        ),
        (
            lambda h, g: setattr(h, "_collect_layout", lambda _d, _n: ({}, [], {})),
            "The frame's dimension is not among the view's",
        ),
    ],
    ids=["no display data", "no annotation", "dimension not read"],
)
async def test_a_frame_that_cannot_be_kept_clear_is_an_error(
    on_plan, break_it, message
) -> None:
    harness, gtol, _hole = on_plan
    break_it(harness, gtol)

    result = await harness.add_gtol(
        "position", 0.2, 0.0, 0.0, dimension=("Drawing View2", "D3@Sketch1")
    )

    assert message in result.error


@pytest.mark.asyncio
async def test_a_part_dimension_on_an_assembly_drawing_is_found(on_plan) -> None:
    harness, _gtol, hole = on_plan
    harness._dimension_annotations = lambda _view: [
        (object(), None),
        (hole, "D3@Sketch1@Demo Plate-1@Plate Stack"),
    ]

    result = await harness.add_gtol(
        "position", 0.2, 0.0, 0.0, dimension=("Drawing View2", "D3@Sketch1")
    )

    assert result.is_success, result.error
    assert harness.selected == [hole]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dimension",
    [("Drawing View2", "D9@Sketch1"), ("Drawing View7", "D3@Sketch1")],
    ids=["unknown dimension", "unknown view"],
)
async def test_a_frame_on_a_missing_dimension_is_an_error(on_plan, dimension) -> None:
    harness, _gtol, _hole = on_plan

    result = await harness.add_gtol("position", 0.2, 0.0, 0.0, dimension=dimension)

    assert f"No dimension {dimension[1]!r} in view {dimension[0]!r}" in result.error
