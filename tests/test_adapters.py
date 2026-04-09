"""
Tests for SolidWorks adapter implementations.

Comprehensive test suite covering adapter factory, pywin32 adapter,
mock adapter, circuit breaker, and connection pooling functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from types import SimpleNamespace

from src.solidworks_mcp.adapters import (
    create_adapter,
    AdapterFactory,
    SolidWorksAdapter,
)
from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from src.solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerAdapter,
    CircuitState,
)
from src.solidworks_mcp.adapters.connection_pool import (
    ConnectionPool,
    ConnectionPoolAdapter,
)
from src.solidworks_mcp.config import AdapterType, SolidWorksMCPConfig
from src.solidworks_mcp.exceptions import (
    SolidWorksMCPError,
    SolidWorksConnectionError,
    SolidWorksOperationError,
)
from src.solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus


class TestAdapterFactory:
    """Test suite for adapter factory."""

    @pytest.mark.asyncio
    async def test_create_mock_adapter(self, mock_config):
        """Test creating mock adapter."""
        adapter = await create_adapter(mock_config)
        assert isinstance(adapter, MockSolidWorksAdapter)
        assert adapter.config == mock_config

    @pytest.mark.asyncio
    async def test_create_pywin32_adapter_on_windows(self, mock_config):
        """Test creating pywin32 adapter on Windows."""
        # Override config to use pywin32
        mock_config.adapter_type = AdapterType.PYWIN32
        mock_config.mock_solidworks = False

        with patch("platform.system", return_value="Windows"):
            with patch("src.solidworks_mcp.adapters.pywin32_adapter.PyWin32Adapter"):
                adapter = await create_adapter(mock_config)
                # Would be PyWin32Adapter on actual Windows system

    @pytest.mark.asyncio
    async def test_create_adapter_non_windows_fallback(self, mock_config):
        """Test fallback to mock adapter on non-Windows systems."""
        mock_config.adapter_type = AdapterType.PYWIN32
        mock_config.mock_solidworks = False

        with patch("platform.system", return_value="Linux"):
            adapter = await create_adapter(mock_config)
            assert isinstance(adapter, MockSolidWorksAdapter)

    def test_adapter_factory_registry(self):
        """Test that all adapter types are registered."""
        factory = AdapterFactory()

        # Test that factory has all expected adapter types
        assert AdapterType.MOCK in factory._adapters
        assert AdapterType.PYWIN32 in factory._adapters


class TestMockAdapter:
    """Test suite for mock SolidWorks adapter."""

    @pytest.mark.asyncio
    async def test_mock_adapter_initialization(self, mock_config):
        """Test mock adapter initialization."""
        adapter = MockSolidWorksAdapter(mock_config)
        assert adapter.config == mock_config
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_mock_adapter_connect_disconnect(self, mock_adapter):
        """Test mock adapter connection lifecycle."""
        # Connect
        await mock_adapter.connect()
        assert mock_adapter.is_connected

        # Disconnect
        await mock_adapter.disconnect()
        assert not mock_adapter.is_connected

    @pytest.mark.asyncio
    async def test_mock_adapter_health_check(self, mock_adapter):
        """Test mock adapter health check."""
        await mock_adapter.connect()
        health = await mock_adapter.health_check()

        assert health["status"] == "healthy"
        assert health["adapter_type"] == "mock"
        assert health["connected"] is True
        assert "version" in health
        assert "uptime" in health

    @pytest.mark.asyncio
    async def test_mock_adapter_file_operations(self, mock_adapter):
        """Test mock adapter file operations."""
        await mock_adapter.connect()

        # Test open model
        result = await mock_adapter.open_model("test.sldprt")
        assert result.is_success
        assert "test.sldprt" in result.data["title"]

        # Test save file
        result = await mock_adapter.save_file("test_saved.sldprt")
        assert result.is_success
        assert result.data["file_path"] == "test_saved.sldprt"

    @pytest.mark.asyncio
    async def test_mock_adapter_modeling_operations(self, mock_adapter):
        """Test mock adapter modeling operations."""
        await mock_adapter.connect()

        # Test create part
        result = await mock_adapter.create_part("TestPart", "mm")
        assert result.is_success
        assert result.data["name"] == "TestPart"
        assert result.data["units"] == "mm"

        # Test create extrusion
        result = await mock_adapter.create_extrusion("Sketch1", 10.0, "blind")
        assert result.is_success
        assert result.data["depth"] == 10.0
        assert result.data["direction"] == "blind"

    @pytest.mark.asyncio
    async def test_mock_adapter_sketch_operations(self, mock_adapter):
        """Test mock adapter sketch operations."""
        await mock_adapter.connect()

        # Test create sketch
        result = await mock_adapter.create_sketch("Front Plane")
        assert result.is_success
        assert result.data["plane"] == "Front Plane"

        # Test add sketch line
        result = await mock_adapter.add_sketch_line(0, 0, 10, 10, False)
        assert result.is_success
        assert result.data["start"] == {"x": 0, "y": 0}
        assert result.data["end"] == {"x": 10, "y": 10}

    @pytest.mark.asyncio
    async def test_mock_adapter_error_simulation(self, mock_config):
        """Test mock adapter error simulation."""
        config = mock_config
        config.simulate_errors = True
        adapter = MockSolidWorksAdapter(config)

        await adapter.connect()

        # Some operations should fail when error simulation is enabled
        with pytest.raises(SolidWorksOperationError):
            await adapter.open_model("nonexistent.sldprt")


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
        with pytest.raises(Exception):
            await cb.call(failing_operation)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

        # Second failure - should open circuit
        with pytest.raises(Exception):
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
        with pytest.raises(Exception):
            await cb.call(failing_then_success)
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        import asyncio

        await asyncio.sleep(0.2)

        # Next call should enter half-open state
        result = await cb.call(lambda: "success")
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


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
        conn2 = await pool.acquire()

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
        from src.solidworks_mcp.adapters.base import AdapterHealth

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


class TestPyWin32AdapterBranches:
    """Additional PyWin32Adapter branch coverage with pure mocks."""

    @staticmethod
    def _build_adapter(monkeypatch) -> PyWin32Adapter:
        """Test helper for build adapter."""
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

    @pytest.mark.asyncio
    async def test_health_check_and_model_info_branches(self, monkeypatch):
        """Test healthy/disconnected checks and model-info default branches."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = SimpleNamespace(RevisionNumber=lambda: "33.2")
        healthy = await adapter.health_check()
        assert healthy.healthy is True
        assert healthy.connection_status == "connected"
        assert healthy.metrics["sw_version"] == "33.2"

        adapter.swApp = SimpleNamespace(RevisionNumber=lambda: None)
        unhealthy = await adapter.health_check()
        assert unhealthy.healthy is False
        assert unhealthy.connection_status == "disconnected"

        adapter.currentModel = SimpleNamespace(
            GetTitle=lambda: "Model1",
            GetPathName=lambda: "C:/tmp/model1.sldprt",
            GetType=lambda: 99,
            GetActiveConfiguration=lambda: None,
            GetSaveFlag=lambda: True,
            GetRebuildStatus=lambda: 0,
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda include_hidden: 7),
        )
        info = await adapter.get_model_info()
        assert info.is_success
        assert info.data["type"] == "Unknown"
        assert info.data["configuration"] == "Default"

    @pytest.mark.asyncio
    async def test_save_export_close_and_dimension_error_paths(self, monkeypatch):
        """Test save/export/close operation branches and dimension failure paths."""
        adapter = self._build_adapter(monkeypatch)
        # Avoid real filesystem calls: makedirs is a no-op and existence check
        # always returns True so SaveAs3 returning True is treated as success.
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.makedirs",
            lambda *a, **kw: None,
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: True,
        )

        no_model = await adapter.close_model()
        assert no_model.status.name == "WARNING"

        model = SimpleNamespace(
            Save=Mock(),
            Save3=Mock(return_value=False),
            SaveAs3=Mock(return_value=False),
            Parameter=Mock(return_value=None),
            ForceRebuild3=Mock(return_value=False),
            GetTitle=Mock(return_value="Model1"),
        )
        adapter.currentModel = model
        adapter.swApp = SimpleNamespace(CloseDoc=Mock())

        assert (await adapter.save_file()).is_error
        assert (await adapter.save_file("C:/tmp/new.sldprt")).is_error
        assert (await adapter.export_file("C:/tmp/out.bad", "badfmt")).is_error

        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: False,
        )
        assert (await adapter.export_file("C:/tmp/out.step", "step")).is_error
        assert (await adapter.get_dimension("D1@Sketch1")).is_error
        assert (await adapter.set_dimension("D1@Sketch1", 20.0)).is_error
        assert (await adapter.rebuild_model()).is_error

        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: True,
        )
        model.Save3 = Mock(return_value=True)
        model.SaveAs3 = Mock(return_value=True)
        model.ForceRebuild3 = Mock(return_value=True)
        model.Parameter = Mock(
            return_value=SimpleNamespace(
                GetValue3=Mock(return_value=0.015), SetValue3=Mock(return_value=True)
            )
        )

        assert (await adapter.save_file()).is_success
        assert (await adapter.save_file("C:/tmp/new.sldprt")).is_success
        assert (await adapter.export_file("C:/tmp/out.step", "step")).is_success
        assert (await adapter.get_dimension("D1@Sketch1")).data == pytest.approx(15.0)
        assert (await adapter.set_dimension("D1@Sketch1", 20.0)).is_success
        assert (await adapter.rebuild_model()).is_success

        closed = await adapter.close_model(save=True)
        assert closed.is_success
        assert adapter.currentModel is None
        adapter.swApp.CloseDoc.assert_any_call("Model1")

    @pytest.mark.asyncio
    async def test_sketch_placeholder_and_exit_paths(self, monkeypatch):
        """Test sketch placeholder helpers and exit-sketch branches."""
        adapter = self._build_adapter(monkeypatch)

        no_sketch = await adapter.exit_sketch()
        assert no_sketch.status.name == "WARNING"

        adapter.currentSketchManager = SimpleNamespace(InsertSketch=Mock())

        assert (await adapter.add_sketch_constraint("L1", None, "unknown")).is_success
        assert (
            await adapter.add_sketch_dimension("L1", None, "linear", 10.0)
        ).is_success
        assert (
            await adapter.sketch_linear_pattern(["L1"], 1.0, 0.0, 5.0, 3)
        ).is_success
        assert (
            await adapter.sketch_circular_pattern(["L1"], 0.0, 0.0, 180.0, 4)
        ).is_success
        assert (await adapter.sketch_mirror(["L1"], "CL1")).is_success
        assert (await adapter.sketch_offset(["L1"], 1.0, True)).is_success

        exited = await adapter.exit_sketch()
        assert exited.is_success
        assert adapter.currentSketchManager is None

    @pytest.mark.asyncio
    async def test_list_features_prefers_tree_traversal(self, monkeypatch):
        """List features should traverse FirstFeature/GetNextFeature when available."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, feature_type, suppressed=False):
                """Test helper for init."""
                self.Name = name
                self._feature_type = feature_type
                self._suppressed = suppressed
                self._next = None

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return self._feature_type

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                return self._suppressed

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return self._next

        f1 = _Feature("Front Plane", "RefPlane", False)
        f2 = _Feature("Boss-Extrude1", "Boss", False)
        f3 = _Feature("Cut-Extrude1", "Cut", True)
        f1._next = f2
        f2._next = f3

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: f1,
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        )

        result = await adapter.list_features(include_suppressed=False)

        assert result.is_success
        assert [row["name"] for row in result.data] == ["Front Plane", "Boss-Extrude1"]

    @pytest.mark.asyncio
    async def test_list_features_falls_back_to_reverse_positions(self, monkeypatch):
        """List features should fall back to model FeatureByPositionReverse when needed."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, feature_type):
                """Test helper for init."""
                self.Name = name
                self._feature_type = feature_type

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return self._feature_type

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                return False

        by_pos = {
            1: _Feature("Boss-Extrude1", "Boss"),
            2: _Feature("Sketch1", "ProfileFeature"),
        }

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: (_ for _ in ()).throw(RuntimeError("not available")),
            FeatureByPositionReverse=lambda pos: by_pos.get(pos),
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 2),
        )

        result = await adapter.list_features(include_suppressed=False)

        assert result.is_success
        assert [row["name"] for row in result.data] == ["Boss-Extrude1", "Sketch1"]

    @pytest.mark.asyncio
    async def test_list_features_suppressed_fallback_uses_is_suppressed2(
        self, monkeypatch
    ):
        """When IsSuppressed is unavailable, list_features should fallback to IsSuppressed2."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            Name = "SuppressedCut"

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return "Cut"

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("IsSuppressed unavailable")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                return (True,)

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return None

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: _Feature(),
            FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        )

        hidden = await adapter.list_features(include_suppressed=False)
        shown = await adapter.list_features(include_suppressed=True)

        assert hidden.is_success
        assert hidden.data == []
        assert shown.is_success
        assert len(shown.data) == 1
        assert shown.data[0]["suppressed"] is True

    @pytest.mark.asyncio
    async def test_list_configurations_supports_tuple_property(self, monkeypatch):
        """list_configurations should handle COM variants exposing names as tuple properties."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = SimpleNamespace(GetConfigurationNames=("Default", "Alt"))
        result = await adapter.list_configurations()

        assert result.is_success
        assert result.data == ["Default", "Alt"]

    @pytest.mark.asyncio
    async def test_list_configurations_falls_back_to_active_configuration(
        self, monkeypatch
    ):
        """list_configurations should fall back to the active configuration name."""
        adapter = self._build_adapter(monkeypatch)

        adapter.currentModel = SimpleNamespace(
            GetConfigurationNames=Mock(return_value=None),
            GetActiveConfiguration=Mock(
                return_value=SimpleNamespace(GetName=Mock(return_value="Default"))
            ),
        )

        result = await adapter.list_configurations()

        assert result.is_success
        assert result.data == ["Default"]

    @pytest.mark.asyncio
    async def test_connect_disconnect_and_document_creation_paths(self, monkeypatch):
        """Test COM connect lifecycle plus model creation/open branches with mocks."""
        adapter = self._build_adapter(monkeypatch)

        co_initialize = Mock()
        co_uninitialize = Mock()
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(
                CoInitialize=co_initialize,
                CoUninitialize=co_uninitialize,
                VT_BYREF=0x4000,
                VT_I4=3,
            ),
            raising=False,
        )

        fake_app = SimpleNamespace(
            Visible=False,
            SetUserPreferenceToggle=Mock(),
            OpenDoc6=Mock(),
            NewDocument=Mock(),
            CloseDoc=Mock(),
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(
                client=SimpleNamespace(
                    GetActiveObject=Mock(side_effect=RuntimeError("no running app")),
                    Dispatch=Mock(return_value=fake_app),
                    VARIANT=lambda _kind, val: val,
                )
            ),
            raising=False,
        )

        await adapter.connect()
        assert adapter.swApp is fake_app
        assert fake_app.Visible is True
        fake_app.SetUserPreferenceToggle.assert_any_call(150, False)
        fake_app.SetUserPreferenceToggle.assert_any_call(149, False)
        co_initialize.assert_called_once()

        fake_open_model = SimpleNamespace(
            GetTitle=lambda: "OpenedAsm",
            GetActiveConfiguration=lambda: None,
            GetSaveTime=lambda: "now",
        )
        fake_app.OpenDoc6.return_value = fake_open_model
        fake_app.GetUserPreferenceStringValue = Mock(
            side_effect=lambda idx: {
                0: "C:/Templates/Part.prtdot",
                1: "",
                2: "",
            }[idx]
        )

        fake_app.NewDocument.side_effect = lambda template, *_args: SimpleNamespace(
            GetTitle=lambda: (
                template.split("/")[-1]
                .replace(".prtdot", "")
                .replace(".asmdot", "")
                .replace(".drwdot", "")
            )
        )

        opened = await adapter.open_model("C:/Models/sample.sldasm")
        assert opened.is_success
        assert opened.data.type == "Assembly"
        assert opened.data.configuration == "Default"

        unsupported = await adapter.open_model("C:/Models/sample.txt")
        assert unsupported.is_error
        assert "Unsupported file type" in (unsupported.error or "")

        part = await adapter.create_part()
        assembly = await adapter.create_assembly()
        drawing = await adapter.create_drawing()
        assert part.is_success and part.data.type == "Part"
        assert assembly.is_success and assembly.data.type == "Assembly"
        assert drawing.is_success and drawing.data.type == "Drawing"

        adapter.currentModel = SimpleNamespace(GetTitle=lambda: "ActiveModel")
        adapter.currentSketch = object()
        adapter.currentSketchManager = object()
        await adapter.disconnect()
        fake_app.SetUserPreferenceToggle.assert_any_call(150, True)
        fake_app.SetUserPreferenceToggle.assert_any_call(149, True)
        assert adapter.swApp is None
        assert adapter.currentSketchManager is None
        co_uninitialize.assert_called_once()

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
    async def test_feature_id_and_mass_properties_tuple_fallback(self, monkeypatch):
        """Feature IDs and mass properties should support common COM compatibility variants."""
        adapter = self._build_adapter(monkeypatch)

        feature_obj = SimpleNamespace(Name="FeatInt", GetID=lambda: 123)
        feature_manager = SimpleNamespace(
            FeatureExtrusion3=Mock(return_value=feature_obj),
            FeatureExtrusion2=Mock(return_value=feature_obj),
            FeatureExtruThin2=Mock(return_value=feature_obj),
            FeatureRevolve2=Mock(return_value=feature_obj),
            FeatureCut3=Mock(return_value=feature_obj),
            FeatureFillet3=Mock(return_value=feature_obj),
            FeatureChamfer=Mock(return_value=feature_obj),
        )
        sketch_manager = SimpleNamespace(
            InsertSketch=Mock(return_value=SimpleNamespace(Name="SketchA")),
            CreateCenterLine=Mock(return_value=object()),
            CreateLine=Mock(return_value=object()),
        )
        extension = SimpleNamespace(
            SelectByID2=Mock(return_value=True),
            CreateMassProperty=Mock(side_effect=RuntimeError("member not found")),
        )
        adapter.currentModel = SimpleNamespace(
            Extension=extension,
            SketchManager=sketch_manager,
            FeatureManager=feature_manager,
            GetMassProperties=(
                0.001,
                0.002,
                0.003,
                4.0e-9,
                7.0e-6,
                0.5,
                11.0,
                22.0,
                33.0,
                44.0,
                55.0,
                66.0,
            ),
        )

        extrude = await adapter.create_extrusion(
            SimpleNamespace(
                depth=10.0,
                draft_angle=0.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
                merge_result=True,
            )
        )
        mass = await adapter.get_mass_properties()

        assert extrude.is_success
        assert extrude.data.id == "123"
        assert mass.is_success
        assert mass.data.volume == pytest.approx(4.0)
        assert mass.data.surface_area == pytest.approx(7.0)
        assert mass.data.mass == pytest.approx(0.5)
        assert mass.data.center_of_mass == [1.0, 2.0, 3.0]
        assert mass.data.moments_of_inertia["Ixx"] == pytest.approx(11.0)
        assert mass.data.moments_of_inertia["Iyy"] == pytest.approx(22.0)
        assert mass.data.moments_of_inertia["Izz"] == pytest.approx(33.0)

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
            "src.solidworks_mcp.adapters.pywin32_adapter.pywintypes",
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
    async def test_save_file_fallback_and_noop_paths(self, monkeypatch, tmp_path):
        """Cover save_file fallback branches: SaveAs fallback, Save3 fallback, and clean-file no-op."""
        adapter = self._build_adapter(monkeypatch)

        target = tmp_path / "out.sldprt"

        # SaveAs3 fails, SaveAs fallback also fails -> explicit error branch.
        adapter.swApp = SimpleNamespace(
            CloseDoc=Mock(side_effect=RuntimeError("locked"))
        )
        adapter.currentModel = SimpleNamespace(
            SaveAs3=Mock(return_value=1),
            SaveAs=Mock(return_value=1),
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.remove",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
        )
        failed_save_as = await adapter.save_file(str(target))
        assert failed_save_as.is_error
        assert "Failed to save as" in (failed_save_as.error or "")

        # SaveAs3 reports numeric success but file is still missing -> file-not-written error.
        adapter.currentModel = SimpleNamespace(SaveAs3=Mock(return_value=0))
        missing_output = await adapter.save_file(str(target))
        assert missing_output.is_error
        assert "File not written after save" in (missing_output.error or "")

        # Save3 raises; fallback Save returns non-success, but existing path means no-op success.
        existing = tmp_path / "existing.sldprt"
        existing.write_text("x", encoding="utf-8")
        adapter.currentModel = SimpleNamespace(
            Save3=Mock(side_effect=RuntimeError("Save3 unavailable")),
            Save=Mock(return_value=1),
            GetPathName=Mock(return_value=str(existing)),
        )
        no_op = await adapter.save_file()
        assert no_op.is_success

    @pytest.mark.asyncio
    async def test_feature_and_configuration_edge_paths(self, monkeypatch):
        """Cover list_features/list_configurations edge cases and guarded feature ops."""
        adapter = self._build_adapter(monkeypatch)

        # Guard branches on no active model.
        assert (await adapter.list_configurations()).is_error
        assert (
            await adapter.create_cut_extrude(
                SimpleNamespace(depth=1.0, draft_angle=0.0, reverse_direction=False)
            )
        ).is_error
        assert (await adapter.add_fillet(1.0, ["E1"])).is_error
        assert (await adapter.add_chamfer(1.0, ["E1"])).is_error
        assert (await adapter.rebuild_model()).is_error

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name, next_feature=None):
                """Test helper for init."""
                self.Name = name
                self._next = next_feature

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("fallback")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                return 1

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                raise RuntimeError("unknown type")

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                raise RuntimeError("walk break")

        dup = _Feature("Dup")
        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: dup,
            FeatureManager=SimpleNamespace(
                GetFeatureCount=Mock(side_effect=RuntimeError("count fail"))
            ),
            FeatureByPositionReverse=Mock(side_effect=RuntimeError("reverse fail")),
        )
        listed = await adapter.list_features(include_suppressed=True)
        assert listed.is_success
        assert listed.data and listed.data[0]["type"] == "Unknown"

        # list_configurations callable/None/string/list branches.
        adapter.currentModel = SimpleNamespace(
            GetConfigurationNames=Mock(return_value=None)
        )
        assert (await adapter.list_configurations()).data == []
        adapter.currentModel = SimpleNamespace(GetConfigurationNames="Default")
        assert (await adapter.list_configurations()).data == ["Default"]
        adapter.currentModel = SimpleNamespace(GetConfigurationNames=["Default", "Alt"])
        assert (await adapter.list_configurations()).data == ["Default", "Alt"]

    @pytest.mark.asyncio
    async def test_feature_creation_failure_paths(self, monkeypatch):
        """Cover failure branches for cut/fillet/chamfer feature creation."""
        adapter = self._build_adapter(monkeypatch)
        model = SimpleNamespace(
            Extension=SimpleNamespace(SelectByID2=Mock(return_value=False)),
            FeatureManager=SimpleNamespace(
                FeatureCut3=Mock(return_value=None),
                FeatureFillet3=Mock(return_value=None),
                FeatureChamfer=Mock(return_value=None),
            ),
        )
        adapter.currentModel = model

        cut_fail = await adapter.create_cut_extrude(
            SimpleNamespace(depth=2.0, draft_angle=0.0, reverse_direction=False)
        )
        assert cut_fail.is_error
        assert "Failed to create cut extrude feature" in (cut_fail.error or "")

        fillet_select_fail = await adapter.add_fillet(1.0, ["Edge1"])
        chamfer_select_fail = await adapter.add_chamfer(1.0, ["Edge1"])
        assert fillet_select_fail.is_error
        assert "Failed to select edge" in (fillet_select_fail.error or "")
        assert chamfer_select_fail.is_error
        assert "Failed to select edge" in (chamfer_select_fail.error or "")

        model.Extension.SelectByID2 = Mock(return_value=True)
        fillet_create_fail = await adapter.add_fillet(1.0, ["Edge1"])
        chamfer_create_fail = await adapter.add_chamfer(1.0, ["Edge1"])
        assert fillet_create_fail.is_error
        assert "Failed to create fillet" in (fillet_create_fail.error or "")
        assert chamfer_create_fail.is_error
        assert "Failed to create chamfer" in (chamfer_create_fail.error or "")

    @pytest.mark.asyncio
    async def test_title_template_and_document_type_fallbacks(self, monkeypatch):
        """Cover _read_model_title, _resolve_template_path, and _get_document_type fallback branches."""
        adapter = self._build_adapter(monkeypatch)

        class _ModelWithTitleProperty:
            """Test suite for ModelWithTitleProperty."""

            GetTitle = 123
            Title = "FromTitleProperty"

        class _ModelUntitled:
            """Test suite for ModelUntitled."""

            def GetTitle(self):
                """Test helper for GetTitle."""
                raise RuntimeError("title fail")

            Title = None

        assert (
            adapter._read_model_title(_ModelWithTitleProperty()) == "FromTitleProperty"
        )
        assert adapter._read_model_title(_ModelUntitled()) == "Untitled"

        adapter.swApp = SimpleNamespace(
            GetUserPreferenceStringValue=Mock(
                side_effect=lambda idx: {
                    8: "C:/Templates/Part.prtdot",
                    0: "C:/Templates/Backup.prtdot",
                }.get(idx, "")
            )
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.os.path.exists",
            lambda p: str(p).endswith("Part.prtdot"),
        )
        resolved = adapter._resolve_template_path([8, 0], ".prtdot")
        assert resolved and resolved.endswith("Part.prtdot")

        adapter.currentModel = None
        assert adapter._get_document_type() == "Unknown"

    @pytest.mark.asyncio
    async def test_create_part_and_assembly_no_template_paths(self, monkeypatch):
        """Cover create_part/create_assembly branches where native creators fail and no template exists."""
        adapter = self._build_adapter(monkeypatch)

        adapter.swApp = SimpleNamespace(
            NewPart=Mock(side_effect=RuntimeError("native part failed")),
            NewAssembly=Mock(side_effect=RuntimeError("native asm failed")),
            GetUserPreferenceStringValue=Mock(return_value=""),
            NewDocument=Mock(return_value=None),
        )

        part_result = await adapter.create_part()
        asm_result = await adapter.create_assembly()
        assert part_result.is_error
        assert "No part template configured" in (part_result.error or "")
        assert asm_result.is_error
        assert "No assembly template configured" in (asm_result.error or "")

    @pytest.mark.asyncio
    async def test_save_guard_non_numeric_success_and_rebuild_failure(
        self, monkeypatch
    ):
        """Cover save guard path, non-numeric Save3 success, and rebuild operation failure branch."""
        adapter = self._build_adapter(monkeypatch)

        no_model_save = await adapter.save_file()
        assert no_model_save.is_error

        adapter.currentModel = SimpleNamespace(
            Save3=Mock(return_value=object()),
            ForceRebuild3=Mock(return_value=False),
        )
        # non-numeric truthy value follows bool(value) branch in _is_success
        save_success = await adapter.save_file()
        assert save_success.is_success

        rebuild_fail = await adapter.rebuild_model()
        assert rebuild_fail.is_error
        assert "Failed to rebuild model" in (rebuild_fail.error or "")

    @pytest.mark.asyncio
    async def test_list_features_additional_fallback_branches(self, monkeypatch):
        """Cover list_features branches for nested suppression failures, dedupe, and reverse traversal errors."""
        adapter = self._build_adapter(monkeypatch)

        class _Feature:
            """Test suite for Feature."""

            def __init__(self, name: str, next_feature=None):
                """Test helper for init."""
                self.Name = name
                self._next = next_feature

            def IsSuppressed(self):
                """Test helper for IsSuppressed."""
                raise RuntimeError("primary suppression unavailable")

            def IsSuppressed2(self, *_args):
                """Test helper for IsSuppressed2."""
                raise RuntimeError("secondary suppression unavailable")

            def GetTypeName2(self):
                """Test helper for GetTypeName2."""
                return "Boss"

            def GetNextFeature(self):
                """Test helper for GetNextFeature."""
                return self._next

        duplicate_1 = _Feature("Dup")
        duplicate_2 = _Feature("Dup")
        duplicate_1._next = duplicate_2
        duplicate_2._next = None

        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: duplicate_1,
            FeatureManager=SimpleNamespace(
                GetFeatureCount=Mock(side_effect=RuntimeError("count unavailable"))
            ),
            FeatureByPositionReverse=Mock(side_effect=RuntimeError("reverse fail")),
        )

        listed = await adapter.list_features(include_suppressed=True)
        assert listed.is_success
        assert len(listed.data) == 1  # dedupe branch
        assert listed.data[0]["suppressed"] is False

        # Cover _append_feature early return when reverse traversal yields None.
        adapter.currentModel = SimpleNamespace(
            FirstFeature=lambda: None,
            FeatureManager=SimpleNamespace(GetFeatureCount=Mock(return_value=1)),
            FeatureByPositionReverse=Mock(return_value=None),
        )
        none_feature = await adapter.list_features(include_suppressed=True)
        assert none_feature.is_success
        assert none_feature.data == []


class TestMockAdapterAdditionalCoverage:
    """Target additional edge paths for mock adapter coverage."""

    @pytest.mark.asyncio
    async def test_uncovered_mock_adapter_branches(self):
        """Test uncovered mock adapter branches."""
        adapter = MockSolidWorksAdapter({})

        # Cover bool/callable compatibility shim and direct method path.
        assert bool(adapter.is_connected) is False
        assert MockSolidWorksAdapter.is_connected(adapter) is False

        await adapter.connect()
        opened_asm = await adapter.open_model("C:/Models/a.sldasm")
        opened_drw = await adapter.open_model("C:/Models/a.slddrw")
        unsupported = await adapter.open_model("C:/Models/a.txt")
        assert opened_asm.is_success
        assert opened_drw.is_success
        assert unsupported.is_error

        closed_with_save = await adapter.close_model(save=True)
        assert closed_with_save.is_success

        no_sketch_exit = await adapter.exit_sketch()
        no_mass = await adapter.get_mass_properties()
        assert no_sketch_exit.status == AdapterResultStatus.WARNING
        assert no_mass.is_error

        await adapter.create_part("ExportPart", "mm")
        exported_default_delay = await adapter.export_file("C:/tmp/out.obj", "obj")
        assert exported_default_delay.is_success
        assert exported_default_delay.execution_time == pytest.approx(1.0)


class TestPyWin32AdapterAdditionalCoverage:
    """Target additional edge paths for pywin32 adapter coverage."""

    @staticmethod
    def _build_adapter(monkeypatch) -> PyWin32Adapter:
        """Test helper for build adapter."""
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

    def test_platform_guard_raises_on_non_windows(self, monkeypatch):
        """Test platform guard raises on non windows."""
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.platform.system",
            lambda: "Linux",
        )
        with pytest.raises(SolidWorksMCPError, match="requires Windows"):
            PyWin32Adapter({})

    @pytest.mark.asyncio
    async def test_connect_failure_and_com_error_branch(self, monkeypatch):
        """Test connect failure and com error branch."""
        adapter = self._build_adapter(monkeypatch)

        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(CoInitialize=Mock(side_effect=RuntimeError("boom"))),
            raising=False,
        )
        with pytest.raises(SolidWorksMCPError, match="Failed to connect"):
            await adapter.connect()

        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.pywintypes",
            SimpleNamespace(com_error=ValueError),
            raising=False,
        )
        com_result = adapter._handle_com_operation(
            "forced_com_error", lambda: (_ for _ in ()).throw(ValueError("bad com"))
        )
        assert com_result.is_error
        assert "COM error in forced_com_error" in (com_result.error or "")

    @pytest.mark.asyncio
    async def test_open_create_and_feature_failure_paths(self, monkeypatch):
        """Test open create and feature failure paths."""
        adapter = self._build_adapter(monkeypatch)

        fake_app = SimpleNamespace(
            OpenDoc6=Mock(return_value=None),
            NewDocument=Mock(return_value=None),
            GetUserPreferenceStringValue=Mock(
                side_effect=lambda idx: {
                    0: "C:/Templates/Part.prtdot",
                    1: "",
                    2: "",
                }.get(idx, "")
            ),
        )
        adapter.swApp = fake_app

        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.pythoncom",
            SimpleNamespace(VT_BYREF=0x4000, VT_I4=3),
            raising=False,
        )
        monkeypatch.setattr(
            "src.solidworks_mcp.adapters.pywin32_adapter.win32com",
            SimpleNamespace(client=SimpleNamespace(VARIANT=lambda _kind, val: val)),
            raising=False,
        )

        failed_part_open = await adapter.open_model("C:/tmp/model.sldprt")
        failed_drawing_open = await adapter.open_model("C:/tmp/model.slddrw")
        assert failed_part_open.is_error
        assert failed_drawing_open.is_error

        failed_part_create = await adapter.create_part()
        failed_assembly_create = await adapter.create_assembly()
        failed_drawing_create = await adapter.create_drawing()
        assert failed_part_create.is_error
        assert failed_assembly_create.is_error
        assert failed_drawing_create.is_error

        adapter.swApp = SimpleNamespace(
            RevisionNumber=Mock(side_effect=[RuntimeError("x"), "Unknown"])
        )
        health = await adapter.health_check()
        assert health.healthy is False

        adapter.currentModel = SimpleNamespace(
            FeatureManager=SimpleNamespace(
                FeatureExtrusion2=Mock(return_value=None),
                FeatureExtruThin2=Mock(return_value=None),
                FeatureRevolve2=Mock(return_value=None),
            )
        )
        extrusion_failed = await adapter.create_extrusion(
            SimpleNamespace(
                depth=10.0,
                draft_angle=0.0,
                reverse_direction=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
        revolve_failed = await adapter.create_revolve(
            SimpleNamespace(
                angle=90.0,
                reverse_direction=False,
                both_directions=False,
                thin_feature=False,
                thin_thickness=None,
            )
        )
        assert extrusion_failed.is_error
        assert revolve_failed.is_error


class TestAdapterCompatibilityFixes:
    """Coverage for adapter compatibility fixes used by real integration tests."""

    @pytest.mark.asyncio
    async def test_pywin32_health_check_with_property_revision_number(
        self, monkeypatch
    ):
        """Test pywin32 health check with property revision number."""
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

        adapter = PyWin32Adapter({})
        adapter.swApp = SimpleNamespace(RevisionNumber="33.2.1")
        health = await adapter.health_check()

        assert health.healthy is True
        assert health.metrics["sw_version"] == "33.2.1"

    @pytest.mark.asyncio
    async def test_circuit_breaker_create_part_accepts_optional_args(self):
        """Test circuit breaker create part accepts optional args."""
        base = MockSolidWorksAdapter({})
        await base.connect()
        cb = CircuitBreakerAdapter(base)

        result = await cb.create_part("CompatPart", "mm")

        assert result.is_success
        assert result.data.name == "CompatPart"

    @pytest.mark.asyncio
    async def test_circuit_breaker_create_assembly_name_fallback(self):
        """Test circuit breaker create assembly name fallback."""

        class NoArgAssemblyAdapter(MockSolidWorksAdapter):
            """Test suite for NoArgAssemblyAdapter."""

            async def create_assembly(self):  # type: ignore[override]
                """Test helper for create assembly."""
                return await super().create_assembly()

        base = NoArgAssemblyAdapter({})
        await base.connect()
        cb = CircuitBreakerAdapter(base)

        result = await cb.create_assembly("NamedAssembly")

        assert result.is_success

    @pytest.mark.asyncio
    async def test_circuit_breaker_exposes_save_file_passthrough(self):
        """Test circuit breaker exposes save file passthrough."""
        base = MockSolidWorksAdapter({})
        await base.connect()
        await base.create_part("SaveCompat", "mm")
        cb = CircuitBreakerAdapter(base)

        result = await cb.save_file("C:/tmp/save_compat.sldprt")

        assert result.is_success


class TestAdapterIntegration:
    """Integration tests for adapter components."""

    @pytest.mark.asyncio
    async def test_adapter_with_circuit_breaker(self, mock_config):
        """Test adapter with circuit breaker protection."""
        mock_config.circuit_breaker_enabled = True
        adapter = await create_adapter(mock_config)

        await adapter.connect()

        # Normal operations should work
        result = await adapter.open_model("test.sldprt")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_adapter_with_connection_pooling(self, mock_config):
        """Test adapter with connection pooling."""
        mock_config.connection_pooling = True
        mock_config.max_connections = 3

        adapter = await create_adapter(mock_config)
        await adapter.connect()

        # Test that operations work with pooled connections
        result = await adapter.create_part("TestPart")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_adapter_error_handling(self, mock_adapter):
        """Test comprehensive adapter error handling."""
        await mock_adapter.connect()

        # Test operation error
        with patch.object(
            mock_adapter, "open_model", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception):
                await mock_adapter.open_model("test.sldprt")

        # Adapter should still be connected after error
        assert mock_adapter.is_connected

    @pytest.mark.asyncio
    async def test_adapter_performance_monitoring(self, mock_adapter, perf_monitor):
        """Test adapter operation performance."""
        await mock_adapter.connect()

        perf_monitor.start()
        result = await mock_adapter.create_part("PerfTestPart")
        perf_monitor.stop()

        assert result.is_success
        # Mock operations should be very fast
        perf_monitor.assert_max_time(0.1)
