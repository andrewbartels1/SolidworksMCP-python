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
    _mirror_feature_impl,
    _pattern_circular_impl,
    _select_reference_entity,
    _suppress_feature_impl,
)
from solidworks_mcp.adapters.solidworks.io import (
    SolidWorksIOMixin,
    _payload,
    _payload_dict,
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
    async def test_errors_when_model_file_not_found(self, monkeypatch) -> None:
        adapter = self._drawing_adapter(monkeypatch)

        result = await adapter.create_drawing_view(
            {"model_path": "C:/definitely/does/not/exist.sldprt"}
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
