"""Sheet metal on fake COM objects shaped like SolidWorks 2026's (queue item 15).

Spec: tools/sheet-metal. The calls and their order are the ones the live
probes settled (design, "What the live probes settled").
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import sheet_metal as sm


class _Feature:
    def __init__(self, name: str, definition: Any = None) -> None:
        self.Name = name
        self._definition = definition
        self.selected: list[Any] = []

    def GetDefinition(self) -> Any:
        return self._definition

    def Select2(self, append: bool, mark: int) -> bool:
        self.selected.append((append, mark))
        return True


class _Manager:
    """IFeatureManager: records each call, builds unless told not to."""

    def __init__(self, builds: bool = True, patterns: int = 1) -> None:
        self.builds = builds
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.allowance = SimpleNamespace(Type=None, KFactor=None)
        self.bend = SimpleNamespace(
            BendAngle=None,
            UseDefaultBendRadius=None,
            BendRadius=None,
            ReverseDirection=None,
        )
        self._patterns = [_Feature("Flat-Pattern1") for _ in range(patterns)]

    def CreateCustomBendAllowance(self) -> Any:
        return self.allowance

    def InsertSheetMetalBaseFlange2(self, *args: Any) -> Any:
        self.calls.append(("base", args))
        data = SimpleNamespace(Thickness=0.002, BendRadius=0.002, KFactor=0.5)
        return _Feature("Base-Flange1", data) if self.builds else None

    def InsertSheetMetalEdgeFlange2(self, *args: Any) -> Any:
        self.calls.append(("edge", args))
        return _Feature("Edge-Flange1") if self.builds else None

    def CreateDefinition(self, kind: int) -> Any:
        self.calls.append(("definition", (kind,)))
        return self.bend

    def CreateFeature(self, data: Any) -> Any:
        self.calls.append(("feature", (data,)))
        return _Feature("Sketched Bend1") if self.builds else None

    def GetFlatPatternFolder(self) -> Any:
        return SimpleNamespace(GetFlatPatterns=lambda: self._patterns)


class _SketchManager:
    def __init__(self) -> None:
        self.AddToDB = False
        self.lines: list[tuple[float, ...]] = []
        self.closed = False

    def SketchUseEdge(self, chain: bool) -> bool:
        return True

    def CreateLine(self, *coords: float) -> Any:
        self.lines.append(coords)
        return object()

    def InsertSketch(self, rebuild: bool) -> None:
        self.closed = True


class _Model:
    def __init__(
        self, sheet: bool = True, closed: bool | None = True, builds: bool = True
    ) -> None:
        self.FeatureManager = _Manager(builds)
        self.SketchManager = _SketchManager()
        self._sheet = sheet
        self._closed = closed
        point = SimpleNamespace
        line = SimpleNamespace(
            GetStartPoint2=lambda: point(X=-0.05, Y=0.0),
            GetEndPoint2=lambda: point(X=0.05, Y=0.0),
        )
        self._profile = SimpleNamespace(GetSketchSegments=lambda: [line])
        self.edge = SimpleNamespace(
            GetCurveParams2=lambda: [-0.05, 0, 0.03, 0.05, 0, 0.03, 0, 1, 0, 0, 0],
            Select4=lambda append, data: True,
        )
        self.SelectionManager = SimpleNamespace(
            GetSelectedObject6=lambda index, mark: self.edge
        )
        self.edited = False

    def GetBodies2(self, kind: int, visible: bool) -> list[Any]:
        return [SimpleNamespace(IsSheetMetal=lambda: self._sheet)]

    def FeatureByName(self, name: str) -> Any:
        if self._closed is None:
            return None
        contour = SimpleNamespace(IsClosed=lambda: self._closed)
        sketch = SimpleNamespace(GetSketchContours=lambda: [contour])
        return SimpleNamespace(GetSpecificFeature2=lambda: sketch)

    def ClearSelection2(self, everything: bool) -> None:
        return None

    def InsertSketchForEdgeFlange(self, edge: Any, angle: float, flip: bool) -> Any:
        return _Feature("Sketch2")

    def EditSketch(self) -> None:
        self.edited = True

    def GetActiveSketch2(self) -> Any:
        return self._profile


class _Harness(sm.SolidWorksSheetMetalMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any) -> None:
        self.currentModel = model
        self._last_sketch_name: str | None = "Sketch1"
        self.suppressed: list[tuple[str, bool]] = []
        self.suppress_error: str | None = None

    def _attempt(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception:
            return default

    def _handle_com_operation(self, name: str, operation: Any) -> AdapterResult[Any]:
        try:
            data = operation()
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    async def _measured(
        self, operation: str, build: Any, *, first_feature: bool = False
    ) -> AdapterResult[Any]:
        result = self._handle_com_operation(operation, build)
        if result.is_success:
            result.data["first_feature"] = first_feature
        return result

    async def get_model_geometry_summary(self) -> AdapterResult[dict[str, Any]]:
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"bounding_box_mm": {"size": [100.0, 2.0, 78.7]}},
        )

    async def suppress_feature(self, name: str, suppress: bool = True) -> Any:
        self.suppressed.append((name, suppress))
        if self.suppress_error:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=self.suppress_error
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={})


class _Picker:
    """_BodyEntityPicker: one edge at a set distance."""

    distance = 0.0
    selects = True

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def nearest(self, getter: str, point: tuple[float, float, float]) -> Any:
        if self.distance is None:
            return None
        return (self.adapter.currentModel.edge, self.distance)

    def select(self, entity: Any, append: bool, mark: int = 0) -> bool:
        return self.selects


@pytest.fixture(autouse=True)
def _plain_com(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sm.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(sm, "_null_callout", lambda: None)
    monkeypatch.setattr(sm, "dispatch_array", lambda values: list(values))
    monkeypatch.setattr(sm, "_select_named_feature", lambda *a, **k: True)
    monkeypatch.setattr(sm, "_BodyEntityPicker", _Picker)
    _Picker.distance = 0.0
    _Picker.selects = True


@pytest.mark.asyncio
async def test_a_base_flange_with_its_k_factor_read_back() -> None:
    model = _Model(sheet=False)
    harness = _Harness(model)

    result = await harness.create_base_flange(2.0, 2.0, 0.4)

    args = model.FeatureManager.calls[0][1]
    assert args[0] == 0.002 and args[2] == 0.002
    assert args[8] == 1  # DirToUse: 0 builds nothing
    assert (
        model.FeatureManager.allowance.Type,
        model.FeatureManager.allowance.KFactor,
    ) == (2, 0.4)
    assert result.data == {
        "name": "Base-Flange1",
        "sketch": "Sketch1",
        "thickness_mm": 2.0,
        "bend_radius_mm": 2.0,
        "k_factor": 0.5,
        "read_back": True,
        "first_feature": True,
    }


@pytest.mark.asyncio
async def test_base_flange_refusals_and_an_unreadable_feature() -> None:
    no_sketch = _Harness(_Model())
    no_sketch._last_sketch_name = None
    open_profile = await _Harness(_Model(closed=False)).create_base_flange(2.0, 2.0)
    nothing = await _Harness(_Model(builds=False)).create_base_flange(2.0, 2.0)
    unread_model = _Model(closed=None)
    unread_model.FeatureManager.InsertSheetMetalBaseFlange2 = lambda *a: _Feature("B1")
    unread = await _Harness(unread_model).create_base_flange(2.0, 3.0, 0.45, depth=10)

    assert (
        "No sketch to make the base flange"
        in (await no_sketch.create_base_flange(2.0, 2.0)).error
    )
    assert "open profile, so it needs depth" in open_profile.error
    assert "made no base flange from 'Sketch1'" in nothing.error
    assert (unread.data["bend_radius_mm"], unread.data["read_back"]) == (3.0, False)


@pytest.mark.asyncio
async def test_a_base_flange_needs_its_sketch_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sm, "_select_named_feature", lambda *a, **k: False)

    result = await _Harness(_Model()).create_base_flange(2.0, 2.0, sketch="Sketch9")

    assert "Couldn't select the sketch 'Sketch9'" in result.error


@pytest.mark.asyncio
async def test_an_edge_flange_draws_its_profile_then_builds() -> None:
    model = _Model()

    result = await _Harness(model).add_edge_flange([0.0, 0.0, 30.0], 20.0)

    assert model.edited and model.SketchManager.closed
    assert model.SketchManager.lines == [
        (-0.05, 0.0, 0.0, -0.05, 0.02, 0.0),
        (-0.05, 0.02, 0.0, 0.05, 0.02, 0.0),
        (0.05, 0.02, 0.0, 0.05, 0.0, 0.0),
    ]
    edge_args = model.FeatureManager.calls[0][1]
    assert edge_args[0] == [model.edge]
    assert edge_args[2] == 1  # the sheet's radius
    assert edge_args[6] == pytest.approx(0.02)
    assert result.data["edge_length_mm"] == 100.0
    assert result.data["name"] == "Edge-Flange1"


@pytest.mark.asyncio
async def test_edge_flange_refusals() -> None:
    plain = await _Harness(_Model(sheet=False)).add_edge_flange([0, 0, 30], 20)
    empty = await _Harness(None).add_edge_flange([0, 0, 30], 20)
    _Picker.distance = 0.005
    far = await _Harness(_Model()).add_edge_flange([0, 0, 0], 20)
    _Picker.distance = None
    none = await _Harness(_Model()).add_edge_flange([0, 0, 0], 20)
    _Picker.distance = 0.0
    _Picker.selects = False
    unselected = await _Harness(_Model()).add_edge_flange([0, 0, 30], 20)
    _Picker.selects = True
    unbuilt = await _Harness(_Model(builds=False)).add_edge_flange(
        [0, 0, 30], 20, 45.0, 3.0, True
    )

    assert "needs a sheet-metal part" in plain.error
    assert "Start with create_base_flange" in plain.error
    assert empty.error == "No active model"
    assert (
        "No sheet edge at [0, 0, 0] mm" in far.error and "No sheet edge" in none.error
    )
    assert "Couldn't select the edge" in unselected.error
    assert "made no edge flange" in unbuilt.error


@pytest.mark.asyncio
async def test_an_edge_without_ends_and_a_failed_profile() -> None:
    model = _Model()
    model.edge.GetCurveParams2 = lambda: []
    no_profile = _Model()
    no_profile.InsertSketchForEdgeFlange = lambda *a: None

    measured = await _Harness(model).add_edge_flange([0, 0, 30], 20)
    failed = await _Harness(no_profile).add_edge_flange([0, 0, 30], 20)

    assert measured.data["edge_length_mm"] is None
    assert "made no profile sketch" in failed.error


@pytest.mark.asyncio
async def test_a_sketched_bend_and_its_box() -> None:
    model = _Model()

    result = await _Harness(model).create_sketched_bend(90.0, 3.0, reverse=True)

    bend = model.FeatureManager.bend
    assert model.FeatureManager.calls[0] == ("definition", (35,))
    assert bend.UseDefaultBendRadius is False and bend.BendRadius == 0.003
    assert bend.ReverseDirection is True
    assert result.data["bounding_box_mm"]["size"] == [100.0, 2.0, 78.7]


@pytest.mark.asyncio
async def test_sketched_bend_refusals(monkeypatch: pytest.MonkeyPatch) -> None:
    no_sketch = _Harness(_Model())
    no_sketch._last_sketch_name = None
    plain = await _Harness(_Model(sheet=False)).create_sketched_bend()
    unbuilt = await _Harness(_Model(builds=False)).create_sketched_bend()
    monkeypatch.setattr(sm, "_select_named_feature", lambda *a, **k: False)
    unselected = await _Harness(_Model()).create_sketched_bend()

    assert (
        "No sketch with a bend line" in (await no_sketch.create_sketched_bend()).error
    )
    assert "needs a sheet-metal part" in plain.error
    assert "made no sketched bend" in unbuilt.error
    assert "Couldn't select the sketch" in unselected.error


@pytest.mark.asyncio
async def test_flat_and_folded_through_the_flat_pattern_feature() -> None:
    harness = _Harness(_Model())

    flat = await harness.set_flat_pattern(True)
    folded = await harness.set_flat_pattern(False)

    assert harness.suppressed == [("Flat-Pattern1", False), ("Flat-Pattern1", True)]
    assert flat.data == {
        "flat": True,
        "feature": "Flat-Pattern1",
        "bounding_box_mm": {"size": [100.0, 2.0, 78.7]},
    }
    assert folded.data["flat"] is False


@pytest.mark.asyncio
async def test_flat_pattern_failures() -> None:
    plain = await _Harness(_Model(sheet=False)).set_flat_pattern(True)
    none = _Model()
    none.FeatureManager = _Manager(patterns=0)
    missing = await _Harness(none).set_flat_pattern(True)
    refused = _Harness(_Model())
    refused.suppress_error = "Couldn't suppress"

    assert "needs a sheet-metal part" in plain.error
    assert "has no flat pattern" in missing.error
    assert (await refused.set_flat_pattern(True)).error == "Couldn't suppress"


@pytest.mark.asyncio
async def test_a_sketch_with_no_contours_is_not_judged() -> None:
    model = _Model()
    model.FeatureByName = lambda name: SimpleNamespace(
        GetSpecificFeature2=lambda: SimpleNamespace(GetSketchContours=lambda: [])
    )

    result = await _Harness(model).create_base_flange(2.0, 2.0)

    assert result.is_success
