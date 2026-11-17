"""Macro Recording and Playback tools for SolidWorks MCP Server.

Provides ``execute_macro``, which runs a SolidWorks macro file (``.swp`` or
``.swb``), or VBA source text when the server allows it.
"""

import asyncio
import tempfile
import uuid
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
        dialog_timeout (float): Seconds a dialog the macro opens may wait
            before it is answered and the run fails.
        vba_source (str | None): The macro's VBA text, instead of a file.
    """

    macro_path: str | None = Field(
        default=None,
        description=(
            "Path to a SolidWorks macro file (.swp, or legacy .swb). For VBA "
            "source text, use vba_source."
        ),
    )
    macro_file: str | None = Field(
        default=None, description="Alternative to macro_path (.swp or .swb)"
    )
    vba_source: str | None = Field(
        default=None,
        min_length=1,
        max_length=200_000,
        description=(
            "The macro's VBA text, instead of a file: written to a .swb and "
            "run. Only when the server allows it (SOLIDWORKS_MCP_ALLOW_VBA_SOURCE)"
        ),
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
    dialog_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=600.0,
        description=(
            "Seconds a dialog the macro opens (MsgBox, form, prompt) may wait "
            "before it is answered with Cancel (or its only button) and the "
            "run fails as macro_waited_for_user"
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        """Reject macro files ``ISldWorks::RunMacro2`` cannot run.

        ``RunMacro2`` only runs binary ``.swp`` (or legacy ``.swb``) macros;
        anything else fails deep inside COM with an opaque error.

        Args:
            __context (Any): The context value.

        Raises:
            ValueError: A macro path is not a ``.swp`` or ``.swb`` file, VBA
                source is given with a file, or the source has characters a
                Windows-1252 text file can't hold.
        """
        if self.vba_source is not None:
            if self.macro_path or self.macro_file:
                raise ValueError(
                    "Give vba_source or a macro file (macro_path), not both."
                )
            try:
                self.vba_source.encode("cp1252")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "vba_source has a character VBA files can't hold "
                    f"({exc.object[exc.start : exc.end]!r}); use plain text."
                ) from exc
        for path in (self.macro_path, self.macro_file):
            if path and Path(path).suffix.lower() not in _RUNNABLE_MACRO_SUFFIXES:
                raise ValueError(
                    f"execute_macro runs only SolidWorks macro files "
                    f"(.swp or .swb), got {path!r}. Pass VBA source as "
                    "vba_source instead (when the server allows it), or save "
                    "it as a .swp in the SolidWorks VBA editor."
                )


#: Why VBA source wasn't run, and how to allow it.
VBA_SOURCE_OFF = (
    "Running VBA source is turned off on this server, so nothing was written "
    "or run. VBA can do anything you can on this computer; to allow it, start "
    "the server with SOLIDWORKS_MCP_ALLOW_VBA_SOURCE=1. Or save the macro as "
    "a .swp in SolidWorks and pass macro_path."
)


def _write_source(source: str, config: Any) -> Path:
    """Write VBA source to a new ``.swb`` file, when the server allows it.

    Args:
        source: The macro's VBA text.
        config: The server configuration (``allow_vba_source``).

    Returns:
        Path: The written file, under ``<temp>/solidworks_mcp/macros``.

    Raises:
        ToolOperationError: Running VBA source isn't allowed.
    """
    if not getattr(config, "allow_vba_source", False):
        raise ToolOperationError(VBA_SOURCE_OFF)
    folder = Path(tempfile.gettempdir()) / "solidworks_mcp" / "macros"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"vba-{uuid.uuid4().hex[:12]}.swb"
    path.write_text(source, encoding="cp1252")
    return path


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
        """Run a SolidWorks macro (.swp, or legacy .swb), or VBA source text, in the running SolidWorks, calling its `main` procedure.

        Use it to run an existing macro file, or VBA you wrote (for example from a
        `generate_vba_*` tool) as `vba_source`. VBA source runs only when the user
        started the server with SOLIDWORKS_MCP_ALLOW_VBA_SOURCE=1; otherwise it is
        refused as `vba_source_off`, so ask the user, never set it yourself. The
        source is written to a .swb file, and the reply gives `source_file` and the
        `vba_source` that ran. The macro must not wait for the user (no MsgBox or
        forms): a dialog still open after `dialog_timeout` seconds (30) is answered
        with Cancel, or its only button, and the run fails as
        `macro_waited_for_user`; a Yes/No prompt is left for the user. It runs
        `repeat_count` times, `pause_between_runs` seconds apart, and stops at the
        first run that fails. Needs: SolidWorks running and the macro file on disk
        (or the setting for source). Changes: whatever the macro does; it can't be
        undone from here. Returns: `runs_completed` and `data` from the last run,
        with `macro_path`, `module_name`, `proc_name` and `errors`.

        Args:
            input_data: The macro to run. Give `macro_path` (or `macro_file`), or
                `vba_source`; `proc_name` (main), `repeat_count` (1),
                `pause_between_runs` (0 s) and `dialog_timeout` (30 s) have
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
        payload = input_data.model_dump()
        if input_data.vba_source is not None:
            payload["macro_path"] = str(_write_source(input_data.vba_source, config))
        total = input_data.repeat_count
        execution_time = 0.0
        result = None
        for run in range(total):
            if run and input_data.pause_between_runs:
                await asyncio.sleep(input_data.pause_between_runs)
            # require_capability above checked the adapter has it.
            result = await adapter.execute_macro(payload)  # type: ignore[attr-defined]
            if not result.is_success:
                raise ToolOperationError(
                    f"Run {run + 1} of {total} failed after {run} completed: "
                    f"{result.error or 'the macro reported an error'}",
                    execution_time=execution_time + (result.execution_time or 0.0),
                    data=result.data,
                )
            execution_time += result.execution_time or 0.0
        runs = "1 run" if total == 1 else f"{total} runs"
        reply: dict[str, Any] = {
            "status": "success",
            "message": f"Macro completed {runs}",
            "runs_completed": total,
            "data": result.data if result is not None else None,
            "execution_time": execution_time,
        }
        if input_data.vba_source is not None:
            reply["source_file"] = payload["macro_path"]
            reply["vba_source"] = input_data.vba_source
        return reply

    tool_count = 1  # execute_macro
    return tool_count
