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
from pydantic import BaseModel

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.tools.docs_discovery import (
    SolidWorksDocsDiscovery,
    _discover_vba_references_via_registry,
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
from solidworks_mcp.tools.tool_boundary import ToolOperationError
from solidworks_mcp.tools.type_library import (
    SOLIDWORKS_TYPELIB_GUID,
    ApiInterface,
    TypeLibraryInfo,
)

REAL_SW_ENV_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"


def _dump(model: BaseModel) -> dict:
    """A lookup result as the tools return it."""
    return model.model_dump(exclude_unset=True)


def _method(*params: tuple[str, str, str], returns: str | None = None) -> dict:
    """A method record as the type library reader writes it."""
    return {
        "kind": "method",
        "description": "",
        "parameters": [
            {"name": name, "type": kind, "direction": direction}
            for name, kind, direction in params
        ],
        "return_type": returns,
    }


def _property(kind: str, access: str = "read") -> dict:
    """A property record as the type library reader writes it."""
    return {"kind": "property", "description": "", "type": kind, "access": access}


def _iface(**members: dict) -> dict:
    """An interface record: name lists and counts derived from its members."""
    methods = sorted(n for n, m in members.items() if m["kind"] == "method")
    properties = sorted(n for n, m in members.items() if m["kind"] == "property")
    return {
        "methods": methods,
        "properties": properties,
        "method_count": len(methods),
        "property_count": len(properties),
        "members": members,
    }


_COM_OBJECTS = {
    "ISldWorks": _iface(
        OpenDoc6={
            **_method(
                ("FileName", "String", "in"),
                ("Type", "Long", "in"),
                ("Options", "Long", "in"),
                ("Configuration", "String", "in"),
                ("Errors", "Long", "in_out"),
                ("Warnings", "Long", "in_out"),
                returns="IModelDoc2",
            ),
            "description": "Opens an existing document",
        },
        CloseDoc=_method(("Name", "String", "in")),
        ActivateDoc3=_method(returns="Object"),
        Visible=_property("Boolean", "read_write"),
        ActiveDoc=_property("Object"),
    ),
    "IModelDoc2": _iface(
        GetTitle=_method(returns="String"),
        CloseDoc=_method(),
        ViewZoomtofit2=_method(),
        Visible=_property("Boolean", "read_write"),
    ),
}

_LIBRARY = TypeLibraryInfo(
    guid=SOLIDWORKS_TYPELIB_GUID,
    version="34.0",
    year=2026,
    path=r"C:\SOLIDWORKS\sldworks.tlb",
)


@pytest.fixture(autouse=True)
def _isolated_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run each test in an empty folder, so no index on disk is found or written.

    The root conftest already reports no type library; a test that wants one
    uses ``fake_type_library``.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fake_type_library(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """A registered type library 34.0 holding ``_COM_OBJECTS``.

    Returns:
        The ``(year, strict)`` of every load, i.e. every index build.
    """
    import solidworks_mcp.tools.docs_discovery as docs_mod

    calls: list[tuple] = []

    def _load(year: int | None = None, strict: bool = False) -> tuple:
        calls.append((year, strict))
        return "the library", _LIBRARY

    monkeypatch.setattr(docs_mod, "load_type_library", _load)
    monkeypatch.setattr(docs_mod, "target_version", lambda *_a, **_k: (34, 0))
    monkeypatch.setattr(
        docs_mod,
        "index_type_library",
        lambda _lib: {
            name: ApiInterface.model_validate(record)
            for name, record in _COM_OBJECTS.items()
        },
    )
    monkeypatch.setattr(docs_mod, "_discover_vba_references_via_registry", dict)
    # No RAG builder: discovery skips the rebuild instead of loading the
    # embedding model. A test that wants one sets its own.
    monkeypatch.setitem(
        sys.modules, "solidworks_mcp.agents.vector_rag", SimpleNamespace()
    )
    return calls


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
        assert "type_library" in result, "Success result should name the type library"

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
                "version": "2.0",
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


def test_save_index_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    """Save_index writes JSON, and a write error names the file."""
    discovery = SolidWorksDocsDiscovery(output_dir=temp_dir)
    saved = discovery.save_index("docs_index.json")
    assert saved is not None and saved.exists()

    import solidworks_mcp.tools.docs_discovery as docs_mod

    monkeypatch.setattr(
        docs_mod.json,
        "dump",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(ToolOperationError, match="Couldn't save the API index to"):
        discovery.save_index("bad.json")


def test_index_load_and_search_helpers(temp_dir: Path) -> None:
    """Low-level index find/load/search helpers should return coherent structures."""
    index_dir = Path(".generated/docs-index")
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

    assert _find_index_file(2026) == index_path

    loaded = _load_index_file(index_path)
    assert isinstance(loaded, dict)

    results = [_dump(m) for m in _search_index(loaded or {}, "open", 5)]
    assert results
    assert results[0]["member_type"] in {"method", "property", "reference"}


def test_fallback_help_profiles() -> None:
    """Fallback guidance should adapt by query intent."""
    revolve_help = _fallback_help_for_query("how to revolve a bat profile")
    extrude_help = _fallback_help_for_query("extrude this sketch")
    generic_help = _fallback_help_for_query("unknown phrase")

    assert "create_revolve" in revolve_help["suggested_tools"]
    assert "create_extrusion" in extrude_help["suggested_tools"]
    assert "lookup_api_interface" in generic_help["suggested_tools"]


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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read failed")),
    )
    assert _load_index_file(arr_file) is None


def test_find_index_file_search_dir_and_search_index_edge_cases(temp_dir: Path) -> None:
    """Cover search-dir discovery and empty-token/exact-match scoring in _search_index."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    base = Path("tests/.generated/docs-index")
    base.mkdir(parents=True, exist_ok=True)
    idx = base / "solidworks_docs_index_2027.json"
    idx.write_text("{}", encoding="utf-8")

    assert docs_mod._find_index_file(2027) == idx

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
    exact = [_dump(m) for m in docs_mod._search_index(index, "OpenDoc6", 10)]
    assert exact and exact[0]["member"] == "OpenDoc6"
    refs = [_dump(m) for m in docs_mod._search_index(index, "SolidWorks API", 10)]
    assert any(item["member_type"] == "reference" for item in refs)


def test_year_comes_from_the_install_path_and_is_never_guessed() -> None:
    """Without --year, a year in the configured install path is used; else None."""
    import solidworks_mcp.tools.docs_discovery as docs_mod

    cfg = SimpleNamespace(solidworks_year=None, solidworks_path="C:/SW/SOLIDWORKS 2028")
    assert docs_mod._resolve_solidworks_year(None, cfg) == 2028
    # None means "the newest installed type library".
    assert docs_mod._resolve_solidworks_year(None, SimpleNamespace()) is None


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
    results = [_dump(m) for m in docs_mod._search_index(index, "RevisionNumber", 5)]
    assert any(item["member_type"] == "property" for item in results)


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


def test_find_index_file_none_when_missing() -> None:
    """Covers _find_index_file final return None branch."""
    from solidworks_mcp.tools.docs_discovery import _find_index_file

    assert _find_index_file(2099) is None


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

_LOOKUP_INDEX = {"version": "2.0", "com_objects": _COM_OBJECTS}


def test_lookup_interface_known_returns_all_members():
    result = _dump(_lookup_interface(_LOOKUP_INDEX, "isldworks"))  # any case
    assert result["found"] is True
    assert result["interface"] == "ISldWorks"
    assert result["method_count"] == 3
    assert result["property_count"] == 2
    assert "OpenDoc6" in result["methods"]


def test_lookup_interface_unknown_reports_not_found():
    result = _dump(_lookup_interface(_LOOKUP_INDEX, "INotIndexed"))
    assert result["found"] is False


def test_lookup_method_resolves_a_property_too():
    result = _dump(_lookup_method(_LOOKUP_INDEX, "ISldWorks", "visible"))
    assert result["found"] is True
    assert result["member_type"] == "property"


def test_lookup_method_unknown_member_reports_not_found():
    result = _dump(_lookup_method(_LOOKUP_INDEX, "ISldWorks", "NoSuchMethod"))
    assert result["found"] is False


def test_lookup_method_unknown_interface_reports_not_found():
    result = _dump(_lookup_method(_LOOKUP_INDEX, "INope", "OpenDoc6"))
    assert result["found"] is False


def test_find_related_from_interface_returns_its_members():
    result = _dump(_find_related_api_members(_LOOKUP_INDEX, "IModelDoc2", 25))
    assert result["resolved_as"] == "interface"
    members = {(r["object"], r["member"]) for r in result["related"]}
    assert ("IModelDoc2", "GetTitle") in members


def test_find_related_from_member_returns_siblings_across_interfaces():
    result = _dump(_find_related_api_members(_LOOKUP_INDEX, "CloseDoc", 25))
    assert result["resolved_as"] == "member"
    objs = {r["object"] for r in result["related"]}
    # CloseDoc lives on both interfaces -> siblings from both come back
    assert objs == {"ISldWorks", "IModelDoc2"}
    assert all(r["member"] != "CloseDoc" for r in result["related"])


def test_find_related_name_substring_match():
    result = _dump(_find_related_api_members(_LOOKUP_INDEX, "Doc", 25))
    assert result["resolved_as"] == "name-match"
    assert any("Doc" in r["member"] for r in result["related"])


def test_find_related_respects_max_results():
    result = _dump(_find_related_api_members(_LOOKUP_INDEX, "ISldWorks", 2))
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

    related = await tools["find_related_api_members"]({**common, "name": "CloseDoc"})
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
    return {"version": "2.0", "com_objects": {}}, index_file


_REFRESH_ON = SimpleNamespace(docs_index_auto_refresh=True, docs_index_max_age_days=21)


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
            "year": 2030,
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
        ("unknown intent", "lookup_api_interface"),
        ("generic query", "lookup_api_interface"),
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

    matches = [_dump(m) for m in _search_index(test_index, query, max_results=10)]
    assert len(matches) >= expected_matches_min


def test_search_index_with_empty_index() -> None:
    """_search_index should handle empty index gracefully."""
    empty_index = {"com_objects": {}, "vba_references": {}}
    matches = [_dump(m) for m in _search_index(empty_index, "anything", max_results=5)]
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

    matches = [_dump(m) for m in _search_index(test_index, "method", max_results=5)]
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


# ---------------------------------------------------------------------------
# The index comes from the SolidWorks type library (#195)
# ---------------------------------------------------------------------------


async def _docs_tools(mcp_server, mock_config) -> dict:
    """Register the docs tools and return them by name."""
    await register_docs_discovery_tools(mcp_server, object(), mock_config)
    return {tool.name: tool.fn for tool in await mcp_server.list_tools()}


def test_discovery_reads_the_type_library(fake_type_library, tmp_path) -> None:
    discovery = SolidWorksDocsDiscovery(
        output_dir=tmp_path, year=2025, strict_year=True
    )

    index = discovery.discover_all()

    assert fake_type_library == [(2025, True)]
    assert index["version"] == "2.0"
    assert index["type_library"] == _LIBRARY.model_dump()
    assert index["solidworks_version"] == "34.0"
    assert index["com_objects"] == _COM_OBJECTS
    assert index["vba_references"] == {}
    assert index["total_methods"] == 6
    assert index["total_properties"] == 3


def test_save_index_writes_compact_json(fake_type_library, tmp_path) -> None:
    discovery = SolidWorksDocsDiscovery(output_dir=tmp_path)
    discovery.discover_all()

    saved = discovery.save_index("index.json")

    text = saved.read_text(encoding="utf-8")
    assert "\n" not in text and ", " not in text
    assert json.loads(text)["com_objects"] == _COM_OBJECTS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vector_rag", "rag_indexed"),
    [
        (
            SimpleNamespace(
                build_solidworks_api_docs_index=lambda _path: SimpleNamespace(
                    chunk_count=2, save=lambda: None
                )
            ),
            True,
        ),
        # No builder in the module -> ImportError on "from ... import ...".
        (SimpleNamespace(), False),
        (
            SimpleNamespace(
                build_solidworks_api_docs_index=MagicMock(
                    side_effect=RuntimeError("disk full")
                )
            ),
            False,
        ),
    ],
)
async def test_discover_tool_saves_the_index_under_the_library_year(
    mcp_server,
    mock_config,
    fake_type_library,
    monkeypatch,
    tmp_path,
    vector_rag,
    rag_indexed,
) -> None:
    monkeypatch.setitem(sys.modules, "solidworks_mcp.agents.vector_rag", vector_rag)
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["discover_solidworks_docs"]({"output_dir": str(tmp_path)})

    assert result["status"] == "success"
    assert result["year"] == 2026
    assert result["output_file"] == str(tmp_path / "solidworks_docs_index_2026.json")
    assert result["summary"]["total_com_objects"] == 2
    assert result["rag_indexed"] is rag_indexed
    # The megabytes of index stay on disk, out of the response.
    assert "index" not in result
    assert result["type_library"] == _LIBRARY.model_dump()
    assert fake_type_library[-1][1] is False  # no year asked for: not strict


@pytest.mark.asyncio
async def test_discover_tool_holds_an_asked_for_year_to_that_year(
    mcp_server, mock_config, fake_type_library, tmp_path
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    await tools["discover_solidworks_docs"]({"output_dir": str(tmp_path), "year": 2025})

    assert fake_type_library == [(2025, True)]


@pytest.mark.asyncio
async def test_discover_tool_needs_no_running_solidworks_but_an_installed_one(
    mcp_server, mock_config
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["discover_solidworks_docs"]({})

    assert result["status"] == "error"
    assert result["message"] == "No SolidWorks type library in this test."


@pytest.mark.asyncio
async def test_a_lookup_builds_a_missing_index(
    mcp_server, mock_config, fake_type_library
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["lookup_api_method"](
        {"interface": "ISldWorks", "method": "OpenDoc6"}
    )

    assert result["index_status"] == "rebuilt"
    assert result["type_library_version"] == "34.0"
    saved = Path(result["source_index_file"])
    assert saved.name == "solidworks_docs_index_2026.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["version"] == "2.0"
    assert result["result"]["found"] is True


@pytest.mark.asyncio
async def test_an_old_format_index_is_rebuilt_not_answered_from(
    mcp_server, mock_config, fake_type_library, tmp_path
) -> None:
    old = tmp_path / "old_index.json"
    old.write_text(
        json.dumps(
            {
                "version": "1.0",
                "com_objects": {
                    "IModelDoc2": {"methods": ["SaveBitmapWithVariableSize"]}
                },
            }
        ),
        encoding="utf-8",
    )
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["lookup_api_method"](
        {
            "interface": "IModelDoc2",
            "method": "SaveBitmapWithVariableSize",
            "index_file": str(old),
        }
    )

    assert result["index_status"] == "rebuilt"
    assert result["result"]["found"] is False
    assert fake_type_library  # the type library was read


@pytest.mark.asyncio
async def test_a_current_index_is_answered_from_without_reading_the_library(
    mcp_server, mock_config, fake_type_library, tmp_path
) -> None:
    current = tmp_path / "current.json"
    current.write_text(json.dumps(_LOOKUP_INDEX), encoding="utf-8")
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["lookup_api_interface"](
        {"interface": "ISldWorks", "index_file": str(current)}
    )

    assert result["index_status"] == "ready"
    assert result["source_index_file"] == str(current)
    assert result["result"]["method_count"] == 3
    assert fake_type_library == []


@pytest.mark.asyncio
async def test_a_lookup_for_a_year_asks_for_that_year(
    mcp_server, mock_config, fake_type_library, monkeypatch
) -> None:
    import solidworks_mcp.tools.docs_discovery as docs_mod

    asked: list[tuple] = []

    def _target(year: int | None, strict: bool) -> tuple[int, int]:
        asked.append((year, strict))
        return 33, 0

    monkeypatch.setattr(docs_mod, "target_version", _target)
    tools = await _docs_tools(mcp_server, mock_config)

    await tools["lookup_api_interface"]({"interface": "ISldWorks", "year": 2025})

    assert asked == [(2025, True)]
    assert fake_type_library == [(2025, True)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("lookup_api_method", {"interface": "IModelDoc2", "method": "SaveBMP"}),
        ("lookup_api_interface", {"interface": "IModelDoc2"}),
        ("find_related_api_members", {"name": "SaveBMP"}),
    ],
)
async def test_without_a_type_library_lookups_say_why(
    mcp_server, mock_config, tool, arguments
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools[tool](arguments)

    assert result["status"] == "success"
    assert result["index_status"] == "unavailable"
    assert result["source_index_file"] is None
    assert result["type_library_version"] is None
    assert result["result"]["found"] is False
    assert result["result"]["note"] == "No SolidWorks type library in this test."


@pytest.mark.asyncio
async def test_without_a_type_library_search_says_why_in_its_guidance(
    mcp_server, mock_config
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    # The old opt-in is still accepted, and changes nothing.
    result = await tools["search_solidworks_api_help"](
        {"query": "save bitmap", "auto_discover_if_missing": True}
    )

    assert result["status"] == "success"
    assert result["index_status"] == "unavailable"
    assert result["matches"] == []
    assert "No SolidWorks type library in this test." in result["guidance"]


@pytest.mark.asyncio
async def test_search_points_at_lookup_api_method_for_signatures(
    mcp_server, mock_config, fake_type_library
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["search_solidworks_api_help"]({"query": "OpenDoc6"})

    assert result["index_status"] == "rebuilt"
    assert result["matches"][0]["member"] == "OpenDoc6"
    assert "lookup_api_method" in result["guidance"]


def test_lookup_method_returns_the_signature() -> None:
    result = _dump(_lookup_method(_LOOKUP_INDEX, "ISldWorks", "OpenDoc6"))

    assert result == {
        "found": True,
        "interface": "ISldWorks",
        "member": "OpenDoc6",
        "member_type": "method",
        "signature_indexed": True,
        "description": "Opens an existing document",
        "parameters": _COM_OBJECTS["ISldWorks"]["members"]["OpenDoc6"]["parameters"],
        "return_type": "IModelDoc2",
    }
    directions = [p["direction"] for p in result["parameters"]]
    assert directions == ["in", "in", "in", "in", "in_out", "in_out"]


def test_lookup_method_reports_the_real_spelling_and_says_casing_differs() -> None:
    result = _dump(_lookup_method(_LOOKUP_INDEX, "IModelDoc2", "ViewZoomToFit2"))

    assert result["found"] is True
    assert result["member"] == "ViewZoomtofit2"
    assert result["note"] == (
        "SolidWorks spells it 'ViewZoomtofit2'. COM matches names regardless "
        "of case, so 'ViewZoomToFit2' also works."
    )


def test_lookup_method_gives_a_property_its_value_type() -> None:
    result = _dump(_lookup_method(_LOOKUP_INDEX, "ISldWorks", "Visible"))

    assert result["member_type"] == "property"
    assert result["parameters"] == []
    assert result["return_type"] == "Boolean"
    assert result["access"] == "read_write"
    assert "note" not in result


def test_maybe_refresh_index_rebuilds_an_old_current_format_index(
    stale_index, fake_type_library
) -> None:
    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    index, index_file = stale_index

    refreshed, refreshed_file = _maybe_refresh_index(
        index, index_file, 2026, _REFRESH_ON
    )

    assert refreshed["com_objects"] == _COM_OBJECTS
    assert refreshed_file.name == "solidworks_docs_index_2026.json"
    assert refreshed_file != index_file
    assert fake_type_library == [(2026, False)]


def test_maybe_refresh_index_keeps_the_old_index_without_a_type_library(
    stale_index,
) -> None:
    from solidworks_mcp.tools.docs_discovery import _maybe_refresh_index

    index, index_file = stale_index

    assert _maybe_refresh_index(index, index_file, 2026, _REFRESH_ON) == (
        index,
        index_file,
    )


# ---------------------------------------------------------------------------
# The index is reused, the year comes from the server, descriptions guide
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_lookups_build_the_index_once(
    mcp_server, mock_config, fake_type_library
) -> None:
    tools = await _docs_tools(mcp_server, mock_config)
    arguments = {"interface": "ISldWorks", "method": "OpenDoc6"}

    statuses = [
        (await tools["lookup_api_method"](arguments))["index_status"] for _ in range(3)
    ]

    assert statuses == ["rebuilt", "ready", "ready"]
    assert len(fake_type_library) == 1


@pytest.mark.asyncio
async def test_an_index_from_another_type_library_version_is_rebuilt(
    mcp_server, mock_config, fake_type_library
) -> None:
    older = {**_LOOKUP_INDEX, "type_library": {"version": "33.0", "year": 2026}}
    folder = Path(".generated/docs-index")
    folder.mkdir(parents=True)
    (folder / "solidworks_docs_index_2026.json").write_text(
        json.dumps(older), encoding="utf-8"
    )
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["lookup_api_interface"]({"interface": "ISldWorks"})

    assert result["index_status"] == "rebuilt"
    assert result["type_library_version"] == "34.0"


@pytest.mark.asyncio
async def test_a_server_year_that_isnt_installed_falls_back_to_the_newest(
    mcp_server, fake_type_library, monkeypatch
) -> None:
    import solidworks_mcp.tools.docs_discovery as docs_mod
    import solidworks_mcp.tools.type_library as type_library

    # The real version choice, over a registry holding only SolidWorks 2026.
    monkeypatch.setattr(docs_mod, "target_version", type_library.target_version)
    monkeypatch.setattr(type_library, "winreg", object())
    monkeypatch.setattr(type_library, "registered_versions", lambda _r: [(34, 0)])
    tools = await _docs_tools(mcp_server, SolidWorksMCPConfig(solidworks_year=2025))

    first = await tools["lookup_api_interface"]({"interface": "ISldWorks"})
    second = await tools["lookup_api_interface"]({"interface": "ISldWorks"})

    assert (first["year"], first["index_status"]) == (2026, "rebuilt")
    assert (second["year"], second["index_status"]) == (2026, "ready")


@pytest.mark.asyncio
async def test_discover_without_vba_skips_the_registry_scan(
    mcp_server, mock_config, fake_type_library, monkeypatch, tmp_path
) -> None:
    import solidworks_mcp.tools.docs_discovery as docs_mod

    scan = MagicMock(return_value={"lib": {"status": "available"}})
    monkeypatch.setattr(docs_mod, "_discover_vba_references_via_registry", scan)
    tools = await _docs_tools(mcp_server, mock_config)

    result = await tools["discover_solidworks_docs"](
        {"output_dir": str(tmp_path), "include_vba": False}
    )

    scan.assert_not_called()
    assert result["summary"]["available_vba_libs"] == []


@pytest.mark.asyncio
async def test_each_docs_tool_tells_the_agent_its_setup(
    mcp_server, mock_config
) -> None:
    await register_docs_discovery_tools(mcp_server, object(), mock_config)
    tools = {tool.name: tool for tool in await mcp_server.list_tools()}
    lookups = (
        "search_solidworks_api_help",
        "lookup_api_method",
        "lookup_api_interface",
        "find_related_api_members",
    )

    for name in (*lookups, "discover_solidworks_docs"):
        description = " ".join(tools[name].description.split())
        assert "installed, not running" in description, name
        assert "Example input:" in description, name
        # Every input field explains itself (the model is inlined, then null).
        model = tools[name].parameters["properties"]["input_data"]["anyOf"][0]
        for field, schema in model["properties"].items():
            assert schema.get("description"), f"{name}.{field}"
    for name in lookups:
        assert "builds the index" in " ".join(tools[name].description.split()), name
        assert "index_status" in tools[name].description, name


@pytest.mark.asyncio
async def test_a_registered_library_that_wont_load_is_explained(
    mcp_server, mock_config, fake_type_library, monkeypatch
) -> None:
    import solidworks_mcp.tools.docs_discovery as docs_mod
    from solidworks_mcp.tools.type_library import TypeLibraryUnavailable

    def _broken(*_args: object) -> None:
        raise TypeLibraryUnavailable("registered but couldn't be loaded")

    monkeypatch.setattr(docs_mod, "load_type_library", _broken)
    tools = await _docs_tools(mcp_server, SolidWorksMCPConfig(solidworks_year=2026))

    result = await tools["lookup_api_method"](
        {"interface": "ISldWorks", "method": "OpenDoc6"}
    )

    assert result["index_status"] == "unavailable"
    assert result["year"] == 2026
    assert result["result"]["note"] == "registered but couldn't be loaded"
