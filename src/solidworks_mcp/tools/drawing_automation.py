"""Drawing-automation tools: model dimensions, layout, BOM, sheet scale, full drawings.

``generate_drawing_package`` produces a complete A3 drawing that follows the
A3 drafting standard in ``adapters/solidworks/drawing_standard.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from ..adapters.base import SolidWorksAdapter
from .engineering_data import _guard, _run
from .input_compat import CompatInput


class InsertModelDimensionsInput(CompatInput):
    """Input schema for importing model dimensions into drawing views.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
        include_hole_wizard (bool): Also import Hole Wizard location dims.
    """

    view_name: str | None = Field(
        default=None,
        description="One view, e.g. 'Drawing View1'; every view when omitted",
    )
    include_hole_wizard: bool = Field(
        default=True, description="Also import Hole Wizard location dimensions"
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


class ArrangeDimensionsInput(CompatInput):
    """Input schema for arranging drawing dimensions.

    Attributes:
        view_name (str | None): One view, or every view when omitted.
    """

    view_name: str | None = Field(
        default=None,
        description="One view, e.g. 'Drawing View1'; every view when omitted",
    )


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

    @mcp.tool()
    @_guard
    async def insert_model_dimensions(
        input_data: InsertModelDimensionsInput,
    ) -> dict[str, Any]:
        """Bring the model's dimensions into drawing views (auto-dimension).

        Imports the model's "marked for drawing" dimensions and falls back to
        SolidWorks AutoDimension for any view that stays empty. The response
        gives before/after dimension counts and the method used per view.
        """
        return await _run(
            adapter.insert_model_dimensions,
            "inserted model dimensions",
            input_data.view_name,
            input_data.include_hole_wizard,
        )

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
    async def arrange_dimensions(input_data: ArrangeDimensionsInput) -> dict[str, Any]:
        """Move drawing dimensions so nothing overlaps, then verify on the real geometry.

        Dimensions go outside the views in rows (first 8 mm out, rows 7 mm,
        columns 9 mm). Returns an error listing every remaining overlap if the
        rule cannot be met.
        """
        return await _run(
            adapter.arrange_dimensions, "arranged dimensions", input_data.view_name
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
