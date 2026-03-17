"""
Tests for SolidWorks file management tools.

Comprehensive test suite covering file operations, format conversions,
and property management.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.file_management import (
    FileOperationInput,
    FormatConversionInput,
    SaveAsInput,
    register_file_management_tools,
)


class TestFileManagementTools:
    """Test suite for file management tools."""

    @pytest.mark.asyncio
    async def test_register_file_management_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that file management tools register correctly."""
        tool_count = await register_file_management_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 3

    @pytest.mark.asyncio
    async def test_manage_file_properties_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful file property management."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.manage_file_properties = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "properties_updated": 5,
                    "custom_properties": {
                        "Author": "Test User",
                        "Description": "Test Part",
                        "Material": "Steel",
                        "PartNo": "SW-001",
                        "Revision": "A",
                    },
                    "system_properties": {
                        "Created": "2024-01-15",
                        "Modified": "2024-03-15",
                        "Size": "1.2 MB",
                    },
                },
                execution_time=0.4,
            )
        )

        input_data = FileOperationInput(
            file_path="test_part.sldprt",
            operation="get_properties",
            parameters={"include_custom": True, "include_system": True},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "manage_file_properties":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["properties_updated"] == 5
        assert "Author" in result["data"]["custom_properties"]
        assert "Created" in result["data"]["system_properties"]
        mock_adapter.manage_file_properties.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_file_format_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful file format conversion."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.convert_file_format = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "source_file": "test_part.sldprt",
                    "target_file": "test_part.step",
                    "format_from": "SLDPRT",
                    "format_to": "STEP",
                    "file_size": "2.1 MB",
                    "conversion_time": 1.8,
                },
                execution_time=1.8,
            )
        )

        input_data = FormatConversionInput(
            source_file="test_part.sldprt",
            target_format="STEP",
            output_path="exports/test_part.step",
            conversion_options={"quality": "high", "units": "mm"},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "convert_file_format":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["format_to"] == "STEP"
        assert result["data"]["target_file"] == "test_part.step"
        mock_adapter.convert_file_format.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_file_operations_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful batch file operations."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_file_operations = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "total_files": 3,
                    "processed_files": 3,
                    "failed_files": 0,
                    "results": [
                        {
                            "file": "part1.sldprt",
                            "status": "success",
                            "operation": "backup",
                        },
                        {
                            "file": "part2.sldprt",
                            "status": "success",
                            "operation": "backup",
                        },
                        {
                            "file": "assembly1.sldasm",
                            "status": "success",
                            "operation": "backup",
                        },
                    ],
                    "processing_time": 2.5,
                },
                execution_time=2.5,
            )
        )

        input_data = FileOperationInput(
            file_path="./parts/",
            operation="batch_backup",
            parameters={
                "target_directory": "./backups/",
                "include_subdirectories": True,
                "file_pattern": "*.sld*",
            },
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "batch_file_operations":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_files"] == 3
        assert result["data"]["failed_files"] == 0
        mock_adapter.batch_file_operations.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_properties_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in file property management."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.manage_file_properties = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="File is read-only or locked",
                execution_time=0.1,
            )
        )

        input_data = FileOperationInput(
            file_path="locked_part.sldprt",
            operation="set_properties",
            parameters={"Author": "New User"},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "manage_file_properties":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "read-only or locked" in result["message"]

    @pytest.mark.asyncio
    async def test_format_conversion_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in format conversion."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.convert_file_format = AsyncMock(
            return_value=Mock(
                is_success=False, error="Unsupported target format", execution_time=0.1
            )
        )

        input_data = FormatConversionInput(
            source_file="test_part.sldprt", target_format="INVALID_FORMAT"
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "convert_file_format":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Unsupported target format" in result["message"]

    @pytest.mark.asyncio
    async def test_file_management_tools_fallback_without_adapter_methods(
        self, mcp_server, mock_config
    ):
        """Test fallback success payloads when adapter has no specialized methods."""
        adapter_without_methods = object()
        await register_file_management_tools(
            mcp_server, adapter_without_methods, mock_config
        )

        manage_tool = None
        convert_tool = None
        batch_tool = None
        for tool in mcp_server._tools:
            if tool.name == "manage_file_properties":
                manage_tool = tool.handler
            if tool.name == "convert_file_format":
                convert_tool = tool.handler
            if tool.name == "batch_file_operations":
                batch_tool = tool.handler

        assert manage_tool is not None
        assert convert_tool is not None
        assert batch_tool is not None

        manage_result = await manage_tool(
            input_data=FileOperationInput(file_path="demo.sldprt", operation="rename")
        )
        assert manage_result["status"] == "success"
        assert manage_result["data"]["file_path"] == "demo.sldprt"

        convert_result = await convert_tool(
            input_data=FormatConversionInput(
                source_file="demo.sldprt",
                target_file="demo.step",
                target_format="STEP",
            )
        )
        assert convert_result["status"] == "success"
        assert convert_result["data"]["target_file"] == "demo.step"

        batch_result = await batch_tool(
            input_data=FileOperationInput(file_path="./parts", operation="batch")
        )
        assert batch_result["status"] == "success"
        assert batch_result["data"]["operation"] == "batch"

    @pytest.mark.asyncio
    async def test_save_file_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test save_file exception handling branch."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.save_file = AsyncMock(side_effect=RuntimeError("disk unavailable"))

        save_tool = None
        for tool in mcp_server._tools:
            if tool.name == "save_file":
                save_tool = tool.handler
                break

        assert save_tool is not None
        result = await save_tool(input_data={"force_save": True})

        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]

    @pytest.mark.asyncio
    async def test_save_file_success_with_adapter_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test save_file adapter success path."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"path": "demo.sldprt", "saved": True},
                execution_time=0.05,
            )
        )

        save_tool = None
        for tool in mcp_server._tools:
            if tool.name == "save_file":
                save_tool = tool.handler
                break

        assert save_tool is not None
        result = await save_tool(input_data={"force_save": True})
        assert result["status"] == "success"
        assert result["data"]["saved"] is True

    @pytest.mark.asyncio
    async def test_save_file_fallback_without_adapter_method(
        self, mcp_server, mock_config
    ):
        """Test save_file fallback path when adapter has no save_file method."""
        await register_file_management_tools(mcp_server, object(), mock_config)

        save_tool = None
        for tool in mcp_server._tools:
            if tool.name == "save_file":
                save_tool = tool.handler
                break

        fallback_result = await save_tool(input_data={"force_save": False})
        assert fallback_result["status"] == "success"
        assert "timestamp" in fallback_result

    @pytest.mark.asyncio
    async def test_save_file_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test save_file adapter error return path."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=False, error="write failed")
        )

        save_tool = None
        for tool in mcp_server._tools:
            if tool.name == "save_file":
                save_tool = tool.handler
                break

        result = await save_tool(input_data={"force_save": True})
        assert result["status"] == "error"
        assert "write failed" in result["message"]

    @pytest.mark.asyncio
    async def test_save_as_and_get_file_properties_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test save_as and get_file_properties simulated success branches."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_as_tool = None
        properties_tool = None
        for tool in mcp_server._tools:
            if tool.name == "save_as":
                save_as_tool = tool.handler
            if tool.name == "get_file_properties":
                properties_tool = tool.handler

        assert save_as_tool is not None
        assert properties_tool is not None

        save_as_result = await save_as_tool(
            input_data=SaveAsInput(
                file_path="exports/new_part.step",
                format_type="step",
                overwrite=True,
            )
        )
        assert save_as_result["status"] == "success"
        assert save_as_result["format"] == "step"

        properties_result = await properties_tool()
        assert properties_result["status"] == "success"
        assert properties_result["properties"]["file_name"] == "Example.sldprt"

    @pytest.mark.asyncio
    async def test_manage_convert_batch_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test exception branches for manage/convert/batch file operations."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.manage_file_properties = AsyncMock(
            side_effect=RuntimeError("properties crash")
        )
        mock_adapter.convert_file_format = AsyncMock(
            side_effect=RuntimeError("conversion crash")
        )
        mock_adapter.batch_file_operations = AsyncMock(
            side_effect=RuntimeError("batch crash")
        )

        manage_tool = None
        convert_tool = None
        batch_tool = None
        for tool in mcp_server._tools:
            if tool.name == "manage_file_properties":
                manage_tool = tool.handler
            if tool.name == "convert_file_format":
                convert_tool = tool.handler
            if tool.name == "batch_file_operations":
                batch_tool = tool.handler

        assert manage_tool is not None
        assert convert_tool is not None
        assert batch_tool is not None

        manage_result = await manage_tool(
            input_data=FileOperationInput(file_path="x.sldprt", operation="rename")
        )
        assert manage_result["status"] == "error"
        assert "Unexpected error" in manage_result["message"]

        convert_result = await convert_tool(
            input_data=FormatConversionInput(
                source_file="x.sldprt",
                target_file="x.step",
                target_format="STEP",
            )
        )
        assert convert_result["status"] == "error"
        assert "Unexpected error" in convert_result["message"]

        batch_result = await batch_tool(
            input_data=FileOperationInput(file_path="./parts", operation="batch")
        )
        assert batch_result["status"] == "error"
        assert "Unexpected error" in batch_result["message"]

    @pytest.mark.unit
    def test_file_operation_input_validation(self):
        """Test input validation for file operations."""
        # Valid input
        valid_input = FileOperationInput(
            file_path="test.sldprt", operation="get_properties"
        )
        assert valid_input.file_path == "test.sldprt"
        assert valid_input.operation == "get_properties"

        # Test with parameters
        input_with_params = FileOperationInput(
            file_path="test.sldprt",
            operation="set_properties",
            parameters={"Author": "Test User"},
        )
        assert input_with_params.parameters == {"Author": "Test User"}

    @pytest.mark.unit
    def test_format_conversion_input_validation(self):
        """Test input validation for format conversion."""
        # Valid input
        valid_input = FormatConversionInput(
            source_file="test.sldprt", target_format="STEP"
        )
        assert valid_input.source_file == "test.sldprt"
        assert valid_input.target_format == "STEP"

        # Test with optional parameters
        full_input = FormatConversionInput(
            source_file="test.sldprt",
            target_format="IGES",
            output_path="exports/test.igs",
            conversion_options={"units": "mm", "precision": "high"},
        )
        assert full_input.output_path == "exports/test.igs"
        assert full_input.conversion_options["units"] == "mm"
