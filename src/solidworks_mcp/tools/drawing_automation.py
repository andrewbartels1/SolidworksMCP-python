"""Drawing-automation tools: dimensions, BOM, sheet scale and complete drawings.

Every tool works on SolidWorks through real adapter methods
(``adapters/solidworks/documentation.py`` and ``drawing_standard.py``); the
dimension layout geometry is in ``adapters/solidworks/dimension_layout.py``.
``generate_drawing_package`` makes a complete A3 drawing that follows the
drafting standard in ``drawing_standard.py``.
"""

from __future__ import annotations

from typing import Any, Literal

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

#: Files generate_drawing_package can draw.
_MODEL_SUFFIXES = (".sldprt", ".sldasm")


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

    view_name: str = Field(
        min_length=1,
        description="A view of an assembly, e.g. 'Drawing View1'. Find names "
        "with list_drawing_views.",
    )
    template_path: str | None = Field(
        default=None,
        description=".sldbomtbt template; bom-standard.sldbomtbt from the BOM "
        "templates folder when omitted",
    )
    bom_type: Literal["top_level_only", "parts_only", "indented"] = Field(
        default="top_level_only",
        description="top_level_only: the assembly's own components; parts_only: "
        "every part, sub-assemblies flattened; indented: the tree, numbered by level",
    )
    x_mm: float | None = Field(
        default=None,
        description="Table X on the sheet (mm); the sheet format's BOM anchor "
        "unless x_mm and y_mm are both given",
    )
    y_mm: float | None = Field(default=None, description="Table Y on the sheet (mm)")

    def model_post_init(self, __context: Any) -> None:
        """Refuse a position with only one coordinate.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: When only one of ``x_mm`` and ``y_mm`` is given.
        """
        if (self.x_mm is None) != (self.y_mm is None):
            raise ValueError(
                "give both x_mm and y_mm to place the table, or neither to use "
                "the sheet format's BOM anchor"
            )


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
        subtitle (str | None): Company field when ``company`` is empty.
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
        description="Where to save the drawing and PDF; the model's folder when omitted",
    )
    title: str | None = Field(
        default=None,
        description="Short title, e.g. 'Mounting Plate'; the file name when omitted",
    )
    subtitle: str | None = Field(
        default=None,
        description="Shown in the company field when company is empty, e.g. "
        "'Base support'",
    )
    drawing_number: str | None = Field(
        default=None,
        description="DWG NO., also the drawing file name, e.g. 'MP-RevA-01'; "
        "<MODEL>-Rev<revision>-01 when omitted",
    )
    author: str = Field(default="", description="DRAWN name")
    revision: str = Field(default="A", description="Revision letter")
    company: str = Field(default="", description="Company name")
    notes: list[str] = Field(
        default_factory=list,
        description="Extra note lines after the standard ones (material, units, "
        "projection, deburr); seven lines are shown at most",
    )
    include_isometric: bool = Field(default=True, description="Add an isometric view")
    write_model_properties: bool = Field(
        default=True,
        description="Write Description/Material/Weight into the model so the "
        "title block shows them, and save the model",
    )

    def model_post_init(self, __context: Any) -> None:
        """Refuse a model path that is not a part or assembly.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: When ``model_path`` does not end in ``.sldprt`` or
                ``.sldasm``.
        """
        if not self.model_path.lower().endswith(_MODEL_SUFFIXES):
            raise ValueError(
                f"model_path must be a .SLDPRT or .SLDASM, got {self.model_path!r}"
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

    @mcp.tool()
    async def insert_bom_table(input_data: InsertBomTableInput) -> dict[str, Any]:
        """Insert a bill-of-materials table for a view of an assembly.

        The view must show an assembly; the BOM lists that view's
        configuration. With no position the table snaps to the sheet format's
        BOM anchor, and with no template ``bom-standard.sldbomtbt`` from the
        BOM templates folder is used.

        Args:
            input_data (InsertBomTableInput): ``view_name``, plus optional
                ``template_path``, ``bom_type`` and ``x_mm``/``y_mm``.

        Returns:
            dict[str, Any]: ``data`` has ``view``, ``bom_type``, ``template``,
            ``configuration`` and ``row_count`` (header included).
            ``not_found`` for an unknown view or template;
            ``wrong_document_type`` for a view of a part or when no drawing is
            active.

        Example:
            ```python
            await insert_bom_table({"view_name": "Drawing View1"})
            await insert_bom_table({"view_name": "Drawing View1", "bom_type": "indented"})
            ```
        """
        input_data = normalize_input(input_data, InsertBomTableInput)
        _supports("insert_bom_table")
        result = await adapter.insert_bom_table(
            input_data.view_name,
            input_data.template_path,
            input_data.bom_type,
            input_data.x_mm,
            input_data.y_mm,
        )
        require_success(result, context="Failed to insert the BOM table")
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Inserted a BOM for {data.get('view')} ({data.get('bom_type')}, "
                f"{data.get('row_count')} row(s) including the header)"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_sheet_scale(input_data: SetSheetScaleInput) -> dict[str, Any]:
        """Set the active drawing sheet's scale, e.g. 1:2.

        Views that use the sheet scale (the default) follow it. The scale is
        read back from the sheet, so success means it really changed.

        Args:
            input_data (SetSheetScaleInput): ``numerator`` and ``denominator``,
                both positive.

        Returns:
            dict[str, Any]: ``data`` has ``sheet`` and the ``scale`` read
            back. ``invalid_input`` for a zero or negative value;
            ``wrong_document_type`` unless a drawing is active.

        Example:
            ```python
            await set_sheet_scale({"numerator": 1, "denominator": 2})
            ```
        """
        input_data = normalize_input(input_data, SetSheetScaleInput)
        _supports("set_sheet_scale")
        result = await adapter.set_sheet_scale(
            input_data.numerator, input_data.denominator
        )
        require_success(result, context="Failed to set the sheet scale")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Sheet {data.get('sheet')} is now at {data.get('scale')}",
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def generate_drawing_package(
        input_data: GenerateDrawingPackageInput,
    ) -> dict[str, Any]:
        """Create a complete A3 drawing of a part or assembly, saved with a PDF.

        One call does what otherwise takes a dozen: an A3 ISO sheet with a
        filled title block (title, drawing number, material, weight, drawn
        by/date, revision, company); front, plan and side views in third-angle
        projection plus an isometric, each in its own cell at the largest
        standard scale that fits; the model's dimensions shown once and laid
        out in rows; bold view captions; a NOTES block; and a check that
        nothing overlaps. Saves ``<drawing_number>.SLDDRW`` and a PDF.

        Args:
            input_data (GenerateDrawingPackageInput): ``model_path``, plus the
                title-block fields, extra ``notes``, ``output_dir`` and
                whether to add the isometric view.

        Returns:
            dict[str, Any]: ``data`` has ``drawing_path``, ``pdf_path``,
            ``drawing_number``, ``scale``, ``views`` (role and caption),
            ``dimensions``, ``overlap_check``, ``properties_written`` and each
            build ``steps`` outcome. ``not_found`` for a missing model or
            sheet format; ``invalid_input`` for a file that isn't a part or
            assembly. An error keeps the data when a step failed, a file was
            not written or an overlap remains.

        Example:
            ```python
            await generate_drawing_package({
                "model_path": "C:/parts/bracket.SLDPRT",
                "title": "Bracket",
                "author": "A. Bartels",
                "notes": ["Break all edges 0.5 mm"],
            })
            ```
        """
        input_data = normalize_input(input_data, GenerateDrawingPackageInput)
        _supports("create_standard_drawing")
        result = await adapter.create_standard_drawing(
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
        require_success(
            result, context="Failed to generate the drawing package", with_data=True
        )
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Saved {data.get('drawing_path')} and its PDF at "
                f"{data.get('scale')}, with no overlaps"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    return 5
