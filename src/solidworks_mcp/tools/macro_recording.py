"""Macro Recording and Playback tools for SolidWorks MCP Server.

Provides ``execute_macro``, which runs a binary SolidWorks macro (``.swp``).
"""

import asyncio
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    ToolOperationError,
    normalize_input,
    require_capability,
    with_tool_boundary,
)

# Input schemas for macro operations

# ISldWorks::RunMacro2 runs only binary macros.
_RUNNABLE_MACRO_SUFFIXES = frozenset({".swp", ".swb"})


class MacroPlaybackInput(CompatInput):
    """Input schema for macro playback.

    Attributes:
        macro_file (str | None): The macro file value.
        macro_path (str | None): The macro path value.
        proc_name (str): The procedure to call.
        pause_between_runs (float): The pause between runs value.
        repeat_count (int): The repeat count value.
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
    proc_name: str = Field(
        default="main", description="The macro procedure to call; main by default"
    )
    repeat_count: int = Field(
        default=1,
        ge=1,
        le=100,
        description="How many times to run the macro (1-100); it stops at the first failure",
    )
    pause_between_runs: float = Field(
        default=0.0, ge=0.0, description="Seconds to wait between runs"
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
    async def execute_macro(input_data: MacroPlaybackInput) -> dict[str, Any]:
        """Run a binary SolidWorks macro (.swp, or legacy .swb) in the running SolidWorks, calling its `main` procedure once.

        Use it to run an existing macro file. VBA source (.bas, .vb, plain text, or what
        the `generate_vba_*` tools return) is refused as invalid input before SolidWorks
        sees it. The macro must not wait for the user (no MsgBox or forms), or the call
        hangs. It runs `repeat_count` times, `pause_between_runs` seconds apart, and
        stops at the first run that fails. Needs: SolidWorks running and the macro file
        on disk. Changes: whatever the macro does; it can't be undone from here.
        Returns: `runs_completed` and `data` from the last run, with `macro_path`,
        `module_name`, `proc_name` and `errors`.

        Args:
            input_data: The macro to run. Give `macro_path` (or `macro_file`);
                `proc_name` (main), `repeat_count` (1) and `pause_between_runs` (0 s)
                have defaults.

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
        payload = input_data.model_dump()
        total = input_data.repeat_count
        execution_time = 0.0
        result = None
        for run in range(total):
            if run and input_data.pause_between_runs:
                await asyncio.sleep(input_data.pause_between_runs)
            result = await adapter.execute_macro(payload)
            if not result.is_success:
                raise ToolOperationError(
                    f"Run {run + 1} of {total} failed after {run} completed: "
                    f"{result.error or 'the macro reported an error'}",
                    execution_time=execution_time + (result.execution_time or 0.0),
                    data=result.data,
                )
            execution_time += result.execution_time or 0.0
        runs = "1 run" if total == 1 else f"{total} runs"
        return {
            "status": "success",
            "message": f"Macro completed {runs}",
            "runs_completed": total,
            "data": result.data if result is not None else None,
            "execution_time": execution_time,
        }

    tool_count = 1  # execute_macro
    return tool_count
