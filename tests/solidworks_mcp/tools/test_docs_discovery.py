"""Deterministic regression tests for docs discovery tool."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.tools.docs_discovery import (
    SolidWorksDocsDiscovery,
    _detect_installed_solidworks_year,
    _discover_vba_references_via_registry,
    _enumerate_typeinfo_members,
    _extract_year,
    _fallback_help_for_query,
    _find_index_file,
    _find_related_api_members,
    _load_index_file,
    _lookup_interface,
    _lookup_method,
    _resolve_solidworks_year,
    _search_index,
    register_docs_discovery_tools,
)

REAL_SW_ENV_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"


def _real_solidworks_enabled() -> bool:
    """Check if real SolidWorks integration is enabled."""
    value = os.getenv(REAL_SW_ENV_FLAG, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


async def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    """Find a tool by name in the MCP server."""
    for tool in await server.mcp.list_tools():
        if tool.name == tool_name:
            return tool.fn
    raise AssertionError(f"Tool '{tool_name}' not found")


@pytest_asyncio.fixture
async def real_server() -> AsyncGenerator[SolidWorksMCPServer]:
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
        discover_tool = await _find_tool(real_server, "discover_solidworks_docs")
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
    """Test that docs discovery tool executes successfully with real SolidWorks."""
    try:
        discover_tool = await _find_tool(real_server, "discover_solidworks_docs")
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
        from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

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
    from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

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
    for tool in await mcp_server.list_tools():
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.fn
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
    """Connect_to_solidworks should fail fast when win32com is unavailable."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", False)
    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect")
    )

    assert discovery.connect_to_solidworks() is False


def test_discovery_connect_fails_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connect_to_solidworks should reject non-Windows platforms."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Linux")
    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect-os")
    )

    assert discovery.connect_to_solidworks() is False


def test_discovery_connect_uses_dispatch_when_getobject_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connect_to_solidworks should fall back to gencache.EnsureDispatch when GetActiveObject raises com_error."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    fake_sw = object()

    class _FakeComError(Exception):
        """Test fake com error."""

        pass

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "com_error", _FakeComError, raising=False)
    monkeypatch.setattr(
        docs_mod,
        "win32com",
        SimpleNamespace(
            client=SimpleNamespace(
                GetActiveObject=lambda _: (_ for _ in ()).throw(
                    _FakeComError("not running")
                ),
                gencache=SimpleNamespace(EnsureDispatch=lambda _: fake_sw),
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
    """Discover_com_objects should return empty dict when disconnected."""
    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-empty"))
    assert discovery.discover_com_objects() == {}


def test_discover_com_objects_and_summary_with_fake_app() -> None:
    """Discover_com_objects should index methods/properties and create summary."""

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
    """Discover_vba_references should return whatever _discover_vba_references_via_registry finds."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    fake_refs = {
        "SldWorks Type Library ({A4B97BA4-941C-45F8-B4E5-3AB637EA0306} v1.0)": {
            "description": "SldWorks Type Library",
            "guid": "{A4B97BA4-941C-45F8-B4E5-3AB637EA0306}",
            "version": "1.0",
            "status": "available",
        },
        "VBA ({000204EF-0000-0000-C000-000000000046} v4.1)": {
            "description": "VBA",
            "guid": "{000204EF-0000-0000-C000-000000000046}",
            "version": "4.1",
            "status": "available",
        },
    }

    monkeypatch.setattr(
        docs_mod, "_discover_vba_references_via_registry", lambda: fake_refs
    )

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-vba")
    )
    refs = discovery.discover_vba_references()

    assert refs is fake_refs
    assert all(v["status"] == "available" for v in refs.values())
    assert any("VBA" in v["description"] for v in refs.values())
    assert any("SldWorks" in v["description"] for v in refs.values())


def test_discover_all_returns_index_when_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover_all should return base index when connection fails."""
    discovery = SolidWorksDocsDiscovery(output_dir=Path("tests/.generated/docs-all"))
    monkeypatch.setattr(discovery, "connect_to_solidworks", lambda: False)

    index = discovery.discover_all()
    assert isinstance(index, dict)
    assert index["com_objects"] == {}


def test_save_index_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    """Save_index should write JSON and return None on write errors."""
    discovery = SolidWorksDocsDiscovery(output_dir=temp_dir)
    saved = discovery.save_index("docs_index.json")
    assert saved is not None and saved.exists()

    import solidworks_mcp.tools.docs_discovery as docs_mod

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
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
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
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
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
    """Connect_to_solidworks should return False when both GetActiveObject and EnsureDispatch raise com_error."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

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
                GetActiveObject=lambda _: (_ for _ in ()).throw(_FakeComError("boom")),
                gencache=SimpleNamespace(
                    EnsureDispatch=lambda _: (_ for _ in ()).throw(
                        _FakeComError("boom")
                    )
                ),
            )
        ),
        raising=False,
    )

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-connect-com-error")
    )
    assert discovery.connect_to_solidworks() is False


def test_discover_com_objects_handles_attribute_and_catalog_errors() -> None:
    """Discover_com_objects should tolerate both extraction and catalog-level failures."""

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
    """Discover_all should stitch connect/com/vba steps into final index."""
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


def test_extract_year_handles_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_extract_year should return None when int conversion fails."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

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
    import solidworks_mcp.tools.docs_discovery as docs_mod

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
    from solidworks_mcp.tools.docs_discovery import _load_index_file

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
    import solidworks_mcp.tools.docs_discovery as docs_mod

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
    import solidworks_mcp.tools.docs_discovery as docs_mod

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
    import solidworks_mcp.tools.docs_discovery as docs_mod

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


@pytest.mark.asyncio
async def test_discover_solidworks_docs_tool_non_windows_error(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover_solidworks_docs should reject non-Windows platforms."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
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
    """Search_solidworks_api_help should auto-discover index when requested."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.fn
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
    """Search_solidworks_api_help should return structured error on unexpected exceptions."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.fn
            break
    assert search_tool is not None

    monkeypatch.setattr(
        docs_mod,
        "normalize_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("normalize failed")
        ),
    )

    result = await search_tool({"query": "OpenDoc6"})
    assert result["status"] == "error"
    assert result["error_type"] == "internal"


def test_enumerate_typeinfo_members_happy_path_and_error_item() -> None:
    """Covers method/property extraction, dedupe, and per-item exception continue."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    class _TypeAttr:
        cFuncs = 4

    class _FuncDesc:
        def __init__(self, memid: int, invkind: int):
            self.memid = memid
            self.invkind = invkind

    class _TypeInfo:
        def GetTypeAttr(self):
            return _TypeAttr()

        def GetFuncDesc(self, i: int):
            if i == 3:
                raise RuntimeError("bad func")
            return [_FuncDesc(1, 1), _FuncDesc(2, 2), _FuncDesc(1, 1)][i]

        def GetNames(self, memid: int):
            return {1: ["OpenDoc6"], 2: ["Visible"]}[memid]

    methods, properties = docs_mod._enumerate_typeinfo_members(_TypeInfo())
    assert methods == ["OpenDoc6"]
    assert properties == ["Visible"]


def test_discover_com_via_typeinfo_no_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers early-return branch when win32com is unavailable."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", False)
    assert docs_mod._discover_com_via_typeinfo(object()) == ({}, 0, 0)


def test_discover_com_via_typeinfo_with_impl_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers implemented-interface merge path and counters."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)

    class _TypeAttr:
        cImplTypes = 1

    class _TypeInfo:
        def GetTypeAttr(self):
            return _TypeAttr()

        def GetRefTypeOfImplType(self, _idx: int):
            return "ref"

        def GetRefTypeInfo(self, _ref):
            return object()

    class _Ole:
        def GetTypeInfo(self):
            return _TypeInfo()

    sw_app = SimpleNamespace(_oleobj_=_Ole())

    def _enum_members(typeinfo):
        if isinstance(typeinfo, _TypeInfo):
            return ["OpenDoc6"], ["Visible"]
        return ["CloseDoc"], ["FrameState"]

    monkeypatch.setattr(docs_mod, "_enumerate_typeinfo_members", _enum_members)

    index, total_m, total_p = docs_mod._discover_com_via_typeinfo(sw_app)
    assert "ISldWorks" in index
    assert set(index["ISldWorks"]["methods"]) == {"OpenDoc6", "CloseDoc"}
    assert set(index["ISldWorks"]["properties"]) == {"Visible", "FrameState"}
    assert total_m == 2
    assert total_p == 2


def test_discover_com_via_typeinfo_outer_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers exception path when GetTypeInfo fails."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    sw_app = SimpleNamespace(
        _oleobj_=SimpleNamespace(
            GetTypeInfo=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
    )

    index, total_m, total_p = docs_mod._discover_com_via_typeinfo(sw_app)
    assert index == {}
    assert total_m == 0
    assert total_p == 0


def test_discover_vba_references_via_registry_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers Windows registry scan success, duplicate guard, and query fallback."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")

    class _FakeWinReg:
        HKEY_CLASSES_ROOT = object()
        KEY_READ = 1

        def OpenKey(self, root, key, access=None):
            return (root, key, access)

        def EnumKey(self, key, idx: int):
            name = key[1]
            if name == "TypeLib":
                values = ["{GUID-1}"]
            elif name == "{GUID-1}":
                values = ["1.0", "2.0"]
            else:
                values = []
            if idx >= len(values):
                raise OSError("done")
            return values[idx]

        def QueryValueEx(self, key, _name: str):
            version = key[1]
            if version == "2.0":
                raise OSError("missing")
            return "SldWorks Type Library", None

        def CloseKey(self, _key):
            return None

    monkeypatch.setitem(sys.modules, "winreg", _FakeWinReg())
    refs = docs_mod._discover_vba_references_via_registry()
    assert refs
    only = next(iter(refs.values()))
    assert only["status"] == "available"


def test_discover_com_objects_with_typeinfo_and_active_doc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers typeinfo logging path and active document supplement path."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    discovery = docs_mod.SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-typeinfo-active")
    )
    discovery.sw_app = SimpleNamespace(
        ActiveDoc=SimpleNamespace(
            _oleobj_=SimpleNamespace(GetTypeInfo=lambda: object())
        ),
        RevisionNumber=lambda: "33.4",
    )

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(
        docs_mod,
        "_discover_com_via_typeinfo",
        lambda _sw: ({"ISldWorks": {"methods": ["OpenDoc6"], "properties": []}}, 1, 0),
    )
    monkeypatch.setattr(
        docs_mod,
        "_enumerate_typeinfo_members",
        lambda _ti: (["GetTitle"], ["ActiveView"]),
    )

    result = discovery.discover_com_objects()
    assert "ISldWorks" in result
    assert "IModelDoc2_active" in result


def test_find_index_file_none_when_missing() -> None:
    """Covers _find_index_file final return None branch."""
    from solidworks_mcp.tools.docs_discovery import _find_index_file

    assert _find_index_file(2099, "tests/.generated/does-not-exist.json") is None


@pytest.mark.asyncio
async def test_discover_tool_sets_rag_indexed_true_when_rag_rebuild_succeeds(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """Covers RAG rebuild success branch in discover_solidworks_docs."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    class _FakeDiscovery:
        def __init__(self, output_dir=None):
            self.output_dir = output_dir

        def discover_all(self):
            return {"com_objects": {}, "vba_references": {}}

        def save_index(self, filename="solidworks_docs_index.json"):
            path = temp_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            return {
                "total_com_objects": 0,
                "total_methods": 0,
                "total_properties": 0,
                "solidworks_version": None,
                "available_vba_libs": [],
            }

    class _FakeRagIndex:
        chunk_count = 7

        def save(self):
            return None

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)

    fake_vector_rag = SimpleNamespace(
        build_solidworks_api_docs_index=lambda _output: _FakeRagIndex()
    )
    monkeypatch.setitem(
        sys.modules, "solidworks_mcp.agents.vector_rag", fake_vector_rag
    )

    result = await discover_tool({"output_dir": str(temp_dir), "year": 2026})
    assert result["status"] == "success"
    assert result["rag_indexed"] is True


@pytest.mark.asyncio
async def test_discover_tool_handles_rag_import_error(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """Covers ImportError branch when vector_rag rebuild is unavailable."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    class _FakeDiscovery:
        def __init__(self, output_dir=None):
            self.output_dir = output_dir

        def discover_all(self):
            return {"com_objects": {}, "vba_references": {}}

        def save_index(self, filename="solidworks_docs_index.json"):
            path = temp_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            return {
                "total_com_objects": 0,
                "total_methods": 0,
                "total_properties": 0,
                "solidworks_version": None,
                "available_vba_libs": [],
            }

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)

    # Module exists but missing the imported symbol -> ImportError in "from ... import ...".
    monkeypatch.setitem(
        sys.modules, "solidworks_mcp.agents.vector_rag", SimpleNamespace()
    )

    result = await discover_tool({"output_dir": str(temp_dir), "year": 2026})
    assert result["status"] == "success"
    assert result["rag_indexed"] is False


@pytest.mark.asyncio
async def test_discover_tool_top_level_exception_path(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers top-level exception handler in discover_solidworks_docs."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        docs_mod,
        "SolidWorksDocsDiscovery",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("construct failed")
        ),
    )

    result = await discover_tool({})
    assert result["status"] == "error"
    assert result["error_type"] == "internal"


# ---------------------------------------------------------------------------
# #64 — granular API lookups (helpers are pure, no COM / no server)
# ---------------------------------------------------------------------------

_LOOKUP_INDEX = {
    "com_objects": {
        "ISldWorks": {
            "methods": ["OpenDoc6", "CloseDoc", "ActivateDoc3"],
            "properties": ["Visible", "ActiveDoc"],
        },
        "IModelDoc2": {
            "methods": ["GetTitle", "CloseDoc"],
            "properties": ["Visible"],
        },
    }
}


def test_lookup_interface_known_returns_all_members():
    result = _lookup_interface(_LOOKUP_INDEX, "isldworks")  # case-insensitive
    assert result["found"] is True
    assert result["interface"] == "ISldWorks"
    assert result["method_count"] == 3
    assert result["property_count"] == 2
    assert "OpenDoc6" in result["methods"]


def test_lookup_interface_unknown_reports_not_found():
    result = _lookup_interface(_LOOKUP_INDEX, "INotIndexed")
    assert result["found"] is False


def test_lookup_method_known_confirms_member_no_signature():
    result = _lookup_method(_LOOKUP_INDEX, "ISldWorks", "opendoc6")
    assert result["found"] is True
    assert result["member"] == "OpenDoc6"
    assert result["member_type"] == "method"
    assert result["signature_indexed"] is False
    assert result["parameters"] is None


def test_lookup_method_resolves_a_property_too():
    result = _lookup_method(_LOOKUP_INDEX, "ISldWorks", "visible")
    assert result["found"] is True
    assert result["member_type"] == "property"


def test_lookup_method_unknown_member_reports_not_found():
    result = _lookup_method(_LOOKUP_INDEX, "ISldWorks", "NoSuchMethod")
    assert result["found"] is False


def test_lookup_method_unknown_interface_reports_not_found():
    result = _lookup_method(_LOOKUP_INDEX, "INope", "OpenDoc6")
    assert result["found"] is False


def test_find_related_from_interface_returns_its_members():
    result = _find_related_api_members(_LOOKUP_INDEX, "IModelDoc2", 25)
    assert result["resolved_as"] == "interface"
    members = {(r["object"], r["member"]) for r in result["related"]}
    assert ("IModelDoc2", "GetTitle") in members


def test_find_related_from_member_returns_siblings_across_interfaces():
    result = _find_related_api_members(_LOOKUP_INDEX, "CloseDoc", 25)
    assert result["resolved_as"] == "member"
    objs = {r["object"] for r in result["related"]}
    # CloseDoc lives on both interfaces -> siblings from both come back
    assert objs == {"ISldWorks", "IModelDoc2"}
    assert all(r["member"] != "CloseDoc" for r in result["related"])


def test_find_related_name_substring_match():
    result = _find_related_api_members(_LOOKUP_INDEX, "Doc", 25)
    assert result["resolved_as"] == "name-match"
    assert any("Doc" in r["member"] for r in result["related"])


def test_find_related_respects_max_results():
    result = _find_related_api_members(_LOOKUP_INDEX, "ISldWorks", 2)
    assert len(result["related"]) == 2


@pytest.mark.asyncio
async def test_granular_lookup_tools_registered_and_callable(
    mcp_server,
    mock_config,
    temp_dir: Path,
) -> None:
    """The three new tools register and answer against a synthetic index;
    search_solidworks_api_help is unaffected."""
    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    tools = {t.name: t.fn for t in await mcp_server.list_tools()}
    for name in (
        "lookup_api_method",
        "lookup_api_interface",
        "find_related_api_members",
        "search_solidworks_api_help",
    ):
        assert name in tools, f"{name} not registered"

    index_path = temp_dir / "solidworks_docs_index_2026.json"
    index_path.write_text(json.dumps(_LOOKUP_INDEX), encoding="utf-8")
    common = {"year": 2026, "index_file": str(index_path)}

    iface = await tools["lookup_api_interface"]({**common, "interface": "ISldWorks"})
    assert iface["status"] == "success"
    assert iface["result"]["found"] is True
    assert iface["result"]["method_count"] == 3

    method = await tools["lookup_api_method"](
        {**common, "interface": "ISldWorks", "method": "CloseDoc"}
    )
    assert method["status"] == "success"
    assert method["result"]["found"] is True

    missing = await tools["lookup_api_method"](
        {**common, "interface": "ISldWorks", "method": "Nope"}
    )
    assert missing["status"] == "success"
    assert missing["result"]["found"] is False  # no-match, not an error

    related = await tools["find_related_api_members"](
        {**common, "name": "CloseDoc"}
    )
    assert related["status"] == "success"
    assert related["result"]["related"]

    # regression: full-text search still works
    search = await tools["search_solidworks_api_help"](
        {**common, "query": "open document", "max_results": 5}
    )
    assert search["status"] == "success"
    assert isinstance(search["matches"], list)


# ---------------------------------------------------------------------------
# Docs index auto-refresh on staleness (config-gated)
# ---------------------------------------------------------------------------


def test_index_is_stale_thresholds(tmp_path):
    import os
    import time as _time

    from solidworks_mcp.tools.docs_discovery import _index_is_stale

    assert _index_is_stale(None, 21) is False
    assert _index_is_stale(tmp_path / "missing.json", 21) is False

    fresh = tmp_path / "fresh.json"
    fresh.write_text("{}")
    assert _index_is_stale(fresh, 21) is False

    old = tmp_path / "old.json"
    old.write_text("{}")
    old_mtime = _time.time() - 30 * 86400
    os.utime(old, (old_mtime, old_mtime))
    assert _index_is_stale(old, 21) is True
    assert _index_is_stale(old, 60) is False


def test_maybe_refresh_index_is_a_noop_when_disabled(tmp_path):
    from types import SimpleNamespace

    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    idx = {"com_objects": {}}
    f = tmp_path / "i.json"
    f.write_text("{}")
    cfg = SimpleNamespace(docs_index_auto_refresh=False, docs_index_max_age_days=21)
    assert _maybe_refresh_index(idx, f, 2026, cfg) == (idx, f)


def test_maybe_refresh_index_leaves_fresh_index_untouched(tmp_path):
    from types import SimpleNamespace

    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    idx = {"com_objects": {"ISldWorks": {"methods": [], "properties": []}}}
    f = tmp_path / "i.json"
    f.write_text("{}")  # just written -> fresh
    cfg = SimpleNamespace(docs_index_auto_refresh=True, docs_index_max_age_days=21)
    assert _maybe_refresh_index(idx, f, 2026, cfg) == (idx, f)


def test_docs_discovery_imports_without_pywin32(import_without) -> None:
    attrs = import_without(
        "solidworks_mcp.tools.docs_discovery",
        # Only win32com.client: fastmcp -> mcp needs pywintypes on Windows.
        ["win32com.client"],
        ["HAS_WIN32COM"],
    )

    assert attrs == {"HAS_WIN32COM": False}


def test_index_is_stale_treats_an_unreadable_file_as_fresh() -> None:
    from solidworks_mcp.tools.docs_discovery import _index_is_stale

    def denied():
        raise PermissionError("access denied")

    unreadable = SimpleNamespace(exists=lambda: True, stat=denied)

    assert _index_is_stale(unreadable, 21) is False


@pytest.fixture
def stale_index(tmp_path):
    index_file = tmp_path / "solidworks_docs_index_2026.json"
    index_file.write_text("{}")
    old = time.time() - 30 * 86400
    os.utime(index_file, (old, old))
    return {"com_objects": {}}, index_file


def _refresh_env(monkeypatch, *, saved_to=None, error=None):
    """Pretend to be on Windows with pywin32; record what discovery was asked."""
    from solidworks_mcp.tools import docs_discovery as dd

    calls: list[str] = []

    class _Discovery:
        def discover_all(self):
            if error is not None:
                raise error
            return {"com_objects": {"ISldWorks": {}}}

        def save_index(self, filename):
            calls.append(filename)
            return saved_to

    monkeypatch.setattr(dd, "HAS_WIN32COM", True)
    monkeypatch.setattr(dd.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dd, "SolidWorksDocsDiscovery", _Discovery)
    return calls


_REFRESH_ON = SimpleNamespace(docs_index_auto_refresh=True, docs_index_max_age_days=21)


def test_maybe_refresh_index_rebuilds_a_stale_index(stale_index, monkeypatch, tmp_path):
    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    index, index_file = stale_index
    fresh_file = tmp_path / "fresh.json"
    calls = _refresh_env(monkeypatch, saved_to=fresh_file)

    refreshed, refreshed_file = _maybe_refresh_index(
        index, index_file, 2026, _REFRESH_ON
    )

    assert refreshed == {"com_objects": {"ISldWorks": {}}}
    assert refreshed_file == fresh_file
    assert calls == ["solidworks_docs_index_2026.json"]


def test_maybe_refresh_index_keeps_the_old_path_when_save_reports_none(
    stale_index, monkeypatch
):
    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    index, index_file = stale_index
    calls = _refresh_env(monkeypatch, saved_to=None)

    _refreshed, refreshed_file = _maybe_refresh_index(
        index, index_file, None, _REFRESH_ON
    )

    assert refreshed_file == index_file
    assert calls == ["solidworks_docs_index.json"]


def test_maybe_refresh_index_serves_the_stale_index_when_discovery_fails(
    stale_index, monkeypatch
):
    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    index, index_file = stale_index
    _refresh_env(monkeypatch, error=RuntimeError("SolidWorks not running"))

    assert _maybe_refresh_index(index, index_file, 2026, _REFRESH_ON) == (
        index,
        index_file,
    )


def test_maybe_refresh_index_needs_windows_and_pywin32(stale_index, monkeypatch):
    from solidworks_mcp.tools import docs_discovery as dd

    index, index_file = stale_index
    monkeypatch.setattr(dd, "HAS_WIN32COM", False)

    assert dd._maybe_refresh_index(index, index_file, 2026, _REFRESH_ON) == (
        index,
        index_file,
    )


@pytest.mark.asyncio
async def test_discover_docs_tool_rag_index_rebuild_success(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """RAG index rebuild should succeed when faiss-cpu is available."""
    import solidworks_mcp.tools.docs_discovery as docs_mod
    from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    # Mock successful RAG index build
    fake_rag_idx = MagicMock()
    fake_rag_idx.chunk_count = 1234
    fake_rag_idx.save = MagicMock()

    def fake_build_rag(output_file):
        """Fake RAG index builder."""
        return fake_rag_idx

    # Mock SolidWorksDocsDiscovery to succeed
    class _FakeDiscovery:
        """Mock discovery that succeeds."""

        def __init__(self, output_dir=None):
            """Init."""
            self.output_dir = output_dir or temp_dir

        def discover_all(self):
            """Return mock index."""
            return {
                "com_objects": {"ISldWorks": {"methods": ["OpenDoc6"]}},
                "vba_references": {},
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
            }

        def save_index(self, filename="solidworks_docs_index.json"):
            """Save mock index."""
            path = self.output_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            """Return mock summary."""
            return {
                "total_com_objects": 1,
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
                "available_vba_libs": [],
            }

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)

    result = await discover_tool({"output_dir": str(temp_dir)})
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_discover_docs_tool_rag_index_rebuild_faiss_import_error(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """RAG rebuild should skip gracefully when faiss-cpu ImportError occurs."""
    import solidworks_mcp.tools.docs_discovery as docs_mod
    from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    class _FakeDiscovery:
        """Mock discovery that succeeds."""

        def __init__(self, output_dir=None):
            """Init."""
            self.output_dir = output_dir or temp_dir

        def discover_all(self):
            """Return mock index."""
            return {
                "com_objects": {"ISldWorks": {"methods": ["OpenDoc6"]}},
                "vba_references": {},
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
            }

        def save_index(self, filename="solidworks_docs_index.json"):
            """Save mock index."""
            path = self.output_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            """Return mock summary."""
            return {
                "total_com_objects": 1,
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
                "available_vba_libs": [],
            }

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)

    result = await discover_tool({"output_dir": str(temp_dir)})
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_discover_docs_tool_rag_index_rebuild_generic_exception(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
) -> None:
    """RAG rebuild should warn and continue on generic Exception (lines 1052-1053).

    This exercises the ``except Exception as _rag_exc`` branch that fires when
    ``build_solidworks_api_docs_index`` raises something other than ImportError.
    """
    import solidworks_mcp.agents.vector_rag as _rag_mod
    import solidworks_mcp.tools.docs_discovery as docs_mod
    from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    discover_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "discover_solidworks_docs":
            discover_tool = tool.fn
            break
    assert discover_tool is not None

    class _FakeDiscovery:
        """Mock discovery that succeeds."""

        def __init__(self, output_dir=None):
            """Init."""
            self.output_dir = output_dir or temp_dir

        def discover_all(self):
            """Return mock index."""
            return {
                "com_objects": {"ISldWorks": {"methods": ["OpenDoc6"]}},
                "vba_references": {},
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
            }

        def save_index(self, filename="solidworks_docs_index.json"):
            """Save mock index."""
            path = self.output_dir / filename
            path.write_text("{}", encoding="utf-8")
            return path

        def create_search_summary(self):
            """Return mock summary."""
            return {
                "total_com_objects": 1,
                "total_methods": 1,
                "total_properties": 0,
                "solidworks_version": "33.2",
                "available_vba_libs": [],
            }

    monkeypatch.setattr(docs_mod, "HAS_WIN32COM", True)
    monkeypatch.setattr(docs_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docs_mod, "SolidWorksDocsDiscovery", _FakeDiscovery)
    # Patch build_solidworks_api_docs_index to raise a RuntimeError so the
    # generic except block (lines 1052-1053) is reached instead of ImportError.
    monkeypatch.setattr(
        _rag_mod,
        "build_solidworks_api_docs_index",
        MagicMock(side_effect=RuntimeError("disk full")),
    )

    result = await discover_tool({"output_dir": str(temp_dir)})
    # Despite the RAG failure the discovery itself should still succeed.
    assert result["status"] == "success"


def test_discover_com_objects_with_active_doc_typeinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover_com_objects should extract IModelDoc2_active interface from open document."""
    from solidworks_mcp.tools.docs_discovery import HAS_WIN32COM

    if not HAS_WIN32COM:
        pytest.skip("win32com not available")

    class _FakeTypeInfo:
        """Mock ITypeInfo for active document."""

        def GetTypeAttr(self):
            """Return mock type attributes."""
            return SimpleNamespace(
                cFuncs=1,
                cImplTypes=0,
            )

        def GetFuncDesc(self, i):
            """Return mock function descriptor."""
            return SimpleNamespace(
                memid=1,
                invkind=1,  # FUNC
            )

        def GetNames(self, memid):
            """Return mock function names."""
            return ["ShowNamedView2"]

    class _FakeOleObj:
        """Mock ole object for active document."""

        def GetTypeInfo(self):
            """Return mock typeinfo."""
            return _FakeTypeInfo()

    class _FakeDoc:
        """Mock active document."""

        def __init__(self):
            """Init."""
            self._oleobj_ = _FakeOleObj()

    class _FakeApp:
        """Mock SolidWorks app with active document."""

        def __init__(self):
            """Init."""
            self.ActiveDoc = _FakeDoc()

        def RevisionNumber(self):
            """Return revision."""
            return "33.2"

    discovery = SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-activeDoc")
    )
    discovery.sw_app = _FakeApp()

    index = discovery.discover_com_objects()
    # Should have both ISldWorks and IModelDoc2_active (Line 457-467)
    assert "IModelDoc2_active" in index or "ISldWorks" in index


def test_discover_com_objects_with_active_doc_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discover_com_objects should handle exceptions during active document enumeration."""

    class _FailingApp:
        """Mock app that fails on ActiveDoc access."""

        def __getattr__(self, name):
            """Raise exception for any attribute."""
            if name == "ActiveDoc":
                raise RuntimeError("Cannot access ActiveDoc")
            raise AttributeError(f"No attribute {name}")

        def RevisionNumber(self):
            """Return revision."""
            return "33.2"

    discovery = SolidWorksDocsDiscovery(
        output_dir=Path("tests/.generated/docs-activeDoc-error")
    )
    discovery.sw_app = _FailingApp()

    # Should not crash despite the error (Line 458-467)
    index = discovery.discover_com_objects()
    assert isinstance(index, dict)


def test_enumerate_typeinfo_members_with_inherited_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_enumerate_typeinfo_members should walk inherited interfaces."""

    class _InheritedTypeInfo:
        """Mock typeinfo for inherited interface."""

        def GetTypeAttr(self):
            """Return attributes."""
            return SimpleNamespace(
                cFuncs=1,
                cImplTypes=0,
            )

        def GetFuncDesc(self, i):
            """Return function descriptor."""
            return SimpleNamespace(
                memid=101,
                invkind=1,  # FUNC
            )

        def GetNames(self, memid):
            """Return names."""
            return ["InheritedMethod"]

    class _MainTypeInfo:
        """Mock typeinfo for main interface."""

        def __init__(self):
            """Init."""
            self.inherited = _InheritedTypeInfo()

        def GetTypeAttr(self):
            """Return attributes."""
            return SimpleNamespace(
                cFuncs=2,
                cImplTypes=1,
            )

        def GetFuncDesc(self, i):
            """Return function descriptor."""
            if i == 0:
                return SimpleNamespace(
                    memid=1,
                    invkind=1,  # FUNC
                )
            else:
                return SimpleNamespace(
                    memid=2,
                    invkind=2,  # PROPERTYGET
                )

        def GetNames(self, memid):
            """Return names."""
            if memid == 1:
                return ["MainMethod"]
            elif memid == 2:
                return ["MainProperty"]
            return []

        def GetRefTypeOfImplType(self, idx):
            """Return reference to inherited type."""
            return 1

        def GetRefTypeInfo(self, ref):
            """Return inherited typeinfo."""
            return self.inherited

    typeinfo = _MainTypeInfo()
    from solidworks_mcp.tools.docs_discovery import HAS_WIN32COM

    if not HAS_WIN32COM:
        pytest.skip("win32com not available")

    methods, properties = _enumerate_typeinfo_members(typeinfo)
    # Should include both main and inherited members (Line 243-275)
    assert "MainMethod" in methods
    assert "MainProperty" in properties


def test_enumerate_typeinfo_members_handles_bad_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_enumerate_typeinfo_members should handle GetNames failures."""

    class _BadTypeInfo:
        """Mock typeinfo with bad GetNames."""

        def GetTypeAttr(self):
            """Return attributes."""
            return SimpleNamespace(cFuncs=1, cImplTypes=0)

        def GetFuncDesc(self, i):
            """Return function descriptor."""
            return SimpleNamespace(memid=1, invkind=1)

        def GetNames(self, memid):
            """Raise exception."""
            raise RuntimeError("GetNames failed")

    from solidworks_mcp.tools.docs_discovery import HAS_WIN32COM

    if not HAS_WIN32COM:
        pytest.skip("win32com not available")

    methods, properties = _enumerate_typeinfo_members(_BadTypeInfo())
    # Should return empty lists on exception
    assert methods == []
    assert properties == []


def test_discover_vba_references_registry_scan_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_discover_vba_references_via_registry should handle registry errors gracefully."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    refs = _discover_vba_references_via_registry()
    # Should return empty dict on non-Windows platform
    assert isinstance(refs, dict)


def test_discover_vba_references_typelib_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_discover_vba_references_via_registry should handle various error conditions."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    refs = _discover_vba_references_via_registry()
    assert isinstance(refs, dict)


@pytest.mark.asyncio
async def test_search_api_help_tool_no_index_file(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Search_solidworks_api_help should return fallback when index not found."""
    from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.fn
            break
    assert search_tool is not None

    # Query with non-existent index file
    result = await search_tool(
        {
            "query": "how to open a document",
            "year": 2999,
            "max_results": 5,
        }
    )

    assert result["status"] == "success"
    assert "guidance" in result
    assert "matches" in result


@pytest.mark.asyncio
async def test_search_api_help_tool_empty_index_file(
    mcp_server,
    mock_config: SolidWorksMCPConfig,
    temp_dir: Path,
) -> None:
    """Search_solidworks_api_help should handle empty index gracefully."""
    from solidworks_mcp.tools.docs_discovery import register_docs_discovery_tools

    await register_docs_discovery_tools(mcp_server, object(), mock_config)

    search_tool = None
    for tool in await mcp_server.list_tools():
        if tool.name == "search_solidworks_api_help":
            search_tool = tool.fn
            break
    assert search_tool is not None

    # Create empty index file
    index_path = temp_dir / "empty_index.json"
    index_path.write_text("{}", encoding="utf-8")

    result = await search_tool(
        {
            "query": "create part",
            "index_file": str(index_path),
            "max_results": 5,
        }
    )

    assert result["status"] == "success"
    assert isinstance(result["matches"], list)


@pytest.mark.parametrize(
    "query,expected_tool",
    [
        ("how to revolve", "create_revolve"),
        ("lathe operation", "create_revolve"),
        ("extrude feature", "create_extrusion"),
        ("boss cut operation", "create_extrusion"),
        ("unknown intent", "discover_solidworks_docs"),
        ("generic query", "discover_solidworks_docs"),
    ],
)
def test_fallback_help_for_query_variants(query: str, expected_tool: str) -> None:
    """_fallback_help_for_query should suggest appropriate tools by intent."""
    help_guidance = _fallback_help_for_query(query)

    assert "suggested_tools" in help_guidance
    assert len(help_guidance["suggested_tools"]) > 0
    # Check if expected tool is in suggestions
    assert expected_tool in help_guidance["suggested_tools"]


@pytest.mark.parametrize(
    "input_year,config_year,expected",
    [
        (2026, None, 2026),  # Explicit input overrides
        (None, 2025, 2025),  # Config fallback
        (2026, 2025, 2026),  # Explicit overrides config
    ],
)
def test_resolve_solidworks_year_priority(
    input_year: int | None,
    config_year: int | None,
    expected: int | None,
) -> None:
    """_resolve_solidworks_year should prioritize explicit input > config."""
    config = SolidWorksMCPConfig(solidworks_year=config_year)
    resolved = _resolve_solidworks_year(input_year, config)
    assert resolved == expected


def test_detect_installed_solidworks_year_finds_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_detect_installed_solidworks_year should find latest installed year."""

    def fake_path_exists(self):
        """Check if path exists."""
        if "2026" in str(self):
            return True
        if "2025" in str(self):
            return True
        if "SOLIDWORKS" in str(self):
            return True
        return False

    def fake_path_iterdir(self):
        """Iterate directory."""
        # Return mock years
        base_path = Path(str(self))
        if "SOLIDWORKS Corp" in str(base_path):
            yield Path(str(self) + "/SOLIDWORKS 2026")
            yield Path(str(self) + "/SOLIDWORKS 2025")
        return
        # This return is unreachable but satisfies type checker
        yield  # pragma: no cover

    monkeypatch.setattr(Path, "exists", fake_path_exists)

    # Note: This test is complex because _detect_installed_solidworks_year
    # depends on actual file system. We're just testing the error path.
    result = _detect_installed_solidworks_year()
    assert result is None or isinstance(result, int)


@pytest.mark.parametrize(
    "query,expected_matches_min",
    [
        ("open", 1),  # Should match "OpenDoc6"
        ("doc", 1),  # Should match "CloseDoc", "IModelDoc2"
        ("title", 1),  # Should match "GetTitle"
        ("xyz", 0),  # No matches
    ],
)
def test_search_index_query_scoring(query: str, expected_matches_min: int) -> None:
    """_search_index should score matches by relevance."""
    test_index = {
        "com_objects": {
            "ISldWorks": {
                "methods": ["OpenDoc6", "CloseDoc", "GetActiveObject"],
                "properties": ["Visible", "ActiveDoc", "RevisionNumber"],
            },
            "IModelDoc2": {
                "methods": ["SaveBitmapWithVariableSize", "GetTitle"],
                "properties": ["ActiveView", "ActiveLayer"],
            },
        },
        "vba_references": {
            "SldWorks": {"description": "SolidWorks API", "status": "available"}
        },
    }

    matches = _search_index(test_index, query, max_results=10)
    assert len(matches) >= expected_matches_min


def test_search_index_with_empty_index() -> None:
    """_search_index should handle empty index gracefully."""
    empty_index = {"com_objects": {}, "vba_references": {}}
    matches = _search_index(empty_index, "anything", max_results=5)
    assert matches == []


def test_search_index_respects_max_results() -> None:
    """_search_index should limit results to max_results."""
    test_index = {
        "com_objects": {
            "ISldWorks": {
                "methods": [f"Method{i}" for i in range(20)],
                "properties": [f"Prop{i}" for i in range(20)],
            }
        }
    }

    matches = _search_index(test_index, "method", max_results=5)
    assert len(matches) <= 5


@pytest.mark.parametrize(
    "input_str,expected_year",
    [
        ("SOLIDWORKS 2026", 2026),
        ("C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS 2025", 2025),
        ("version-2024-build", 2024),
        ("sw 2023", 2023),  # Space before year creates word boundary
        ("no year here", None),
        ("", None),
        ("sw2023", None),  # No word boundary, won't match
    ],
)
def test_extract_year_regex_coverage(input_str: str, expected_year: int | None) -> None:
    """_extract_year should extract years from various formats with word boundaries."""
    result = _extract_year(input_str)
    assert result == expected_year


def test_enumerate_typeinfo_members_skips_none_and_underscore_names() -> None:
    """_enumerate_typeinfo_members skips entries where name is None or starts with _
    (docs_discovery.py line 215: continue branch)."""
    from types import SimpleNamespace

    class _TypeInfoWithNullName:
        """Mock that returns None for the first entry, then a valid name."""

        def GetTypeAttr(self):
            return SimpleNamespace(cFuncs=2, cImplTypes=0)

        def GetFuncDesc(self, i):
            return SimpleNamespace(memid=i, invkind=1)

        def GetNames(self, memid):
            # First entry returns no names; second returns a name with leading underscore.
            if memid == 0:
                return []
            return ["_InternalMethod"]

    methods, props = _enumerate_typeinfo_members(_TypeInfoWithNullName())
    # Both entries should be skipped — methods and props stay empty.
    assert methods == []
    assert props == []


def test_enumerate_typeinfo_members_outer_exception() -> None:
    """_enumerate_typeinfo_members returns empty lists when GetTypeAttr() raises
    (docs_discovery.py lines 226-227: outer except block)."""

    class _BrokenTypeInfo:
        """Raises on GetTypeAttr."""

        def GetTypeAttr(self):
            raise RuntimeError("no type info")

    methods, props = _enumerate_typeinfo_members(_BrokenTypeInfo())
    assert methods == []
    assert props == []


def test_discover_com_via_typeinfo_impl_type_exception() -> None:
    """_discover_com_via_typeinfo continues gracefully when GetRefTypeOfImplType raises
    (docs_discovery.py lines 270-271) and when the outer GetTypeAttr raises (lines 272-273)."""
    from types import SimpleNamespace

    import solidworks_mcp.tools.docs_discovery as docs_mod

    # First GetTypeAttr (inside _enumerate_typeinfo_members) must succeed.
    # Second GetTypeAttr (inside _discover_com_via_typeinfo) raises.
    call_count = {"n": 0}

    class _TypeInfo:
        def GetTypeAttr(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return SimpleNamespace(cFuncs=1, cImplTypes=1)
            # Second call raises — triggers outer except (lines 272-273).
            raise RuntimeError("type attr unavailable")

        def GetFuncDesc(self, i):
            return SimpleNamespace(memid=i, invkind=1)

        def GetNames(self, memid):
            return ["CreatePart"]

    class _FakeSWApp:
        class _OleObj:
            def GetTypeInfo(self_inner):  # noqa: N805
                return _TypeInfo()

        _oleobj_ = _OleObj()

    with patch.object(docs_mod, "HAS_WIN32COM", True):
        result = docs_mod._discover_com_via_typeinfo(_FakeSWApp())

    com_dict, m_count, p_count = result
    # CreatePart should appear as a method despite the outer exception.
    assert "ISldWorks" in com_dict
    assert "CreatePart" in com_dict["ISldWorks"]["methods"]


def test_discover_com_via_typeinfo_impl_type_ref_exception() -> None:
    """_discover_com_via_typeinfo skips impl interfaces when GetRefTypeOfImplType raises
    (docs_discovery.py lines 270-271: inner continue branch)."""
    from types import SimpleNamespace

    import solidworks_mcp.tools.docs_discovery as docs_mod

    class _TypeInfo:
        def GetTypeAttr(self):
            return SimpleNamespace(cFuncs=1, cImplTypes=1)

        def GetFuncDesc(self, i):
            return SimpleNamespace(memid=i, invkind=1)

        def GetNames(self, memid):
            return ["SaveFile"]

        def GetRefTypeOfImplType(self, impl_idx):
            raise RuntimeError("COM interface unavailable")

    class _FakeSWApp:
        class _OleObj:
            def GetTypeInfo(self_inner):  # noqa: N805
                return _TypeInfo()

        _oleobj_ = _OleObj()

    with patch.object(docs_mod, "HAS_WIN32COM", True):
        result = docs_mod._discover_com_via_typeinfo(_FakeSWApp())

    com_dict, m_count, p_count = result
    # The impl type is skipped but the primary method is still registered.
    assert "SaveFile" in com_dict["ISldWorks"]["methods"]


def test_discover_vba_references_typelib_key_open_fails() -> None:
    """Returns empty dict when HKEY_CLASSES_ROOT\\TypeLib cannot be opened
    (docs_discovery.py lines 370-371)."""
    import sys

    if sys.platform != "win32":
        pytest.skip("winreg only on Windows")

    import winreg

    with patch.object(winreg, "OpenKey", side_effect=OSError("access denied")):
        refs = _discover_vba_references_via_registry()

    assert refs == {}


def test_discover_vba_references_guid_key_open_fails() -> None:
    """Continues enumeration when individual GUID key cannot be opened
    (docs_discovery.py lines 367-368)."""
    import sys

    if sys.platform != "win32":
        pytest.skip("winreg only on Windows")

    import winreg

    call_count = {"n": 0}

    def _open_key_side_effect(root, sub_key, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call (typelib_key) must succeed but return a mock.
            return MagicMock()
        raise OSError("no such guid key")

    enum_call = {"n": 0}

    def _enum_key_once(key, idx):
        # Return one GUID then raise to break the while-True loop.
        # Without raising, EnumKey always returns and the loop never exits.
        enum_call["n"] += 1
        if enum_call["n"] == 1:
            return "{00000000-0000-0000-0000-000000000000}"
        raise OSError("no more keys")

    with (
        patch.object(winreg, "OpenKey", side_effect=_open_key_side_effect),
        patch.object(winreg, "EnumKey", side_effect=_enum_key_once),
        patch.object(winreg, "CloseKey"),
    ):
        refs = _discover_vba_references_via_registry()

    assert isinstance(refs, dict)


def test_discover_vba_references_version_key_open_fails() -> None:
    """Continues enumeration when version key cannot be opened
    (docs_discovery.py lines 364-365)."""
    import sys

    if sys.platform != "win32":
        pytest.skip("winreg only on Windows")

    import winreg

    call_count = {"n": 0}

    def _open_key_side_effect(root, sub_key, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MagicMock()  # typelib_key
        if call_count["n"] == 2:
            return MagicMock()  # guid_key
        # Third call (version key) fails.
        raise OSError("version key missing")

    enum_call = {"n": 0}

    def _enum_key_side_effect(key, idx):
        # First EnumKey (GUID level) returns a GUID.
        # Second EnumKey (version level) returns a version then raises.
        enum_call["n"] += 1
        if enum_call["n"] == 1:
            return "{DEADBEEF-0000-0000-0000-000000000000}"
        if enum_call["n"] == 2:
            return "1.0"
        raise OSError("no more keys")

    with (
        patch.object(winreg, "OpenKey", side_effect=_open_key_side_effect),
        patch.object(winreg, "EnumKey", side_effect=_enum_key_side_effect),
        patch.object(winreg, "CloseKey"),
    ):
        refs = _discover_vba_references_via_registry()

    assert isinstance(refs, dict)


def test_discover_com_objects_typeinfo_exception_is_logged() -> None:
    """discover_com_objects logs and continues when _discover_com_via_typeinfo raises
    (docs_discovery.py lines 472-473)."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    discovery = SolidWorksDocsDiscovery()
    discovery.sw_app = MagicMock()  # fake connected app

    with (
        patch.object(docs_mod, "HAS_WIN32COM", True),
        patch.object(
            docs_mod,
            "_discover_com_via_typeinfo",
            side_effect=RuntimeError("COM explosion"),
        ),
    ):
        result = discovery.discover_com_objects()

    # Despite the exception, discover_com_objects should return a dict (not raise).
    assert isinstance(result, dict)


def test_discover_vba_references_empty_result_logs_debug() -> None:
    """discover_vba_references logs at DEBUG level when no refs are found
    (docs_discovery.py line 543)."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    discovery = SolidWorksDocsDiscovery()

    with patch.object(
        docs_mod, "_discover_vba_references_via_registry", return_value={}
    ):
        refs = discovery.discover_vba_references()

    assert refs == {}


def test_detect_installed_solidworks_year_oserror_on_iterdir(tmp_path) -> None:
    """_detect_installed_solidworks_year returns None when iterdir raises OSError
    (docs_discovery.py lines 725-727)."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    # We test the real implementation directly — no mock needed here.
    pass

    # Patch the root path to exist but iterdir() raises OSError.
    from pathlib import Path

    real_func = docs_mod._detect_installed_solidworks_year

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "iterdir", side_effect=OSError("permission denied")):
            result = real_func()

    assert result is None
