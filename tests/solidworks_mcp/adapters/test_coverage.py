"""Coverage tests for adapters: base.py, circuit_breaker.py, mock_adapter.py, connection_pool.py."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    SolidWorksFeature,
)
from solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreakerAdapter,
    CircuitState,
)
from solidworks_mcp.adapters.connection_pool import (
    ConnectionPool,
    ConnectionPoolAdapter,
)
from solidworks_mcp.adapters.mock_adapter import (
    MockSolidWorksAdapter,
    _BoolCallable,
)

# ---------------------------------------------------------------------------
# AdapterHealth / base.py
# ---------------------------------------------------------------------------


class TestAdapterHealthCoverage:
    """Test adapter health coverage."""

    def test_getitem_fallback_unknown_key(self):
        """Line 52 — unknown key falls through to model_dump().get(key)."""
        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=5,
            average_response_time=0.1,
            connection_status="connected",
        )
        # "success_count" is a real field but not one of the legacy shortcuts
        result = health["success_count"]
        assert result == 5

    def test_getitem_fallback_missing_key_returns_none(self):
        """Test getitem fallback missing key returns none."""

        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="connected",
        )
        assert health["nonexistent_field"] is None

    def test_contains_nonlegacy_key(self):
        """Line 67 — non-legacy key checked via model_dump()."""
        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="connected",
        )
        assert "healthy" in health  # real field, not in legacy_keys
        assert "nonexistent" not in health  # not in model_dump either

    def test_contains_legacy_keys_always_true(self):
        """Test contains legacy keys always true."""

        health = AdapterHealth(
            healthy=False,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="disconnected",
        )
        for key in ("status", "connected", "adapter_type", "version", "uptime"):
            assert key in health

    def test_getitem_status_unhealthy(self):
        """Test getitem status unhealthy."""

        health = AdapterHealth(
            healthy=False,
            last_check=datetime.now(),
            error_count=0,
            success_count=0,
            average_response_time=0.0,
            connection_status="disconnected",
        )
        assert health["status"] == "unhealthy"


class TestSolidWorksFeatureCoverage:
    """Test solid works feature coverage."""

    def test_getitem_returns_parameter_value(self):
        """Line 148-150 — feature["key"] checks parameters first."""
        feature = SolidWorksFeature(
            id="f1",
            name="Boss-Extrude1",
            type="Extrusion",
            parameters={"depth": 10.0},
        )
        assert feature["depth"] == 10.0

    def test_getitem_fallback_to_model_dump(self):
        """Line 150 — unknown key falls through to model_dump()."""
        feature = SolidWorksFeature(id="f1", name="Boss1", type="Extrusion")
        assert feature["name"] == "Boss1"
        assert feature["nonexistent"] is None


class TestAdapterBaseInitCoverage:
    """Test adapter base init coverage."""

    def test_init_with_model_dump_config(self):
        """Line 222 — config with model_dump() method normalized via it."""

        class FakeConfig:
            """Test fake config."""

            def model_dump(self):
                """Test model dump."""

                return {"mock_solidworks": True, "timeout": 30}

        adapter = MockSolidWorksAdapter(FakeConfig())
        assert adapter.config_dict == {"mock_solidworks": True, "timeout": 30}

    @pytest.mark.asyncio
    async def test_save_file_default_not_implemented(self):
        """Line 269 — base save_file returns error."""
        adapter = MockSolidWorksAdapter({})
        # MockSolidWorksAdapter overrides save_file, so call the base directly
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.save_file(adapter)
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in result.error

    @pytest.mark.asyncio
    async def test_add_arc_not_implemented(self):
        """Line 378 — base add_arc returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_arc(None, 0, 0, 1, 0, 0, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_spline_not_implemented(self):
        """Line 385 — base add_spline returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_spline(None, [])
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_centerline_not_implemented(self):
        """Line 394 — base add_centerline returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.add_centerline(None, 0, 0, 1, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_create_cut_not_implemented(self):
        """Line 504 — base create_cut returns error."""
        from solidworks_mcp.adapters.base import SolidWorksAdapter

        result = await SolidWorksAdapter.create_cut(None, "Sketch1", 5.0)
        assert result.status == AdapterResultStatus.ERROR

    def test_get_metrics_returns_copy(self):
        """Line 555 — get_metrics returns a copy."""
        adapter = MockSolidWorksAdapter({})
        metrics = adapter.get_metrics()
        assert "operations_count" in metrics
        metrics["operations_count"] = 9999
        # Original not mutated
        assert adapter.get_metrics()["operations_count"] != 9999

    @pytest.mark.asyncio
    async def test_add_sketch_circle_alias(self):
        """Line 500 — add_sketch_circle delegates to add_circle."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        result = await adapter.add_sketch_circle(0.0, 0.0, 5.0, construction=False)
        assert result.status == AdapterResultStatus.SUCCESS


# ---------------------------------------------------------------------------
# _BoolCallable — mock_adapter.py line 52
# ---------------------------------------------------------------------------


class TestBoolCallableCoverage:
    """Test bool callable coverage."""

    def test_call_returns_bool(self):
        """Line 52 — __call__ returns bool(getter())."""
        bc = _BoolCallable(lambda: True)
        assert bc() is True

    def test_call_false(self):
        """Test call false."""

        bc = _BoolCallable(lambda: False)
        assert bc() is False


# ---------------------------------------------------------------------------
# MockSolidWorksAdapter success paths — lines 237-317, 662-667
# ---------------------------------------------------------------------------


class TestMockAdapterSuccessPaths:
    """Test mock adapter success paths."""

    @pytest.mark.asyncio
    async def test_get_model_info_success(self):
        """Lines 237-255 — get_model_info with active model."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part(name="TestPart")

        result = await adapter.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS
        assert "title" in result.data
        assert "feature_count" in result.data

    @pytest.mark.asyncio
    async def test_list_features_with_actual_features(self):
        """Lines 286-300 — list_features with features in the tree (non-empty)."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        await adapter.exit_sketch()
        await adapter.create_extrusion(ExtrusionParameters(depth=10.0))

        result = await adapter.list_features(include_suppressed=False)
        assert result.status == AdapterResultStatus.SUCCESS
        assert isinstance(result.data, list)

    @pytest.mark.asyncio
    async def test_list_features_seeded_when_empty(self):
        """Lines 272-284 — list_features with no real features returns seeded list."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.list_features()
        assert result.status == AdapterResultStatus.SUCCESS
        assert len(result.data) > 0
        assert any(f["name"] == "Origin" for f in result.data)

    @pytest.mark.asyncio
    async def test_list_configurations_non_default_config(self):
        """Lines 314-316 — non-Default active config produces [Default, active]."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        # Create a model with a non-default config name
        await adapter.create_part()
        # Directly set configuration to a custom name
        adapter._current_model.configuration = "HighTolerance"

        result = await adapter.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS
        assert "Default" in result.data
        assert "HighTolerance" in result.data

    @pytest.mark.asyncio
    async def test_add_centerline_success(self):
        """Lines 662-670 — add_centerline with active sketch returns centerline id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_centerline(0.0, 0.0, 1.0, 1.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert "Centerline" in result.data

    @pytest.mark.asyncio
    async def test_add_arc_success(self):
        """Mock add_arc returns an Arc* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_arc(0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Arc")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_arc_error_when_no_sketch(self):
        """Mock add_arc returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_arc(0.0, 0.0, 5.0, 0.0, 0.0, 5.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_spline_success(self):
        """Mock add_spline returns a Spline* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_spline(
            [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 2.5}, {"x": 10.0, "y": 0.0}]
        )
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Spline")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_spline_error_when_no_sketch(self):
        """Mock add_spline returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_spline(
            [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_spline_error_when_too_few_points(self):
        """Mock add_spline rejects single-point input."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_spline([{"x": 0.0, "y": 0.0}])
        assert result.status == AdapterResultStatus.ERROR
        assert "at least 2 points" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_ellipse_success(self):
        """Mock add_ellipse returns an Ellipse_* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_ellipse(0.0, 0.0, 60.0, 30.0)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Ellipse_")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_ellipse_error_when_no_sketch(self):
        """Mock add_ellipse returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_ellipse(0.0, 0.0, 60.0, 30.0)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_polygon_success(self):
        """Mock add_polygon returns a Polygon_<sides>sided_* id with an active sketch."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.add_polygon(0.0, 0.0, 15.0, 6)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Polygon_")
        assert result.data in adapter._sketch_entity_ids

    @pytest.mark.asyncio
    async def test_add_polygon_error_when_no_sketch(self):
        """Mock add_polygon returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.add_polygon(0.0, 0.0, 15.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_success(self):
        """Mock sketch_linear_pattern returns a LinearPattern_* id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(0.0, 0.0, 3.0)

        result = await adapter.sketch_linear_pattern(
            [circle.data], 1.0, 0.0, 10.0, 4
        )
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("LinearPattern_4x10.0_")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_error_when_no_sketch(self):
        """Mock sketch_linear_pattern returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_linear_pattern(["Line1"], 1.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_rejects_unknown_entity(self):
        """Mock sketch_linear_pattern surfaces a clear error for missing IDs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.sketch_linear_pattern(
            ["Bogus_123"], 1.0, 0.0, 10.0, 3
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_linear_pattern_input_validation(self):
        """Empty entities / count<2 / spacing<=0 / zero direction → ERROR."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(0.0, 0.0, 3.0)

        # Empty entities
        result = await adapter.sketch_linear_pattern([], 1.0, 0.0, 10.0, 3)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        # count < 2
        result = await adapter.sketch_linear_pattern(
            [circle.data], 1.0, 0.0, 10.0, 1
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "count >= 2" in (result.error or "")

        # spacing <= 0
        result = await adapter.sketch_linear_pattern(
            [circle.data], 1.0, 0.0, 0.0, 3
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "spacing > 0" in (result.error or "")

        # zero direction vector
        result = await adapter.sketch_linear_pattern(
            [circle.data], 0.0, 0.0, 10.0, 3
        )
        assert result.status == AdapterResultStatus.ERROR
        assert "non-zero direction" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_success(self):
        """Mock sketch_circular_pattern returns a CircularPattern_* id."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([circle.data], 360.0, 6)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("CircularPattern_6x360.0deg_")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_error_when_no_sketch(self):
        """Mock sketch_circular_pattern returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_circular_pattern(["Circle1"], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_rejects_unknown_entity(self):
        """Mock sketch_circular_pattern surfaces error for missing IDs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")

        result = await adapter.sketch_circular_pattern(["Bogus_999"], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_input_validation(self):
        """Empty entities / count<2 / angle<=0 → ERROR with descriptive message."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([], 360.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_circular_pattern([circle.data], 360.0, 1)
        assert result.status == AdapterResultStatus.ERROR
        assert "count >= 2" in (result.error or "")

        result = await adapter.sketch_circular_pattern([circle.data], 0.0, 6)
        assert result.status == AdapterResultStatus.ERROR
        assert "angle > 0" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_circular_pattern_partial_sweep(self):
        """Mock handles partial sweeps (e.g. 180° with 3 instances) the
        same way as a full pattern — the mock only synthesises an ID, but
        the real impl uses ``angle / (count - 1)`` for partial sweeps so
        the last instance lands at the requested total angle.
        """
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        circle = await adapter.add_circle(30.0, 0.0, 3.0)

        result = await adapter.sketch_circular_pattern([circle.data], 180.0, 3)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("CircularPattern_3x180.0deg_")

    @pytest.mark.asyncio
    async def test_sketch_mirror_success(self):
        """Mock sketch_mirror returns a Mirror_* id with valid inputs."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)
        line = await adapter.add_line(5.0, 0.0, 25.0, 0.0)

        result = await adapter.sketch_mirror([line.data], cl.data)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith(f"Mirror_{cl.data}_")

    @pytest.mark.asyncio
    async def test_sketch_mirror_error_when_no_sketch(self):
        """Mock sketch_mirror returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_mirror(["Line1"], "Centerline1")
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_mirror_rejects_unknown_entity(self):
        """Mock sketch_mirror surfaces error for unknown source entities."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)

        result = await adapter.sketch_mirror(["Bogus_999"], cl.data)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_mirror_input_validation(self):
        """Empty entities and missing/unknown mirror_line each error."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        cl = await adapter.add_centerline(0.0, -30.0, 0.0, 30.0)
        line = await adapter.add_line(5.0, 0.0, 25.0, 0.0)

        result = await adapter.sketch_mirror([], cl.data)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_mirror([line.data], "")
        assert result.status == AdapterResultStatus.ERROR
        assert "mirror_line entity ID" in (result.error or "")

        result = await adapter.sketch_mirror([line.data], "NotACenterline_42")
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown mirror_line entity" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_offset_outward_success(self):
        """Mock sketch_offset returns Offset_*_outward_* with reverse=False."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 0.0, 50.0, 0.0)

        result = await adapter.sketch_offset([line.data], 5.0, False)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Offset_5.0_outward_")

    @pytest.mark.asyncio
    async def test_sketch_offset_inward_success(self):
        """Mock sketch_offset returns Offset_*_inward_* with reverse=True."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 20.0, 50.0, 20.0)

        result = await adapter.sketch_offset([line.data], 3.0, True)
        assert result.status == AdapterResultStatus.SUCCESS
        assert result.data.startswith("Offset_3.0_inward_")

    @pytest.mark.asyncio
    async def test_sketch_offset_error_when_no_sketch(self):
        """Mock sketch_offset returns ERROR when no sketch is open."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()

        result = await adapter.sketch_offset(["Line1"], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "No active sketch" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sketch_offset_input_validation(self):
        """Empty entities / non-positive distance / unknown entity each error."""
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
        await adapter.create_sketch("Front")
        line = await adapter.add_line(0.0, 0.0, 50.0, 0.0)

        result = await adapter.sketch_offset([], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "at least one entity" in (result.error or "")

        result = await adapter.sketch_offset([line.data], 0.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "offset_distance > 0" in (result.error or "")

        result = await adapter.sketch_offset([line.data], -1.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "offset_distance > 0" in (result.error or "")

        result = await adapter.sketch_offset(["Bogus_42"], 5.0, False)
        assert result.status == AdapterResultStatus.ERROR
        assert "Unknown sketch entity" in (result.error or "")


# ---------------------------------------------------------------------------
# Real (PyWin32) circular pattern impl — fake SketchManager unit tests
# ---------------------------------------------------------------------------


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
                return AdapterResult(
                    status=AdapterResultStatus.SUCCESS, data=fn()
                )
            except Exception as exc:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR, error=str(exc)
                )

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

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Line_1"], 360.0, 6
        )

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

        result = sketch_ops._sketch_circular_pattern_impl(
            adapter, ["Slot_1"], 360.0, 6
        )

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


# ---------------------------------------------------------------------------
# CircuitBreakerAdapter — lines 119, 137, 165-173, 187, 197-198, 235, 367+
# ---------------------------------------------------------------------------


class TestCircuitBreakerCoverage:
    """Test circuit breaker coverage."""

    def _make_cb(self, failure_threshold=3, recovery_timeout=60):
        """Test make cb."""

        inner = MockSolidWorksAdapter({})
        cb = CircuitBreakerAdapter(
            adapter=inner,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        return cb, inner

    @pytest.mark.asyncio
    async def test_record_failure_half_open_to_open(self):
        """Line 119 — HALF_OPEN failure → back to OPEN."""
        cb, inner = self._make_cb(failure_threshold=1)
        await inner.connect()
        cb.state = CircuitState.HALF_OPEN
        cb._record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_record_failure_closed_to_open_logs(self):
        """Line 137 — CLOSED → OPEN after threshold (logging path)."""
        cb, inner = self._make_cb(failure_threshold=2)
        await inner.connect()
        cb._record_failure()
        assert cb.state == CircuitState.CLOSED
        cb._record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_connect_circuit_open_raises(self):
        """Line 165-166 — connect when OPEN raises exception."""
        cb, inner = self._make_cb()
        await inner.connect()
        cb.state = CircuitState.OPEN
        cb.last_failure_time = time.time()  # recent failure, won't recover

        with pytest.raises(Exception, match="open"):
            await cb.connect()

    @pytest.mark.asyncio
    async def test_connect_success_records_success(self):
        """Lines 169-170 — connect succeeds → _record_success called."""
        cb, inner = self._make_cb()
        await inner.connect()
        # Set to HALF_OPEN so _record_success does something visible
        cb.state = CircuitState.HALF_OPEN
        await cb.connect()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_connect_failure_records_failure_reraises(self):
        """Lines 171-173 — connect raises → _record_failure, re-raised."""
        inner = MockSolidWorksAdapter({})
        inner.connect = AsyncMock(side_effect=RuntimeError("connect failed"))
        cb = CircuitBreakerAdapter(adapter=inner, failure_threshold=5)

        with pytest.raises(RuntimeError, match="connect failed"):
            await cb.connect()
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_health_check_open_sets_unhealthy(self):
        """Lines 196-198 — OPEN state marks health as unhealthy."""
        cb, inner = self._make_cb()
        await inner.connect()
        await inner.create_part()
        cb.state = CircuitState.OPEN

        health = await cb.health_check()
        assert not health.healthy
        assert health.connection_status == "circuit_breaker_open"

    @pytest.mark.asyncio
    async def test_health_check_initializes_metrics_when_missing(self):
        """Health checks should create a metrics dict when the adapter returns None."""
        cb, inner = self._make_cb()
        inner.health_check = AsyncMock(
            return_value=AdapterHealth(
                healthy=True,
                last_check=datetime.now(),
                error_count=0,
                success_count=1,
                average_response_time=0.1,
                connection_status="connected",
                metrics=None,
            )
        )

        health = await cb.health_check()

        assert health.metrics is not None
        assert health.metrics["circuit_breaker"]["state"] == cb.state.value

    @pytest.mark.asyncio
    async def test_get_model_info_via_circuit_breaker(self):
        """Line 235 — get_model_info delegates through circuit breaker."""
        cb, inner = self._make_cb()
        await inner.connect()
        await inner.create_part()
        result = await cb.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_get_mass_properties_via_circuit_breaker(self):
        """Line 367 — get_mass_properties delegates through circuit breaker."""
        cb, inner = self._make_cb()
        await inner.connect()
        await inner.create_part()
        result = await cb.get_mass_properties()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_features_via_circuit_breaker(self):
        """Line 375 — list_features delegates through circuit breaker."""
        cb, inner = self._make_cb()
        await inner.connect()
        await inner.create_part()
        result = await cb.list_features()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_configurations_via_circuit_breaker(self):
        """Line 382 — list_configurations delegates through circuit breaker."""
        cb, inner = self._make_cb()
        await inner.connect()
        await inner.create_part()
        result = await cb.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_remaining_circuit_breaker_wrappers(self):
        """Cover remaining thin circuit-breaker wrapper methods."""
        cb, inner = self._make_cb()

        feature_result = AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=SolidWorksFeature(id="f1", name="Fillet1", type="Fillet"),
        )
        string_result = AdapterResult(status=AdapterResultStatus.SUCCESS, data="Dim1")
        dict_result = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"fully_defined": True}
        )
        macro_result = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"macro": "ok"}
        )
        export_result = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"path": "preview.png"}
        )
        file_result = AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)
        model_result = AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

        inner.create_part = AsyncMock(return_value=model_result)
        inner.create_assembly = AsyncMock(return_value=model_result)
        inner.create_cut_extrude = AsyncMock(return_value=feature_result)
        inner.add_fillet = AsyncMock(return_value=feature_result)
        inner.add_arc = AsyncMock(
            return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="Arc1")
        )
        inner.add_sketch_dimension = AsyncMock(return_value=string_result)
        inner.check_sketch_fully_defined = AsyncMock(return_value=dict_result)
        inner.execute_macro = AsyncMock(return_value=macro_result)
        inner.export_image = AsyncMock(return_value=export_result)
        inner.export_file = AsyncMock(return_value=file_result)

        async def passthrough(operation_name, operation, **kwargs):
            return await operation()

        cb._execute_with_circuit_breaker = AsyncMock(side_effect=passthrough)
        cb._invoke_with_optional_args = AsyncMock(return_value=file_result)

        extrusion = ExtrusionParameters(depth=2.0)

        part_result = await cb.create_part(name="MyPart", units="mm")
        default_part_result = await cb.create_part()
        assembly_result = await cb.create_assembly(name="MyAssembly")
        default_assembly_result = await cb.create_assembly()
        cut_result = await cb.create_cut_extrude(extrusion)
        fillet_result = await cb.add_fillet(1.5, ["Edge1"])
        macro_exec = await cb.execute_macro({"name": "macro"})
        arc_result = await cb.add_arc(0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
        dim_result = await cb.add_sketch_dimension("Line1", None, "linear", 5.0)
        sketch_result = await cb.check_sketch_fully_defined("Sketch1")
        image_result = await cb.export_image({"output": "preview.png"})
        export_file_result = await cb.export_file("model.step", "step")

        assert part_result is file_result
        assert default_part_result is model_result
        assert assembly_result is file_result
        assert default_assembly_result is model_result
        assert cut_result is feature_result
        assert fillet_result is feature_result
        assert macro_exec is macro_result
        assert arc_result.status == AdapterResultStatus.SUCCESS
        assert dim_result is string_result
        assert sketch_result is dict_result
        assert image_result is export_result
        assert export_file_result is file_result
        cb._invoke_with_optional_args.assert_any_call(inner.create_part, "MyPart", "mm")
        cb._invoke_with_optional_args.assert_any_call(
            inner.create_assembly, "MyAssembly"
        )


# ---------------------------------------------------------------------------
# ConnectionPoolAdapter — exception paths and uncovered branches
# ---------------------------------------------------------------------------


class TestConnectionPoolAdapterCoverage:
    """Test connection pool adapter coverage."""

    @pytest.mark.asyncio
    async def test_attempt_async_exception_returns_default(self):
        """Lines 82-83 — _attempt_async catches exception, returns default."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )

        async def _raiser():
            """Test raiser."""

            raise RuntimeError("boom")

        result = await pool._attempt_async(_raiser, default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_attempt_async_with_error_returns_tuple(self):
        """Lines 91-92 — _attempt_async_with_error returns (None, exc)."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )

        async def _raiser():
            """Test raiser."""

            raise ValueError("bad value")

        result, err = await pool._attempt_async_with_error(_raiser)
        assert result is None
        assert isinstance(err, ValueError)

    @pytest.mark.asyncio
    async def test_attempt_sync_exception_returns_default(self):
        """Lines 98-101 — _attempt_sync catches exception, returns default."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )

        def _raiser():
            """Test raiser."""

            raise RuntimeError("sync boom")

        result = pool._attempt_sync(_raiser, default=42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_invoke_with_optional_args_type_error_retries_without(self):
        """Lines 110-114 — TypeError on call with args → retry without args."""

        class StrictAdapter:
            """Test strict adapter."""

            async def strict_method(self):
                """Test strict method."""

                return "ok"

        adapter = StrictAdapter()
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        result = await pool._invoke_with_optional_args(
            adapter, "strict_method", "extra_arg"
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_replace_failed_adapter_exception_returns_exc(self):
        """Lines 126-127 — _replace_failed_adapter returns the exception when connect fails."""
        fail_adapter = MockSolidWorksAdapter({})
        fail_adapter.connect = AsyncMock(side_effect=RuntimeError("no connection"))

        pool = ConnectionPoolAdapter(adapter_factory=lambda: fail_adapter, pool_size=1)
        result = await pool._replace_failed_adapter()
        assert isinstance(result, RuntimeError)

    @pytest.mark.asyncio
    async def test_acquire_delegates_to_get_adapter(self):
        """Line 156 — acquire() wraps _get_adapter."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        adapter = await pool.acquire()
        assert adapter is not None

    @pytest.mark.asyncio
    async def test_release_puts_adapter_back(self):
        """Line 168 — release() wraps _return_adapter."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        adapter = await pool.acquire()
        await pool.release(adapter)
        assert pool.available_adapters.qsize() == 1

    @pytest.mark.asyncio
    async def test_cleanup_delegates_to_disconnect(self):
        """Line 177 — cleanup() calls disconnect()."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        await pool.cleanup()
        assert not pool.is_connected()

    @pytest.mark.asyncio
    async def test_is_connected_true_when_pool_has_adapters(self):
        """Line 186 — is_connected() True when pool initialized and non-empty."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        assert pool.is_connected() is True

    @pytest.mark.asyncio
    async def test_get_adapter_timeout_raises(self):
        """Lines 197-198 — TimeoutError when no adapter available."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1, timeout=0.01
        )
        await pool.connect()
        # Drain the pool
        _ = await pool.acquire()
        # Now no adapters available — should timeout quickly
        with pytest.raises(Exception, match="No adapter available"):
            await pool._get_adapter(timeout=0.01)

    @pytest.mark.asyncio
    async def test_disconnect_logs_error_and_continues(self):
        """Line 281 — error disconnecting adapter is logged, not raised."""
        fail_adapter = MockSolidWorksAdapter({})
        fail_adapter.disconnect = AsyncMock(side_effect=RuntimeError("disc error"))

        pool = ConnectionPoolAdapter(adapter_factory=lambda: fail_adapter, pool_size=1)
        await pool.connect()
        # Should not raise even though disconnect fails
        await pool.disconnect()
        assert not pool.is_connected()

    @pytest.mark.asyncio
    async def test_health_check_with_healthy_adapter(self):
        """Line 324 — health_check accumulates response time from healthy adapters."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        health = await pool.health_check()
        assert health.healthy

    @pytest.mark.asyncio
    async def test_create_part_with_name_and_units(self):
        """Lines 380-385 — create_part with name and units uses _invoke_with_optional_args."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        result = await pool.create_part(name="MyPart", units="mm")
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_create_assembly_with_name(self):
        """Lines 402-407 — create_assembly with name uses _invoke_with_optional_args."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        result = await pool.create_assembly(name="MyAssembly")
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_get_model_info_via_pool(self):
        """Line 502 — get_model_info via pool."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        # Need active model — use pool directly after getting inner
        adapter = pool.pool[0]
        await adapter.create_part()
        result = await pool.get_model_info()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_features_via_pool(self):
        """Line 510 — list_features via pool."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        adapter = pool.pool[0]
        await adapter.create_part()
        result = await pool.list_features()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_configurations_via_pool(self):
        """Line 517 — list_configurations via pool."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        adapter = pool.pool[0]
        await adapter.create_part()
        result = await pool.list_configurations()
        assert result.status == AdapterResultStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_save_file_via_pool(self):
        """Line 361 — save_file via pool."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        await pool.connect()
        result = await pool.save_file("/tmp/test.sldprt")
        # Mock adapter returns success or error — just check it runs
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

    def test_default_adapter_factory_uses_mock_adapter(self):
        """No explicit factory should fall back to MockSolidWorksAdapter."""
        pool = ConnectionPoolAdapter(config={"mock_solidworks": True})
        created = pool.adapter_factory()
        assert isinstance(created, MockSolidWorksAdapter)

    @pytest.mark.asyncio
    async def test_initialize_pool_logs_and_skips_failed_adapter(self):
        """Pool initialization should skip adapters that fail to connect."""
        first = MockSolidWorksAdapter({})
        first.connect = AsyncMock(side_effect=RuntimeError("no connect"))
        second = MockSolidWorksAdapter({})
        calls = [first, second]
        pool = ConnectionPoolAdapter(adapter_factory=lambda: calls.pop(0), pool_size=2)

        await pool.connect()

        assert pool.size == 1
        assert pool.available_adapters.qsize() == 1

    @pytest.mark.asyncio
    async def test_initialize_pool_returns_when_marked_initialized_under_lock(self):
        """The second pool_initialized guard should exit without creating adapters."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )

        await pool._lock.acquire()
        task = asyncio.create_task(pool._initialize_pool())
        await asyncio.sleep(0)
        pool.pool_initialized = True
        pool._lock.release()
        await task

        assert pool.size == 0
        assert pool.available_adapters.qsize() == 0

    @pytest.mark.asyncio
    async def test_health_check_skips_missing_adapter_health(self):
        """Connection-pool health_check should continue when adapter health is unavailable."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        pool.pool_initialized = True
        adapter = MockSolidWorksAdapter({})
        adapter.health_check = AsyncMock(side_effect=RuntimeError("boom"))
        pool.pool = [adapter]

        health = await pool.health_check()

        assert health.healthy is False
        assert health.metrics["healthy_adapters"] == 0

    @pytest.mark.asyncio
    async def test_remaining_pool_wrappers(self):
        """Cover remaining thin connection-pool wrapper methods."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        stub = SimpleNamespace(
            create_cut_extrude=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data=SolidWorksFeature(id="f1", name="Cut1", type="Cut"),
                )
            ),
            add_fillet=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data=SolidWorksFeature(id="f2", name="Fillet1", type="Fillet"),
                )
            ),
            add_arc=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS, data="Arc1"
                )
            ),
            add_sketch_dimension=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS, data="Dim1"
                )
            ),
            check_sketch_fully_defined=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data={"fully_defined": True},
                )
            ),
            execute_macro=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data={"macro": "ok"},
                )
            ),
            export_image=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data={"path": "preview.png"},
                )
            ),
            export_file=AsyncMock(
                return_value=AdapterResult(
                    status=AdapterResultStatus.SUCCESS, data=None
                )
            ),
        )

        async def passthrough(operation_name, operation):
            return await operation(stub)

        pool._execute_with_pool = AsyncMock(side_effect=passthrough)

        extrusion = ExtrusionParameters(depth=3.0)

        cut_result = await pool.create_cut_extrude(extrusion)
        fillet_result = await pool.add_fillet(2.0, ["Edge1"])
        macro_result = await pool.execute_macro({"name": "macro"})
        arc_result = await pool.add_arc(0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
        dim_result = await pool.add_sketch_dimension("Line1", None, "linear", 2.5)
        sketch_result = await pool.check_sketch_fully_defined("Sketch1")
        image_result = await pool.export_image({"output": "preview.png"})
        export_file_result = await pool.export_file("model.step", "step")

        assert cut_result.data.name == "Cut1"
        assert fillet_result.data.name == "Fillet1"
        assert macro_result.data["macro"] == "ok"
        assert arc_result.data == "Arc1"
        assert dim_result.data == "Dim1"
        assert sketch_result.data["fully_defined"] is True
        assert image_result.data["path"] == "preview.png"
        assert export_file_result.status == AdapterResultStatus.SUCCESS


# ---------------------------------------------------------------------------
# Legacy ConnectionPool — wait loop (621-623) and async close (653)
# ---------------------------------------------------------------------------


class TestConnectionPoolLegacyCoverage:
    """Test connection pool legacy coverage."""

    @pytest.mark.asyncio
    async def test_acquire_wait_loop_then_gets_connection(self):
        """Lines 621-623 — waits when all connections in use, gets one after release."""
        created = []

        async def create_conn():
            """Test create conn."""

            obj = SimpleNamespace(id=len(created))
            created.append(obj)
            return obj

        pool = ConnectionPool(create_connection=create_conn, max_size=1, timeout=1.0)
        conn1 = await pool.acquire()
        assert conn1 is not None

        # Release after short delay from background task
        async def _release_soon():
            """Test release soon."""

            await asyncio.sleep(0.02)
            await pool.release(conn1)

        asyncio.create_task(_release_soon())
        conn2 = await pool.acquire()
        assert conn2 is conn1  # same object returned from _available

    @pytest.mark.asyncio
    async def test_cleanup_with_async_close(self):
        """Line 653 — cleanup awaits coroutine-based close()."""
        closed = []

        class AsyncCloseConn:
            """Test async close conn."""

            async def close(self):
                """Test close."""

                closed.append(True)

        async def create_conn():
            """Test create conn."""

            return AsyncCloseConn()

        pool = ConnectionPool(create_connection=create_conn, max_size=1, timeout=1.0)
        conn = await pool.acquire()
        await pool.release(conn)
        await pool.cleanup()
        assert closed == [True]
