"""Direct branch coverage tests for solidworks_mcp.adapters.solidworks.features."""

from __future__ import annotations

from types import SimpleNamespace

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
        FirstFeature=None,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: False),
    )
    adapter._last_sketch_name = "Sketch2"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(depth=4.0, end_condition="ThroughAll", draft_angle=1.0),
    )

    assert result.status == AdapterResultStatus.ERROR
    assert "FeatureCut4: cut4 failed" in (result.error or "")
    assert "FeatureCut3 modern: cut3 failed" in (result.error or "")
    assert "FeatureCut3 legacy: cut3 failed" in (result.error or "")


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
        FirstFeature=None,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )

    result = features._create_cut_extrude_impl(adapter, ExtrusionParameters(depth=6.0))
    assert result.is_success
    assert result.data.type == "Cut-Extrude"
    assert result.data.name == "Cut-Extrude9"


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
        FirstFeature=None,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(depth=5.0, end_condition="ThroughAll", both_directions=True),
    )
    assert result.is_success
    assert result.data.type == "Cut-Extrude"


def test_create_cut_extrude_raises_when_no_feature_and_no_errors() -> None:
    """Missing cut feature should raise a generic error when no fallback errors exist."""
    # Force all cut methods to return None without errors to hit the final raise.
    adapter = _FakeFeatureAdapter()

    feature_manager = SimpleNamespace(
        FeatureCut4=lambda *args: None,
        FeatureCut3=lambda *args: None,
    )
    adapter.currentModel = SimpleNamespace(
        FeatureManager=feature_manager,
        ClearSelection2=lambda *_args: True,
        FirstFeature=None,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
    )
    adapter._last_sketch_name = "Sketch1"

    result = features._create_cut_extrude_impl(
        adapter,
        ExtrusionParameters(depth=4.0),
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to create cut extrude feature" in (result.error or "")


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
