"""Advanced Drawing Analysis tools for SolidWorks MCP Server.

Provides ``compare_drawing_versions``, which compares two drawing files on disk.
The drawing check that reads a drawing's contents is planned in queue item 12
(``check_drawing``).
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .file_facts import file_fact_snapshot
from .input_compat import CompatInput
from .tool_boundary import (
    ToolOperationError,
    normalize_input,
    with_tool_boundary,
)

# Input schemas for drawing analysis


class DrawingVersionsInput(CompatInput):
    """Input schema for comparing two saved versions of a drawing.

    Attributes:
        drawing_version_1 (str): The first drawing file.
        drawing_version_2 (str): The second drawing file.
    """

    drawing_version_1: str = Field(
        min_length=1, description="Full path to the first drawing file"
    )
    drawing_version_2: str = Field(
        min_length=1, description="Full path to the second drawing file"
    )


async def register_drawing_analysis_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register advanced drawing analysis tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        >>> tool_count = await register_drawing_analysis_tools(mcp, adapter, config)
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def compare_drawing_versions(
        input_data: DrawingVersionsInput,
    ) -> dict[str, Any]:
        """Compare two drawing files on disk: whether they are byte-identical, and how their sizes differ.

        Use it to tell whether a drawing changed between two saved versions. It does not
        open SolidWorks, so it can't say which views, dimensions or notes differ.
        Identical files mean nothing changed, but different files may not: SolidWorks
        writes a different file each time it saves, even with no change. Needs:
        both files on disk. Read-only. Returns: `comparison` with `file_1` and `file_2`
        (size, modified time, SHA-256), `identical` and `size_delta_bytes`.

        Args:
            input_data: Both full paths, `drawing_version_1` and
                `drawing_version_2`; both are required.

        Returns:
            dict[str, Any]: The comparison.
        """
        input_data = normalize_input(input_data, DrawingVersionsInput)
        drawing_v1 = input_data.drawing_version_1
        drawing_v2 = input_data.drawing_version_2

        file_1 = file_fact_snapshot(drawing_v1)
        file_2 = file_fact_snapshot(drawing_v2)

        missing = [
            path
            for path, snapshot in ((drawing_v1, file_1), (drawing_v2, file_2))
            if snapshot is None
        ]
        if missing:
            raise ToolOperationError(
                "Cannot compare drawing versions; file(s) not found "
                f"on disk: {', '.join(missing)}. No SolidWorks-level "
                "diff was performed."
            )

        assert file_1 is not None
        assert file_2 is not None
        identical = file_1["sha256"] == file_2["sha256"]

        return {
            "status": "success",
            "message": (
                "Drawing files are byte-identical"
                if identical
                else "Drawing files differ on disk"
            ),
            "comparison": {
                "file_1": file_1,
                "file_2": file_2,
                "identical": identical,
                "size_delta_bytes": file_2["size_bytes"] - file_1["size_bytes"],
            },
            "note": (
                "This is a filesystem-level comparison only; no "
                "SolidWorks session was opened, so geometric, "
                "dimension, and annotation differences were not "
                "analyzed."
            ),
        }

    tool_count = 1  # compare_drawing_versions
    return tool_count
