"""The real adapter's part features, against a fake COM layer.

Specs: tools/hole-wizard, tools/cosmetic-thread, tools/shell-draft-rib,
tools/sketch-convert-entities, tools/feature-patterns and
tools/measured-feature-change. The fake records each COM call so the
argument lists (taken from the type library) are checked too.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import part_features as pf
from solidworks_mcp.adapters.solidworks.part_features import (
    SolidWorksPartFeaturesMixin,
)
from solidworks_mcp.adapters.solidworks.rebuild_diagnostics import RawRebuildIssue


class FakeAdapter(SolidWorksPartFeaturesMixin):
    """Just enough of PyWin32Adapter for the part-feature methods."""

    def __init__(self, volumes: list[float | None], feature: Any = "made") -> None:
        made = SimpleNamespace(Name="Feature9") if feature == "made" else feature
        self.manager = MagicMock()
        for method in (
            "FeatureLinearPattern5",
            "InsertMultiFaceDraft",
            "HoleWizard5",
            "InsertCosmeticThread3",
        ):
            getattr(self.manager, method).return_value = made
        self.currentModel = MagicMock()
        self.currentModel.FeatureManager = self.manager
        self.currentModel.FeatureByPositionReverse.return_value = SimpleNamespace(
            Name="Shell1"
        )
        self.currentModel.Extension.SelectByID2.return_value = True
        self._volumes = iter(volumes)
        self.deleted: list[str] = []
        self.segments: list[Any] = []
        sketch = SimpleNamespace(GetSketchSegments=lambda: list(self.segments))
        self.currentSketchManager = MagicMock()
        self.currentSketchManager.ActiveSketch = sketch
        self._sketch_entities: dict[str, Any] = {}

    async def get_mass_properties(self) -> AdapterResult[Any]:
        volume = next(self._volumes)
        if volume is None:
            return AdapterResult(status=AdapterResultStatus.ERROR, error="no read")
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=SimpleNamespace(volume=volume)
        )

    async def delete_feature(self, name: str) -> None:
        self.deleted.append(name)

    def _attempt(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except Exception:
            return default

    def _get_attr_or_call(self, obj: Any, name: str) -> Any:
        return getattr(obj, name)

    def _handle_com_operation(self, name: str, fn: Any) -> AdapterResult[Any]:
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=fn())
        except Exception as error:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(error))


@pytest.fixture
def pick_rebuilds() -> list[bool]:
    """Whether each pick asked for a rebuild first (filled by ``picks``)."""
    return []


@pytest.fixture
def picks(
    monkeypatch: pytest.MonkeyPatch, pick_rebuilds: list[bool]
) -> list[tuple[Any, ...]]:
    """Fake the pick helpers; record every pick."""
    seen: list[tuple[Any, ...]] = []

    def select_by_coord(adapter, x, y, z, append, mark, entity_type, picker, rebuild):  # type: ignore[no-untyped-def]
        seen.append(
            (
                round(x * 1000, 6),
                round(y * 1000, 6),
                round(z * 1000, 6),
                append,
                mark,
                entity_type,
            )
        )
        pick_rebuilds.append(rebuild)
        return x != 0.999  # 999 mm: nothing there

    def select_named(adapter, name, mark, append):  # type: ignore[no-untyped-def]
        seen.append((name, mark, append))
        return not name.startswith("missing")

    monkeypatch.setattr(pf, "_select_edge_by_coord", select_by_coord)
    monkeypatch.setattr(pf, "_select_named_feature", select_named)
    monkeypatch.setattr(pf, "_BodyEntityPicker", lambda adapter: None)
    monkeypatch.setattr(pf.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(pf, "collect_rebuild_issues", lambda adapter, model: [])
    return seen


# --- the shared volume rule ------------------------------------------------


@pytest.mark.asyncio
async def test_no_model_is_refused() -> None:
    adapter = FakeAdapter([])
    adapter.currentModel = None

    result = await adapter.create_shell(2, [])

    assert result.error == "No active model"


@pytest.mark.asyncio
async def test_an_unchanged_volume_deletes_the_feature(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 1000.0])

    result = await adapter.create_hole([0, 0, 20], "simple", "iso", "M6")

    assert adapter.deleted == ["Feature9"]
    assert "made no change" in (result.error or "")
    assert "Feature9 was removed" in (result.error or "")


@pytest.mark.asyncio
async def test_an_unchanged_volume_without_a_name(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 1000.0])
    adapter.currentModel.FeatureByPositionReverse.return_value = None

    result = await adapter.create_shell(2, [[0, 0, 20]])

    assert adapter.deleted == []
    assert "the feature was removed" in (result.error or "")


@pytest.mark.asyncio
async def test_an_unreadable_volume_is_an_error(picks: list[Any]) -> None:
    result = await FakeAdapter([None, 900.0]).create_shell(2, [])

    assert "could not be read" in (result.error or "")


@pytest.mark.asyncio
async def test_a_failed_build_is_returned_as_is(picks: list[Any]) -> None:
    result = await FakeAdapter([1000.0]).create_rib("missing sketch", 2)

    assert result.error == "Couldn't select the sketch 'missing sketch' for the rib."


@pytest.mark.asyncio
async def test_a_volume_change_is_reported(picks: list[Any]) -> None:
    result = await FakeAdapter([1000.0, 800.0]).create_shell(2, [[0, 0, 20]], True)

    assert result.data["volume_change"] == -200.0
    assert result.data["name"] == "Shell1"
    assert result.data["outward"] is True


# --- each feature ----------------------------------------------------------


@pytest.mark.asyncio
async def test_pattern_linear_one_named_direction(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 3000.0])

    result = await adapter.pattern_linear(["Boss1"], "Axis1", 3, 10)

    args = adapter.manager.FeatureLinearPattern5.call_args.args
    assert len(args) == 22
    assert args[:8] == (3, 0.01, 1, 0.0, False, False, "Axis1", "")
    assert picks == [("Axis1", 1, False), ("Boss1", 4, True)]
    assert (result.data["count2"], result.data["spacing2_mm"]) == (None, None)


@pytest.mark.asyncio
async def test_pattern_linear_grid_by_points(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 6000.0])

    result = await adapter.pattern_linear(
        ["Boss1"], [0, -20, 20], 3, 10, [20, 0, 20], 2, 5, True, True
    )

    args = adapter.manager.FeatureLinearPattern5.call_args.args
    assert args[:8] == (3, 0.01, 2, 0.005, True, True, "", "")
    assert picks[:2] == [(0, -20, 20, False, 1, "EDGE"), (20, 0, 20, True, 2, "EDGE")]
    assert result.data["count2"] == 2


@pytest.mark.parametrize(
    ("features", "direction", "message"),
    [
        (["Boss1"], "missing axis", "Couldn't select the direction 'missing axis'."),
        (["missing boss"], "Axis1", "Couldn't select the feature 'missing boss'"),
        (["Boss1"], [999, 0, 0], "Couldn't select the edge at [999, 0, 0] mm"),
    ],
)
@pytest.mark.asyncio
async def test_pattern_linear_selection_failures(
    picks: list[Any], features: list[str], direction: Any, message: str
) -> None:
    result = await FakeAdapter([1000.0]).pattern_linear(features, direction, 3, 10)

    assert (result.error or "").startswith(message)


@pytest.mark.asyncio
async def test_pattern_linear_nothing_returned(picks: list[Any]) -> None:
    result = await FakeAdapter([1000.0], feature=None).pattern_linear(
        ["Boss1"], "Axis1", 3, 10
    )

    assert "FeatureLinearPattern5 returned nothing" in (result.error or "")


@pytest.mark.asyncio
async def test_shell_calls_insert_feature_shell(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 400.0])

    await adapter.create_shell(2.5, [[0, 0, 20], [0, 0, 0]])

    adapter.currentModel.InsertFeatureShell.assert_called_once_with(0.0025, False)
    assert [p[3:] for p in picks] == [(False, 0, "FACE"), (True, 0, "FACE")]


@pytest.mark.asyncio
async def test_draft_marks_the_neutral_face_and_the_faces(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 990.0])

    result = await adapter.add_draft(3, [[20, 0, 10]], [0, 0, 0], reverse=True)

    adapter.manager.InsertMultiFaceDraft.assert_called_once_with(
        math.radians(3), True, False, 0, False, False
    )
    assert [p[4] for p in picks] == [1, 2]
    assert result.data["faces_drafted"] == 1


@pytest.mark.asyncio
async def test_draft_nothing_returned(picks: list[Any]) -> None:
    result = await FakeAdapter([1000.0], feature=None).add_draft(
        3, [[1, 0, 0]], [0, 0, 0]
    )

    assert "InsertMultiFaceDraft returned nothing" in (result.error or "")


@pytest.mark.asyncio
async def test_rib_calls_insert_rib(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 1080.0])

    result = await adapter.create_rib("Sketch3", 2, False, True, True)

    adapter.manager.InsertRib.assert_called_once_with(
        False, False, 0.002, 0, True, False, False, 0.0, True, False
    )
    assert result.data["sketch"] == "Sketch3"


@pytest.mark.asyncio
async def test_hole_wizard_arguments(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 900.0])

    result = await adapter.create_hole(
        [10, 0, 20], "counterbore", "iso", "M6", "blind", 8
    )

    args = adapter.manager.HoleWizard5.call_args.args
    assert len(args) == 27
    assert args[:8] == (
        0,
        8,
        139,  # Cap (4762), from the sample library
        "M6",
        0,
        -1.0,
        0.008,
        -1.0,
    )
    assert args[8:20] == (-1.0,) * 12
    assert args[20:] == ("", False, True, True, True, True, False)
    select = adapter.currentModel.Extension.SelectByID2.call_args.args
    assert select[:7] == ("", "FACE", 0.01, 0.0, 0.02, False, 0)
    assert result.data["at_mm"] == [10, 0, 20]


@pytest.mark.asyncio
async def test_hole_through_all_leaves_the_depth_to_the_table(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 900.0])

    await adapter.create_hole([0, 0, 20], "tapped", "ansi_inch", "1/4-20")

    args = adapter.manager.HoleWizard5.call_args.args
    assert args[:7] == (4, 0, 27, "1/4-20", 1, -1.0, -1.0)


@pytest.mark.asyncio
async def test_hole_with_no_face_or_no_feature(picks: list[Any]) -> None:
    no_face = FakeAdapter([1000.0])
    no_face.currentModel.Extension.SelectByID2.return_value = False
    no_hole = FakeAdapter([1000.0], feature=None)

    missed = await no_face.create_hole([0, 0, 20], "simple", "iso", "M6")
    refused = await no_hole.create_hole([0, 0, 20], "counterbore", "iso", "M8")

    assert missed.error == "No face at [0, 0, 20] mm to put the hole on."
    assert 'HoleWizard5 made no hole (counterbore, iso, "Cap (4762)" M8)' in (
        refused.error or ""
    )


@pytest.mark.asyncio
async def test_cosmetic_thread_keeps_the_volume(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 1000.0])

    result = await adapter.add_cosmetic_thread([5, 0, 20], "M10x1.5", 10, "blind", 15)

    adapter.manager.InsertCosmeticThread3.assert_called_once_with(
        8, "Machine Threads", "M10x1.5", 0.01, 0, 0.015, "M10x1.5"
    )
    assert result.data["volume_change"] == 0.0
    assert picks[0][3:] == (False, 0, "EDGE")


@pytest.mark.asyncio
async def test_cosmetic_thread_through_and_failures(picks: list[Any]) -> None:
    through = FakeAdapter([1000.0, 1000.0])
    changed = FakeAdapter([1000.0, 990.0])
    nothing = FakeAdapter([1000.0], feature=None)

    await through.add_cosmetic_thread(
        [5, 0, 20], "1/4-20", 6.35, "through", None, "ansi_inch"
    )
    moved = await changed.add_cosmetic_thread([5, 0, 20], "M6", 6, depth=5)
    failed = await nothing.add_cosmetic_thread([5, 0, 20], "M6", 6, depth=5)

    assert through.manager.InsertCosmeticThread3.call_args.args[4:6] == (2, 0.0)
    assert "a cosmetic thread must not" in (moved.error or "")
    assert "InsertCosmeticThread3 made no thread" in (failed.error or "")


@pytest.mark.asyncio
async def test_convert_entities_registers_the_new_segments(
    picks: list[Any], pick_rebuilds: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copies get ids; the picks skip the rebuild, which would close the
    sketch, and the sketch is flagged so its segments can be read (both seen
    live)."""
    flagged_as: list[str] = []

    def flagged(obj: Any, *interfaces: str) -> Any:
        flagged_as.extend(interfaces)
        return obj

    monkeypatch.setattr(pf.sw_type_info, "flagged", flagged)
    adapter = FakeAdapter([])
    adapter.segments = [SimpleNamespace(ConstructionGeometry=False)]
    new = [SimpleNamespace(ConstructionGeometry=False) for _ in range(4)]

    def use_edge(chain: bool, inner: bool) -> bool:
        adapter.segments.extend(new)
        return True

    adapter.currentSketchManager.SketchUseEdge3.side_effect = use_edge

    result = await adapter.sketch_convert_entities([[20, 0, 20]], [0, 0, 20], True)

    assert result.data["entities"] == [f"Converted_{n}" for n in range(1, 5)]
    assert all(segment.ConstructionGeometry for segment in new)
    assert adapter._sketch_entities["Converted_1"] is new[0]
    assert [p[5] for p in picks] == ["EDGE", "FACE"]
    assert pick_rebuilds == [False, False]
    assert "ISketch" in flagged_as


@pytest.mark.asyncio
async def test_convert_entities_failures(picks: list[Any]) -> None:
    no_sketch = FakeAdapter([])
    no_sketch.currentSketchManager = None
    refused = FakeAdapter([])
    refused.currentSketchManager.SketchUseEdge3.return_value = False

    missing = await no_sketch.sketch_convert_entities(face_point=[0, 0, 20])
    copied_nothing = await refused.sketch_convert_entities([[1, 0, 0]])

    assert missing.error == "No active sketch"
    assert "SketchUseEdge3 copied nothing" in (copied_nothing.error or "")


# --- rebuild warnings and errors on the new feature -------------------------


def _issues(monkeypatch: pytest.MonkeyPatch, *issues: RawRebuildIssue) -> None:
    monkeypatch.setattr(
        pf, "collect_rebuild_issues", lambda adapter, model: list(issues)
    )


@pytest.mark.asyncio
async def test_a_rebuild_warning_on_the_new_feature_is_passed_on(
    picks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _issues(
        monkeypatch,
        RawRebuildIssue("Feature9", "HoleWzd", 1, True),
        RawRebuildIssue("Other", "Fillet", 1, True),
    )

    result = await FakeAdapter([1000.0, 900.0]).create_hole(
        [0, 0, 20], "tapped", "iso", "M6x1.0"
    )

    assert result.is_success
    (warning,) = result.data["rebuild_warnings"]
    assert (warning["feature"], warning["severity"]) == ("Feature9", "warning")


@pytest.mark.asyncio
async def test_a_rebuild_error_on_the_new_feature_removes_it(
    picks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _issues(monkeypatch, RawRebuildIssue("Feature9", "HoleWzd", 1, False))
    adapter = FakeAdapter([1000.0, 900.0])

    result = await adapter.create_hole([0, 0, 20], "simple", "iso", "M6")

    assert adapter.deleted == ["Feature9"]
    assert (result.error or "").startswith("create_hole: SolidWorks reports")
    assert "on Feature9" in (result.error or "")


@pytest.mark.asyncio
async def test_a_failed_rebuild_read_reports_nothing(
    picks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(adapter: Any, model: Any) -> list[Any]:
        raise RuntimeError("GetWhatsWrong failed")

    monkeypatch.setattr(pf, "collect_rebuild_issues", broken)

    result = await FakeAdapter([1000.0, 900.0]).create_hole(
        [0, 0, 20], "simple", "iso", "M6"
    )

    assert result.is_success
    assert "rebuild_warnings" not in result.data


@pytest.mark.asyncio
async def test_no_name_means_no_rebuild_read(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 800.0])
    adapter.currentModel.FeatureByPositionReverse.return_value = None

    assert adapter._rebuild_issues("create_shell", None) == []


# --- a blind tapped hole's thread depth ---------------------------------------


class _HoleDefinition:
    """``IWizardHoleFeatureData2`` with a thread depth (metres)."""

    def __init__(self, thread: float) -> None:
        self.ThreadDepth = thread
        self.accessed = False
        self.released = False

    def AccessSelections(self, model: Any, component: Any) -> bool:
        self.accessed = True
        return True

    def ReleaseSelectionAccess(self) -> None:
        self.released = True


class _Hole:
    """A hole feature whose definition can be read and saved."""

    def __init__(self, definition: Any, saves: bool = True) -> None:
        self.Name = "M6 Tapped Hole1"
        self.definition = definition
        self.saves = saves
        self.saved: Any = None

    def GetDefinition(self) -> Any:
        return self.definition

    def ModifyDefinition(self, data: Any, model: Any, component: Any) -> bool:
        self.saved = data
        return self.saves


async def _tapped(hole: _Hole, depth: float | None = 8) -> Any:
    adapter = FakeAdapter([1000.0, 900.0], feature=hole)
    return await adapter.create_hole(
        [0, 0, 20], "tapped", "iso", "M6x1.0", "blind", depth
    )


@pytest.mark.parametrize("thread", [0.012, 0.008])
@pytest.mark.asyncio
async def test_a_deep_thread_stops_short_of_the_hole_bottom(
    picks: list[Any], thread: float
) -> None:
    """Deeper than the hole, or exactly as deep (a zero-length sketch line,
    seen live): capped at 80% of the 8 mm hole."""
    definition = _HoleDefinition(thread)
    hole = _Hole(definition)

    result = await _tapped(hole)

    assert definition.ThreadDepth == pytest.approx(0.0064)
    assert definition.accessed and hole.saved is definition
    assert result.data["thread_depth_mm"] == pytest.approx(6.4)


@pytest.mark.asyncio
async def test_a_shallow_thread_is_left_alone(picks: list[Any]) -> None:
    hole = _Hole(_HoleDefinition(0.006))

    result = await _tapped(hole)

    assert hole.saved is None
    assert result.data["thread_depth_mm"] == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_a_refused_save_keeps_the_table_depth(picks: list[Any]) -> None:
    definition = _HoleDefinition(0.012)

    result = await _tapped(_Hole(definition, saves=False))

    assert definition.released
    assert result.data["thread_depth_mm"] == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_an_unreadable_definition_reports_no_thread_depth(
    picks: list[Any],
) -> None:
    result = await _tapped(_Hole(None))

    assert result.data["thread_depth_mm"] is None


@pytest.mark.asyncio
async def test_a_tapped_hole_without_depth_is_not_capped(picks: list[Any]) -> None:
    hole = _Hole(_HoleDefinition(0.012))

    result = await _tapped(hole, depth=None)

    assert hole.saved is None
    assert result.data["thread_depth_mm"] is None


# --- a simple hole through all, and several holes in one feature ------------


@pytest.mark.asyncio
async def test_a_simple_hole_through_all_falls_back_to_blind(picks: list[Any]) -> None:
    """SolidWorks makes no simple hole through all (seen live); it is retried
    blind, as deep as the part box's diagonal + 1 mm."""
    adapter = FakeAdapter([1000.0, 900.0])
    made = SimpleNamespace(Name="Hole1")
    adapter.manager.HoleWizard5.side_effect = [None, made]
    adapter.currentModel.GetPartBox.return_value = (0, 0, 0, 0.03, 0.04, 0)

    result = await adapter.create_hole([0, 20, 0], "simple", "iso", "Ø6.0")

    first, second = (c.args for c in adapter.manager.HoleWizard5.call_args_list)
    assert (first[4], first[6]) == (1, -1.0)
    assert second[4] == 0 and second[6] == pytest.approx(0.051)
    assert result.data["end_condition"] == "through_all"
    assert result.data["end_condition_used"] == "blind"
    assert result.data["depth_mm"] == pytest.approx(51.0)
    assert "blind, 51.0 mm deep" in result.data["warnings"][0]


@pytest.mark.asyncio
async def test_an_unreadable_part_box_gives_a_metre(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 900.0])
    adapter.manager.HoleWizard5.side_effect = [None, SimpleNamespace(Name="Hole1")]
    adapter.currentModel.GetPartBox.return_value = None

    result = await adapter.create_hole([0, 20, 0], "simple", "iso", "Ø6.0")

    assert result.data["depth_mm"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_only_a_simple_hole_falls_back(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0], feature=None)

    result = await adapter.create_hole([0, 20, 0], "tapped", "iso", "M6x1.0")

    assert adapter.manager.HoleWizard5.call_count == 1
    assert "HoleWizard5 made no hole" in (result.error or "")


class _PositionSketch:
    """An ``ISketch`` whose points grow as the sketch manager adds them."""

    def __init__(self, points: list[list[float]]) -> None:
        self.points = [SimpleNamespace(X=x, Y=y, Z=z) for x, y, z in points]

    def GetSketchPoints2(self) -> list[Any]:
        return list(self.points)


def _hole_with_sketch(sketch: Any, kinds: tuple[str, ...] = ("ProfileFeature",)) -> Any:
    """A hole feature whose sub-features are ``kinds``; the last holds ``sketch``."""
    subs = [
        SimpleNamespace(
            GetTypeName2=lambda k=kind: k,
            GetSpecificFeature2=lambda: sketch,
            Select2=MagicMock(),
        )
        for kind in kinds
    ]
    for sub, nxt in zip(subs, [*subs[1:], None], strict=True):
        sub.GetNextSubFeature = lambda n=nxt: n
    return SimpleNamespace(Name="Hole1", GetFirstSubFeature=lambda: subs[0])


@pytest.fixture
def sketch_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sketch space is model space shifted: z - 0.02 m (the face at z = 20 mm)."""
    monkeypatch.setattr(
        pf, "_to_sketch", lambda adapter, sketch, p: [p[0], p[1], p[2] - 0.02]
    )


def _adding(adapter: FakeAdapter, sketch: _PositionSketch, keep: bool = True) -> None:
    def create_point(x: float, y: float, z: float) -> None:
        if keep:
            sketch.points.append(SimpleNamespace(X=x, Y=y, Z=z))

    adapter.currentModel.SketchManager.CreatePoint.side_effect = create_point


@pytest.mark.asyncio
async def test_positions_go_into_the_hole_sketch(
    picks: list[Any], sketch_space: None
) -> None:
    """Each position is a point of the hole's position sketch: one feature,
    three holes (the Hole Wizard's Positions tab, done through the API)."""
    sketch = _PositionSketch([[0.0, 0.0, 0.0]])
    hole = _hole_with_sketch(sketch, ("HoleWzdProfile", "ProfileFeature"))
    adapter = FakeAdapter([1000.0, 700.0], feature=hole)
    _adding(adapter, sketch)

    result = await adapter.create_hole(
        [0, 0, 20], "counterbore", "iso", "M6", positions=[[10, 0, 20], [0, 10, 20]]
    )

    assert result.data["hole_count"] == 3
    assert result.data["positions_mm"] == [[10, 0, 20], [0, 10, 20]]
    manager = adapter.currentModel.SketchManager
    assert [c.args for c in manager.CreatePoint.call_args_list] == [
        (0.01, 0.0, 0.0),
        (0.0, 0.01, 0.0),
    ]
    assert manager.AddToDB is False
    manager.InsertSketch.assert_called_once_with(True)
    adapter.currentModel.EditSketch.assert_called_once()
    assert adapter.deleted == []


@pytest.mark.parametrize(
    ("positions", "sketch_points", "keep", "message"),
    [
        ([[10, 0, 25]], [[0.0, 0.0, 0.0]], True, "is 5.000 mm off the face"),
        ([[10, 0, 20]], [[0.05, 0.0, 0.0]], True, "position sketch couldn't be found"),
        ([[10, 0, 20]], [[0.0, 0.0, 0.0]], False, "has 1 points after adding 1"),
    ],
)
@pytest.mark.asyncio
async def test_a_failed_position_removes_the_hole(
    picks: list[Any],
    sketch_space: None,
    positions: list[list[float]],
    sketch_points: list[list[float]],
    keep: bool,
    message: str,
) -> None:
    sketch = _PositionSketch(sketch_points)
    adapter = FakeAdapter([1000.0], feature=_hole_with_sketch(sketch))
    _adding(adapter, sketch, keep)

    result = await adapter.create_hole(
        [0, 0, 20], "simple", "iso", "Ø6.0", "blind", 5, positions
    )

    assert message in (result.error or "")
    assert (result.error or "").endswith("The hole Hole1 was removed again.")
    assert adapter.deleted == ["Hole1"]


def test_a_model_point_in_sketch_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """The point goes through the math utility and the sketch's transform."""
    monkeypatch.setattr(pf.sw_type_info, "flagged", lambda obj, *_: obj)
    monkeypatch.setattr(pf, "double_array", lambda values: tuple(values))
    transform = object()
    moved = SimpleNamespace(ArrayData=(0.1, 0.2, 0.0))
    point = MagicMock()
    point.MultiplyTransform.return_value = moved
    utility = MagicMock()
    utility.CreatePoint.return_value = point
    adapter = SimpleNamespace(swApp=SimpleNamespace(GetMathUtility=lambda: utility))

    at = pf._to_sketch(
        adapter, SimpleNamespace(ModelToSketchTransform=transform), [1.0, 2.0, 3.0]
    )

    assert at == [0.1, 0.2, 0.0]
    utility.CreatePoint.assert_called_once_with((1.0, 2.0, 3.0))
    point.MultiplyTransform.assert_called_once_with(transform)


# ---- the Hole Wizard library (queue item 22) ---------------------------------------


@pytest.mark.asyncio
async def test_a_size_the_library_lacks_makes_no_com_call(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 900.0])

    result = await adapter.create_hole([0, 0, 20], "simple", "iso", "M7")

    assert result.error == (
        '"Screw Clearances" (iso) has no size "M7"; nearest: M4, M5, M6, M8, M10.'
    )
    adapter.manager.HoleWizard5.assert_not_called()
    adapter.currentModel.ClearSelection2.assert_not_called()


@pytest.mark.asyncio
async def test_a_named_fastener_and_a_bare_diameter(picks: list[Any]) -> None:
    adapter = FakeAdapter([1000.0, 900.0])

    result = await adapter.create_hole(
        [0, 0, 20], "simple", "iso", "6", "blind", 5, fastener="drill sizes"
    )

    args = adapter.manager.HoleWizard5.call_args.args
    assert args[2:4] == (143, "Ø6.0")
    assert (result.data["fastener"], result.data["size"]) == ("Drill sizes", "Ø6.0")
    assert "warnings" not in result.data


@pytest.mark.asyncio
async def test_an_unreadable_library_tries_the_default_with_a_warning(
    picks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing() -> Any:
        raise pf.HoleLibraryError("No Hole Wizard library found.")

    monkeypatch.setattr(pf, "find_library", missing)
    adapter = FakeAdapter([1000.0, 900.0])

    made = await adapter.create_hole([0, 0, 20], "counterbore", "din", "M6")
    refused = await adapter.create_hole(
        [0, 0, 20], "counterbore", "din", "M6", fastener="Pan (7045)"
    )

    assert adapter.manager.HoleWizard5.call_args.args[1:4] == (4, 67, "M6")
    assert made.data["warnings"] == [
        "The size wasn't checked: No Hole Wizard library found. The hole was "
        'attempted as "Cap (912)" M6.'
    ]
    assert "Leave `fastener` out" in (refused.error or "")


@pytest.mark.asyncio
async def test_list_hole_sizes_reads_the_library() -> None:
    adapter = FakeAdapter([])

    listed = await adapter.list_hole_sizes("iso", "countersink")
    one = await adapter.list_hole_sizes("iso", "counterbore", size="M6")
    unknown = await adapter.list_hole_sizes("iso", "tapped", size="M7")

    assert listed.data["hole_types"] == [
        {"name": "CTSK Flat (7046-1)", "sizes": ["M3", "M4", "M5", "M6", "M8", "M10"]}
    ]
    assert one.data["dimensions"] == {
        "size": "M6",
        "diameter": 6.0,
        "cbore_dia": 11.0,
        "cbore_depth": 6.4,
    }
    assert unknown.status == AdapterResultStatus.ERROR
    assert "nearest: M4, M5, M6, M8, M8x1.0" in (unknown.error or "")


@pytest.mark.asyncio
async def test_list_hole_sizes_without_a_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing() -> Any:
        raise pf.HoleLibraryError("Looked in: C:\nowhere.")

    monkeypatch.setattr(pf, "find_library", missing)

    result = await FakeAdapter([]).list_hole_sizes("iso", "simple")

    assert result.error == "Looked in: C:\nowhere."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("summary", "before"), [(None, 0.0), (0.0, 0.0), (500.0, 500.0)]
)
async def test_a_first_feature_reads_the_volume_before_from_the_summary(
    summary: float | None, before: float, picks: list[tuple[Any, ...]]
) -> None:
    """A base flange's part has no body: the summary reads 0, mass properties fail."""
    adapter = FakeAdapter([12000.0])

    async def geometry_summary() -> AdapterResult[Any]:
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"volume_mm3": summary}
        )

    adapter.get_model_geometry_summary = geometry_summary  # type: ignore[attr-defined]

    result = await adapter._measured(
        "create_base_flange", lambda: {"name": "Base-Flange1"}, first_feature=True
    )

    assert result.data["volume_before"] == before
    assert result.data["volume_after"] == 12000.0
