"""
Tests for SolidWorks macro recording tools.

Comprehensive test suite covering macro recording, playback, analysis,
batch execution, optimization, and library management.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.solidworks_mcp.tools.macro_recording import (
    MacroAnalysisInput,
    MacroBatchInput,
    MacroPlaybackInput,
    MacroRecordingInput,
    register_macro_recording_tools,
)


class TestMacroRecordingTools:
    """Test suite for macro recording tools."""

    @pytest.mark.asyncio
    async def test_register_macro_recording_tools(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test that macro recording tools register correctly."""
        tool_count = await register_macro_recording_tools(
            mcp_server, mock_adapter, mock_config
        )
        assert tool_count == 8

    @pytest.mark.asyncio
    async def test_start_macro_recording_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful macro recording start."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.start_macro_recording = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "recording_id": "REC_20240315_103000",
                    "recording_file": "user_actions.swp",
                    "recording_started": True,
                    "recording_mode": "User actions",
                    "start_time": "2024-03-15T10:30:00",
                    "capture_settings": {
                        "mouse_actions": True,
                        "keyboard_actions": True,
                        "feature_operations": True,
                        "sketch_operations": True,
                    },
                },
                execution_time=0.2,
            )
        )

        input_data = MacroRecordingInput(
            recording_name="User Workflow Recording",
            output_file="user_actions.swp",
            recording_mode="User actions",
            capture_mouse=True,
            capture_keyboard=True,
            auto_cleanup=True,
            recording_quality="High",
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
        assert result["data"]["recording_file"] == "user_actions.swp"
        assert result["data"]["recording_id"] == "REC_20240315_103000"
        mock_adapter.start_macro_recording.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_macro_recording_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful macro recording stop."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.stop_macro_recording = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "recording_id": "REC_20240315_103000",
                    "recording_stopped": True,
                    "final_file": "user_actions_completed.swp",
                    "recording_duration": 185.5,
                    "actions_captured": 42,
                    "file_size": "8.7 KB",
                    "summary": {
                        "sketch_operations": 15,
                        "feature_operations": 18,
                        "view_changes": 5,
                        "selection_operations": 4,
                    },
                },
                execution_time=0.5,
            )
        )

        input_data = {
            "recording_id": "REC_20240315_103000",
            "save_location": "./macros/",
            "optimize_code": True,
            "include_comments": True,
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "stop_macro_recording":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["recording_stopped"] is True
        assert result["data"]["actions_captured"] == 42
        assert result["data"]["recording_duration"] == 185.5
        mock_adapter.stop_macro_recording.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_macro_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful macro execution."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "macro_file": "batch_process.swp",
                    "execution_status": "Completed",
                    "execution_time": 12.3,
                    "operations_performed": 25,
                    "errors_encountered": 0,
                    "warnings_encountered": 2,
                    "output_files": [
                        "processed_part1.sldprt",
                        "processed_part2.sldprt",
                    ],
                    "log_file": "macro_execution_log.txt",
                },
                execution_time=12.3,
            )
        )

        input_data = MacroPlaybackInput(
            macro_file="batch_process.swp",
            target_file="input_part.sldprt",
            execution_mode="Normal",
            pause_on_error=False,
            log_execution=True,
            execution_parameters={"batch_size": 10},
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "execute_macro":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["execution_status"] == "Completed"
        assert result["data"]["operations_performed"] == 25
        assert result["data"]["errors_encountered"] == 0
        mock_adapter.execute_macro.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_macro_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful macro analysis."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_macro = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "macro_file": "complex_workflow.swp",
                    "analysis_results": {
                        "complexity_score": 7.5,
                        "estimated_execution_time": 45.2,
                        "code_lines": 185,
                        "function_count": 8,
                        "loop_count": 3,
                        "conditional_count": 12,
                    },
                    "optimization_suggestions": [
                        {
                            "type": "REDUNDANT_OPERATIONS",
                            "description": "Remove duplicate selections",
                            "impact": "15% faster",
                        },
                        {
                            "type": "LOOP_OPTIMIZATION",
                            "description": "Combine nested loops",
                            "impact": "Memory savings",
                        },
                        {
                            "type": "ERROR_HANDLING",
                            "description": "Add error checking for file operations",
                            "impact": "Reliability",
                        },
                    ],
                    "dependencies": ["SldWorks API", "File System"],
                    "risk_assessment": "Medium",
                    "maintainability_score": 6.8,
                },
                execution_time=1.1,
            )
        )

        input_data = MacroAnalysisInput(
            macro_file="complex_workflow.swp",
            analysis_depth="Comprehensive",
            include_performance_analysis=True,
            include_security_analysis=True,
            suggest_optimizations=True,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "analyze_macro":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["analysis_results"]["complexity_score"] == 7.5
        assert result["data"]["analysis_results"]["code_lines"] == 185
        assert len(result["data"]["optimization_suggestions"]) == 3
        assert result["data"]["risk_assessment"] == "Medium"
        mock_adapter.analyze_macro.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_execute_macros_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful batch macro execution."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.batch_execute_macros = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "batch_id": "BATCH_20240315_114500",
                    "total_macros": 5,
                    "successful_executions": 4,
                    "failed_executions": 1,
                    "total_execution_time": 89.7,
                    "execution_results": [
                        {"macro": "macro1.swp", "status": "success", "time": 15.2},
                        {"macro": "macro2.swp", "status": "success", "time": 22.8},
                        {
                            "macro": "macro3.swp",
                            "status": "failed",
                            "error": "File not found",
                        },
                        {"macro": "macro4.swp", "status": "success", "time": 18.5},
                        {"macro": "macro5.swp", "status": "success", "time": 33.2},
                    ],
                    "log_file": "batch_execution_log.txt",
                },
                execution_time=89.7,
            )
        )

        input_data = MacroBatchInput(
            macro_list=[
                "macro1.swp",
                "macro2.swp",
                "macro3.swp",
                "macro4.swp",
                "macro5.swp",
            ],
            target_directory="./input_files/",
            execution_mode="Sequential",
            continue_on_error=True,
            log_execution=True,
            parallel_limit=2,
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "batch_execute_macros":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["total_macros"] == 5
        assert result["data"]["successful_executions"] == 4
        assert result["data"]["failed_executions"] == 1
        mock_adapter.batch_execute_macros.assert_called_once()

    @pytest.mark.asyncio
    async def test_optimize_macro_success(self, mcp_server, mock_adapter, mock_config):
        """Test successful macro optimization."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.optimize_macro = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "original_macro": "unoptimized_workflow.swp",
                    "optimized_macro": "optimized_workflow.swp",
                    "optimization_results": {
                        "original_lines": 245,
                        "optimized_lines": 180,
                        "lines_removed": 65,
                        "performance_improvement": "28%",
                        "estimated_time_savings": 8.5,
                    },
                    "optimizations_applied": [
                        "Removed redundant selections",
                        "Consolidated similar operations",
                        "Optimized loop structures",
                        "Added error handling",
                        "Improved variable declarations",
                    ],
                    "warnings": [
                        "Some manual review recommended for complex operations"
                    ],
                },
                execution_time=2.1,
            )
        )

        input_data = {
            "macro_file": "unoptimized_workflow.swp",
            "optimization_level": "Aggressive",
            "preserve_functionality": True,
            "add_error_handling": True,
            "optimize_loops": True,
            "remove_redundant_code": True,
            "output_file": "optimized_workflow.swp",
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "optimize_macro":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert (
            result["data"]["optimization_results"]["performance_improvement"] == "28%"
        )
        assert result["data"]["optimization_results"]["lines_removed"] == 65
        assert "Removed redundant selections" in result["data"]["optimizations_applied"]
        mock_adapter.optimize_macro.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_macro_library_success(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test successful macro library creation."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.create_macro_library = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={
                    "library_name": "Engineering Workflows",
                    "library_path": "C:\\MacroLibrary\\",
                    "categories_created": ["Modeling", "Drawing", "Analysis", "Export"],
                    "templates_included": 15,
                    "documentation_generated": True,
                    "index_file": "library_index.html",
                    "total_macros": 0,  # Initial empty library
                    "library_structure": {
                        "root": "C:\\MacroLibrary\\",
                        "categories": ["Modeling", "Drawing", "Analysis", "Export"],
                        "documentation": "docs/",
                        "templates": "templates/",
                    },
                },
                execution_time=1.8,
            )
        )

        input_data = {
            "library_name": "Engineering Workflows",
            "library_path": "C:\\MacroLibrary\\",
            "categories": ["Modeling", "Drawing", "Analysis", "Export"],
            "include_templates": True,
            "generate_documentation": True,
            "version_control": True,
        }

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "create_macro_library":
                tool_func = tool.handler
                break

        assert tool_func is not None
        result = await tool_func(input_data=input_data)

        assert result["status"] == "success"
        assert result["data"]["library_name"] == "Engineering Workflows"
        assert len(result["data"]["categories_created"]) == 4
        assert result["data"]["documentation_generated"] is True
        mock_adapter.create_macro_library.assert_called_once()

    @pytest.mark.asyncio
    async def test_macro_recording_error_handling(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test error handling in macro recording."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.start_macro_recording = AsyncMock(
            return_value=Mock(
                is_success=False,
                error="Recording already in progress",
                execution_time=0.1,
            )
        )

        input_data = MacroRecordingInput(
            recording_name="Test Recording", output_file="test.swp"
        )

        tool_func = None
        for tool in mcp_server._tools:
            if tool.name == "start_macro_recording":
                tool_func = tool.handler
                break

        result = await tool_func(input_data=input_data)
        assert result["status"] == "error"
        assert "Recording already in progress" in result["message"]

    @pytest.mark.asyncio
    async def test_start_macro_recording_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test start_macro_recording exception handling branch."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.start_macro_recording = AsyncMock(
            side_effect=RuntimeError("recorder unavailable")
        )

        start_tool = None
        for tool in mcp_server._tools:
            if tool.name == "start_macro_recording":
                start_tool = tool.handler
                break

        assert start_tool is not None
        result = await start_tool(
            input_data=MacroRecordingInput(
                recording_name="Explode", output_file="explode.swp"
            )
        )

        assert result["status"] == "error"
        assert "Failed to start recording" in result["message"]

    @pytest.mark.asyncio
    async def test_stop_macro_recording_fallback_path(self, mcp_server, mock_config):
        """Test stop_macro_recording fallback branch."""
        await register_macro_recording_tools(mcp_server, object(), mock_config)

        stop_tool = None
        for tool in mcp_server._tools:
            if tool.name == "stop_macro_recording":
                stop_tool = tool.handler
                break

        assert stop_tool is not None
        result = await stop_tool(
            input_data={
                "session_id": "REC-12345",
                "save_path": "C:\\Macros\\REC-12345.swp",
                "clean_code": False,
            }
        )
        assert result["status"] == "success"
        assert result["recorded_macro"]["session_id"] == "REC-12345"

    @pytest.mark.asyncio
    async def test_stop_macro_recording_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test stop_macro_recording exception handling path."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.stop_macro_recording = AsyncMock(
            side_effect=RuntimeError("stop failed")
        )

        stop_tool = None
        for tool in mcp_server._tools:
            if tool.name == "stop_macro_recording":
                stop_tool = tool.handler
                break

        exception_result = await stop_tool(input_data={"session_id": "REC-2"})
        assert exception_result["status"] == "error"
        assert "Failed to stop recording" in exception_result["message"]

    @pytest.mark.asyncio
    async def test_macro_tools_fallback_without_adapter_methods(
        self, mcp_server, mock_config
    ):
        """Test simulated fallback branches when adapter methods are unavailable."""
        adapter_without_methods = object()
        await register_macro_recording_tools(
            mcp_server, adapter_without_methods, mock_config
        )

        start_tool = None
        execute_tool = None
        batch_tool = None
        for tool in mcp_server._tools:
            if tool.name == "start_macro_recording":
                start_tool = tool.handler
            if tool.name == "execute_macro":
                execute_tool = tool.handler
            if tool.name == "batch_execute_macros":
                batch_tool = tool.handler

        assert start_tool is not None
        assert execute_tool is not None
        assert batch_tool is not None

        start_result = await start_tool(
            input_data=MacroRecordingInput(
                recording_name="Fallback recording",
                output_file="fallback.swp",
            )
        )
        assert start_result["status"] == "success"
        assert start_result["data"]["status"] == "recording"

        execute_result = await execute_tool(
            input_data=MacroPlaybackInput(
                macro_file="fallback.swp",
                repeat_count=2,
                pause_between_runs=0,
            )
        )
        assert execute_result["status"] == "success"
        assert execute_result["data"]["repeat_count"] == 2

        batch_result = await batch_tool(
            input_data=MacroBatchInput(
                macro_list=["a.swp", "b.swp", "c.swp"],
                stop_on_error=True,
            )
        )
        assert batch_result["status"] == "partial_success"
        assert batch_result["data"]["failed_macros"] == 1

    @pytest.mark.asyncio
    async def test_execute_macro_exception_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test execute_macro exception handling branch."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(side_effect=RuntimeError("engine down"))

        execute_tool = None
        for tool in mcp_server._tools:
            if tool.name == "execute_macro":
                execute_tool = tool.handler
                break

        assert execute_tool is not None
        result = await execute_tool(
            input_data=MacroPlaybackInput(macro_file="boom.swp", repeat_count=1)
        )

        assert result["status"] == "error"
        assert "Failed to execute macro" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_macro_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test execute_macro adapter error return path."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.execute_macro = AsyncMock(
            return_value=Mock(is_success=False, error="macro syntax error")
        )

        execute_tool = None
        for tool in mcp_server._tools:
            if tool.name == "execute_macro":
                execute_tool = tool.handler
                break

        assert execute_tool is not None
        result = await execute_tool(
            input_data=MacroPlaybackInput(macro_file="bad.swp", repeat_count=1)
        )
        assert result["status"] == "error"
        assert "macro syntax error" in result["message"]

    @pytest.mark.asyncio
    async def test_analyze_macro_fallback_path(self, mcp_server, mock_config):
        """Test analyze_macro fallback branch."""
        await register_macro_recording_tools(mcp_server, object(), mock_config)

        analyze_tool = None
        for tool in mcp_server._tools:
            if tool.name == "analyze_macro":
                analyze_tool = tool.handler
                break

        assert analyze_tool is not None
        result = await analyze_tool(
            input_data=MacroAnalysisInput(
                macro_file="analysis.swp", analysis_depth="Full"
            )
        )
        assert result["status"] == "success"
        assert result["analysis"]["code_metrics"]["total_lines"] == 67

    @pytest.mark.asyncio
    async def test_analyze_macro_adapter_error_path(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test analyze_macro adapter error branch."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.analyze_macro = AsyncMock(
            return_value=Mock(is_success=False, error="parse failure")
        )
        analyze_tool = None
        for tool in mcp_server._tools:
            if tool.name == "analyze_macro":
                analyze_tool = tool.handler
                break

        error_result = await analyze_tool(
            input_data=MacroAnalysisInput(macro_file="analysis.swp")
        )
        assert error_result["status"] == "error"
        assert "parse failure" in error_result["message"]

    @pytest.mark.asyncio
    async def test_batch_execute_macros_error_and_exception_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test batch_execute_macros adapter error and exception branches."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)
        mock_adapter.batch_execute_macros = AsyncMock(
            return_value=Mock(is_success=False, error="batch failed")
        )

        batch_tool = None
        for tool in mcp_server._tools:
            if tool.name == "batch_execute_macros":
                batch_tool = tool.handler
                break

        assert batch_tool is not None
        error_result = await batch_tool(
            input_data=MacroBatchInput(macro_list=["m1.swp"], stop_on_error=True)
        )
        assert error_result["status"] == "error"
        assert "batch failed" in error_result["message"]

        mock_adapter.batch_execute_macros = AsyncMock(
            side_effect=RuntimeError("executor down")
        )
        exception_result = await batch_tool(
            input_data=MacroBatchInput(macro_list=["m1.swp"], stop_on_error=True)
        )
        assert exception_result["status"] == "error"
        assert "Failed batch execution" in exception_result["message"]

    @pytest.mark.asyncio
    async def test_optimize_and_library_fallback_paths(self, mcp_server, mock_config):
        """Test optimize_macro and create_macro_library fallback payload branches."""
        await register_macro_recording_tools(mcp_server, object(), mock_config)

        optimize_tool = None
        library_tool = None
        for tool in mcp_server._tools:
            if tool.name == "optimize_macro":
                optimize_tool = tool.handler
            if tool.name == "create_macro_library":
                library_tool = tool.handler

        assert optimize_tool is not None
        assert library_tool is not None

        optimize_result = await optimize_tool(
            input_data={"macro_file": "legacy.swp", "level": "aggressive"}
        )
        assert optimize_result["status"] == "success"
        assert (
            optimize_result["optimization_report"]["optimization_level"] == "aggressive"
        )

        library_result = await library_tool(
            input_data={
                "library_name": "Team Library",
                "library_path": "C:\\Macros\\Team",
                "categories": ["Modeling"],
                "include_templates": False,
            }
        )
        assert library_result["status"] == "success"
        assert library_result["data"]["library_name"] == "Team Library"

    @pytest.mark.asyncio
    async def test_optimize_and_library_adapter_error_paths(
        self, mcp_server, mock_adapter, mock_config
    ):
        """Test optimize_macro and create_macro_library adapter error paths."""
        await register_macro_recording_tools(mcp_server, mock_adapter, mock_config)

        mock_adapter.optimize_macro = AsyncMock(
            return_value=Mock(is_success=False, error="optimizer failed")
        )
        mock_adapter.create_macro_library = AsyncMock(
            return_value=Mock(is_success=False, error="library create failed")
        )

        optimize_tool = None
        library_tool = None
        for tool in mcp_server._tools:
            if tool.name == "optimize_macro":
                optimize_tool = tool.handler
            if tool.name == "create_macro_library":
                library_tool = tool.handler

        assert optimize_tool is not None
        assert library_tool is not None

        optimize_error = await optimize_tool(input_data={"macro_file": "m.swp"})
        assert optimize_error["status"] == "error"
        assert "optimizer failed" in optimize_error["message"]

        library_error = await library_tool(input_data={"library_name": "Bad"})
        assert library_error["status"] == "error"
        assert "library create failed" in library_error["message"]

    @pytest.mark.unit
    def test_macro_recording_input_validation(self):
        """Test input validation for macro recording."""
        # Valid input
        valid_input = MacroRecordingInput(
            recording_name="Test Recording", output_file="test.swp"
        )
        assert valid_input.recording_name == "Test Recording"
        assert valid_input.output_file == "test.swp"

        # Test with optional parameters
        full_input = MacroRecordingInput(
            recording_name="Full Recording",
            output_file="full_test.swp",
            recording_mode="User actions",
            capture_mouse=True,
            capture_keyboard=False,
        )
        assert full_input.recording_mode == "User actions"
        assert full_input.capture_mouse is True
        assert full_input.capture_keyboard is False

    @pytest.mark.unit
    def test_macro_analysis_input_validation(self):
        """Test input validation for macro analysis."""
        # Valid input
        valid_input = MacroAnalysisInput(macro_file="test.swp", analysis_depth="Basic")
        assert valid_input.macro_file == "test.swp"
        assert valid_input.analysis_depth == "Basic"

        # Test with optional parameters
        full_input = MacroAnalysisInput(
            macro_file="complex.swp",
            analysis_depth="Comprehensive",
            include_performance_analysis=True,
            suggest_optimizations=False,
        )
        assert full_input.include_performance_analysis is True
        assert full_input.suggest_optimizations is False

    @pytest.mark.unit
    def test_macro_batch_input_validation(self):
        """Test input validation for batch macro operations."""
        # Valid input
        valid_input = MacroBatchInput(
            macro_list=["macro1.swp", "macro2.swp"], target_directory="./files/"
        )
        assert len(valid_input.macro_list) == 2
        assert valid_input.target_directory == "./files/"

        # Test with optional parameters
        full_input = MacroBatchInput(
            macro_list=["macro1.swp", "macro2.swp", "macro3.swp"],
            target_directory="./files/",
            execution_mode="Parallel",
            continue_on_error=False,
            parallel_limit=3,
        )
        assert full_input.execution_mode == "Parallel"
        assert full_input.continue_on_error is False
        assert full_input.parallel_limit == 3
