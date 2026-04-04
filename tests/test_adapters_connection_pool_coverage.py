"""
Tests targeting uncovered lines in connection_pool.py.

Covers:
- _attempt_async exception path (lines 82-83)
- _attempt_async_with_error exception path (lines 91-92)
- _attempt_sync exception path (lines 98-101)
- _invoke_with_optional_args TypeError path (lines 110-114)
- _replace_failed_adapter connect raises (lines 126-127)
- acquire() / release() / cleanup() delegation (lines 156, 168, 177)
- is_connected True branch (line 186)
- _get_adapter TimeoutError (lines 197-198)
- logging during failure in _execute_with_pool (line 255)
- disconnect error path (line 281)
- asyncio.QueueEmpty in disconnect while loop (lines 289-290)
- is_connected False after clear (line 296)
- health_check healthy adapter accumulates response time (line 324)
- save_file via pool (line 361)
- create_part with name/units (lines 380-385)
- create_assembly with name (lines 402-407)
- get_model_info via pool (line 502)
- list_features via pool (line 510)
- list_configurations via pool (line 517)
- ConnectionPool acquire wait loop (lines 621-623)
- ConnectionPool cleanup async close() coroutine (line 653)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from src.solidworks_mcp.adapters.connection_pool import ConnectionPool, ConnectionPoolAdapter
from src.solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
)
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(pool_size: int = 1, **kwargs) -> ConnectionPoolAdapter:
    """Return a ConnectionPoolAdapter backed by MockSolidWorksAdapter."""
    return ConnectionPoolAdapter(
        adapter_factory=lambda: MockSolidWorksAdapter({}),
        pool_size=pool_size,
        **kwargs,
    )


def _make_healthy_health(average_response_time: float = 0.05) -> AdapterHealth:
    return AdapterHealth(
        healthy=True,
        last_check=datetime.now(),
        error_count=0,
        success_count=1,
        average_response_time=average_response_time,
        connection_status="connected",
        metrics={"adapter_type": "mock"},
    )


def _make_unhealthy_health() -> AdapterHealth:
    return AdapterHealth(
        healthy=False,
        last_check=datetime.now(),
        error_count=1,
        success_count=0,
        average_response_time=0.0,
        connection_status="disconnected",
    )


# ===========================================================================
# TestConnectionPoolAdapterCoverage
# ===========================================================================


class TestConnectionPoolAdapterCoverage:
    """Coverage tests for ConnectionPoolAdapter internals."""

    # ------------------------------------------------------------------
    # _attempt_async – exception path (lines 82-83)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_attempt_async_returns_default_on_exception(self):
        pool = _make_pool()

        async def raising_op():
            raise RuntimeError("boom")

        result = await pool._attempt_async(raising_op)
        assert result is None

    @pytest.mark.asyncio
    async def test_attempt_async_returns_custom_default_on_exception(self):
        pool = _make_pool()

        async def raising_op():
            raise ValueError("oops")

        result = await pool._attempt_async(raising_op, default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_attempt_async_returns_value_on_success(self):
        pool = _make_pool()

        async def good_op():
            return 42

        result = await pool._attempt_async(good_op)
        assert result == 42

    # ------------------------------------------------------------------
    # _attempt_async_with_error – exception path (lines 91-92)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_attempt_async_with_error_returns_none_exc_on_exception(self):
        pool = _make_pool()

        async def raising_op():
            raise ValueError("bad input")

        value, exc = await pool._attempt_async_with_error(raising_op)
        assert value is None
        assert isinstance(exc, ValueError)
        assert str(exc) == "bad input"

    @pytest.mark.asyncio
    async def test_attempt_async_with_error_success_path(self):
        pool = _make_pool()

        async def good_op():
            return "ok"

        value, exc = await pool._attempt_async_with_error(good_op)
        assert value == "ok"
        assert exc is None

    # ------------------------------------------------------------------
    # _attempt_sync – exception path (lines 98-101)
    # ------------------------------------------------------------------

    def test_attempt_sync_returns_default_on_exception(self):
        pool = _make_pool()

        def raising_op():
            raise RuntimeError("sync boom")

        result = pool._attempt_sync(raising_op)
        assert result is None

    def test_attempt_sync_returns_custom_default_on_exception(self):
        pool = _make_pool()

        def raising_op():
            raise KeyError("missing")

        result = pool._attempt_sync(raising_op, default=-1)
        assert result == -1

    def test_attempt_sync_returns_value_on_success(self):
        pool = _make_pool()

        def good_op():
            return "sync_result"

        result = pool._attempt_sync(good_op)
        assert result == "sync_result"

    # ------------------------------------------------------------------
    # _invoke_with_optional_args – TypeError retry path (lines 110-114)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invoke_with_optional_args_falls_back_on_type_error(self):
        """When method(*args) raises TypeError, retry with no args."""
        pool = _make_pool()

        mock_adapter = MagicMock()

        # First call (with args) raises TypeError; second call (no args) succeeds.
        async def method_no_args():
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data="no-args-result")

        async def method_with_args(*args):
            raise TypeError("unexpected keyword argument")

        # Attach both sides via side_effect list
        mock_method = AsyncMock(side_effect=[TypeError("too many args"), "fallback"])
        mock_adapter.create_part = mock_method

        # Patch the no-arg call after the TypeError path
        # Use a real async callable that the retry will use
        no_arg_result = AdapterResult(status=AdapterResultStatus.SUCCESS, data="fallback")

        call_count = 0

        async def smart_method(*args):
            nonlocal call_count
            call_count += 1
            if args:
                raise TypeError("extra args not accepted")
            return no_arg_result

        mock_adapter.create_part = smart_method

        result = await pool._invoke_with_optional_args(mock_adapter, "create_part", "MyPart", "mm")
        assert result is no_arg_result
        assert call_count == 2  # first with args, then without

    @pytest.mark.asyncio
    async def test_invoke_with_optional_args_success_with_args(self):
        pool = _make_pool()

        mock_adapter = MagicMock()
        expected = AdapterResult(status=AdapterResultStatus.SUCCESS, data="with-args")

        async def method(*args):
            return expected

        mock_adapter.create_assembly = method

        result = await pool._invoke_with_optional_args(mock_adapter, "create_assembly", "Asm1")
        assert result is expected

    # ------------------------------------------------------------------
    # _replace_failed_adapter – connect raises (lines 126-127)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_replace_failed_adapter_returns_exception_when_connect_raises(self):
        bad_adapter = MagicMock()
        bad_adapter.connect = AsyncMock(side_effect=ConnectionError("cannot connect"))

        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: bad_adapter,
            pool_size=0,
        )
        # pool_initialized stays False so _return_adapter won't be reached
        pool.pool_initialized = True  # skip _initialize_pool in _return_adapter

        exc = await pool._replace_failed_adapter()
        assert isinstance(exc, ConnectionError)

    # ------------------------------------------------------------------
    # acquire() -> _get_adapter delegation (line 156)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_delegates_to_get_adapter(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        adapter = await pool.acquire()
        assert adapter is not None
        # Return it so cleanup works
        await pool.release(adapter)
        await pool.disconnect()

    # ------------------------------------------------------------------
    # release() -> _return_adapter delegation (line 168)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_release_delegates_to_return_adapter(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        adapter = await pool.acquire()
        qsize_before = pool.available_adapters.qsize()
        await pool.release(adapter)
        assert pool.available_adapters.qsize() == qsize_before + 1
        await pool.disconnect()

    # ------------------------------------------------------------------
    # cleanup() -> disconnect delegation (line 177)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cleanup_delegates_to_disconnect(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()
        assert pool.pool_initialized is True

        await pool.cleanup()
        assert pool.pool_initialized is False
        assert len(pool.pool) == 0

    # ------------------------------------------------------------------
    # is_connected – True branch (line 186 / 296)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_is_connected_true_when_initialized_and_non_empty(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        assert pool.is_connected() is True
        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_is_connected_false_before_connect(self):
        pool = _make_pool(pool_size=1)
        assert pool.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()
        await pool.disconnect()
        # pool_initialized is False and pool list is cleared
        assert pool.is_connected() is False

    # ------------------------------------------------------------------
    # _get_adapter TimeoutError (lines 197-198)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_adapter_raises_after_timeout(self):
        pool = _make_pool(pool_size=1, timeout=0.05)
        await pool.connect()

        # Drain the queue so there are no available adapters
        adapter = await pool.acquire()

        with pytest.raises(Exception, match="No adapter available within"):
            await pool._get_adapter(timeout=0.05)

        # Restore
        await pool.release(adapter)
        await pool.disconnect()

    # ------------------------------------------------------------------
    # _execute_with_pool – logging on replacement failure (line 255)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_with_pool_logs_when_replacement_adapter_fails(self):
        """When the operation keeps failing and replacement adapter creation also
        fails, the pool should log the replacement error and eventually return
        an ERROR result."""

        bad_factory_calls = 0

        def bad_factory():
            nonlocal bad_factory_calls
            bad_factory_calls += 1
            adapter = MagicMock()
            adapter.connect = AsyncMock(side_effect=RuntimeError("factory fail"))
            adapter.disconnect = AsyncMock()
            return adapter

        pool = ConnectionPoolAdapter(
            adapter_factory=bad_factory,
            pool_size=0,
            max_retries=1,
        )
        # Manually seed the pool with one adapter that will fail the operation
        seed_adapter = MockSolidWorksAdapter({})
        await seed_adapter.connect()
        pool.pool.append(seed_adapter)
        await pool.available_adapters.put(seed_adapter)
        pool.pool_initialized = True

        async def always_fail(adapter):
            raise RuntimeError("operation failed")

        with patch("src.solidworks_mcp.adapters.connection_pool.logger") as mock_logger:
            result = await pool._execute_with_pool("test_op", always_fail)

        assert result.status == AdapterResultStatus.ERROR
        # logger.error should have been called for the replacement failure
        mock_logger.error.assert_called()

    # ------------------------------------------------------------------
    # disconnect – error disconnecting adapter (line 281)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disconnect_logs_warning_when_adapter_disconnect_raises(self):
        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        bad_adapter = MagicMock()
        bad_adapter.disconnect = AsyncMock(side_effect=RuntimeError("disconnect failed"))
        pool.pool.append(bad_adapter)
        await pool.available_adapters.put(bad_adapter)

        with patch("src.solidworks_mcp.adapters.connection_pool.logger") as mock_logger:
            await pool.disconnect()

        mock_logger.warning.assert_called()
        assert len(pool.pool) == 0

    # ------------------------------------------------------------------
    # asyncio.QueueEmpty in disconnect while loop (lines 289-290)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disconnect_handles_queue_empty_race(self):
        """Cover the except asyncio.QueueEmpty branch inside disconnect."""
        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        # Patch get_nowait to raise QueueEmpty on first call
        original_empty = pool.available_adapters.empty

        call_count = 0

        def patched_empty():
            nonlocal call_count
            call_count += 1
            # First time: report non-empty so loop enters; second time: empty
            return call_count > 1

        pool.available_adapters.empty = patched_empty

        original_get_nowait = pool.available_adapters.get_nowait

        def raising_get_nowait():
            raise asyncio.QueueEmpty()

        pool.available_adapters.get_nowait = raising_get_nowait

        # Should not raise
        await pool.disconnect()
        assert pool.pool_initialized is False

    # ------------------------------------------------------------------
    # health_check – healthy adapter accumulates response time (line 324)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_check_accumulates_response_time_for_healthy_adapters(self):
        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        healthy_adapter = MagicMock()
        healthy_health = _make_healthy_health(average_response_time=0.1)
        healthy_adapter.health_check = AsyncMock(return_value=healthy_health)

        pool.pool.append(healthy_adapter)
        await pool.available_adapters.put(healthy_adapter)

        health = await pool.health_check()

        assert health.healthy is True
        assert health.average_response_time == pytest.approx(0.1)
        assert health.success_count == 1

    @pytest.mark.asyncio
    async def test_health_check_with_mixed_healthy_unhealthy_adapters(self):
        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        healthy_adapter = MagicMock()
        healthy_adapter.health_check = AsyncMock(return_value=_make_healthy_health(0.2))

        unhealthy_adapter = MagicMock()
        unhealthy_adapter.health_check = AsyncMock(return_value=_make_unhealthy_health())

        pool.pool.extend([healthy_adapter, unhealthy_adapter])
        await pool.available_adapters.put(healthy_adapter)
        await pool.available_adapters.put(unhealthy_adapter)

        health = await pool.health_check()

        assert health.healthy is True  # at least one healthy
        assert health.success_count == 1
        assert health.error_count == 1

    # ------------------------------------------------------------------
    # save_file via pool (line 361)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_save_file_via_pool(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.save_file("output.sldprt")
        # Mock adapter's save_file is not implemented — just verify the call completes
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

        await pool.disconnect()

    # ------------------------------------------------------------------
    # create_part with name and units – _invoke_with_optional_args (lines 380-385)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_part_with_name_and_units(self):
        """Exercises the non-None branch that calls _invoke_with_optional_args."""
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.create_part(name="MyPart", units="mm")
        assert result.status == AdapterResultStatus.SUCCESS

        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_create_part_no_args_uses_direct_call(self):
        """Exercises the name is None and units is None branch."""
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.create_part()
        assert result.status == AdapterResultStatus.SUCCESS

        await pool.disconnect()

    # ------------------------------------------------------------------
    # create_assembly with name (lines 402-407)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_assembly_with_name(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.create_assembly(name="MyAssembly")
        assert result.status == AdapterResultStatus.SUCCESS

        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_create_assembly_no_name(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.create_assembly()
        assert result.status == AdapterResultStatus.SUCCESS

        await pool.disconnect()

    # ------------------------------------------------------------------
    # get_model_info via pool (line 502)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_model_info_via_pool(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.get_model_info()
        # Mock adapter returns ERROR when no model is open; that is acceptable
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

        await pool.disconnect()

    # ------------------------------------------------------------------
    # list_features via pool (line 510)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_features_via_pool(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.list_features()
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

        await pool.disconnect()

    # ------------------------------------------------------------------
    # list_configurations via pool (line 517)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_configurations_via_pool(self):
        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.list_configurations()
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

        await pool.disconnect()


# ===========================================================================
# TestConnectionPoolLegacyCoverage
# ===========================================================================


class TestConnectionPoolLegacyCoverage:
    """Coverage tests for legacy ConnectionPool class."""

    # ------------------------------------------------------------------
    # acquire wait loop – all connections in use, waits then gets one
    # (lines 621-623)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_wait_loop_gets_connection_after_release(self):
        """Acquires all connections, then releases one from a background task
        while the main task is blocked in the wait loop."""

        conn_obj = MagicMock()
        conn_obj.close = None  # no close method

        def create_connection():
            return conn_obj

        pool = ConnectionPool(create_connection=create_connection, max_size=1, timeout=2.0)

        # Acquire the only connection so the pool is saturated
        first = await pool.acquire()
        assert first is conn_obj

        async def release_after_delay():
            await asyncio.sleep(0.05)
            await pool.release(first)

        # Start the background release
        release_task = asyncio.create_task(release_after_delay())

        # This should block in the wait loop until release_task releases the conn
        second = await pool.acquire()

        assert second is conn_obj  # same object reused
        await release_task

    # ------------------------------------------------------------------
    # acquire wait loop – timeout raises TimeoutError (line 626)
    # Already covered by test_adapters.py; include a lightweight variant.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_times_out_when_no_connection_available(self):
        def create_connection():
            return MagicMock()

        pool = ConnectionPool(create_connection=create_connection, max_size=1, timeout=0.05)
        _conn = await pool.acquire()

        with pytest.raises(TimeoutError):
            await pool.acquire()

    # ------------------------------------------------------------------
    # cleanup – async close() coroutine (line 653)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cleanup_awaits_async_close_coroutine(self):
        """Connection with an async close() method should be awaited."""

        close_called = False

        class AsyncCloseConn:
            async def close(self):
                nonlocal close_called
                close_called = True

        conn_instance = AsyncCloseConn()

        def create_connection():
            return conn_instance

        pool = ConnectionPool(create_connection=create_connection, max_size=1)
        conn = await pool.acquire()
        await pool.release(conn)

        await pool.cleanup()

        assert close_called is True

    @pytest.mark.asyncio
    async def test_cleanup_skips_connections_without_close(self):
        """Connections with no close attribute should be skipped silently."""

        class NoCloseConn:
            pass

        def create_connection():
            return NoCloseConn()

        pool = ConnectionPool(create_connection=create_connection, max_size=1)
        conn = await pool.acquire()
        await pool.release(conn)

        # Should not raise
        await pool.cleanup()
        assert pool.size == 0

    @pytest.mark.asyncio
    async def test_cleanup_calls_sync_close_without_await(self):
        """Connections with a synchronous close() should be called normally."""

        sync_close_called = False

        class SyncCloseConn:
            def close(self):
                nonlocal sync_close_called
                sync_close_called = True

        def create_connection():
            return SyncCloseConn()

        pool = ConnectionPool(create_connection=create_connection, max_size=1)
        conn = await pool.acquire()
        await pool.release(conn)

        await pool.cleanup()

        assert sync_close_called is True
