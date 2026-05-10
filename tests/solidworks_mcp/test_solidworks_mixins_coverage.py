"""Targeted coverage tests for the adapters/solidworks mixin modules.

Exercises the specific code paths missed by the main branch test suite:
- SolidWorksFeaturesMixin.create_sweep / create_loft
- SolidWorksIOMixin._adapter staticmethod and not-connected error returns
- SolidWorksSketchMixin geometry-helper methods (_point_xyz, _set_point_xyz, etc.)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from src.solidworks_mcp.adapters.solidworks.io import SolidWorksIOMixin
from src.solidworks_mcp.adapters.solidworks.sketch import SolidWorksSketchMixin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_adapter(monkeypatch) -> PyWin32Adapter:
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.pywin32_adapter.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
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
        from unittest.mock import AsyncMock, patch

        adapter = _build_adapter(monkeypatch)
        adapter.currentModel = MagicMock()
        adapter._last_sketch_name = "Sketch1"

        expected = {"fully_defined": True, "sketch_name": "Sketch1"}

        with patch(
            "src.solidworks_mcp.adapters.solidworks.sketch._check_sketch_fully_defined_impl",
        ) as mock_fn:
            from src.solidworks_mcp.adapters.base import (
                AdapterResult,
                AdapterResultStatus,
            )

            mock_fn.return_value = AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=expected
            )
            result = await adapter.check_sketch_fully_defined("Sketch1")

        assert result.is_success
        assert result.data == expected
