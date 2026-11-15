"""Template Management tools for SolidWorks MCP Server.

Provides ``compare_templates``, which compares two template files on disk.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .file_facts import file_fact_snapshot
from .input_compat import CompatInput
from .tool_boundary import (
    ToolOperationError,
    with_tool_boundary,
)

# Input schemas for template management


class TemplateComparisonInput(CompatInput):
    """Input schema for comparing templates.

    The six comparison switches it used to take are refused
    (``input_compat.REMOVED_INPUTS``): it compares the files only.

    Attributes:
        template1_path (str): The first template file.
        template2_path (str): The second template file.
    """

    template1_path: str = Field(description="Path to first template")
    template2_path: str = Field(description="Path to second template")


async def register_template_management_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register template management tools with FastMCP.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (Any): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        >>> tool_count = await register_template_management_tools(mcp, adapter, config)
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def compare_templates(input_data: TemplateComparisonInput) -> dict[str, Any]:
        """Compare two template files on disk: whether they are byte-identical, and how their sizes differ.

        Use it to tell whether two templates are the same file. It does not read the
        templates' settings, so it can't say which properties or dimensions differ.
        Needs: both files on disk. Read-only. Returns: `comparison` with `file_1` and
        `file_2` (size, modified time, SHA-256), `identical` and `size_delta_bytes`.

        Args:
            input_data: The two templates: `template1_path` and `template2_path`,
                both required.

        Returns:
            dict[str, Any]: The comparison.
        """
        file_1 = file_fact_snapshot(input_data.template1_path)
        file_2 = file_fact_snapshot(input_data.template2_path)

        missing = [
            path
            for path, snapshot in (
                (input_data.template1_path, file_1),
                (input_data.template2_path, file_2),
            )
            if snapshot is None
        ]
        if missing:
            raise ToolOperationError(
                "Cannot compare templates; file(s) not found on "
                f"disk: {', '.join(missing)}. No template-property "
                "diff was performed."
            )

        assert file_1 is not None
        assert file_2 is not None
        identical = file_1["sha256"] == file_2["sha256"]

        return {
            "status": "success",
            "message": (
                "Template files are byte-identical"
                if identical
                else "Template files differ on disk"
            ),
            "comparison": {
                "file_1": file_1,
                "file_2": file_2,
                "identical": identical,
                "size_delta_bytes": file_2["size_bytes"] - file_1["size_bytes"],
            },
            "note": (
                "This is a filesystem-level comparison only; template "
                "properties, dimensions, and formatting were not "
                "analyzed."
            ),
        }

    tool_count = 1  # compare_templates
    return tool_count
