"""Tests for SolidWorks file management tools."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from solidworks_mcp.tools.file_management import (
    FileOperationInput,
    FormatConversionInput,
    SaveAsInput,
    register_file_management_tools,
)
from solidworks_mcp.utils.feature_tree_classifier import (
    classify_feature_tree_snapshot,
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
        # Ensure the reported tool count matches the number of tools actually registered
        registered_tool_names = {tool.name for tool in await mcp_server.list_tools()}
        assert tool_count == len(registered_tool_names)

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
        for tool in await mcp_server.list_tools():
            if tool.name == "manage_file_properties":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "convert_file_format":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "batch_file_operations":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "manage_file_properties":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "convert_file_format":
                tool_func = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "manage_file_properties":
                manage_tool = tool.fn
            if tool.name == "convert_file_format":
                convert_tool = tool.fn
            if tool.name == "batch_file_operations":
                batch_tool = tool.fn

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
        for tool in await mcp_server.list_tools():
            if tool.name == "save_file":
                save_tool = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "save_file":
                save_tool = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "save_file":
                save_tool = tool.fn
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
        for tool in await mcp_server.list_tools():
            if tool.name == "save_file":
                save_tool = tool.fn
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
        await mock_adapter.create_part("CoveragePart", "mm")

        save_as_tool = None
        properties_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_as":
                save_as_tool = tool.fn
            if tool.name == "get_file_properties":
                properties_tool = tool.fn

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
    async def test_save_as_solidworks_path_success_and_error(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover save_as SolidWorks save_file branch for both success and error."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_as_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_as":
                save_as_tool = tool.fn
                break

        assert save_as_tool is not None

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=True, execution_time=0.11)
        )
        success_result = await save_as_tool(
            input_data=SaveAsInput(
                file_path="C:/tmp/renamed_part.sldprt",
                format_type="solidworks",
                overwrite=True,
            )
        )
        assert success_result["status"] == "success"
        assert success_result["format"] == "solidworks"

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=False, error="save blocked")
        )
        error_result = await save_as_tool(
            input_data=SaveAsInput(
                file_path="C:/tmp/renamed_part.sldprt",
                format_type="sldprt",
                overwrite=True,
            )
        )
        assert error_result["status"] == "error"
        assert "save blocked" in error_result["message"]

    @pytest.mark.asyncio
    async def test_save_as_export_error_and_fallback_without_methods(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover save_as export error branch and no-method fallback branch."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_as_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_as":
                save_as_tool = tool.fn
                break

        assert save_as_tool is not None

        mock_adapter.export_file = AsyncMock(
            return_value=Mock(is_success=False, error="export failed")
        )
        export_error = await save_as_tool(
            input_data=SaveAsInput(
                file_path="C:/tmp/part.stl",
                format_type="stl",
                overwrite=True,
            )
        )
        assert export_error["status"] == "error"
        assert "export failed" in export_error["message"]

        from fastmcp import FastMCP

        fallback_server = FastMCP("fallback-test")
        await register_file_management_tools(fallback_server, object(), mock_config)

        fallback_save_as = None
        for tool in await fallback_server.list_tools():
            if tool.name == "save_as":
                fallback_save_as = tool.fn
                break

        assert fallback_save_as is not None
        fallback_result = await fallback_save_as(
            input_data=SaveAsInput(
                file_path="C:/tmp/fallback.step",
                format_type="step",
                overwrite=False,
            )
        )
        assert fallback_result["status"] == "success"
        assert fallback_result["file_path"].endswith("fallback.step")

    @pytest.mark.asyncio
    async def test_save_as_exception_path(self, mcp_server, mock_adapter, mock_config):
        """Cover save_as unexpected exception branch."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_as_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_as":
                save_as_tool = tool.fn
                break

        assert save_as_tool is not None

        mock_adapter.export_file = AsyncMock(side_effect=RuntimeError("boom"))
        result = await save_as_tool(
            input_data=SaveAsInput(
                file_path="C:/tmp/crash.stl",
                format_type="stl",
                overwrite=True,
            )
        )
        assert result["status"] == "error"
        assert "Unexpected error" in result["message"]

    @pytest.mark.asyncio
    async def test_batch_file_operations_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover batch_file_operations branch when adapter returns non-success."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_file_operations = AsyncMock(
            return_value=Mock(is_success=False, error="batch rejected")
        )

        batch_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "batch_file_operations":
                batch_tool = tool.fn
                break

        assert batch_tool is not None
        result = await batch_tool(
            input_data=FileOperationInput(file_path="./parts", operation="batch")
        )
        assert result["status"] == "error"
        assert "batch rejected" in result["message"]

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
        for tool in await mcp_server.list_tools():
            if tool.name == "manage_file_properties":
                manage_tool = tool.fn
            if tool.name == "convert_file_format":
                convert_tool = tool.fn
            if tool.name == "batch_file_operations":
                batch_tool = tool.fn

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

    @pytest.mark.asyncio
    async def test_get_model_info_list_features_list_configurations_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover success/error/exception paths for read-before-write file-management tools."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        get_model_info_tool = None
        list_features_tool = None
        list_configs_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "get_model_info":
                get_model_info_tool = tool.fn
            if tool.name == "list_features":
                list_features_tool = tool.fn
            if tool.name == "list_configurations":
                list_configs_tool = tool.fn

        assert get_model_info_tool is not None
        assert list_features_tool is not None
        assert list_configs_tool is not None

        mock_adapter.get_model_info = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"title": "Part1", "type": "Part", "feature_count": 3},
                execution_time=0.01,
            )
        )
        info_success = await get_model_info_tool()
        assert info_success["status"] == "success"
        assert info_success["model_info"]["feature_count"] == 3

        mock_adapter.get_model_info = AsyncMock(
            return_value=Mock(is_success=False, error="no active model")
        )
        info_error = await get_model_info_tool()
        assert info_error["status"] == "error"

        mock_adapter.get_model_info = AsyncMock(side_effect=RuntimeError("boom"))
        info_exception = await get_model_info_tool()
        assert info_exception["status"] == "error"
        assert "Unexpected error" in info_exception["message"]

        mock_adapter.list_features = AsyncMock(
            return_value=Mock(
                is_success=True,
                data=[
                    {"name": "Sketch1", "type": "ProfileFeature", "suppressed": False}
                ],
                execution_time=0.01,
            )
        )
        features_success = await list_features_tool(
            input_data={"include_suppressed": False}
        )
        assert features_success["status"] == "success"
        assert features_success["count"] == 1

        mock_adapter.list_features = AsyncMock(
            return_value=Mock(is_success=False, error="feature tree unavailable")
        )
        features_error = await list_features_tool(
            input_data={"include_suppressed": True}
        )
        assert features_error["status"] == "error"

        mock_adapter.list_features = AsyncMock(side_effect=RuntimeError("explode"))
        features_exception = await list_features_tool(
            input_data={"include_suppressed": True}
        )
        assert features_exception["status"] == "error"

        mock_adapter.list_configurations = AsyncMock(
            return_value=Mock(
                is_success=True, data=["Default", "Alt"], execution_time=0.01
            )
        )
        configs_success = await list_configs_tool()
        assert configs_success["status"] == "success"
        assert configs_success["count"] == 2

        mock_adapter.list_configurations = AsyncMock(
            return_value=Mock(is_success=False, error="config manager failed")
        )
        configs_error = await list_configs_tool()
        assert configs_error["status"] == "error"

        mock_adapter.list_configurations = AsyncMock(
            side_effect=RuntimeError("explode")
        )
        configs_exception = await list_configs_tool()
        assert configs_exception["status"] == "error"

    def test_classify_feature_tree_snapshot_paths(self):
        """Classify common feature families and low-confidence sketch-only snapshots."""
        revolve = classify_feature_tree_snapshot(
            {"type": "Part"},
            [{"name": "Boss-Revolve1", "type": "BossRevolve", "suppressed": False}],
        )
        assert revolve["family"] == "revolve"
        assert revolve["recommended_workflow"] == "direct-mcp-revolve"
        assert revolve["confidence"] == "high"

        sheet_metal = classify_feature_tree_snapshot(
            {"type": "Part"},
            [
                {"name": "Base-Flange1", "type": "Sheet-Metal", "suppressed": False},
                {"name": "Fold1", "type": "Fold", "suppressed": False},
            ],
        )
        assert sheet_metal["family"] == "sheet_metal"
        assert sheet_metal["needs_vba"] is True

        sketch_only = classify_feature_tree_snapshot(
            {"type": "Part"},
            [
                {"name": "Top Plane", "type": "RefPlane", "suppressed": False},
                {"name": "Sketch1", "type": "ProfileFeature", "suppressed": False},
            ],
        )
        assert sketch_only["family"] == "sketch_only"
        assert sketch_only["confidence"] == "low"
        assert sketch_only["warnings"]

    @pytest.mark.asyncio
    async def test_classify_feature_tree_tool_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover success, inline-payload, and error paths for classify_feature_tree."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        classify_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "classify_feature_tree":
                classify_tool = tool.fn

        assert classify_tool is not None

        mock_adapter.get_model_info = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"title": "Bat", "type": "Part", "feature_count": 2},
                execution_time=0.01,
            )
        )
        mock_adapter.list_features = AsyncMock(
            return_value=Mock(
                is_success=True,
                data=[
                    {
                        "name": "Boss-Revolve1",
                        "type": "BossRevolve",
                        "suppressed": False,
                    }
                ],
                execution_time=0.01,
            )
        )

        success = await classify_tool(input_data={"include_suppressed": True})
        assert success["status"] == "success"
        assert success["classification"]["family"] == "revolve"

        inline = await classify_tool(
            input_data={
                "model_info": {"type": "Part"},
                "features": [
                    {"name": "Base-Flange1", "type": "Sheet-Metal", "suppressed": False}
                ],
            }
        )
        assert inline["status"] == "success"
        assert inline["classification"]["family"] == "sheet_metal"

        mock_adapter.list_features = AsyncMock(
            return_value=Mock(is_success=False, error="feature tree unavailable")
        )
        error_result = await classify_tool(input_data={})
        assert error_result["status"] == "error"

        mock_adapter.list_features = AsyncMock(side_effect=RuntimeError("explode"))
        exception_result = await classify_tool(input_data={})
        assert exception_result["status"] == "error"

    @pytest.mark.asyncio
    async def test_load_part_and_load_assembly_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover validation and adapter result branches for load_part/load_assembly."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        load_part_tool = None
        load_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "load_part":
                load_part_tool = tool.fn
            if tool.name == "load_assembly":
                load_assembly_tool = tool.fn

        assert load_part_tool is not None
        assert load_assembly_tool is not None

        invalid_part = await load_part_tool(
            input_data={"file_path": "C:/tmp/not-part.txt"}
        )
        assert invalid_part["status"] == "error"

        invalid_asm = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/not-asm.txt"}
        )
        assert invalid_asm["status"] == "error"

        mock_adapter.open_model = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "title": "Demo",
                    "path": "C:/tmp/demo.sldprt",
                    "configuration": "Default",
                },
                execution_time=0.02,
            )
        )
        loaded_part = await load_part_tool(
            input_data={"file_path": "C:/tmp/demo.sldprt"}
        )
        assert loaded_part["status"] == "success"
        assert loaded_part["model"]["type"] == "Part"

        loaded_asm = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/demo.sldasm"}
        )
        assert loaded_asm["status"] == "success"
        assert loaded_asm["model"]["type"] == "Assembly"

        mock_adapter.open_model = AsyncMock(
            return_value=Mock(is_success=False, error="open failed")
        )
        failed_part = await load_part_tool(
            input_data={"file_path": "C:/tmp/demo.sldprt"}
        )
        failed_asm = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/demo.sldasm"}
        )
        assert failed_part["status"] == "error"
        assert failed_asm["status"] == "error"

        mock_adapter.open_model = AsyncMock(side_effect=RuntimeError("open crash"))
        except_part = await load_part_tool(
            input_data={"file_path": "C:/tmp/demo.sldprt"}
        )
        except_asm = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/demo.sldasm"}
        )
        assert except_part["status"] == "error"
        assert except_asm["status"] == "error"

    @pytest.mark.asyncio
    async def test_save_part_and_save_assembly_paths(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Cover path normalization and error branches for save_part/save_assembly."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_part_tool = None
        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_part":
                save_part_tool = tool.fn
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_part_tool is not None
        assert save_assembly_tool is not None

        empty_part_path = await save_part_tool(input_data={"file_path": "   "})
        assert empty_part_path["status"] == "error"
        assert "empty or whitespace" in empty_part_path["message"]

        extension_only = await save_part_tool(input_data={"file_path": ".sldprt"})
        assert extension_only["status"] == "error"
        assert "missing base filename" in extension_only["message"]

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=True, execution_time=0.02)
        )

        out_dir = tmp_path / "save_paths"
        out_dir.mkdir(parents=True, exist_ok=True)

        save_part_as = await save_part_tool(
            input_data={"file_path": str(out_dir / "demo.step")}
        )
        assert save_part_as["status"] == "success"
        assert save_part_as["file_path"].endswith(".sldprt")

        save_asm_as = await save_assembly_tool(
            input_data={"file_path": str(out_dir / "demo.step")}
        )
        assert save_asm_as["status"] == "success"
        assert save_asm_as["file_path"].endswith(".sldasm")

        save_part_current = await save_part_tool()
        save_asm_current = await save_assembly_tool()
        assert save_part_current["status"] == "success"
        assert save_asm_current["status"] == "success"

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=False, error="save failed")
        )
        save_part_err = await save_part_tool(
            input_data={"file_path": str(out_dir / "demo.sldprt")}
        )
        save_asm_err = await save_assembly_tool(
            input_data={"file_path": str(out_dir / "demo.sldasm")}
        )
        assert save_part_err["status"] == "error"
        assert save_asm_err["status"] == "error"

        mock_adapter.save_file = AsyncMock(side_effect=RuntimeError("save crash"))
        save_part_ex = await save_part_tool(
            input_data={"file_path": str(out_dir / "demo.sldprt")}
        )
        save_asm_ex = await save_assembly_tool(
            input_data={"file_path": str(out_dir / "demo.sldasm")}
        )
        assert save_part_ex["status"] == "error"
        assert save_asm_ex["status"] == "error"

    @pytest.mark.asyncio
    async def test_save_tools_path_validation_and_overwrite_policy(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Cover directory/writability/overwrite guards for save_part and save_assembly."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_part_tool = None
        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_part":
                save_part_tool = tool.fn
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_part_tool is not None
        assert save_assembly_tool is not None

        missing_dir_part = tmp_path / "missing_part_dir" / "demo.sldprt"
        missing_dir_asm = tmp_path / "missing_asm_dir" / "demo.sldasm"

        missing_part_result = await save_part_tool(
            input_data={"file_path": str(missing_dir_part), "overwrite": True}
        )
        missing_asm_result = await save_assembly_tool(
            input_data={"file_path": str(missing_dir_asm), "overwrite": True}
        )

        assert missing_part_result["status"] == "error"
        assert "Target directory does not exist" in missing_part_result["message"]
        assert missing_asm_result["status"] == "error"
        assert "Target directory does not exist" in missing_asm_result["message"]

        parent_file = tmp_path / "not_a_directory"
        parent_file.write_text("placeholder", encoding="utf-8")
        parent_file_part_target = parent_file / "child_part.sldprt"
        parent_file_asm_target = parent_file / "child_asm.sldasm"

        parent_file_part_result = await save_part_tool(
            input_data={"file_path": str(parent_file_part_target), "overwrite": True}
        )
        parent_file_asm_result = await save_assembly_tool(
            input_data={"file_path": str(parent_file_asm_target), "overwrite": True}
        )

        assert parent_file_part_result["status"] == "error"
        assert (
            "Target parent path is not a directory"
            in parent_file_part_result["message"]
        )
        assert parent_file_asm_result["status"] == "error"
        assert (
            "Target parent path is not a directory" in parent_file_asm_result["message"]
        )

        writable_dir = tmp_path / "writable"
        writable_dir.mkdir(parents=True, exist_ok=True)
        non_writable_part = writable_dir / "no_write_part.sldprt"
        non_writable_asm = writable_dir / "no_write_asm.sldasm"

        with patch(
            "solidworks_mcp.tools.file_management.os.access", return_value=False
        ):
            no_write_part_result = await save_part_tool(
                input_data={"file_path": str(non_writable_part), "overwrite": True}
            )
            no_write_asm_result = await save_assembly_tool(
                input_data={"file_path": str(non_writable_asm), "overwrite": True}
            )

        assert no_write_part_result["status"] == "error"
        assert "Target directory is not writable" in no_write_part_result["message"]
        assert no_write_asm_result["status"] == "error"
        assert "Target directory is not writable" in no_write_asm_result["message"]

        target_dir_part = writable_dir / "target_is_dir.sldprt"
        target_dir_asm = writable_dir / "target_is_dir.sldasm"
        target_dir_part.mkdir(parents=True, exist_ok=True)
        target_dir_asm.mkdir(parents=True, exist_ok=True)

        target_dir_part_result = await save_part_tool(
            input_data={"file_path": str(target_dir_part), "overwrite": True}
        )
        target_dir_asm_result = await save_assembly_tool(
            input_data={"file_path": str(target_dir_asm), "overwrite": True}
        )

        assert target_dir_part_result["status"] == "error"
        assert "Target path is a directory" in target_dir_part_result["message"]
        assert target_dir_asm_result["status"] == "error"
        assert "Target path is a directory" in target_dir_asm_result["message"]

        existing_part = writable_dir / "existing_part.sldprt"
        existing_asm = writable_dir / "existing_asm.sldasm"
        existing_part.write_text("part", encoding="utf-8")
        existing_asm.write_text("assembly", encoding="utf-8")

        exists_no_overwrite_part = await save_part_tool(
            input_data={"file_path": str(existing_part), "overwrite": False}
        )
        exists_no_overwrite_asm = await save_assembly_tool(
            input_data={"file_path": str(existing_asm), "overwrite": False}
        )

        assert exists_no_overwrite_part["status"] == "error"
        assert (
            "File already exists and overwrite=False"
            in exists_no_overwrite_part["message"]
        )
        assert exists_no_overwrite_asm["status"] == "error"
        assert (
            "File already exists and overwrite=False"
            in exists_no_overwrite_asm["message"]
        )

        default_no_overwrite_part = await save_part_tool(
            input_data={"file_path": str(existing_part)}
        )
        default_no_overwrite_asm = await save_assembly_tool(
            input_data={"file_path": str(existing_asm)}
        )

        assert default_no_overwrite_part["status"] == "error"
        assert (
            "File already exists and overwrite=False"
            in default_no_overwrite_part["message"]
        )
        assert default_no_overwrite_asm["status"] == "error"
        assert (
            "File already exists and overwrite=False"
            in default_no_overwrite_asm["message"]
        )

        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=True, execution_time=0.03)
        )

        overwrite_part_ok = await save_part_tool(
            input_data={"file_path": str(existing_part), "overwrite": True}
        )
        overwrite_asm_ok = await save_assembly_tool(
            input_data={"file_path": str(existing_asm), "overwrite": True}
        )

        assert overwrite_part_ok["status"] == "success"
        assert overwrite_asm_ok["status"] == "success"

        new_part_path = Path(tmp_path / "writable" / "new_part_target.step")
        new_asm_path = Path(tmp_path / "writable" / "new_asm_target.step")

        happy_part = await save_part_tool(
            input_data={"file_path": str(new_part_path), "overwrite": False}
        )
        happy_asm = await save_assembly_tool(
            input_data={"file_path": str(new_asm_path), "overwrite": False}
        )

        assert happy_part["status"] == "success"
        assert happy_part["file_path"].endswith(".sldprt")
        assert happy_asm["status"] == "success"
        assert happy_asm["file_path"].endswith(".sldasm")

        saved_paths = [call.args[0] for call in mock_adapter.save_file.await_args_list]
        assert str(existing_part) in saved_paths
        assert str(existing_asm) in saved_paths
        assert str(new_part_path.with_suffix(".sldprt")) in saved_paths
        assert str(new_asm_path.with_suffix(".sldasm")) in saved_paths

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_copy_path(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Copy active assembly and dependencies when include_references=True."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        source_dir = tmp_path / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_asm = source_dir / "wifi_box.sldasm"
        source_part_a = source_dir / "router.sldprt"
        source_part_b = source_dir / "lid.sldprt"
        source_asm.write_text("asm", encoding="utf-8")
        source_part_a.write_text("part-a", encoding="utf-8")
        source_part_b.write_text("part-b", encoding="utf-8")

        current_model = Mock()
        current_model.GetPathName = Mock(return_value=str(source_asm))
        current_model.GetDependencies2 = Mock(
            return_value=(
                "router",
                str(source_part_a),
                "lid",
                str(source_part_b),
            )
        )
        mock_adapter.currentModel = current_model
        mock_adapter.save_file = AsyncMock(
            return_value=Mock(is_success=True, execution_time=0.01)
        )

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_asm_path = target_dir / "wifi_box_copy.sldasm"

        result = await save_assembly_tool(
            input_data={
                "file_path": str(target_asm_path),
                "include_references": True,
                "overwrite": False,
            }
        )

        assert result["status"] == "success"
        assert result["copy_method"] == "tool_dependency_copy"
        assert result["file_path"] == str(target_asm_path)
        assert result["copied_file_count"] == 3
        assert target_asm_path.exists()
        assert (target_dir / source_part_a.name).exists()
        assert (target_dir / source_part_b.name).exists()
        assert mock_adapter.save_file.await_count == 0

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_requires_active_model(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Return deterministic error when include_references=True without active model."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        mock_adapter.currentModel = None
        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)
        result = await save_assembly_tool(
            input_data={
                "file_path": str(target_dir / "copy.sldasm"),
                "include_references": True,
            }
        )

        assert result["status"] == "error"
        assert "No active model" in result["message"]

    @pytest.mark.asyncio
    async def test_read_tools_fallback_when_adapter_methods_missing(
        self, mcp_server, mock_config
    ):
        """Cover read-helper adapter-missing branches."""
        await register_file_management_tools(mcp_server, object(), mock_config)

        get_model_info_tool = None
        list_features_tool = None
        list_configs_tool = None
        classify_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "get_model_info":
                get_model_info_tool = tool.fn
            if tool.name == "list_features":
                list_features_tool = tool.fn
            if tool.name == "list_configurations":
                list_configs_tool = tool.fn
            if tool.name == "classify_feature_tree":
                classify_tool = tool.fn

        assert get_model_info_tool is not None
        assert list_features_tool is not None
        assert list_configs_tool is not None
        assert classify_tool is not None

        model_info_result = await get_model_info_tool()
        features_result = await list_features_tool(
            input_data={"include_suppressed": False}
        )
        configs_result = await list_configs_tool()
        classify_result = await classify_tool(input_data={"include_suppressed": False})

        assert model_info_result["status"] == "error"
        assert "does not support get_model_info" in model_info_result["message"]
        assert features_result["status"] == "error"
        assert "does not support list_features" in features_result["message"]
        assert configs_result["status"] == "error"
        assert "does not support list_configurations" in configs_result["message"]
        assert classify_result["status"] == "error"
        assert "does not support list_features" in classify_result["message"]

    @pytest.mark.asyncio
    async def test_load_tools_result_value_defaults_with_sparse_payloads(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Cover _result_value defaults for None/sparse model payloads."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        load_part_tool = None
        load_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "load_part":
                load_part_tool = tool.fn
            if tool.name == "load_assembly":
                load_assembly_tool = tool.fn

        assert load_part_tool is not None
        assert load_assembly_tool is not None

        # result.data is None -> _result_value returns defaults.
        mock_adapter.open_model = AsyncMock(
            return_value=Mock(is_success=True, data=None, execution_time=0.02)
        )
        part_none_data = await load_part_tool(
            input_data={"file_path": "C:/tmp/a.sldprt"}
        )
        assert part_none_data["status"] == "success"
        assert part_none_data["model"]["name"] == "C:/tmp/a.sldprt"
        assert part_none_data["model"]["path"] == "C:/tmp/a.sldprt"
        assert part_none_data["model"]["configuration"] == "Default"

        # Sparse object payload with None values -> _result_value falls through keys/default.
        sparse_model = Mock()
        sparse_model.title = None
        sparse_model.name = None
        sparse_model.path = None
        sparse_model.file_path = None
        sparse_model.configuration = None
        mock_adapter.open_model = AsyncMock(
            return_value=Mock(is_success=True, data=sparse_model, execution_time=0.02)
        )

        asm_sparse = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/a.sldasm"}
        )
        assert asm_sparse["status"] == "success"
        assert asm_sparse["model"]["name"] == "C:/tmp/a.sldasm"
        assert asm_sparse["model"]["path"] == "C:/tmp/a.sldasm"
        assert asm_sparse["model"]["configuration"] == "Default"

        # Dict payload with only None fields exercises dict fallback return-default path.
        mock_adapter.open_model = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"title": None, "name": None, "path": None, "file_path": None},
                execution_time=0.02,
            )
        )
        part_dict_none = await load_part_tool(
            input_data={"file_path": "C:/tmp/b.sldprt"}
        )
        assert part_dict_none["status"] == "success"
        assert part_dict_none["model"]["name"] == "C:/tmp/b.sldprt"

        # Object payload with a non-null secondary key exercises attribute return path.
        obj_model = Mock()
        obj_model.title = None
        obj_model.name = None
        obj_model.path = None
        obj_model.file_path = "C:/tmp/object-model.sldasm"
        obj_model.configuration = None
        mock_adapter.open_model = AsyncMock(
            return_value=Mock(is_success=True, data=obj_model, execution_time=0.02)
        )
        asm_obj_value = await load_assembly_tool(
            input_data={"file_path": "C:/tmp/c.sldasm"}
        )
        assert asm_obj_value["status"] == "success"
        assert asm_obj_value["model"]["path"] == "C:/tmp/object-model.sldasm"

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_missing_deps_and_collision(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Missing dep files are tracked; colliding names get a numeric suffix."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        source_dir = tmp_path / "src_collision"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_asm = source_dir / "box.sldasm"
        source_part = source_dir / "bracket.sldprt"
        source_asm.write_text("asm", encoding="utf-8")
        source_part.write_text("part", encoding="utf-8")

        target_dir = tmp_path / "tgt_collision"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Pre-place a file that collides with the dependency name.
        (target_dir / "bracket.sldprt").write_text("existing", encoding="utf-8")

        current_model = Mock()
        current_model.GetPathName = Mock(return_value=str(source_asm))
        current_model.GetDependencies2 = Mock(
            return_value=(
                str(source_part),
                # This path does not exist — should end up in missing_source_files.
                str(source_dir / "ghost.sldprt"),
            )
        )
        mock_adapter.currentModel = current_model

        target_asm_path = target_dir / "box_copy.sldasm"
        # Force native Pack-and-Go to fail so the fallback copy path is exercised.
        with patch("win32com.client.Dispatch", side_effect=RuntimeError("no COM")):
            result = await save_assembly_tool(
                input_data={
                    "file_path": str(target_asm_path),
                    "include_references": True,
                    "overwrite": False,
                }
            )

        assert result["status"] == "success"
        assert result["copy_method"] == "tool_dependency_copy"
        # The collision produces bracket_1.sldprt instead of bracket.sldprt.
        assert any("bracket_1.sldprt" in f for f in result["copied_files"])
        # The ghost file ends up in missing_source_files.
        assert any("ghost.sldprt" in f for f in result["missing_source_files"])

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_getdeps_exception(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Error is surfaced cleanly when GetDependencies2 raises."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        source_dir = tmp_path / "src_exc"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_asm = source_dir / "crash.sldasm"
        source_asm.write_text("asm", encoding="utf-8")

        current_model = Mock()
        current_model.GetPathName = Mock(return_value=str(source_asm))
        current_model.GetDependencies2 = Mock(side_effect=RuntimeError("COM explosion"))
        mock_adapter.currentModel = current_model

        target_dir = tmp_path / "tgt_exc"
        target_dir.mkdir(parents=True, exist_ok=True)
        with patch("win32com.client.Dispatch", side_effect=RuntimeError("no COM")):
            result = await save_assembly_tool(
                input_data={
                    "file_path": str(target_dir / "crash_copy.sldasm"),
                    "include_references": True,
                }
            )

        assert result["status"] == "error"
        assert "COM explosion" in result["message"]

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_unsaved_source(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Return error when active assembly has no path (not yet saved to disk)."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        current_model = Mock()
        current_model.GetPathName = Mock(return_value="")
        mock_adapter.currentModel = current_model

        target_dir = tmp_path / "tgt_unsaved"
        target_dir.mkdir(parents=True, exist_ok=True)
        with patch("win32com.client.Dispatch", side_effect=RuntimeError("no COM")):
            result = await save_assembly_tool(
                input_data={
                    "file_path": str(target_dir / "copy.sldasm"),
                    "include_references": True,
                }
            )

        assert result["status"] == "error"
        assert "must be saved before" in result["message"]

    @pytest.mark.asyncio
    async def test_save_assembly_with_references_no_getdeps_method(
        self, mcp_server, mock_adapter, mock_config, tmp_path
    ):
        """Error when adapter's model has no GetDependencies2 callable."""
        await register_file_management_tools(mcp_server, mock_adapter, mock_config)

        save_assembly_tool = None
        for tool in await mcp_server.list_tools():
            if tool.name == "save_assembly":
                save_assembly_tool = tool.fn

        assert save_assembly_tool is not None

        source_dir = tmp_path / "src_nodeps"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_asm = source_dir / "nodeps.sldasm"
        source_asm.write_text("asm", encoding="utf-8")

        current_model = Mock(spec=[])  # no attributes at all
        # Manually set GetPathName but not GetDependencies2.
        current_model.GetPathName = Mock(return_value=str(source_asm))
        mock_adapter.currentModel = current_model

        target_dir = tmp_path / "tgt_nodeps"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Force native Pack-and-Go off so the fallback copy runs and hits the
        # missing-GetDependencies2 branch.
        with patch("win32com.client.Dispatch", side_effect=RuntimeError("no COM")):
            result = await save_assembly_tool(
                input_data={
                    "file_path": str(target_dir / "copy.sldasm"),
                    "include_references": True,
                }
            )

        assert result["status"] == "error"
        assert "GetDependencies2" in result["message"]
