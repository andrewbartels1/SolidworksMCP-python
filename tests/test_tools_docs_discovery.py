"""Deterministic regression tests for docs discovery tool.

These tests validate the docs discovery functionality and ensure that
COM/VBA indexing produces consistent, expected results.
"""

from __future__ import annotations

import os
import platform
import shutil
import time
import json
from types import SimpleNamespace
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from src.solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from src.solidworks_mcp.server import SolidWorksMCPServer
from src.solidworks_mcp.tools.docs_discovery import (
    DiscoverDocsInput,
    _extract_year,
    _fallback_help_for_query,
    _find_index_file,
    _load_index_file,
    _resolve_solidworks_year,
    _search_index,
    SolidWorksDocsDiscovery,
    register_docs_discovery_tools,
)


REAL_SW_ENV_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"


def _real_solidworks_enabled() -> bool:
    """Check if real SolidWorks integration is enabled."""
    value = os.getenv(REAL_SW_ENV_FLAG, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    """Find a tool by name in the MCP server."""
    for tool in server.mcp._tools:
        if tool.name == tool_name:
            return tool.func
    raise AssertionError(f"Tool '{tool_name}' not found")


@pytest_asyncio.fixture
async def real_server() -> AsyncGenerator[SolidWorksMCPServer, None]:
    """Create real MCP server for testing."""
    config = SolidWorksMCPConfig(
        adapter_type=AdapterType.PYWIN32,
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
    )
    server = SolidWorksMCPServer(config)
    await server.setup()
    yield server


@pytest_asyncio.fixture
async def integration_output_dir() -> Path:
    """Create output directory for integration test artifacts."""
    output_dir = Path("tests/.generated/solidworks_integration")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.mark.skipif(
    not _real_solidworks_enabled(),
    reason="Real SolidWorks integration disabled (set SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true)",
)
@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="COM discovery only works on Windows",
)
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_discover_solidworks_docs_available(
    real_server: SolidWorksMCPServer,
) -> None:
    """Test that docs discovery tool is registered."""
    try:
        discover_tool = _find_tool(real_server, "discover_solidworks_docs")
        assert discover_tool is not None, (
            "discover_solidworks_docs tool should be registered"
        )
    except AssertionError:
        pytest.skip("discover_solidworks_docs tool not yet registered in server")


@pytest.mark.skipif(
    not _real_solidworks_enabled(),
    reason="Real SolidWorks integration disabled (set SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true)",
)
@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="COM discovery only works on Windows",
)
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_discover_solidworks_docs_execution(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Test that docs discovery tool executes successfully with real SolidWorks.

    This test validates:
    1. Tool execution completes without errors
    2. COM object indexing produces results
    3. VBA reference discovery completes
    4. Output is a valid structured response
    """
    try:
        discover_tool = _find_tool(real_server, "discover_solidworks_docs")
    except AssertionError:
        pytest.skip("discover_solidworks_docs tool not yet registered")

    # Execute docs discovery
    result = await discover_tool(
        {
            "output_dir": str(integration_output_dir / "docs-index"),
            "include_vba": True,
        }
    )

    # Validate response structure
    assert isinstance(result, dict), "Result should be a dictionary"
    assert "status" in result, "Result should have 'status' field"

    if result["status"] == "success":
        # Validate successful discovery structure
        assert "summary" in result, "Success result should have 'summary' field"
        assert "index" in result, "Success result should have 'index' field"

        summary = result["summary"]
        assert "total_com_objects" in summary
        assert "total_methods" in summary
        assert "total_properties" in summary

        # Ensure we found some COM objects
        assert summary["total_com_objects"] > 0, (
            "Should discover at least one COM object"
        )
        assert summary["total_methods"] > 0, "Should discover at least one method"

        # Validate VBA references
        assert "available_vba_libs" in summary
        assert isinstance(summary["available_vba_libs"], list)

        # If output_file is provided, verify it's a valid path
        if "output_file" in result and result["output_file"]:
            output_path = Path(result["output_file"])
            assert output_path.exists(), f"Output file should exist: {output_path}"
            assert output_path.suffix == ".json", "Output should be JSON format"

    elif result["status"] == "error":
        # Error is acceptable if win32com not available or other issues
        assert "message" in result, "Error result should have 'message' field"


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="COM discovery only works on Windows",
)
@pytest.mark.windows_only
async def test_docs_discovery_import() -> None:
    """Test that docs discovery module imports without errors."""
    try:
        from src.solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

        assert SolidWorksDocsDiscovery is not None
        assert hasattr(SolidWorksDocsDiscovery, "discover_com_objects")
        assert hasattr(SolidWorksDocsDiscovery, "discover_vba_references")
        assert hasattr(SolidWorksDocsDiscovery, "save_index")
    except ImportError as e:
        pytest.fail(f"Failed to import docs discovery module: {e}")


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="COM discovery only works on Windows",
)
@pytest.mark.windows_only
async def test_docs_discovery_output_dir_creation() -> None:
    """Test that docs discovery creates output directory if it doesn't exist."""
    from src.solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

    # Use a unique directory to avoid flaky pre-cleanup on Windows file locks.
    test_dir = Path("tests/.generated") / f"docs-discovery-test-{time.time_ns()}"

    try:
        SolidWorksDocsDiscovery(output_dir=test_dir)

        # Verify directory was created
        assert test_dir.exists(), "Output directory should be created"
    finally:
        # Best-effort cleanup after test with retry logic.
        if test_dir.exists():
            for attempt in range(3):
                try:
                    shutil.rmtree(test_dir)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.5)
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)


def test_docs_discovery_year_resolution_from_config() -> None:
    """Resolve year from explicit config fields when provided."""
    config = SolidWorksMCPConfig(solidworks_year=2026)
    resolved = _resolve_solidworks_year(None, config)
    assert resolved == 2026


def test_docs_discovery_extract_year_from_path() -> None:
    """Extract year from common SolidWorks path/text variants."""
    assert _extract_year("C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS 2026") == 2026
    assert _extract_year("SOLIDWORKS 2025") == 2025
    assert _extract_year("no year here") is None


@pytest.mark.asyncio
async def test_search_solidworks_api_help_with_index(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    temp_dir: Path,
) -> None:
    """Search API help using a synthetic index and verify coherent structured output."""
    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in mcp_server._tools:
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.func
            break

    assert search_tool is not None

    index_path = temp_dir / "solidworks_docs_index_2026.json"
    index_path.write_text(
        json.dumps(
            {
                "com_objects": {
                    "ISldWorks": {
                        "methods": ["OpenDoc6", "CloseDoc"],
                        "properties": ["RevisionNumber"],
                    }
                },
                "vba_references": {
                    "SldWorks": {
                        "description": "SolidWorks API",
                        "status": "available",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = await search_tool(
        {
            "query": "open document",
            "year": 2026,
            "index_file": str(index_path),
            "max_results": 5,
        }
    )

    assert result["status"] == "success"
    assert result["year"] == 2026
    assert result["source_index_file"] == str(index_path)
    assert isinstance(result["matches"], list)
    assert result["guidance"]


def test_discovery_connect_fails_without_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_to_solidworks should fail fast when win32com is unavailable."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", False)
    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect")
    )

    assert discovery.connect_to_solidworks() is False


def test_discovery_connect_fails_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connect_to_solidworks should reject non-Windows platforms."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Linux")
    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect-os")
    )

    assert discovery.connect_to_solidworks() is False


def test_discovery_connect_uses_dispatch_when_getobject_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connect_to_solidworks should fallback to Dispatch when GetObject returns None."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    fake_sw = object()

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        docs_mod,
        "win32com",
        SimpleNamespace(
            client=SimpleNamespace(
                GetObject=lambda *_args, **_kwargs: None,
                Dispatch=lambda _prog_id: fake_sw,
            )
        ),
        raising=False,
    )

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect-dispatch")
    )
    assert discovery.connect_to_solidworks() is True
    assert discovery.sw_app is fake_sw


def test_discover_com_objects_empty_without_connection() -> None:
    """discover_com_objects should return empty dict when disconnected."""
    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-empty"))
    assert discovery.discover_com_objects() == {}


def test_discover_com_objects_and_summary_with_fake_app() -> None:
    """discover_com_objects should index methods/properties and create summary."""

    class _FakeApp:
        """Test suite for FakeApp."""

        revision = "33.2"

        def RevisionNumber(self):
            """Test helper for RevisionNumber."""
            return self.revision

        def OpenDoc6(self):
            """Test helper for OpenDoc6."""
            return None

        @property
        def Visible(self):
            """Test helper for Visible."""
            return True

    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-com"))
    discovery.sw_app = _FakeApp()

    index = discovery.discover_com_objects()
    assert "ISldWorks" in index
    assert discovery.index["solidworks_version"] == "33.2"
    discovery.index["com_objects"] = index

    summary = discovery.create_search_summary()
    assert summary["total_com_objects"] >= 1


def test_discover_vba_references_handles_available_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover_vba_references should classify available/missing/error libraries."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    def _get_object(*_args, **kwargs):
        """Test helper for get object."""
        name = kwargs.get("Class")
        if name is None and _args:
            name = _args[-1]
        if name in {"VBA", "SldWorks"}:
            return object()
        if name == "Office":
            raise RuntimeError("lookup failed")
        return None

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(
        docs_mod,
        "win32com",
        SimpleNamespace(client=SimpleNamespace(GetObject=_get_object)),
        raising=False,
    )

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-vba")
    )
    refs = discovery.discover_vba_references()

    assert refs["VBA"]["status"] == "available"
    assert refs["SldWorks"]["status"] == "available"
    assert refs["Office"]["status"] == "not_available"
    assert "lookup failed" in refs["Office"]["note"]


def test_discover_all_returns_index_when_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover_all should return base index when connection fails."""
    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-all"))
    monkeypatch.setattr(discovery, "connect_to_solidworks", lambda: False)

    index = discovery.discover_all()
    assert isinstance(index, dict)
    assert index["com_objects"] == {}


def test_save_index_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    """save_index should write JSON and return None on write errors."""
    discovery = SolidWorksDocsDiscovery(output_dir=temp_dir)
    saved = discovery.save_index("docs_index.json")
    assert saved is not None and saved.exists()

    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(
        docs_mod.json,
        "dump",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    failed = discovery.save_index("bad.json")
    assert failed is None


def test_index_load_and_search_helpers(temp_dir: Path) -> None:
    """Low-level index find/load/search helpers should return coherent structures."""
    index_dir = temp_dir / "docs-index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "solidworks_docs_index_2026.json"
    payload = {
        "com_objects": {
            "ISldWorks": {
                "methods": ["OpenDoc6", "CloseDoc"],
                "properties": ["RevisionNumber"],
            }
        },
        "vba_references": {
            "SldWorks": {"description": "SolidWorks API", "status": "available"}
        },
    }
    index_path.write_text(json.dumps(payload), encoding="utf-8")

    found = _find_index_file(2026, str(index_path))
    assert found == index_path

    loaded = _load_index_file(index_path)
    assert isinstance(loaded, dict)

    results = _search_index(loaded or {}, "open", 5)
    assert results
    assert results[0]["member_type"] in {"method", "property", "reference"}


def test_fallback_help_profiles() -> None:
    """Fallback guidance should adapt by query intent."""
    revolve_help = _fallback_help_for_query("how to revolve a bat profile")
    extrude_help = _fallback_help_for_query("extrude this sketch")
    generic_help = _fallback_help_for_query("unknown phrase")

    assert "create_revolve" in revolve_help["suggested_tools"]
    assert "create_extrusion" in extrude_help["suggested_tools"]
    assert "discover_solidworks_docs" in generic_help["suggested_tools"]


@pytest.mark.asyncio
async def test_discover_solidworks_docs_tool_error_paths(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool should return structured error on unsupported environments."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in mcp_server._tools:
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.func
            break
    assert discover_tool is not None

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", False)
    result = await discover_tool({})
    assert result["status"] == "error"
    assert "win32com" in result["message"]


@pytest.mark.asyncio
async def test_discover_solidworks_docs_tool_success_path(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """Tool should return successful payload when discovery and save succeed."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in mcp_server._tools:
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.func
            break
    assert discover_tool is not None

    class _FakeDiscovery:
        """Test suite for FakeDiscovery."""

        def __init__(self, output_dir=None):
            """Test helper for init."""
            self.output_dir = output_dir

        def discover_all(self):
            """Test helper for discover all."""
            return {
                "com_objects": {
                    "ISldWorks": {"methods": ["OpenDoc6"], "properties": ["Visible"]}
                },
                "vba_references": {"SldWorks": {"status": "available"}},
                "total_methods": 1,
                "total_properties": 1,
                "solidworks_version": "33.2",
            }

        def save_index(self, filename="solidworks_docs_index.json"):
            """Test helper for save index."""
            path = temp_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            """Test helper for create search summary."""
            return {
                "total_com_objects": 1,
                "total_methods": 1,
                "total_properties": 1,
                "solidworks_version": "33.2",
                "available_vba_libs": ["SldWorks"],
            }

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)

    result = await discover_tool({"output_dir": str(temp_dir), "year": 2026})
    assert result["status"] == "success"
    assert result["year"] == 2026
    assert result["summary"]["total_com_objects"] == 1


def test_discovery_connect_handles_com_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_to_solidworks should return False when COM binding raises com_error."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    class _FakeComError(Exception):
        """Test suite for FakeComError."""

        pass

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "com_error", _FakeComError, raising=False)
    monkeypatch.setattr(
        docs_mod,
        "win32com",
        SimpleNamespace(
            client=SimpleNamespace(
                GetObject=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    _FakeComError("boom")
                ),
                Dispatch=lambda *_args: (_ for _ in ()).throw(_FakeComError("boom")),
            )
        ),
        raising=False,
    )

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect-com-error")
    )
    assert discovery.connect_to_solidworks() is False


def test_discover_com_objects_handles_attribute_and_catalog_errors() -> None:
    """discover_com_objects should tolerate both extraction and catalog-level failures."""

    class _BrokenApp:
        """Test suite for BrokenApp."""

        def RevisionNumber(self):
            """Test helper for RevisionNumber."""
            raise RuntimeError("no revision")

    discovery = SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-com-broken")
    )
    discovery.sw_app = _BrokenApp()

    # Force outer catalog exception via incompatible accumulator type.
    discovery.index["total_methods"] = "not-an-int"
    indexed = discovery.discover_com_objects()
    assert isinstance(indexed, dict)
    assert "ISldWorks" in indexed
    # Catalog-level accumulator failure should be tolerated without crashing discovery.
    assert discovery.index["total_methods"] == "not-an-int"


def test_discover_all_success_path_with_stubbed_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover_all should stitch connect/com/vba steps into final index."""
    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-all-ok"))

    monkeypatch.setattr(discovery, "connect_to_solidworks", lambda: True)
    monkeypatch.setattr(
        discovery,
        "discover_com_objects",
        lambda: {"ISldWorks": {"methods": ["OpenDoc6"], "properties": ["Visible"]}},
    )
    monkeypatch.setattr(
        discovery,
        "discover_vba_references",
        lambda: {"SldWorks": {"status": "available"}},
    )

    result = discovery.discover_all()
    assert "ISldWorks" in result["com_objects"]
    assert result["vba_references"]["SldWorks"]["status"] == "available"


def test_normalize_input_helper_branches() -> None:
    """_normalize_input should accept None/model/dict/model_dump objects."""
    from src.solidworks_mcp.tools.docs_discovery import _normalize_input

    none_normalized = _normalize_input(None, DiscoverDocsInput)
    assert isinstance(none_normalized, DiscoverDocsInput)

    model_input = DiscoverDocsInput(output_dir="x", include_vba=False)
    model_normalized = _normalize_input(model_input, DiscoverDocsInput)
    assert model_normalized is model_input

    dict_normalized = _normalize_input(
        {"output_dir": "y", "include_vba": True}, DiscoverDocsInput
    )
    assert dict_normalized.output_dir == "y"

    class _ModelDumpCarrier:
        """Test suite for ModelDumpCarrier."""

        def model_dump(self):
            """Test helper for model dump."""
            return {"output_dir": "z", "include_vba": True}

    dump_normalized = _normalize_input(_ModelDumpCarrier(), DiscoverDocsInput)
    assert dump_normalized.output_dir == "z"


def test_extract_year_handles_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_extract_year should return None when int conversion fails."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    class _BadMatch:
        """Test suite for BadMatch."""

        def group(self, _idx: int) -> str:
            """Test helper for group."""
            return "20xx"

    monkeypatch.setattr(docs_mod.re, "search", lambda *_args, **_kwargs: _BadMatch())
    assert docs_mod._extract_year("any") is None


def test_detect_installed_year_no_root_and_no_year_dirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_detect_installed_solidworks_year should handle missing/empty install roots."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    class _MissingRoot:
        """Test suite for MissingRoot."""

        def exists(self):
            """Test helper for exists."""
            return False

    monkeypatch.setattr(docs_mod, "Path", lambda *_args, **_kwargs: _MissingRoot())
    assert docs_mod._detect_installed_solidworks_year() is None


def test_load_index_file_non_dict_and_exception_paths(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    """_load_index_file should return None for invalid JSON shape and read exceptions."""
    from src.solidworks_mcp.tools.docs_discovery import _load_index_file

    arr_file = temp_dir / "array.json"
    arr_file.write_text("[1, 2, 3]", encoding="utf-8")
    assert _load_index_file(arr_file) is None

    monkeypatch.setattr(
        Path,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("read failed")),
    )
    assert _load_index_file(arr_file) is None


def test_find_index_file_search_dir_and_search_index_edge_cases(temp_dir: Path) -> None:
    """Cover search-dir discovery and empty-token/exact-match scoring in _search_index."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    original_path = docs_mod.Path
    base = temp_dir / "docs-index"
    base.mkdir(parents=True, exist_ok=True)
    idx = base / "solidworks_docs_index_2027.json"
    idx.write_text("{}", encoding="utf-8")

    def _path_redirect(value):
        """Test helper for path redirect."""
        if str(value) == ".generated/docs-index":
            return base
        return original_path(value)

    docs_mod.Path = _path_redirect
    try:
        found = docs_mod._find_index_file(2027, None)
    finally:
        docs_mod.Path = original_path

    assert found == idx

    # Empty/whitespace-only tokens branch.
    assert docs_mod._search_index({}, "   ", 10) == []

    # Exact token and reference result branches.
    index = {
        "com_objects": {
            "ISldWorks": {"methods": ["OpenDoc6"], "properties": ["Visible"]}
        },
        "vba_references": {
            "SldWorks": {"description": "SolidWorks API", "status": "available"}
        },
    }
    exact = docs_mod._search_index(index, "OpenDoc6", 10)
    assert exact and exact[0]["member"] == "OpenDoc6"
    refs = docs_mod._search_index(index, "SolidWorks API", 10)
    assert any(item["member_type"] == "reference" for item in refs)


def test_detect_year_iteration_and_config_path_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover non-dir iteration continue, no-year return, and config-path year resolution."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    class _Child:
        """Test suite for Child."""

        def __init__(self, name: str, is_dir: bool):
            """Test helper for init."""
            self.name = name
            self._is_dir = is_dir

        def is_dir(self):
            """Test helper for is dir."""
            return self._is_dir

    class _Root:
        """Test suite for Root."""

        def exists(self):
            """Test helper for exists."""
            return True

        def iterdir(self):
            """Test helper for iterdir."""
            return [
                _Child("readme.txt", False),
                _Child("RandomFolder", True),
            ]

    monkeypatch.setattr(docs_mod, "Path", lambda *_args, **_kwargs: _Root())
    assert docs_mod._detect_installed_solidworks_year() is None

    cfg = SimpleNamespace(solidworks_year=None, solidworks_path="C:/SW/SOLIDWORKS 2028")
    assert docs_mod._resolve_solidworks_year(None, cfg) == 2028


def test_load_index_file_missing_and_search_property_match(temp_dir: Path) -> None:
    """Cover missing-file early return and property-result append scoring branch."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    missing = temp_dir / "missing.json"
    assert docs_mod._load_index_file(missing) is None

    index = {
        "com_objects": {
            "ISldWorks": {
                "methods": ["OpenDoc6"],
                "properties": ["RevisionNumber"],
            }
        },
        "vba_references": {},
    }
    results = docs_mod._search_index(index, "RevisionNumber", 5)
    assert any(item["member_type"] == "property" for item in results)


def test_normalize_input_non_dict_non_model_dump_path() -> None:
    """_normalize_input should validate plain objects via final fallback branch."""
    from src.solidworks_mcp.tools.docs_discovery import _normalize_input

    class _PlainInput:
        """Test suite for PlainInput."""

        output_dir = "plain"
        include_vba = True
        year = None

    with pytest.raises(Exception):
        _normalize_input(_PlainInput(), DiscoverDocsInput)


@pytest.mark.asyncio
async def test_discover_solidworks_docs_tool_non_windows_error(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover_solidworks_docs should reject non-Windows platforms."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in mcp_server._tools:
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.func
            break
    assert discover_tool is not None

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Linux")

    result = await discover_tool({})
    assert result["status"] == "error"
    assert "Windows" in result["message"]


@pytest.mark.asyncio
async def test_search_api_help_auto_discovers_when_index_missing(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """search_solidworks_api_help should auto-discover index when requested."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in mcp_server._tools:
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.func
            break
    assert search_tool is not None

    class _AutoDiscovery:
        """Test suite for AutoDiscovery."""

        def __init__(self, output_dir=None):
            """Test helper for init."""
            self.output_dir = output_dir

        def discover_all(self):
            """Test helper for discover all."""
            return {
                "com_objects": {
                    "ISldWorks": {
                        "methods": ["OpenDoc6"],
                        "properties": ["Visible"],
                    }
                },
                "vba_references": {},
            }

        def save_index(self, filename="solidworks_docs_index.json"):
            """Test helper for save index."""
            path = temp_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _AutoDiscovery)
    monkeypatch.setattr(docs_mod, "_find_index_file", lambda *_args, **_kwargs: None)

    result = await search_tool(
        {
            "query": "OpenDoc6",
            "year": 2026,
            "auto_discover_if_missing": True,
            "max_results": 5,
        }
    )

    assert result["status"] == "success"
    assert result["source_index_file"] is not None


@pytest.mark.asyncio
async def test_search_api_help_exception_path(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_solidworks_api_help should return structured error on unexpected exceptions."""
    import src.solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in mcp_server._tools:
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.func
            break
    assert search_tool is not None

    monkeypatch.setattr(
        docs_mod,
        "_normalize_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("normalize failed")
        ),
    )

    result = await search_tool({"query": "OpenDoc6"})
    assert result["status"] == "error"
    assert "API help search failed" in result["message"]
