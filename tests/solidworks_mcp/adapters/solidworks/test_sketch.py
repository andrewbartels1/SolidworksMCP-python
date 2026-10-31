"""Direct branch coverage tests for solidworks_mcp.adapters.solidworks.sketch."""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks import sketch
from solidworks_mcp.adapters.solidworks.sketch import SolidWorksSketchMixin


class _FakeSwApp:
    """Minimal swApp stand-in; ActiveDoc proxies the adapter's currentModel."""

    def __init__(self, adapter: _FakeSketchAdapter) -> None:
        self._adapter = adapter

    @property
    def ActiveDoc(self) -> object:
        return self._adapter.currentModel


class _FakeSketchAdapter:
    def __init__(self) -> None:
        self.currentModel = None
        self.currentSketchManager = None
        self.currentSketch = None
        self._sketch_count = 0
        self._last_sketch_name = None
        self._sketch_entities: dict[str, object] = {}
        self._sketch_entity_centers: dict[str, tuple[float, float]] = {}
        self._next_id = 1
        self.constants = {
            "swSmartDimensionDirectionRight": 0,
            "swSmartDimensionDirectionUp": 1,
            "swSmartDimensionDirectionLeft": 2,
            "swSmartDimensionDirectionDown": 3,
        }
        self.swApp = _FakeSwApp(self)

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

    def _reset_sketch_entity_registry(self):
        self._sketch_entities = {}

    def _register_sketch_entity(self, prefix: str, entity: object) -> str:
        entity_id = f"{prefix}_{self._next_id}"
        self._next_id += 1
        self._sketch_entities[entity_id] = entity
        return entity_id

    def _select_sketch_entity(self, entity: object, append: bool) -> bool:
        if hasattr(entity, "Select2"):
            return bool(entity.Select2(append, 0))
        return True

    def _get_attr_or_call(self, obj: object, attr_name: str):
        value = getattr(obj, attr_name)
        return value() if callable(value) else value


def test_create_sketch_requires_active_model() -> None:
    adapter = _FakeSketchAdapter()
    result = sketch._create_sketch_impl(adapter, "Top")
    assert result.status == AdapterResultStatus.ERROR
    assert result.error == "No active model"


def test_create_sketch_selects_feature_plane_and_uses_named_sketch() -> None:
    adapter = _FakeSketchAdapter()
    plane_feature = SimpleNamespace(Select2=lambda _append, _mark: True)
    inserted_sketch = SimpleNamespace(Name="SketchA")
    model = SimpleNamespace(
        FeatureByName=lambda _name: plane_feature,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: False),
        SketchManager=SimpleNamespace(InsertSketch=lambda *args: inserted_sketch),
        GetActiveSketch2=lambda: None,
    )
    adapter.currentModel = model

    result = sketch._create_sketch_impl(adapter, "Front")

    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data == "SketchA"
    assert adapter._last_sketch_name == "SketchA"
    assert adapter._sketch_count == 1


def test_create_sketch_falls_back_to_select_by_id_and_generated_name() -> None:
    adapter = _FakeSketchAdapter()

    insert_true = Mock(side_effect=RuntimeError("signature mismatch"))
    insert_plain = Mock(return_value=None)

    sketch_manager = SimpleNamespace()

    def _insert(*args):
        if args:
            return insert_true(*args)
        return insert_plain()

    sketch_manager.InsertSketch = _insert
    calls = {"n": 0}

    def _feature_by_name(_name):
        calls["n"] += 1
        raise RuntimeError("not found")

    model = SimpleNamespace(
        FeatureByName=_feature_by_name,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: True),
        SketchManager=sketch_manager,
        GetActiveSketch2=lambda: None,
    )
    adapter.currentModel = model

    result = sketch._create_sketch_impl(adapter, "Top")

    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data == "Sketch_1"
    assert adapter._last_sketch_name == "Sketch_1"
    assert calls["n"] >= 1


def test_create_sketch_uses_active_sketch_property_when_insert_returns_falsy() -> None:
    """Regression: InsertSketch's return value can be an empty Sub result.

    When that happens, ISketchManager.ActiveSketch (a real property) must be
    consulted before falling back to the synthetic ``Sketch_N`` name — a
    wrong synthetic name breaks every later ``_last_sketch_name``-based
    lookup, including create_cut_extrude's implicit-sketch reselection.
    """
    adapter = _FakeSketchAdapter()
    plane_feature = SimpleNamespace(Select2=lambda _append, _mark: True)
    real_active_sketch = SimpleNamespace(Name="Sketch4")
    model = SimpleNamespace(
        FeatureByName=lambda _name: plane_feature,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: False),
        SketchManager=SimpleNamespace(
            InsertSketch=lambda *args: None,
            ActiveSketch=real_active_sketch,
        ),
        GetActiveSketch2=lambda: None,
    )
    adapter.currentModel = model

    result = sketch._create_sketch_impl(adapter, "Top")

    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data == "Sketch4"
    assert adapter._last_sketch_name == "Sketch4"


def test_create_sketch_reports_plane_selection_failure() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentModel = SimpleNamespace(
        FeatureByName=lambda _name: None,
        Extension=SimpleNamespace(SelectByID2=lambda *args, **kwargs: False),
        SketchManager=SimpleNamespace(InsertSketch=lambda *_args: None),
        GetActiveSketch2=lambda: None,
    )

    result = sketch._create_sketch_impl(adapter, "Missing")
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to select plane" in (result.error or "")


def test_basic_entity_functions_require_active_sketch() -> None:
    adapter = _FakeSketchAdapter()
    assert (
        sketch._add_line_impl(adapter, 0, 0, 1, 1).status == AdapterResultStatus.ERROR
    )
    assert sketch._add_circle_impl(adapter, 0, 0, 1).status == AdapterResultStatus.ERROR
    assert (
        sketch._add_rectangle_impl(adapter, 0, 0, 1, 1).status
        == AdapterResultStatus.ERROR
    )
    assert (
        sketch._add_arc_impl(adapter, 0, 0, 1, 0, 0, 1).status
        == AdapterResultStatus.ERROR
    )


def test_basic_entity_success_paths_register_entities() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace(
        CreateLine=lambda *args: SimpleNamespace(Name="L"),
        CreateCircleByRadius=lambda *args: SimpleNamespace(Name="C"),
        CreateCornerRectangle=lambda *args: [1, 2, 3, 4],
        CreateArc=lambda *args: SimpleNamespace(Name="A"),
    )

    assert sketch._add_line_impl(adapter, 0, 0, 10, 0).data.startswith("Line_")
    assert sketch._add_circle_impl(adapter, 0, 0, 5).data.startswith("Circle_")
    assert sketch._add_rectangle_impl(adapter, 0, 0, 5, 5).data.startswith("Rectangle_")
    assert sketch._add_arc_impl(adapter, 0, 0, 5, 0, 0, 5).data.startswith("Arc_")


def test_spline_centerline_polygon_and_ellipse_paths() -> None:
    adapter = _FakeSketchAdapter()
    spline_calls: list[tuple[object, bool]] = []

    def _create_spline(points: object, simulate_natural_ends: bool) -> object:
        # Store the raw points argument (a VARIANT on Windows, a list on
        # other platforms) so the assertion below can unwrap it via the
        # ``.value`` attribute when present. The second arg name matches
        # the SolidWorks API parameter ``SimulateNaturalEnds`` (passed
        # as False by add_spline), not an open/closed-spline flag.
        spline_calls.append((points, simulate_natural_ends))
        return object()

    adapter.currentSketchManager = SimpleNamespace(
        CreateSpline2=_create_spline,
        CreateCenterLine=lambda *args: object(),
        CreatePolygon=lambda *args: object(),
        CreateEllipse=lambda *args: object(),
    )

    spline_ok = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 1.0}]
    )
    assert spline_ok.is_success
    assert spline_ok.data.startswith("Spline_")
    # CreateSpline2 must be called with the SW-spec 2-arg signature:
    # (flattened XYZ doubles, simulateNaturalEnds=False). On Windows the
    # impl wraps the doubles in VARIANT(VT_ARRAY|VT_R8) so pywin32 marshals
    # them as a single SAFEARRAY argument instead of unpacking the list.
    # On non-Windows CI a bare list is passed through.
    assert len(spline_calls) == 1
    points_arg, simulate_natural_ends = spline_calls[0]
    assert simulate_natural_ends is False
    flat_points = getattr(points_arg, "value", points_arg)
    assert list(flat_points) == [0.0, 0.0, 0.0, 0.002, 0.001, 0.0]

    center_ok = sketch._add_centerline_impl(adapter, 0, 0, 10, 0)
    polygon_ok = sketch._add_polygon_impl(adapter, 0, 0, 10, 6)
    ellipse_ok = sketch._add_ellipse_impl(adapter, 0, 0, 10, 4)
    assert center_ok.is_success and center_ok.data.startswith("Centerline_")
    assert polygon_ok.is_success and polygon_ok.data.startswith("Polygon_")
    assert ellipse_ok.is_success and ellipse_ok.data.startswith("Ellipse_")


def test_spline_error_when_create_returns_none() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace(CreateSpline2=lambda *args: None)
    result = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to create spline" in (result.error or "")


def test_spline_error_when_no_sketch_manager() -> None:
    adapter = _FakeSketchAdapter()
    result = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "No active sketch" in (result.error or "")


def test_spline_error_when_too_few_points() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace(CreateSpline2=lambda *args: object())
    result = sketch._add_spline_impl(adapter, [{"x": 0.0, "y": 0.0}])
    assert result.status == AdapterResultStatus.ERROR
    assert "at least 2 points" in (result.error or "")


def test_spline_uses_segments_fallback_when_current_sketch_present() -> None:
    """When currentSketch is set and GetSketchSegments returns segments, the last
    segment is registered instead of the raw spline IDispatch (sketch.py:706)."""
    adapter = _FakeSketchAdapter()
    sentinel_segment = object()

    adapter.currentSketchManager = SimpleNamespace(
        CreateSpline2=lambda *args: object()  # returns a truthy spline object
    )
    fake_sketch = SimpleNamespace(
        GetSketchSegments=lambda: [sentinel_segment],
    )
    adapter.currentSketch = fake_sketch

    result = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
    )
    assert result.is_success
    # The registered entity must be the sentinel segment, not the raw spline.
    entity_id = result.data
    assert entity_id.startswith("Spline_")
    assert adapter._sketch_entities[entity_id] is sentinel_segment


def _make_pattern_adapter() -> tuple[_FakeSketchAdapter, Mock, Mock, Mock, Mock]:
    """Build a fake adapter wired for the real sketch_linear_pattern impl.

    The impl resolves entity IDs against ``adapter._sketch_entities``,
    calls ``adapter.currentModel.ClearSelection2`` before/after,
    invokes ``adapter.currentModel.SelectionManager.CreateSelectData``
    to obtain an ``ISelectData`` with the mark, calls ``Select4(True,
    select_data)`` on each entity, and finally calls
    ``adapter.currentSketchManager.CreateLinearSketchStepAndRepeat(...)``.
    The returned mocks let assertions verify each call.
    """
    adapter = _FakeSketchAdapter()
    seed_entity = Mock()
    seed_entity.Select4 = Mock(return_value=True)
    adapter._sketch_entities = {"Line_1": seed_entity}

    create_pattern = Mock(return_value=True)
    sketch_manager = Mock()
    sketch_manager.CreateLinearSketchStepAndRepeat = create_pattern
    adapter.currentSketchManager = sketch_manager

    select_data = Mock()
    selection_mgr = Mock()
    selection_mgr.CreateSelectData = Mock(return_value=select_data)

    clear_selection = Mock(return_value=True)
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=clear_selection,
        SelectionManager=selection_mgr,
    )
    return adapter, create_pattern, clear_selection, seed_entity, selection_mgr


def test_sketch_linear_pattern_calls_com_with_converted_args() -> None:
    """Real ``_sketch_linear_pattern_impl`` selects the seed entities and
    calls ``CreateLinearSketchStepAndRepeat`` with mm-to-m and
    direction-vector-to-radian conversions.
    """
    adapter, create_pattern, clear_selection, seed_entity, _ = _make_pattern_adapter()

    result = sketch._sketch_linear_pattern_impl(adapter, ["Line_1"], 1, 0, 5.0, 3)

    assert result.is_success
    assert result.data.startswith("LinearPattern_3x5.0_")
    # ClearSelection2 is called twice (before + finally after).
    assert clear_selection.call_count == 2
    # The seed entity was selected with the mark-0 select data.
    assert seed_entity.Select4.call_count == 1
    create_pattern.assert_called_once()
    call_args = create_pattern.call_args.args
    # Signature: NumX, NumY, SpacingX(m), SpacingY, AngleX(rad), AngleY,
    # DeleteInstances, XSpacingDim, YSpacingDim, AngleDim,
    # CreateNumOfInstancesDimInXDir, CreateNumOfInstancesDimInYDir
    assert call_args[0] == 3  # NumX == count
    assert call_args[1] == 1  # NumY == 1 (single row)
    assert call_args[2] == 5.0 / 1000.0  # SpacingX in metres
    # AngleX == atan2(0, 1) == 0 for direction (1, 0)
    assert call_args[4] == 0.0


def test_sketch_linear_pattern_validates_inputs() -> None:
    adapter, _, _, _, _ = _make_pattern_adapter()

    assert (
        sketch._sketch_linear_pattern_impl(adapter, [], 1, 0, 5.0, 3).status
        == AdapterResultStatus.ERROR
    )
    assert (
        sketch._sketch_linear_pattern_impl(adapter, ["Line_1"], 1, 0, 5.0, 1).status
        == AdapterResultStatus.ERROR
    )
    assert (
        sketch._sketch_linear_pattern_impl(adapter, ["Line_1"], 1, 0, 0.0, 3).status
        == AdapterResultStatus.ERROR
    )
    assert (
        sketch._sketch_linear_pattern_impl(adapter, ["Line_1"], 0, 0, 5.0, 3).status
        == AdapterResultStatus.ERROR
    )


def test_sketch_linear_pattern_unknown_entity_does_not_mutate_selection() -> None:
    """Validating IDs happens before ``ClearSelection2`` so an unknown ID
    does not leave SW with a half-built selection state."""
    adapter, _, clear_selection, _, _ = _make_pattern_adapter()

    result = sketch._sketch_linear_pattern_impl(adapter, ["Line_NOPE"], 1, 0, 5.0, 3)

    assert result.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity 'Line_NOPE'" in (result.error or "")
    clear_selection.assert_not_called()


def test_sketch_linear_pattern_clears_selection_on_com_failure() -> None:
    """``CreateLinearSketchStepAndRepeat`` returning ``False`` must still
    leave selection state cleaned up (try/finally invariant)."""
    adapter, create_pattern, clear_selection, _, _ = _make_pattern_adapter()
    create_pattern.return_value = False

    result = sketch._sketch_linear_pattern_impl(adapter, ["Line_1"], 1, 0, 5.0, 3)

    assert result.status == AdapterResultStatus.ERROR
    # ClearSelection2 must run both before selecting and after the failure.
    assert clear_selection.call_count == 2


def _make_offset_adapter() -> tuple[_FakeSketchAdapter, Mock, Mock]:
    """Build a fake adapter wired for the real sketch_offset impl.

    Mirrors ``_make_pattern_adapter`` — entity registered, SketchOffset2
    on the sketch manager, ClearSelection2 + CreateSelectData on the
    model. Returns the adapter + key mocks for assertions.
    """
    adapter = _FakeSketchAdapter()
    seed_entity = Mock()
    seed_entity.Select4 = Mock(return_value=True)
    adapter._sketch_entities = {"Line_1": seed_entity}

    sketch_offset2 = Mock(return_value=True)
    sketch_manager = Mock()
    sketch_manager.SketchOffset2 = sketch_offset2
    adapter.currentSketchManager = sketch_manager

    select_data = Mock()
    selection_mgr = Mock()
    selection_mgr.CreateSelectData = Mock(return_value=select_data)

    clear_selection = Mock(return_value=True)
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=clear_selection,
        SelectionManager=selection_mgr,
    )
    return adapter, sketch_offset2, clear_selection


def test_sketch_offset_outward_calls_com_with_positive_offset() -> None:
    """``reverse_direction=False`` passes a positive metre value to
    ``SketchOffset2`` and synthesises an ``_outward_`` ID."""
    adapter, sketch_offset2, clear_selection = _make_offset_adapter()

    result = sketch._sketch_offset_impl(adapter, ["Line_1"], 5.0, False)

    assert result.is_success
    assert "_outward_" in result.data
    sketch_offset2.assert_called_once()
    args = sketch_offset2.call_args.args
    assert args[0] == 5.0 / 1000.0  # mm → m
    # ClearSelection2 runs once before selecting and once in the finally.
    assert clear_selection.call_count == 2


def test_sketch_offset_inward_flips_sign() -> None:
    """``reverse_direction=True`` negates ``Offset`` per SketchOffset2 docs."""
    adapter, sketch_offset2, _ = _make_offset_adapter()

    result = sketch._sketch_offset_impl(adapter, ["Line_1"], 2.5, True)

    assert result.is_success
    assert "_inward_" in result.data
    args = sketch_offset2.call_args.args
    assert args[0] == -2.5 / 1000.0


def test_sketch_offset_unknown_entity_does_not_mutate_selection() -> None:
    adapter, _, clear_selection = _make_offset_adapter()

    result = sketch._sketch_offset_impl(adapter, ["Line_NOPE"], 5.0, False)

    assert result.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity 'Line_NOPE'" in (result.error or "")
    clear_selection.assert_not_called()


def test_sketch_offset_clears_selection_on_com_failure() -> None:
    """``SketchOffset2`` returning False must still leave selection
    state cleaned up (try/finally invariant)."""
    adapter, sketch_offset2, clear_selection = _make_offset_adapter()
    sketch_offset2.return_value = False

    result = sketch._sketch_offset_impl(adapter, ["Line_1"], 5.0, False)

    assert result.status == AdapterResultStatus.ERROR
    assert clear_selection.call_count == 2


def _make_constraint_adapter(
    *,
    add_relation_raises: Exception | None = None,
    add_relation_returns: object = "sentinel-relation-obj",
    no_active_sketch: bool = False,
) -> tuple[_FakeSketchAdapter, Mock, Mock]:
    """Build a fake adapter wired for the constraint code path.

    The rewritten impl uses
    ``ISketchRelationManager.AddRelation([entities], relation_type_enum)``
    so the fake exposes ``currentModel.GetActiveSketch2().RelationManager``.
    """
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    line1 = SimpleNamespace()
    line2 = SimpleNamespace()
    centerline = SimpleNamespace()
    adapter._sketch_entities = {
        "Line_1": line1,
        "Line_2": line2,
        "Centerline_3": centerline,
    }

    def _add_rel(_entities, _rt):
        if add_relation_raises is not None:
            raise add_relation_raises
        return add_relation_returns

    add_relation = Mock(side_effect=_add_rel)
    relmgr = SimpleNamespace(AddRelation=add_relation)
    sketch_obj = SimpleNamespace(RelationManager=relmgr)
    adapter.currentModel = SimpleNamespace(
        GetActiveSketch2=lambda: None if no_active_sketch else sketch_obj,
    )
    return adapter, add_relation, sketch_obj


def test_add_sketch_constraint_requires_active_sketch() -> None:
    adapter = _FakeSketchAdapter()
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", None, "parallel")
    assert result.status == AdapterResultStatus.ERROR
    assert "No active sketch" in (result.error or "")


def test_add_sketch_constraint_requires_active_model() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", None, "parallel")
    assert result.status == AdapterResultStatus.ERROR
    assert "No active model" in (result.error or "")


def test_add_sketch_constraint_unsupported_relation_type() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", "Line_2", "unknown")
    assert result.status == AdapterResultStatus.ERROR
    assert "Unsupported relation type 'unknown'" in (result.error or "")


def test_add_sketch_constraint_unknown_entity_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(adapter, "L99", None, "horizontal")
    assert result.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity 'L99'" in (result.error or "")


def test_add_sketch_constraint_two_entity_happy_path() -> None:
    constraint_obj = SimpleNamespace(Name="Perp1")
    adapter, add_relation, _sk = _make_constraint_adapter(
        add_relation_returns=constraint_obj
    )

    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "perpendicular"
    )

    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data.startswith("Constraint_")
    assert adapter._sketch_entities[result.data] is constraint_obj
    # AddRelation is called with the VARIANT entity array and PERPENDICULAR=8
    assert add_relation.call_count == 1
    _ents_arg, rt_arg = add_relation.call_args.args
    assert rt_arg == 8


def test_add_sketch_constraint_single_entity_horizontal() -> None:
    adapter, add_relation, _sk = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", None, "Horizontal")
    assert result.status == AdapterResultStatus.SUCCESS
    _ents_arg, rt_arg = add_relation.call_args.args
    assert rt_arg == 4  # swConstraintType_HORIZONTAL


def test_add_sketch_constraint_sw_rejection_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter(
        add_relation_raises=RuntimeError("incompatible geometry"),
    )
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", "Line_2", "parallel")
    assert result.status == AdapterResultStatus.ERROR
    msg = result.error or ""
    assert "rejected" in msg and "parallel" in msg
    assert "Line_1" in msg and "Line_2" in msg
    assert "incompatible geometry" in msg


def test_add_sketch_constraint_no_active_sketch_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter(no_active_sketch=True)
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", None, "fix")
    assert result.status == AdapterResultStatus.ERROR
    assert "No active sketch" in (result.error or "")


def test_add_sketch_constraint_add_relation_returns_none_is_error() -> None:
    adapter, *_ = _make_constraint_adapter(add_relation_returns=None)
    result = sketch._add_sketch_constraint_impl(adapter, "Line_1", None, "fix")
    assert result.status == AdapterResultStatus.ERROR
    assert "rejected" in (result.error or "")


def test_add_sketch_constraint_symmetric_happy_path() -> None:
    constraint_obj = SimpleNamespace(Name="Sym1")
    adapter, add_relation, _sk = _make_constraint_adapter(
        add_relation_returns=constraint_obj
    )

    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "symmetric", "Centerline_3"
    )

    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data.startswith("Constraint_")
    assert adapter._sketch_entities[result.data] is constraint_obj
    ents_arg, rt_arg = add_relation.call_args.args
    assert rt_arg == 11  # swConstraintType_SYMMETRIC
    # Three-element entity list, in order: entity1, entity2, entity3.
    # When pywin32 is available (real Windows runs) the impl wraps
    # entities in a VARIANT(value=[...]); when it is not (Linux CI) the
    # non-Windows branch passes the entities through as a plain list.
    entities_seq = getattr(ents_arg, "value", ents_arg)
    assert len(entities_seq) == 3


def test_add_sketch_constraint_symmetric_missing_entity3_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "symmetric", None
    )
    assert result.status == AdapterResultStatus.ERROR
    msg = result.error or ""
    assert "symmetric" in msg
    assert "entity3" in msg


def test_add_sketch_constraint_symmetric_missing_entity2_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", None, "symmetric", "Centerline_3"
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "entity2" in (result.error or "")


def test_add_sketch_constraint_entity3_rejected_for_non_symmetric() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "perpendicular", "Centerline_3"
    )
    assert result.status == AdapterResultStatus.ERROR
    msg = result.error or ""
    assert "does not accept entity3" in msg
    assert "perpendicular" in msg


def test_add_sketch_constraint_unknown_entity3_returns_error() -> None:
    adapter, *_ = _make_constraint_adapter()
    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "symmetric", "CL_99"
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity 'CL_99'" in (result.error or "")


def test_exit_sketch_no_model_returns_warning() -> None:
    """Without a ``currentModel`` nothing can be in sketch-edit mode; return
    WARNING so defensive-cleanup callers don't see spurious errors."""
    adapter = _FakeSketchAdapter()
    result = sketch._exit_sketch_impl(adapter)
    assert result.status == AdapterResultStatus.WARNING
    assert "No active sketch to exit" in (result.error or "")


def test_exit_sketch_warning_and_success_paths() -> None:
    """Cover both branches of the SW-state-aware exit:

    - SW reports no active sketch AND adapter has no manager -> WARNING
      (already-exited is not a failure).
    - SW reports an active sketch -> InsertSketch toggled and adapter
      state cleared.
    """
    adapter = _FakeSketchAdapter()
    # Model present but nothing is in sketch-edit mode anywhere.
    inactive_manager = SimpleNamespace(InsertSketch=Mock())
    adapter.currentModel = SimpleNamespace(
        GetActiveSketch2=lambda: None,
        SketchManager=inactive_manager,
    )
    warning = sketch._exit_sketch_impl(adapter)
    assert warning.status == AdapterResultStatus.WARNING
    inactive_manager.InsertSketch.assert_not_called()

    # Adapter-side state populated (the original-fixture happy path).
    active_manager = SimpleNamespace(InsertSketch=Mock())
    adapter.currentSketchManager = active_manager
    adapter.currentSketch = object()
    adapter._sketch_entities = {"Line_1": object()}

    success = sketch._exit_sketch_impl(adapter)
    assert success.status == AdapterResultStatus.SUCCESS
    assert adapter.currentSketch is None
    assert adapter.currentSketchManager is None
    assert adapter._sketch_entities == {}
    active_manager.InsertSketch.assert_called_once_with(True)


def test_exit_sketch_sw_active_but_adapter_state_empty() -> None:
    """Regression for the bug: SW has a sketch open (e.g. from a prior
    aborted run) but ``adapter.currentSketchManager`` is ``None``.

    The fix must still toggle SW out of sketch-edit mode using
    ``currentModel.SketchManager`` rather than reporting "no active
    sketch" — otherwise every subsequent ``create_sketch("Front")``
    fails with ``Failed to select plane: Front Plane`` because SW
    cannot open a new sketch while one is already active.
    """
    adapter = _FakeSketchAdapter()
    sketch_manager = SimpleNamespace(InsertSketch=Mock())
    sw_active_sketch = object()
    adapter.currentModel = SimpleNamespace(
        GetActiveSketch2=lambda: sw_active_sketch,
        SketchManager=sketch_manager,
    )
    assert adapter.currentSketchManager is None  # the divergent state

    result = sketch._exit_sketch_impl(adapter)
    assert result.status == AdapterResultStatus.SUCCESS, f"unexpected: {result.error}"
    sketch_manager.InsertSketch.assert_called_once_with(True)
    # Adapter state stays clean afterwards.
    assert adapter.currentSketchManager is None
    assert adapter.currentSketch is None
    assert adapter._sketch_entities == {}


def test_add_sketch_dimension_linear_success_and_fallback_value_setters() -> None:
    adapter = _FakeSketchAdapter()
    primary_entity = SimpleNamespace(Select2=lambda append, _mark: True)
    adapter._sketch_entities = {"Line_1": primary_entity}
    adapter.currentSketchManager = object()
    adapter._single_line_dimension_placement = lambda _entity: (0.01, 0.02, 0.0, 1)

    dim_obj = SimpleNamespace(
        SetSystemValue3=lambda *_args: None,
        SetSystemValue2=lambda *_args: None,
        SystemValue=None,
    )
    display_dim = SimpleNamespace(GetDimension2=lambda *_args: dim_obj)
    model = SimpleNamespace(
        ClearSelection2=lambda *_args: True,
        Extension=SimpleNamespace(AddDimension=lambda *_args: display_dim),
    )
    adapter.currentModel = model

    result = sketch._add_sketch_dimension_impl(adapter, "Line_1", None, "linear", 25.0)
    assert result.status == AdapterResultStatus.SUCCESS
    assert result.data.startswith("Dimension_")
    assert dim_obj.SystemValue == 0.025


def test_add_sketch_dimension_radial_diameter_and_selection_errors() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    primary_entity = SimpleNamespace(Select2=lambda append, _mark: not append)
    secondary_entity = SimpleNamespace(Select2=lambda _append, _mark: False)
    adapter._sketch_entities = {"Arc_1": primary_entity, "Line_2": secondary_entity}
    adapter._single_line_dimension_placement = lambda _entity: (0.01, 0.02, 0.0, 1)
    adapter._angular_dimension_placement = lambda _e1, _e2: (0.01, 0.01, 0.0, 1)
    adapter._shared_segment_vertex = lambda _e1, _e2: None

    model = SimpleNamespace(
        ClearSelection2=lambda *_args: True,
        AddRadialDimension2=lambda *_args: SimpleNamespace(
            GetDimension2=lambda *_a: SimpleNamespace(SetSystemValue3=lambda *_b: True)
        ),
        AddDiameterDimension2=lambda *_args: SimpleNamespace(
            GetDimension2=lambda *_a: SimpleNamespace(SetSystemValue3=lambda *_b: True)
        ),
        Extension=SimpleNamespace(
            AddDimension=lambda *_args: SimpleNamespace(
                GetDimension2=lambda *_a: SimpleNamespace(
                    SetSystemValue3=lambda *_b: True
                )
            )
        ),
    )
    adapter.currentModel = model

    radial = sketch._add_sketch_dimension_impl(adapter, "Arc_1", None, "radial", 3.0)
    diameter = sketch._add_sketch_dimension_impl(
        adapter, "Arc_1", None, "diameter", 6.0
    )
    angular = sketch._add_sketch_dimension_impl(
        adapter, "Arc_1", "Line_2", "angular", 45.0
    )
    bad_secondary = sketch._add_sketch_dimension_impl(
        adapter, "Arc_1", "Line_2", "linear", 5.0
    )

    assert radial.is_success
    assert diameter.is_success
    # No shared vertex -> no angular dimension can be placed: an error, not a
    # silent success registering nothing (was a bug before the fix).
    assert angular.status == AdapterResultStatus.ERROR
    assert "failed to create sketch dimension" in (angular.error or "")
    assert bad_secondary.status == AdapterResultStatus.ERROR
    assert "Failed to select secondary entity" in (bad_secondary.error or "")


def test_add_sketch_dimension_missing_entities_and_placement_errors() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda *_a: True,
        Extension=SimpleNamespace(AddDimension=lambda *_a: None),
    )
    adapter._single_line_dimension_placement = lambda _entity: None
    adapter._sketch_entities = {}

    missing = sketch._add_sketch_dimension_impl(adapter, "Line_X", None, "linear", 10.0)
    assert missing.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity 'Line_X'" in (missing.error or "")

    adapter._sketch_entities = {"Line_1": object()}
    no_placement = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", None, "linear", 10.0
    )
    assert no_placement.status == AdapterResultStatus.ERROR
    assert "Unsupported or ambiguous dimension placement" in (no_placement.error or "")


def test_add_sketch_dimension_angular_loop_tries_multiple_directions() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()

    class _Vertex:
        def __init__(self, ok: bool) -> None:
            self._ok = ok

        def Select2(self, _append, _mark):
            return self._ok

    entity1 = SimpleNamespace(Select2=lambda _append, _mark: True)
    entity2 = SimpleNamespace(Select2=lambda _append, _mark: True)
    adapter._sketch_entities = {"L1": entity1, "L2": entity2}
    adapter._angular_dimension_placement = lambda _e1, _e2: (0.02, 0.02, 0.0, 0)
    adapter._shared_segment_vertex = lambda _e1, _e2: (
        object(),
        _Vertex(True),
        _Vertex(True),
    )

    add_dim_calls = {"n": 0}

    def _add_dimension(_x, _y, _z, direction):
        add_dim_calls["n"] += 1
        if direction == 0:
            return None
        return SimpleNamespace(
            GetDimension2=lambda *_a: SimpleNamespace(SetSystemValue3=lambda *_b: True)
        )

    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda *_args: True,
        Extension=SimpleNamespace(AddDimension=_add_dimension),
    )

    result = sketch._add_sketch_dimension_impl(adapter, "L1", "L2", "angular", 15.0)
    assert result.is_success
    assert add_dim_calls["n"] >= 2


def test_add_sketch_dimension_returns_generated_id_when_model_missing() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    adapter.currentModel = None
    adapter._sketch_entities = {"Line_1": object()}
    adapter._single_line_dimension_placement = lambda _entity: (0.0, 0.0, 0.0, 0)

    result = sketch._add_sketch_dimension_impl(adapter, "Line_1", None, "linear", 12.0)
    assert result.is_success
    assert result.data.startswith("Dimension_")


def test_check_sketch_fully_defined_variants() -> None:
    adapter = _FakeSketchAdapter()

    no_model = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert no_model.status == AdapterResultStatus.ERROR

    adapter.currentModel = SimpleNamespace(FeatureByName=lambda _name: None)
    missing_named = sketch._check_sketch_fully_defined_impl(adapter, "Sketch9")
    assert missing_named.status == AdapterResultStatus.ERROR
    assert "Sketch not found" in (missing_named.error or "")

    sketch_obj = SimpleNamespace(IsFullyDefined=lambda: True)
    adapter.currentSketch = sketch_obj
    fully_defined = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert fully_defined.is_success
    assert fully_defined.data["is_fully_defined"] is True
    assert fully_defined.data["definition_state"] == "fully_defined"

    under_obj = SimpleNamespace(IsUnderDefined=lambda: True)
    adapter.currentSketch = under_obj
    under_defined = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert under_defined.is_success
    assert under_defined.data["is_fully_defined"] is False

    unknown_obj = SimpleNamespace(GetStatus=lambda: "not-a-number")
    adapter.currentSketch = unknown_obj
    unknown = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert unknown.is_success
    assert unknown.data["definition_state"] == "unknown"


def test_check_sketch_fully_defined_feature_fallback_and_over_defined_count() -> None:
    adapter = _FakeSketchAdapter()

    sketch_specific = SimpleNamespace(GetOverDefinedCount=lambda: 1)
    feature_obj = SimpleNamespace(
        Name="SketchFromFeature", GetSpecificFeature2=lambda: sketch_specific
    )
    adapter.currentSketch = None
    adapter._last_sketch_name = "SketchFromFeature"
    adapter.currentModel = SimpleNamespace(
        GetActiveSketch2=lambda: None,
        FeatureByName=lambda name: feature_obj if name == "SketchFromFeature" else None,
    )

    result = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert result.is_success
    assert result.data["sketch_name"] == "SketchFromFeature"
    assert result.data["is_fully_defined"] is False
    assert result.data["source"].startswith("sketch.") or result.data[
        "source"
    ].startswith("feature.")


def test_check_sketch_fully_defined_handles_textual_probe_values() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketch = SimpleNamespace(
        GetFullyDefinedStatus=lambda: "fully defined"
    )
    adapter.currentModel = SimpleNamespace(
        GetActiveSketch2=lambda: adapter.currentSketch
    )

    result = sketch._check_sketch_fully_defined_impl(adapter, None)
    assert result.is_success
    assert result.data["definition_state"] == "fully_defined"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_spline_without_pythoncom(monkeypatch, platform: str) -> None:
    """No pywin32: Windows fails clearly; mock mode elsewhere passes a plain list."""
    import sys

    monkeypatch.setitem(sys.modules, "pythoncom", None)
    monkeypatch.setattr(sys, "platform", platform)
    received: list = []
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace(
        CreateSpline2=lambda points, _ends: received.append(points) or object()
    )

    result = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 1000.0, "y": 0.0}]
    )

    if platform == "win32":
        assert result.status == AdapterResultStatus.ERROR
        assert "pywin32 is required for add_spline" in (result.error or "")
        assert received == []
    else:
        assert result.status == AdapterResultStatus.SUCCESS
        assert received == [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0]]


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_constraint_without_pythoncom(monkeypatch, platform: str) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "pythoncom", None)
    monkeypatch.setattr(sys, "platform", platform)
    adapter, add_relation, _sk = _make_constraint_adapter(
        add_relation_returns=SimpleNamespace(Name="Perp1")
    )

    result = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "perpendicular"
    )

    if platform == "win32":
        assert result.status == AdapterResultStatus.ERROR
        assert "pywin32 is required for add_sketch_constraint" in (result.error or "")
        add_relation.assert_not_called()
    else:
        assert result.status == AdapterResultStatus.SUCCESS
        ents_arg, _rt = add_relation.call_args.args
        assert isinstance(ents_arg, list)


# ---- sketch-definition probe helpers ------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (0, False),
        (1.0, True),
        (2, None),
        (" Fully Defined ", True),
        ("under_defined", False),
        ("over defined", False),
        ("maybe", None),
        ([True], True),
        ((), None),
        (None, None),
    ],
)
def test_to_bool(raw: object, expected: bool | None) -> None:
    assert sketch._to_bool(raw) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(3, 3.0), (" 2.5 ", 2.5), ("abc", None), ([4], 4.0), ([], None), (None, None)],
)
def test_to_number(raw: object, expected: float | None) -> None:
    assert sketch._to_number(raw) == expected


@pytest.mark.parametrize(
    ("source", "raw", "expected"),
    [
        ("IsUnderDefined", 0, True),  # numeric: zero under-defined entities
        ("IsUnderDefined", 3, False),
        ("IsUnderDefined", "yes", False),  # bool: under-defined -> not fully
        ("IsUnderDefined", object(), None),  # neither number nor bool
        ("GetOverDefinedCount", 2, False),
        ("IsOverDefined", True, False),
        ("IsOverDefined", 0, False),  # 0 -> falls through to _to_bool(0)
        ("IsOverDefined", "yes", False),  # non-numeric over-defined flag
        ("IsFullyDefined", "true", True),
        ("Status", "Fully constrained", True),
        ("Status", "under-constrained", False),
        ("Status", 1, True),
    ],
)
def test_probe_to_flag(source: str, raw: object, expected: bool | None) -> None:
    assert sketch._probe_to_flag(source, raw) is expected


@pytest.mark.parametrize(
    ("flag", "state"),
    [(True, "fully_defined"), (False, "not_fully_defined"), (None, "unknown")],
)
def test_state_from_bool(flag: bool | None, state: str) -> None:
    assert sketch._state_from_bool(flag) == state


# ---- adapter-level validation of sketch patterns / mirror / offset ----------


def _sketching_adapter(**entities: object) -> _FakeSketchAdapter:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace()
    adapter._sketch_entities = dict(entities)
    return adapter


@pytest.mark.parametrize(
    ("entities", "angle", "count", "fragment"),
    [
        ([], 360.0, 4, "requires at least one entity"),
        (["Line_1"], 360.0, 1, "requires count >= 2"),
        (["Line_1"], 0.0, 4, "requires angle > 0"),
        (["Ghost_1"], 360.0, 4, "Unknown sketch entity 'Ghost_1'"),
    ],
)
def test_circular_pattern_validates_its_arguments(
    entities: list[str], angle: float, count: int, fragment: str
) -> None:
    adapter = _sketching_adapter(Line_1=object())

    result = sketch._sketch_circular_pattern_impl(adapter, entities, angle, count)

    assert result.status == AdapterResultStatus.ERROR
    assert fragment in (result.error or "")


@pytest.mark.parametrize(
    ("entities", "mirror_line", "fragment"),
    [
        ([], "Centerline_1", "requires at least one entity"),
        (["Line_1"], "", "mirror_line"),
        (["Line_1"], "Centerline_9", "Centerline_9"),
        (["Line_1"], "Line_2", "Line_2"),
        (["Nope_1"], "Centerline_1", "Nope_1"),
    ],
)
def test_mirror_validates_entities_and_mirror_line(
    entities: list[str], mirror_line: str, fragment: str
) -> None:
    adapter = _sketching_adapter(
        Line_1=object(), Line_2=object(), Centerline_1=object()
    )

    result = sketch._sketch_mirror_impl(adapter, entities, mirror_line)

    assert result.status == AdapterResultStatus.ERROR
    assert fragment in (result.error or "")


@pytest.mark.parametrize(
    ("entities", "distance", "fragment"),
    [
        ([], 2.0, "requires at least one entity"),
        (["Line_1"], 0.0, "offset_distance > 0"),
    ],
)
def test_offset_validates_entities_and_distance(
    entities: list[str], distance: float, fragment: str
) -> None:
    adapter = _sketching_adapter(Line_1=object())

    result = sketch._sketch_offset_impl(adapter, entities, distance, False)

    assert result.status == AdapterResultStatus.ERROR
    assert fragment in (result.error or "")


def test_add_sketch_dimension_angular_applies_the_value_in_radians() -> None:
    """The requested angle is applied (degrees -> radians), like other types."""
    import math

    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    vertex = SimpleNamespace(Select2=lambda _append, _mark: True)
    entity = SimpleNamespace(Select2=lambda _append, _mark: True)
    adapter._sketch_entities = {"L1": entity, "L2": entity}
    adapter._angular_dimension_placement = lambda _e1, _e2: (0.02, 0.02, 0.0, 0)
    adapter._shared_segment_vertex = lambda _e1, _e2: (object(), vertex, vertex)
    applied: list[float] = []
    dimension = SimpleNamespace(
        SetSystemValue3=lambda value, _cfg, _names: applied.append(value) or True
    )
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda *_args: True,
        Extension=SimpleNamespace(
            AddDimension=lambda *_a: SimpleNamespace(
                GetDimension2=lambda *_b: dimension
            )
        ),
    )

    result = sketch._add_sketch_dimension_impl(adapter, "L1", "L2", "angular", 30.0)

    assert result.is_success
    assert applied == [pytest.approx(math.radians(30.0))]


# ---- remaining sketch failure paths ---------------------------------------------


def test_constraint_unknown_second_entity_and_missing_relation_manager() -> None:
    adapter, add_relation, sketch_obj = _make_constraint_adapter()

    unknown = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_9", "perpendicular"
    )
    sketch_obj.RelationManager = None
    no_manager = sketch._add_sketch_constraint_impl(
        adapter, "Line_1", "Line_2", "perpendicular"
    )

    assert "Unknown sketch entity 'Line_9'" in (unknown.error or "")
    assert "Active sketch has no RelationManager" in (no_manager.error or "")
    add_relation.assert_not_called()


def _dimension_adapter(select_ok: bool) -> _FakeSketchAdapter:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    entity = SimpleNamespace(Select2=lambda _append, _mark: select_ok)
    adapter._sketch_entities = {"L1": entity, "L2": entity}
    adapter._single_line_dimension_placement = lambda _e: (0.01, 0.0, 0.0, 1)
    adapter._angular_dimension_placement = lambda _e1, _e2: (0.01, 0.01, 0.0, 0)
    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda *_a: True,
        Extension=SimpleNamespace(AddDimension=lambda *_a: None),
    )
    return adapter


def test_dimension_unknown_second_entity_and_unselectable_primary() -> None:
    adapter = _dimension_adapter(select_ok=False)

    unknown = sketch._add_sketch_dimension_impl(adapter, "L1", "L9", "linear", 5.0)
    unselectable = sketch._add_sketch_dimension_impl(adapter, "L1", None, "linear", 5.0)

    assert "Unknown sketch entity 'L9'" in (unknown.error or "")
    assert "Failed to select primary entity 'L1'" in (unselectable.error or "")


@pytest.mark.parametrize(
    ("segment_ok", "vertex_ok"), [(False, True), (True, False), (True, True)]
)
def test_angular_dimension_reports_failure_when_every_attempt_fails(
    segment_ok: bool, vertex_ok: bool
) -> None:
    """Segment refusal, vertex refusal, or AddDimension returning nothing."""
    adapter = _dimension_adapter(select_ok=segment_ok)
    vertex = SimpleNamespace(Select2=lambda _append, _mark: vertex_ok)
    adapter._shared_segment_vertex = lambda _e1, _e2: (object(), vertex, vertex)

    result = sketch._add_sketch_dimension_impl(adapter, "L1", "L2", "angular", 30.0)

    assert result.status == AdapterResultStatus.ERROR
    assert "failed to create sketch dimension" in (result.error or "")


class _SelMgr:
    def __init__(self) -> None:
        self.select_data = SimpleNamespace(Mark=None)

    def CreateSelectData(self):  # noqa: N802
        return self.select_data


@pytest.mark.parametrize(
    ("entity", "fragment"),
    [
        (None, "Unknown sketch entity 'E_1'"),
        ((SimpleNamespace(Select4=lambda *_a: False),), "Failed to select segment"),
        (SimpleNamespace(Select4=lambda *_a: False), "Failed to select sketch entity"),
    ],
)
def test_select_sketch_entities_failures(entity: object, fragment: str) -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentModel = SimpleNamespace(SelectionManager=_SelMgr())
    adapter._sketch_entities = {} if entity is None else {"E_1": entity}

    with pytest.raises(Exception, match=fragment):
        sketch._select_sketch_entities(adapter, ["E_1"], mark=1)


def test_exit_sketch_reports_insert_sketch_failure() -> None:
    adapter = _FakeSketchAdapter()

    def _boom(_rebuild: bool) -> None:
        raise RuntimeError("cannot leave sketch")

    adapter.currentSketchManager = SimpleNamespace(InsertSketch=_boom)
    adapter.currentModel = SimpleNamespace(GetActiveSketch2=lambda: object())

    result = sketch._exit_sketch_impl(adapter)

    assert result.status == AdapterResultStatus.ERROR
    assert "cannot leave sketch" in (result.error or "")


def test_check_fully_defined_by_name_and_with_no_sketch_anywhere() -> None:
    adapter = _FakeSketchAdapter()
    fully = SimpleNamespace(GetSketchStatus=lambda: True, IsFullyDefined=True)
    feature = SimpleNamespace(GetSpecificFeature2=lambda: fully, Name="Sketch1")
    adapter.currentModel = SimpleNamespace(
        FeatureByName=lambda name: feature if name == "Sketch1" else None,
        GetActiveSketch2=lambda: None,
    )

    named = sketch._check_sketch_fully_defined_impl(adapter, "Sketch1")
    missing = sketch._check_sketch_fully_defined_impl(adapter, None)

    assert named.is_success
    assert named.data["sketch_name"] == "Sketch1"
    assert missing.status == AdapterResultStatus.ERROR
    assert "No active sketch found" in (missing.error or "")


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


class TestSolidWorksSketchMixinGeometryHelpers:
    """Cover the _point_xyz, _set_point_xyz, ... helper delegation methods."""

    # --- _adapter staticmethod (line 17 in sketch.py) ---

    def test_sketch_adapter_staticmethod_returns_obj(self) -> None:
        sentinel = object()
        assert SolidWorksSketchMixin._adapter(sentinel) is sentinel

    # --- _point_xyz (lines 20-21) ---

    def test_point_xyz_delegates_to_sketch_geometry(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        mock_geom = Mock()
        mock_geom.point_xyz = Mock(return_value=(1.0, 2.0, 3.0))
        adapter._sketch_geometry = mock_geom

        result = adapter._point_xyz("pt_obj")
        mock_geom.point_xyz.assert_called_once_with("pt_obj")
        assert result == (1.0, 2.0, 3.0)

    # --- _set_point_xyz (lines 27-28) ---

    def test_set_point_xyz_delegates_to_sketch_geometry(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        mock_geom = Mock()
        mock_geom.set_point_xyz = Mock(return_value=True)
        adapter._sketch_geometry = mock_geom

        result = adapter._set_point_xyz("pt_obj", 1.0, 2.0, 3.0)
        mock_geom.set_point_xyz.assert_called_once_with("pt_obj", 1.0, 2.0, 3.0)
        assert result is True

    # --- _read_segment_endpoints (lines 33-34) ---

    def test_read_segment_endpoints_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        endpoints = ((0.0, 0.0, 0.0), (1.0, 1.0, 0.0))
        mock_geom = Mock()
        mock_geom.read_segment_endpoints = Mock(return_value=endpoints)
        adapter._sketch_geometry = mock_geom

        result = adapter._read_segment_endpoints("seg_obj")
        mock_geom.read_segment_endpoints.assert_called_once_with("seg_obj")
        assert result == endpoints

    # --- _segment_point_objects (lines 40-41) ---

    def test_segment_point_objects_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        pt_a, pt_b = object(), object()
        mock_geom = Mock()
        mock_geom.segment_point_objects = Mock(return_value=(pt_a, pt_b))
        adapter._sketch_geometry = mock_geom

        result = adapter._segment_point_objects("seg_obj")
        mock_geom.segment_point_objects.assert_called_once_with("seg_obj")
        assert result == (pt_a, pt_b)

    # --- _shared_segment_vertex (lines 49-50) ---

    def test_shared_segment_vertex_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        vertex_triple = (object(), object(), object())
        mock_geom = Mock()
        mock_geom.shared_segment_vertex = Mock(return_value=vertex_triple)
        adapter._sketch_geometry = mock_geom

        result = adapter._shared_segment_vertex("e1", "e2")
        mock_geom.shared_segment_vertex.assert_called_once_with("e1", "e2")
        assert result == vertex_triple

    # --- _smart_dimension_direction (lines 56-57) ---

    def test_smart_dimension_direction_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        mock_geom = Mock()
        mock_geom.smart_dimension_direction = Mock(return_value=1)
        adapter._sketch_geometry = mock_geom

        result = adapter._smart_dimension_direction(1.0, 0.0)
        mock_geom.smart_dimension_direction.assert_called_once_with(1.0, 0.0)
        assert result == 1

    # --- _single_line_dimension_placement (lines 62-63) ---

    def test_single_line_dimension_placement_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        placement = (5.0, 5.0, 0.0, 0)
        mock_geom = Mock()
        mock_geom.single_line_dimension_placement = Mock(return_value=placement)
        adapter._sketch_geometry = mock_geom

        result = adapter._single_line_dimension_placement("line_obj")
        mock_geom.single_line_dimension_placement.assert_called_once_with("line_obj")
        assert result == placement

    # --- _angular_dimension_placement (lines 71-72) ---

    def test_angular_dimension_placement_delegates(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        placement = (3.0, 4.0, 0.0, 1)
        mock_geom = Mock()
        mock_geom.angular_dimension_placement = Mock(return_value=placement)
        adapter._sketch_geometry = mock_geom

        result = adapter._angular_dimension_placement("l1", "l2")
        mock_geom.angular_dimension_placement.assert_called_once_with("l1", "l2")
        assert result == placement

    # --- check_sketch_fully_defined (last statement in sketch.py) ---

    @pytest.mark.asyncio
    async def test_check_sketch_fully_defined_delegates(self, monkeypatch) -> None:
        """Verify check_sketch_fully_defined passes through to sketch ops."""

        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter._last_sketch_name = "Sketch1"

        expected = {"fully_defined": True, "sketch_name": "Sketch1"}

        with patch(
            "solidworks_mcp.adapters.solidworks.sketch._check_sketch_fully_defined_impl",
        ) as mock_fn:
            from solidworks_mcp.adapters.base import (
                AdapterResult,
                AdapterResultStatus,
            )

            mock_fn.return_value = AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=expected
            )
            result = await adapter.check_sketch_fully_defined("Sketch1")

        assert result.is_success
        assert result.data == expected


class TestRealCircularPatternImpl:
    """Direct tests for ``_sketch_circular_pattern_impl`` against a fake
    SketchManager. Verifies the COM-call argument shape so partial sweeps
    and full circles use the right ``PatternSpacing`` formula.
    """

    @staticmethod
    def _build_adapter() -> tuple[SimpleNamespace, Mock, Mock]:
        """Build the minimum object graph the real impl reads from.

        The impl needs:
          * ``adapter._sketch_entities`` — registered seed entities
          * ``adapter.currentSketchManager.CreateCircularSketchStepAndRepeat``
          * ``adapter.currentModel.ClearSelection2`` and
            ``adapter.currentModel.SelectionManager.CreateSelectData``
          * ``adapter._handle_com_operation(name, fn)`` — invoked
            synchronously
          * ``adapter._attempt(fn, default=...)`` — synchronous
        """
        seed_entity = Mock()
        seed_entity.Select4 = Mock(return_value=True)
        # GetCenterPoint must resolve to a length-2 tuple of metres for the
        # impl's seed-centre lookup to succeed; without this the impl would
        # raise the "can't derive the seed centre" error and tests that
        # don't care about the seed position would break. (30, 0) mm puts
        # the seed on +X — a sensible default for circular-pattern tests.
        seed_entity.GetCenterPoint = Mock(return_value=(0.030, 0.0))
        sketch_entities = {"Circle_1": seed_entity}

        create_pattern = Mock(return_value=True)
        sketch_manager = Mock()
        sketch_manager.CreateCircularSketchStepAndRepeat = create_pattern

        select_data = Mock()
        selection_mgr = Mock()
        selection_mgr.CreateSelectData = Mock(return_value=select_data)
        current_model = SimpleNamespace(
            ClearSelection2=Mock(return_value=True),
            SelectionManager=selection_mgr,
        )

        def _handle(_name, fn):
            try:
                return AdapterResult(status=AdapterResultStatus.SUCCESS, data=fn())
            except Exception as exc:
                return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))

        def _attempt(fn, default=None):
            try:
                return fn()
            except Exception:
                return default

        adapter = SimpleNamespace(
            _sketch_entities=sketch_entities,
            _sketch_entity_centers={},
            currentSketchManager=sketch_manager,
            currentModel=current_model,
            _handle_com_operation=_handle,
            _attempt=_attempt,
        )
        return adapter, create_pattern, seed_entity

    def test_full_circle_uses_angle_over_count(self):
        """A 360° pattern with count=6 should hand the COM call a
        ``PatternSpacing`` of ``2π / 6`` so adjacent instances tile."""
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Circle_1"], 360.0, 6
        )

        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("CircularPattern_6x360.0deg_")
        create_pattern.assert_called_once()
        args = create_pattern.call_args.args
        # Signature: ArcRadius, ArcAngle, PatternNum, PatternSpacing,
        # PatternRotate, DeleteInstances, RadiusDim, AngleDim,
        # CreateNumOfInstancesDim
        assert args[2] == 6  # PatternNum
        assert args[3] == pytest.approx(math.radians(360.0) / 6)
        assert args[4] is True  # PatternRotate

    def test_partial_sweep_uses_angle_over_count_minus_one(self):
        """For ``angle=180, count=3`` the partial-sweep formula puts the
        last instance at 180°, so spacing must be ``π / (3 - 1)`` rad."""
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Circle_1"], 180.0, 3
        )

        assert result.status == AdapterResultStatus.SUCCESS
        args = create_pattern.call_args.args
        assert args[2] == 3
        assert args[3] == pytest.approx(math.radians(180.0) / 2)

    def test_clear_selection_runs_on_com_failure(self):
        """``CreateCircularSketchStepAndRepeat`` returning False must
        still leave selection state cleaned up (try/finally)."""
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()
        create_pattern.return_value = False
        clear_selection = adapter.currentModel.ClearSelection2

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Circle_1"], 360.0, 6
        )

        assert result.status == AdapterResultStatus.ERROR
        # ClearSelection2 runs before selecting and again in the finally
        # block after the COM failure.
        assert clear_selection.call_count == 2

    def test_polygon_seed_with_cached_center_drives_arc_radius(self):
        """When ``_add_polygon_impl`` cached the polygon center at register
        time, circular_pattern must use that cached center to derive the
        seed-to-axis distance instead of rejecting the seed."""
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()
        adapter._sketch_entities["Polygon_1"] = (Mock(), Mock(), Mock())
        # Polygon at (30, 40) mm → seed-to-origin distance is 50 mm.
        adapter._sketch_entity_centers["Polygon_1"] = (30.0, 40.0)

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Polygon_1"], 360.0, 6
        )

        assert result.status == AdapterResultStatus.SUCCESS
        create_pattern.assert_called_once()
        args = create_pattern.call_args.args
        # ArcRadius is in metres: hypot(30, 40) / 1000 = 0.05.
        assert args[0] == pytest.approx(0.05)
        assert args[2] == 6

    def test_rectangle_seed_with_cached_center_drives_arc_radius(self):
        """Rectangles register as a SAFEARRAY tuple of line segments — same
        shape as polygons. ``_add_rectangle_impl`` now caches the geometric
        centre at register time, so a rectangle seed must flow through
        circular_pattern the same as a polygon seed, deriving ArcRadius
        from the cached centre.
        """
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()
        adapter._sketch_entities["Rectangle_1"] = (Mock(), Mock(), Mock(), Mock())
        # Rectangle centred at (60, 80) mm → seed-to-origin distance is 100 mm.
        adapter._sketch_entity_centers["Rectangle_1"] = (60.0, 80.0)

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Rectangle_1"], 360.0, 4
        )

        assert result.status == AdapterResultStatus.SUCCESS
        create_pattern.assert_called_once()
        args = create_pattern.call_args.args
        # ArcRadius is in metres: hypot(60, 80) / 1000 = 0.100.
        assert args[0] == pytest.approx(0.100)
        assert args[2] == 4

    def test_single_dispatch_seed_without_get_center_point_raises(self):
        """Lines, splines, and centerlines register as a single dispatch but
        none of them expose ``GetCenterPoint`` on the flagged interfaces
        (``ISketchArc``/``ISketchEllipse``). The previous impl let this fall
        through to a 1 mm placeholder radius, silently producing a tightly
        clustered pattern instead of the intended one. Surface a clear
        error pointing the caller at the supported seed types instead."""
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()
        # Stand-in for a line/spline/centerline: single dispatch whose
        # GetCenterPoint returns a non-iterable value (the real impl swallows
        # the AttributeError via ``_attempt`` and ``point`` stays as a Mock
        # that fails the ``len(point) >= 2`` check). Use return_value=None to
        # be explicit.
        bare_seed = Mock()
        bare_seed.Select4 = Mock(return_value=True)
        bare_seed.GetCenterPoint = Mock(return_value=None)
        adapter._sketch_entities["Line_1"] = bare_seed

        result = sketch_ops._sketch_circular_pattern_impl(adapter, ["Line_1"], 360.0, 6)

        assert result.status == AdapterResultStatus.ERROR
        assert "Line_1" in (result.error or "")
        assert "GetCenterPoint" in (result.error or "")
        # COM call must NOT have fired — silent 1 mm placeholder pattern
        # was the bug.
        create_pattern.assert_not_called()

    def test_tuple_seed_without_cached_center_raises_clear_error(self):
        """Group-registering primitives (polygons, rectangles) cache their
        centre at register time so circular_pattern can derive the
        seed-to-axis radius from the tuple seed. Any *other* tuple seed
        without a cached centre — e.g. a future ``add_slot`` — would
        otherwise fall through to a misleading 1 mm placeholder radius.
        Surface a clear, actionable error that names only the
        always-works primitives instead.
        """
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, _ = self._build_adapter()
        # Stand in for a hypothetical tuple-registering primitive whose
        # ``add_*`` writer never stashed a centre.
        adapter._sketch_entities["Slot_1"] = (Mock(), Mock(), Mock(), Mock())

        result = sketch_ops._sketch_circular_pattern_impl(adapter, ["Slot_1"], 360.0, 6)

        assert result.status == AdapterResultStatus.ERROR
        # Error must name the offending entity and the accepted seed types.
        # Polygons and rectangles always reach the cached branch, so the
        # message lists only the always-works primitives.
        assert "Slot_1" in (result.error or "")
        assert "circle, arc, or ellipse" in (result.error or "")
        create_pattern.assert_not_called()

    def test_arc_angle_normalized_to_positive_when_seed_on_plus_x_axis(self):
        """A seed at (+X, 0) must hand SW a positive ``ArcAngle`` (+π), not
        the ``-π`` that Python's ``math.atan2(-0.0, -seed_x)`` produces.

        Regression: ``CreateCircularSketchStepAndRepeat`` silently returns
        ``False`` on negative angle values — both the live
        ``test_sketch_circular_pattern_creates_real_pattern`` regression
        and the live demo failed without this normalisation.
        """
        from solidworks_mcp.adapters.solidworks import sketch as sketch_ops

        adapter, create_pattern, seed_entity = self._build_adapter()
        # Seed at (+30 mm, 0): GetCenterPoint returns metres on the SW side,
        # so the impl multiplies by 1000 to get mm.  Length-2 tuple suffices
        # for the ``len(point) >= 2`` check.
        seed_entity.GetCenterPoint = Mock(return_value=(0.030, 0.0))

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Circle_1"], 360.0, 6
        )

        assert result.status == AdapterResultStatus.SUCCESS
        # Signature: ArcRadius, ArcAngle, PatternNum, ...
        args = create_pattern.call_args.args
        assert args[0] == pytest.approx(0.030)  # radius in metres
        # The angle must be ~+π (positive), not -π.  Without normalisation
        # ``math.atan2(-0.0, -0.030)`` returns ``-π`` and SW silently rejects
        # the call.
        assert args[1] == pytest.approx(math.pi)


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
    async def test_sketch_placeholder_and_exit_paths(self, monkeypatch):
        """Test sketch operation helpers and exit-sketch branches.

        The linear pattern call is wired with a fake SketchManager so the
        real impl (``CreateLinearSketchStepAndRepeat`` via the executor)
        succeeds. Circular pattern, mirror, and offset are still
        placeholders at this point in the stack — they don't touch COM
        and so only need ``currentSketchManager`` to be truthy.
        """
        adapter = self._build_adapter(monkeypatch)

        no_sketch = await adapter.exit_sketch()
        assert no_sketch.status.name == "WARNING"

        adapter.currentSketchManager = SimpleNamespace(InsertSketch=Mock())

        # Unknown relation types now error out — the placeholder that always
        # returned success was replaced by a real SketchAddConstraints call.
        assert (await adapter.add_sketch_constraint("L1", None, "unknown")).is_error
        # add_sketch_dimension's no-model fast path returns a synthesised ID
        # when ``adapter.currentModel`` is ``None``.
        assert (
            await adapter.add_sketch_dimension("L1", None, "linear", 10.0)
        ).is_success

        # Linear, circular, and mirror are real COM-touching impls now
        # (placeholders only before #16/#17/#18). Wire the minimum:
        #   currentSketchManager.CreateLinearSketchStepAndRepeat(...)
        #   currentSketchManager.CreateCircularSketchStepAndRepeat(...)
        #   currentModel.SketchMirror() (mirror)
        #   currentModel.ClearSelection2 and SelectionManager.CreateSelectData
        #   adapter._sketch_entities[entity_id].Select4(...)
        #   The mirror_line entity must use a ``Centerline_*`` ID since
        #   the real impl rejects anything else.
        seed_entity = Mock()
        seed_entity.Select4 = Mock(return_value=True)
        # Circular pattern now requires a resolvable seed centre — either via
        # GetCenterPoint (single dispatch) or via _sketch_entity_centers
        # (group entities). Wire GetCenterPoint so this test's seed stands in
        # for a circle/arc/ellipse rather than a line.
        seed_entity.GetCenterPoint = Mock(return_value=(0.030, 0.0))
        centerline = Mock()
        centerline.Select4 = Mock(return_value=True)
        adapter._sketch_entities = {
            "L1": seed_entity,
            "Centerline_42": centerline,
        }

        adapter.currentSketchManager = SimpleNamespace(
            InsertSketch=Mock(),
            CreateLinearSketchStepAndRepeat=Mock(return_value=True),
            CreateCircularSketchStepAndRepeat=Mock(return_value=True),
            SketchOffset2=Mock(return_value=True),
        )

        select_data = Mock()
        selection_mgr = Mock()
        selection_mgr.CreateSelectData = Mock(return_value=select_data)
        adapter.currentModel = SimpleNamespace(
            ClearSelection2=Mock(return_value=True),
            SelectionManager=selection_mgr,
            SketchMirror=Mock(return_value=None),
        )

        assert (
            await adapter.sketch_linear_pattern(["L1"], 1.0, 0.0, 5.0, 3)
        ).is_success
        assert (await adapter.sketch_circular_pattern(["L1"], 180.0, 4)).is_success
        assert (await adapter.sketch_mirror(["L1"], "Centerline_42")).is_success
        assert (await adapter.sketch_offset(["L1"], 1.0, True)).is_success

        exited = await adapter.exit_sketch()
        assert exited.is_success
        assert adapter.currentSketchManager is None

    @pytest.mark.asyncio
    async def test_sketch_geometry_feature_and_mass_property_paths(self, monkeypatch):
        """Test sketch/entity creation, feature creation, and mass properties with full mocks."""
        adapter = self._build_adapter(monkeypatch)

        feature_id = SimpleNamespace(ToString=lambda: "feat-1")
        feature_obj = SimpleNamespace(Name="Feat1", GetID=lambda: feature_id)

        sketch_manager = SimpleNamespace(
            InsertSketch=Mock(return_value=SimpleNamespace(Name="SketchA")),
            CreateLine=Mock(return_value=object()),
            CreateCircleByRadius=Mock(return_value=object()),
            CreateCornerRectangle=Mock(return_value=object()),
            CreateArc=Mock(return_value=object()),
            CreateSpline2=Mock(return_value=object()),
            CreateCenterLine=Mock(return_value=object()),
            CreatePolygon=Mock(return_value=object()),
            CreateEllipse=Mock(return_value=object()),
        )
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
        mass_props = SimpleNamespace(
            Volume=2.0e-9,
            SurfaceArea=5.0e-6,
            Mass=0.25,
            CenterOfMass=[0.01, 0.02, 0.03],
            GetMomentOfInertia=lambda _about: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        )
        extension = SimpleNamespace(
            SelectByID2=Mock(return_value=True),
            CreateMassProperty=Mock(return_value=mass_props),
        )
        adapter.currentModel = SimpleNamespace(
            Extension=extension,
            SketchManager=sketch_manager,
            FeatureManager=feature_manager,
            ClearSelection2=Mock(return_value=True),
            FirstFeature=SimpleNamespace(
                GetTypeName2=lambda: "ProfileFeature",
                Name="SketchA",
                GetNextFeature=lambda: None,
            ),
        )

        created_sketch = await adapter.create_sketch("XY")
        assert created_sketch.is_success
        assert created_sketch.data == "SketchA"

        assert (await adapter.add_line(0, 0, 10, 0)).is_success
        assert (await adapter.add_circle(0, 0, 5)).is_success
        assert (await adapter.add_rectangle(0, 0, 5, 3)).is_success
        assert (await adapter.add_arc(0, 0, 1, 0, 0, 1)).is_success
        assert (
            await adapter.add_spline(
                [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 0.0}]
            )
        ).is_success
        assert (await adapter.add_centerline(0, 0, 0, 10)).is_success
        assert (await adapter.add_polygon(0, 0, 5, 6)).is_success
        assert (await adapter.add_ellipse(0, 0, 10, 6)).is_success

        extrude_standard = await adapter.create_extrusion(
            SimpleNamespace(
                depth=10.0,
                draft_angle=2.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )
        extrude_thin = await adapter.create_extrusion(
            SimpleNamespace(
                depth=8.0,
                draft_angle=0.0,
                reverse_direction=True,
                thin_feature=True,
                thin_thickness=1.0,
                merge_result=True,
            )
        )
        revolve = await adapter.create_revolve(
            SimpleNamespace(
                angle=180.0,
                reverse_direction=False,
                both_directions=True,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )
        cut = await adapter.create_cut_extrude(
            SimpleNamespace(depth=4.0, draft_angle=1.0, reverse_direction=False)
        )
        fillet = await adapter.add_fillet(2.0, ["Edge1", "Edge2"])
        chamfer = await adapter.add_chamfer(1.5, ["Edge1"])
        mass = await adapter.get_mass_properties()

        assert extrude_standard.is_success
        assert extrude_thin.is_success
        assert revolve.is_success
        assert cut.is_success
        assert fillet.is_success
        assert chamfer.is_success
        assert mass.is_success
        assert mass.data.volume == pytest.approx(2.0)
        assert mass.data.surface_area == pytest.approx(5.0)
        assert mass.data.center_of_mass == [10.0, 20.0, 30.0]

        plane_select_calls = [
            call.args
            for call in extension.SelectByID2.call_args_list
            if len(call.args) >= 9
            and call.args[0] == "Top Plane"
            and call.args[1] == "PLANE"
        ]
        assert plane_select_calls, "Expected plane selection call for sketch creation"
        assert any(call_args[7] in ("", None, 0) for call_args in plane_select_calls)
        assert feature_manager.FeatureExtrusion3.called
        assert feature_manager.FeatureExtruThin2.called
        assert feature_manager.FeatureRevolve2.called
        assert feature_manager.FeatureCut3.called

    @pytest.mark.asyncio
    async def test_sketch_methods_guard_and_failure_paths(self, monkeypatch):
        """Cover no-active-sketch guards and per-entity creation failures."""
        adapter = self._build_adapter(monkeypatch)

        # Guard returns when sketch manager is missing.
        for call in (
            adapter.add_line(0, 0, 1, 1),
            adapter.add_circle(0, 0, 1),
            adapter.add_rectangle(0, 0, 1, 1),
            adapter.add_arc(0, 0, 1, 0, 0, 1),
            adapter.add_spline(
                [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 0.0}]
            ),
            adapter.add_centerline(0, 0, 1, 1),
            adapter.add_polygon(0, 0, 1, 5),
            adapter.add_ellipse(0, 0, 2, 1),
            adapter.add_sketch_constraint("L1", None, "parallel"),
        ):
            result = await call
            assert result.is_error

        adapter.currentSketchManager = SimpleNamespace(
            CreateLine=Mock(return_value=None),
            CreateCircleByRadius=Mock(return_value=None),
            CreateCornerRectangle=Mock(return_value=None),
            CreateArc=Mock(return_value=None),
            CreateSpline2=Mock(return_value=None),
            CreateCenterLine=Mock(return_value=None),
            CreatePolygon=Mock(return_value=None),
            CreateEllipse=Mock(return_value=None),
        )

        assert "Failed to create line" in (
            (await adapter.add_line(0, 0, 1, 1)).error or ""
        )
        assert "Failed to create circle" in (
            (await adapter.add_circle(0, 0, 1)).error or ""
        )
        assert "Failed to create rectangle" in (
            (await adapter.add_rectangle(0, 0, 1, 1)).error or ""
        )
        assert "Failed to create arc" in (
            (await adapter.add_arc(0, 0, 1, 0, 0, 1)).error or ""
        )
        assert "Failed to create spline" in (
            (
                await adapter.add_spline(
                    [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 2.0, "y": 0.0}]
                )
            ).error
            or ""
        )
        assert "Failed to create centerline" in (
            (await adapter.add_centerline(0, 0, 1, 1)).error or ""
        )
        assert "Failed to create polygon" in (
            (await adapter.add_polygon(0, 0, 1, 5)).error or ""
        )
        assert "Failed to create ellipse" in (
            (await adapter.add_ellipse(0, 0, 2, 1)).error or ""
        )

    @pytest.mark.asyncio
    async def test_create_sketch_plane_selection_fallback_paths(self, monkeypatch):
        """Cover create_sketch feature-lookup/SelectByID2 fallback and InsertSketch variants."""
        adapter = self._build_adapter(monkeypatch)

        class _FakeComError(Exception):
            """Test suite for FakeComError."""

            pass

        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=_FakeComError),
            raising=False,
        )

        class _PlaneFeature:
            """Test suite for PlaneFeature."""

            def Select2(self, *_args):
                """Test helper for Select2."""
                return True

        feature_calls = {"count": 0}

        def _feature_by_name(_name):
            """Test helper for feature by name."""
            feature_calls["count"] += 1
            if feature_calls["count"] == 1:
                raise RuntimeError("feature lookup failed")
            return _PlaneFeature()

        adapter.currentModel = SimpleNamespace(
            FeatureByName=_feature_by_name,
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            SketchManager=SimpleNamespace(
                InsertSketch=Mock(side_effect=[_FakeComError("variant"), None])
            ),
            GetActiveSketch2=Mock(side_effect=RuntimeError("no active sketch object")),
        )

        sketch_result = await adapter.create_sketch("Top")
        assert sketch_result.is_success
        assert str(sketch_result.data).startswith("Sketch_")

        # Force total selection failure to cover explicit error branch.
        adapter.currentModel = SimpleNamespace(
            FeatureByName=Mock(side_effect=RuntimeError("lookup failed")),
            Extension=SimpleNamespace(
                SelectByID2=Mock(side_effect=RuntimeError("select failed"))
            ),
            SketchManager=SimpleNamespace(InsertSketch=Mock(return_value=None)),
        )
        failed = await adapter.create_sketch("Top")
        assert failed.is_error
        assert "Failed to select plane" in (failed.error or "")

    @pytest.mark.asyncio
    async def test_create_sketch_empty_plane_and_total_select_failure(
        self, monkeypatch
    ) -> None:
        """create_sketch should skip empty candidates and surface explicit plane selection failure."""
        adapter = self._build_adapter(monkeypatch)
        adapter.currentModel = SimpleNamespace(
            FeatureByName=Mock(return_value=None),
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            SketchManager=SimpleNamespace(InsertSketch=Mock(return_value=None)),
            GetActiveSketch2=Mock(return_value="Sketch1"),
        )

        failed = await adapter.create_sketch("")
        assert failed.is_error
        assert "Failed to select plane" in (failed.error or "")

    @pytest.mark.asyncio
    async def test_sketch_and_mass_property_guard_and_fallback_errors(
        self, monkeypatch
    ) -> None:
        """Cover sketch guard returns and mass-properties fallback error branches."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = None
        assert (await adapter.create_sketch("Top")).is_error
        assert (await adapter.get_mass_properties()).is_error

        adapter.currentSketchManager = None
        assert (await adapter.add_sketch_dimension("L1", None, "linear", 10.0)).is_error
        assert (await adapter.sketch_linear_pattern(["L1"], 1.0, 0.0, 5.0, 3)).is_error
        assert (await adapter.sketch_circular_pattern(["L1"], 180.0, 4)).is_error
        assert (await adapter.sketch_mirror(["L1"], "CL1")).is_error
        assert (await adapter.sketch_offset(["L1"], 1.0, True)).is_error

        adapter.currentModel = SimpleNamespace(
            ForceRebuild3=Mock(return_value=True),
            Extension=SimpleNamespace(CreateMassProperty=Mock(return_value=None)),
            GetMassProperties=[0.0, 0.0, 0.0, 1.0, 2.0, 3.0],
        )
        mass_result = await adapter.get_mass_properties()
        assert mass_result.is_success
        assert mass_result.data is not None
        assert mass_result.data.moments_of_inertia == {
            "Ixx": 0.0,
            "Iyy": 0.0,
            "Izz": 0.0,
            "Ixy": 0.0,
            "Ixz": 0.0,
            "Iyz": 0.0,
        }

        # IMassProperty path with short MOI tuple should zero-fill inertia values.
        adapter.currentModel = SimpleNamespace(
            ForceRebuild3=Mock(return_value=True),
            Extension=SimpleNamespace(
                CreateMassProperty=Mock(
                    return_value=SimpleNamespace(
                        Volume=1.0,
                        SurfaceArea=2.0,
                        Mass=3.0,
                        CenterOfMass=[0.0, 0.0, 0.0],
                        GetMomentOfInertia=Mock(return_value=[1.0]),
                    )
                )
            ),
        )
        short_moi = await adapter.get_mass_properties()
        assert short_moi.is_success
        assert short_moi.data is not None
        assert short_moi.data.moments_of_inertia == {
            "Ixx": 0.0,
            "Iyy": 0.0,
            "Izz": 0.0,
            "Ixy": 0.0,
            "Ixz": 0.0,
            "Iyz": 0.0,
        }

        adapter.currentModel = SimpleNamespace(
            ForceRebuild3=Mock(return_value=True),
            Extension=SimpleNamespace(CreateMassProperty=Mock(return_value=None)),
            GetMassProperties=[0.0, 0.0, 0.0],
        )
        mass_error = await adapter.get_mass_properties()
        assert mass_error.is_error
        assert "Failed to get mass properties" in (mass_error.error or "")


# ---- linear dimension between a line and a circle (hole location) -------------


def _line_and_circle_adapter(
    *, add_dimension2=(), extension=None, centre_selectable=True, positions=True
):
    """A sketch with a vertical line at x=0 (0..50 mm) and a circle at (10, 10) mm.

    ``add_dimension2`` lists what successive ``AddDimension2`` calls return;
    ``extension`` is what ``Extension.AddDimension`` returns.
    """
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()
    adapter._single_line_dimension_placement = lambda _e: (0.01, 0.025, 0.0, 0)
    selected: list[object] = []

    def selectable(name):
        return SimpleNamespace(
            name=name, Select2=lambda append, _m: selected.append(name) or True
        )

    line = selectable("line")
    centre = SimpleNamespace(
        Select2=lambda _a, _m: selected.append("centre") or centre_selectable
    )
    circle = selectable("circle")
    if positions:
        circle.GetCenterPoint = lambda: (0.01, 0.01, 0.0)
    circle.GetCenterPoint2 = centre
    adapter._sketch_entities = {"Line_1": line, "Circle_2": circle}
    adapter._sketch_geometry = SimpleNamespace(
        read_segment_endpoints=lambda e: (
            ((0.0, 0.05, 0.0), (0.0, 0.0, 0.0)) if e is line else None
        )
    )
    results = iter(add_dimension2)
    calls: list[tuple] = []

    def add_dimension2_call(*xyz):
        calls.append(("AddDimension2", selected[-1], xyz))
        return next(results, None)

    def extension_call(*args):
        calls.append(("AddDimension", selected[-1], args))
        return extension

    adapter.currentModel = SimpleNamespace(
        ClearSelection2=lambda *_a: selected.clear() or True,
        AddDimension2=add_dimension2_call,
        Extension=SimpleNamespace(AddDimension=extension_call),
    )
    return adapter, calls


def _display_dimension() -> SimpleNamespace:
    dim = SimpleNamespace(SetSystemValue3=lambda *_a: True)
    return SimpleNamespace(GetDimension2=lambda *_a: dim)


def test_line_to_circle_dimension_uses_add_dimension2_at_the_midpoint() -> None:
    adapter, calls = _line_and_circle_adapter(add_dimension2=[_display_dimension()])

    result = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", "Circle_2", "linear", 10.0
    )

    assert result.is_success, result.error
    # Midway between the line's midpoint (0, 25) mm and the centre (10, 10) mm.
    assert calls == [("AddDimension2", "circle", pytest.approx((0.005, 0.0175, 0.0)))]


def test_line_to_circle_dimension_falls_back_to_the_centre_point() -> None:
    adapter, calls = _line_and_circle_adapter(
        add_dimension2=[None, _display_dimension()]
    )

    result = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", "Circle_2", "linear", 10.0
    )

    assert result.is_success, result.error
    assert [(c[0], c[1]) for c in calls] == [
        ("AddDimension2", "circle"),
        ("AddDimension2", "centre"),
    ]


def test_line_to_circle_dimension_falls_back_to_extension_add_dimension() -> None:
    adapter, calls = _line_and_circle_adapter(
        extension=_display_dimension(), centre_selectable=False
    )

    result = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", "Circle_2", "linear", 10.0
    )

    assert result.is_success, result.error
    # The unselectable centre point is skipped, not tried.
    assert [(c[0], c[1]) for c in calls] == [
        ("AddDimension2", "circle"),
        ("AddDimension", "circle"),
    ]


def test_line_to_circle_dimension_that_nothing_creates_is_an_error() -> None:
    adapter, calls = _line_and_circle_adapter()

    result = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", "Circle_2", "linear", 10.0
    )

    assert "SolidWorks failed to create sketch dimension" in (result.error or "")
    assert len(calls) == 3


def test_line_to_circle_dimension_needs_both_positions() -> None:
    adapter, calls = _line_and_circle_adapter(positions=False)

    result = sketch._add_sketch_dimension_impl(
        adapter, "Line_1", "Circle_2", "linear", 10.0
    )

    assert "Cannot read where the two entities are" in (result.error or "")
    assert calls == []


def test_two_entity_linear_dimension_names_an_unselectable_primary() -> None:
    adapter = _dimension_adapter(select_ok=False)

    result = sketch._add_sketch_dimension_impl(adapter, "L1", "L2", "linear", 5.0)

    assert "Failed to select primary entity 'L1'" in (result.error or "")


def test_diameter_dimension_with_an_unselectable_second_entity_is_an_error() -> None:
    adapter = _dimension_adapter(select_ok=True)
    adapter._sketch_entities["L2"] = SimpleNamespace(Select2=lambda _a, _m: False)

    result = sketch._add_sketch_dimension_impl(adapter, "L1", "L2", "diameter", 5.0)

    assert "Failed to select secondary entity 'L2'" in (result.error or "")
