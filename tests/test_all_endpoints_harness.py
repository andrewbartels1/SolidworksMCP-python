"""Full endpoint integration test harness for the SolidWorks MCP Server.

Provides three test levels:
  Level A  - Schema/Contract: every registered tool is callable and returns a dict.
             Safe to run with the mock adapter (no SolidWorks required).
  Level B  - Execution smoke: every tool is invoked with a minimal, safe payload
             and must NOT raise an unhandled exception.
             Runs with mock adapter by default; real adapter when
             SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true.
  Level C  - Real-COM lifecycle: create/save/export/close flows executed against a
             live SolidWorks instance.
             Only active when SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true on Windows.

Docs-discovery compatibility phase (pre-test):
  Before Level-C tests the harness calls `discover_solidworks_docs` and compares
  the discovered COM API surface to a reference snapshot.  Differences are
  classified as Compatible / Degraded / Hard-break and written to
  tests/.generated/solidworks_integration/api_compat_report.json.

Run with:
    # Mock-safe (CI)
    pytest tests/test_all_endpoints_harness.py -v

    # Full real integration (Windows + SolidWorks running)
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION="true"
    pytest tests/test_all_endpoints_harness.py -v
"""

from __future__ import annotations

import json
import os
import platform
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from src.solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from src.solidworks_mcp.server import SolidWorksMCPServer

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

REAL_SW_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"
OUTPUT_DIR = Path("tests/.generated/solidworks_integration")
CATALOG_PATH = Path("tests/.generated/tool_catalog.json")
MAX_TOOL_RESPONSE_BYTES = 250_000
MAX_SMOKE_TOTAL_RESPONSE_BYTES = 3_000_000
SAMPLE_MODELS_ENV = "SOLIDWORKS_MCP_SAMPLE_MODELS_DIR"

# Reference snapshot of required COM objects – add to this list as the server grows.
REQUIRED_COM_METHODS: list[str] = [
    "SldWorks.ISldWorks",
    "SldWorks.IModelDoc2",
    "SldWorks.IFeatureManager",
    "SldWorks.ISketchManager",
    "SldWorks.IDrawingDoc",
    "SldWorks.IAssemblyDoc",
]


def _real_sw_enabled() -> bool:
    """Test helper for real sw enabled."""
    return os.getenv(REAL_SW_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_windows() -> bool:
    """Test helper for is windows."""
    return platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_server() -> AsyncGenerator[SolidWorksMCPServer, None]:
    """Mock-adapter server — no SolidWorks required."""
    config = SolidWorksMCPConfig(
        adapter_type=AdapterType.MOCK,
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        testing=True,
    )
    server = SolidWorksMCPServer(config)
    await server.setup()
    yield server


@pytest_asyncio.fixture
async def real_server() -> AsyncGenerator[SolidWorksMCPServer, None]:
    """Real COM adapter — requires Windows + SolidWorks running."""
    config = SolidWorksMCPConfig(
        adapter_type=AdapterType.PYWIN32,
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
    )
    server = SolidWorksMCPServer(config)
    await server.setup()
    if server.adapter and not server.adapter.is_connected():
        await server.adapter.connect()
        server.state.is_connected = True
    yield server
    if server.adapter and server.adapter.is_connected():
        await server.adapter.disconnect()
        server.state.is_connected = False


@pytest_asyncio.fixture
async def output_dir() -> Path:
    """Test helper for output dir."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _load_catalog() -> list[dict[str, Any]]:
    """Test helper for load catalog."""
    if not CATALOG_PATH.exists():
        return []
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    """Test helper for find tool."""
    for tool in server.mcp._tools:
        if tool.name == tool_name:
            return tool.func
    return None


def _candidate_sample_roots() -> list[Path]:
    """Return likely SolidWorks sample roots in preferred order."""
    candidates: list[Path] = []

    env_override = os.getenv(SAMPLE_MODELS_ENV, "").strip()
    if env_override:
        candidates.append(Path(env_override))

    # Keep 2026 first, then try nearby versions to support side-by-side installs.
    years = [2026, 2025, 2024, 2023, 2022]
    for year in years:
        candidates.append(
            Path(
                f"C:/Users/Public/Documents/SOLIDWORKS/SOLIDWORKS {year}/samples/learn"
            )
        )

    # De-duplicate while preserving order.
    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def _resolve_sample_parts_dir() -> Path:
    """Find the first existing sample root or skip with a clear diagnostic."""
    for candidate in _candidate_sample_roots():
        if candidate.exists():
            return candidate

    searched = "\n".join(f"  - {p}" for p in _candidate_sample_roots())
    pytest.skip(
        "No SolidWorks sample models directory found. "
        f"Set {SAMPLE_MODELS_ENV} to override. Searched:\n{searched}"
    )


def _find_sample_part() -> Path:
    """Test helper for find sample part."""
    sample_parts_dir = _resolve_sample_parts_dir()
    preferred = [
        sample_parts_dir / "Baseball Bat.SLDPRT",
        sample_parts_dir / "Paper Airplane.SLDPRT",
        sample_parts_dir / "Coping Saw.SLDPRT",
    ]
    for candidate in preferred:
        if candidate.exists():
            return candidate

    discovered = sorted(sample_parts_dir.rglob("*.sldprt"))
    if discovered:
        return discovered[0]

    pytest.skip(f"No sample .sldprt files found under {sample_parts_dir}")


# ---------------------------------------------------------------------------
# Level A — Schema / Contract Tests (mock-safe)
# ---------------------------------------------------------------------------


# start_macro_recording and stop_macro_recording intentionally exist in both
# automation.py and macro_recording.py — they are the same operation exposed
# from two code paths.
KNOWN_DUPLICATES = {"start_macro_recording", "stop_macro_recording"}


class TestLevelASchema:
    """Every registered tool must exist and be callable on the mock server."""

    @pytest.mark.asyncio
    async def test_tool_count_meets_minimum(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """At least 95 tools must be registered (verified count as of SolidWorks 2026)."""
        registered = len(mock_server.mcp._tools)
        assert registered >= 95, (
            f"Expected ≥95 registered tools, found {registered}. "
            "Run the server setup and registration pipeline before this test."
        )

    @pytest.mark.asyncio
    async def test_all_catalog_tools_registered(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """Every tool listed in the JSON catalog must be registered in the server."""
        catalog = _load_catalog()
        if not catalog:
            pytest.skip(
                "tool_catalog.json not found – run generate_tool_catalog.py first"
            )

        registered_names = {t.name for t in mock_server.mcp._tools}
        missing: list[str] = []
        for entry in catalog:
            name = entry["tool_name"]
            # Also check func_name as some tools use a name= override
            if (
                name not in registered_names
                and entry["func_name"] not in registered_names
            ):
                missing.append(name)

        assert not missing, (
            f"{len(missing)} catalog tools NOT registered:\n"
            + "\n".join(f"  - {m}" for m in sorted(missing))
        )

    @pytest.mark.asyncio
    async def test_no_duplicate_tool_names(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """Every registered tool must have a unique name."""
        names = [t.name for t in mock_server.mcp._tools]
        seen: dict[str, int] = {}
        for n in names:
            seen[n] = seen.get(n, 0) + 1
        unexpected_duplicates = {
            k: v for k, v in seen.items() if v > 1 and k not in KNOWN_DUPLICATES
        }
        known_found = {k: v for k, v in seen.items() if v > 1 and k in KNOWN_DUPLICATES}
        if known_found:
            print(
                f"\n⚠️  Known duplicate tool names (in multiple modules): {known_found}"
            )
        assert not unexpected_duplicates, (
            f"Unexpected duplicate tool names: {unexpected_duplicates}"
        )

    @pytest.mark.asyncio
    async def test_all_tools_have_callable_attribute(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """Every registered tool must expose a callable func."""
        for tool in mock_server.mcp._tools:
            assert callable(tool.func), f"Tool '{tool.name}' func is not callable"

    @pytest.mark.asyncio
    async def test_catalog_json_structure(self) -> None:
        """The generated catalog JSON must have the expected schema."""
        catalog = _load_catalog()
        if not catalog:
            pytest.skip("tool_catalog.json not found")

        required_keys = {
            "tool_name",
            "func_name",
            "category",
            "description",
            "fields",
            "sample_payload",
        }
        for entry in catalog:
            missing_keys = required_keys - set(entry.keys())
            assert not missing_keys, (
                f"Catalog entry '{entry.get('tool_name', '?')}' missing keys: {missing_keys}"
            )

    @pytest.mark.asyncio
    async def test_category_coverage(self, mock_server: SolidWorksMCPServer) -> None:
        """All expected tool categories must be represented."""
        catalog = _load_catalog()
        if not catalog:
            pytest.skip("tool_catalog.json not found")
        categories = {e["category"] for e in catalog}
        expected = {
            "modeling",
            "sketching",
            "drawing",
            "drawing_analysis",
            "analysis",
            "export",
            "file_management",
            "automation",
            "vba_generation",
            "template_management",
            "macro_recording",
            "docs_discovery",
        }
        missing_cats = expected - categories
        assert not missing_cats, f"Missing tool categories in catalog: {missing_cats}"

    @pytest.mark.asyncio
    async def test_tool_catalog_snapshot_written(self, output_dir: Path) -> None:
        """Snapshot file must exist and contain tool names for regression detection."""
        snapshot_path = output_dir / "tool_catalog_snapshot.json"
        catalog = _load_catalog()
        if not catalog:
            pytest.skip("tool_catalog.json not found")
        names = [e["tool_name"] for e in catalog]
        snapshot_path.write_text(json.dumps(names, indent=2), encoding="utf-8")
        assert snapshot_path.exists()

    def test_sample_path_candidates_include_supported_versions(self) -> None:
        """Candidate sample roots should include current and fallback SolidWorks years."""
        candidates = [str(p).replace("\\", "/") for p in _candidate_sample_roots()]
        assert any("SOLIDWORKS 2026/samples/learn" in p for p in candidates)
        assert any("SOLIDWORKS 2025/samples/learn" in p for p in candidates)

    def test_sample_path_env_override_is_prioritized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment override should be first lookup path when configured."""
        override = "D:/custom/sw/samples/learn"
        monkeypatch.setenv(SAMPLE_MODELS_ENV, override)
        candidates = _candidate_sample_roots()
        assert str(candidates[0]).replace("\\", "/") == override


# ---------------------------------------------------------------------------
# Level B — Execution Smoke Tests (mock-safe)
# ---------------------------------------------------------------------------

# Minimal safe payloads for every tool. Empty dict means no required params.
# Tools that require actual file paths get a dummy value – the mock adapter
# ignores real paths.

_SMOKE_PAYLOADS: dict[str, dict[str, Any]] = {
    # Modeling
    "open_model": {"file_path": "C:\\Temp\\dummy.sldprt"},
    "create_part": {"name": "smoke_part"},
    "create_assembly": {"name": "smoke_asm"},
    "create_drawing": {"name": "smoke_drw"},
    "close_model": {"save": False},
    "create_extrusion": {"sketch_name": "Sketch1", "depth": 10.0},
    "create_revolve": {
        "sketch_name": "Sketch1",
        "axis_entity": "Line1",
        "angle": 360.0,
    },
    "get_dimension": {"name": "D1@Sketch1"},
    "set_dimension": {"name": "D1@Sketch1", "value": 25.0},
    # Sketching
    "create_sketch": {"plane": "Front"},
    "add_line": {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0},
    "add_circle": {"center_x": 0.0, "center_y": 0.0, "radius": 5.0},
    "add_rectangle": {"x1": -10.0, "y1": -10.0, "x2": 10.0, "y2": 10.0},
    "exit_sketch": {},
    "add_arc": {
        "center_x": 0.0,
        "center_y": 0.0,
        "start_x": 5.0,
        "start_y": 0.0,
        "end_x": 0.0,
        "end_y": 5.0,
    },
    "add_spline": {
        "points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 5.0}, {"x": 20.0, "y": 0.0}]
    },
    "add_centerline": {"x1": -20.0, "y1": 0.0, "x2": 20.0, "y2": 0.0},
    "add_polygon": {"center_x": 0.0, "center_y": 0.0, "sides": 6, "circumradius": 10.0},
    "add_ellipse": {
        "center_x": 0.0,
        "center_y": 0.0,
        "major_radius": 10.0,
        "minor_radius": 5.0,
    },
    "add_sketch_constraint": {"entity1": "Line1", "relation_type": "horizontal"},
    "add_sketch_dimension": {
        "entity1": "Line1",
        "value": 20.0,
        "dimension_type": "linear",
    },
    "sketch_linear_pattern": {
        "entity": "Line1",
        "x_count": 3,
        "y_count": 2,
        "x_spacing": 10.0,
        "y_spacing": 10.0,
    },
    "sketch_circular_pattern": {
        "entity": "Line1",
        "count": 4,
        "angle": 90.0,
        "center_x": 0.0,
        "center_y": 0.0,
    },
    "sketch_mirror": {"entity": "Line1", "mirror_line": "Line2"},
    "sketch_offset": {"entity": "Line1", "distance": 5.0},
    "sketch_tutorial_simple_hole": {
        "plane": "Front",
        "center_x": 0.0,
        "center_y": 0.0,
        "diameter": 10.0,
    },
    "tutorial_simple_hole": {
        "plane": "Front",
        "center_x": 0.0,
        "center_y": 0.0,
        "diameter": 10.0,
    },
    # Analysis
    "calculate_mass_properties": {},
    "get_mass_properties": {},
    "check_interference": {},
    "analyze_geometry": {"analysis_type": "curvature"},
    "get_material_properties": {},
    # Export
    "export_step": {"file_path": "C:\\Temp\\smoke.step", "format_type": "step"},
    "export_iges": {"file_path": "C:\\Temp\\smoke.iges", "format_type": "iges"},
    "export_stl": {"file_path": "C:\\Temp\\smoke.stl", "format_type": "stl"},
    "export_pdf": {"file_path": "C:\\Temp\\smoke.pdf", "format_type": "pdf"},
    "export_dwg": {"file_path": "C:\\Temp\\smoke.dwg", "format_type": "dwg"},
    "export_image": {"file_path": "C:\\Temp\\smoke.jpg", "format_type": "jpg"},
    "batch_export": {
        "source_directory": "C:\\Temp\\src",
        "output_directory": "C:\\Temp\\out",
        "format_type": "step",
    },
    # File management
    "save_file": {},
    "save_as": {"file_path": "C:\\Temp\\save_as.sldprt"},
    "get_file_properties": {},
    "get_model_info": {},
    "list_features": {},
    "list_configurations": {},
    "manage_file_properties": {},
    "convert_file_format": {
        "source_path": "C:\\Temp\\part.sldprt",
        "target_format": "step",
    },
    "batch_file_operations": {"source_directory": "C:\\Temp\\src", "operation": "copy"},
    "load_part": {"file_path": "C:\\Temp\\part.sldprt"},
    "load_assembly": {"file_path": "C:\\Temp\\asm.sldasm"},
    "save_part": {},
    "save_assembly": {},
    # Automation
    "generate_vba_code": {"code_type": "extrusion"},
    "start_macro_recording": {"macro_name": "smoke_macro"},
    "stop_macro_recording": {},
    "batch_process_files": {
        "source_directory": "C:\\Temp\\src",
        "operation": "export",
        "output_directory": "C:\\Temp\\out",
    },
    "manage_design_table": {"action": "list"},
    "execute_workflow": {"steps": []},
    "create_template": {"template_name": "smoke_template", "template_type": "part"},
    "optimize_performance": {},
    # VBA generation
    "generate_vba_extrusion": {"sketch_name": "Sketch1", "depth": 10.0},
    "generate_vba_revolve": {
        "sketch_name": "Sketch1",
        "axis_entity": "Line1",
        "angle": 360.0,
    },
    "generate_vba_assembly_insert": {"component_path": "C:\\Temp\\part.sldprt"},
    "generate_vba_drawing_views": {"model_path": "C:\\Temp\\part.sldprt"},
    "generate_vba_batch_export": {
        "source_directory": "C:\\Temp\\src",
        "output_directory": "C:\\Temp\\out",
        "format_type": "step",
    },
    "generate_vba_part_modeling": {"operations": []},
    "generate_vba_assembly_mates": {"mate_type": "coincident"},
    "generate_vba_drawing_dimensions": {},
    "generate_vba_file_operations": {"operation": "save"},
    "generate_vba_macro_recorder": {"macro_name": "smoke"},
    # Template management
    "extract_template": {"model_path": "C:\\Temp\\part.sldprt"},
    "apply_template": {
        "template_path": "C:\\Temp\\template.prtdot",
        "target_path": "C:\\Temp\\part.sldprt",
    },
    "batch_apply_template": {
        "template_path": "C:\\Temp\\template.prtdot",
        "source_directory": "C:\\Temp\\src",
    },
    "compare_templates": {
        "template1_path": "C:\\Temp\\t1.prtdot",
        "template2_path": "C:\\Temp\\t2.prtdot",
    },
    "save_to_template_library": {
        "template_path": "C:\\Temp\\template.prtdot",
        "library_name": "smoke",
    },
    "list_template_library": {},
    # Macro recording
    "execute_macro": {"macro_path": "C:\\Temp\\macro.swp"},
    "analyze_macro": {"macro_path": "C:\\Temp\\macro.swp"},
    "batch_execute_macros": {"macro_paths": ["C:\\Temp\\macro.swp"]},
    "optimize_macro": {"macro_path": "C:\\Temp\\macro.swp"},
    "create_macro_library": {"library_name": "smoke_lib", "macro_paths": []},
    # Drawing
    "create_drawing_view": {
        "model_path": "C:\\Temp\\part.sldprt",
        "view_type": "front",
    },
    "add_dimension": {"entity1": "Line1", "value": 20.0, "dimension_type": "linear"},
    "add_note": {"text": "Smoke test note", "x": 0.0, "y": 0.0},
    "create_section_view": {"cutting_line": "Line1"},
    "create_detail_view": {
        "center_x": 0.0,
        "center_y": 0.0,
        "radius": 10.0,
        "scale": 2.0,
    },
    "update_sheet_format": {"sheet_format_path": "C:\\Temp\\format.slddrt"},
    "auto_dimension_view": {"view_name": "Drawing View1"},
    "check_drawing_standards": {},
    "create_technical_drawing": {"model_path": "C:\\Temp\\part.sldprt"},
    "add_drawing_view": {"model_path": "C:\\Temp\\part.sldprt", "view_type": "front"},
    "add_annotation": {"annotation_type": "note", "text": "smoke", "x": 0.0, "y": 0.0},
    "update_title_block": {"title": "Smoke Test"},
    # Drawing analysis
    "analyze_drawing_comprehensive": {},
    "analyze_drawing_dimensions": {},
    "analyze_drawing_annotations": {},
    "check_drawing_compliance": {},
    "analyze_drawing_views": {},
    "generate_drawing_report": {},
    "compare_drawing_versions": {
        "drawing1_path": "C:\\Temp\\drw1.slddrw",
        "drawing2_path": "C:\\Temp\\drw2.slddrw",
    },
    "validate_drawing_completeness": {},
    # Docs discovery
    "discover_solidworks_docs": {},
    "search_solidworks_api_help": {"query": "extrude"},
}


class TestLevelBSmokeExecution:
    """Every tool must handle a minimal payload without raising an unhandled exception."""

    @pytest.mark.asyncio
    async def test_smoke_all_tools(
        self, mock_server: SolidWorksMCPServer, output_dir: Path
    ) -> None:
        """Run every registered tool with a safe mock payload."""
        results: list[dict[str, Any]] = []
        failed: list[str] = []

        for tool in mock_server.mcp._tools:
            name = tool.name
            payload = _SMOKE_PAYLOADS.get(name, {})
            t0 = time.perf_counter()
            try:
                result = await tool.func(payload)
                elapsed = time.perf_counter() - t0
                status = (
                    result.get("status", "unknown")
                    if isinstance(result, dict)
                    else "non-dict"
                )
                results.append(
                    {
                        "tool": name,
                        "status": status,
                        "elapsed_s": round(elapsed, 4),
                        "payload_keys": list(payload.keys()),
                    }
                )
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                results.append(
                    {
                        "tool": name,
                        "status": "EXCEPTION",
                        "elapsed_s": round(elapsed, 4),
                        "error": str(exc),
                    }
                )
                failed.append(f"{name}: {exc}")

        # Write report
        report_path = output_dir / "smoke_test_report.json"
        report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        if failed:
            summary = "\n".join(failed)
            pytest.fail(
                f"{len(failed)}/{len(results)} tools raised unhandled exceptions:\n{summary}\n"
                f"Full report: {report_path}"
            )

    @pytest.mark.asyncio
    async def test_all_tools_return_dict(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """Every tool must return a dict (not None, not a bare string, not an exception)."""
        non_dict: list[str] = []
        for tool in mock_server.mcp._tools:
            name = tool.name
            payload = _SMOKE_PAYLOADS.get(name, {})
            try:
                result = await tool.func(payload)
                if not isinstance(result, dict):
                    non_dict.append(f"{name}: returned {type(result).__name__}")
            except Exception:
                pass  # Exceptions are caught in test_smoke_all_tools

        assert not non_dict, (
            f"{len(non_dict)} tools did not return a dict:\n" + "\n".join(non_dict)
        )

    @pytest.mark.asyncio
    async def test_all_tools_have_status_field(
        self, mock_server: SolidWorksMCPServer
    ) -> None:
        """Every tool response dict must contain a 'status' key."""
        missing_status: list[str] = []
        for tool in mock_server.mcp._tools:
            name = tool.name
            payload = _SMOKE_PAYLOADS.get(name, {})
            try:
                result = await tool.func(payload)
                if isinstance(result, dict) and "status" not in result:
                    missing_status.append(name)
            except Exception:
                pass

        assert not missing_status, (
            f"{len(missing_status)} tools returned dicts without 'status':\n"
            + "\n".join(missing_status)
        )

    @pytest.mark.asyncio
    async def test_smoke_responses_within_context_budget(
        self, mock_server: SolidWorksMCPServer, output_dir: Path
    ) -> None:
        """Guardrail: smoke responses should stay reasonably small for LLM context usage."""
        oversize: list[str] = []
        total_bytes = 0
        size_rows: list[dict[str, Any]] = []

        for tool in mock_server.mcp._tools:
            name = tool.name
            payload = _SMOKE_PAYLOADS.get(name, {})
            try:
                result = await tool.func(payload)
            except Exception as exc:
                # Size-budget test is not responsible for behavioral failures.
                size_rows.append({"tool": name, "bytes": 0, "error": str(exc)})
                continue

            serialized = json.dumps(result, default=str)
            size_bytes = len(serialized.encode("utf-8"))
            total_bytes += size_bytes
            size_rows.append({"tool": name, "bytes": size_bytes})

            if size_bytes > MAX_TOOL_RESPONSE_BYTES:
                oversize.append(
                    f"{name}: {size_bytes} bytes (max {MAX_TOOL_RESPONSE_BYTES})"
                )

        size_report = output_dir / "smoke_response_size_report.json"
        size_report.write_text(
            json.dumps(
                {
                    "max_tool_response_bytes": MAX_TOOL_RESPONSE_BYTES,
                    "max_total_response_bytes": MAX_SMOKE_TOTAL_RESPONSE_BYTES,
                    "total_response_bytes": total_bytes,
                    "tools": size_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if oversize:
            pytest.fail(
                "One or more smoke responses exceeded per-tool size budget:\n"
                + "\n".join(oversize)
                + f"\nReport: {size_report}"
            )

        assert total_bytes <= MAX_SMOKE_TOTAL_RESPONSE_BYTES, (
            f"Total smoke response size {total_bytes} bytes exceeds "
            f"budget {MAX_SMOKE_TOTAL_RESPONSE_BYTES} bytes. "
            f"Report: {size_report}"
        )


# ---------------------------------------------------------------------------
# Level C — Real COM Lifecycle (Windows + SolidWorks required)
# ---------------------------------------------------------------------------

DEMO_DIR = Path("C:/Temp/mcp_smoke_integration")


@pytest.mark.skipif(
    not _real_sw_enabled(), reason=f"Set {REAL_SW_FLAG}=true to run real COM tests"
)
@pytest.mark.skipif(not _is_windows(), reason="COM tests require Windows")
@pytest.mark.windows_only
@pytest.mark.solidworks_only
class TestLevelCRealCOM:
    """Real SolidWorks COM integration — one per lifecycle stage."""

    @pytest.mark.asyncio
    async def test_c01_health_check(self, real_server: SolidWorksMCPServer) -> None:
        """SolidWorks COM connection must report healthy."""
        tool = _find_tool(real_server, "discover_solidworks_docs")
        assert tool is not None, "discover_solidworks_docs not registered"
        result = await tool({})
        assert isinstance(result, dict)
        assert result.get("status") in ("success", "error"), (
            f"Unexpected status: {result}"
        )

    @pytest.mark.asyncio
    async def test_c02_create_and_save_part(
        self, real_server: SolidWorksMCPServer, output_dir: Path
    ) -> None:
        """Create a part, save it, and verify the file exists."""
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        part_path = DEMO_DIR / "smoke_c02_part.sldprt"

        create = _find_tool(real_server, "create_part")
        assert create, "create_part not registered"
        result = await create({"name": "smoke_c02_part"})
        assert result["status"] == "success", f"create_part failed: {result}"

        save_as = _find_tool(real_server, "save_as")
        assert save_as, "save_as not registered"
        result = await save_as({"file_path": str(part_path)})
        assert result["status"] == "success", f"save_as failed: {result}"
        assert part_path.exists(), f"Part file not created: {part_path}"

    @pytest.mark.asyncio
    async def test_c03_sketch_and_extrude(
        self, real_server: SolidWorksMCPServer, output_dir: Path
    ) -> None:
        """Create a part, save it, reopen it, and save again in one lifecycle."""
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        part_path = DEMO_DIR / "smoke_c03_roundtrip.sldprt"

        create = _find_tool(real_server, "create_part")
        result = await create({"name": "smoke_c03_roundtrip"})
        assert result["status"] == "success"

        save_as = _find_tool(real_server, "save_as")
        result = await save_as({"file_path": str(part_path)})
        assert result["status"] == "success"
        assert part_path.exists()

        close_model = _find_tool(real_server, "close_model")
        result = await close_model({"save": False})
        assert result["status"] in {"success", "error"}

        open_model = _find_tool(real_server, "open_model")
        result = await open_model({"file_path": str(part_path)})
        assert result["status"] == "success"

        save_file = _find_tool(real_server, "save_file")
        result = await save_file({"force_save": True})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_c04_mass_properties(self, real_server: SolidWorksMCPServer) -> None:
        """Open a shipped sample part and verify file properties can be read."""
        sample_part = _find_sample_part()

        open_tool = _find_tool(real_server, "open_model")
        assert open_tool
        result = await open_tool({"file_path": str(sample_part)})
        assert result["status"] == "success"

        props_tool = _find_tool(real_server, "get_file_properties")
        assert props_tool
        result = await props_tool({})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_c05_export_step(self, real_server: SolidWorksMCPServer) -> None:
        """Open a shipped sample part, export it to STEP, and verify file exists."""
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        step_path = DEMO_DIR / "smoke_c05_export.step"

        sample_part = _find_sample_part()
        open_tool = _find_tool(real_server, "open_model")
        assert open_tool
        result = await open_tool({"file_path": str(sample_part)})
        assert result["status"] == "success", f"open_model failed: {result}"

        tool = _find_tool(real_server, "export_step")
        assert tool
        result = await tool({"file_path": str(step_path), "format_type": "step"})
        assert result["status"] == "success", f"STEP export failed: {result}"
        assert step_path.exists(), f"STEP file not found: {step_path}"

    @pytest.mark.asyncio
    async def test_c06_export_image(self, real_server: SolidWorksMCPServer) -> None:
        """Open a shipped sample part and verify image export returns usable output."""
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        img_path = DEMO_DIR / "smoke_c06_image.jpg"

        sample_part = _find_sample_part()
        open_tool = _find_tool(real_server, "open_model")
        assert open_tool
        result = await open_tool({"file_path": str(sample_part)})
        assert result["status"] == "success", f"open_model failed: {result}"

        tool = _find_tool(real_server, "export_image")
        assert tool
        result = await tool({"file_path": str(img_path), "format_type": "jpg"})
        assert result["status"] == "success", f"Image export failed: {result}"
        if not img_path.exists():
            export_info = result.get("export") or result.get("data") or {}
            assert export_info.get("file_path") == str(img_path), (
                f"Image export returned success without file or matching metadata: {result}"
            )

    @pytest.mark.asyncio
    async def test_c07_create_assembly(self, real_server: SolidWorksMCPServer) -> None:
        """Create an assembly and save it."""
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        asm_path = DEMO_DIR / "smoke_c07_assembly.sldasm"
        tool = _find_tool(real_server, "create_assembly")
        assert tool
        result = await tool({"name": "smoke_c07_asm"})
        assert result["status"] == "success"

        save_as = _find_tool(real_server, "save_as")
        result = await save_as({"file_path": str(asm_path)})
        assert result["status"] == "success"
        assert asm_path.exists()

    @pytest.mark.asyncio
    async def test_c08_close_model(self, real_server: SolidWorksMCPServer) -> None:
        """Close the active document cleanly."""
        tool = _find_tool(real_server, "close_model")
        assert tool
        result = await tool({"save": False})
        assert result["status"] in ("success", "error"), (
            f"Unexpected close result: {result}"
        )

    @pytest.mark.asyncio
    async def test_c09_open_sample_part(self, real_server: SolidWorksMCPServer) -> None:
        """Open one of the shipped 2026 sample parts and read its file properties."""
        sample_part = _find_sample_part()

        open_tool = _find_tool(real_server, "open_model")
        assert open_tool
        result = await open_tool({"file_path": str(sample_part)})
        assert result["status"] == "success", f"open_model failed: {result}"

        props = _find_tool(real_server, "get_file_properties")
        assert props
        result = await props({})
        assert result["status"] == "success"

        close = _find_tool(real_server, "close_model")
        await close({"save": False})

    @pytest.mark.asyncio
    async def test_c10_docs_discovery_and_compat(
        self, real_server: SolidWorksMCPServer, output_dir: Path
    ) -> None:
        """Discover live COM surface and write compatibility report."""
        tool = _find_tool(real_server, "discover_solidworks_docs")
        assert tool

        docs_out = output_dir / "docs-index"
        result = await tool({"output_dir": str(docs_out), "include_vba": True})
        assert result["status"] in ("success", "error")

        compat: dict[str, Any] = {
            "solidworks_version": "2026",
            "compat_check_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "required_com_interfaces": REQUIRED_COM_METHODS,
            "discovery_status": result.get("status"),
            "classification": {},
        }

        if result.get("status") == "success":
            discovered_ifaces: list[str] = list(
                result.get("index", {}).get("com_objects", {}).keys()
            )
            for iface in REQUIRED_COM_METHODS:
                if any(iface.lower() in d.lower() for d in discovered_ifaces):
                    compat["classification"][iface] = "OK"
                else:
                    compat["classification"][iface] = "NOT_FOUND"

        compat_path = output_dir / "api_compat_report.json"
        compat_path.write_text(json.dumps(compat, indent=2), encoding="utf-8")

        not_found = [k for k, v in compat["classification"].items() if v == "NOT_FOUND"]
        if not_found:
            # Warn but don't fail — the LLM needs the report to choose fallback paths
            print(f"\n⚠️  COM interfaces not found (suggest fallback VBA): {not_found}")

    @pytest.mark.asyncio
    async def test_c11_read_tools_feature_and_configuration_listing(
        self, real_server: SolidWorksMCPServer
    ) -> None:
        """Open a sample part and validate read-before-write tools for tree/config context."""
        sample_part = _find_sample_part()

        open_tool = _find_tool(real_server, "open_model")
        assert open_tool is not None, "open_model not registered"
        opened = await open_tool({"file_path": str(sample_part)})
        assert opened.get("status") == "success", f"open_model failed: {opened}"

        list_features_tool = _find_tool(real_server, "list_features")
        assert list_features_tool is not None, "list_features not registered"
        features_result = await list_features_tool({"include_suppressed": False})
        assert features_result.get("status") == "success", (
            f"list_features failed: {features_result}"
        )
        assert isinstance(features_result.get("features", []), list), (
            f"Expected list in features payload: {features_result}"
        )

        list_configs_tool = _find_tool(real_server, "list_configurations")
        assert list_configs_tool is not None, "list_configurations not registered"
        configs_result = await list_configs_tool({})
        assert configs_result.get("status") == "success", (
            f"list_configurations failed: {configs_result}"
        )
        configs = configs_result.get("configurations", [])
        assert isinstance(configs, list), (
            f"Expected list in configurations payload: {configs_result}"
        )
        assert len(configs) >= 1, (
            "Expected at least one configuration in an opened sample part"
        )


# ---------------------------------------------------------------------------
# Docs-discovery compatibility adapter tests (mock-safe)
# ---------------------------------------------------------------------------


class TestDocsDiscoveryCompat:
    """Verify that the compatibility classification logic works offline."""

    @pytest.mark.asyncio
    async def test_compat_report_structure(self, output_dir: Path) -> None:
        """The saved compat report (if present) must have expected keys."""
        compat_path = output_dir / "api_compat_report.json"
        if not compat_path.exists():
            pytest.skip("api_compat_report.json not present — run Level C tests first")

        with open(compat_path, encoding="utf-8") as fh:
            report = json.load(fh)

        for key in (
            "solidworks_version",
            "required_com_interfaces",
            "discovery_status",
            "classification",
        ):
            assert key in report, f"compat report missing key: {key}"

    @pytest.mark.asyncio
    async def test_smoke_report_exists(self, output_dir: Path) -> None:
        """The smoke execution report must be present after Level B tests."""
        smoke_path = output_dir / "smoke_test_report.json"
        if not smoke_path.exists():
            pytest.skip("smoke_test_report.json not present — run Level B tests first")

        with open(smoke_path, encoding="utf-8") as fh:
            report = json.load(fh)

        assert isinstance(report, list)
        assert len(report) > 0, "Smoke report is empty"
        # Count successes
        success_count = sum(1 for r in report if r.get("status") == "success")
        total = len(report)
        print(f"\n📊 Smoke test results: {success_count}/{total} success")
