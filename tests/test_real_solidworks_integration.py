"""Real SolidWorks integration smoke tests.

These tests intentionally connect to a real local SolidWorks installation through
pywin32. They are disabled by default and only run when explicitly enabled.
"""

from __future__ import annotations

import json
import os
import platform
from collections import Counter
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from src.solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from src.solidworks_mcp.server import SolidWorksMCPServer
from src.solidworks_mcp.tools.file_management import SaveAsInput, SaveFileInput
from src.solidworks_mcp.tools.modeling import (
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


def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    """Test helper for find tool."""
    for tool in server.mcp._tools:
        if tool.name == tool_name:
            return tool.func
    raise AssertionError(f"Tool '{tool_name}' not found")


def _tool_names(server: SolidWorksMCPServer) -> list[str]:
    """Test helper for tool names."""
    return sorted(tool.name for tool in server.mcp._tools)


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
            close_tool = _find_tool(server, "close_model")
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
    tool_names = _tool_names(real_server)
    duplicate_counts = {
        name: count for name, count in Counter(tool_names).items() if count > 1
    }
    allowed_duplicate_counts = {
        # Intentional aliases registered from different tool categories.
        "start_macro_recording": 2,
        "stop_macro_recording": 2,
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
    create_part = _find_tool(real_server, "create_part")
    save_as = _find_tool(real_server, "save_as")
    open_model = _find_tool(real_server, "open_model")
    save_file = _find_tool(real_server, "save_file")
    close_model = _find_tool(real_server, "close_model")

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
    create_assembly = _find_tool(real_server, "create_assembly")
    save_as = _find_tool(real_server, "save_as")
    close_model = _find_tool(real_server, "close_model")

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
    create_part = _find_tool(real_server, "create_part")
    save_as = _find_tool(real_server, "save_as")
    open_model = _find_tool(real_server, "open_model")
    save_file = _find_tool(real_server, "save_file")
    close_model = _find_tool(real_server, "close_model")

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
    """Test comprehensive load/save/open lifecycle with real SolidWorks.

    Validates the full document lifecycle:
    1. Create a part
    2. Save the part
    3. Close the part
    4. Load the part using load_part convenience tool
    5. Verify the document is open
    6. Save again using save_part convenience tool
    7. Close the document

    This test ensures that newly added convenience tools (load_part, save_part)
    integrate properly with the existing SolidWorks CAD workflow.
    """
    create_part = _find_tool(real_server, "create_part")
    save_part = _find_tool(real_server, "save_part")
    load_part = _find_tool(real_server, "load_part")
    close_model = _find_tool(real_server, "close_model")

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
