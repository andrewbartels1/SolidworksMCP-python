"""
Tests for SolidWorks automation tools.

Comprehensive test suite covering VBA generation, macro recording,
batch processing, and workflow orchestration.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from src.solidworks_mcp.tools.automation import (
    register_automation_tools,
    GenerateVBAInput,
    VBAGenerationInput,
    RecordMacroInput,
    BatchProcessInput,
    DesignTableInput,
    WorkflowInput,
    TemplateInput,
    PerformanceOptimizationInput,
)


class TestAutomationTools:
    """Test suite for automation tools."""

    @pytest.mark.asyncio
    async def test_register_automation_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that automation tools register correctly."""
        tool_count = await register_automation_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 8

    @pytest.mark.asyncio
    async def test_generate_vba_code_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful VBA code generation."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_code = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "vba_code": "Sub CreateExtrusion()\n    ' Generated VBA code\n    swModel.FeatureManager.FeatureExtrusion2(...)\nEnd Sub",
                    "operation_type": "Extrusion",
                    "parameter_count": 15,
                    "estimated_execution_time": 2.1,
                    "complexity_level": "High",
                },
                execution_time=0.8,
            )
        )

        input_data = VBAGenerationInput(
            operation_type="Extrusion",
            parameters={
                "sketch_name": "Sketch1",
                "depth": 25.0,
                "direction": "Blind",
                "reverse_direction": False,
                "draft_angle": 0.0,
                "draft_outward": True,
                "thin_feature": False,
                "merge_result": True,
                "start_condition": "SketchPlane",
                "end_condition": "Blind",
                "end_condition_reference": None,
                "offset_parameters": {},
                "feature_scope": "All bodies",
                "auto_select": True,
                "assembly_feature_scope": "All components",
            },
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_code":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert "CreateExtrusion" in result["data"]["vba_code"]
        assert result["data"]["parameter_count"] == 15
        assert result["data"]["complexity_level"] == "High"
        mock_adapter.generate_vba_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_macro_recording_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful macro recording start."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.start_macro_recording = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "recording_session_id": "rec_001",
                    "recording_started": True,
                    "output_file": "recorded_macro.swp",
                    "recording_mode": "User actions",
                    "start_timestamp": "2024-03-15T10:30:00",
                },
                execution_time=0.3,
            )
        )

        input_data = RecordMacroInput(
            recording_name="Test Recording",
            output_file="recorded_macro.swp",
            recording_mode="User actions",
            capture_mouse=True,
            capture_keyboard=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "start_macro_recording":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["recording_started"] is True
        assert result["data"]["output_file"] == "recorded_macro.swp"
        mock_adapter.start_macro_recording.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_process_files_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful batch file processing."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_process_files = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "total_files": 10,
                    "processed_files": 9,
                    "failed_files": 1,
                    "processing_time": 45.2,
                    "operation": "Update custom properties",
                    "results": [
                        {"file": "part1.sldprt", "status": "success"},
                        {"file": "part2.sldprt", "status": "success"},
                        {
                            "file": "part3.sldprt",
                            "status": "failed",
                            "error": "File locked",
                        },
                        # ... more results
                    ],
                },
                execution_time=45.2,
            )
        )

        input_data = BatchProcessInput(
            source_directory="./parts/",
            operation="Update custom properties",
            operation_parameters={
                "properties": {"Author": "Engineer", "Revision": "A"},
                "overwrite_existing": True,
            },
            file_pattern="*.sldprt",
            include_subdirectories=True,
            parallel_processing=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "batch_process_files":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_files"] == 10
        assert result["data"]["processed_files"] == 9
        assert result["data"]["failed_files"] == 1
        mock_adapter.batch_process_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_manage_design_table_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful design table management."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.manage_design_table = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "design_table_file": "part_configurations.xls",
                    "configurations_created": 5,
                    "parameters_linked": 12,
                    "operation": "Link Excel table",
                    "table_rows": 6,  # Including header
                    "table_columns": 8,
                },
                execution_time=1.5,
            )
        )

        input_data = DesignTableInput(
            model_path="configurable_part.sldprt",
            table_file="part_configurations.xls",
            operation="Link Excel table",
            auto_update=True,
            create_configurations=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "manage_design_table":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["configurations_created"] == 5
        assert result["data"]["parameters_linked"] == 12
        mock_adapter.manage_design_table.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_workflow_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful workflow execution."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_workflow = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "workflow_name": "Part Creation Workflow",
                    "steps_completed": 8,
                    "total_steps": 8,
                    "execution_time": 12.5,
                    "output_files": ["final_part.sldprt", "part_drawing.slddrw"],
                    "workflow_status": "Completed successfully",
                },
                execution_time=12.5,
            )
        )

        input_data = WorkflowInput(
            workflow_name="Part Creation Workflow",
            steps=[
                {"action": "open_template", "template": "part_template.prtdot"},
                {"action": "create_sketch", "plane": "Front"},
                {"action": "sketch_rectangle", "width": 50, "height": 30},
                {"action": "extrude", "depth": 25},
                {"action": "create_drawing", "template": "drawing_template.drwdot"},
                {"action": "add_views", "views": ["Front", "Right", "Top"]},
                {"action": "add_dimensions", "auto_dimension": True},
                {"action": "save_all"},
            ],
            parallel_execution=False,
            error_handling="Stop on error",
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "execute_workflow":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["steps_completed"] == 8
        assert result["data"]["total_steps"] == 8
        assert "final_part.sldprt" in result["data"]["output_files"]
        mock_adapter.execute_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_template_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful template creation."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_template = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "template_file": "custom_part_template.prtdot",
                    "template_type": "Part",
                    "included_features": [
                        "Base sketch",
                        "Custom properties",
                        "Material assignment",
                    ],
                    "settings_captured": 15,
                    "template_size": "125 KB",
                },
                execution_time=2.8,
            )
        )

        input_data = TemplateInput(
            source_model="reference_part.sldprt",
            template_name="Custom Part Template",
            template_type="Part",
            output_path="templates/custom_part_template.prtdot",
            include_custom_properties=True,
            include_materials=True,
            include_features=["Base sketch"],
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_template":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["template_file"] == "custom_part_template.prtdot"
        assert result["data"]["settings_captured"] == 15
        mock_adapter.create_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_optimize_performance_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful performance optimization."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.optimize_performance = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "optimization_type": "Assembly performance",
                    "optimizations_applied": [
                        "Lightweight components",
                        "Simplified representations",
                        "Display states optimization",
                        "Large assembly mode",
                    ],
                    "performance_improvement": "35%",
                    "memory_savings": "450 MB",
                    "load_time_reduction": "12.3 seconds",
                },
                execution_time=3.2,
            )
        )

        input_data = PerformanceOptimizationInput(
            target_file="large_assembly.sldasm",
            optimization_type="Assembly performance",
            optimization_level="Aggressive",
            preserve_features=["Mates", "Dimensions"],
            create_backup=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "optimize_performance":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["performance_improvement"] == "35%"
        assert "Lightweight components" in result["data"]["optimizations_applied"]
        mock_adapter.optimize_performance.assert_called_once()

    @pytest.mark.asyncio
    async def test_automation_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in automation operations."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_code = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="Invalid operation parameters",
                execution_time=0.1,
            )
        )

        input_data = VBAGenerationInput(
            operation_type="Invalid Operation", parameters={}
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "generate_vba_code":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Invalid operation parameters" in result["message"]

    @pytest.mark.asyncio
    async def test_automation_fallback_paths_without_adapter_methods(
        self, mcp_server, mock_config
    ):
        """Test fallback simulation branches for all automation tools."""
        await register_automation_tools(mcp_server, object(), mock_config)

        by_name = {tool.name: tool.handler for tool in mcp_server._tools}

        vba = await by_name["generate_vba_code"](
            input_data=VBAGenerationInput(operation_type="Create Block")
        )
        start = await by_name["start_macro_recording"](
            input_data=RecordMacroInput(recording_name="Macro A")
        )
        stop = await by_name["stop_macro_recording"](input_data={"session": "x"})
        batch = await by_name["batch_process_files"](
            input_data=BatchProcessInput(
                source_directory="./parts",
                operation="export",
                target_format="step",
                file_pattern="*.sldprt",
            )
        )
        table = await by_name["manage_design_table"](
            input_data=DesignTableInput(operation="create")
        )
        workflow = await by_name["execute_workflow"](
            input_data=WorkflowInput(
                workflow_name="WF",
                steps=[{"name": "step-1"}],
                parallel_execution=False,
                error_handling="stop",
            )
        )
        template = await by_name["create_template"](
            input_data=TemplateInput(template_type="part", template_name="StdPart")
        )
        optimize = await by_name["optimize_performance"](
            input_data={"optimization_type": "general"}
        )

        assert vba["status"] == "success"
        assert "vba_code" in vba
        assert start["status"] == "success"
        assert start["macro_recording"]["status"] == "recording"
        assert stop["status"] == "success"
        assert stop["macro_recording"]["status"] == "stopped"
        assert batch["status"] == "success"
        assert batch["batch_process"]["files_found"] == 25
        assert table["status"] == "success"
        assert table["design_table"]["operation"] == "create"
        assert workflow["status"] == "success"
        assert workflow["workflow"]["total_steps"] == 1
        assert template["status"] == "success"
        assert template["template"]["type"] == "part"
        assert optimize["status"] == "success"
        assert optimize["optimization"]["settings_optimized"] == 12

    @pytest.mark.asyncio
    async def test_automation_exception_paths_from_adapter_methods(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test exception handlers across automation tools that call adapter methods."""
        await register_automation_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.generate_vba_code = AsyncMock(side_effect=RuntimeError("vba boom"))
        mock_adapter.start_macro_recording = AsyncMock(
            side_effect=RuntimeError("record boom")
        )
        mock_adapter.batch_process_files = AsyncMock(
            side_effect=RuntimeError("batch boom")
        )
        mock_adapter.manage_design_table = AsyncMock(
            side_effect=RuntimeError("table boom")
        )
        mock_adapter.execute_workflow = AsyncMock(side_effect=RuntimeError("wf boom"))
        mock_adapter.create_template = AsyncMock(side_effect=RuntimeError("tpl boom"))
        mock_adapter.optimize_performance = AsyncMock(
            side_effect=RuntimeError("perf boom")
        )

        by_name = {tool.name: tool.handler for tool in mcp_server._tools}

        vba = await by_name["generate_vba_code"](
            input_data=VBAGenerationInput(operation_type="X")
        )
        start = await by_name["start_macro_recording"](
            input_data=RecordMacroInput(recording_name="Y")
        )
        batch = await by_name["batch_process_files"](
            input_data=BatchProcessInput(source_directory="./parts", operation="export")
        )
        table = await by_name["manage_design_table"](
            input_data=DesignTableInput(operation="create")
        )
        workflow = await by_name["execute_workflow"](
            input_data=WorkflowInput(
                workflow_name="WF",
                steps=[{"name": "step-1"}],
                parallel_execution=False,
                error_handling="stop",
            )
        )
        template = await by_name["create_template"](
            input_data=TemplateInput(template_type="part", template_name="StdPart")
        )
        optimize = await by_name["optimize_performance"](
            input_data={"optimization_type": "general"}
        )

        assert vba["status"] == "error"
        assert "Unexpected error" in vba["message"]
        assert start["status"] == "error"
        assert "Unexpected error" in start["message"]
        assert batch["status"] == "error"
        assert "Unexpected error" in batch["message"]
        assert table["status"] == "error"
        assert "Unexpected error" in table["message"]
        assert workflow["status"] == "error"
        assert "Unexpected error" in workflow["message"]
        assert template["status"] == "error"
        assert "Unexpected error" in template["message"]
        assert optimize["status"] == "error"
        assert "Unexpected error" in optimize["message"]

    @pytest.mark.unit
    def test_vba_generation_input_validation(self):
        """Test input validation for VBA generation."""
        # Valid input
        valid_input = GenerateVBAInput(
            operation_type="Extrusion", parameters={"depth": 25.0}
        )
        assert valid_input.operation_type == "Extrusion"
        assert valid_input.parameters["depth"] == 25.0

    @pytest.mark.unit
    def test_batch_processing_input_validation(self):
        """Test input validation for batch processing."""
        # Valid input
        valid_input = BatchProcessInput(
            source_directory="./parts/", operation="Export STEP"
        )
        assert valid_input.source_directory == "./parts/"
        assert valid_input.operation == "Export STEP"

        # Test with optional parameters
        full_input = BatchProcessInput(
            source_directory="./parts/",
            operation="Export STEP",
            file_pattern="*.sldprt",
            parallel_processing=True,
        )
        assert full_input.file_pattern == "*.sldprt"
        assert full_input.parallel_processing is True
