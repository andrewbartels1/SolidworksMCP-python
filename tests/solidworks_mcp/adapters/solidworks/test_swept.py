"""Helices and sweeps on fake COM objects shaped like SolidWorks 2026's (queue item 34).

Spec: tools/helix and tools/swept-features. The calls and selection marks
are the ones the live probe of 2026-11-24 settled (design, "What the live
demo has to settle").
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    HelixParameters,
    SweepParameters,
)
from solidworks_mcp.adapters.solidworks import swept
from solidworks_mcp.exceptions import InputRefused


class _Segment:
    """ISketchSegment / ISketchArc."""

    def __init__(self, kind: int | None, circle: bool = False, radius: float = 0.01):
        self._kind, self._circle, self._radius = kind, circle, radius

    def GetType(self) -> int:
        if self._kind is None:
            raise RuntimeError("unreadable")
        return self._kind

    def IsCircle(self) -> int:
        return int(self._circle)

    def GetRadius(self) -> float:
        return self._radius


def _sketch(*segments: _Segment) -> Any:
    """A sketch feature holding ``segments``."""
    body = SimpleNamespace(GetSketchSegments=lambda: list(segments))
    return SimpleNamespace(GetSpecificFeature2=lambda: body)


def _helix_feature(start: Any = (0.0, 0.0, 0.01), readable: bool = True) -> Any:
    """A helix feature whose curve reads back a 504.924 mm length."""
    params = SimpleNamespace(
        StartPoint=start, EndPoint=(0.0, 0.048, 0.01), UMinValue=0.0, UMaxValue=1.0
    )
    curve = SimpleNamespace(GetLength3=lambda u0, u1: 0.504924)
    edge = SimpleNamespace(GetCurveParams3=lambda: params, GetCurve=lambda: curve)

    def first() -> Any:
        if not readable:
            raise RuntimeError("no curve")
        return edge

    reference = SimpleNamespace(GetFirstSegment=first)
    return SimpleNamespace(GetSpecificFeature2=lambda: reference)


class _Manager:
    """IFeatureManager: records each sweep call, builds unless told not to."""

    def __init__(self) -> None:
        self.builds = True
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def InsertProtrusionSwept4(self, *args: Any) -> Any:
        self.calls.append(("boss", args))
        return SimpleNamespace(Name="Sweep1") if self.builds else None

    def InsertCutSwept5(self, *args: Any) -> Any:
        self.calls.append(("cut", args))
        return SimpleNamespace(Name="Cut-Sweep1") if self.builds else None


class _Model:
    """IModelDoc2 with a tree of (type, name) and named features."""

    def __init__(self) -> None:
        self.features: dict[str, Any] = {
            "Sketch1": _sketch(_Segment(1, circle=True, radius=0.01))
        }
        self.tree: list[tuple[str, str]] = [("ProfileFeature", "Sketch1")]
        self.helix_args: tuple[Any, ...] | None = None
        self.makes: str | None = "Helix"
        self.helix = _helix_feature()
        self.FeatureManager = _Manager()

    def FeatureByName(self, name: str) -> Any:
        return self.features.get(name)

    def ClearSelection2(self, everything: bool) -> None:
        return None

    def InsertHelix(self, *args: Any) -> None:
        self.helix_args = args
        if self.makes:
            name = "Helix/Spiral1"
            self.tree.append((self.makes, name))
            self.features[name] = self.helix


class _Harness(swept.SolidWorksSweptMixin):
    """The mixin plus the PyWin32Adapter members it relies on."""

    def __init__(self, model: Any) -> None:
        self.currentModel = model
        self._last_sketch_name: str | None = None
        self.measured: dict[str, Any] = {}
        self.measure_error: str | None = None

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

    def _get_feature_id(self, feature: Any) -> str:
        return "id-7"

    async def _measured(
        self,
        operation: str,
        build: Any,
        *,
        first_feature: bool = False,
        direction: int = 0,
    ) -> AdapterResult[Any]:
        self.measured = {"first_feature": first_feature, "direction": direction}
        if self.measure_error:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=self.measure_error
            )
        result = self._handle_com_operation(operation, build)
        if result.is_success:
            result.data.update(volume_before=0.0, volume_after=1586.2)
        return result


@pytest.fixture
def selected(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, bool]]:
    """Plain COM, the tree read from the fake model, selections recorded."""
    picks: list[tuple[str, int, bool]] = []

    def select(adapter: Any, name: str, mark: int, append: bool) -> bool:
        picks.append((name, mark, append))
        return name in adapter.currentModel.features

    monkeypatch.setattr(swept.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(swept, "_select_named_feature", select)
    monkeypatch.setattr(swept, "_tree_features", lambda a: list(a.currentModel.tree))
    monkeypatch.setattr(
        swept,
        "_profile_feature_names",
        lambda a: [n for k, n in a.currentModel.tree if k == "ProfileFeature"],
    )
    return picks


# ── create_helix ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_helix_by_height_and_pitch(selected: list[Any]) -> None:
    model = _Model()
    harness = _Harness(model)

    result = await harness.create_helix(
        HelixParameters(sketch="Sketch1@Part1", height=48, pitch=6, start_angle=90)
    )

    assert result.is_success, result.error
    assert model.helix_args == (
        False,
        False,
        False,
        False,
        2,
        0.048,
        0.006,
        8.0,
        0.0,
        pytest.approx(math.pi / 2),
    )
    assert selected == [("Sketch1", 0, False)]
    data = result.data
    assert data["name"] == "Helix/Spiral1"
    assert (data["height_mm"], data["pitch_mm"], data["revolutions"]) == (48, 6, 8)
    assert data["diameter_mm"] == 20
    assert data["length_mm"] == 504.924 and data["length_measured"] is True
    assert data["start_point_mm"] == [0.0, 0.0, 10.0]
    assert data["end_point_mm"] == [0.0, 48.0, 10.0]
    assert data["taper_angle"] is None


@pytest.mark.asyncio
async def test_a_tapered_helix_sends_the_taper(selected: list[Any]) -> None:
    model = _Model()

    result = await _Harness(model).create_helix(
        HelixParameters(
            sketch="Sketch1",
            defined_by="height_and_revolutions",
            height=30,
            revolutions=5,
            taper_angle=10,
            taper_outward=True,
            clockwise=True,
            reverse=True,
        )
    )

    assert result.is_success, result.error
    args = model.helix_args or ()
    assert args[:5] == (True, True, True, True, 1)
    assert args[8] == pytest.approx(math.radians(10))
    assert result.data["taper_angle"] == 10 and result.data["taper_outward"] is True


@pytest.mark.asyncio
async def test_an_unreadable_curve_falls_back_to_the_worked_out_length(
    selected: list[Any],
) -> None:
    model = _Model()
    model.helix = _helix_feature(readable=False)

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", defined_by="spiral", pitch=5, revolutions=3)
    )

    assert result.is_success, result.error
    assert result.data["height_mm"] == 0
    assert result.data["length_measured"] is False
    assert result.data["length_mm"] == round(math.pi * 3 * (20 + 3 * 5), 3)
    assert result.data["start_point_mm"] is None
    assert (model.helix_args or ())[4] == 3


@pytest.mark.asyncio
async def test_a_short_start_point_reads_as_none(selected: list[Any]) -> None:
    model = _Model()
    model.helix = _helix_feature(start=(0.0, 0.0))

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert result.data["start_point_mm"] is None


@pytest.mark.asyncio
async def test_a_helix_needs_an_active_model() -> None:
    result = await _Harness(None).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_a_helix_missing_a_value_makes_nothing(selected: list[Any]) -> None:
    model = _Model()

    result = await _Harness(model).create_helix(
        HelixParameters(
            sketch="Sketch1", defined_by="height_and_revolutions", height=30
        )
    )

    assert "needs revolutions" in (result.error or "")
    assert model.helix_args is None


@pytest.mark.asyncio
async def test_a_missing_base_sketch_lists_the_sketches(selected: list[Any]) -> None:
    result = await _Harness(_Model()).create_helix(
        HelixParameters(sketch="Sketch9", height=48, pitch=6)
    )

    assert "No sketch named 'Sketch9'" in (result.error or "")
    assert "Sketches: Sketch1" in (result.error or "")


@pytest.mark.asyncio
async def test_a_missing_base_sketch_in_an_empty_part(selected: list[Any]) -> None:
    model = _Model()
    model.tree = []

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch9", height=48, pitch=6)
    )

    assert "Sketches: none" in (result.error or "")


@pytest.mark.parametrize(
    ("segments", "holds"),
    [
        ((), "holds nothing"),
        (
            (_Segment(1, circle=True), _Segment(1, circle=True)),
            "holds 2 circles",
        ),
        (
            (_Segment(1, circle=True), _Segment(0), _Segment(0), _Segment(1)),
            "holds 1 circle, 1 arc, 2 lines",
        ),
        ((_Segment(9), _Segment(None)), "1 other entity, 1 unreadable entity"),
    ],
)
@pytest.mark.asyncio
async def test_the_base_sketch_must_be_one_circle(
    selected: list[Any], segments: tuple[_Segment, ...], holds: str
) -> None:
    model = _Model()
    model.features["Sketch1"] = _sketch(*segments)

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert holds in (result.error or "")
    assert model.helix_args is None


@pytest.mark.asyncio
async def test_an_unreadable_sketch_holds_nothing(selected: list[Any]) -> None:
    model = _Model()
    model.features["Sketch1"] = SimpleNamespace(GetSpecificFeature2=lambda: None)

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert "holds nothing" in (result.error or "")


@pytest.mark.asyncio
async def test_an_unselectable_base_sketch(
    selected: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(swept, "_select_named_feature", lambda *a: False)
    model = _Model()

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert "Couldn't select the sketch 'Sketch1'" in (result.error or "")
    assert model.helix_args is None


@pytest.mark.parametrize("makes", [None, "RefAxis"])
@pytest.mark.asyncio
async def test_no_new_helix_is_an_error(selected: list[Any], makes: str | None) -> None:
    model = _Model()
    model.makes = makes

    result = await _Harness(model).create_helix(
        HelixParameters(sketch="Sketch1", height=48, pitch=6)
    )

    assert "SolidWorks made no helix on 'Sketch1'" in (result.error or "")


# ── sweeps ───────────────────────────────────────────────────────────────


def _two_sketches() -> _Model:
    """A profile (Sketch2) and a path (Sketch3) beside the base sketch."""
    model = _Model()
    for name in ("Sketch2", "Sketch3"):
        model.tree.append(("ProfileFeature", name))
        model.features[name] = _sketch()
    return model


@pytest.mark.asyncio
async def test_a_named_profile_along_a_path(selected: list[Any]) -> None:
    model = _two_sketches()
    harness = _Harness(model)
    harness._last_sketch_name = "Sketch3"

    result = await harness.create_sweep(
        SweepParameters(
            path="sketch3", profile="Sketch1", twist_along_path=True, twist_angle=90
        )
    )

    assert result.is_success, result.error
    assert selected == [("Sketch1", 1, False), ("Sketch3", 4, True)]
    kind, args = model.FeatureManager.calls[0]
    assert kind == "boss" and len(args) == 20
    assert args[2] == 8 and args[15] == pytest.approx(math.pi / 2)
    assert args[12] is True  # Merge
    assert (args[17], args[18]) == (False, 0.0)
    feature = result.data
    assert (feature.name, feature.type, feature.id) == ("Sweep1", "Sweep", "id-7")
    assert feature.parameters["profile"] == "Sketch1"
    assert feature.parameters["path"] == "Sketch3"
    assert feature.parameters["merge_result"] is True
    assert feature.parameters["volume_after"] == 1586.2
    assert harness.measured == {"first_feature": True, "direction": 1}


@pytest.mark.asyncio
async def test_a_circle_along_a_helix_selects_only_the_path(
    selected: list[Any],
) -> None:
    model = _Model()
    model.features["Helix/Spiral1"] = model.helix

    result = await _Harness(model).create_sweep(
        SweepParameters(path="Helix/Spiral1", circular_profile_diameter=2)
    )

    assert result.is_success, result.error
    assert selected == [("Helix/Spiral1", 4, False)]
    args = model.FeatureManager.calls[0][1]
    assert (args[17], args[18]) == (True, 0.002)
    assert result.data.parameters["profile"] is None
    assert result.data.parameters["circular_profile_diameter_mm"] == 2


@pytest.mark.asyncio
async def test_a_cut_sweep_removes_material(selected: list[Any]) -> None:
    model = _two_sketches()
    harness = _Harness(model)

    result = await harness.create_cut_sweep(SweepParameters(path="Sketch3"))

    assert result.is_success, result.error
    kind, args = model.FeatureManager.calls[0]
    assert kind == "cut" and len(args) == 22
    assert (args[2], args[14], args[19], args[20]) == (0, 0.0, False, 0.0)
    # The sketch closed last isn't tracked, so the latest other sketch.
    assert result.data.parameters["profile"] == "Sketch2"
    assert result.data.type == "CutSweep"
    assert "merge_result" not in result.data.parameters
    assert harness.measured == {"first_feature": False, "direction": -1}


@pytest.mark.asyncio
async def test_a_circular_cut_sweep(selected: list[Any]) -> None:
    model = _two_sketches()

    result = await _Harness(model).create_cut_sweep(
        SweepParameters(path="Sketch3", circular_profile_diameter=0.6)
    )

    args = model.FeatureManager.calls[0][1]
    assert (args[19], args[20]) == (True, pytest.approx(0.0006))
    assert result.is_success


@pytest.mark.asyncio
async def test_the_sketch_closed_last_is_the_profile(selected: list[Any]) -> None:
    model = _two_sketches()
    harness = _Harness(model)
    harness._last_sketch_name = "Sketch1"

    result = await harness.create_sweep(SweepParameters(path="Sketch3"))

    assert result.data.parameters["profile"] == "Sketch1"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (SweepParameters(path=""), "needs a 'path'"),
        (
            SweepParameters(path="Sketch3", circular_profile_diameter=0),
            "circular_profile_diameter must be greater than 0",
        ),
    ],
)
@pytest.mark.asyncio
async def test_sweep_inputs_checked_first(
    selected: list[Any], params: SweepParameters, message: str
) -> None:
    model = _two_sketches()

    result = await _Harness(model).create_sweep(params)

    assert message in (result.error or "")
    assert model.FeatureManager.calls == []


@pytest.mark.asyncio
async def test_a_sweep_needs_an_active_model() -> None:
    result = await _Harness(None).create_cut_sweep(SweepParameters(path="Sketch3"))

    assert result.error == "No active model"


@pytest.mark.parametrize(
    ("params", "tree", "message"),
    [
        (SweepParameters(path="Path9"), None, "no sketch or curve named 'Path9'"),
        (
            SweepParameters(path="Sketch3", profile="SKETCH3"),
            None,
            "The profile 'SKETCH3' is the path itself",
        ),
        (
            SweepParameters(path="Sketch3", profile="Sketch9"),
            None,
            "no sketch named 'Sketch9' for the profile",
        ),
        (
            SweepParameters(path="Sketch1"),
            [("ProfileFeature", "Sketch1")],
            "needs a profile sketch distinct from the path",
        ),
        (SweepParameters(path="Sketch1"), [], "Sketches: none"),
    ],
)
@pytest.mark.asyncio
async def test_an_unclear_profile_or_path_is_refused(
    selected: list[Any],
    params: SweepParameters,
    tree: list[tuple[str, str]] | None,
    message: str,
) -> None:
    model = _two_sketches()
    if tree is not None:
        model.tree = tree
    harness = _Harness(model)
    harness._last_sketch_name = "Sketch1"

    result = await harness.create_sweep(params)

    assert message in (result.error or "")
    assert model.FeatureManager.calls == []


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("Sketch2", "Failed to select sweep profile sketch: Sketch2"),
        ("Sketch3", "Failed to select sweep path: Sketch3"),
    ],
)
@pytest.mark.asyncio
async def test_an_unselectable_profile_or_path(
    selected: list[Any], monkeypatch: pytest.MonkeyPatch, missing: str, message: str
) -> None:
    monkeypatch.setattr(swept, "_select_named_feature", lambda a, n, m, p: n != missing)
    model = _two_sketches()

    result = await _Harness(model).create_sweep(
        SweepParameters(path="Sketch3", profile="Sketch2")
    )

    assert message in (result.error or "")


@pytest.mark.parametrize(
    ("params", "made_from"),
    [
        (SweepParameters(path="Sketch3", profile="Sketch2"), "from 'Sketch2'"),
        (
            SweepParameters(path="Sketch3", circular_profile_diameter=2),
            "from a 2 mm circle",
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_sweep_solidworks_refuses(
    selected: list[Any], params: SweepParameters, made_from: str
) -> None:
    model = _two_sketches()
    model.FeatureManager.builds = False

    result = await _Harness(model).create_sweep(params)

    assert "Failed to create sweep feature" in (result.error or "")
    assert made_from in (result.error or "")


@pytest.mark.asyncio
async def test_a_failed_volume_check_is_the_error(selected: list[Any]) -> None:
    harness = _Harness(_two_sketches())
    harness.measure_error = "create_cut_sweep should remove material but added 4 mm³"

    result = await harness.create_cut_sweep(SweepParameters(path="Sketch3"))

    assert result.error == harness.measure_error


def test_input_refused_is_what_a_bad_sketch_raises() -> None:
    harness = _Harness(_Model())

    with pytest.raises(InputRefused):
        harness._base_circle_diameter(_sketch(), "Sketch1")
