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
    SolidWorksConnectionError,
    SolidWorksOperationError,
)


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


class TestPyWin32AdapterBranches:
    """Additional PyWin32Adapter branch coverage with pure mocks."""

    @staticmethod
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
        assert (await adapter.export_file("C:/tmp/out.step", "step")).is_error
        assert (await adapter.get_dimension("D1@Sketch1")).is_error
        assert (await adapter.set_dimension("D1@Sketch1", 20.0)).is_error
        assert (await adapter.rebuild_model()).is_error

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
        adapter.swApp.CloseDoc.assert_called_once_with("Model1")

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
            )
        )
        extrude_thin = await adapter.create_extrusion(
            SimpleNamespace(
                depth=8.0,
                draft_angle=0.0,
                reverse_direction=True,
                thin_feature=True,
                thin_thickness=1.0,
            )
        )
        revolve = await adapter.create_revolve(
            SimpleNamespace(
                angle=180.0,
                reverse_direction=False,
                both_directions=True,
                thin_feature=False,
                thin_thickness=None,
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

        extension.SelectByID2.assert_any_call(
            "Top Plane", "PLANE", 0, 0, 0, False, 0, None, 0
        )
        assert feature_manager.FeatureExtrusion2.called
        assert feature_manager.FeatureExtruThin2.called
        assert feature_manager.FeatureRevolve2.called
        assert feature_manager.FeatureCut3.called
        assert feature_manager.FeatureFillet3.called
        assert feature_manager.FeatureChamfer.called


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
