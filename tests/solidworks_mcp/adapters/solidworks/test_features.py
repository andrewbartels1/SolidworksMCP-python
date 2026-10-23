"""Direct branch coverage tests for solidworks_mcp.adapters.solidworks.features."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
)
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks import features
from solidworks_mcp.adapters.solidworks.features import (
    _create_axis_impl,
    _create_reference_plane_impl,
    _delete_feature_impl,
    _feature_count,
    _is_suppressed,
    _mirror_feature_impl,
    _pattern_circular_impl,
    _rename_feature_impl,
    _select_reference_entity,
    _suppress_feature_impl,
    _undo_impl,
)


class _FakeFeatureAdapter:
    def __init__(self) -> None:
        self.currentModel = None
        self.constants = {
            "swEndCondBlind": 1,
            "swEndCondThroughAll": 2,
            "swStartSketchPlane": 0,
        }
        self._last_sketch_name = None
        self._sketch_count = 2

    def _handle_com_operation(self, _name, callback):
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=callback())
        except Exception as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))

    def _attempt(self, callback, default=None):
        try:
            return callback()
        except Exception:
            return default

    def _attempt_with_error(self, callback):
        try:
            return callback(), None
        except Exception as exc:
            return None, str(exc)

    def _get_feature_id(self, feature):
        return getattr(feature, "Name", "feature-id")


def _fake_sketch_feature(name: str) -> SimpleNamespace:
    """A single-node fake feature tree containing one ProfileFeature (sketch).

    Used so ``_profile_feature_names`` (the ground-truth tree walk
    create_cut_extrude now requires before it will target a sketch) finds a
    real match for ``adapter._last_sketch_name`` in these unit tests.
    """
    return SimpleNamespace(
        GetTypeName2=lambda: "ProfileFeature",
        Name=name,
        GetNextFeature=lambda: None,
    )


def test_create_cut_extrude_requires_model() -> None:
    adapter = _FakeFeatureAdapter()
    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=5.0))
    assert result.status == AdapterResultStatus.ERROR
    assert result.error == "No active model"


def test_create_cut_extrude_collects_all_fallback_errors() -> None:
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: (_ for _ in ()).throw(RuntimeError("cut4 failed")),
        FeatureCut3=lambda *args: (_ for _ in ()).throw(RuntimeError("cut3 failed")),
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(depth=4.0, end_condition="ThroughAll", draft_angle=1.0),
    )

    assert result.status == AdapterResultStatus.ERROR
    assert "Sketch2" in (result.error or "")
    assert "FeatureCut4: cut4 failed" in (result.error or "")
    assert "FeatureCut3: cut3 failed" in (result.error or "")


def test_create_cut_extrude_fails_clearly_when_sketch_selection_rejected() -> None:
    """SelectByID2 rejecting the resolved sketch must fail fast, by name.

    No FeatureCut variant should even be attempted — cutting with whatever
    happens to still be selected would risk operating on the wrong profile.
    """
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureCut4=Mock(side_effect=AssertionError("should not be called")),
        FeatureCut3=Mock(side_effect=AssertionError("should not be called")),
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: False),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=4.0))

    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to select sketch 'Sketch2'" in (result.error or "")
    feature_manager.FeatureCut4.assert_not_called()
    feature_manager.FeatureCut3.assert_not_called()


def test_create_cut_extrude_never_passes_bare_none_as_callout() -> None:
    """SelectByID2's Callout arg must never be plain None.

    Plain None marshals as VT_NULL, which real SolidWorks rejects with
    DISP_E_TYPEMISMATCH (runbook item 11) — silently swallowed by _attempt
    into an unhelpful "selection failed" guess unless the call site passes
    the VT_DISPATCH null helper instead.
    """
    adapter = _FakeFeatureAdapter()

    select_calls: list[tuple] = []

    def _select_by_id2(*args, **kwargs):
        select_calls.append(args)
        return True

    feature = SimpleNamespace(Name="Cut-Extrude1")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureCut4=lambda *args: feature, FeatureCut3=lambda *args: None
        ),
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=_select_by_id2),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=4.0))

    assert result.is_success
    assert select_calls, "expected at least one SelectByID2 call"
    for call_args in select_calls:
        callout = call_args[7]
        assert callout is not None, (
            "SelectByID2's Callout arg was bare None — SolidWorks rejects "
            "this with DISP_E_TYPEMISMATCH"
        )


def test_create_cut_extrude_surfaces_real_selection_com_error() -> None:
    """A COM error during sketch selection must appear in the failure message.

    Previously this was swallowed by ``_attempt`` into a generic "may
    already be consumed..." guess, hiding the actual cause.
    """
    adapter = _FakeFeatureAdapter()

    def _select_by_id2(*_args, **_kwargs):
        raise RuntimeError("(-2147352571, 'Type mismatch.', None, 8)")

    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureCut4=Mock(side_effect=AssertionError("should not be called")),
            FeatureCut3=Mock(side_effect=AssertionError("should not be called")),
        ),
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=_select_by_id2),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=4.0))

    assert result.status == AdapterResultStatus.ERROR
    assert "Type mismatch" in (result.error or "")


def test_create_cut_extrude_explicit_sketch_name_not_found_fails_fast() -> None:
    """An explicit sketch_name that doesn't exist must fail with the real list."""
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureCut4=Mock(side_effect=AssertionError("should not be called")),
        FeatureCut3=Mock(side_effect=AssertionError("should not be called")),
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )

    result = features._create_cut_extrude_impl(
        adapter, ExtrusionParameters(depth=4.0, sketch_name="Sketch99")
    )

    assert result.status == AdapterResultStatus.ERROR
    assert "Sketch 'Sketch99' not found" in (result.error or "")
    assert "Sketch2" in (result.error or "")
    feature_manager.FeatureCut4.assert_not_called()
    feature_manager.FeatureCut3.assert_not_called()


def test_create_cut_extrude_explicit_sketch_name_overrides_last_tracked() -> None:
    """sketch_name wins even when it differs from _last_sketch_name."""
    adapter = _FakeFeatureAdapter()

    feature = SimpleNamespace(Name="Cut-Extrude2")
    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: feature,
        FeatureCut3=lambda *args: None,
    )
    selected: list[str] = []
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch7"),
        Extension=SimpleNamespace(
            SelectByID2=lambda name, *_args, **_kwargs: selected.append(name) or True
        ),
    )
    adapter._last_sketch_name = "Sketch2"  # stale/unrelated tracked value

    result = features._create_cut_extrude_impl(
        adapter, ExtrusionParameters(depth=4.0, sketch_name="Sketch7")
    )

    assert result.is_success
    assert result.data.parameters["sketch_name"] == "Sketch7"
    assert selected == ["Sketch7"]


def test_create_cut_extrude_uses_modern_fallback_when_cut4_returns_none() -> None:
    adapter = _FakeFeatureAdapter()

    feature = SimpleNamespace(Name="Cut-Extrude9")

    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: None,
        FeatureCut3=lambda *args: feature,
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch2"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=6.0))
    assert result.is_success
    assert result.data.type == "Cut-Extrude"
    assert result.data.name == "Cut-Extrude9"
    assert result.data.parameters["sketch_name"] == "Sketch2"


def test_add_fillet_and_chamfer_selection_and_feature_failures() -> None:
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureFillet3=lambda *args: None,
        FeatureChamfer=lambda *args: None,
    )
    extension = SimpleNamespace(SelectByID2=lambda edge, *_args: edge != "Edge<bad>")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager, Extension=extension
    )

    fillet_select_error = features._add_fillet_impl(adapter, 2.0, ["Edge<bad>"])
    assert fillet_select_error.status == AdapterResultStatus.ERROR
    assert "Failed to select edge" in (fillet_select_error.error or "")

    fillet_feature_error = features._add_fillet_impl(adapter, 2.0, ["Edge<1>"])
    assert fillet_feature_error.status == AdapterResultStatus.ERROR
    assert "Failed to create fillet" in (fillet_feature_error.error or "")

    chamfer_select_error = features._add_chamfer_impl(adapter, 1.0, ["Edge<bad>"])
    assert chamfer_select_error.status == AdapterResultStatus.ERROR
    assert "Failed to select edge" in (chamfer_select_error.error or "")

    chamfer_feature_error = features._add_chamfer_impl(adapter, 1.0, ["Edge<2>"])
    assert chamfer_feature_error.status == AdapterResultStatus.ERROR
    assert "Failed to create chamfer" in (chamfer_feature_error.error or "")


def test_create_cut_extrude_through_all_both_directions() -> None:
    """Through-all + both directions should use the combined end condition."""
    # Exercise the branch that uses swEndCondThroughAllBoth.
    adapter = _FakeFeatureAdapter()

    feature = SimpleNamespace(Name="Cut-Extrude1")
    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: feature,
        FeatureCut3=lambda *args: None,
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch1"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(
            depth=5.0, end_condition="ThroughAll", both_directions=True
        ),
    )
    assert result.is_success
    assert result.data.type == "Cut-Extrude"


def test_create_cut_extrude_raises_when_no_feature_and_no_errors() -> None:
    """Missing cut feature should give a diagnostic error when no fallback errors exist."""
    # Force all cut methods to return None without errors to hit the final raise.
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: None,
        FeatureCut3=lambda *args: None,
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=_fake_sketch_feature("Sketch1"),
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(depth=4.0),
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Sketch1" in (result.error or "")
    assert "without raising an error, but returned no feature" in (result.error or "")


# ---------------------------------------------------------------------------
# Fillet: SW 2025+ (major >= 33) code paths
# ---------------------------------------------------------------------------


class _FilletAdapterSW2026(_FakeFeatureAdapter):
    """Fake adapter that simulates SW 2026 (major=34) for fillet tests."""

    def _get_attr_or_call(self, obj, name, default=None):
        if obj is None:
            return default
        candidate = getattr(obj, name, None)
        if candidate is None:
            return default
        if callable(candidate):
            try:
                return candidate()
            except Exception:
                return default
        return candidate


def _make_sw2026_adapter(fillet3_return=1, last_feature=None):
    """Return a fake adapter reporting SW 2026 (major=34)."""
    adapter = _FilletAdapterSW2026()
    adapter.swApp = SimpleNamespace(RevisionNumber="34.0.0")

    feature_manager = SimpleNamespace(
        FeatureFillet3=lambda *args: None,  # old path — not used for major >= 33
        GetLastModifiedFeature=lambda: last_feature,
    )
    extension = SimpleNamespace(SelectByID2=lambda edge, *_args: edge != "Edge<bad>")

    # IModelDoc2.FeatureFillet3 on the model directly (SW 2025+ path)
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        Extension=extension,
        FeatureFillet3=lambda *args: fillet3_return,
    )
    return adapter


def test_add_fillet_sw2026_success_returns_default_name() -> None:
    """SW 2026 path: FeatureFillet3 returns non-zero; name defaults to 'Fillet'
    because IModelDoc2.FeatureFillet3 returns an int, not an IFeature."""
    adapter = _make_sw2026_adapter(fillet3_return=1)

    result = features._add_fillet_impl(adapter, 3.0, ["Edge<1>"])

    assert result.is_success
    assert result.data.type == "Fillet"
    assert result.data.name == "Fillet"


def test_add_fillet_sw2026_success_last_feature_none_uses_default_name() -> None:
    """SW 2026 path: GetLastModifiedFeature returns None — fall back to 'Fillet'."""
    adapter = _make_sw2026_adapter(fillet3_return=1, last_feature=None)

    result = features._add_fillet_impl(adapter, 2.0, ["Edge<1>"])

    assert result.is_success
    assert result.data.name == "Fillet"
    assert result.data.id == ""


def test_add_fillet_sw2026_failure_returns_zero() -> None:
    """SW 2026 path: FeatureFillet3 returns 0 — should raise and return error."""
    adapter = _make_sw2026_adapter(fillet3_return=0)

    result = features._add_fillet_impl(adapter, 2.0, ["Edge<1>"])

    assert result.status == AdapterResultStatus.ERROR
    assert "FeatureFillet3 returned 0" in (result.error or "")


def test_add_fillet_sw2026_edge_selection_failure() -> None:
    """SW 2026 path: edge selection failure is reported before fillet call."""
    adapter = _make_sw2026_adapter(fillet3_return=1)

    result = features._add_fillet_impl(adapter, 2.0, ["Edge<bad>"])

    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to select edge" in (result.error or "")


def test_add_fillet_empty_edge_names_does_not_touch_selection() -> None:
    """edge_names=[] must skip ClearSelection2/SelectByID2 entirely and go
    straight to FeatureFillet3 on whatever is already selected in the live
    UI -- see com-api-pitfalls.md #22. Regression test for the bug where an
    unconditional ClearSelection2 wiped out a hand-picked multi-edge
    selection before the fillet call ever ran."""
    adapter = _make_sw2026_adapter(fillet3_return=1)
    clear_selection = Mock(return_value=True)
    select_by_id2 = Mock(return_value=True)
    adapter.currentModel.ClearSelection2 = clear_selection
    adapter.currentModel.Extension.SelectByID2 = select_by_id2

    result = features._add_fillet_impl(adapter, 1.0, [])

    assert result.is_success
    clear_selection.assert_not_called()
    select_by_id2.assert_not_called()


def test_add_chamfer_empty_edge_names_does_not_touch_selection() -> None:
    """Same guarantee as above, for add_chamfer."""
    adapter = _FakeFeatureAdapter()
    clear_selection = Mock(return_value=True)
    select_by_id2 = Mock(return_value=True)
    feature = SimpleNamespace(Name="Chamfer1")
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=clear_selection,
        Extension=SimpleNamespace(SelectByID2=select_by_id2),
        FeatureManager=SimpleNamespace(
            InsertFeatureChamfer=lambda *args: feature,
        ),
    )

    result = features._add_chamfer_impl(adapter, 1.0, [])

    assert result.is_success
    clear_selection.assert_not_called()
    select_by_id2.assert_not_called()


def test_add_fillet_sw33_also_uses_new_path() -> None:
    """major=33 (SW 2025) hits the >= 33 branch; name defaults to 'Fillet'
    because IModelDoc2.FeatureFillet3 returns int, not IFeature."""
    adapter = _FilletAdapterSW2026()
    adapter.swApp = SimpleNamespace(RevisionNumber="33.2.1")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureFillet3=lambda *args: None,
        ),
        Extension=SimpleNamespace(SelectByID2=lambda *_args: True),
        FeatureFillet3=lambda *args: 1,
    )

    result = features._add_fillet_impl(adapter, 1.5, ["Edge<1>"])

    assert result.is_success
    assert result.data.name == "Fillet"


# ---------------------------------------------------------------------------
# _offset_plane_distance — issue #84: InsertRefPlane's Distance constraint
# takes a positive magnitude only; a negative offset must flip the
# OptionFlip bit instead of going negative, or SolidWorks silently
# collapses the plane onto its base (clamped to 0).
# ---------------------------------------------------------------------------


def test_offset_plane_distance_positive_offset_no_flip() -> None:
    distance_m, flip_bits = features._offset_plane_distance(76.2, base_flip=False)
    assert distance_m == pytest.approx(0.0762)
    assert flip_bits == 0


def test_offset_plane_distance_negative_offset_toggles_flip() -> None:
    distance_m, flip_bits = features._offset_plane_distance(-76.2, base_flip=False)
    assert distance_m == pytest.approx(0.0762)
    assert flip_bits == features._REF_PLANE_OPTION_FLIP


def test_offset_plane_distance_negative_offset_and_flip_cancel() -> None:
    distance_m, flip_bits = features._offset_plane_distance(-76.2, base_flip=True)
    assert distance_m == pytest.approx(0.0762)
    assert flip_bits == 0


def test_offset_plane_distance_positive_offset_with_flip() -> None:
    distance_m, flip_bits = features._offset_plane_distance(76.2, base_flip=True)
    assert distance_m == pytest.approx(0.0762)
    assert flip_bits == features._REF_PLANE_OPTION_FLIP


# --- _parse_edge_spec ---------------------------------------------------


def test_parse_edge_spec_topology_name_is_edge() -> None:
    name, x, y, z, entity_type = features._parse_edge_spec("Edge<1>")
    assert (name, x, y, z, entity_type) == ("Edge<1>", 0.0, 0.0, 0.0, "EDGE")


def test_parse_edge_spec_coordinate_is_edge() -> None:
    name, x, y, z, entity_type = features._parse_edge_spec("0.01,0.02,0.03")
    assert name == ""
    assert (x, y, z) == pytest.approx((0.01, 0.02, 0.03))
    assert entity_type == "EDGE"


def test_parse_edge_spec_face_prefix_selects_whole_face() -> None:
    name, x, y, z, entity_type = features._parse_edge_spec("face:0.01,0.02,0.03")
    assert name == ""
    assert (x, y, z) == pytest.approx((0.01, 0.02, 0.03))
    assert entity_type == "FACE"


def test_parse_edge_spec_face_prefix_is_case_insensitive() -> None:
    _, _, _, _, entity_type = features._parse_edge_spec("FACE:0.01,0.02,0.03")
    assert entity_type == "FACE"


def test_parse_edge_spec_face_prefix_with_unparseable_coordinates() -> None:
    """A malformed face: coordinate falls back to name-based FACE selection
    rather than silently mis-parsing as a coordinate.
    """
    name, x, y, z, entity_type = features._parse_edge_spec("face:not,a,coord")
    assert name == "not,a,coord"
    assert (x, y, z) == (0.0, 0.0, 0.0)
    assert entity_type == "FACE"


# ---- rename_feature ---------------------------------------------------------


class _Feature:
    def __init__(self, name: str, *, refuse_rename: bool = False) -> None:
        self._name, self._refuse = name, refuse_rename

    @property
    def Name(self) -> str:  # noqa: N802
        return self._name

    @Name.setter
    def Name(self, value: str) -> None:  # noqa: N802
        if self._refuse:
            raise RuntimeError("name is read-only")
        self._name = value


def _rename_adapter(features_by_name: dict) -> _FakeFeatureAdapter:
    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(
        FeatureByName=lambda name: features_by_name.get(name),
        EditRebuild3=lambda: True,
    )
    adapter._get_attr_or_call = lambda obj, name: getattr(obj, name)
    return adapter


def test_rename_requires_a_model_and_a_name() -> None:
    no_model = _FakeFeatureAdapter()
    empty_name = _rename_adapter({})

    assert features._rename_feature_impl(no_model, "A", "B").error == "No active model"
    assert (
        features._rename_feature_impl(empty_name, "A", " @Part1").error
        == "new_name must not be empty"
    )


def test_rename_reports_a_refused_and_a_silently_dropped_rename() -> None:
    refused = _rename_adapter({"Boss1": _Feature("Boss1", refuse_rename=True)})
    dropped = _rename_adapter({"Boss1": _Feature("Boss1")})  # new name never resolves

    refused_result = features._rename_feature_impl(refused, "Boss1", "Base")
    dropped_result = features._rename_feature_impl(dropped, "Boss1", "Base")

    assert "Failed to rename Boss1 to Base" in (refused_result.error or "")
    assert "did not take" in (dropped_result.error or "")


# ---- create_reference_point -------------------------------------------------


def _point_adapter(
    *, selected=True, manager=True, counts=(5, 6)
) -> _FakeFeatureAdapter:
    adapter = _FakeFeatureAdapter()
    remaining = list(counts)
    feature_manager = SimpleNamespace(
        GetFeatureCount=lambda _top: remaining.pop(0) if remaining else None,
        InsertReferencePoint=lambda *_a: object(),
    )
    adapter.currentModel = SimpleNamespace(
        ForceRebuild3=lambda _t: True,
        ClearSelection2=lambda _a: True,
        EditRebuild3=lambda: True,
        FeatureManager=feature_manager if manager else None,
        Extension=SimpleNamespace(SelectByID2=lambda *_a: selected),
    )
    return adapter


def test_reference_point_input_rules() -> None:
    assert (
        features._create_reference_point_impl(
            _FakeFeatureAdapter(), "face_center", 0, 0, 0, None, None
        ).error
        == "No active model"
    )
    assert (
        features._create_reference_point_impl(
            _point_adapter(), "along_curve", 0, 0, 0, 0.0, None
        ).error
        == "distance must be positive"
    )


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"selected": False}, "No edge found at (1, 2, 3) mm"),
        ({"manager": False}, "Part has no FeatureManager"),
        ({"counts": (None, None)}, "could not be read"),
        ({"counts": (5, 5)}, "added no feature"),
    ],
)
def test_reference_point_failures_are_explained(kwargs: dict, fragment: str) -> None:
    result = features._create_reference_point_impl(
        _point_adapter(**kwargs), "along_curve", 1, 2, 3, 10.0, None
    )

    assert result.status == AdapterResultStatus.ERROR
    assert fragment in (result.error or "")


def test_reference_point_along_curve_by_distance_succeeds() -> None:
    result = features._create_reference_point_impl(
        _point_adapter(), "along_curve", 1, 2, 3, 10.0, None
    )

    assert result.is_success, result.error
    assert result.data["distance_mm"] == 10.0


# ---- null callout -----------------------------------------------------------


def test_null_callout_sentinel_without_pywin32(monkeypatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "pythoncom", None)

    callout = features._null_callout()

    assert callout is features._NULL_CALLOUT_SENTINEL
    assert callout is not None
    assert repr(callout) == "<null callout: pywin32 unavailable>"


# ---- feature-tree walk helpers ----------------------------------------------


def test_read_member_returns_the_raw_member_when_calling_it_fails() -> None:
    class _ComObject:
        def __call__(self) -> None:  # default dispatch: "Member not found"
            raise RuntimeError("Member not found")

    sketch_obj = _ComObject()
    holder = SimpleNamespace(GetSpecificFeature2=sketch_obj)

    assert features._read_member(holder, "GetSpecificFeature2") is sketch_obj


class _ExplodingFeature:
    """A dispatch whose member access raises, like a stale COM object."""

    def __init__(self, fail_on: str, name: str = "Sketch9") -> None:
        self._fail_on, self.Name = fail_on, name

    def __getattr__(self, attr: str):
        if attr == self._fail_on:
            raise RuntimeError(f"com_error reading {attr}")
        if attr == "GetTypeName2":
            return lambda: "ProfileFeature"
        if attr == "GetNextFeature":
            return lambda: None
        raise AttributeError(attr)


@pytest.mark.parametrize(
    ("first", "expected"),
    [
        (_ExplodingFeature("GetTypeName2"), []),  # type unreadable: skipped
        (_ExplodingFeature("GetNextFeature"), ["Sketch9"]),  # walk stops
    ],
)
def test_profile_feature_names_survives_unreadable_members(
    first: object, expected: list[str]
) -> None:
    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(FirstFeature=lambda: first)

    assert features._profile_feature_names(adapter) == expected


def test_profile_feature_names_without_a_model_is_empty() -> None:
    assert features._profile_feature_names(SimpleNamespace()) == []


def test_parse_edge_spec_treats_non_numeric_triplets_as_names() -> None:
    assert features._parse_edge_spec("a,b,c") == ("a,b,c", 0.0, 0.0, 0.0, "EDGE")


@pytest.mark.parametrize(
    ("point", "responses", "expected"),
    [
        ((0.01, 0.0, 0.02), [RuntimeError("busy"), True], True),  # off-axis, retry
        ((0.0, 0.01, 0.0), [False, False, False], False),  # nothing there
    ],
)
def test_select_edge_by_coord_retries_and_gives_up(point, responses, expected) -> None:
    replies = iter(responses)

    def _select(*_args):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(
        ForceRebuild3=lambda _t: True, Extension=SimpleNamespace(SelectByID2=_select)
    )

    assert features._select_edge_by_coord(adapter, *point, append=False) is expected


# ---- version-specific and selection-failure feature paths ---------------------


def _versioned_adapter(revision: str) -> _FilletAdapterSW2026:
    adapter = _FilletAdapterSW2026()
    adapter.swApp = SimpleNamespace(RevisionNumber=revision)
    adapter.constants = {
        **adapter.constants,
        "swEndCondThroughAllBoth": 9,
    }
    return adapter


@pytest.mark.parametrize("revision", ["33.4.0", "34.4.0"])
def test_revolve_angles_use_exact_radians(revision: str) -> None:
    import math

    from solidworks_mcp.adapters.base import RevolveParameters

    calls: list[tuple] = []
    adapter = _versioned_adapter(revision)
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureRevolve2=lambda *args: (
                calls.append(args) or SimpleNamespace(Name="Revolve1")
            )
        )
    )

    result = features._create_revolve_impl(
        adapter, RevolveParameters(angle=90.0, both_directions=True)
    )

    assert result.is_success, result.error
    (args,) = calls
    assert args[8] == pytest.approx(math.pi / 2)  # Dir1Angle
    assert args[9] == pytest.approx(math.pi / 2)  # Dir2Angle


def test_revolve_on_sw2025_accepts_a_none_return() -> None:
    """SW 2025's FeatureRevolve2 returns nothing even when it succeeds."""
    from solidworks_mcp.adapters.base import RevolveParameters

    adapter = _versioned_adapter("33.0")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(FeatureRevolve2=lambda *_a: None)
    )

    result = features._create_revolve_impl(adapter, RevolveParameters(angle=360.0))

    assert result.is_success
    assert result.data.name == "Revolve-Auto"


def _tree(*names: str):
    """A FirstFeature chain of sketches with the given names."""
    nodes = [
        SimpleNamespace(GetTypeName2=lambda: "ProfileFeature", Name=n) for n in names
    ]
    for node, nxt in zip(nodes, [*nodes[1:], None], strict=True):
        node.GetNextFeature = lambda nxt=nxt: nxt
    return lambda: nodes[0]


def _selectable(*names: str):
    def _by_name(name: str):
        if name in names:
            return SimpleNamespace(Select2=lambda _append, _mark: True)
        return None

    return _by_name


def test_sweep_reports_an_unselectable_path() -> None:
    from solidworks_mcp.adapters.base import SweepParameters

    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(),
        ClearSelection2=lambda _a: True,
        FirstFeature=_tree("Profile1"),
        FeatureByName=_selectable("Profile1"),
    )

    result = features._create_sweep_impl(adapter, SweepParameters(path="Path1"))

    assert "Failed to select sweep path: Path1" in (result.error or "")


def test_loft_reports_an_unselectable_guide_curve() -> None:
    from solidworks_mcp.adapters.base import LoftParameters

    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(),
        ClearSelection2=lambda _a: True,
        FeatureByName=_selectable("P1", "P2"),
    )

    result = features._create_loft_impl(
        adapter, LoftParameters(profiles=["P1", "P2"], guide_curves=["G1"])
    )

    assert "Failed to select loft guide curve: G1" in (result.error or "")


@pytest.mark.parametrize(
    ("revision", "end_condition", "expected_t1"),
    [
        ("not-a-version", "ThroughAllBoth", 9),
        ("33.1.0", "Blind", 1),
    ],
)
def test_cut_extrude_version_and_end_condition_paths(
    revision: str, end_condition: str, expected_t1: int
) -> None:
    calls: list[tuple] = []
    adapter = _versioned_adapter(revision)
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureCut4=lambda *args: (
                calls.append(args) or SimpleNamespace(Name="Cut-Extrude1")
            ),
            FeatureCut3=lambda *_a: None,
        ),
        ClearSelection2=lambda *_a: True,
        FirstFeature=_fake_sketch_feature("Sketch1"),
        Extension=SimpleNamespace(SelectByID2=lambda *_a, **_k: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(
        adapter, ExtrusionParameters(depth=5.0, end_condition=end_condition)
    )

    assert result.is_success, result.error
    assert calls[0][3] == expected_t1  # T1
    if revision.startswith("33"):
        assert len(calls[0]) == 27  # SW 2025 signature


def test_fillet_with_unparseable_version_and_unreadable_feature_name() -> None:
    class _Fillet:
        @property
        def Name(self):  # noqa: N802
            raise RuntimeError("stale dispatch")

    adapter = _versioned_adapter("garbage")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(FeatureFillet3=lambda *_a: _Fillet()),
        Extension=SimpleNamespace(SelectByID2=lambda *_a: True),
    )

    result = features._add_fillet_impl(adapter, 2.0, ["Edge<1>"])

    assert result.is_success, result.error
    assert result.data.name == "Fillet"


@pytest.mark.parametrize("percent", [0.0, 100.0, 150.0])
def test_reference_point_percent_must_be_inside_the_curve(percent: float) -> None:
    result = features._create_reference_point_impl(
        _point_adapter(), "along_curve", 0, 0, 0, None, percent
    )

    assert result.error == "percent must be between 0 and 100 (exclusive)"


def _build_adapter(monkeypatch) -> PyWin32Adapter:
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter._ComSessionCoordinator",
        lambda _adapter: SimpleNamespace(),
        raising=False,
    )
    return PyWin32Adapter({})


class TestSolidWorksFeaturesMixinSweepLoft:
    """Cover the create_sweep and create_loft delegation paths."""

    @pytest.mark.asyncio
    async def test_create_sweep_returns_error(self, monkeypatch) -> None:
        """create_sweep is a stub that always returns ERROR."""
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        params = SimpleNamespace(profile_sketch="Sketch1", path_sketch="Path1")
        result = await adapter.create_sweep(params)
        assert result.is_error
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_create_loft_returns_error(self, monkeypatch) -> None:
        """create_loft is a stub that always returns ERROR."""
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        params = SimpleNamespace(profiles=["Sketch1", "Sketch2"])
        result = await adapter.create_loft(params)
        assert result.is_error
        assert result.error is not None


class TestMirrorAndPatternVolumeBracketing:
    """Cover the async wrapper methods' before/after volume-check branches."""

    @pytest.mark.asyncio
    async def test_mirror_feature_errors_when_volume_unreadable(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.get_mass_properties = AsyncMock(
            return_value=AdapterResult(
                status=AdapterResultStatus.ERROR, error="no solid bodies"
            )
        )
        with patch(
            "solidworks_mcp.adapters.solidworks.features._mirror_feature_impl",
            return_value=AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={"name": "Mirror1"}
            ),
        ):
            result = await adapter.mirror_feature(["Body1"], "Right Plane")
        assert result.is_error
        assert "volume could not be read" in (result.error or "")

    @pytest.mark.asyncio
    async def test_mirror_feature_errors_when_volume_did_not_grow(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        same_volume = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=SimpleNamespace(volume=100.0)
        )
        adapter.get_mass_properties = AsyncMock(return_value=same_volume)
        with patch(
            "solidworks_mcp.adapters.solidworks.features._mirror_feature_impl",
            return_value=AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={"name": "Mirror1"}
            ),
        ):
            result = await adapter.mirror_feature(["Body1"], "Right Plane")
        assert result.is_error
        assert "no new geometry" in (result.error or "")

    @pytest.mark.asyncio
    async def test_pattern_circular_errors_when_volume_unreadable(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.get_mass_properties = AsyncMock(
            return_value=AdapterResult(status=AdapterResultStatus.ERROR, error="n/a")
        )
        with patch(
            "solidworks_mcp.adapters.solidworks.features._pattern_circular_impl",
            return_value=AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={"name": "CirPattern1"}
            ),
        ):
            result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 4)
        assert result.is_error
        assert "volume could not be read" in (result.error or "")

    @pytest.mark.asyncio
    async def test_pattern_circular_errors_when_volume_did_not_grow(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        same_volume = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=SimpleNamespace(volume=48431.5)
        )
        adapter.get_mass_properties = AsyncMock(return_value=same_volume)
        with patch(
            "solidworks_mcp.adapters.solidworks.features._pattern_circular_impl",
            return_value=AdapterResult(
                status=AdapterResultStatus.SUCCESS, data={"name": "CirPattern1"}
            ),
        ):
            result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 4)
        assert result.is_error
        assert "produced no geometry" in (result.error or "")


class TestSelectReferenceEntityFallback:
    """Cover ``_select_reference_entity``'s SelectByID2 PLANE/FACE fallback."""

    def test_falls_back_to_face_selectbyid2(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        # The named-feature path fails, so the fallback loop runs.
        adapter.currentModel.FeatureByName.return_value = None
        # PLANE attempt fails, FACE attempt succeeds.
        adapter.currentModel.Extension.SelectByID2.side_effect = [False, True]

        result = _select_reference_entity(adapter, "SomeFace", 0, append=False)

        assert result is True
        assert adapter.currentModel.Extension.SelectByID2.call_count == 2

    def test_returns_false_when_every_attempt_fails(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None
        adapter.currentModel.Extension.SelectByID2.return_value = False

        result = _select_reference_entity(adapter, "Nothing", 0, append=False)

        assert result is False


class TestCreateReferencePlaneImplErrors:
    """Cover ``_create_reference_plane_impl``'s two raise branches."""

    def test_errors_when_reference_not_selectable(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None
        adapter.currentModel.Extension.SelectByID2.return_value = False

        result = _create_reference_plane_impl(
            adapter, "Nonexistent Plane", 10.0, 0.0, False
        )

        assert result.is_error
        assert "Failed to select reference plane/face" in (result.error or "")

    def test_errors_when_plane_name_unreadable(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        # Named-feature selection succeeds.
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        # Feature count must rise (before < after) to pass that guard.
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.side_effect = [5, 6]
        adapter.currentModel.FeatureManager = feature_manager
        # InsertRefPlane succeeds but the resulting plane's Name is empty.
        feature_manager.InsertRefPlane.return_value = SimpleNamespace(Name="")

        result = _create_reference_plane_impl(adapter, "Front Plane", 10.0, 0.0, False)

        assert result.is_error
        assert "name could not be read" in (result.error or "")


class TestCreateAxisImplErrors:
    """Cover ``_create_axis_impl``'s "feature count unreadable" branch."""

    def test_errors_when_feature_count_unreadable(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        # GetFeatureCount returns a non-numeric value both times, so
        # _feature_count(adapter) resolves to None on both reads.
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.return_value = None
        adapter.currentModel.FeatureManager = feature_manager

        result = _create_axis_impl(adapter, "z")

        assert result.is_error
        assert "feature count could not be read" in (result.error or "")


class TestMirrorAndPatternImplReturnedNothing:
    """Cover the "COM returned nothing after a valid selection" raises."""

    def test_mirror_feature_impl_errors_when_insert_returns_nothing(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        # mirror_bodies=False routes source AND plane selection through the
        # named-feature path (FeatureByName + Select2), avoiding the need to
        # also wire up the SelectByID2 body-selection branch.
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        feature_manager = MagicMock()
        feature_manager.InsertMirrorFeature.return_value = None
        adapter.currentModel.FeatureManager = feature_manager

        result = _mirror_feature_impl(adapter, ["Loft1"], "Right Plane", True, False)

        assert result.is_error
        assert "InsertMirrorFeature returned nothing" in (result.error or "")

    def test_pattern_circular_impl_errors_when_call_returns_nothing(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        # Axis and feature selection both go through SelectByID2 directly.
        adapter.currentModel.Extension.SelectByID2.return_value = True
        feature_manager = MagicMock()
        feature_manager.FeatureCircularPattern5.return_value = None
        adapter.currentModel.FeatureManager = feature_manager

        result = _pattern_circular_impl(
            adapter, ["Boss-Extrude1"], "Axis1", 4, 360.0, True
        )

        assert result.is_error
        assert "FeatureCircularPattern5 returned nothing" in (result.error or "")


class TestSuppressFeatureImplStateMismatch:
    """Cover the "state did not change" guard in ``_suppress_feature_impl``."""

    def test_errors_when_readback_state_does_not_match_request(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        # First FeatureByName call (initial select) and second (post-rebuild
        # refresh) both resolve to a feature reporting IsSuppressed=False -
        # a suppress request (suppress=True) that the COM call accepted but
        # that did not actually take effect.
        adapter.currentModel.FeatureByName.side_effect = [
            SimpleNamespace(IsSuppressed=False, Select2=lambda append, mark: True),
            SimpleNamespace(IsSuppressed=False),
        ]

        result = _suppress_feature_impl(adapter, "Fillet1", True)

        assert result.is_error
        assert "did not change" in (result.error or "")


class TestFeatureCountAndSuppressedHelpers:
    """Direct unit tests for the small module-level helpers in features.py."""

    def test_feature_count_returns_none_when_manager_unreadable(self) -> None:
        class _Adapter:
            currentModel = SimpleNamespace(FeatureManager=None)

            def _attempt(self, op, default=None):
                try:
                    return op()
                except Exception:
                    return default

        assert _feature_count(_Adapter()) is None

    def test_feature_count_returns_none_when_count_not_numeric(self) -> None:
        class _Adapter:
            currentModel = SimpleNamespace(
                FeatureManager=SimpleNamespace(
                    GetFeatureCount=lambda include_hidden: "not-a-number"
                )
            )

            def _attempt(self, op, default=None):
                try:
                    return op()
                except Exception:
                    return default

        assert _feature_count(_Adapter()) is None

    def test_is_suppressed_reads_list_state(self) -> None:
        class _Adapter:
            def _attempt(self, op, default=None):
                try:
                    return op()
                except Exception:
                    return default

            def _get_attr_or_call(self, obj, attr_name):
                attr = getattr(obj, attr_name, None)
                return attr() if callable(attr) else attr

        feature = SimpleNamespace(IsSuppressed=[True])
        assert _is_suppressed(_Adapter(), feature) is True

    def test_is_suppressed_reads_int_state(self) -> None:
        class _Adapter:
            def _attempt(self, op, default=None):
                try:
                    return op()
                except Exception:
                    return default

            def _get_attr_or_call(self, obj, attr_name):
                attr = getattr(obj, attr_name, None)
                return attr() if callable(attr) else attr

        feature = SimpleNamespace(IsSuppressed=1)
        assert _is_suppressed(_Adapter(), feature) is True

    def test_is_suppressed_returns_none_for_unrecognized_type(self) -> None:
        class _Adapter:
            def _attempt(self, op, default=None):
                try:
                    return op()
                except Exception:
                    return default

            def _get_attr_or_call(self, obj, attr_name):
                attr = getattr(obj, attr_name, None)
                return attr() if callable(attr) else attr

        feature = SimpleNamespace(IsSuppressed="unexpected")
        assert _is_suppressed(_Adapter(), feature) is None


class TestDeleteFeatureImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _delete_feature_impl(adapter, "Boss-Extrude1")
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_edit_delete_did_not_remove_feature(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        feature = SimpleNamespace(Select2=lambda append, mark: True)
        adapter.currentModel.FeatureByName.return_value = feature

        result = _delete_feature_impl(adapter, "Boss-Extrude1")

        assert result.is_error
        assert "EditDelete did not remove feature" in (result.error or "")


class TestSuppressFeatureImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _suppress_feature_impl(adapter, "Fillet1", True)
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_feature_not_found(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None

        result = _suppress_feature_impl(adapter, "Ghost1", True)

        assert result.is_error
        assert "Feature not found: Ghost1" in (result.error or "")

    def test_errors_when_edit_suppress_raises(self, monkeypatch) -> None:
        """Late binding can resolve EditSuppress2 as a property that performs
        the edit and *then* raises "'bool' object is not callable" - the
        operation succeeds while the caller sees a failure. Reproduced here
        via a plain raise, which _attempt_with_error reports the same way."""
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True, IsSuppressed=False
        )
        adapter.currentModel.EditSuppress2.side_effect = TypeError(
            "'bool' object is not callable"
        )

        result = _suppress_feature_impl(adapter, "Fillet1", True)

        assert result.is_error
        assert "Failed to suppress Fillet1" in (result.error or "")


class TestUndoImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _undo_impl(adapter, 1)
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_both_undo_overloads_fail(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.EditUndo2.side_effect = RuntimeError("not supported")
        adapter.currentModel.EditUndo.side_effect = RuntimeError("legacy gone too")

        result = _undo_impl(adapter, 1)

        assert result.is_error
        assert "Undo failed" in (result.error or "")


class TestCreateReferencePlaneImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _create_reference_plane_impl(adapter, "Front Plane", 10.0, 0.0, False)
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_reference_blank(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()

        result = _create_reference_plane_impl(adapter, "", 10.0, 0.0, False)

        assert result.is_error
        assert "requires a reference plane/face name" in (result.error or "")

    def test_flip_true_combines_the_option_flag_on_success(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.side_effect = [5, 6]
        feature_manager.InsertRefPlane.return_value = SimpleNamespace(Name="Plane1")
        adapter.currentModel.FeatureManager = feature_manager

        result = _create_reference_plane_impl(adapter, "Front Plane", 10.0, 0.0, True)

        assert result.is_success
        no_flip_constraint = feature_manager.InsertRefPlane.call_args.args[0]
        assert no_flip_constraint & 256  # _REF_PLANE_OPTION_FLIP bit is set

    def test_errors_when_no_plane_added_to_tree(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.return_value = 5  # unchanged before/after
        adapter.currentModel.FeatureManager = feature_manager

        result = _create_reference_plane_impl(adapter, "Front Plane", 10.0, 0.0, False)

        assert result.is_error
        assert "No reference plane was added" in (result.error or "")

    def test_errors_when_insert_ref_plane_returns_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.side_effect = [5, 6]
        feature_manager.InsertRefPlane.return_value = None
        adapter.currentModel.FeatureManager = feature_manager

        result = _create_reference_plane_impl(adapter, "Front Plane", 10.0, 0.0, False)

        assert result.is_error
        assert "InsertRefPlane returned nothing" in (result.error or "")


class TestCreateAxisImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _create_axis_impl(adapter, "z")
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_plane_selection_fails(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None
        adapter.currentModel.Extension.SelectByID2.return_value = False

        result = _create_axis_impl(adapter, "z")

        assert result.is_error
        assert "Failed to select" in (result.error or "")

    def test_errors_when_no_axis_created_but_counts_readable(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Select2=lambda append, mark: True
        )
        feature_manager = MagicMock()
        feature_manager.GetFeatureCount.return_value = 5  # unchanged
        adapter.currentModel.FeatureManager = feature_manager

        result = _create_axis_impl(adapter, "z")

        assert result.is_error
        assert "No reference axis was created" in (result.error or "")


class TestMirrorFeatureImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _mirror_feature_impl(adapter, ["Loft1"], "Right Plane", True, True)
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_errors_when_plane_selection_fails_but_source_succeeds(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()

        def feature_by_name(name):
            if name == "Loft1":
                return SimpleNamespace(Select2=lambda append, mark: True)
            return None

        adapter.currentModel.FeatureByName.side_effect = feature_by_name
        adapter.currentModel.Extension.SelectByID2.return_value = False

        result = _mirror_feature_impl(adapter, ["Loft1"], "Right Plane", True, False)

        assert result.is_error
        assert "Failed to select mirror plane: Right Plane" in (result.error or "")


class TestPatternCircularImplMoreErrors:
    def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = _pattern_circular_impl(
            adapter, ["Boss-Extrude1"], "Axis1", 4, 360.0, True
        )
        assert result.is_error
        assert "No active model" in (result.error or "")

    def test_falls_back_to_named_feature_selection_and_then_fails(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()

        def select_by_id2(name, kind, x, y, z, append, mark, callout, opt):
            return kind == "AXIS"

        adapter.currentModel.Extension.SelectByID2.side_effect = select_by_id2
        adapter.currentModel.FeatureByName.return_value = None

        result = _pattern_circular_impl(
            adapter, ["Boss-Extrude1"], "Axis1", 4, 360.0, True
        )

        assert result.is_error
        assert "Failed to select feature to pattern" in (result.error or "")


class TestMirrorAndPatternWrapperNoActiveModel:
    """The async wrapper methods' own early 'no active model' guard."""

    @pytest.mark.asyncio
    async def test_mirror_feature_errors_when_no_active_model(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.mirror_feature(["Body1"], "Right Plane")
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_pattern_circular_errors_when_no_active_model(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.pattern_circular(["Boss-Extrude1"], "Axis1", 4)
        assert result.is_error
        assert "No active model" in (result.error or "")


class TestPyWin32AdapterBranches:
    """Additional PyWin32Adapter branch coverage with pure mocks."""

    @staticmethod
    def _build_adapter(monkeypatch) -> PyWin32Adapter:
        """Test helper for build adapter."""
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Windows",
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=RuntimeError),
            raising=False,
        )
        adapter = PyWin32Adapter({})
        # Synchronous mock ComExecutor: avoids "ComExecutor is not running"
        # guard in _handle_com_operation for tests that set swApp/currentModel
        # directly without going through connect().
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_com = MagicMock()
        mock_com._thread = mock_thread
        mock_com.run = lambda fn, timeout=None: fn()
        adapter._com = mock_com
        return adapter

    @staticmethod
    def _sketch_tree(*names):
        """Build a FirstFeature→GetNextFeature chain of ProfileFeature mocks.

        Each node mimics the COM ``IFeature`` attributes the feature-tree
        walk in ``features.py`` reads: ``GetTypeName2`` and ``Name`` as
        properties and ``GetNextFeature`` as the link to the next node.
        """
        nxt = None
        for name in reversed(names):
            nxt = SimpleNamespace(
                GetTypeName2="ProfileFeature", Name=name, GetNextFeature=nxt
            )
        return nxt

    @staticmethod
    def _feature_by_name(selected, *, fail=()):
        """Return a FeatureByName mock that records ``Select2(append, mark)``.

        ``features.py`` selects sketches/curves via
        ``currentModel.FeatureByName(name).Select2(append, mark)``.  This
        helper returns a callable that appends ``(name, append, mark)`` to
        ``selected`` and reports success, except for names in ``fail`` (which
        return ``None`` from ``FeatureByName`` to simulate a missing feature).
        """

        def factory(name):
            if name in fail:
                return None
            feature = SimpleNamespace()
            feature.Select2 = lambda append, mark, _n=name: bool(
                selected.append((_n, append, mark)) or True
            )
            return feature

        return factory

    @pytest.mark.asyncio
    async def test_feature_id_and_mass_properties_tuple_fallback(self, monkeypatch):
        """Feature IDs and mass properties should support common COM compatibility variants."""
        adapter = self._build_adapter(monkeypatch)

        feature_obj = SimpleNamespace(Name="FeatInt", GetID=lambda: 123)
        feature_manager = SimpleNamespace(
            FeatureExtrusion3=Mock(return_value=feature_obj),
            FeatureExtrusion2=Mock(return_value=feature_obj),
            FeatureExtruThin2=Mock(return_value=feature_obj),
            FeatureRevolve2=Mock(return_value=feature_obj),
            FeatureCut3=Mock(return_value=feature_obj),
            FeatureFillet3=Mock(return_value=feature_obj),
            FeatureChamfer=Mock(return_value=feature_obj),
            InsertFeatureChamfer=Mock(return_value=feature_obj),
        )
        sketch_manager = SimpleNamespace(
            InsertSketch=Mock(return_value=SimpleNamespace(Name="SketchA")),
            CreateCenterLine=Mock(return_value=object()),
            CreateLine=Mock(return_value=object()),
        )
        extension = SimpleNamespace(
            SelectByID2=Mock(return_value=True),
            CreateMassProperty=Mock(side_effect=RuntimeError("member not found")),
        )
        adapter.currentModel = SimpleNamespace(
            Extension=extension,
            SketchManager=sketch_manager,
            FeatureManager=feature_manager,
            ClearSelection2=Mock(return_value=True),
            GetMassProperties=(
                0.001,
                0.002,
                0.003,
                4.0e-9,
                7.0e-6,
                0.5,
                11.0,
                22.0,
                33.0,
                44.0,
                55.0,
                66.0,
            ),
        )

        extrude = await adapter.create_extrusion(
            SimpleNamespace(
                depth=10.0,
                draft_angle=0.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )
        mass = await adapter.get_mass_properties()

        assert extrude.is_success
        assert extrude.data.id == "123"
        assert mass.is_success
        assert mass.data.volume == pytest.approx(4.0)
        assert mass.data.surface_area == pytest.approx(7.0)
        assert mass.data.mass == pytest.approx(0.5)
        assert mass.data.center_of_mass == [1.0, 2.0, 3.0]
        assert mass.data.moments_of_inertia["Ixx"] == pytest.approx(11.0)
        assert mass.data.moments_of_inertia["Iyy"] == pytest.approx(22.0)
        assert mass.data.moments_of_inertia["Izz"] == pytest.approx(33.0)

    @pytest.mark.asyncio
    async def test_feature_creation_failure_paths(self, monkeypatch):
        """Cover failure branches for cut/fillet/chamfer feature creation."""
        adapter = self._build_adapter(monkeypatch)
        model = SimpleNamespace(
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=True)),
            FeatureManager=SimpleNamespace(
                FeatureCut3=Mock(return_value=None),
                FeatureFillet3=Mock(return_value=None),
                FeatureChamfer=Mock(return_value=None),
            ),
            FirstFeature=SimpleNamespace(
                GetTypeName2=lambda: "ProfileFeature",
                Name="Sketch1",
                GetNextFeature=lambda: None,
            ),
            ClearSelection2=Mock(return_value=True),
        )
        adapter.currentModel = model
        adapter._last_sketch_name = "Sketch1"

        cut_fail = await adapter.create_cut_extrude(
            SimpleNamespace(depth=2.0, draft_angle=0.0, reverse_direction=False)
        )
        assert cut_fail.is_error
        assert "Sketch1" in (cut_fail.error or "")
        assert "FeatureCut4" in (cut_fail.error or "")

        model.Extension.SelectByID2 = Mock(return_value=False)
        fillet_select_fail = await adapter.add_fillet(1.0, ["Edge1"])
        chamfer_select_fail = await adapter.add_chamfer(1.0, ["Edge1"])
        assert fillet_select_fail.is_error
        assert "Failed to select edge" in (fillet_select_fail.error or "")
        assert chamfer_select_fail.is_error
        assert "Failed to select edge" in (chamfer_select_fail.error or "")

        model.Extension.SelectByID2 = Mock(return_value=True)
        fillet_create_fail = await adapter.add_fillet(1.0, ["Edge1"])
        chamfer_create_fail = await adapter.add_chamfer(1.0, ["Edge1"])
        assert fillet_create_fail.is_error
        assert "Failed to create fillet" in (fillet_create_fail.error or "")
        assert chamfer_create_fail.is_error
        assert "Failed to create chamfer" in (chamfer_create_fail.error or "")

    @pytest.mark.asyncio
    async def test_create_extrusion_and_revolve_feature_none_errors(
        self, monkeypatch
    ) -> None:
        """create_extrusion/create_revolve should error when feature manager returns None."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FeatureManager=SimpleNamespace(
                FeatureExtrusion3=Mock(return_value=None),
                FeatureExtrusion2=Mock(return_value=None),
                FeatureRevolve2=Mock(return_value=None),
            )
        )

        extrusion_result = await adapter.create_extrusion(
            SimpleNamespace(
                depth=5.0,
                draft_angle=0.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )
        revolve_result = await adapter.create_revolve(
            SimpleNamespace(
                angle=90.0,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )

        assert extrusion_result.is_error
        assert "Failed to create extrusion feature" in (extrusion_result.error or "")
        assert revolve_result.is_error
        assert "Failed to create revolve feature" in (revolve_result.error or "")

    @pytest.mark.asyncio
    async def test_create_sweep_no_model_and_missing_path(self, monkeypatch) -> None:
        """create_sweep guards: no active model, then missing path name."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = None
        no_model = await adapter.create_sweep(SimpleNamespace(path="Sketch2"))
        assert no_model.is_error
        assert "No active model" in (no_model.error or "")

        adapter.currentModel = SimpleNamespace()
        no_path = await adapter.create_sweep(
            SimpleNamespace(path="", twist_along_path=False, twist_angle=0.0)
        )
        assert no_path.is_error
        assert "path" in (no_path.error or "")

    @pytest.mark.asyncio
    async def test_create_sweep_success_selects_profile_and_path(
        self, monkeypatch
    ) -> None:
        """create_sweep selects the non-path sketch (mark 1) + path (mark 4)
        and forwards the constant-twist option to InsertProtrusionSwept4."""
        adapter = self._build_adapter(monkeypatch)

        selected: list[tuple] = []
        swept = Mock(return_value=SimpleNamespace(Name="Sweep1", GetID=lambda: 7))
        adapter.currentModel = SimpleNamespace(
            FirstFeature=self._sketch_tree("Sketch1", "Sketch2"),
            FeatureByName=self._feature_by_name(selected),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(InsertProtrusionSwept4=swept),
        )

        result = await adapter.create_sweep(
            SimpleNamespace(
                path="Sketch2",
                twist_along_path=True,
                twist_angle=90.0,
                merge_result=True,
            )
        )

        assert result.is_success, result.error
        assert result.data.type == "Sweep"
        assert result.data.parameters["profile"] == "Sketch1"
        assert result.data.parameters["path"] == "Sketch2"

        # Profile selected under mark 1 (append False), path under mark 4
        # (append True). Recorded tuples are (name, append, mark).
        assert ("Sketch1", False, 1) in selected
        assert ("Sketch2", True, 4) in selected

        # TwistCtrlOption (arg index 2) == 8 (constant twist along path) and
        # TwistAngle (arg index 15) == 90 degrees in radians.
        swept_args = swept.call_args.args
        assert swept_args[2] == 8
        assert swept_args[15] == pytest.approx(math.radians(90.0))

    @pytest.mark.asyncio
    async def test_create_sweep_no_profile_distinct_from_path(
        self, monkeypatch
    ) -> None:
        """When the only sketch is the path itself, create_sweep errors."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FirstFeature=self._sketch_tree("Sketch2"),
            FeatureByName=self._feature_by_name([]),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(InsertProtrusionSwept4=Mock()),
        )

        result = await adapter.create_sweep(
            SimpleNamespace(path="Sketch2", twist_along_path=False, twist_angle=0.0)
        )
        assert result.is_error
        assert "profile sketch distinct from the path" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_sweep_feature_none_errors(self, monkeypatch) -> None:
        """create_sweep errors when InsertProtrusionSwept4 returns None."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FirstFeature=self._sketch_tree("Sketch1", "Sketch2"),
            FeatureByName=self._feature_by_name([]),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(
                InsertProtrusionSwept4=Mock(return_value=None)
            ),
        )

        result = await adapter.create_sweep(
            SimpleNamespace(path="Sketch2", twist_along_path=False, twist_angle=0.0)
        )
        assert result.is_error
        assert "Failed to create sweep feature" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_sweep_profile_selection_failure(self, monkeypatch) -> None:
        """create_sweep errors with the profile name when Select2 can't find it."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FirstFeature=self._sketch_tree("Sketch1", "Sketch2"),
            # FeatureByName returns None for the inferred profile sketch.
            FeatureByName=self._feature_by_name([], fail=("Sketch1",)),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(InsertProtrusionSwept4=Mock()),
        )

        result = await adapter.create_sweep(
            SimpleNamespace(path="Sketch2", twist_along_path=False, twist_angle=0.0)
        )
        assert result.is_error
        assert "Sketch1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_loft_no_model_and_too_few_profiles(self, monkeypatch) -> None:
        """create_loft guards: no active model, then fewer than two profiles."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = None
        no_model = await adapter.create_loft(SimpleNamespace(profiles=["A", "B"]))
        assert no_model.is_error
        assert "No active model" in (no_model.error or "")

        adapter.currentModel = SimpleNamespace()
        too_few = await adapter.create_loft(SimpleNamespace(profiles=["OnlyOne"]))
        assert too_few.is_error
        assert "at least 2 profile" in (too_few.error or "")

    @pytest.mark.asyncio
    async def test_create_loft_success_selects_profiles_in_order(
        self, monkeypatch
    ) -> None:
        """create_loft selects every profile under mark 1 (first replaces,
        rest append) and guide curves under mark 2."""
        adapter = self._build_adapter(monkeypatch)

        selected: list[tuple] = []
        blend = Mock(return_value=SimpleNamespace(Name="Loft1", GetID=lambda: 9))
        adapter.currentModel = SimpleNamespace(
            FeatureByName=self._feature_by_name(selected),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(InsertProtrusionBlend2=blend),
        )

        result = await adapter.create_loft(
            SimpleNamespace(
                profiles=["Sketch1", "Sketch2"],
                guide_curves=["Sketch3"],
                start_tangent="normal",
                end_tangent=None,
                merge_result=True,
            )
        )

        assert result.is_success, result.error
        assert result.data.type == "Loft"
        assert result.data.parameters["profiles"] == ["Sketch1", "Sketch2"]

        # Recorded tuples are (name, append, mark).
        assert ("Sketch1", False, 1) in selected  # first profile, replace
        assert ("Sketch2", True, 1) in selected  # second profile, append
        assert ("Sketch3", True, 2) in selected  # guide curve, mark 2

        # StartMatchingType (arg 4) == 1 (tangent to normal) from
        # start_tangent="normal"; EndMatchingType (arg 5) == 0 from None.
        blend_args = blend.call_args.args
        assert blend_args[4] == 1
        assert blend_args[5] == 0

    @pytest.mark.asyncio
    async def test_create_loft_feature_none_errors(self, monkeypatch) -> None:
        """create_loft errors when InsertProtrusionBlend2 returns None."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FeatureByName=self._feature_by_name([]),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(
                InsertProtrusionBlend2=Mock(return_value=None)
            ),
        )

        result = await adapter.create_loft(
            SimpleNamespace(
                profiles=["Sketch1", "Sketch2"],
                guide_curves=None,
                start_tangent=None,
                end_tangent=None,
                merge_result=True,
            )
        )
        assert result.is_error
        assert "Failed to create loft feature" in (result.error or "")

    @pytest.mark.asyncio
    async def test_create_loft_profile_selection_failure(self, monkeypatch) -> None:
        """create_loft errors with the profile name when Select2 can't find it."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FeatureByName=self._feature_by_name([], fail=("SketchA",)),
            ClearSelection2=Mock(return_value=True),
            FeatureManager=SimpleNamespace(InsertProtrusionBlend2=Mock()),
        )

        result = await adapter.create_loft(
            SimpleNamespace(
                profiles=["SketchA", "SketchB"],
                guide_curves=None,
                start_tangent=None,
                end_tangent=None,
                merge_result=True,
            )
        )
        assert result.is_error
        assert "SketchA" in (result.error or "")


def test_zero_arg_edit_members_are_not_called_with_parentheses() -> None:
    """``EditSuppress2`` and friends must go through ``_get_attr_or_call``.

    Late binding resolves these zero-argument members as properties on some
    dispatches. Calling them with ``()`` performs the edit and *then* raises
    ``'bool' object is not callable``, so the operation succeeds while the
    caller is told it failed — measured on SW 2025 before this was fixed.
    """
    from pathlib import Path

    import solidworks_mcp.adapters.solidworks.features as features_module

    source = Path(features_module.__file__).read_text(encoding="utf-8")
    for member in ("EditSuppress2", "EditUnsuppress2", "EditDelete", "IsSuppressed"):
        assert f".{member}()" not in source, (
            f"{member} is called with parentheses; late binding may resolve it "
            "as a property, which raises after the edit has already happened. "
            "Use adapter._get_attr_or_call(obj, name)."
        )


def test_mirror_selection_marks_match_the_solidworks_api() -> None:
    """These are the SolidWorks-documented selection marks for InsertMirrorFeature.

    Per the API reference: features are mark 1, faces are mark 128, bodies
    are mark 256, and the mirror plane is mark 2. Wrong marks make the call
    report a feature while mirroring nothing - a bug no other test here
    would catch, since the live COM code is off-limits for modification and
    the mock does not execute this path at all.
    """
    from solidworks_mcp.adapters.solidworks.features import (
        _MIRROR_MARK_BODIES,
        _MIRROR_MARK_FEATURES,
        _MIRROR_MARK_PLANE,
    )

    assert _MIRROR_MARK_FEATURES == 1
    assert _MIRROR_MARK_BODIES == 256
    assert _MIRROR_MARK_PLANE == 2


def test_pattern_selection_marks_match_the_solidworks_api() -> None:
    """These are the SolidWorks-documented selection marks for FeatureCircularPattern5.

    Per the API reference: the direction axis is mark 1 and the features to
    pattern are mark 4. These differ from the mirror marks (features 1,
    plane 2) - reusing those makes the call report a feature while
    patterning nothing, a bug no other test here would catch, since the
    live COM code is off-limits for modification and the mock does not
    execute this path at all.
    """
    from solidworks_mcp.adapters.solidworks.features import (
        _PATTERN_MARK_AXIS,
        _PATTERN_MARK_FEATURES,
    )

    assert _PATTERN_MARK_AXIS == 1
    assert _PATTERN_MARK_FEATURES == 4


@pytest.mark.asyncio
async def test_mock_create_axis_plane_pairs_match_the_com_layer() -> None:
    """The mock's plane pairs must match the COM layer's ``_AXIS_PLANE_PAIRS``.

    The two are the same object (imported directly, not copied), so this
    also guards against a future refactor accidentally duplicating and
    diverging the mapping.
    """
    from solidworks_mcp.adapters.solidworks.features import _AXIS_PLANE_PAIRS

    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    for direction, (plane_a, plane_b) in _AXIS_PLANE_PAIRS.items():
        result = await adapter.create_axis(direction)
        assert result.is_success
        assert result.data["planes"] == [plane_a, plane_b]


# ---- Branches previously reached only by the live suite ----------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "impl", "args"),
    [
        ("delete_feature", "_delete_feature_impl", ("Fillet1",)),
        ("suppress_feature", "_suppress_feature_impl", ("Fillet1", False)),
        ("rename_feature", "_rename_feature_impl", ("Fillet1", "EdgeRound")),
        ("undo", "_undo_impl", (2,)),
        ("create_reference_plane", "_create_reference_plane_impl", ("Top Plane",)),
        ("create_axis", "_create_axis_impl", ("z",)),
        (
            "create_reference_point",
            "_create_reference_point_impl",
            ("face_center", 1.0, 2.0, 3.0),
        ),
    ],
)
async def test_mixin_methods_delegate_to_their_impl(
    monkeypatch, method: str, impl: str, args: tuple
) -> None:
    calls: list[tuple] = []
    sentinel = AdapterResult(status=AdapterResultStatus.SUCCESS, data={"ok": method})
    monkeypatch.setattr(features, impl, lambda *a: calls.append(a[1:]) or sentinel)
    adapter = _build_adapter(monkeypatch)

    result = await getattr(adapter, method)(*args)

    assert result is sentinel
    assert calls[0][: len(args)] == args


class TestMirrorAndPatternVolumeOutcomes:
    """The wrappers pass impl failures through and report the volume rise."""

    @staticmethod
    def _volumes(*values: float) -> AsyncMock:
        return AsyncMock(
            side_effect=[
                AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data=SimpleNamespace(volume=v),
                )
                for v in values
            ]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "impl", "args"),
        [
            ("pattern_circular", "_pattern_circular_impl", (["Cut1"], "Axis1", 4)),
            ("mirror_feature", "_mirror_feature_impl", (["Boss1"], "Right Plane")),
        ],
    )
    async def test_impl_failure_is_returned_unchanged(
        self, monkeypatch, method, impl, args
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.get_mass_properties = self._volumes(100.0)
        failure = AdapterResult(status=AdapterResultStatus.ERROR, error="no axis")
        monkeypatch.setattr(features, impl, lambda *_a: failure)

        assert await getattr(adapter, method)(*args) is failure

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "impl", "args"),
        [
            ("pattern_circular", "_pattern_circular_impl", (["Cut1"], "Axis1", 4)),
            ("mirror_feature", "_mirror_feature_impl", (["Boss1"], "Right Plane")),
        ],
    )
    async def test_success_reports_volume_before_and_after(
        self, monkeypatch, method, impl, args
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.get_mass_properties = self._volumes(100.0, 250.0)
        monkeypatch.setattr(
            features,
            impl,
            lambda *_a: AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data={"name": "Feature9"},
                execution_time=0.5,
            ),
        )

        result = await getattr(adapter, method)(*args)

        assert result.is_success
        assert result.data == {
            "name": "Feature9",
            "volume_before": 100.0,
            "volume_after": 250.0,
            "volume_ratio": 2.5,
        }
        assert result.execution_time == 0.5


def test_sweep_prefers_the_last_created_sketch_as_profile() -> None:
    """A helix base circle precedes the profile; the tracked sketch wins."""
    from solidworks_mcp.adapters.base import SweepParameters

    selected: list[str] = []

    def by_name(name: str):
        return SimpleNamespace(
            Select2=lambda _append, _mark: selected.append(name) or True
        )

    adapter = _FakeFeatureAdapter()
    adapter._last_sketch_name = "Base"
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(InsertProtrusionSwept4=lambda *_a: None),
        ClearSelection2=lambda _a: True,
        FirstFeature=_tree("Base", "Later", "Path1"),
        FeatureByName=by_name,
    )

    features._create_sweep_impl(adapter, SweepParameters(path="Path1"))

    assert selected[0] == "Base"


@pytest.mark.parametrize(
    ("tracked", "expected"),
    [
        (None, "no create_sketch/exit_sketch call has run this session"),
        ("Sketch9", "the last create_sketch call returned 'Sketch9'"),
    ],
)
def test_cut_extrude_without_a_usable_sketch_explains_why(
    tracked: str | None, expected: str
) -> None:
    adapter = _FakeFeatureAdapter()
    adapter._last_sketch_name = tracked
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(),
        ClearSelection2=lambda *_a: True,
        FirstFeature=_fake_sketch_feature("Sketch1"),
    )

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=5.0))

    assert result.is_error
    assert expected in (result.error or "")
    assert "Sketches available to cut from: Sketch1" in (result.error or "")


def test_cut_extrude_on_sw_2026_uses_the_27_input_signature() -> None:
    calls: list[tuple] = []
    adapter = _versioned_adapter("34.1.0")
    adapter.currentModel = SimpleNamespace(
        FeatureManager=SimpleNamespace(
            FeatureCut4=lambda *args: (
                calls.append(args) or SimpleNamespace(Name="Cut-Extrude1")
            ),
        ),
        ClearSelection2=lambda *_a: True,
        FirstFeature=_fake_sketch_feature("Sketch1"),
        Extension=SimpleNamespace(SelectByID2=lambda *_a, **_k: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=5.0))

    assert result.is_success, result.error
    assert len(calls[0]) == 27


@pytest.mark.parametrize("impl", ["_add_fillet_impl", "_add_chamfer_impl"])
def test_fillet_and_chamfer_pick_coordinate_specs_by_nearest_entity(
    monkeypatch, impl: str
) -> None:
    picks: list[tuple] = []
    monkeypatch.setattr(
        features,
        "_select_edge_by_coord",
        lambda _adapter, x, y, z, append=False, mark=0, entity_type="EDGE": (
            picks.append((x, y, z, append, entity_type)) and False
        ),
    )
    adapter = _FakeFeatureAdapter()
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda _a: True,
        FeatureManager=SimpleNamespace(),
        Extension=SimpleNamespace(),
    )

    result = getattr(features, impl)(adapter, 1.0, ["face:0.01,0.02,0.0"])

    assert picks == [(0.01, 0.02, 0.0, False, "FACE")]
    assert "Failed to select edge: face:0.01,0.02,0.0" in (result.error or "")


def _selectable_feature(**attrs: Any) -> SimpleNamespace:
    return SimpleNamespace(Select2=lambda _append, _mark: True, **attrs)


class TestFeatureTreeEditOutcomes:
    """Delete, suppress, rename and undo: the paths a live run takes."""

    def test_delete_unknown_feature_is_not_found(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None

        result = _delete_feature_impl(adapter, "Ghost1")

        assert "Feature not found: Ghost1" in (result.error or "")

    def test_delete_reports_how_many_features_went(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.side_effect = [_selectable_feature(), None]
        adapter.currentModel.FeatureManager.GetFeatureCount.side_effect = [7, 5]

        result = _delete_feature_impl(adapter, "Boss-Extrude1@Part1")

        assert result.data == {
            "deleted": "Boss-Extrude1@Part1",
            "features_before": 7,
            "features_after": 5,
            "features_removed": 2,
        }

    def test_suppress_reports_the_read_back_state(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.side_effect = [
            _selectable_feature(IsSuppressed=False),
            SimpleNamespace(IsSuppressed=True),
        ]

        result = _suppress_feature_impl(adapter, "Fillet1", True)

        assert result.is_success, result.error
        assert result.data["feature"] == "Fillet1"
        assert result.data["requested"] is True
        assert result.data["suppressed"] is True

    def test_rename_refuses_an_empty_name(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _rename_feature_impl(adapter, "Fillet1", " @Part1")
        assert result.error == "new_name must not be empty"

    def test_rename_unknown_feature_is_not_found(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = None
        result = _rename_feature_impl(adapter, "Ghost1", "Other")
        assert "Feature not found: Ghost1" in (result.error or "")

    def test_rename_to_the_same_name_changes_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(
            Name="Fillet1"
        )

        result = _rename_feature_impl(adapter, "Fillet1@Part1", "Fillet1")

        assert result.data == {
            "renamed": False,
            "old_name": "Fillet1",
            "new_name": "Fillet1",
            "reason": "old and new names are the same",
        }

    def test_rename_onto_an_existing_name_is_refused(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = SimpleNamespace(Name="x")

        result = _rename_feature_impl(adapter, "Fillet1", "Fillet2")

        assert "a feature with that name already exists" in (result.error or "")

    def test_rename_that_does_not_take_is_an_error(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        feature = SimpleNamespace(Name="Fillet1")
        # Source found, no clash, and nothing resolves by the new name after.
        adapter.currentModel.FeatureByName.side_effect = [feature, None, None]

        result = _rename_feature_impl(adapter, "Fillet1", "EdgeRound")

        assert "the call did not take" in (result.error or "")

    def test_rename_reports_the_name_solidworks_now_shows(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        feature = SimpleNamespace(Name="Fillet1")
        adapter.currentModel.FeatureByName.side_effect = [
            feature,
            None,
            SimpleNamespace(Name="EdgeRound"),
        ]

        result = _rename_feature_impl(adapter, "Fillet1", "EdgeRound@Part1")

        assert result.data == {
            "renamed": True,
            "old_name": "Fillet1",
            "new_name": "EdgeRound",
        }
        assert feature.Name == "EdgeRound"

    @pytest.mark.parametrize(
        ("counts", "changed"), [([6, 5], True), ([6, 6], False), ([None, 5], None)]
    )
    def test_undo_reports_whether_the_tree_changed(
        self, monkeypatch, counts, changed
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureManager.GetFeatureCount.side_effect = counts

        result = _undo_impl(adapter, 0)

        assert result.data["requested_steps"] == 1
        assert result.data["tree_changed"] is changed


class TestReferenceGeometryOutcomes:
    """Reference plane, axis and point: refusals and successes."""

    def test_angled_plane_is_refused(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _create_reference_plane_impl(adapter, "Top Plane", 0.0, 30.0, False)
        assert "does not support 'angle' yet" in (result.error or "")

    def test_plane_without_offset_is_refused(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _create_reference_plane_impl(adapter, "Top Plane", 0.0, 0.0, False)
        assert result.is_error
        assert "offset" in (result.error or "")

    def test_unknown_axis_reference_lists_the_choices(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _create_axis_impl(adapter, "w")
        assert "Unknown axis reference 'w'" in (result.error or "")

    def test_axis_reports_its_planes(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.FeatureByName.return_value = _selectable_feature()
        adapter.currentModel.FeatureManager.GetFeatureCount.side_effect = [5, 6]

        result = _create_axis_impl(adapter, "-Z")

        assert result.data["reference"] == "z"
        assert len(result.data["planes"]) == 2
        assert result.data["features_before"] == 5
        assert result.data["features_after"] == 6

    def test_unknown_point_mode_is_refused(self) -> None:
        result = features._create_reference_point_impl(
            _point_adapter(), "vertex", 0, 0, 0, None, None
        )
        assert result.error == (
            "Unknown mode 'vertex'. Use 'along_curve' or 'face_center'."
        )

    @pytest.mark.parametrize(("distance", "percent"), [(None, None), (5.0, 50.0)])
    def test_along_curve_needs_exactly_one_of_distance_or_percent(
        self, distance, percent
    ) -> None:
        result = features._create_reference_point_impl(
            _point_adapter(), "along_curve", 0, 0, 0, distance, percent
        )
        assert result.error == "along_curve needs exactly one of distance or percent"

    @pytest.mark.parametrize(
        ("mode", "percent", "expected_percent"),
        [("along_curve", 25.0, 25.0), ("face_center", None, None)],
    )
    def test_point_is_created(self, mode, percent, expected_percent) -> None:
        result = features._create_reference_point_impl(
            _point_adapter(), mode, 1.0, 2.0, 3.0, None, percent
        )

        assert result.is_success, result.error
        assert result.data["mode"] == mode
        assert result.data["at_mm"] == [1.0, 2.0, 3.0]
        assert result.data["percent"] == expected_percent
        assert result.data["features_before"] == 5
        assert result.data["features_after"] == 6


class TestMirrorAndPatternImplOutcomes:
    """Mirror and circular pattern: argument refusals and successes."""

    @pytest.mark.parametrize(
        ("features_arg", "plane", "error"),
        [
            ([], "Right Plane", "requires at least one body or feature name"),
            (["Boss1"], "", "requires a mirror plane name"),
        ],
    )
    def test_mirror_argument_refusals(
        self, monkeypatch, features_arg, plane, error
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _mirror_feature_impl(adapter, features_arg, plane, True, False)
        assert error in (result.error or "")

    def test_mirror_body_that_cannot_be_selected_is_named(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.Extension.SelectByID2.return_value = False
        adapter.currentModel.FeatureByName.return_value = None

        result = _mirror_feature_impl(adapter, ["Body9"], "Right Plane", True, True)

        assert "Failed to select body to mirror: Body9" in (result.error or "")

    def test_mirror_bodies_selects_solid_bodies_and_reports_the_feature(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.Extension.SelectByID2.return_value = True
        adapter.currentModel.FeatureByName.return_value = _selectable_feature()
        adapter.currentModel.FeatureManager.InsertMirrorFeature.return_value = (
            SimpleNamespace(Name="Mirror1")
        )

        result = _mirror_feature_impl(adapter, ["Body1"], "Right Plane", True, True)

        assert result.data == {
            "name": "Mirror1",
            "mirrored": ["Body1"],
            "mirror_plane": "Right Plane",
            "merge": True,
            "mirror_bodies": True,
        }
        first = adapter.currentModel.Extension.SelectByID2.call_args_list[0].args
        assert first[:2] == ("Body1", "SOLIDBODY")

    @pytest.mark.parametrize(
        ("features_arg", "axis", "count", "error"),
        [
            ([], "Axis1", 4, "requires at least one feature name"),
            (["Cut1"], "", 4, "requires an axis name"),
            (["Cut1"], "Axis1", 1, "needs a count of at least 2 (got 1)"),
        ],
    )
    def test_pattern_argument_refusals(
        self, monkeypatch, features_arg, axis, count, error
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = _pattern_circular_impl(adapter, features_arg, axis, count, 360.0, True)
        assert error in (result.error or "")

    def test_pattern_without_a_selectable_axis_says_how_to_make_one(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.Extension.SelectByID2.return_value = False

        result = _pattern_circular_impl(adapter, ["Cut1"], "Axis9", 4, 360.0, True)

        assert "Failed to select axis 'Axis9'" in (result.error or "")
        assert "create_axis" in (result.error or "")

    def test_pattern_reports_the_new_feature(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.Extension.SelectByID2.return_value = True
        manager = adapter.currentModel.FeatureManager
        manager.FeatureCircularPattern5.return_value = SimpleNamespace(
            Name="CirPattern1"
        )

        result = _pattern_circular_impl(adapter, ["Cut1"], "Axis1", 6, 180.0, False)

        assert result.data == {
            "name": "CirPattern1",
            "patterned": ["Cut1"],
            "axis": "Axis1",
            "count": 6,
            "angle": 180.0,
            "equal_spacing": False,
        }
        args = manager.FeatureCircularPattern5.call_args.args
        assert args[0] == 6
        assert args[1] == pytest.approx(math.pi)
