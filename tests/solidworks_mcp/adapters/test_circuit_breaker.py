"""Tests for ``solidworks_mcp.adapters.circuit_breaker``."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    SolidWorksAdapter,
    SolidWorksFeature,
    SolidWorksModel,
)
from solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerAdapter,
    CircuitState,
)
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
def open_circuit_breaker():
    """Return a CircuitBreakerAdapter with the "open_model" bucket already OPEN.

    Each operation gets its own breaker bucket (see CircuitBreakerAdapter's
    per-operation isolation), so forcing this fixture's target operation open
    means pre-opening that operation's specific bucket, not the legacy
    ``cb.state`` attribute (which only backs ``connect()``/``call()``).
    """
    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(
        adapter=mock,
        failure_threshold=1,
        recovery_timeout=9999.0,
    )
    # Force the "open_model" bucket to OPEN without timing dependencies
    import time

    bucket = cb._get_bucket("open_model")
    bucket.state = CircuitState.OPEN
    bucket.last_failure_time = time.time()
    return cb


@pytest.fixture
def cb_with_mock():
    """Return (CircuitBreakerAdapter, inner_mock) with a permissive mock adapter."""
    inner = AsyncMock()
    inner.add_spline = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="spline")
    )
    inner.add_polygon = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="polygon")
    )
    inner.add_ellipse = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="ellipse")
    )
    inner.sketch_linear_pattern = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_circular_pattern = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_mirror = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_offset = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.add_sketch_constraint = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.is_connected = MagicMock(return_value=False)

    cb = CircuitBreakerAdapter(adapter=inner, failure_threshold=10)
    return cb, inner


@pytest.mark.asyncio
async def test_execute_with_circuit_breaker_open_returns_error(open_circuit_breaker):
    """_execute_with_circuit_breaker should return an error AdapterResult when OPEN.

    Covers circuit_breaker.py line 205-209.
    """
    result = await open_circuit_breaker.open_model("some/path.sldprt")
    assert result.status == AdapterResultStatus.ERROR
    assert "circuit breaker" in result.error.lower() or "OPEN" in result.error


@pytest.mark.asyncio
async def test_soc_log_writes_record_when_session_set(monkeypatch, tmp_path):
    """_soc_log should call insert_tool_call_record when soc_session_id and input_dict provided.

    Covers circuit_breaker.py lines 245-263.
    """
    records: list[dict] = []
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: records.append(kw),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock, failure_threshold=5)
    cb.soc_session_id = "test-session"

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS, data={"ok": True})
    cb._soc_log("test_tool", {"param": "value"}, result_mock, 42.5)

    assert len(records) == 1
    assert records[0]["tool_name"] == "test_tool"
    assert records[0]["success"] is True


@pytest.mark.asyncio
async def test_soc_log_skips_when_no_session_id(monkeypatch):
    """_soc_log should skip when soc_session_id is falsy.

    Covers circuit_breaker.py line 243-244.
    """
    called = []
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: called.append(kw),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock)
    cb.soc_session_id = ""  # falsy

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS)
    cb._soc_log("test_tool", {"x": 1}, result_mock, 1.0)
    assert called == []


@pytest.mark.asyncio
async def test_soc_log_handles_insert_exception(monkeypatch):
    """_soc_log should swallow exceptions from insert_tool_call_record.

    Covers circuit_breaker.py lines 264-267.
    """
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("db error")),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock)
    cb.soc_session_id = "s1"

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS)
    # Should not raise
    cb._soc_log("test_tool", {"x": 1}, result_mock, 1.0)


@pytest.mark.asyncio
async def test_circuit_breaker_add_spline(cb_with_mock):
    """add_spline should route through _execute_with_circuit_breaker. Covers line 728."""
    cb, inner = cb_with_mock
    result = await cb.add_spline([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}])
    assert result.is_success
    inner.add_spline.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_polygon(cb_with_mock):
    """add_polygon should route through _execute_with_circuit_breaker. Covers line 738."""
    cb, inner = cb_with_mock
    result = await cb.add_polygon(0.0, 0.0, 5.0, 6)
    assert result.is_success
    inner.add_polygon.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_ellipse(cb_with_mock):
    """add_ellipse should route through _execute_with_circuit_breaker. Covers line 757."""
    cb, inner = cb_with_mock
    result = await cb.add_ellipse(0.0, 0.0, 3.0, 1.5)
    assert result.is_success
    inner.add_ellipse.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_linear_pattern(cb_with_mock):
    """sketch_linear_pattern should route through circuit breaker. Covers line 779."""
    cb, inner = cb_with_mock
    result = await cb.sketch_linear_pattern(["e1"], 1.0, 0.0, 5.0, 3)
    assert result.is_success
    inner.sketch_linear_pattern.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_circular_pattern(cb_with_mock):
    """sketch_circular_pattern should route through circuit breaker. Covers line 800."""
    cb, inner = cb_with_mock
    result = await cb.sketch_circular_pattern(["e1"], 90.0, 4)
    assert result.is_success
    inner.sketch_circular_pattern.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_mirror(cb_with_mock):
    """sketch_mirror should route through circuit breaker. Covers line 810."""
    cb, inner = cb_with_mock
    result = await cb.sketch_mirror(["e1"], "centerline1")
    assert result.is_success
    inner.sketch_mirror.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_offset(cb_with_mock):
    """sketch_offset should route through circuit breaker. Covers line 823."""
    cb, inner = cb_with_mock
    result = await cb.sketch_offset(["e1"], 2.5, False)
    assert result.is_success
    inner.sketch_offset.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_sketch_constraint(cb_with_mock):
    """add_sketch_constraint should route through circuit breaker. Covers line 843."""
    cb, inner = cb_with_mock
    result = await cb.add_sketch_constraint("e1", "e2", "coincident")
    assert result.is_success
    inner.add_sketch_constraint.assert_awaited_once()


@pytest.mark.asyncio
async def test_soc_create_checkpoint_returns_none_when_no_session(monkeypatch):
    """soc_create_checkpoint should return None when soc_session_id is falsy. Covers line 1051."""
    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = ""
    result = await cb.soc_create_checkpoint("my-label", "/tmp/cp.sldprt")
    assert result is None


@pytest.mark.asyncio
async def test_soc_create_checkpoint_creates_record_when_session_set(
    monkeypatch, tmp_path
):
    """soc_create_checkpoint should create a DB record when soc_session_id is set. Covers 1052-1087."""
    snapshots: list[dict] = []
    checkpoints: list[dict] = []

    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_tool_call_records",
        lambda *_a, **_kw: [],
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_model_state_snapshot",
        lambda **kw: snapshots.append(kw) or 1,
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_model_state_snapshots",
        lambda *_a, **_kw: [{"id": 42}],
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.create_soc_checkpoint",
        lambda **kw: checkpoints.append(kw) or 99,
    )

    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = "test-session"

    result = await cb.soc_create_checkpoint(
        "cp1",
        "/tmp/cp.sldprt",
        feature_tree=[{"name": "Extrude1"}],
    )
    assert result == 99
    assert len(checkpoints) == 1
    assert checkpoints[0]["label"] == "cp1"


@pytest.mark.asyncio
async def test_soc_create_checkpoint_swallows_exceptions(monkeypatch):
    """soc_create_checkpoint exceptions should be caught and return None. Covers lines 1088-1090."""
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_tool_call_records",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = "test-session"

    result = await cb.soc_create_checkpoint("cp1", "/tmp/cp.sldprt")
    assert result is None


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


class _DummyAdapter(SolidWorksAdapter):
    """Test suite for DummyAdapter."""

    async def connect(self):
        """Test helper for connect."""
        return None

    async def disconnect(self):
        """Test helper for disconnect."""
        return None

    def is_connected(self) -> bool:
        """Test helper for is connected."""
        return True

    async def health_check(self) -> AdapterHealth:
        """Test helper for health check."""
        return AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=1,
            average_response_time=0.01,
            connection_status="connected",
            metrics={"adapter_type": "dummy", "version": "test", "uptime": 1.0},
        )

    async def open_model(self, file_path: str):
        """Test helper for open model."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=SolidWorksModel(path=file_path, name="m", type="Part", is_active=True),
        )

    async def close_model(self, save: bool = False):
        """Test helper for close model."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_model_info(self):
        """Test helper for get model info."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": "m",
                "path": "p",
                "type": "Part",
                "configuration": "Default",
            },
        )

    async def list_features(
        self, include_suppressed: bool = False, max_assembly_depth: int = 2
    ):
        """Test helper for list features."""
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=[
                {
                    "name": "Sketch1",
                    "type": "ProfileFeature",
                    "suppressed": False,
                }
            ],
        )

    async def list_configurations(self):
        """Test helper for list configurations."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=["Default"])

    async def create_part(self):
        """Test helper for create part."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_assembly(self):
        """Test helper for create assembly."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_drawing(self):
        """Test helper for create drawing."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_extrusion(self, params):
        """Test helper for create extrusion."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_revolve(self, params):
        """Test helper for create revolve."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_sweep(self, params):
        """Test helper for create sweep."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_loft(self, params):
        """Test helper for create loft."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def create_sketch(self, plane: str):
        """Test helper for create sketch."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="Sketch1")

    async def add_line(self, x1: float, y1: float, x2: float, y2: float):
        """Test helper for add line."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="L1")

    async def add_circle(self, center_x: float, center_y: float, radius: float):
        """Test helper for add circle."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="C1")

    async def add_rectangle(self, x1: float, y1: float, x2: float, y2: float):
        """Test helper for add rectangle."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data="R1")

    async def exit_sketch(self):
        """Test helper for exit sketch."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_mass_properties(self):
        """Test helper for get mass properties."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def export_file(self, file_path: str, format_type: str):
        """Test helper for export file."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def export_image(self, payload: dict):
        """Test helper for export image."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    async def get_dimension(self, name: str):
        """Test helper for get dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=1.0)

    async def set_dimension(self, name: str, value: float):
        """Test helper for set dimension."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)


@pytest.mark.asyncio
async def test_circuit_breaker_adapter_core_paths(monkeypatch):
    """Test circuit breaker adapter core paths."""
    adapter = _DummyAdapter({})
    cb = CircuitBreakerAdapter(
        adapter=adapter,
        failure_threshold=1,
        recovery_timeout=0,
        half_open_max_calls=1,
    )

    # open -> allow after timeout -> half-open (per-operation bucket)
    bucket = cb._get_bucket("ok")
    bucket.state = CircuitState.OPEN
    bucket.last_failure_time = 0
    assert cb._should_allow_request(bucket) is True
    assert bucket.state == CircuitState.HALF_OPEN

    # success in half-open closes breaker
    async def _ok():
        """Test helper for ok."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    result = await cb._execute_with_circuit_breaker("ok", _ok)
    assert result.is_success
    assert cb._get_bucket("ok").state == CircuitState.CLOSED

    # error result increments failures and opens (independent bucket)
    async def _bad_result():
        """Test helper for bad result."""
        return AdapterResult(status=AdapterResultStatus.ERROR, error="bad")

    cb.failure_threshold = 1
    res2 = await cb._execute_with_circuit_breaker("bad", _bad_result)
    assert res2.is_error
    assert cb._get_bucket("bad").state == CircuitState.OPEN

    # exception path (independent bucket, unaffected by "bad" being open)
    async def _boom():
        """Test helper for boom."""
        raise RuntimeError("boom")

    res3 = await cb._execute_with_circuit_breaker("boom", _boom)
    assert res3.is_error


@pytest.mark.asyncio
async def test_circuit_breaker_adapter_passthrough_methods(monkeypatch):
    """Test circuit breaker adapter passthrough methods."""
    cb = CircuitBreakerAdapter(adapter=_DummyAdapter({}), config={})

    async def _fake_exec(name, operation, **kwargs):
        """Test helper for fake exec."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"name": name})

    monkeypatch.setattr(cb, "_execute_with_circuit_breaker", _fake_exec)

    assert (await cb.open_model("a.sldprt")).is_success
    assert (await cb.close_model()).is_success
    assert (await cb.create_part()).is_success
    assert (await cb.create_assembly()).is_success
    assert (await cb.create_drawing()).is_success
    assert (await cb.create_extrusion({})).is_success
    assert (await cb.create_revolve({})).is_success
    assert (await cb.create_sweep({})).is_success
    assert (await cb.create_loft({})).is_success
    assert (await cb.create_sketch("Top")).is_success
    assert (await cb.add_line(0, 0, 1, 1)).is_success
    assert (await cb.add_circle(0, 0, 1)).is_success
    assert (await cb.add_rectangle(0, 0, 1, 1)).is_success
    assert (await cb.exit_sketch()).is_success
    assert (await cb.get_mass_properties()).is_success
    assert (await cb.export_file("a.step", "step")).is_success
    assert (await cb.get_dimension("D1@S")).is_success
    assert (await cb.set_dimension("D1@S", 1.0)).is_success

    await cb.disconnect()
    assert cb.is_connected() is True
    health = await cb.health_check()
    assert health.metrics and "circuit_breaker" in health.metrics


@pytest.mark.asyncio
async def test_legacy_circuit_breaker_paths():
    """Test legacy circuit breaker paths."""
    c = CircuitBreaker(
        failure_threshold=1, recovery_timeout=0.01, expected_exception=ValueError
    )

    async def _raise_once():
        """Test helper for raise once."""
        raise ValueError("x")

    with pytest.raises(ValueError):
        await c.call(_raise_once)
    assert c.state == CircuitState.OPEN

    with pytest.raises(Exception, match="Circuit breaker is open"):
        await c.call(lambda: 1)

    await asyncio.sleep(0.02)
    value = await c.call(lambda: 7)
    assert value == 7
    assert c.state == CircuitState.CLOSED


class TestCircuitBreaker:
    """Test suite for circuit breaker pattern."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initialization."""
        cb = CircuitBreaker(
            failure_threshold=3, recovery_timeout=10.0, expected_exception=Exception
        )

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_success_path(self):
        """Test circuit breaker with successful operations."""
        cb = CircuitBreakerAdapter(failure_threshold=3, recovery_timeout=10.0)

        async def success_operation():
            """Test helper for success operation."""
            return "success"

        # Successful operations should pass through
        result = await cb.call(success_operation)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker opening after failure threshold."""
        cb = CircuitBreakerAdapter(failure_threshold=2, recovery_timeout=10.0)

        async def failing_operation():
            """Test helper for failing operation."""
            raise Exception("Operation failed")

        # First failure
        with pytest.raises(RuntimeError):
            await cb.call(failing_operation)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

        # Second failure - should open circuit
        with pytest.raises(RuntimeError):
            await cb.call(failing_operation)
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 2

        # Further calls should be rejected immediately
        with pytest.raises(Exception, match="Circuit breaker is open"):
            await cb.call(failing_operation)

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        cb = CircuitBreakerAdapter(failure_threshold=1, recovery_timeout=0.1)

        async def failing_then_success():
            """Test helper for failing then success."""
            if cb.failure_count == 0:
                raise Exception("First call fails")
            return "success"

        # Trigger circuit open
        with pytest.raises(RuntimeError):
            await cb.call(failing_then_success)
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        import asyncio

        await asyncio.sleep(0.2)

        # Next call should enter half-open state
        result = await cb.call(lambda: "success")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_isolates_failures_per_operation(self):
        """A tool that keeps failing must not trip the breaker for other tools.

        Regression test for the bug reported against create_cut_extrude:
        repeated failures on one operation used to open a single
        adapter-wide CircuitState, which then rejected unrelated read-only
        calls like list_features and get_model_info too.
        """
        from solidworks_mcp.adapters.base import ExtrusionParameters

        class _PartlyFailingAdapter:
            async def create_cut_extrude(self, params):
                return AdapterResult(
                    status=AdapterResultStatus.ERROR, error="Parameter not optional"
                )

            async def list_features(self, include_suppressed, max_assembly_depth):
                return AdapterResult(status=AdapterResultStatus.SUCCESS, data=[])

            async def get_model_info(self):
                return AdapterResult(status=AdapterResultStatus.SUCCESS, data={})

        cb = CircuitBreakerAdapter(
            adapter=_PartlyFailingAdapter(), failure_threshold=2, recovery_timeout=10.0
        )
        params = ExtrusionParameters(depth=6.0)

        for _ in range(2):
            result = await cb.create_cut_extrude(params)
            assert result.status == AdapterResultStatus.ERROR

        # The cut-extrude breaker is now open ...
        tripped = await cb.create_cut_extrude(params)
        assert "Circuit breaker is open" in (tripped.error or "")

        # ... but reads on unrelated operations still go through.
        features = await cb.list_features()
        assert features.is_success
        info = await cb.get_model_info()
        assert info.is_success

    @pytest.mark.asyncio
    async def test_circuit_breaker_health_check_flags_open_operation_bucket(self):
        """health_check must report unhealthy when a per-operation bucket is
        open, even though the legacy connection-level breaker stays closed.
        """
        from datetime import datetime

        from solidworks_mcp.adapters.base import AdapterHealth, ExtrusionParameters

        class _AlwaysFailingCutAdapter:
            async def health_check(self):
                return AdapterHealth(
                    healthy=True,
                    last_check=datetime.now(),
                    error_count=0,
                    success_count=1,
                    average_response_time=0.01,
                    connection_status="connected",
                )

            async def create_cut_extrude(self, params):
                return AdapterResult(status=AdapterResultStatus.ERROR, error="boom")

        cb = CircuitBreakerAdapter(
            adapter=_AlwaysFailingCutAdapter(), failure_threshold=1, recovery_timeout=10.0
        )
        params = ExtrusionParameters(depth=6.0)

        await cb.create_cut_extrude(params)  # opens the "create_cut_extrude" bucket

        health = await cb.health_check()
        assert health.healthy is False
        assert "create_cut_extrude" in health.connection_status
        assert (
            health.metrics["circuit_breaker_operations"]["create_cut_extrude"]["state"]
            == "open"
        )
        # The legacy connection-level bucket (used by connect()) is untouched.
        assert health.metrics["circuit_breaker"]["state"] == "closed"


#: Capabilities added on this branch.
CAPABILITIES = [
    "insert_component",
    "list_components",
    "add_mate",
]


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_wrappers_do_not_silently_fall_through_to_base(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


CAPABILITIESFeatureEditingCapability = ["delete_feature", "suppress_feature", "rename_feature", "undo"]


@pytest.mark.parametrize("capability", CAPABILITIESFeatureEditingCapability)
def test_wrappers_do_not_silently_fall_through_to_base_feature_editing(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


CAPABILITY = "check_interference"


def test_wrappers_do_not_silently_fall_through_to_base_interference() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert CAPABILITY in vars(cls), (
            f"{cls.__name__} inherits {CAPABILITY} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


CAPABILITYMirrorCapability = "mirror_feature"


def test_wrappers_do_not_silently_fall_through_to_base_mirror() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert CAPABILITYMirrorCapability in vars(cls), (
            f"{cls.__name__} inherits {CAPABILITYMirrorCapability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


def test_wrappers_do_not_silently_fall_through_to_base_multibody() -> None:
    """The breaker and pool define their own pass-through, not inherit the stub."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert "save_body_as_part" in vars(cls), (
            f"{cls.__name__} inherits save_body_as_part from the base adapter"
        )


CAPABILITIESOpenDocumentsCapability = ["list_open_documents", "activate_document"]


@pytest.mark.parametrize("capability", CAPABILITIESOpenDocumentsCapability)
def test_wrappers_do_not_silently_fall_through_to_base_open_documents(capability: str) -> None:
    """The breaker and pool define their own pass-through, not inherit the stub."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter"
        )


CAPABILITYPatternCapability = "pattern_circular"


def test_wrappers_do_not_silently_fall_through_to_base_pattern() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert CAPABILITYPatternCapability in vars(cls), (
            f"{cls.__name__} inherits {CAPABILITYPatternCapability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


#: Reference-geometry capabilities on ``SolidWorksFeaturesMixin``.
CAPABILITIESReferenceGeometryCapability = [
    "create_reference_plane",
    "create_axis",
    "create_reference_point",
]


@pytest.mark.parametrize("capability", CAPABILITIESReferenceGeometryCapability)
def test_wrappers_do_not_silently_fall_through_to_base_reference_geometry(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )


def test_wrappers_do_not_silently_fall_through_to_base_set_units() -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert "set_units" in vars(cls), (
            f"{cls.__name__} inherits set_units from the base adapter, so calls "
            "to it return 'not implemented' instead of reaching the real adapter"
        )


#: Capabilities added on this branch. These names are a contract with the
#: gates in ``tools/drawing.py`` — see the module docstring.
CAPABILITIESDrawingCapabilities = [
    "create_drawing_view",
    "add_drawing_view",
    "create_technical_drawing",
    "add_note",
    "list_drawing_views",
    "auto_center_marks",
]


@pytest.mark.parametrize("capability", CAPABILITIESDrawingCapabilities)
def test_wrappers_do_not_silently_fall_through_to_base_drawing(capability: str) -> None:
    """The breaker and pool must define their own pass-through, not inherit."""
    for cls in (CircuitBreakerAdapter, ConnectionPoolAdapter):
        assert capability in vars(cls), (
            f"{cls.__name__} inherits {capability} from the base adapter, so "
            "calls to it return 'not implemented' instead of reaching the real "
            "adapter"
        )
