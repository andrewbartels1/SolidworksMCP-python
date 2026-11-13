"""Pytest configuration and fixtures for SolidWorks MCP Server tests."""

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import pytest_asyncio
from fastmcp import FastMCP

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer

# Test configuration
os.environ["USE_MOCK_SOLIDWORKS"] = "true"

_REAL_INTEGRATION = os.getenv(
    "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes", "on"}

# The real adapter pauses after every COM operation so live SolidWorks can
# finish its idle-time UI work (COM pitfall #26). Fake-COM unit tests have
# nothing to wait for; live runs keep the defaults unless overridden.
if not _REAL_INTEGRATION:
    os.environ.setdefault("SOLIDWORKS_MCP_COM_SETTLE_SECONDS", "0")
    os.environ.setdefault("SOLIDWORKS_MCP_DOC_SETTLE_SECONDS", "0")

# A non-live run must never start SolidWorks. Creating SldWorks.Application
# from a process outside the desktop session (an SSH shell, CI) starts a hidden
# SLDWORKS.exe nobody can see or close. Every Dispatch / EnsureDispatch /
# DispatchEx ends in pythoncom.CoCreateInstance[Ex], so wrap those: a
# SolidWorks class fails like an unregistered one, and the test that tried
# fails (see _no_solidworks_launch). Attaching (GetActiveObject) is untouched.
_SOLIDWORKS_LAUNCH_ATTEMPTS: list[str] = []


def _install_solidworks_launch_guard() -> None:
    """Make SolidWorks COM object creation raise instead of launching it."""
    try:
        import pythoncom
        import pywintypes
    except ImportError:
        return

    try:
        sw_clsids = {str(pywintypes.IID("SldWorks.Application")).upper()}
    except pywintypes.com_error:
        sw_clsids = set()

    def _is_solidworks(clsid: Any) -> bool:
        text = str(clsid)
        if text.lower().startswith("sldworks."):
            return True
        if not text.startswith("{"):
            try:
                text = str(pywintypes.IID(text))
            except pywintypes.com_error:
                return False
        return text.upper() in sw_clsids

    def _guard(create: Any) -> Any:
        def guarded(clsid: Any, *args: Any, **kwargs: Any) -> Any:
            if _is_solidworks(clsid):
                _SOLIDWORKS_LAUNCH_ATTEMPTS.append(f"{create.__name__}({clsid!r})")
                raise pythoncom.com_error(
                    -2147221005, "Invalid class string", None, None
                )
            return create(clsid, *args, **kwargs)

        guarded.solidworks_launch_guard = True  # type: ignore[attr-defined]
        return guarded

    pythoncom.CoCreateInstance = _guard(pythoncom.CoCreateInstance)
    pythoncom.CoCreateInstanceEx = _guard(pythoncom.CoCreateInstanceEx)


if not _REAL_INTEGRATION:
    _install_solidworks_launch_guard()

# Keep the embedding model (sentence-transformers / all-MiniLM-L6-v2) fully
# local during tests. Without this every SentenceTransformer(...) construction
# fires ~30 HuggingFace Hub HEAD requests to revalidate the already-cached
# model files - slow, and it floods the live-log with httpx/huggingface_hub
# noise on whichever test happens to trigger a docs-discovery RAG rebuild.
# setdefault so a dev can still `HF_HUB_OFFLINE=0 ...` to refresh the cache.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def pytest_configure(config: pytest.Config) -> None:
    """Silence third-party INFO chatter that otherwise dominates the live log.

    faiss's AVX-probe lines, huggingface_hub's cache-hit HEADs, httpx request
    logging and sentence-transformers' load banner add nothing to a test
    report - they just bury the actual PASSED/FAILED lines, especially in the
    batched real-SolidWorks run.
    """
    import logging

    for name in (
        "httpx",
        "httpcore",
        "huggingface_hub",
        "sentence_transformers",
        "transformers",
        "faiss",
        "faiss.loader",
        "filelock",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


@pytest.fixture
def solidworks_launch_attempts() -> list[str]:
    """SolidWorks creations the launch guard refused (cleared by the caller)."""
    return _SOLIDWORKS_LAUNCH_ATTEMPTS


@pytest.fixture(autouse=True)
def _no_solidworks_launch() -> Generator[None]:
    """Fail any test whose code tried to start SolidWorks."""
    start = len(_SOLIDWORKS_LAUNCH_ATTEMPTS)
    yield
    attempts = _SOLIDWORKS_LAUNCH_ATTEMPTS[start:]
    del _SOLIDWORKS_LAUNCH_ATTEMPTS[start:]
    if attempts:
        pytest.fail(
            "Code under test tried to launch SolidWorks outside a live run: "
            + ", ".join(attempts)
            + ". Attach with GetActiveObject or go through the adapter."
        )


@pytest.fixture(autouse=True)
def _no_real_type_library(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the API lookup tools off this machine's SolidWorks type library.

    The lookups build their index from the installed type library when none
    is found, and discovery then rebuilds the RAG index (seconds of
    embedding). Outside a live run that would make results depend on what
    is installed and write an index into the repo, so the loader reports no
    type library. Tests that want one patch in a fake.
    """
    if request.node.get_closest_marker("solidworks_only"):
        return
    from solidworks_mcp.tools import docs_discovery
    from solidworks_mcp.tools.type_library import TypeLibraryUnavailable

    def _no_library(*_args: object, **_kwargs: object) -> None:
        raise TypeLibraryUnavailable("No SolidWorks type library in this test.")

    monkeypatch.setattr(docs_discovery, "load_type_library", _no_library)
    monkeypatch.setattr(docs_discovery, "target_version", _no_library)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path]:
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
) -> AsyncGenerator[MockSolidWorksAdapter]:
    """Create mock SolidWorks adapter."""
    adapter = await create_adapter(mock_config)
    await adapter.connect()
    yield adapter
    await adapter.disconnect()


@pytest_asyncio.fixture
async def mcp_server(mock_config: SolidWorksMCPConfig) -> AsyncGenerator[FastMCP]:
    """Create FastMCP server instance."""
    mcp = FastMCP("Test SolidWorks MCP Server")
    yield mcp


@pytest_asyncio.fixture
async def solidworks_server(
    mock_config: SolidWorksMCPConfig,
) -> AsyncGenerator[SolidWorksMCPServer]:
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


@pytest.fixture
def import_without():
    """Import a module in a child interpreter with some dependencies blocked.

    Used to test the "dependency not installed" fallbacks (pywin32,
    pydantic-ai, ...). A child process keeps the blocked import out of this
    test session; coverage measures it via ``patch = subprocess``.

    Call it with the module to import, the modules to block, and the module
    attributes to read; it returns those attributes (``repr`` of any value that
    is not JSON-serialisable) as a dict.
    """
    import json
    import subprocess
    import sys

    def _run(module: str, blocked: list[str], attributes: list[str]) -> dict:
        code = (
            "import json, sys\n"
            f"for name in {blocked!r}:\n"
            "    sys.modules[name] = None\n"
            f"import {module} as target\n"
            "out = {}\n"
            f"for attr in {attributes!r}:\n"
            "    value = getattr(target, attr)\n"
            "    try:\n"
            "        json.dumps(value)\n"
            "        out[attr] = value\n"
            "    except TypeError:\n"
            "        out[attr] = repr(value)\n"
            "print(json.dumps(out))\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.strip().splitlines()[-1])

    return _run
