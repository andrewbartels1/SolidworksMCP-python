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
            SelectByID2=lambda name, *_args, **_kwargs: selected.append(name)
            or True
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
