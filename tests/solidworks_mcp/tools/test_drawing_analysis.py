"""Tests for SolidWorks drawing analysis tools."""

from types import SimpleNamespace

import pytest
from fastmcp import FastMCP

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.tools.drawing_analysis import register_drawing_analysis_tools


class TestDrawingAnalysisTools:
    """Test suite for drawing analysis tools."""

    @pytest.mark.asyncio
    async def test_register_drawing_analysis_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that drawing analysis tools register correctly."""
        tool_count = await register_drawing_analysis_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 1

    @pytest.mark.asyncio
    async def test_compare_drawing_versions_reads_real_files(
        self, mcp_server, mock_config, tmp_path
    ):
        """compare_drawing_versions reports honest filesystem facts instead of
        a fabricated geometric/dimension/annotation diff."""
        await register_drawing_analysis_tools(mcp_server, object(), mock_config)

        compare_tool = next(
            t.fn
            for t in await mcp_server.list_tools()
            if t.name == "compare_drawing_versions"
        )

        # Missing paths refuse outright.
        missing_paths = await compare_tool(input_data={})
        assert missing_paths["status"] == "error"
        assert missing_paths["error_type"] == "invalid_input"
        assert "drawing_version_1" in missing_paths["message"]
        assert "drawing_version_2" in missing_paths["message"]

        # Non-existent files refuse with a clear message naming them.
        rev_a = tmp_path / "rev_a.slddrw"
        rev_b = tmp_path / "rev_b.slddrw"
        not_found = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert not_found["status"] == "error"
        assert "not found on disk" in not_found["message"]

        # Two identical files compare as identical.
        rev_a.write_bytes(b"same content")
        rev_b.write_bytes(b"same content")
        identical = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert identical["status"] == "success"
        assert identical["comparison"]["identical"] is True
        assert identical["comparison"]["size_delta_bytes"] == 0

        # Two different files compare as different, with an honest size delta.
        rev_b.write_bytes(b"different content, longer")
        different = await compare_tool(
            input_data={
                "drawing_version_1": str(rev_a),
                "drawing_version_2": str(rev_b),
            }
        )
        assert different["status"] == "success"
        assert different["comparison"]["identical"] is False
        assert different["comparison"]["size_delta_bytes"] == len(
            b"different content, longer"
        ) - len(b"same content")


def _ok(data):
    """Test helper for ok."""
    return SimpleNamespace(
        is_success=True,
        data=data,
        error=None,
        execution_time=0.01,
    )


async def _tool(mcp_server, name: str):
    """Test helper for tool."""
    for registered in await mcp_server.list_tools():
        if registered.name == name:
            return registered.fn
    raise AssertionError(f"Tool not found: {name}")


class _DrawingAndAnalysisAdapterStub:
    """Test suite for DrawingAndAnalysisAdapterStub."""

    async def create_technical_drawing(self, *_args, **_kwargs):
        """Test helper for create technical drawing."""
        return _ok({"drawing_path": "d.slddrw"})

    async def add_drawing_view(self, *_args, **_kwargs):
        """Test helper for add drawing view."""
        return _ok({"view_name": "Front"})

    async def update_title_block(self, *_args, **_kwargs):
        """Test helper for update title block."""
        return _ok({"title": "T"})


def _make_mcp():
    """Create a plain FastMCP instance."""
    mcp = FastMCP("test")
    return mcp


def _make_config():
    """Test make config."""

    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=SecurityLevel.MINIMAL,
        adapter_type=AdapterType.MOCK,
        mock_solidworks=True,
    )


async def _get_tool(mcp, name: str):
    """Test get tool."""

    for tool in await mcp.list_tools():
        if tool.name == name:
            return tool.fn
    raise KeyError(f"Tool {name!r} not registered in list_tools()")


class TestDrawingAnalysisExceptionPaths:
    """Test drawing analysis exception paths."""
