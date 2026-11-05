"""Drawing-automation tools: model dimensions on drawing views, laid out without overlaps.

The tools call real adapter methods (``adapters/solidworks/documentation.py``
and ``adapters/solidworks/drawing_standard.py``); the layout geometry is in
``adapters/solidworks/dimension_layout.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field, field_validator

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


class AddGtolInput(CompatInput):
    """Input schema for a GD&T feature control frame.

    Attributes:
        characteristic (str): The geometric characteristic.
        tolerance (float): Tolerance value in drawing units.
        diameter_zone (bool): Ø before the tolerance.
        material_condition (str): none, mmc or lmc.
        datums (list[str]): Datum letters, primary first.
        x_mm (float): Frame position on the sheet.
        y_mm (float): Frame position on the sheet.
        attach_x_mm (float | None): A point on the edge the leader points to.
        attach_y_mm (float | None): A point on the edge the leader points to.
        dimension_view (str | None): View holding the dimension to attach to.
        dimension_name (str | None): Model dimension to attach to.
    """

    characteristic: Literal[
        "position",
        "flatness",
        "perpendicularity",
        "parallelism",
        "profile_surface",
        "concentricity",
    ] = Field(description="Geometric characteristic")
    tolerance: float = Field(gt=0, description="Tolerance value, e.g. 0.2")
    diameter_zone: bool = Field(
        default=False, description="Cylindrical zone: Ø before the tolerance"
    )
    material_condition: Literal["none", "mmc", "lmc"] = Field(
        default="none", description="Material condition modifier"
    )
    datums: list[str] = Field(
        default_factory=list, max_length=3, description="Datum letters, primary first"
    )
    x_mm: float = Field(
        default=0.0,
        description="Frame X on the sheet (mm); not used when on a dimension",
    )
    y_mm: float = Field(
        default=0.0,
        description="Frame Y on the sheet (mm); not used when on a dimension",
    )
    attach_x_mm: float | None = Field(
        default=None, description="X of a point on the edge the leader points to"
    )
    attach_y_mm: float | None = Field(
        default=None, description="Y of a point on the edge the leader points to"
    )
    dimension_view: str | None = Field(
        default=None, description="View holding the dimension to attach to"
    )
    dimension_name: str | None = Field(
        default=None,
        description="Model dimension to attach to, e.g. 'D3@Sketch1' (see "
        "list_model_dimensions); the frame sits under its text",
    )

    def attach_point(self) -> tuple[float, float] | None:
        """The leader's attach point, when both coordinates are given."""
        if self.attach_x_mm is None or self.attach_y_mm is None:
            return None
        return (self.attach_x_mm, self.attach_y_mm)

    def attach_dimension(self) -> tuple[str, str] | None:
        """``(view, dimension)`` to attach to, when both are given."""
        if not self.dimension_view or not self.dimension_name:
            return None
        return (self.dimension_view, self.dimension_name)


class AddDatumTagInput(CompatInput):
    """Input schema for a datum feature symbol.

    Attributes:
        label (str): The datum letter.
        attach_x_mm (float): A point on the edge it marks.
        attach_y_mm (float): A point on the edge it marks.
        x_mm (float): Tag position on the sheet.
        y_mm (float): Tag position on the sheet.
    """

    label: str = Field(min_length=1, max_length=1, description="Datum letter, e.g. 'A'")
    attach_x_mm: float = Field(description="X of a point on the edge it marks (mm)")
    attach_y_mm: float = Field(description="Y of a point on the edge it marks (mm)")
    x_mm: float = Field(description="Tag X on the sheet (mm)")
    y_mm: float = Field(description="Tag Y on the sheet (mm)")


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
        title_block_text_height_mm (float | None): Cap on DWG NO./TITLE text height.
        include_bom (bool): Put a BOM above the isometric view (assemblies).
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
    title_block_text_height_mm: float | None = Field(
        default=None,
        gt=0,
        description="Largest text height (mm) for the title block's DWG NO. and "
        "TITLE, e.g. 3 for smaller text. By default they keep the sheet "
        "format's height and are only shrunk to fit their boxes.",
    )
    include_bom: bool = Field(
        default=False,
        description="Assemblies only: put a bill of materials in the top of the "
        "isometric view's cell, with the isometric fitted below it",
    )

    @field_validator("model_path")
    @classmethod
    def _part_or_assembly(cls, value: str) -> str:
        """Only parts and assemblies can be drawn."""
        if not value.strip().lower().endswith((".sldprt", ".sldasm")):
            raise ValueError(
                "model_path must be a part (.SLDPRT) or assembly (.SLDASM)"
            )
        return value


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
        """Bring the model's dimensions into the active drawing's views, each dimension shown once.

        Imports the model's "marked for drawing" dimensions view by view; a repeat in a
        later view is deleted. Pictorial views (isometric, dimetric, trimetric) are
        skipped unless named. Falls back to SolidWorks AutoDimension only when nothing
        could be imported. SolidWorks places them inside the views, so run
        `arrange_dimensions` next. Needs: an open, active drawing with views. Changes:
        adds dimensions to the views. Returns: `data` with per-view `views`
        (before/after counts, `duplicates_removed`), `dimensions_added`,
        `unique_dimensions`, `skipped_pictorial_views` and the `method` used. An unknown
        view is `not_found`.

        Args:
            input_data: Which views. Nothing is required: give `view_name` for one
                view, or omit it for every view; `include_hole_wizard` has a default.

        Returns:
            dict[str, Any]: The dimensions added.
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
        """Move drawing dimensions out of their views into tidy rows so nothing overlaps, then check the sheet.

        Rows start 8 mm outside each view, 7 mm apart, shortest span nearest the view. A
        dimension with no room stays put and is listed in `unplaced`. The check reads
        back every text box and line: no text on text, no line through text or across a
        view, nothing off the sheet. Use it after `insert_model_dimensions`. Needs: an
        open, active drawing. Changes: moves dimensions on the sheet. Returns: `data`
        with `dimensions`, `moved`, `overlaps_before`, `overlaps_after` and `unplaced`.
        If any overlap remains the call is an error whose `data` lists
        `remaining_overlaps`; try a smaller sheet scale (`set_sheet_scale`).

        Args:
            input_data: Which views. Nothing is required: give `view_name` for one
                view's dimensions, or omit it for every view.

        Returns:
            dict[str, Any]: The arrangement and its check.
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
    async def insert_bom_table(
        input_data: InsertBomTableInput | None = None,
    ) -> dict[str, Any]:
        """Insert a bill-of-materials table for an assembly view on the active drawing.

        Use it on an assembly drawing after placing a view of the assembly (see
        `list_drawing_views` for view names). Needs: an open, active drawing with a view
        of an assembly. Changes: adds a BOM table to the sheet. Returns: `data` with
        `view`, `bom_type`, `template` and `row_count`. An unknown view is `not_found`
        and the message lists the views.

        Args:
            input_data: The table. `view_name` (a view of an assembly) is
                required; `bom_type` ("top_level_only", "parts_only" or "indented"),
                `template_path` and the position `x_mm`/`y_mm` (the sheet's BOM
                anchor when omitted) have defaults.

        Returns:
            dict[str, Any]: The table inserted.
        """
        _supports("insert_bom_table")
        input_data = normalize_input(input_data, InsertBomTableInput)
        result = await adapter.insert_bom_table(
            input_data.view_name,
            input_data.template_path,
            input_data.bom_type,
            input_data.x_mm,
            input_data.y_mm,
        )
        require_success(result, context="Failed to insert the BOM table")
        return {
            "status": "success",
            "message": f"Inserted a {input_data.bom_type} BOM on {input_data.view_name}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_gtol(input_data: AddGtolInput | None = None) -> dict[str, Any]:
        """Add a GD&T feature control frame to the active drawing, e.g. position Ø0.2 (M) to A|B|C.

        Attach it to a drawing dimension (`dimension_view` + `dimension_name`; the frame
        sits under the dimension's text, the usual place for a hole's position
        tolerance), or place it at `x_mm`/`y_mm` with an optional leader to the edge at
        `attach_x_mm`/`attach_y_mm`. Add the datums it refers to with `add_datum_tag`.
        Needs: an open, active drawing. Changes: adds the frame. Returns: `data`, the
        frame as read back from SolidWorks. No edge at the attach point is `not_found`.

        Args:
            input_data: The frame. `characteristic` (position, flatness,
                perpendicularity, parallelism, profile_surface or concentricity) and
                `tolerance` are required, plus either the dimension or the sheet
                position; `diameter_zone`, `material_condition` (none, mmc, lmc) and
                up to three `datums` (primary first) have defaults.

        Returns:
            dict[str, Any]: The frame added.
        """
        _supports("add_gtol")
        input_data = normalize_input(input_data, AddGtolInput)
        attach = input_data.attach_point()
        result = await adapter.add_gtol(
            input_data.characteristic,
            input_data.tolerance,
            input_data.x_mm,
            input_data.y_mm,
            input_data.diameter_zone,
            input_data.material_condition,
            input_data.datums,
            attach,
            input_data.attach_dimension(),
        )
        require_success(result, context="Failed to add the feature control frame")
        return {
            "status": "success",
            "message": (
                f"Added a {input_data.characteristic} frame "
                f"({input_data.tolerance:g}"
                + (f" to {'|'.join(input_data.datums)}" if input_data.datums else "")
                + ")"
            ),
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_datum_tag(
        input_data: AddDatumTagInput | None = None,
    ) -> dict[str, Any]:
        """Add a datum feature symbol (A, B, C, ...) on an edge of the active drawing.

        Use it to mark the datums a feature control frame from `add_gtol` refers to.
        Needs: an open, active drawing with an edge at the attach point. Changes: adds
        the datum tag. Returns: `data` with the `label` as read back. No edge at the
        point is `not_found`.

        Args:
            input_data: The tag. `label` (one letter), `attach_x_mm`/`attach_y_mm`
                (a point on the edge it marks) and `x_mm`/`y_mm` (where the tag
                goes) are all required, in mm on the sheet.

        Returns:
            dict[str, Any]: The tag added.
        """
        _supports("add_datum_tag")
        input_data = normalize_input(input_data, AddDatumTagInput)
        result = await adapter.add_datum_tag(
            input_data.label,
            (input_data.attach_x_mm, input_data.attach_y_mm),
            input_data.x_mm,
            input_data.y_mm,
        )
        require_success(result, context="Failed to add the datum tag")
        return {
            "status": "success",
            "message": f"Added datum {input_data.label.strip().upper()}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_sheet_scale(
        input_data: SetSheetScaleInput | None = None,
    ) -> dict[str, Any]:
        """Set the active drawing sheet's scale, e.g. 1:2; views that use the sheet scale follow it.

        Use it when views are too large for the sheet, or when `arrange_dimensions`
        reports overlaps it can't clear. Needs: an open, active drawing. Changes: the
        sheet scale. Returns: `data` with the `sheet` name and the new `scale`.

        Args:
            input_data: The scale. `numerator` and `denominator` are required and
                must be above zero, e.g. 1 and 2 for 1:2.

        Returns:
            dict[str, Any]: The new scale.
        """
        _supports("set_sheet_scale")
        input_data = normalize_input(input_data, SetSheetScaleInput)
        result = await adapter.set_sheet_scale(
            input_data.numerator, input_data.denominator
        )
        require_success(result, context="Failed to set the sheet scale")
        return {
            "status": "success",
            "message": f"Sheet scale set to {(result.data or {}).get('scale')}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def generate_drawing_package(
        input_data: GenerateDrawingPackageInput | None = None,
    ) -> dict[str, Any]:
        """Create a complete A3 drawing of a part or assembly in one call, and save it with a PDF.

        It opens a new drawing with an A3 ISO frame and fills the title block (title,
        number, material, weight, drawn by, date, revision). It places front, plan, side
        and isometric views at one standard scale, shows the model dimensions once in
        tidy rows, and adds view captions and a NOTES block. Then it checks nothing
        overlaps. Use it instead of the step-by-step drawing tools when you want the
        whole drawing. Needs: the model file on disk. Changes: saves
        `<drawing_number>.SLDDRW` and a PDF, replacing files of those names, and by
        default writes Description, Material and Weight into the model and saves it
        (turn off with `write_model_properties`). Returns: `data` with `scale`, `views`,
        `dimensions`, `overlap_check`, `title_block`, `drawing_path`, `pdf_path` and
        `steps`. A remaining overlap makes the call an error carrying that data; for
        long title-block text pass `title_block_text_height_mm` (e.g. 3).

        Args:
            input_data: The drawing. `model_path` (.sldprt or .sldasm) is
                required; `output_dir`, the title-block fields (`title`,
                `drawing_number`, `author`, `revision`, `company`), `notes`,
                `include_isometric`, `include_bom` and `write_model_properties` have
                defaults.

        Returns:
            dict[str, Any]: The drawing and its check.
        """
        require_capability(
            adapter,
            "create_standard_drawing",
            "The active adapter does not support generate_drawing_package; "
            "nothing was done.",
        )
        input_data = normalize_input(input_data, GenerateDrawingPackageInput)
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
            input_data.title_block_text_height_mm,
            input_data.include_bom,
        )
        require_success(
            result, context="Failed to create the standard drawing", with_data=True
        )
        data = result.data or {}
        return {
            "status": "success",
            "message": (
                f"Created {data.get('drawing_path')} at {data.get('scale')} "
                f"with PDF {data.get('pdf_path')}"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    return 7
