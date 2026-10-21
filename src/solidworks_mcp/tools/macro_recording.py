"""Macro Recording and Playback tools for SolidWorks MCP Server.

Provides tools for recording, managing, and executing SolidWorks macros for automation
and workflow optimization.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    UnsupportedOperationError,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas for macro operations


class MacroRecordingInput(CompatInput):
    """Input schema for macro recording operations.

    Attributes:
        auto_cleanup (bool): The auto cleanup value.
        auto_stop (bool): The auto stop value.
        capture_keyboard (bool): The capture keyboard value.
        capture_mouse (bool): The capture mouse value.
        description (str): The description value.
        macro_name (str | None): The macro name value.
        output_file (str): The output file value.
        recording_mode (str): The recording mode value.
        recording_name (str | None): The recording name value.
        recording_quality (str): The recording quality value.
        timeout_seconds (int): The timeout seconds value.
    """

    macro_name: str | None = Field(
        default=None, description="Name for the recorded macro"
    )
    recording_name: str | None = Field(
        default=None, description="Alternative recording name"
    )
    description: str = Field(
        default="", description="Description of macro functionality"
    )
    output_file: str = Field(description="Output file for the recorded macro")
    recording_mode: str = Field(default="User actions", description="Recording mode")
    capture_mouse: bool = Field(default=True, description="Capture mouse actions")
    capture_keyboard: bool = Field(default=True, description="Capture keyboard actions")
    recording_quality: str = Field(
        default="High", description="Recording quality level"
    )
    auto_cleanup: bool = Field(default=False, description="Cleanup temporary files")
    auto_stop: bool = Field(
        default=False, description="Auto-stop recording after timeout"
    )
    timeout_seconds: int = Field(
        default=300, description="Timeout for auto-stop in seconds"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the macro recording input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.macro_name is None:
            self.macro_name = self.recording_name or "Recorded Macro"


class MacroPlaybackInput(CompatInput):
    """Input schema for macro playback.

    Attributes:
        execution_mode (str | None): The execution mode value.
        execution_parameters (dict[str, Any] | None): The execution parameters value.
        log_execution (bool): The log execution value.
        macro_file (str | None): The macro file value.
        macro_path (str | None): The macro path value.
        parameters (dict[str, Any]): The parameters value.
        pause_between_runs (float): The pause between runs value.
        pause_on_error (bool): The pause on error value.
        repeat_count (int): The repeat count value.
        target_file (str | None): The target file value.
    """

    macro_path: str | None = Field(
        default=None, description="Path to macro file (.swp or .vb)"
    )
    macro_file: str | None = Field(
        default=None, description="Alternative macro file path"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Macro parameters"
    )
    target_file: str | None = Field(default=None, description="Target file")
    execution_mode: str | None = Field(default=None, description="Execution mode")
    pause_on_error: bool = Field(default=False, description="Pause on error")
    log_execution: bool = Field(default=False, description="Log execution")
    execution_parameters: dict[str, Any] | None = Field(
        default=None, description="Execution parameters"
    )
    repeat_count: int = Field(default=1, description="Number of times to execute")
    pause_between_runs: float = Field(
        default=0.0, description="Pause between executions in seconds"
    )


class MacroAnalysisInput(CompatInput):
    """Input schema for macro analysis.

    Attributes:
        analysis_depth (str): The analysis depth value.
        analysis_type (str): The analysis type value.
        macro_file (str | None): The macro file value.
        macro_path (str | None): The macro path value.
        suggest_optimizations (bool): The suggest optimizations value.
    """

    macro_path: str | None = Field(
        default=None, description="Path to macro file to analyze"
    )
    macro_file: str | None = Field(
        default=None, description="Alternative macro file path"
    )
    analysis_type: str = Field(
        default="full", description="Analysis type (full, dependencies, performance)"
    )
    analysis_depth: str = Field(default="Basic", description="Analysis depth alias")
    suggest_optimizations: bool = Field(
        default=False, description="Suggest optimizations"
    )


class MacroBatchInput(CompatInput):
    """Input schema for batch macro operations.

    Attributes:
        execution_order (str): The execution order value.
        file_pattern (str | None): The file pattern value.
        macro_list (list[str]): The macro list value.
        source_directory (str | None): The source directory value.
        stop_on_error (bool): The stop on error value.
        target_directory (str | None): The target directory value.
    """

    macro_list: list[str] = Field(description="List of macro file paths")
    target_directory: str | None = Field(
        default=None, description="Target directory alias"
    )
    source_directory: str | None = Field(
        default=None, description="Source directory alias"
    )
    file_pattern: str | None = Field(default=None, description="File pattern alias")
    execution_order: str = Field(
        default="sequential", description="Execution order (sequential, parallel)"
    )
    stop_on_error: bool = Field(default=True, description="Stop batch if error occurs")


async def register_macro_recording_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register macro recording and playback tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        >>> tool_count = await register_macro_recording_tools(mcp, adapter, config)
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def start_macro_recording(input_data: MacroRecordingInput) -> dict[str, Any]:
        """Start recording a SolidWorks macro.

        This tool initiates macro recording to capture user actions for later playback and
        automation.

        Args:
            input_data (MacroRecordingInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await start_macro_recording(recording_input)
        """
        require_capability(
            adapter,
            "start_macro_recording",
            "Active adapter does not support start_macro_recording; "
            f"no recording of {input_data.macro_name} was started.",
        )
        result = await adapter.start_macro_recording(input_data.model_dump())
        require_success(result, "Failed to start recording")
        return {
            "status": "success",
            "message": f"Macro recording started: {input_data.macro_name}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def stop_macro_recording(input_data: dict[str, Any]) -> dict[str, Any]:
        """Stop macro recording and save the recorded macro.

        This tool stops the active recording session and saves the generated macro code to a
        file.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await stop_macro_recording(stop_input)
        """
        require_capability(
            adapter,
            "stop_macro_recording",
            "No adapter capability exists for stopping a macro "
            "recording; this tool never started a real recording "
            "session, so there is no macro code to save.",
        )
        result = await adapter.stop_macro_recording(input_data)
        require_success(result, "Failed to stop recording")
        return {
            "status": "success",
            "message": "Macro recording completed and saved",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def execute_macro(input_data: MacroPlaybackInput) -> dict[str, Any]:
        """Handle execute macro.

        This tool runs a previously recorded or written macro with optional parameters and
        repeat functionality.

        Args:
            input_data (MacroPlaybackInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await execute_macro(playback_input)
        """

        require_capability(
            adapter,
            "execute_macro",
            "Active adapter does not support execute_macro; "
            f"{input_data.macro_path} was not run, and no features "
            "were created.",
        )
        result = await adapter.execute_macro(input_data.model_dump())
        require_success(result, "Failed to execute macro")
        return {
            "status": "success",
            "message": f"Macro executed {input_data.repeat_count} times successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def analyze_macro(input_data: MacroAnalysisInput) -> dict[str, Any]:
        """Analyze a macro for complexity, dependencies, and optimization opportunities.

        This tool provides insights into macro structure and performance to help with
        optimization and maintenance.

        Args:
            input_data (MacroAnalysisInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await analyze_macro(analysis_input)
        """
        require_capability(
            adapter,
            "analyze_macro",
            "Active adapter does not support analyze_macro; "
            f"{input_data.macro_path} was not analyzed.",
        )
        result = await adapter.analyze_macro(input_data.model_dump())
        require_success(result, "Failed to analyze macro")
        return {
            "status": "success",
            "message": f"Macro analysis completed for {input_data.macro_path}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def batch_execute_macros(input_data: MacroBatchInput) -> dict[str, Any]:
        """Handle batch execute macros.

        This tool allows running multiple macros in sequence or parallel for complex automated
        workflows.

        Args:
            input_data (MacroBatchInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await batch_execute_macros(batch_input)
        """
        payload = (
            input_data.model_dump()
            if hasattr(input_data, "model_dump")
            else dict(input_data)
        )

        if hasattr(adapter, "batch_execute_macros"):
            result = await adapter.batch_execute_macros(payload)
            require_success(result, "Failed batch execution")
            return {
                "status": "success",
                "message": "Batch macro execution completed successfully",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        macro_list = payload.get("macro_list", [])

        raise UnsupportedOperationError(
            "Active adapter does not support batch_execute_macros; "
            f"none of the {len(macro_list)} macro(s) were run."
        )

    @mcp.tool()
    async def optimize_macro(input_data: dict[str, Any]) -> dict[str, Any]:
        """Optimize an existing macro for better performance and reliability.

        This tool analyzes and suggests improvements to existing macro code.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await optimize_macro(optimization_input)
        """
        payload = (
            input_data.model_dump()
            if hasattr(input_data, "model_dump")
            else dict(input_data)
        )

        if hasattr(adapter, "optimize_macro"):
            result = await adapter.optimize_macro(payload)
            require_success(result, "Failed to optimize macro")
            return {
                "status": "success",
                "message": "Macro optimization completed successfully",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        macro_path = payload.get("macro_path") or payload.get("macro_file", "")

        raise UnsupportedOperationError(
            "Active adapter does not support optimize_macro; "
            f"{macro_path} was not analyzed or changed."
        )

    @mcp.tool()
    async def create_macro_library(input_data: dict[str, Any]) -> dict[str, Any]:
        """Create a library of organized macros for team sharing and reuse.

        This tool sets up a structured macro library with categorization, documentation, and
        version control.

        Args:
            input_data (dict[str, Any]): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            >>> result = await create_macro_library(library_input)
        """
        payload = (
            input_data.model_dump()
            if hasattr(input_data, "model_dump")
            else dict(input_data)
        )

        if hasattr(adapter, "create_macro_library"):
            result = await adapter.create_macro_library(payload)
            require_success(result, "Failed to create library")
            return {
                "status": "success",
                "message": "Macro library created successfully",
                "data": result.data,
                "execution_time": result.execution_time,
            }

        library_path = payload.get("library_path", "")

        raise UnsupportedOperationError(
            "Active adapter does not support create_macro_library; "
            f"no library was created at {library_path or '(unspecified path)'}."
        )

    tool_count = 8  # Macro recording and management tools
    return tool_count
