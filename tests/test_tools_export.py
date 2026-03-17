"""
Tests for SolidWorks export tools.

Comprehensive test suite covering file exports in multiple formats
including STEP, IGES, STL, PDF, DWG, and image exports.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.export import (
    BatchExportInput,
    ExportDWGInput,
    ExportIGESInput,
    ExportImageInput,
    ExportPDFInput,
    ExportSTEPInput,
    ExportSTLInput,
    register_export_tools,
)


class TestExportTools:
    """Test suite for export tools."""

    @pytest.mark.asyncio
    async def test_register_export_tools(self, mcp_server, mock_adapter, mock_config):
        """Test that export tools register correctly."""
        tool_count = await register_export_tools(mcp_server, mock_adapter, mock_config)
        assert tool_count == 7

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

        input_data = ExportSTEPInput(
            model_path="test_part.sldprt",
            output_path="exports/test_part.step",
            step_version="AP214",
            units="mm",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_step":
                tool_func = tool.handler
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

        input_data = ExportIGESInput(
            model_path="test_part.sldprt",
            output_path="exports/test_part.iges",
            iges_version="2014",
            surface_type="NURBS",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_iges":
                tool_func = tool.handler
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

        input_data = ExportSTLInput(
            model_path="test_part.sldprt",
            output_path="exports/test_part.stl",
            resolution="High",
            file_format="Binary",
            units="mm",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_stl":
                tool_func = tool.handler
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

        input_data = ExportPDFInput(
            drawing_path="test_drawing.slddrw",
            output_path="exports/test_drawing.pdf",
            quality="High",
            color_mode="Color",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_pdf":
                tool_func = tool.handler
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

        input_data = ExportDWGInput(
            drawing_path="test_drawing.slddrw",
            output_path="exports/test_drawing.dwg",
            autocad_version="2020",
            layer_mapping=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_dwg":
                tool_func = tool.handler
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
        for tool in mcp_server._tools:
            if tool.name == "export_image":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["export_file"] == "test_part.png"
        assert result["data"]["resolution"] == "1920x1080"
        mock_adapter.export_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_export_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful batch export operation."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_export = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "total_files": 5,
                    "exported_files": 5,
                    "failed_files": 0,
                    "export_format": "STEP",
                    "total_time": 3.8,
                    "results": [
                        {
                            "file": "part1.sldprt",
                            "status": "success",
                            "output": "part1.step",
                        },
                        {
                            "file": "part2.sldprt",
                            "status": "success",
                            "output": "part2.step",
                        },
                        {
                            "file": "part3.sldprt",
                            "status": "success",
                            "output": "part3.step",
                        },
                        {
                            "file": "part4.sldprt",
                            "status": "success",
                            "output": "part4.step",
                        },
                        {
                            "file": "part5.sldprt",
                            "status": "success",
                            "output": "part5.step",
                        },
                    ],
                },
                execution_time=3.8,
            )
        )

        input_data = BatchExportInput(
            source_directory="./parts/",
            output_directory="./exports/",
            export_format="STEP",
            file_pattern="*.sldprt",
            include_subdirectories=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "batch_export":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_files"] == 5
        assert result["data"]["failed_files"] == 0
        assert result["data"]["export_format"] == "STEP"
        mock_adapter.batch_export.assert_called_once()

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

        input_data = ExportSTEPInput(
            model_path="test_part.sldprt", output_path="/invalid_path/test_part.step"
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "export_step":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Output directory does not exist" in result["message"]

    @pytest.mark.unit
    def test_export_step_input_validation(self):
        """Test input validation for STEP export."""
        # Valid input
        valid_input = ExportSTEPInput(model_path="test.sldprt", output_path="test.step")
        assert valid_input.model_path == "test.sldprt"
        assert valid_input.output_path == "test.step"

        # Test optional parameters
        full_input = ExportSTEPInput(
            model_path="test.sldprt",
            output_path="test.step",
            step_version="AP214",
            units="mm",
        )
        assert full_input.step_version == "AP214"
        assert full_input.units == "mm"

    @pytest.mark.unit
    def test_batch_export_input_validation(self):
        """Test input validation for batch export."""
        # Valid input
        valid_input = BatchExportInput(
            source_directory="./parts/",
            output_directory="./exports/",
            export_format="STEP",
        )
        assert valid_input.source_directory == "./parts/"
        assert valid_input.export_format == "STEP"

        # Test with optional parameters
        full_input = BatchExportInput(
            source_directory="./parts/",
            output_directory="./exports/",
            export_format="IGES",
            file_pattern="*.sld*",
            include_subdirectories=True,
        )
        assert full_input.file_pattern == "*.sld*"
        assert full_input.include_subdirectories is True


class TestExportToolsBranchCoverage:
    """Additional branch coverage for export error and exception paths."""

    @pytest.mark.asyncio
    async def test_remaining_export_error_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover non-success adapter branches across remaining export tools."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_iges = AsyncMock(
            return_value=Mock(is_success=False, error="iges failed", execution_time=0.1)
        )
        mock_adapter.export_stl = AsyncMock(
            return_value=Mock(is_success=False, error="stl failed", execution_time=0.1)
        )
        mock_adapter.export_pdf = AsyncMock(
            return_value=Mock(is_success=False, error="pdf failed", execution_time=0.1)
        )
        mock_adapter.export_dwg = AsyncMock(
            return_value=Mock(is_success=False, error="dwg failed", execution_time=0.1)
        )
        # exercise default fallback message branches where error is missing
        mock_adapter.export_image = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )
        mock_adapter.batch_export = AsyncMock(
            return_value=Mock(is_success=False, error=None, execution_time=0.1)
        )

        by_name = {t.name: t.handler for t in mcp_server._tools}

        r1 = await by_name["export_iges"](
            input_data=ExportIGESInput(model_path="a.sldprt", output_path="a.iges")
        )
        r2 = await by_name["export_stl"](
            input_data=ExportSTLInput(model_path="a.sldprt", output_path="a.stl")
        )
        r3 = await by_name["export_pdf"](
            input_data=ExportPDFInput(model_path="a.slddrw", output_path="a.pdf")
        )
        r4 = await by_name["export_dwg"](
            input_data=ExportDWGInput(model_path="a.slddrw", output_path="a.dwg")
        )
        r5 = await by_name["export_image"](
            input_data=ExportImageInput(model_path="a.sldprt", output_path="a.png")
        )
        r6 = await by_name["batch_export"](
            input_data=BatchExportInput(
                source_directory="./in",
                output_directory="./out",
                export_format="STEP",
            )
        )

        assert r1["status"] == "error" and "iges failed" in r1["message"].lower()
        assert r2["status"] == "error" and "stl failed" in r2["message"].lower()
        assert r3["status"] == "error" and "pdf failed" in r3["message"].lower()
        assert r4["status"] == "error" and "dwg failed" in r4["message"].lower()
        assert (
            r5["status"] == "error"
            and "failed to export image" in r5["message"].lower()
        )
        assert (
            r6["status"] == "error" and "batch export failed" in r6["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_remaining_export_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover exception handlers for IGES/STL/PDF/DWG/image/batch export tools."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.export_iges = AsyncMock(side_effect=RuntimeError("boom iges"))
        mock_adapter.export_stl = AsyncMock(side_effect=RuntimeError("boom stl"))
        mock_adapter.export_pdf = AsyncMock(side_effect=RuntimeError("boom pdf"))
        mock_adapter.export_dwg = AsyncMock(side_effect=RuntimeError("boom dwg"))
        mock_adapter.export_image = AsyncMock(side_effect=RuntimeError("boom image"))
        mock_adapter.batch_export = AsyncMock(side_effect=RuntimeError("boom batch"))

        by_name = {t.name: t.func for t in mcp_server._tools}

        results = [
            await by_name["export_iges"](
                ExportIGESInput(model_path="a.sldprt", output_path="a.iges")
            ),
            await by_name["export_stl"](
                ExportSTLInput(model_path="a.sldprt", output_path="a.stl")
            ),
            await by_name["export_pdf"](
                ExportPDFInput(model_path="a.slddrw", output_path="a.pdf")
            ),
            await by_name["export_dwg"](
                ExportDWGInput(model_path="a.slddrw", output_path="a.dwg")
            ),
            await by_name["export_image"](
                ExportImageInput(model_path="a.sldprt", output_path="a.png")
            ),
            await by_name["batch_export"](
                BatchExportInput(
                    source_directory="./in",
                    output_directory="./out",
                    export_format="STEP",
                )
            ),
        ]

        for result in results:
            assert result["status"] == "error"
            assert "unexpected error" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_export_step_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover export_step exception handler."""
        await register_export_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.export_step = AsyncMock(side_effect=RuntimeError("boom step"))

        tool = next(t.func for t in mcp_server._tools if t.name == "export_step")
        result = await tool(
            ExportSTEPInput(model_path="test_part.sldprt", output_path="out.step")
        )

        assert result["status"] == "error"
        assert "unexpected error" in result["message"].lower()
