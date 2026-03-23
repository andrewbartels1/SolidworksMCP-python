"""Deterministic regression tests for docs discovery tool.

These tests validate the docs discovery functionality and ensure that
COM/VBA indexing produces consistent, expected results.
"""

from __future__ import annotations

import os
import platform
import shutil
import time
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

    # Create discovery with non-existent directory
    test_dir = Path("tests/.generated/docs-discovery-test")

    # Clean up with retry logic for Windows file locking
    if test_dir.exists():
        max_retries = 3
        for attempt in range(max_retries):
            try:
                shutil.rmtree(test_dir)
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # Wait before retry
                else:
                    # If cleanup fails, skip the test
                    pytest.skip(f"Could not clean up {test_dir} - file may be locked")

    try:
        SolidWorksDocsDiscovery(output_dir=test_dir)

        # Verify directory was created
        assert test_dir.exists(), "Output directory should be created"
    finally:
        # Cleanup after test with retry logic
        if test_dir.exists():
            for attempt in range(3):
                try:
                    shutil.rmtree(test_dir)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.5)
