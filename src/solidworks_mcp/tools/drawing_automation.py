"""Drawing-automation tools: model dimensions on drawing views, laid out without overlaps.

Both tools work on the active drawing and call real adapter methods
(``adapters/solidworks/documentation.py``); the layout geometry is in
``adapters/solidworks/dimension_layout.py``.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, Literal, get_type_hints

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

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


class InsertBomTableInput(CompatInput):
    """Input schema for inserting a BOM table.

    Attributes:
        view_name (str): Assembly drawing view the BOM is attached to.
        template_path (str | None): .sldbomtbt template.
        bom_type (str): BOM type.
        x_mm (float | None): Table X position.
        y_mm (float | None): Table Y position.
    """

    view_name: str = Field(description="A view of an assembly, e.g. 'Drawing View1'")
    template_path: str | None = Field(
        default=None, description=".sldbomtbt template; bom-standard when omitted"
    )
    bom_type: Literal["top_level_only", "parts_only", "indented"] = Field(
        default="top_level_only", description="BOM structure"
    )
    x_mm: float | None = Field(
        default=None,
        description="Table X on the sheet (mm); the sheet's BOM anchor when omitted",
    )
    y_mm: float | None = Field(default=None, description="Table Y on the sheet (mm)")


class SetSheetScaleInput(CompatInput):
    """Input schema for the sheet scale.

    Attributes:
        numerator (float): Scale numerator.
        denominator (float): Scale denominator.
    """

    numerator: float = Field(gt=0, description="e.g. 1 for 1:2")
    denominator: float = Field(gt=0, description="e.g. 2 for 1:2")


class GenerateDrawingPackageInput(CompatInput):
    """Input schema for the standard A3 drawing generator.

    Attributes:
        model_path (str): Part or assembly to draw.
        output_dir (str | None): Folder for the .SLDDRW and PDF.
        title (str | None): Title block TITLE (short).
        subtitle (str | None): Sheet title.
        drawing_number (str | None): DWG NO. and file name.
        author (str): DRAWN name.
        revision (str): Revision letter.
        company (str): Company name field.
        notes (list[str]): Extra note lines.
        include_isometric (bool): Add the isometric view.
        write_model_properties (bool): Write title-block properties into the model.
    """

    model_path: str = Field(description="Full path to the .SLDPRT or .SLDASM")
    output_dir: str | None = Field(
        default=None,
        description="Where to save the drawing; the model's folder when omitted",
    )
    title: str | None = Field(
        default=None,
        description="Short title, e.g. 'Mounting Plate - Rev A'; the file name when omitted",
    )
    subtitle: str | None = Field(
        default=None, description="Sheet title, e.g. 'Base support'"
    )
    drawing_number: str | None = Field(
        default=None,
        description="DWG NO., also the drawing file name, e.g. 'MP-RevA-01'",
    )
    author: str = Field(default="", description="DRAWN name")
    revision: str = Field(default="A", description="Revision letter")
    company: str = Field(default="", description="Company name")
    notes: list[str] = Field(
        default_factory=list,
        description="Extra note lines (material, process, connections); 3-7 lines in total",
    )
    include_isometric: bool = Field(default=True, description="Add an isometric view")
    write_model_properties: bool = Field(
        default=True,
        description="Write Description/Material/Weight into the model so the title block shows them, and save it",
    )


def _guard(
    fn: Callable[..., Awaitable[dict[str, Any]]],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Make a tool accept a plain dict and never raise.

    MCP clients send validated models, but direct callers (and the all-tools
    smoke harness) pass raw dicts. The dict is validated into the annotated
    input model; any failure, validation included, becomes an error response.

    Args:
        fn: A tool coroutine taking one ``input_data`` model.

    Returns:
        Callable[..., Awaitable[dict[str, Any]]]: The guarded tool.
    """

    @functools.wraps(fn)
    async def wrapper(input_data: Any = None) -> dict[str, Any]:
        try:
            model = get_type_hints(fn).get("input_data")
            if not isinstance(input_data, BaseModel) and model is not None:
                input_data = model.model_validate(input_data or {})
            return await fn(input_data)
        except AttributeError as e:
            if "has no attribute" not in str(e):
                raise
            return {
                "status": "error",
                "message": f"Active adapter does not support {fn.__name__}; nothing was done.",
            }
        except Exception as e:
            logger.error(f"Error in {fn.__name__} tool: {e}")
            return {
                "status": "error",
                "message": f"Invalid input or unexpected error: {e}",
            }

    return wrapper


async def _run(
    call: Callable[..., Awaitable[Any]], describe: str, *args: Any
) -> dict[str, Any]:
    """Call one adapter method and shape the standard tool response.

    Args:
        call: The bound adapter method, e.g. ``adapter.get_material``.
        describe: Short description used in success / error messages.
        *args: Positional arguments for the adapter method.

    Returns:
        dict[str, Any]: ``status``, ``message`` and, on success, ``data``.
    """
    method = getattr(call, "__name__", "operation")
    try:
        result = await call(*args)
    except Exception as e:
        logger.error(f"Error in {method} tool: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}
    if result.is_success:
        return {
            "status": "success",
            "message": f"Successfully {describe}",
            "data": result.data,
            "execution_time": result.execution_time,
        }
    return {"status": "error", "message": result.error or f"{method} failed"}


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

    @mcp.tool()
    @_guard
    async def insert_bom_table(input_data: InsertBomTableInput) -> dict[str, Any]:
        """Insert a bill-of-materials table for an assembly drawing view."""
        return await _run(
            adapter.insert_bom_table,
            f"inserted a {input_data.bom_type} BOM",
            input_data.view_name,
            input_data.template_path,
            input_data.bom_type,
            input_data.x_mm,
            input_data.y_mm,
        )

    @mcp.tool()
    @_guard
    async def set_sheet_scale(input_data: SetSheetScaleInput) -> dict[str, Any]:
        """Set the active drawing sheet's scale, e.g. 1:2."""
        return await _run(
            adapter.set_sheet_scale,
            f"set sheet scale {input_data.numerator:g}:{input_data.denominator:g}",
            input_data.numerator,
            input_data.denominator,
        )

    @mcp.tool()
    @_guard
    async def generate_drawing_package(
        input_data: GenerateDrawingPackageInput,
    ) -> dict[str, Any]:
        """Create a complete A3 drawing that follows the A3 drafting standard.

        A3 ISO frame with a filled title block (title, drawing number, material,
        weight, drawn by/date, revision); front, plan, side and isometric views in
        cells sized to fill the sheet; model dimensions shown once and laid out in
        rows; bold view-name captions; a NOTES block; nothing overlapping. Saves
        ``<drawing_number>.SLDDRW`` and a PDF.
        """
        return await _run(
            adapter.create_standard_drawing,
            "created the standard drawing",
            input_data.model_path,
            input_data.output_dir,
            input_data.title,
            input_data.subtitle,
            input_data.drawing_number,
            input_data.author,
            input_data.revision,
            input_data.company,
            None,
            input_data.notes,
            input_data.include_isometric,
            input_data.write_model_properties,
        )

    return 5
