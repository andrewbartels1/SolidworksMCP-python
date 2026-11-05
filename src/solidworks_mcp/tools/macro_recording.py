"""Macro Recording and Playback tools for SolidWorks MCP Server.

Provides tools for recording, managing, and executing SolidWorks macros for automation
and workflow optimization.
"""

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    UnsupportedOperationError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas for macro operations

# ISldWorks::RunMacro2 runs only binary macros.
_RUNNABLE_MACRO_SUFFIXES = frozenset({".swp", ".swb"})


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
        default=None,
        description=(
            "Path to a binary SolidWorks macro (.swp, or legacy .swb). "
            "VBA source (.vb, .bas, text) cannot be run directly."
        ),
    )
    macro_file: str | None = Field(
        default=None, description="Alternative to macro_path (.swp or .swb)"
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

    def model_post_init(self, __context: Any) -> None:
        """Reject macro files ``ISldWorks::RunMacro2`` cannot run.

        ``RunMacro2`` only runs binary ``.swp`` (or legacy ``.swb``) macros;
        anything else fails deep inside COM with an opaque error.

        Args:
            __context (Any): The context value.

        Raises:
            ValueError: A macro path is not a ``.swp`` or ``.swb`` file.
        """
        for path in (self.macro_path, self.macro_file):
            if path and Path(path).suffix.lower() not in _RUNNABLE_MACRO_SUFFIXES:
                raise ValueError(
                    f"execute_macro runs only binary SolidWorks macros "
                    f"(.swp or .swb), got {path!r}. VBA source (.vb, .bas or "
                    "text) must be saved as a .swp in the SolidWorks VBA "
                    "editor first."
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
        """Start SolidWorks' macro recorder, to capture what the user does as a macro.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Recording is
        done in SolidWorks today (Tools > Macro > Record). Changes: once available,
        starts a recording session. Returns: once available, the session details under
        `data`.

        Args:
            input_data: The recording. `output_file` (where the macro is saved) is
                required; `macro_name`, `recording_mode`, the capture switches and
                `timeout_seconds` have defaults.

        Returns:
            dict[str, Any]: The session, or a `not_supported` error.
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
        """Stop the macro recorder and save the recorded macro.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Recording is
        done in SolidWorks today (Tools > Macro > Stop). Changes: once available, ends
        the session and writes the macro file. Returns: once available, the saved
        macro's details under `data`.

        Args:
            input_data: A mapping; nothing in it is used yet.

        Returns:
            dict[str, Any]: The saved macro, or a `not_supported` error.
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
        """Run a binary SolidWorks macro (.swp, or legacy .swb) in the running SolidWorks, calling its `main` procedure once.

        Use it to run an existing macro file. VBA source (.bas, .vb, plain text, or what
        the `generate_vba_*` tools return) is refused as invalid input before SolidWorks
        sees it. The macro must not wait for the user (no MsgBox or forms), or the call
        hangs. `repeat_count` is not used yet: the macro runs once, although the message
        counts the repeats. Needs: SolidWorks running and the macro file on disk.
        Changes: whatever the macro does; it can't be undone from here. Returns: `data`
        with `macro_path`, `module_name`, `proc_name` and `errors`.

        Args:
            input_data: The macro to run. Give `macro_path` (or `macro_file`);
                `target_file`, `execution_mode` and the logging switches have
                defaults.

        Returns:
            dict[str, Any]: The run's result.
        """
        input_data = normalize_input(input_data, MacroPlaybackInput)
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
        """Analyse a macro's structure, dependencies and complexity, and suggest optimisations.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only.
        Returns: once available, the findings under `data`.

        Args:
            input_data: The macro. Give `macro_path` (or `macro_file`);
                `analysis_type`, `analysis_depth` and `suggest_optimizations` have
                defaults.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
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
        """Run several macros in sequence against the files in a folder.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To run one
        macro, use `execute_macro`. Changes: once available, whatever the macros do.
        Returns: once available, each run's result under `data`.

        Args:
            input_data: The batch. `macro_list` (macro file paths) is required;
                `target_directory`, `file_pattern`, `execution_order` and
                `stop_on_error` have defaults.

        Returns:
            dict[str, Any]: The results, or a `not_supported` error.
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
        """Suggest improvements to a macro's code for speed and reliability.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Read-only. It
        would suggest changes, not make them. Returns: once available, the suggestions
        under `data`.

        Args:
            input_data: A mapping with the macro's `macro_path` (or `macro_file`).

        Returns:
            dict[str, Any]: The suggestions, or a `not_supported` error.
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
        """Set up a shared folder of categorised, documented macros.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Changes: once
        available, creates the library folder and its index. Returns: once available,
        the library's contents under `data`.

        Args:
            input_data: A mapping with the `library_path` to create.

        Returns:
            dict[str, Any]: The library, or a `not_supported` error.
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
