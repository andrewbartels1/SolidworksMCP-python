"""Drawing-automation tools: model dimensions on drawing views, laid out without overlaps.

Both tools work on the active drawing and call real adapter methods
(``adapters/solidworks/documentation.py``); the layout geometry is in
``adapters/solidworks/dimension_layout.py``.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)


class InsertModelDimensionsInput(CompatInput):
    """Input schema for importing model dimensions into drawing views.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
        include_hole_wizard (bool): Also import Hole Wizard location dims.
    """

    view_name: str | None = Field(
        default=None,
        description="One view, e.g. 'Drawing View1'; every orthographic view "
        "when omitted. Find names with list_drawing_views.",
    )
    include_hole_wizard: bool = Field(
        default=True, description="Also import Hole Wizard location dimensions"
    )


class ArrangeDimensionsInput(CompatInput):
    """Input schema for arranging drawing dimensions.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
    """

    view_name: str | None = Field(
        default=None,
        description="Only move this view's dimensions, e.g. 'Drawing View1'; "
        "every view when omitted. The overlap check always covers the whole sheet.",
    )


async def register_drawing_automation_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register drawing-automation tools with FastMCP.

    Args:
        mcp (FastMCP): The MCP server.
        adapter (SolidWorksAdapter): Adapter used by every tool.
        config (dict[str, Any]): Server configuration (unused).

    Returns:
        int: Number of tools registered.
    """

    mcp = with_tool_boundary(mcp)

    def _supports(method: str) -> None:
        require_capability(
            adapter,
            method,
            f"The active adapter does not support {method}; nothing was done.",
        )

    @mcp.tool()
    async def insert_model_dimensions(
        input_data: InsertModelDimensionsInput | None = None,
    ) -> dict[str, Any]:
        """Bring the model's dimensions into the active drawing's views.

        Imports the model's "marked for drawing" dimensions view by view, each
        dimension shown once on the sheet (a repeat in a later view is
        deleted). Pictorial views (isometric, dimetric, trimetric) are skipped
        unless named. Falls back to SolidWorks AutoDimension only when nothing
        could be imported. SolidWorks places imported dimensions inside the
        views, so run ``arrange_dimensions`` afterwards.

        Args:
            input_data (InsertModelDimensionsInput | None): ``view_name`` for one
                view and ``include_hole_wizard``; omit for every view.

        Returns:
            dict[str, Any]: ``data`` has per-view ``views`` (before/after counts
            and ``duplicates_removed``), ``dimensions_added``,
            ``unique_dimensions``, ``skipped_pictorial_views`` and the ``method``
            used. ``not_found`` for an unknown view; ``wrong_document_type``
            unless a drawing is active.

        Example:
            ```python
            await insert_model_dimensions()
            await insert_model_dimensions({"view_name": "Drawing View1"})
            ```
        """
        input_data = normalize_input(input_data, InsertModelDimensionsInput)
        _supports("insert_model_dimensions")
        result = await adapter.insert_model_dimensions(
            input_data.view_name, input_data.include_hole_wizard
        )
        require_success(result, context="Failed to insert model dimensions")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Added {data.get('dimensions_added', 0)} dimension(s) to "
                f"{len(data.get('views', []))} view(s) ({data.get('method')})"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def arrange_dimensions(
        input_data: ArrangeDimensionsInput | None = None,
    ) -> dict[str, Any]:
        """Move drawing dimensions so nothing overlaps, then check the real result.

        Dimensions go outside their views in rows (first 8 mm from the
        outline, rows 7 mm apart, columns 9 mm apart), shortest span nearest
        the view, each on the side its extension lines start from. One with no
        room on that side stays put and is listed in ``unplaced``. After moving
        them it re-reads every dimension's real text box and lines and checks
        the whole sheet: no text on text, no line through text, no line across
        another view or across its own view, nothing on a view or outside the
        sheet.

        Args:
            input_data (ArrangeDimensionsInput | None): ``view_name`` to move
                only one view's dimensions; omit for every view.

        Returns:
            dict[str, Any]: ``data`` has ``dimensions``, ``moved``,
            ``overlaps_before``, ``overlaps_after`` and ``unplaced``. When any
            overlap remains the call is an error whose ``data`` lists each one
            in ``remaining_overlaps``; try a smaller sheet scale.

        Example:
            ```python
            await insert_model_dimensions()
            await arrange_dimensions()
            ```
        """
        input_data = normalize_input(input_data, ArrangeDimensionsInput)
        _supports("arrange_dimensions")
        result = await adapter.arrange_dimensions(input_data.view_name)
        require_success(result, context="Failed to arrange dimensions", with_data=True)
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Arranged {data.get('dimensions', 0)} dimension(s): "
                f"{data.get('overlaps_before', 0)} overlap(s) before, "
                f"{data.get('overlaps_after', 0)} after"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    return 2
