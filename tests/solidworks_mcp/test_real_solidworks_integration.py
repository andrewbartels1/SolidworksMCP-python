"""Real SolidWorks integration smoke tests."""

from __future__ import annotations

import json
import os
import platform
from collections import Counter
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.tools.file_management import SaveAsInput, SaveFileInput
from solidworks_mcp.tools.modeling import (
    CloseModelInput,
    CreateAssemblyInput,
    CreatePartInput,
    OpenModelInput,
)

REAL_SW_ENV_FLAG = "SOLIDWORKS_MCP_RUN_REAL_INTEGRATION"


def _real_solidworks_enabled() -> bool:
    """Test helper for real solidworks enabled."""
    value = os.getenv(REAL_SW_ENV_FLAG, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


async def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    """Test helper for find tool."""
    for tool in await server.mcp.list_tools():
        if tool.name == tool_name:
            return tool.fn
    raise AssertionError(f"Tool '{tool_name}' not found")


async def _tool_names(server: SolidWorksMCPServer) -> list[str]:
    """Test helper for tool names."""
    return sorted(tool.name for tool in await server.mcp.list_tools())


@pytest_asyncio.fixture
async def real_server() -> AsyncGenerator[SolidWorksMCPServer, None]:
    """Test helper for real server."""
    if platform.system() != "Windows":
        pytest.skip("Real SolidWorks integration tests require Windows")

    if not _real_solidworks_enabled():
        pytest.skip(
            f"Set {REAL_SW_ENV_FLAG}=true to run real SolidWorks integration tests"
        )

    config = SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        adapter_type=AdapterType.PYWIN32,
        mock_solidworks=False,
        testing=False,
        debug=True,
        enable_windows_validation=False,
    )

    server = SolidWorksMCPServer(config)
    await server.setup()

    try:
        await server.adapter.connect()
    except Exception as exc:
        await server.stop()
        pytest.skip(f"Could not connect to local SolidWorks instance: {exc}")

    try:
        yield server
    finally:
        # Close only documents that were opened/created during this test session.
        # Unwrap circuit-breaker/pool wrappers to reach the pywin32 adapter directly.
        underlying = server.adapter
        while hasattr(underlying, "adapter"):
            underlying = underlying.adapter
        if hasattr(underlying, "close_all_session_docs"):
            try:
                await underlying.close_all_session_docs()
            except Exception:
                pass
        else:
            # Fallback: close only the current active model
            close_tool = await _find_tool(server, "close_model")
            try:
                await close_tool(CloseModelInput(save=False))
            except Exception:
                pass
        await server.stop()


@pytest.fixture
def integration_output_dir() -> Path:
    """Test helper for integration output dir."""
    output_dir = Path("tests") / ".generated" / "solidworks_integration"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_registered_tool_catalog_snapshot(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Verify tool catalog coverage and persist a local snapshot for auditing."""
    tool_names = await _tool_names(real_server)
    duplicate_counts = {
        name: count for name, count in Counter(tool_names).items() if count > 1
    }
    allowed_duplicate_counts: dict[str, int] = {
        # No intentional duplicate tool names are expected.
    }

    assert duplicate_counts == allowed_duplicate_counts, (
        f"Unexpected duplicate tool names: {duplicate_counts}"
    )

    unique_tool_names = set(tool_names)
    assert len(tool_names) >= 77, f"Expected at least 77 tools, got {len(tool_names)}"

    expected_core_tools = {
        # Modeling / file lifecycle
        "create_part",
        "create_assembly",
        "create_drawing",
        "open_model",
        "close_model",
        "save_file",
        "save_as",
        # Sketching
        "create_sketch",
        "add_circle",
        "exit_sketch",
        # Analysis / export
        "get_mass_properties",
        "check_interference",
        "export_step",
        # Automation / templates / macros / drawing analysis
        "batch_process_files",
        "generate_vba_extrusion",
        "extract_template",
        "start_macro_recording",
        "analyze_drawing_comprehensive",
    }

    missing = sorted(expected_core_tools.difference(unique_tool_names))
    assert not missing, f"Missing expected tools: {missing}"

    snapshot_path = integration_output_dir / "tool_catalog_snapshot.json"
    snapshot = {
        "tool_count": len(tool_names),
        "tools": tool_names,
    }
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    assert snapshot_path.exists(), f"Expected snapshot file at {snapshot_path}"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_solidworks_connection_health(
    real_server: SolidWorksMCPServer,
) -> None:
    """Verify that we can connect to and query a real SolidWorks session."""
    assert real_server.adapter.is_connected()

    health = await real_server.health_check()
    assert health["status"] in {"healthy", "warning"}
    assert health["adapter"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_part_create_save_open_close(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Create a part, save it, reopen it, and save again via real tools."""
    create_part = await _find_tool(real_server, "create_part")
    save_as = await _find_tool(real_server, "save_as")
    open_model = await _find_tool(real_server, "open_model")
    save_file = await _find_tool(real_server, "save_file")
    close_model = await _find_tool(real_server, "close_model")

    part_result = await create_part(CreatePartInput(name="MCP_Integration_Part"))
    assert part_result["status"] == "success", part_result

    part_path = integration_output_dir / "mcp_integration_part.sldprt"
    save_as_result = await save_as(
        SaveAsInput(
            file_path=str(part_path),
            format_type="solidworks",
            overwrite=True,
        )
    )
    assert save_as_result["status"] == "success", save_as_result
    assert part_path.exists(), f"Expected saved part at {part_path}"

    close_result = await close_model(CloseModelInput(save=False))
    assert close_result["status"] in {"success", "error"}

    open_result = await open_model(OpenModelInput(file_path=str(part_path)))
    assert open_result["status"] == "success", open_result

    save_result = await save_file(SaveFileInput(force_save=True))
    assert save_result["status"] == "success", save_result

    final_close = await close_model(CloseModelInput(save=True))
    assert final_close["status"] in {"success", "error"}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_assembly_create_and_save(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Create and save a real SolidWorks assembly document."""
    create_assembly = await _find_tool(real_server, "create_assembly")
    save_as = await _find_tool(real_server, "save_as")
    close_model = await _find_tool(real_server, "close_model")

    assembly_result = await create_assembly(
        CreateAssemblyInput(name="MCP_Integration_Assembly")
    )
    assert assembly_result["status"] == "success", assembly_result

    asm_path = integration_output_dir / "mcp_integration_assembly.sldasm"
    save_as_result = await save_as(
        SaveAsInput(
            file_path=str(asm_path),
            format_type="solidworks",
            overwrite=True,
        )
    )
    assert save_as_result["status"] == "success", save_as_result
    assert asm_path.exists(), f"Expected saved assembly at {asm_path}"

    close_result = await close_model(CloseModelInput(save=False))
    assert close_result["status"] in {"success", "error"}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_cross_category_minimal_smoke(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Run a deterministic low-risk workflow touching multiple tool categories."""
    create_part = await _find_tool(real_server, "create_part")
    save_as = await _find_tool(real_server, "save_as")
    open_model = await _find_tool(real_server, "open_model")
    save_file = await _find_tool(real_server, "save_file")
    close_model = await _find_tool(real_server, "close_model")

    part_result = await create_part(CreatePartInput(name="MCP_CrossCategory_Smoke"))
    assert part_result["status"] == "success", part_result

    smoke_part_path = integration_output_dir / "mcp_cross_category_smoke.sldprt"
    save_as_result = await save_as(
        SaveAsInput(
            file_path=str(smoke_part_path),
            format_type="solidworks",
            overwrite=True,
        )
    )
    assert save_as_result["status"] == "success", save_as_result
    assert smoke_part_path.exists(), f"Expected saved part at {smoke_part_path}"

    close_intermediate = await close_model(CloseModelInput(save=False))
    assert close_intermediate["status"] in {"success", "error"}

    reopen_result = await open_model(OpenModelInput(file_path=str(smoke_part_path)))
    assert reopen_result["status"] == "success", reopen_result

    save_result = await save_file(SaveFileInput(force_save=True))
    assert save_result["status"] == "success", save_result

    close_result = await close_model(CloseModelInput(save=True))
    assert close_result["status"] in {"success", "error"}


@pytest.mark.skipif(
    not _real_solidworks_enabled(),
    reason="Real SolidWorks integration disabled (set SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true)",
)
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_load_save_lifecycle(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Test comprehensive load/save/open lifecycle with real SolidWorks."""
    create_part = await _find_tool(real_server, "create_part")
    save_part = await _find_tool(real_server, "save_part")
    load_part = await _find_tool(real_server, "load_part")
    close_model = await _find_tool(real_server, "close_model")

    # Step 1: Create a new part
    part_result = await create_part(CreatePartInput(name="MCP_LoadSave_Lifecycle"))
    assert part_result["status"] == "success", part_result

    # Step 2: Save the part using save_part convenience tool
    lifecycle_part_path = integration_output_dir / "mcp_load_save_lifecycle.sldprt"
    save_result = await save_part(
        {
            "file_path": str(lifecycle_part_path),
            "overwrite": True,
        }
    )
    assert save_result["status"] == "success", save_result
    assert lifecycle_part_path.exists(), f"Expected saved part at {lifecycle_part_path}"

    # Step 3: Close the part
    close_result = await close_model(CloseModelInput(save=False))
    assert close_result["status"] in {"success", "error"}

    # Step 4: Verify the file exists and load it using load_part convenience tool
    assert lifecycle_part_path.exists(), (
        f"Part file should exist at {lifecycle_part_path}"
    )
    load_result = await load_part({"file_path": str(lifecycle_part_path)})
    assert load_result["status"] == "success", load_result
    assert load_result["model"]["type"] == "Part", "Loaded model should be a Part"
    assert load_result["model"]["name"] is not None, "Model should have a name"

    # Step 5: Save again using save_part (without path, should save to current location)
    save_again_result = await save_part({})
    assert save_again_result["status"] == "success", save_again_result

    # Step 6: Close the reloaded part
    close_final_result = await close_model(CloseModelInput(save=True))
    assert close_final_result["status"] in {"success", "error"}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.windows_only
@pytest.mark.solidworks_only
async def test_real_arc_measurements_smoke(
    real_server: SolidWorksMCPServer,
    integration_output_dir: Path,
) -> None:
    """Smoke test: create a sketch with arcs/circles and dimension them without dialog.

    Covers radial dimensions on arcs and circles.  The preference toggle
    swInputDimValOnCreate (62) must remain False for the full dimension
    operation (including SetSystemValue3) so the Modify dialog never appears.

    This test intentionally relies on the popup-safe adapter path: direct COM
    dimension creation with minimal extra COM chatter.  Regressions here tend
    to come from reintroducing AddDimension2 probing or non-essential cleanup
    calls around dimension creation/teardown.
    """
    create_part = await _find_tool(real_server, "create_part")
    save_as = await _find_tool(real_server, "save_as")
    create_sketch = await _find_tool(real_server, "create_sketch")
    add_circle = await _find_tool(real_server, "add_circle")
    add_arc = await _find_tool(real_server, "add_arc")
    add_sketch_dimension = await _find_tool(real_server, "add_sketch_dimension")
    exit_sketch = await _find_tool(real_server, "exit_sketch")
    close_model = await _find_tool(real_server, "close_model")

    # Create a fresh part
    part_result = await create_part(CreatePartInput(name="MCP_ArcMeasurements_Smoke"))
    assert part_result["status"] == "success", part_result

    # Open a sketch on the Front plane
    sketch_result = await create_sketch({"plane": "Front"})
    assert sketch_result["status"] == "success", sketch_result

    # Add a circle (radius 20 mm, centred at origin)
    circle_result = await add_circle({"center_x": 0.0, "center_y": 0.0, "radius": 20.0})
    assert circle_result["status"] == "success", circle_result
    circle_entity = circle_result["circle"]["id"]

    # Add a 90-degree arc (quarter circle, radius 15 mm)
    # Start at (15, 0), end at (0, 15), centre at origin
    arc_result = await add_arc(
        {
            "center_x": 0.0,
            "center_y": 0.0,
            "start_x": 15.0,
            "start_y": 0.0,
            "end_x": 0.0,
            "end_y": 15.0,
        }
    )
    assert arc_result["status"] == "success", arc_result
    arc_entity = arc_result["arc"]["id"]

    # Dimension the circle radius (radial)
    circle_dim_result = await add_sketch_dimension(
        {
            "entity1": circle_entity,
            "dimension_type": "radial",
            "value": 20.0,
        }
    )
    assert circle_dim_result["status"] == "success", (
        f"Circle radial dimension failed: {circle_dim_result}"
    )
    assert circle_dim_result.get("dimension") is not None, (
        "Circle radial dimension returned no data"
    )

    # Dimension the arc radius (radial)
    arc_dim_result = await add_sketch_dimension(
        {
            "entity1": arc_entity,
            "dimension_type": "radial",
            "value": 15.0,
        }
    )
    assert arc_dim_result["status"] == "success", (
        f"Arc radial dimension failed: {arc_dim_result}"
    )
    assert arc_dim_result.get("dimension") is not None, (
        "Arc radial dimension returned no data"
    )

    # Exit sketch
    exit_result = await exit_sketch()
    assert exit_result["status"] == "success", exit_result

    # Save and close
    part_path = integration_output_dir / "mcp_arc_measurements_smoke.sldprt"
    save_as_result = await save_as(
        SaveAsInput(file_path=str(part_path), format_type="solidworks", overwrite=True)
    )
    assert save_as_result["status"] == "success", save_as_result

    close_result = await close_model(CloseModelInput(save=False))
    assert close_result["status"] in {"success", "error"}
