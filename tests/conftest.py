"""
Pytest configuration and fixtures for SolidWorks MCP Server tests.

This module provides common fixtures, test utilities, and configuration
for comprehensive testing of the SolidWorks MCP Server.
"""

import asyncio
import inspect
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastmcp import FastMCP
from types import SimpleNamespace

from src.solidworks_mcp.config import (
    SolidWorksMCPConfig,
    DeploymentMode,
    SecurityLevel,
    AdapterType,
)
from src.solidworks_mcp.adapters import create_adapter
from src.solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from src.solidworks_mcp.server import SolidWorksMCPServer


# Test configuration
os.environ["USE_MOCK_SOLIDWORKS"] = "true"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_config() -> SolidWorksMCPConfig:
    """Create mock configuration for testing."""
    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        adapter_type=AdapterType.MOCK,
        mock_solidworks=True,
        log_level="DEBUG",
        host="127.0.0.1",
        port=8000,
        worker_processes=1,
        solidworks_path="mock://solidworks",
        max_retries=3,
        timeout_seconds=30.0,
        circuit_breaker_enabled=True,
        connection_pooling=True,
        max_connections=5,
        enable_cors=False,
        api_key_required=False,
        rate_limit_enabled=False,
        allowed_origins=[],
        api_keys=[],
    )


@pytest.fixture
def strict_config() -> SolidWorksMCPConfig:
    """Create strict security configuration for testing."""
    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.REMOTE,
        security_level=SecurityLevel.STRICT,
        adapter_type=AdapterType.MOCK,
        mock_solidworks=True,
        log_level="INFO",
        host="0.0.0.0",
        port=8080,
        worker_processes=4,
        solidworks_path="mock://solidworks",
        max_retries=5,
        timeout_seconds=60.0,
        circuit_breaker_enabled=True,
        connection_pooling=True,
        max_connections=10,
        enable_cors=True,
        api_key_required=True,
        rate_limit_enabled=True,
        allowed_origins=["http://localhost:3000"],
        api_keys=["test-key-123"],
    )


@pytest_asyncio.fixture
async def mock_adapter(
    mock_config: SolidWorksMCPConfig,
) -> AsyncGenerator[MockSolidWorksAdapter, None]:
    """Create mock SolidWorks adapter."""
    adapter = await create_adapter(mock_config)
    await adapter.connect()
    yield adapter
    await adapter.disconnect()


@pytest_asyncio.fixture
async def mcp_server(mock_config: SolidWorksMCPConfig) -> AsyncGenerator[FastMCP, None]:
    """Create FastMCP server instance."""
    mcp = FastMCP("Test SolidWorks MCP Server")

    # Backward-compatible tool registry expected by existing tests.
    mcp._tools = []
    original_tool = mcp.tool

    def compat_tool(*args, **kwargs):
        """Test helper for compat tool."""
        decorator = original_tool(*args, **kwargs)

        def _wrap(func):
            """Test helper for wrap."""
            wrapped = decorator(func)

            async def _compat_runner(*runner_args, **runner_kwargs):
                """Test helper for compat runner."""
                payload = runner_kwargs.get("input_data")
                if payload is None and runner_args:
                    payload = runner_args[0]

                params = list(inspect.signature(func).parameters.values())
                if len(params) == 0:
                    result = await func()
                elif len(params) == 1 and payload is not None:
                    result = await func(payload)
                else:
                    result = await func(*runner_args, **runner_kwargs)

                if isinstance(result, dict) and "data" not in result:
                    payload_key_order = [
                        "model",
                        "part",
                        "assembly",
                        "drawing",
                        "analysis",
                        "export",
                        "workflow",
                        "template",
                        "optimization",
                        "recording_session",
                        "recorded_macro",
                    ]
                    payload_items = {
                        k: v
                        for k, v in result.items()
                        if k not in ("status", "message", "execution_time")
                    }
                    selected = None
                    for key in payload_key_order:
                        if key in payload_items:
                            selected = payload_items[key]
                            break
                    if selected is None and len(payload_items) == 1:
                        selected = next(iter(payload_items.values()))
                    if selected is None:
                        dict_payloads = [
                            v for v in payload_items.values() if isinstance(v, dict)
                        ]
                        if len(dict_payloads) == 1:
                            selected = dict_payloads[0]
                    if selected is None:
                        selected = payload_items
                    result["data"] = selected

                return result

            mcp._tools.append(
                SimpleNamespace(
                    name=getattr(func, "__name__", "unknown"),
                    func=_compat_runner,
                    handler=_compat_runner,
                )
            )
            return wrapped

        return _wrap

    mcp.tool = compat_tool
    yield mcp


@pytest_asyncio.fixture
async def solidworks_server(
    mock_config: SolidWorksMCPConfig,
) -> AsyncGenerator[SolidWorksMCPServer, None]:
    """Create full SolidWorks MCP Server instance."""
    server = SolidWorksMCPServer(mock_config)
    await server.setup()
    yield server
    await server.stop()


class MockSolidWorksApp:
    """Mock SolidWorks application for testing."""

    def __init__(self):
        """Test helper for init."""
        self.active_doc = None
        self.documents = []
        self.is_connected = True

    def get_active_document(self) -> Mock:
        """Mock getting active document."""
        if not self.active_doc:
            self.active_doc = Mock()
            self.active_doc.GetTitle.return_value = "Test Part"
            self.active_doc.GetPathName.return_value = "C:\\test\\test_part.sldprt"
            self.active_doc.GetType.return_value = 1  # Part document
        return self.active_doc

    def open_document(self, path: str) -> Mock:
        """Mock opening a document."""
        doc = Mock()
        doc.GetTitle.return_value = Path(path).stem
        doc.GetPathName.return_value = path
        doc.GetType.return_value = 1
        self.documents.append(doc)
        self.active_doc = doc
        return doc

    def close_document(self, doc_name: str) -> bool:
        """Mock closing a document."""
        self.documents = [d for d in self.documents if d.GetTitle() != doc_name]
        if self.active_doc and self.active_doc.GetTitle() == doc_name:
            self.active_doc = self.documents[0] if self.documents else None
        return True


@pytest.fixture
def mock_solidworks_app() -> MockSolidWorksApp:
    """Create mock SolidWorks application."""
    return MockSolidWorksApp()


class TestResult:
    """Helper class for test result validation."""

    @staticmethod
    def assert_success(result: dict[str, Any]) -> None:
        """Assert that a tool result indicates success."""
        assert result["status"] == "success", f"Expected success, got: {result}"
        assert "message" in result

    @staticmethod
    def assert_error(result: dict[str, Any], expected_error: str | None = None) -> None:
        """Assert that a tool result indicates an error."""
        assert result["status"] == "error", f"Expected error, got: {result}"
        assert "message" in result
        if expected_error:
            assert expected_error in result["message"]

    @staticmethod
    def assert_has_keys(result: dict[str, Any], *keys: str) -> None:
        """Assert that result has all specified keys."""
        for key in keys:
            assert key in result, f"Missing key '{key}' in result: {result}"


@pytest.fixture
def test_result() -> type[TestResult]:
    """Provide TestResult helper class."""
    return TestResult


# Async test utilities
class AsyncTestHelper:
    """Helper class for async testing."""

    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """Run coroutine with timeout."""
        return await asyncio.wait_for(coro, timeout=timeout)

    @staticmethod
    def create_mock_async_result(
        return_value: Any = None, exception: Exception | None = None
    ):
        """Create mock async result."""
        future = asyncio.Future()
        if exception:
            future.set_exception(exception)
        else:
            future.set_result(return_value)
        return future


@pytest.fixture
def async_helper() -> AsyncTestHelper:
    """Provide AsyncTestHelper utilities."""
    return AsyncTestHelper()


# Test data factories
class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def create_part_data() -> dict[str, Any]:
        """Create test part data."""
        return {
            "name": "test_part",
            "template": "standard_part",
            "units": "mm",
            "material": "Steel",
        }

    @staticmethod
    def create_sketch_data() -> dict[str, Any]:
        """Create test sketch data."""
        return {
            "plane": "Front Plane",
            "sketch_name": "test_sketch",
        }

    @staticmethod
    def create_extrusion_data() -> dict[str, Any]:
        """Create test extrusion data."""
        return {
            "sketch_name": "test_sketch",
            "depth": 10.0,
            "direction": "blind",
            "reverse": False,
        }

    @staticmethod
    def create_dimension_data() -> dict[str, Any]:
        """Create test dimension data."""
        return {
            "dimension_type": "linear",
            "entity1": "edge1",
            "entity2": "edge2",
            "position_x": 100.0,
            "position_y": 50.0,
            "precision": 2,
        }


@pytest.fixture
def test_data() -> TestDataFactory:
    """Provide TestDataFactory."""
    return TestDataFactory()


# Performance testing utilities
class PerformanceMonitor:
    """Monitor performance during tests."""

    def __init__(self):
        """Test helper for init."""
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start timing."""
        import time

        self.start_time = time.time()

    def stop(self):
        """Stop timing."""
        import time

        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return self.end_time - self.start_time

    def assert_max_time(self, max_seconds: float):
        """Assert that operation completed within max time."""
        elapsed = self.elapsed
        assert elapsed <= max_seconds, (
            f"Operation took {elapsed}s, max allowed: {max_seconds}s"
        )


@pytest.fixture
def perf_monitor() -> PerformanceMonitor:
    """Provide PerformanceMonitor."""
    return PerformanceMonitor()
