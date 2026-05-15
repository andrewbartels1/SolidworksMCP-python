"""Direct branch coverage tests for src.solidworks_mcp.adapters.solidworks.sketch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from src.solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from src.solidworks_mcp.adapters.solidworks import sketch


class _FakeSketchAdapter:
    def __init__(self) -> None:
        self.currentModel = None
        self.currentSketchManager = None
        self.currentSketch = None
        self._sketch_count = 0
        self._last_sketch_name = None
        self._sketch_entities: dict[str, object] = {}
        self._next_id = 1
        self.constants = {
            "swSmartDimensionDirectionRight": 0,
            "swSmartDimensionDirectionUp": 1,
            "swSmartDimensionDirectionLeft": 2,
            "swSmartDimensionDirectionDown": 3,
        }

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
    adapter.currentSketchManager = SimpleNamespace(
        CreateSpline2=lambda points, _closed, _opts: points,
        CreateCenterLine=lambda *args: object(),
        CreatePolygon=lambda *args: object(),
        CreateEllipse=lambda *args: object(),
    )

    spline_ok = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 1.0}]
    )
    assert spline_ok.is_success
    assert spline_ok.data.startswith("Spline_")

    center_ok = sketch._add_centerline_impl(adapter, 0, 0, 10, 0)
    polygon_ok = sketch._add_polygon_impl(adapter, 0, 0, 10, 6)
    ellipse_ok = sketch._add_ellipse_impl(adapter, 0, 0, 10, 4)
    assert center_ok.is_success and center_ok.data.startswith("Centerline_")
    assert polygon_ok.is_success and polygon_ok.data.startswith("Polygon_6sided_")
    assert ellipse_ok.is_success and ellipse_ok.data.startswith("Ellipse_")


def test_spline_error_when_create_returns_none() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = SimpleNamespace(CreateSpline2=lambda *args: None)
    result = sketch._add_spline_impl(
        adapter, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to create spline" in (result.error or "")


def test_pattern_placeholders() -> None:
    adapter = _FakeSketchAdapter()
    adapter.currentSketchManager = object()

    linear_pattern = sketch._sketch_linear_pattern_impl(
        adapter, ["Line_1"], 1, 0, 5.0, 3
    )
    circular_pattern = sketch._sketch_circular_pattern_impl(
        adapter, ["Line_1"], 0, 0, 45.0, 8
    )
    mirror = sketch._sketch_mirror_impl(adapter, ["Line_1"], "Centerline_1")
    offset = sketch._sketch_offset_impl(adapter, ["Line_1"], 2.5, True)

    assert linear_pattern.is_success and linear_pattern.data.startswith(
        "LinearPattern_3x5.0_"
    )
    assert circular_pattern.is_success and circular_pattern.data.startswith(
        "CircularPattern_8x45.0deg_"
    )
    assert mirror.is_success and mirror.data.startswith("Mirror_Centerline_1_")
    assert offset.is_success and "_inward_" in offset.data


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
    adapter._sketch_entities = {"Line_1": line1, "Line_2": line2}

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


def test_exit_sketch_warning_and_success_paths() -> None:
    adapter = _FakeSketchAdapter()
    warning = sketch._exit_sketch_impl(adapter)
    assert warning.status == AdapterResultStatus.WARNING

    manager = SimpleNamespace(InsertSketch=Mock())
    adapter.currentSketchManager = manager
    adapter.currentSketch = object()
    adapter._sketch_entities = {"Line_1": object()}

    success = sketch._exit_sketch_impl(adapter)
    assert success.status == AdapterResultStatus.SUCCESS
    assert adapter.currentSketch is None
    assert adapter.currentSketchManager is None
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
    assert angular.is_success
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
