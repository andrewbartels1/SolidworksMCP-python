"""Direct branch coverage tests for solidworks_mcp.adapters.solidworks.features."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
)
from solidworks_mcp.adapters.solidworks import features


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
