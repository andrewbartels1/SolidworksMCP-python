"""Coverage tests for adapters: base.py, circuit_breaker.py, mock_adapter.py, connection_pool.py."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResultStatus,
    ExtrusionParameters,
    SolidWorksFeature,
)
from src.solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreakerAdapter,
    CircuitState,
)
from src.solidworks_mcp.adapters.connection_pool import ConnectionPool, ConnectionPoolAdapter
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter, _BoolCallable


# ---------------------------------------------------------------------------
# AdapterHealth / base.py
# ---------------------------------------------------------------------------


class TestAdapterHealthCoverage:
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
        health = AdapterHealth(
            healthy=True, last_check=datetime.now(), error_count=0, success_count=0,
            average_response_time=0.0, connection_status="connected",
        )
        assert health["nonexistent_field"] is None

    def test_contains_nonlegacy_key(self):
        """Line 67 — non-legacy key checked via model_dump()."""
        health = AdapterHealth(
            healthy=True, last_check=datetime.now(), error_count=0, success_count=0,
            average_response_time=0.0, connection_status="connected",
        )
        assert "healthy" in health          # real field, not in legacy_keys
        assert "nonexistent" not in health  # not in model_dump either

    def test_contains_legacy_keys_always_true(self):
        health = AdapterHealth(
            healthy=False, last_check=datetime.now(), error_count=0, success_count=0,
            average_response_time=0.0, connection_status="disconnected",
        )
        for key in ("status", "connected", "adapter_type", "version", "uptime"):
            assert key in health

    def test_getitem_status_unhealthy(self):
        health = AdapterHealth(
            healthy=False, last_check=datetime.now(), error_count=0, success_count=0,
            average_response_time=0.0, connection_status="disconnected",
        )
        assert health["status"] == "unhealthy"


class TestSolidWorksFeatureCoverage:
    def test_getitem_returns_parameter_value(self):
        """Line 148-150 — feature["key"] checks parameters first."""
        feature = SolidWorksFeature(
            id="f1", name="Boss-Extrude1", type="Extrusion",
            parameters={"depth": 10.0},
        )
        assert feature["depth"] == 10.0

    def test_getitem_fallback_to_model_dump(self):
        """Line 150 — unknown key falls through to model_dump()."""
        feature = SolidWorksFeature(id="f1", name="Boss1", type="Extrusion")
        assert feature["name"] == "Boss1"
        assert feature["nonexistent"] is None


class TestAdapterBaseInitCoverage:
    def test_init_with_model_dump_config(self):
        """Line 222 — config with model_dump() method normalized via it."""

        class FakeConfig:
            def model_dump(self):
                return {"mock_solidworks": True, "timeout": 30}

        adapter = MockSolidWorksAdapter(FakeConfig())
        assert adapter.config_dict == {"mock_solidworks": True, "timeout": 30}

    @pytest.mark.asyncio
    async def test_save_file_default_not_implemented(self):
        """Line 269 — base save_file returns error."""
        adapter = MockSolidWorksAdapter({})
        # MockSolidWorksAdapter overrides save_file, so call the base directly
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter
        result = await SolidWorksAdapter.save_file(adapter)
        assert result.status == AdapterResultStatus.ERROR
        assert "not implemented" in result.error

    @pytest.mark.asyncio
    async def test_add_arc_not_implemented(self):
        """Line 378 — base add_arc returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter
        result = await SolidWorksAdapter.add_arc(None, 0, 0, 1, 0, 0, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_spline_not_implemented(self):
        """Line 385 — base add_spline returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter
        result = await SolidWorksAdapter.add_spline(None, [])
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_add_centerline_not_implemented(self):
        """Line 394 — base add_centerline returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter
        result = await SolidWorksAdapter.add_centerline(None, 0, 0, 1, 1)
        assert result.status == AdapterResultStatus.ERROR

    @pytest.mark.asyncio
    async def test_create_cut_not_implemented(self):
        """Line 504 — base create_cut returns error."""
        from src.solidworks_mcp.adapters.base import SolidWorksAdapter
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
    def test_call_returns_bool(self):
        """Line 52 — __call__ returns bool(getter())."""
        bc = _BoolCallable(lambda: True)
        assert bc() is True

    def test_call_false(self):
        bc = _BoolCallable(lambda: False)
        assert bc() is False


# ---------------------------------------------------------------------------
# MockSolidWorksAdapter success paths — lines 237-317, 662-667
# ---------------------------------------------------------------------------


class TestMockAdapterSuccessPaths:
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
        model = await adapter.create_part()
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


# ---------------------------------------------------------------------------
# CircuitBreakerAdapter — lines 119, 137, 165-173, 187, 197-198, 235, 367+
# ---------------------------------------------------------------------------


class TestCircuitBreakerCoverage:
    def _make_cb(self, failure_threshold=3, recovery_timeout=60):
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


# ---------------------------------------------------------------------------
# ConnectionPoolAdapter — exception paths and uncovered branches
# ---------------------------------------------------------------------------


class TestConnectionPoolAdapterCoverage:
    @pytest.mark.asyncio
    async def test_attempt_async_exception_returns_default(self):
        """Lines 82-83 — _attempt_async catches exception, returns default."""
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )

        async def _raiser():
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
            raise RuntimeError("sync boom")

        result = pool._attempt_sync(_raiser, default=42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_invoke_with_optional_args_type_error_retries_without(self):
        """Lines 110-114 — TypeError on call with args → retry without args."""

        class StrictAdapter:
            async def strict_method(self):
                return "ok"

        adapter = StrictAdapter()
        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: MockSolidWorksAdapter({}), pool_size=1
        )
        result = await pool._invoke_with_optional_args(adapter, "strict_method", "extra_arg")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_replace_failed_adapter_exception_returns_exc(self):
        """Lines 126-127 — _replace_failed_adapter returns the exception when connect fails."""
        fail_adapter = MockSolidWorksAdapter({})
        fail_adapter.connect = AsyncMock(side_effect=RuntimeError("no connection"))

        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: fail_adapter, pool_size=1
        )
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


# ---------------------------------------------------------------------------
# Legacy ConnectionPool — wait loop (621-623) and async close (653)
# ---------------------------------------------------------------------------


class TestConnectionPoolLegacyCoverage:
    @pytest.mark.asyncio
    async def test_acquire_wait_loop_then_gets_connection(self):
        """Lines 621-623 — waits when all connections in use, gets one after release."""
        created = []

        async def create_conn():
            obj = SimpleNamespace(id=len(created))
            created.append(obj)
            return obj

        pool = ConnectionPool(create_connection=create_conn, max_size=1, timeout=1.0)
        conn1 = await pool.acquire()
        assert conn1 is not None

        # Release after short delay from background task
        async def _release_soon():
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
            async def close(self):
                closed.append(True)

        async def create_conn():
            return AsyncCloseConn()

        pool = ConnectionPool(create_connection=create_conn, max_size=1, timeout=1.0)
        conn = await pool.acquire()
        await pool.release(conn)
        await pool.cleanup()
        assert closed == [True]
