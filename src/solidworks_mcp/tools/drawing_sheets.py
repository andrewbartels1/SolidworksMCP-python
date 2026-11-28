"""Drawing sheets: list them, add one, and choose the active one (queue item 37).

A drawing's views, dimensions and notes go on its active sheet; these tools
let an agent spread a drawing over several sheets: a general arrangement on
one, details on another.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import AddSheetParameters, SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


class AddSheetInput(CompatInput):
    """Input schema for a new sheet.

    Attributes:
        name (str): The sheet's name.
        sheet_format (str): A format name or ``.slddrt`` path.
        paper_size (str | None): a4 to a0.
        scale (str): e.g. ``1:2``.
        projection (str | None): ``first`` or ``third``.
    """

    name: str = Field(min_length=1, description="The new sheet's name, e.g. 'Details'")
    sheet_format: str = Field(
        default="a3 - iso",
        description="A sheet format by name, e.g. 'a3 - iso' or 'a2 - iso', or a "
        ".slddrt path",
    )
    paper_size: Literal["a4", "a3", "a2", "a1", "a0"] | None = Field(
        default=None,
        description="Paper size; read from the format's name when omitted",
    )
    scale: str = Field(default="1:1", description="Sheet scale, e.g. '1:2' or '2:1'")
    projection: Literal["first", "third"] | None = Field(
        default=None,
        description="'first' or 'third' angle projection; the active sheet's when "
        "omitted",
    )


class ActivateSheetInput(CompatInput):
    """Input schema for choosing the active sheet.

    Attributes:
        name (str): The sheet.
    """

    name: str = Field(min_length=1, description="The sheet, as list_sheets names it")


async def register_drawing_sheet_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: Any
) -> int:
    """Register the drawing sheet tools with FastMCP.

    Args:
        mcp (FastMCP): The server.
        adapter (SolidWorksAdapter): The adapter the tools call.
        config (Any): Configuration values (unused).

    Returns:
        int: How many tools were registered.
    """
    mcp = with_tool_boundary(mcp)

    @mcp.tool()
    async def list_sheets() -> dict[str, Any]:
        """List the active drawing's sheets with each one's paper size, scale and projection, and which is active.

        Views, dimensions and notes go on the active sheet; change it with
        `activate_sheet`. Needs: an open drawing. Read-only. Returns: `sheets`,
        each with `name`, `active`, `paper_mm` [width, height], `scale` and
        `projection`; `count` and `active`.
        """
        require_capability(adapter, "list_sheets", "Active adapter can't read sheets")
        result = await adapter.list_sheets()
        require_success(result, "Failed to list the sheets")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"{data.get('count', 0)} sheet(s); active: {data.get('active')}",
            **data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sheet(input_data: AddSheetInput) -> dict[str, Any]:
        """Add a sheet to the active drawing, with a format, paper size and scale, and make it the active sheet.

        E.g. a second sheet for details at 2:1. The new sheet takes the active
        sheet's projection unless `projection` is given. Fails, changing
        nothing, for a name already used, an unknown format, or a bad scale.
        Then add views with `create_drawing_view`; `activate_sheet` goes back.
        Needs: an open drawing. Changes: adds a sheet. Returns: `added`,
        `sheet_format` and the `sheets` after.

        Args:
            input_data: `name`; `sheet_format`, `paper_size`, `scale` and
                `projection` optional.

        Returns:
            dict[str, Any]: The sheets after.
        """
        input_data = normalize_input(input_data, AddSheetInput)
        require_capability(adapter, "add_sheet", "Active adapter can't add sheets")
        result = await adapter.add_sheet(AddSheetParameters(**input_data.model_dump()))
        require_success(result, "Failed to add the sheet")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Added and activated {data.get('added')}; {data.get('count')} sheet(s)"
            ),
            **data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def activate_sheet(input_data: ActivateSheetInput) -> dict[str, Any]:
        """Make a sheet of the active drawing the active one, so new views and notes go on it.

        Names ignore case; an unknown name fails with the sheets listed. Needs:
        an open drawing. Changes: the active sheet only. Returns: the `sheets`
        and `active`.

        Args:
            input_data: `name`.

        Returns:
            dict[str, Any]: The sheets after.
        """
        input_data = normalize_input(input_data, ActivateSheetInput)
        require_capability(
            adapter, "activate_sheet", "Active adapter can't change sheets"
        )
        result = await adapter.activate_sheet(input_data.name)
        require_success(result, "Failed to activate the sheet")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Active sheet: {data.get('active')}",
            **data,
            "execution_time": result.execution_time,
        }

    return 3
