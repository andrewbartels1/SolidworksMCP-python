"""Tests for SolidWorks export tools."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP

from solidworks_mcp.tools.export import (
    ExportFileInput,
    ExportImageInput,
    register_export_tools,
)


class TestExportTools:
    """Test suite for export tools."""

    @pytest.mark.asyncio
    async def test_register_export_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that export tools register correctly."""
        tool_count = await register_export_tools(mcp_server, mock_adapter, mock_config)
        assert tool_count == 6

    @pytest.mark.asyncio
    async def test_export_step_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful STEP file export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_step = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_part.step",
                    "file_size": "1.8 MB",
                    "export_format": "STEP AP214",
                    "units": "mm",
                    "export_time": 1.2,
                },
                execution_time=1.2,
            )
        )

        input_data = ExportFileInput(file_path="exports/test_part.step")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_step":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_part.step"
        assert result["data"]["units"] == "mm"
        mock_adapter.export_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_iges_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful IGES file export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_iges = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_part.iges",
                    "file_size": "2.1 MB",
                    "export_format": "IGES v2014",
                    "surface_representation": "NURBS",
                    "export_time": 0.9,
                },
                execution_time=0.9,
            )
        )

        input_data = ExportFileInput(file_path="exports/test_part.iges")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_iges":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_part.iges"
        assert result["data"]["surface_representation"] == "NURBS"
        mock_adapter.export_iges.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_stl_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful STL file export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_stl = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_part.stl",
                    "file_size": "850 KB",
                    "mesh_quality": "High",
                    "triangle_count": 12500,
                    "file_format": "Binary STL",
                },
                execution_time=0.6,
            )
        )

        input_data = ExportFileInput(file_path="exports/test_part.stl")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_stl":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_part.stl"
        assert result["data"]["triangle_count"] == 12500
        mock_adapter.export_stl.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_pdf_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful PDF export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_pdf = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_drawing.pdf",
                    "file_size": "1.2 MB",
                    "page_count": 1,
                    "resolution": "300 DPI",
                    "color_mode": "Color",
                },
                execution_time=0.8,
            )
        )

        input_data = ExportFileInput(file_path="exports/test_drawing.pdf")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_pdf":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_drawing.pdf"
        assert result["data"]["resolution"] == "300 DPI"
        mock_adapter.export_pdf.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_dwg_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful DWG export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_dwg = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_drawing.dwg",
                    "file_size": "950 KB",
                    "autocad_version": "2020",
                    "export_method": "Native DWG",
                    "layer_mapping": "SolidWorks Standard",
                },
                execution_time=1.1,
            )
        )

        input_data = ExportFileInput(file_path="exports/test_drawing.dwg")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_dwg":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_drawing.dwg"
        assert result["data"]["autocad_version"] == "2020"
        mock_adapter.export_dwg.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_image_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful image export."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_image = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "export_file": "test_part.png",
                    "file_size": "2.3 MB",
                    "image_format": "PNG",
                    "resolution": "1920x1080",
                    "view_orientation": "Isometric",
                },
                execution_time=0.7,
            )
        )

        input_data = ExportImageInput(
            model_path="test_part.sldprt",
            output_path="exports/test_part.png",
            image_format="PNG",
            resolution="1920x1080",
            view_orientation="Isometric",
        )

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_image":
                tool_func = tool.fn
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_part.png"
        assert result["data"]["resolution"] == "1920x1080"
        mock_adapter.export_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_error_handling(self, mcp_server, mock_adapter, mock_config):
        """Test error handling in export operations."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_step = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="Output directory does not exist",
                execution_time=0.1,
            )
        )

        input_data = ExportFileInput(file_path="/invalid_path/test_part.step")

        tool_func = None
        for tool in await mcp_server.list_tools():
            if tool.name == "export_step":
                tool_func = tool.fn
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Output directory does not exist" in result["message"]


class TestExportToolsBranchCoverage:
    """Additional branch coverage for export error and exception paths."""

    @pytest.mark.asyncio
    async def test_export_step_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover export_step exception handler."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.export_step = AsyncMock(side_effect=RuntimeError("boom step"))

        tool = next(
            t.fn for t in await mcp_server.list_tools() if t.name == "export_step"
        )
        result = await tool(ExportFileInput(file_path="out.step"))

        assert result["status"] == "error"
        assert result["error_type"] == "internal"

    @pytest.mark.asyncio
    async def test_export_image_error_and_export_file_fallback_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover image adapter explicit-error branch and export_file fallback success branch."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        by_name = {t.name: t.fn for t in await mcp_server.list_tools()}

        mock_adapter.export_image = AsyncMock(
            return_value=Mock(
                is_success=False, error="image export failed", execution_time=0.1
            )
        )
        image_error = await by_name["export_image"](
            input_data=ExportImageInput(model_path="a.sldprt", output_path="a.png")
        )
        assert image_error["status"] == "error"
        assert "image export failed" in image_error["message"]

        class _FileOnlyAdapter:
            export_file = AsyncMock(
                return_value=Mock(
                    is_success=True, data={"ok": True}, execution_time=0.2
                )
            )

        fallback_server = FastMCP("Export Fallback Test")
        await register_export_tools(fallback_server, _FileOnlyAdapter(), mock_config)
        fallback_tools = {t.name: t.fn for t in await fallback_server.list_tools()}

        fallback = await fallback_tools["export_image"](
            input_data=ExportImageInput(
                file_path="model.sldprt",
                model_path="model.sldprt",
                output_path="model.png",
            )
        )
        assert fallback["status"] == "success"
        assert fallback["export"]["file_path"] == "model.sldprt"

        class _FileOnlyErrorAdapter:
            export_file = AsyncMock(
                return_value=Mock(
                    is_success=False, error="file export failed", execution_time=0.2
                )
            )

        error_server = FastMCP("Export Error Fallback Test")
        await register_export_tools(error_server, _FileOnlyErrorAdapter(), mock_config)
        error_tools = {t.name: t.fn for t in await error_server.list_tools()}
        file_error = await error_tools["export_image"](
            input_data=ExportImageInput(
                file_path="model.sldprt",
                model_path="model.sldprt",
                output_path="model.png",
            )
        )
        assert file_error["status"] == "error"
        assert "file export failed" in file_error["message"]

        no_method_server = FastMCP("Export Refusal Test")
        await register_export_tools(no_method_server, object(), mock_config)
        no_method_tools = {t.name: t.fn for t in await no_method_server.list_tools()}
        refused = await no_method_tools["export_image"](
            input_data=ExportImageInput(
                file_path="model.sldprt",
                model_path="model.sldprt",
                output_path="model.png",
            )
        )
        assert refused["status"] == "error"
        assert "does not support export_image" in refused["message"]


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


class _ExportFallbackAdapter:
    """Test suite for ExportFallbackAdapter."""

    async def export_file(self, file_path: str, format_type: str):
        """Test helper for export file."""
        if not file_path:
            return SimpleNamespace(
                is_success=False, error="missing path", execution_time=0.01
            )
        return SimpleNamespace(
            is_success=True,
            error=None,
            data={"file": file_path, "fmt": format_type},
            execution_time=0.01,
        )


class _ExportNativeAdapter:
    """Test suite for ExportNativeAdapter."""

    async def export_step(self, *_args, **_kwargs):
        """Test helper for export step."""
        return _ok({"fmt": "step"})

    async def export_iges(self, *_args, **_kwargs):
        """Test helper for export iges."""
        return _ok({"fmt": "iges"})

    async def export_stl(self, *_args, **_kwargs):
        """Test helper for export stl."""
        return _ok({"fmt": "stl"})

    async def export_pdf(self, *_args, **_kwargs):
        """Test helper for export pdf."""
        return _ok({"fmt": "pdf"})

    async def export_dwg(self, *_args, **_kwargs):
        """Test helper for export dwg."""
        return _ok({"fmt": "dwg"})

    async def export_image(self, *_args, **_kwargs):
        """Test helper for export image."""
        return _ok({"fmt": "image"})


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_cls", [_ExportFallbackAdapter, _ExportNativeAdapter])
@pytest.mark.parametrize("fmt", ["step", "iges", "stl", "pdf", "dwg"])
async def test_export_tools_accept_a_plain_dict(
    mcp_server, mock_config, adapter_cls, fmt
):
    """A dict argument, as a script calling the tool function passes, works.

    Over MCP the arguments arrive as ``ExportFileInput``; called directly
    they are a dict, which used to fail on ``input_data.file_path``.
    """
    await register_export_tools(mcp_server, adapter_cls(), mock_config)

    result = await (await _tool(mcp_server, f"export_{fmt}"))(
        input_data={"file_path": f"a.{fmt}", "format_type": fmt}
    )

    assert result["status"] == "success"
    assert f"a.{fmt}" in result["message"]


@pytest.mark.asyncio
async def test_a_file_export_without_format_type_uses_the_tools_own(
    mcp_server, mock_adapter, mock_config
) -> None:
    await register_export_tools(mcp_server, mock_adapter, mock_config)
    mock_adapter.export_step = AsyncMock(
        return_value=Mock(is_success=True, data={}, execution_time=0.1)
    )
    tool = next(t.fn for t in await mcp_server.list_tools() if t.name == "export_step")

    result = await tool({"file_path": "C:/out/part.step"})

    assert result["status"] == "success"
    assert mock_adapter.export_step.call_args.args[0]["format_type"] == "step"
    assert ExportFileInput(file_path="C:/out/part.step").format_type is None


class _StlFallbackAdapter:
    """An adapter whose STL export went through the SaveAs3 fallback."""

    async def export_file(self, file_path: str, format_type: str):
        """Report the fallback's note, as the real adapter does."""
        return SimpleNamespace(
            is_success=True,
            error=None,
            data={"warning": "the STL options were not applied"},
            execution_time=0.01,
        )


@pytest.mark.asyncio
async def test_export_stl_passes_the_fallback_warning_on(mcp_server, mock_config):
    """A file written without the STL options says so in the reply."""
    await register_export_tools(mcp_server, _StlFallbackAdapter(), mock_config)

    reply = await (await _tool(mcp_server, "export_stl"))(
        input_data=ExportFileInput(file_path="a.stl")
    )

    assert reply["status"] == "success"
    assert reply["warning"] == "the STL options were not applied"


@pytest.mark.asyncio
async def test_export_stl_without_a_fallback_has_no_warning(mcp_server, mock_config):
    """The usual export carries no warning."""
    await register_export_tools(mcp_server, _ExportFallbackAdapter(), mock_config)

    reply = await (await _tool(mcp_server, "export_stl"))(
        input_data=ExportFileInput(file_path="a.stl")
    )

    assert "warning" not in reply
