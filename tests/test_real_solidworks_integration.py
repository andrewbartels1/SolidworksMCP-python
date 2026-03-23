"""Real SolidWorks integration smoke tests.

These tests intentionally connect to a real local SolidWorks installation through
pywin32. They are disabled by default and only run when explicitly enabled.
"""

from __future__ import annotations

import os
import platform
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
    value = os.getenv(REAL_SW_ENV_FLAG, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _find_tool(server: SolidWorksMCPServer, tool_name: str):
    for tool in server.mcp._tools:
        if tool.name == tool_name:
            return tool.func
    raise AssertionError(f"Tool '{tool_name}' not found")


@pytest_asyncio.fixture
async def real_server() -> AsyncGenerator[SolidWorksMCPServer, None]:
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
        close_tool = _find_tool(server, "close_model")
        try:
            await close_tool(CloseModelInput(save=False))
        except Exception:
            pass
        await server.stop()


@pytest.fixture
def integration_output_dir() -> Path:
    output_dir = Path("tests") / ".generated" / "solidworks_integration"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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
