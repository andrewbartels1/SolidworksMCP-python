"""Targeted coverage tests for the adapters/solidworks mixin modules.

Exercises the specific code paths missed by the main branch test suite:
- SolidWorksFeaturesMixin.create_sweep / create_loft
- SolidWorksIOMixin._adapter staticmethod and not-connected error returns
- SolidWorksSketchMixin geometry-helper methods (_point_xyz, _set_point_xyz, etc.)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks.features import (
    _create_axis_impl,
    _create_reference_plane_impl,
    _delete_feature_impl,
    _feature_count,
    _is_suppressed,
    _mirror_feature_impl,
    _pattern_circular_impl,
    _select_reference_entity,
    _suppress_feature_impl,
    _undo_impl,
)
from solidworks_mcp.adapters.solidworks.io import (
    SolidWorksIOMixin,
    _byref_int,
    _ByrefFallback,
    _component_pairs,
    _component_transforms,
    _interference_details,
    _payload,
    _payload_dict,
    _view_names,
)
from solidworks_mcp.adapters.solidworks.sketch import SolidWorksSketchMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# features.py: create_sweep and create_loft
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# io.py: _adapter staticmethod and not-connected error returns
# ---------------------------------------------------------------------------


class TestSolidWorksIOMixinNotConnected:
    """Cover the not-connected early-return paths in SolidWorksIOMixin."""

    # --- _adapter staticmethod (line 16 in io.py) ---

    def test_adapter_staticmethod_returns_obj(self) -> None:
        """SolidWorksIOMixin._adapter is a transparent identity cast."""
        sentinel = object()
        result = SolidWorksIOMixin._adapter(sentinel)
        assert result is sentinel

    # --- open_model with is_connected() == False (line 21) ---

    @pytest.mark.asyncio
    async def test_open_model_not_connected_returns_error(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.open_model("test.sldprt")
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_part with is_connected() == False (line 71) ---

    @pytest.mark.asyncio
    async def test_create_part_not_connected_returns_error(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_part()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_assembly with is_connected() == False (line 86) ---

    @pytest.mark.asyncio
    async def test_create_assembly_not_connected_returns_error(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_assembly()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    # --- create_drawing with is_connected() == False (line 101) ---

    @pytest.mark.asyncio
    async def test_create_drawing_not_connected_returns_error(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: False)
        result = await adapter.create_drawing()
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_open_model_uses_int_errors_when_variant_ctor_missing(
        self, monkeypatch
    ) -> None:
        """open_model should pass integer error/warning refs when VARIANT is unavailable."""
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: True)

        class _Cfg:
            @staticmethod
            def GetName() -> str:
                return "Default"

        model = MagicMock()
        model.GetActiveConfiguration.return_value = _Cfg()
        app = MagicMock()
        app.OpenDoc6.return_value = model

        adapter.swApp = app
        adapter.constants = {
            "swDocPART": 1,
            "swDocASSEMBLY": 2,
            "swDocDRAWING": 3,
        }
        adapter._attempt = lambda operation, default=None: operation()
        adapter._read_model_title = lambda _m: "Part1"

        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=None)),
            raising=False,
        )
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.pythoncom",
            SimpleNamespace(VT_BYREF=0x4000, VT_I4=3),
            raising=False,
        )

        result = await adapter.open_model("model.sldprt")

        assert result.is_success
        args = app.OpenDoc6.call_args.args
        assert args[4] == 0
        assert args[5] == 0


# ---------------------------------------------------------------------------
# sketch.py: geometry-helper delegation methods
# ---------------------------------------------------------------------------


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
        from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# features.py: narrow COM defensive branches for the new PR #66-71 capabilities
#
# These are pure error-handling logic reacting to a falsy/unexpected COM
# return value (e.g. "InsertMirrorFeature returned nothing") - not a claim
# about what real SolidWorks actually does. Faking the specific return shape
# a COM call produces, to verify OUR code reacts correctly, is safe and
# established elsewhere in this file; it is fabricating a *believable
# success* response (asserting real SW behaviour we cannot verify) that this
# repo's tests avoid.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# io.py: narrow error/fallback branches for the new PR #65/#66 drawing and
# interference capabilities, plus two small pre-existing payload-coercion
# fallbacks these tests happen to also close.
# ---------------------------------------------------------------------------


class TestPayloadCoercionFallbacks:
    """Cover the ``vars(data)`` fallback in ``_payload`` / ``_payload_dict``."""

    def test_payload_coerces_plain_object_via_vars(self) -> None:
        class _Obj:
            def __init__(self) -> None:
                self.text = "hello"
                self._private = "hidden"

        result = _payload(_Obj())
        assert result == {"text": "hello"}

    def test_payload_dict_coerces_plain_object_via_vars(self) -> None:
        class _Obj:
            def __init__(self) -> None:
                self.coincident = True
                self._private = "hidden"

        result = _payload_dict(_Obj())
        assert result == {"coincident": True}

    def test_payload_dict_passes_through_a_plain_dict(self) -> None:
        given = {"coincident": True}
        assert _payload_dict(given) is given

    def test_payload_dict_uses_model_dump_for_pydantic_style_objects(self) -> None:
        model = SimpleNamespace(model_dump=lambda: {"coincident": False})
        assert _payload_dict(model) == {"coincident": False}


class TestRequireDrawingGuard:
    """Cover ``SolidWorksIOMixin._require_drawing``'s two error branches."""

    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None

        result = await adapter.add_note({"text": "hi"})

        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_active_document_is_not_a_drawing(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1  # Part, not a drawing (3)

        result = await adapter.add_note({"text": "hi"})

        assert result.is_error
        assert "requires a drawing document" in (result.error or "")


class TestPlaceViewErrors:
    """Cover ``_place_view``'s input-validation error branches."""

    @staticmethod
    def _drawing_adapter(monkeypatch) -> PyWin32Adapter:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        return adapter

    @pytest.mark.asyncio
    async def test_errors_when_model_path_missing(self, monkeypatch) -> None:
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view({"orientation": "front"})

        assert result.is_error
        assert "A model path is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_file_not_found(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view(
            {"model_path": str(tmp_path / "does-not-exist.sldprt")}
        )

        assert result.is_error
        assert "Model file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_orientation_unknown(self, monkeypatch) -> None:
        adapter = self._drawing_adapter(monkeypatch)
        # __file__ definitely exists on disk, so the file-not-found check
        # passes and the orientation check is what actually gets exercised.
        result = await adapter.create_drawing_view(
            {"model_path": __file__, "orientation": "not_a_real_view"}
        )

        assert result.is_error
        assert "Unknown orientation" in (result.error or "")

    @pytest.mark.asyncio
    async def test_accepts_an_explicit_position_list_and_a_raw_star_view_name(
        self, monkeypatch
    ) -> None:
        """An explicit [x, y] position and a raw '*Name' orientation both parse.

        Doesn't assert success - reaching the raw-name branch means the call
        proceeds to a real (mocked) OpenDoc6, which this bare MagicMock
        currentModel can't satisfy. What matters here is that both parsing
        branches (position-as-list, and the '*'-prefixed raw view name) run
        without raising, rather than falling into their "not given" defaults.
        """
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view(
            {
                "model_path": __file__,
                "position": [200.0, 75.0],
                "orientation": "*CustomView1",
            }
        )

        # However it resolves, it must have gotten past both the
        # "model path required" and "Unknown orientation" checks.
        assert "Unknown orientation" not in (result.error or "")
        assert "A model path is required" not in (result.error or "")


class TestCreateTechnicalDrawingNoViewsCreated:
    """Cover ``create_technical_drawing``'s "no views were created" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_no_new_views_appear(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        # GetViews() defaults to a MagicMock, which _view_names treats as
        # "not a list/tuple" and reduces to [] both before and after, so
        # nothing appears to have been added.

        result = await adapter.create_technical_drawing({"model_path": __file__})

        assert result.is_error
        assert "No views were created" in (result.error or "")


class TestAddNoteInsertNoteReturnsNothing:
    """Cover ``add_note``'s "InsertNote returned nothing" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_insert_note_returns_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3  # Drawing
        adapter.currentModel.InsertNote.return_value = None

        result = await adapter.add_note({"text": "MATERIAL: AISI 1018"})

        assert result.is_error
        assert "InsertNote returned nothing" in (result.error or "")


class TestCheckInterferenceManagerUnavailable:
    """Cover ``check_interference``'s "manager is unavailable" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_interference_detection_manager_unavailable(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2  # Assembly
        adapter.currentModel.InterferenceDetectionManager = None

        result = await adapter.check_interference()

        assert result.is_error
        assert "InterferenceDetectionManager is unavailable" in (result.error or "")


class TestCreateDrawingNoTemplateConfigured:
    """Cover ``create_drawing``'s "no drawing template configured" raise."""

    @pytest.mark.asyncio
    async def test_errors_when_no_template_resolves(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(adapter, "is_connected", lambda: True)
        adapter.swApp = MagicMock()
        adapter._resolve_template_path = lambda *a, **kw: None

        result = await adapter.create_drawing()

        assert result.is_error
        assert "No drawing template configured" in (result.error or "")


class TestByrefFallback:
    """Cover ``_ByrefFallback``'s dunder methods directly.

    Earlier assessment (mine, inherited from an automated survey) called
    this "dead code on Windows+pywin32". That was wrong: it's a plain
    Python class, reachable any time ``win32com.client.VARIANT`` is
    unavailable - the exact same monkeypatch already used a few classes up
    in this file (``test_open_model_uses_int_errors_when_variant_ctor_missing``).
    No mocking is even needed to cover the dunders themselves.
    """

    def test_equality_against_seeded_value_and_another_instance(self) -> None:
        holder = _ByrefFallback(1)
        assert holder == 1
        assert holder == _ByrefFallback(1)
        assert holder != 2
        assert holder != _ByrefFallback(2)

    def test_hash_and_bool_follow_the_seeded_value(self) -> None:
        assert hash(_ByrefFallback(5)) == hash(5)
        assert bool(_ByrefFallback(0)) is False
        assert bool(_ByrefFallback(1)) is True

    def test_repr_shows_the_seeded_value(self) -> None:
        assert repr(_ByrefFallback(3)) == "_ByrefFallback(3)"

    def test_byref_int_falls_back_when_variant_ctor_unavailable(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=None)),
            raising=False,
        )
        result = _byref_int()
        assert isinstance(result, _ByrefFallback)
        assert result.value == 0


class TestAddMateErrorBranches:
    """Cover ``add_mate``'s remaining error branches - pre-existing PR #56
    code, not one of the 7 new-capability PRs this coverage sprint targeted,
    but closed anyway since the technique generalizes directly.

    ``_as_com`` wraps every component/feature through the real
    ``win32com.client.dynamic.Dispatch`` before flagging it, which raises on
    a plain test double (it expects a real COM PyIDispatch). Monkeypatching
    io.py's module-level ``_dynamic`` alias to an identity passthrough
    (mirroring its own non-Windows fallback shape, ``SimpleNamespace(Dispatch=...)``)
    lets ``SimpleNamespace`` components flow through unchanged, the same way
    the real object would after wrapping.
    """

    @staticmethod
    def _identity_dynamic(monkeypatch) -> None:
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )

    @staticmethod
    def _assembly_adapter(monkeypatch) -> PyWin32Adapter:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2  # Assembly
        return adapter

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly_document(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1  # Part, not an assembly

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_on_unknown_mate_type(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)

        result = await adapter.add_mate("part-1", "part-2", mate_type="not_a_type")

        assert result.is_error
        assert "Unknown mate type" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_on_unknown_alignment(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)

        result = await adapter.add_mate("part-1", "part-2", alignment="not_an_alignment")

        assert result.is_error
        assert "Unknown alignment" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_components_unreadable(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        adapter.currentModel.GetComponents.return_value = None

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Could not read the assembly's components" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_every_component_fails_to_wrap(
        self, monkeypatch
    ) -> None:
        """Exercises both the per-component 'continue' and the resulting
        'not found' raise: nothing wraps, so nothing can ever match."""
        adapter = self._assembly_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        adapter.currentModel.GetComponents.return_value = [object(), object()]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Component(s) not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_named_components_are_not_in_the_assembly(
        self, monkeypatch
    ) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="other-part-1"),
            SimpleNamespace(Name2="other-part-2"),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Component(s) not found: part-1, part-2" in (result.error or "")
        assert "other-part-1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_entity_not_found_on_component(
        self, monkeypatch
    ) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: None),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: None),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "not found on part-1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_entity_selection_fails(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: False)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Failed to select" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_selected_count_is_not_two(self, monkeypatch) -> None:
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: True)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]
        adapter.currentModel.SelectionManager.GetSelectedObjectCount2.return_value = 1

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "Expected 2 selected entities" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_solidworks_rejects_the_mate(self, monkeypatch) -> None:
        """error_status=2 mirrors the documented real measurement: this build
        reports 1 for success, so anything else (including a successful-looking
        object with an unhelpful status) is treated as a rejection."""
        adapter = self._assembly_adapter(monkeypatch)
        self._identity_dynamic(monkeypatch)
        feature = SimpleNamespace(Select2=lambda append, mark: True)
        adapter.currentModel.GetComponents.return_value = [
            SimpleNamespace(Name2="part-1", FeatureByName=lambda e: feature),
            SimpleNamespace(Name2="part-2", FeatureByName=lambda e: feature),
        ]
        adapter.currentModel.SelectionManager.GetSelectedObjectCount2.return_value = 2
        adapter.currentModel.AddMate5.return_value = SimpleNamespace()

        def fake_byref_int():
            return SimpleNamespace(value=2)  # not 1 == success per the docstring

        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._byref_int", fake_byref_int
        )

        result = await adapter.add_mate("part-1", "part-2")

        assert result.is_error
        assert "SolidWorks rejected the coincident mate" in (result.error or "")


class TestSaveFileLegacyFallback:
    """Cover ``save_file``'s legacy ``Save()`` fallback and unwritten-file raise."""

    @pytest.mark.asyncio
    async def test_falls_back_to_save_and_errors_when_file_not_written(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        # A path that does not exist, so the final os.path.exists check fails
        # regardless of what the mocked Save3/Save calls "do".
        target = str(tmp_path / "does_not_exist.sldprt")

        model = MagicMock()
        model.GetPathName.return_value = target
        model.Save3.return_value = None  # forces the legacy Save() fallback
        adapter.currentModel = model

        result = await adapter.save_file(target)

        assert result.is_error
        assert "File not written after save" in (result.error or "")
        model.Save.assert_called_once()


# ---------------------------------------------------------------------------
# Second pass: every remaining line from the combined (mock + real-SW)
# coverage report, closed one by one per the user's explicit request.
# ---------------------------------------------------------------------------


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

    def test_errors_when_no_axis_created_but_counts_readable(
        self, monkeypatch
    ) -> None:
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

        result = _mirror_feature_impl(
            adapter, ["Loft1"], "Right Plane", True, False
        )

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


# ---------------------------------------------------------------------------
# io.py: module-level helper functions
# ---------------------------------------------------------------------------


class TestViewNamesHelper:
    def test_skips_unwrappable_views(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        drawing = SimpleNamespace(GetViews=lambda: [["sheet_obj", "view_obj1"]])

        result = _view_names(adapter, drawing)

        assert result == []


class TestComponentTransformsHelper:
    def test_skips_component_that_is_none(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [object()]

        result = _component_transforms(adapter, assembly)

        assert result == {}

    def test_skips_non_list_transform_data(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(
            Name2="part-1", Transform2=SimpleNamespace(ArrayData="not-a-list")
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_transforms(adapter, assembly)

        assert result == {}

    def test_skips_transform_with_unconvertible_values(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(
            Name2="part-1",
            Transform2=SimpleNamespace(ArrayData=["not-a-number"] * 16),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_transforms(adapter, assembly)

        assert result == {}


class TestInterferenceDetailsHelper:
    def test_skips_unwrappable_interference(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )

        result = _interference_details(adapter, [object()])

        assert result == []

    def test_volume_conversion_failure_reports_none(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        item = SimpleNamespace(
            Volume="not-a-number", GetComponentCount=lambda: 2, Components=[]
        )

        result = _interference_details(adapter, [item])

        assert result[0]["volume_mm3"] is None

    def test_skips_unwrappable_nested_component(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(
                Dispatch=lambda obj: None if isinstance(obj, str) else obj
            ),
        )
        item = SimpleNamespace(
            Volume=1e-6, GetComponentCount=lambda: 1, Components=["raw-string"]
        )

        result = _interference_details(adapter, [item])

        assert result[0]["components"] == []


class TestComponentPairsHelper:
    def test_unwrappable_component_reported_as_unnamed(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: None),
        )
        assembly = MagicMock()
        assembly.GetComponents.return_value = [object()]

        result = _component_pairs(adapter, assembly)

        assert result == [("<unnamed>", None)]

    def test_falls_back_to_get_path_name_when_name2_empty(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        component = SimpleNamespace(Name2="", GetPathName=lambda: "C:/parts/a.sldprt")
        assembly = MagicMock()
        assembly.GetComponents.return_value = [component]

        result = _component_pairs(adapter, assembly)

        assert result == [("C:/parts/a.sldprt", component)]


# ---------------------------------------------------------------------------
# io.py: insert_component / list_components
# ---------------------------------------------------------------------------


class TestInsertComponentMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.insert_component("C:/parts/a.sldprt", 0, 0, 0)
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_file_not_found(self, monkeypatch, tmp_path) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        result = await adapter.insert_component(
            str(tmp_path / "does-not-exist.sldprt"), 0, 0, 0
        )
        assert result.is_error
        assert "Component file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_opendoc6_returns_nothing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = None

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        assert "OpenDoc6 returned nothing" in (result.error or "")

    @pytest.mark.asyncio
    async def test_falls_back_to_add_component5_and_still_fails(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        adapter.currentModel.GetComponents.return_value = []
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        adapter.currentModel.AddComponent4.return_value = None
        adapter.currentModel.AddComponent5.return_value = None

        result = await adapter.insert_component(__file__, 0, 0, 0)

        assert result.is_error
        adapter.currentModel.AddComponent5.assert_called_once()
        assert "Component was not inserted" in (result.error or "")


class TestListComponentsMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.list_components()
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_not_an_assembly(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 1

        result = await adapter.list_components()

        assert result.is_error
        assert "requires an assembly document" in (result.error or "")


# ---------------------------------------------------------------------------
# io.py: _place_view / create_drawing_view / add_drawing_view
# ---------------------------------------------------------------------------


class TestPlaceViewMoreErrors:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.create_drawing_view({"model_path": __file__})
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_scale_parse_failure_is_absorbed_not_raised(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.GetViews.return_value = None

        # "1:1" cannot convert via float() - if the except branch (1794-1798)
        # did not absorb it, this would raise ValueError instead of
        # returning a normal AdapterResult.
        result = await adapter.create_drawing_view(
            {"model_path": __file__, "scale": "1:1"}
        )

        assert result.is_error  # a normal error result, not an exception

    @pytest.mark.asyncio
    async def test_errors_when_view_count_unchanged(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        adapter.currentModel.GetViews.return_value = None

        result = await adapter.create_drawing_view({"model_path": __file__})

        assert result.is_error
        assert "View was not created" in (result.error or "")

    @pytest.mark.asyncio
    async def test_applies_scale_when_view_is_created(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.swApp = MagicMock()
        adapter.swApp.OpenDoc6.return_value = MagicMock()
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        view_names_calls = iter([[], ["Drawing View1"]])
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._view_names",
            lambda adapter, drawing: next(view_names_calls),
        )
        adapter.currentModel.CreateDrawViewFromModelView3.return_value = (
            SimpleNamespace()
        )

        result = await adapter.create_drawing_view(
            {"model_path": __file__, "scale": "2.0"}
        )

        assert result.is_success
        assert result.data["name"] == "Drawing View1"


class TestAddDrawingViewDelegates:
    @pytest.mark.asyncio
    async def test_add_drawing_view_reaches_place_view(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None

        result = await adapter.add_drawing_view({"model_path": __file__})

        assert result.is_error
        assert "No active model" in (result.error or "")


class TestCreateTechnicalDrawingMoreErrors:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.create_technical_drawing({"model_path": __file__})
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_path_missing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.create_technical_drawing({})

        assert result.is_error
        assert "A model path is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_errors_when_model_file_not_found(
        self, monkeypatch, tmp_path
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.create_technical_drawing(
            {"model_path": str(tmp_path / "does-not-exist.sldprt")}
        )

        assert result.is_error
        assert "Model file not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_first_angle_projection_calls_the_first_angle_overload(
        self, monkeypatch
    ) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.GetViews.return_value = None

        result = await adapter.create_technical_drawing(
            {"model_path": __file__, "projection": "first_angle"}
        )

        assert result.is_error  # no views appear either way; that's fine here
        adapter.currentModel.Create1stAngleViews2.assert_called_once()
        adapter.currentModel.Create3rdAngleViews2.assert_not_called()


class TestAddNoteMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_text_missing(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3

        result = await adapter.add_note({})

        assert result.is_error
        assert "add_note requires text" in (result.error or "")

    @pytest.mark.asyncio
    async def test_accepts_an_explicit_position_list(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 3
        adapter.currentModel.InsertNote.return_value = None

        result = await adapter.add_note({"text": "hi", "position": [10.0, 20.0]})

        assert result.is_error
        assert "InsertNote returned nothing" in (result.error or "")


class TestListDrawingViewsGuard:
    @pytest.mark.asyncio
    async def test_guard_passthrough_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.list_drawing_views()
        assert result.is_error
        assert "No active model" in (result.error or "")


class TestCheckInterferenceMoreErrors:
    @pytest.mark.asyncio
    async def test_errors_when_no_active_model(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = None
        result = await adapter.check_interference()
        assert result.is_error
        assert "No active model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_filters_by_wanted_component_names(self, monkeypatch) -> None:
        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter.currentModel.GetType.return_value = 2
        monkeypatch.setattr(
            "solidworks_mcp.adapters.solidworks.io._dynamic",
            SimpleNamespace(Dispatch=lambda obj: obj),
        )
        manager = MagicMock()
        manager.GetInterferenceCount.return_value = 1
        item = SimpleNamespace(
            Volume=1e-6,
            GetComponentCount=lambda: 2,
            Components=[
                SimpleNamespace(Name2="part-1"),
                SimpleNamespace(Name2="part-2"),
            ],
        )
        manager.GetInterferences.return_value = [item]
        adapter.currentModel.InterferenceDetectionManager = manager

        result = await adapter.check_interference({"components": ["part-1"]})

        assert result.is_success
        assert result.data["interference_found"] is True
        assert result.data["scope"] == ["part-1"]
