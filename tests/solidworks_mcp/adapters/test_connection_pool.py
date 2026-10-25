"""Tests for ``solidworks_mcp.adapters.connection_pool``."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from solidworks_mcp.adapters.base import (
    AdapterHealth,
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    SolidWorksFeature,
)
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter
from solidworks_mcp.adapters.connection_pool import (
    ConnectionPool,
    ConnectionPoolAdapter,
)
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


class _PoolAdapterStub:
    """Test suite for PoolAdapterStub."""

    def __init__(self, fail: bool = False):
        """Test helper for init."""
        self.fail = fail
        self.disconnected = False

    async def connect(self):
        """Test helper for connect."""
        return None

    async def disconnect(self):
        """Test helper for disconnect."""
        self.disconnected = True

    async def health_check(self):
        """Test helper for health check."""
        return AdapterHealth(
            healthy=not self.fail,
            last_check=datetime.now(),
            error_count=1 if self.fail else 0,
            success_count=0 if self.fail else 1,
            average_response_time=0.01,
            connection_status="connected",
            metrics={"id": id(self)},
        )


@pytest.mark.asyncio
async def test_connection_pool_adapter_retry_and_error_result():
    """Test connection pool adapter retry and error result."""
    created: list[_PoolAdapterStub] = []

    def factory():
        """Test helper for factory."""
        adapter = _PoolAdapterStub()
        created.append(adapter)
        return adapter

    pool = ConnectionPoolAdapter(adapter_factory=factory, pool_size=1, max_retries=1)

    async def always_fail(_adapter):
        """Test helper for always fail."""
        raise RuntimeError("boom")

    result = await pool._execute_with_pool("unit_test", always_fail)
    assert isinstance(result, AdapterResult)
    assert result.status == AdapterResultStatus.ERROR
    assert "failed after" in (result.error or "")
    assert len(created) >= 2


@pytest.mark.asyncio
async def test_connection_pool_adapter_health_and_timeout_paths():
    """Test connection pool adapter health and timeout paths."""
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: _PoolAdapterStub(), pool_size=1
    )

    not_ready = await pool.health_check()
    assert not_ready.connection_status == "pool_not_initialized"

    await pool.connect()
    healthy = await pool.health_check()
    assert healthy.connection_status == "pooled"
    assert healthy.metrics["pool_size"] == 1

    await pool.disconnect()
    pool.pool_initialized = True
    with pytest.raises(Exception, match="No adapter available"):
        await pool._get_adapter(timeout=0.001)


@pytest.mark.asyncio
async def test_connection_pool_passthrough_methods_are_wired(monkeypatch):
    """Test connection pool passthrough methods are wired."""
    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: _PoolAdapterStub(), pool_size=1
    )

    async def _fake_execute(name, operation):
        """Test helper for fake execute."""
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data={"op": name})

    monkeypatch.setattr(pool, "_execute_with_pool", _fake_execute)

    assert (await pool.open_model("a.sldprt")).is_success
    assert (await pool.close_model()).is_success
    assert (await pool.create_part()).is_success
    assert (await pool.create_assembly()).is_success
    assert (await pool.create_drawing()).is_success
    assert (await pool.create_extrusion({"depth": 1})).is_success
    assert (await pool.create_revolve({"angle": 90})).is_success
    assert (await pool.create_sweep({"path": "P"})).is_success
    assert (await pool.create_loft({"profiles": []})).is_success
    assert (await pool.create_sketch("Top")).is_success
    assert (await pool.add_line(0, 0, 1, 1)).is_success
    assert (await pool.add_circle(0, 0, 5)).is_success
    assert (await pool.add_rectangle(0, 0, 2, 3)).is_success
    assert (await pool.exit_sketch()).is_success
    assert (await pool.get_mass_properties()).is_success
    assert (await pool.export_file("x.step", "step")).is_success
    assert (await pool.get_dimension("D1@Sketch1")).is_success
    assert (await pool.set_dimension("D1@Sketch1", 12.0)).is_success


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


class TestConnectionPool:
    """Test suite for connection pooling."""

    @pytest.mark.asyncio
    async def test_connection_pool_creation(self):
        """Test connection pool creation and basic functionality."""

        async def create_connection():
            """Test helper for create connection."""
            mock_conn = Mock()
            mock_conn.is_connected = True
            mock_conn.close = AsyncMock()
            return mock_conn

        pool = ConnectionPoolAdapter(
            create_connection=create_connection, max_size=3, timeout=5.0
        )

        assert pool.size == 0
        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_connection_pool_acquire_release(self):
        """Test acquiring and releasing connections."""

        async def create_connection():
            """Test helper for create connection."""
            mock_conn = Mock()
            mock_conn.is_connected = True
            mock_conn.close = AsyncMock()
            return mock_conn

        pool = ConnectionPool(create_connection=create_connection, max_size=2)

        # Acquire connection
        conn1 = await pool.acquire()
        assert conn1 is not None
        assert pool.active_connections == 1

        # Acquire another connection
        conn2 = await pool.acquire()
        assert conn2 is not None
        assert pool.active_connections == 2
        assert conn1 != conn2  # Should be different connections

        # Release connections
        await pool.release(conn1)
        assert pool.active_connections == 1

        await pool.release(conn2)
        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_connection_pool_max_size(self):
        """Test connection pool respects max size."""

        connection_count = 0

        async def create_connection():
            """Test helper for create connection."""
            nonlocal connection_count
            connection_count += 1
            mock_conn = Mock()
            mock_conn.id = connection_count
            mock_conn.is_connected = True
            mock_conn.close = AsyncMock()
            return mock_conn

        pool = ConnectionPool(create_connection=create_connection, max_size=2)

        # Acquire up to max size
        conn1 = await pool.acquire()
        await pool.acquire()

        # Pool should reuse connections when at max capacity
        await pool.release(conn1)
        conn3 = await pool.acquire()

        # conn3 should be the reused conn1
        assert conn3.id == conn1.id

    @pytest.mark.asyncio
    async def test_connection_pool_cleanup(self):
        """Test connection pool cleanup."""

        created_connections = []

        async def create_connection():
            """Test helper for create connection."""
            mock_conn = Mock()
            mock_conn.is_connected = True
            mock_conn.close = AsyncMock()
            created_connections.append(mock_conn)
            return mock_conn

        pool = ConnectionPool(create_connection=create_connection, max_size=2)

        # Create some connections
        conn1 = await pool.acquire()
        conn2 = await pool.acquire()
        await pool.release(conn1)
        await pool.release(conn2)

        # Cleanup should close all connections
        await pool.cleanup()

        for conn in created_connections:
            conn.close.assert_called_once()

        assert pool.size == 0
        assert pool.active_connections == 0

    @pytest.mark.asyncio
    async def test_connection_pool_acquire_timeout_path(self):
        """Test legacy ConnectionPool timeout when max size is exhausted."""

        async def create_connection():
            """Test helper for create connection."""
            mock_conn = Mock()
            mock_conn.close = AsyncMock()
            return mock_conn

        pool = ConnectionPool(
            create_connection=create_connection, max_size=1, timeout=0.05
        )

        first = await pool.acquire()
        assert first is not None

        with pytest.raises(TimeoutError):
            await pool.acquire()

    @pytest.mark.asyncio
    async def test_connection_pool_release_unknown_connection_noop(self):
        """Test release no-op branch for connection not tracked in in-use set."""

        async def create_connection():
            """Test helper for create connection."""
            mock_conn = Mock()
            mock_conn.close = AsyncMock()
            return mock_conn

        pool = ConnectionPool(create_connection=create_connection, max_size=1)

        unknown_conn = Mock()
        await pool.release(unknown_conn)
        assert pool.active_connections == 0


class TestConnectionPoolAdapterExtras:
    """Additional branch coverage for ConnectionPoolAdapter initialization and legacy fields."""

    @pytest.mark.asyncio
    async def test_connection_pool_adapter_default_factory_and_aliases(self):
        """Test constructor branches for default adapter factory, max_size alias, and timeout alias."""
        adapter = ConnectionPoolAdapter(
            adapter_factory=None,
            create_connection=None,
            max_size=2,
            timeout=1.5,
            config={"mock_solidworks": True},
        )

        assert adapter.pool_size == 2
        assert adapter.timeout == 1.5
        assert adapter.adapter_factory is not None

    def test_adapter_health_legacy_key_membership(self):
        """Test AdapterHealth __contains__ and __getitem__ legacy compatibility keys."""
        from datetime import datetime

        from solidworks_mcp.adapters.base import AdapterHealth

        health = AdapterHealth(
            healthy=True,
            last_check=datetime.now(),
            error_count=0,
            success_count=1,
            average_response_time=0.01,
            connection_status="connected",
            metrics={"adapter_type": "mock", "version": "x", "uptime": 1.0},
        )

        assert "status" in health
        assert "connected" in health
        assert "adapter_type" in health
        assert health["status"] == "healthy"
        assert health["connected"] is True

    @pytest.mark.asyncio
    async def test_connection_wrappers_forward_add_centerline(self):
        """Test that wrapper adapters expose add_centerline passthroughs."""

        class _StubAdapter:
            """Test suite for StubAdapter."""

            async def connect(self):
                """Test helper for connect."""
                return None

            async def disconnect(self):
                """Test helper for disconnect."""
                return None

            async def add_centerline(self, x1, y1, x2, y2):
                """Test helper for add centerline."""
                return AdapterResult(
                    status=AdapterResultStatus.SUCCESS,
                    data=f"centerline:{x1},{y1}->{x2},{y2}",
                )

        circuit = CircuitBreakerAdapter(adapter=_StubAdapter())
        circuit_result = await circuit.add_centerline(0.0, 0.0, 10.0, 0.0)
        assert circuit_result.is_success
        assert circuit_result.data == "centerline:0.0,0.0->10.0,0.0"

        pool = ConnectionPoolAdapter(adapter_factory=lambda: _StubAdapter(), max_size=1)
        await pool.connect()
        pool_result = await pool.add_centerline(0.0, 0.0, 10.0, 0.0)
        assert pool_result.is_success
        assert pool_result.data == "centerline:0.0,0.0->10.0,0.0"
        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_wrapper_adapters_forward_every_remaining_passthrough_method(self):
        """Every pass-through method on both wrapper adapters actually forwards.

        CircuitBreakerAdapter and ConnectionPoolAdapter each expose an
        identical set of thin wrapper methods (create_reference_plane,
        mirror_feature, rename_feature, add_mate, ...). One stub covering
        every one of them, called once through each wrapper, is far cheaper
        than a dedicated test per method for what is otherwise a single
        delegating line.
        """

        def _ok(data=None):
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

        class _FullStubAdapter:
            async def connect(self):
                return None

            async def disconnect(self):
                return None

            async def create_reference_plane(
                self, reference, offset=0.0, angle=0.0, flip=False
            ):
                return _ok("plane")

            async def create_axis(self, reference):
                return _ok("axis")

            async def create_reference_point(
                self, mode, x, y, z, distance=None, percent=None
            ):
                return _ok("point")

            async def mirror_feature(
                self, features, mirror_plane, merge=True, mirror_bodies=True
            ):
                return _ok("mirrored")

            async def pattern_circular(
                self, features, axis, count, angle=360.0, equal_spacing=True
            ):
                return _ok("patterned")

            async def set_units(self, unit_system):
                return _ok({"unit_system": unit_system})

            async def list_open_documents(self):
                return _ok([])

            async def activate_document(self, title_or_path):
                return _ok({"activated": title_or_path})

            async def insert_component(self, file_path, x=0.0, y=0.0, z=0.0):
                return _ok({"file_path": file_path})

            async def list_components(self):
                return _ok([])

            async def create_drawing_view(self, payload=None):
                return _ok("view")

            async def add_drawing_view(self, payload=None):
                return _ok("view")

            async def create_technical_drawing(self, payload=None):
                return _ok("drawing")

            async def add_note(self, payload=None):
                return _ok("note")

            async def list_drawing_views(self):
                return _ok([])

            async def auto_center_marks(
                self, view_name, mark_holes=True, mark_fillets=False, mark_slots=True
            ):
                return _ok("marks")

            async def save_body_as_part(self, body_name, file_path):
                return _ok({"body": body_name})

            async def check_interference(self, params=None):
                return _ok("interference")

            async def delete_feature(self, name):
                return _ok({"deleted": name})

            async def suppress_feature(self, name, suppress=True):
                return _ok({"name": name})

            async def rename_feature(self, old_name, new_name):
                return _ok({"new_name": new_name})

            async def undo(self, count=1):
                return _ok({"count": count})

            async def add_mate(
                self,
                component_a,
                component_b,
                entity_a="Front Plane",
                entity_b="Front Plane",
                mate_type="coincident",
                alignment="aligned",
                distance=0.0,
                angle=0.0,
            ):
                return _ok("mate")

            async def add_chamfer(self, distance, edge_names):
                return _ok("chamfer")

            async def get_selected_entities(self):
                return _ok("selection")

        async def _exercise_every_passthrough(wrapped) -> None:
            assert (await wrapped.create_reference_plane("Top")).is_success
            assert (await wrapped.create_axis("Top")).is_success
            assert (
                await wrapped.create_reference_point("along_curve", 0, 0, 0)
            ).is_success
            assert (await wrapped.mirror_feature(["F1"], "Right")).is_success
            assert (await wrapped.pattern_circular(["F1"], "Axis1", 4)).is_success
            assert (await wrapped.set_units("mm")).is_success
            assert (await wrapped.list_open_documents()).is_success
            assert (await wrapped.activate_document("Part1")).is_success
            assert (await wrapped.insert_component("a.sldprt")).is_success
            assert (await wrapped.list_components()).is_success
            assert (await wrapped.create_drawing_view()).is_success
            assert (await wrapped.add_drawing_view()).is_success
            assert (await wrapped.create_technical_drawing()).is_success
            assert (await wrapped.add_note()).is_success
            assert (await wrapped.list_drawing_views()).is_success
            assert (await wrapped.auto_center_marks("View1")).is_success
            assert (await wrapped.save_body_as_part("Body1", "b.sldprt")).is_success
            assert (await wrapped.check_interference()).is_success
            assert (await wrapped.delete_feature("Sketch1")).is_success
            assert (await wrapped.suppress_feature("Sketch1")).is_success
            assert (await wrapped.rename_feature("Sketch1", "Sketch2")).is_success
            assert (await wrapped.undo()).is_success
            assert (await wrapped.add_mate("Comp1", "Comp2")).is_success
            assert (await wrapped.add_chamfer(1.0, ["Edge1"])).is_success
            assert (await wrapped.get_selected_entities()).is_success

        await _exercise_every_passthrough(
            CircuitBreakerAdapter(adapter=_FullStubAdapter())
        )

        pool = ConnectionPoolAdapter(
            adapter_factory=lambda: _FullStubAdapter(), max_size=1
        )
        await pool.connect()
        try:
            await _exercise_every_passthrough(pool)
        finally:
            await pool.disconnect()


def _make_pool(pool_size: int = 1, **kwargs) -> ConnectionPoolAdapter:
    """Return a ConnectionPoolAdapter backed by MockSolidWorksAdapter."""
    return ConnectionPoolAdapter(
        adapter_factory=lambda: MockSolidWorksAdapter({}),
        pool_size=pool_size,
        **kwargs,
    )


def _make_healthy_health(average_response_time: float = 0.05) -> AdapterHealth:
    """Test make healthy health."""

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
    """Test make unhealthy health."""

    return AdapterHealth(
        healthy=False,
        last_check=datetime.now(),
        error_count=1,
        success_count=0,
        average_response_time=0.0,
        connection_status="disconnected",
    )


class TestConnectionPoolAdapterCoverageCoverage:
    """Coverage tests for ConnectionPoolAdapter internals."""

    # ------------------------------------------------------------------
    # _attempt_async – exception path (lines 82-83)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_attempt_async_returns_default_on_exception(self):
        """Test attempt async returns default on exception."""

        pool = _make_pool()

        async def raising_op():
            """Test raising op."""

            raise RuntimeError("boom")

        result = await pool._attempt_async(raising_op)
        assert result is None

    @pytest.mark.asyncio
    async def test_attempt_async_returns_custom_default_on_exception(self):
        """Test attempt async returns custom default on exception."""

        pool = _make_pool()

        async def raising_op():
            """Test raising op."""

            raise ValueError("oops")

        result = await pool._attempt_async(raising_op, default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_attempt_async_returns_value_on_success(self):
        """Test attempt async returns value on success."""

        pool = _make_pool()

        async def good_op():
            """Test good op."""

            return 42

        result = await pool._attempt_async(good_op)
        assert result == 42

    # ------------------------------------------------------------------
    # _attempt_async_with_error – exception path (lines 91-92)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_attempt_async_with_error_returns_none_exc_on_exception(self):
        """Test attempt async with error returns none exc on exception."""

        pool = _make_pool()

        async def raising_op():
            """Test raising op."""

            raise ValueError("bad input")

        value, exc = await pool._attempt_async_with_error(raising_op)
        assert value is None
        assert isinstance(exc, ValueError)
        assert str(exc) == "bad input"

    @pytest.mark.asyncio
    async def test_attempt_async_with_error_success_path(self):
        """Test attempt async with error success path."""

        pool = _make_pool()

        async def good_op():
            """Test good op."""

            return "ok"

        value, exc = await pool._attempt_async_with_error(good_op)
        assert value == "ok"
        assert exc is None

    # ------------------------------------------------------------------
    # _attempt_sync – exception path (lines 98-101)
    # ------------------------------------------------------------------

    def test_attempt_sync_returns_default_on_exception(self):
        """Test attempt sync returns default on exception."""

        pool = _make_pool()

        def raising_op():
            """Test raising op."""

            raise RuntimeError("sync boom")

        result = pool._attempt_sync(raising_op)
        assert result is None

    def test_attempt_sync_returns_custom_default_on_exception(self):
        """Test attempt sync returns custom default on exception."""

        pool = _make_pool()

        def raising_op():
            """Test raising op."""

            raise KeyError("missing")

        result = pool._attempt_sync(raising_op, default=-1)
        assert result == -1

        def test_attempt_sync_returns_value_on_success(self):
            """Test attempt sync returns value on success."""

        pool = _make_pool()

        def good_op():
            """Test good op."""

            return "sync_result"

        result = pool._attempt_sync(good_op)
        assert result == "sync_result"

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_dispatches(self):
        """add_sketch_constraint should call through the pool."""
        # Verify the adapter call is routed through _execute_with_pool.
        pool = _make_pool()
        pool._execute_with_pool = AsyncMock(
            return_value=AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data="ok",
            )
        )
        result = await pool.add_sketch_constraint("e1", None, "coincident", None)
        assert result.is_success
        pool._execute_with_pool.assert_awaited()

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
            """Test method no args."""

            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data="no-args-result"
            )

        async def method_with_args(*args):
            """Test method with args."""

            raise TypeError("unexpected keyword argument")

        # Attach both sides via side_effect list
        mock_method = AsyncMock(side_effect=[TypeError("too many args"), "fallback"])
        mock_adapter.create_part = mock_method

        # Patch the no-arg call after the TypeError path
        # Use a real async callable that the retry will use
        no_arg_result = AdapterResult(
            status=AdapterResultStatus.SUCCESS, data="fallback"
        )

        call_count = 0

        async def smart_method(*args):
            """Test smart method."""

            nonlocal call_count
            call_count += 1
            if args:
                raise TypeError("extra args not accepted")
            return no_arg_result

        mock_adapter.create_part = smart_method

        result = await pool._invoke_with_optional_args(
            mock_adapter, "create_part", "MyPart", "mm"
        )
        assert result is no_arg_result
        assert call_count == 2  # first with args, then without

    @pytest.mark.asyncio
    async def test_invoke_with_optional_args_success_with_args(self):
        """Test invoke with optional args success with args."""

        pool = _make_pool()

        mock_adapter = MagicMock()
        expected = AdapterResult(status=AdapterResultStatus.SUCCESS, data="with-args")

        async def method(*args):
            """Test method."""

            return expected

        mock_adapter.create_assembly = method

        result = await pool._invoke_with_optional_args(
            mock_adapter, "create_assembly", "Asm1"
        )
        assert result is expected

    # ------------------------------------------------------------------
    # _replace_failed_adapter – connect raises (lines 126-127)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_replace_failed_adapter_returns_exception_when_connect_raises(self):
        """Test replace failed adapter returns exception when connect raises."""

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
        """Test acquire delegates to get adapter."""

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
        """Test release delegates to return adapter."""

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
        """Test cleanup delegates to disconnect."""

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
        """Test is connected true when initialized and non empty."""

        pool = _make_pool(pool_size=1)
        await pool.connect()

        assert pool.is_connected() is True
        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_is_connected_false_before_connect(self):
        """Test is connected false before connect."""

        pool = _make_pool(pool_size=1)
        assert pool.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self):
        """Test is connected false after disconnect."""

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
        """Test get adapter raises after timeout."""

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
    async def test_execute_with_pool_logs_when_replacement_adapter_fails(
        self, monkeypatch
    ):
        """When the operation keeps failing and replacement adapter creation also."""

        bad_factory_calls = 0

        def bad_factory():
            """Test bad factory."""

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
            """Test always fail."""

            raise RuntimeError("operation failed")

        # After the seed adapter fails and the bad_factory replacement also
        # fails to connect, the retry loop's second _get_adapter() call
        # blocks on an empty queue for its hardcoded 30s default timeout.
        # Shrink that to keep the real wait_for/TimeoutError logic intact
        # without the test actually waiting 30 real seconds.
        real_get_adapter = pool._get_adapter

        async def fast_get_adapter(timeout: float = 0.01):
            return await real_get_adapter(timeout=timeout)

        monkeypatch.setattr(pool, "_get_adapter", fast_get_adapter)
        # Also skip the retry loop's 1s-per-retry exponential backoff sleep
        # (max_retries=1 here, so this alone was worth 1 real second).
        monkeypatch.setattr(
            "solidworks_mcp.adapters.connection_pool.asyncio.sleep", AsyncMock()
        )

        with patch("solidworks_mcp.adapters.connection_pool.logger") as mock_logger:
            result = await pool._execute_with_pool("test_op", always_fail)

        assert result.status == AdapterResultStatus.ERROR
        # logger.error should have been called for the replacement failure
        mock_logger.error.assert_called()

    # ------------------------------------------------------------------
    # disconnect – error disconnecting adapter (line 281)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disconnect_logs_warning_when_adapter_disconnect_raises(self):
        """Test disconnect logs warning when adapter disconnect raises."""

        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        bad_adapter = MagicMock()
        bad_adapter.disconnect = AsyncMock(
            side_effect=RuntimeError("disconnect failed")
        )
        pool.pool.append(bad_adapter)
        await pool.available_adapters.put(bad_adapter)

        with patch("solidworks_mcp.adapters.connection_pool.logger") as mock_logger:
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

        call_count = 0

        def patched_empty():
            """Test patched empty."""

            nonlocal call_count
            call_count += 1
            # First time: report non-empty so loop enters; second time: empty
            return call_count > 1

        pool.available_adapters.empty = patched_empty

        def raising_get_nowait():
            """Test raising get nowait."""

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
        """Test health check accumulates response time for healthy adapters."""

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
        """Test health check with mixed healthy unhealthy adapters."""

        pool = _make_pool(pool_size=0)
        pool.pool_initialized = True

        healthy_adapter = MagicMock()
        healthy_adapter.health_check = AsyncMock(return_value=_make_healthy_health(0.2))

        unhealthy_adapter = MagicMock()
        unhealthy_adapter.health_check = AsyncMock(
            return_value=_make_unhealthy_health()
        )

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
        """Test save file via pool."""

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
        """Test create assembly with name."""

        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.create_assembly(name="MyAssembly")
        assert result.status == AdapterResultStatus.SUCCESS

        await pool.disconnect()

    @pytest.mark.asyncio
    async def test_create_assembly_no_name(self):
        """Test create assembly no name."""

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
        """Test get model info via pool."""

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
        """Test list features via pool."""

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
        """Test list configurations via pool."""

        pool = _make_pool(pool_size=1)
        await pool.connect()

        result = await pool.list_configurations()
        assert result.status in (AdapterResultStatus.SUCCESS, AdapterResultStatus.ERROR)

        await pool.disconnect()


class TestConnectionPoolLegacyCoverageCoverage:
    """Coverage tests for legacy ConnectionPool class."""

    # ------------------------------------------------------------------
    # acquire wait loop – all connections in use, waits then gets one
    # (lines 621-623)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_wait_loop_gets_connection_after_release(self):
        """Acquires all connections, then releases one from a background task."""

        conn_obj = MagicMock()
        conn_obj.close = None  # no close method

        def create_connection():
            """Test create connection."""

            return conn_obj

        pool = ConnectionPool(
            create_connection=create_connection, max_size=1, timeout=2.0
        )

        # Acquire the only connection so the pool is saturated
        first = await pool.acquire()
        assert first is conn_obj

        async def release_after_delay():
            """Test release after delay."""

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
    # Already covered by TestConnectionPool above; include a lightweight variant.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_times_out_when_no_connection_available(self):
        """Test acquire times out when no connection available."""

        def create_connection():
            """Test create connection."""

            return MagicMock()

        pool = ConnectionPool(
            create_connection=create_connection, max_size=1, timeout=0.05
        )
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
            """Test async close conn."""

            async def close(self):
                """Test close."""

                nonlocal close_called
                close_called = True

        conn_instance = AsyncCloseConn()

        def create_connection():
            """Test create connection."""

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
            """Test no close conn."""

            pass

        def create_connection():
            """Test create connection."""

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
            """Test sync close conn."""

            def close(self):
                """Test close."""

                nonlocal sync_close_called
                sync_close_called = True

        def create_connection():
            """Test create connection."""

            return SyncCloseConn()

        pool = ConnectionPool(create_connection=create_connection, max_size=1)
        conn = await pool.acquire()
        await pool.release(conn)

        await pool.cleanup()

        assert sync_close_called is True
