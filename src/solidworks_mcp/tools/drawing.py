"""Drawing tools for SolidWorks MCP Server.

Provides tools for creating drawing views, adding dimensions, annotations, and managing
technical drawings in SolidWorks.
"""

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from ..adapters.solidworks.drawing_pack import TITLE_BLOCK_FIELDS, parse_scale
from .drawing_check import check
from .input_compat import CompatInput
from .tool_boundary import (
    InvalidInputError,
    normalize_input,
    require_capability,
    require_success,
    with_tool_boundary,
)

# Input schemas using Python 3.14 built-in types


class CreateDrawingViewInput(BaseModel):
    """Input schema for creating drawing views.

    Attributes:
        model_path (str): The model path value.
        orientation (str): The orientation value.
        position_x (float): The position x value.
        position_y (float): The position y value.
        scale (float): The scale value.
        view_type (str): The view type value.
    """

    model_path: str = Field(description="Path to the SolidWorks model file")
    view_type: str = Field(
        description="Type of view (orthographic, isometric, section, detail)"
    )
    position_x: float = Field(default=100.0, description="X position in drawing (mm)")
    position_y: float = Field(default=200.0, description="Y position in drawing (mm)")
    scale: float = Field(default=1.0, description="View scale factor")
    orientation: str = Field(
        default="front", description="View orientation (front, top, right, isometric)"
    )


class AddDimensionInput(CompatInput):
    """Input schema for one drawing dimension.

    Attributes:
        dimension_type (str): horizontal, vertical, aligned, radial, diameter or angular.
        entity1_point (list[float]): [x, y] sheet mm on the first edge or vertex.
        entity2_point (list[float] | None): The second entity, where the type uses two.
        position (list[float]): [x, y] sheet mm for the dimension's text.
    """

    dimension_type: Literal[
        "horizontal", "vertical", "aligned", "radial", "diameter", "angular"
    ] = Field(description="horizontal, vertical, aligned, radial, diameter or angular")
    entity1_point: list[float] = Field(
        description="[x, y] in sheet mm on the first edge or vertex",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    entity2_point: list[float] | None = Field(
        default=None,
        description="[x, y] sheet mm on the second entity: required for angular, "
        "optional for linear types (one edge measures its own length), not for "
        "radial or diameter",
    )
    position: list[float] = Field(
        description="[x, y] in sheet mm for the dimension text",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )

    def model_post_init(self, __context: Any) -> None:
        if self.entity2_point is not None and len(self.entity2_point) != 2:
            raise ValueError("entity2_point is [x, y] in sheet mm")
        if self.dimension_type == "angular" and self.entity2_point is None:
            raise ValueError("an angular dimension needs entity2_point (two lines)")
        if self.dimension_type in ("radial", "diameter") and self.entity2_point:
            raise ValueError(
                f"a {self.dimension_type} dimension takes one circle or arc: "
                "leave out entity2_point"
            )


class AddNoteInput(BaseModel):
    """Input schema for adding notes/annotations.

    Attributes:
        font_size (float): The font size value.
        leader_attachment (str | None): The leader attachment value.
        position_x (float): The position x value.
        position_y (float): The position y value.
        text (str): The text value.
    """

    text: str = Field(description="Note text content")
    position_x: float = Field(description="X position for note")
    position_y: float = Field(description="Y position for note")
    font_size: float = Field(default=12.0, description="Font size in points")
    leader_attachment: str | None = Field(
        default=None, description="Entity to attach leader line to"
    )


class CreateSectionViewInput(CompatInput):
    """Input schema for a section view.

    Attributes:
        view (str): The parent view's name.
        line_start (list[float]): [x, y] sheet mm where the section line starts.
        line_end (list[float]): [x, y] sheet mm where it ends.
        position (list[float]): [x, y] sheet mm for the new view.
        label (str | None): The section letter; the next free one when omitted.
    """

    view: str = Field(description="Parent view's name, from list_drawing_views")
    line_start: list[float] = Field(
        description="[x, y] sheet mm where the section line starts",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    line_end: list[float] = Field(
        description="[x, y] sheet mm where it ends; it must cross the view",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    position: list[float] = Field(
        description="[x, y] sheet mm for the new view's centre",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    label: str | None = Field(
        default=None,
        description="Section letter, e.g. 'A'; the next free one if omitted",
    )


class CreateDetailViewInput(CompatInput):
    """Input schema for a detail view.

    Attributes:
        view (str): The parent view's name.
        center (list[float]): [x, y] sheet mm, inside the view.
        radius (float): The detail circle's radius on the sheet, mm.
        position (list[float]): [x, y] sheet mm for the new view.
        scale (str): The detail's scale, e.g. "3:1".
        label (str | None): The detail letter; the next free one when omitted.
    """

    view: str = Field(description="Parent view's name, from list_drawing_views")
    center: list[float] = Field(
        description="[x, y] sheet mm of the detail circle, inside the view",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    radius: float = Field(gt=0, description="Detail circle radius on the sheet, mm")
    position: list[float] = Field(
        description="[x, y] sheet mm for the new view's centre",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    scale: str = Field(default="2:1", description="Detail scale, e.g. '2:1' or '3:1'")
    label: str | None = Field(
        default=None,
        description="Detail letter, e.g. 'B'; the next free one if omitted",
    )

    def model_post_init(self, __context: Any) -> None:
        parse_scale(self.scale)


class UpdateSheetFormatInput(CompatInput):
    """Input schema for a new sheet format.

    Attributes:
        sheet_format (str): A format name such as "a2 - iso", or a .slddrt path.
        paper_size (str | None): a4 to a0; read from the format name if omitted.
    """

    sheet_format: str = Field(
        description="Sheet format name such as 'a2 - iso', or a .slddrt path"
    )
    paper_size: Literal["a4", "a3", "a2", "a1", "a0"] | None = Field(
        default=None, description="Paper size; read from the format name if omitted"
    )


class UpdateTitleBlockInput(CompatInput):
    """Input schema for title-block fields; give at least one.

    Attributes:
        title (str | None): The drawing's title (the model's Description).
        drawing_number (str | None): The drawing number (DrawingNo).
        drawn_by (str | None): Who drew it.
        drawn_date (str | None): When.
        revision (str | None): The revision, e.g. "B".
        company (str | None): The company name.
    """

    title: str | None = Field(
        default=None, description="Title (the model's Description)"
    )
    drawing_number: str | None = Field(
        default=None, description="Drawing number (the drawing's DrawingNo property)"
    )
    drawn_by: str | None = Field(default=None, description="Drawn by")
    drawn_date: str | None = Field(default=None, description="Date drawn")
    revision: str | None = Field(default=None, description="Revision, e.g. 'B'")
    company: str | None = Field(default=None, description="Company name")

    def model_post_init(self, __context: Any) -> None:
        if not self.fields():
            raise ValueError(
                "give at least one of title, drawing_number, drawn_by, drawn_date, "
                "revision, company"
            )

    def fields(self) -> dict[str, str]:
        """The fields given."""
        return {
            k: v
            for k, v in self.model_dump(include=set(TITLE_BLOCK_FIELDS)).items()
            if v is not None
        }


class AutoDimensionViewInput(CompatInput):
    """Input schema for auto-dimensioning one view.

    Attributes:
        view (str): The view's name.
        scheme (str): baseline or chain.
    """

    view: str = Field(description="View name, from list_drawing_views")
    scheme: Literal["baseline", "chain"] = Field(
        default="baseline", description="baseline or chain, both directions"
    )


class AutoCenterMarksInput(CompatInput):
    """Input schema for auto-inserting drawing centre marks.

    Attributes:
        view_name (str): Name of a view on the active drawing.
        mark_holes (bool): Mark holes / bores.
        mark_fillets (bool): Mark fillets.
        mark_slots (bool): Mark slots.
    """

    view_name: str = Field(
        description="Name of a view on the active drawing, e.g. 'Drawing View1'"
    )
    mark_holes: bool = Field(default=True, description="Mark holes / bores")
    mark_fillets: bool = Field(default=False, description="Mark fillets")
    mark_slots: bool = Field(default=True, description="Mark slots")

    def model_post_init(self, __context: Any) -> None:
        if not self.view_name.strip():
            raise ValueError("view_name is required")


class DrawingCreationInput(CompatInput):
    """Input schema for placing a model's three standard views.

    Attributes:
        model_file (str | None): The model to draw.
        projection (str): third_angle or first_angle.
    """

    model_file: str | None = Field(
        default=None, description="Model file (.sldprt or .sldasm) to draw"
    )
    projection: Literal["third_angle", "first_angle"] = Field(
        default="third_angle",
        description="Projection the views are laid out in",
    )


class DrawingViewInput(CompatInput):
    """Input schema for drawing view operations.

    Attributes:
        drawing_path (str | None): The drawing path value.
        model_file (str | None): The model file value.
        operation (str): The operation value.
        parameters (dict[str, Any]): The parameters value.
        parent_view (str | None): The parent view value.
        position (list[float] | None): The position value.
        scale (str | None): The scale value.
        view_name (str | None): The view name value.
        view_type (str | None): The view type value.
    """

    drawing_path: str | None = Field(default=None, description="Path to drawing file")
    view_name: str | None = Field(default=None, description="Name of the drawing view")
    operation: str = Field(
        default="add",
        description='Only "add" is supported; any other value is refused',
    )
    model_file: str | None = Field(default=None, description="Model file path")
    view_type: str | None = Field(default=None, description="Type of view")
    parent_view: str | None = Field(default=None, description="Parent view alias")
    position: list[float] | None = Field(default=None, description="View position")
    scale: str | None = Field(default=None, description="View scale")
    parameters: dict[str, Any] = Field(default={}, description="View parameters")


class DimensionInput(CompatInput):
    """Input schema for dimension operations.

    Attributes:
        dimension_name (str | None): The dimension name value.
        dimension_type (str | None): The dimension type value.
        drawing_path (str | None): The drawing path value.
        entities (list[str] | None): The entities value.
        entity1 (str | None): The entity1 value.
        entity2 (str | None): The entity2 value.
        operation (str | None): The operation value.
        position (list[float] | None): The position value.
        position_x (float | None): The position x value.
        position_y (float | None): The position y value.
        precision (int): The precision value.
        tolerance (str | None): The tolerance value.
        value (float | None): The value value.
    """

    drawing_path: str | None = Field(default=None, description="Path to drawing file")
    dimension_name: str | None = Field(
        default=None, description="Name of the dimension"
    )
    operation: str | None = Field(
        default="add", description="Operation to perform (add, update, delete)"
    )
    value: float | None = Field(default=None, description="Dimension value")
    dimension_type: str | None = Field(default=None, description="Type of dimension")
    entities: list[str] | None = Field(
        default=None, description="Entities to dimension"
    )
    entity1: str | None = Field(default=None, description="Primary entity alias")
    entity2: str | None = Field(default=None, description="Secondary entity alias")
    position: list[float] | None = Field(default=None, description="Dimension position")
    position_x: float | None = Field(default=None, description="Position X alias")
    position_y: float | None = Field(default=None, description="Position Y alias")
    precision: int = Field(default=2, description="Precision alias")
    tolerance: str | None = Field(default=None, description="Dimension tolerance")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the dimension input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.entities:
            if self.entity1 is None and len(self.entities) >= 1:
                self.entity1 = self.entities[0]
            if self.entity2 is None and len(self.entities) >= 2:
                self.entity2 = self.entities[1]
        if self.position and len(self.position) >= 2:
            if self.position_x is None:
                self.position_x = float(self.position[0])
            if self.position_y is None:
                self.position_y = float(self.position[1])


async def register_drawing_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register drawing tools with FastMCP.

    Registers comprehensive technical drawing tools for SolidWorks automation including view
    creation, dimensioning, annotation, and drawing standards validation. Essential for
    automated documentation workflows.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.drawing import register_drawing_tools

                        tool_count = await register_drawing_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} drawing tools")
                        ```
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def create_drawing_view(input_data: CreateDrawingViewInput) -> dict[str, Any]:
        """Place one named view of a part or assembly on the active drawing sheet.

        Use it to add views one at a time; for the three standard views in one call, use
        `create_technical_drawing`, and for a whole drawing from a model, use
        `generate_drawing_package`.
        Needs: an open, active drawing and the model file on disk. Changes: adds a view
        to the sheet. Returns: `data` with the view's `name`, `orientation`, `position`,
        `scale` and the view counts before and after.

        Args:
            input_data: The view. `model_path` and `view_type` (front, back, left, right, top, bottom, isometric (iso), trimetric, dimetric or current) are
                required; `position_x`/`position_y` (mm on the sheet) and `scale`
                have defaults.

        Returns:
            dict[str, Any]: The placed view.
        """
        require_capability(
            adapter,
            "create_drawing_view",
            "Active adapter does not support create_drawing_view; no "
            f"{input_data.view_type} view of {input_data.model_path} was created.",
        )
        result = await adapter.create_drawing_view(input_data.model_dump())
        require_success(result, "Failed to create drawing view")
        return {
            "status": "success",
            "message": f"Created {input_data.view_type} view of {input_data.model_path}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_dimension(input_data: AddDimensionInput) -> dict[str, Any]:
        """Add one dimension to a drawing view, between edges picked by points on the sheet.

        Give points in sheet mm on a view's edges or vertices (read view outlines with
        `check_drawing`). Two parallel edges give their distance; one edge its length;
        a circle's edge its radius or diameter; two lines their angle. For the model's
        own dimensions use `insert_model_dimensions` instead. Needs: an open, active
        drawing. Changes: adds a reference dimension. Returns: `dimension` with `name`,
        `value` and `units` (mm, deg for angular).

        Args:
            input_data: The dimension. `dimension_type`, `entity1_point` and
                `position` are required; `entity2_point` for two entities.

        Returns:
            dict[str, Any]: The dimension and its measured value.
        """
        input_data = normalize_input(input_data, AddDimensionInput)
        require_capability(
            adapter,
            "add_dimension",
            "Active adapter does not support add_dimension; no dimension was added.",
        )
        result = await adapter.add_dimension(
            input_data.dimension_type,
            input_data.entity1_point,
            input_data.position,
            input_data.entity2_point,
        )
        require_success(result, "Failed to add dimension")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Added a {input_data.dimension_type} dimension: "
            f"{float(data.get('value') or 0):g} {data.get('units', '')}".rstrip(),
            "dimension": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_note(input_data: AddNoteInput) -> dict[str, Any]:
        """Place a text note on the active drawing sheet at a position in millimetres.

        Use it for general notes such as material or finish. For a title block, use
        `generate_drawing_package`, which fills one. Needs: an open, active drawing.
        Changes: adds a note to the sheet. Returns: `data` with `text`, `position`,
        `positioned` (whether the position was applied) and `font_size_points`.

        Args:
            input_data: The note. `text`, `position_x` and `position_y` (mm from
                the sheet's lower-left corner) are required; `font_size` (points)
                has a default.

        Returns:
            dict[str, Any]: The note placed.
        """
        require_capability(
            adapter,
            "add_note",
            "Active adapter does not support add_note; no note was added.",
        )
        result = await adapter.add_note(input_data.model_dump())
        require_success(result, "Failed to add note")
        return {
            "status": "success",
            "message": f"Added note: {input_data.text[:30]}...",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_section_view(input_data: CreateSectionViewInput) -> dict[str, Any]:
        """Cut a section view along a line across a drawing view, and place it on the sheet.

        Give the line's ends in sheet mm so it crosses the view (e.g. through a hole's
        centre), and where the new view goes. A line that misses the view, or a position
        off the sheet, is refused before anything changes. Needs: an open, active drawing
        with that view. Changes: adds a section view and its section line. Returns:
        `view` with `name`, `label`, `parent` and `outline_mm`.

        Args:
            input_data: The section. `view`, `line_start`, `line_end` and `position`
                are required; `label` defaults to the next free letter.

        Returns:
            dict[str, Any]: The new view.
        """
        input_data = normalize_input(input_data, CreateSectionViewInput)
        require_capability(
            adapter,
            "create_section_view",
            "Active adapter does not support create_section_view; no view was added.",
        )
        result = await adapter.create_section_view(
            input_data.view,
            input_data.line_start,
            input_data.line_end,
            input_data.position,
            input_data.label,
        )
        require_success(result, "Failed to create section view")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Added section view {data.get('label')} of {input_data.view}",
            "view": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_detail_view(input_data: CreateDetailViewInput) -> dict[str, Any]:
        """Magnify a circular area of a drawing view as a detail view, at a scale.

        Give the circle's centre (sheet mm, inside the view) and radius, where the new
        view goes, and its scale. A centre outside the view or a position off the sheet
        is refused before anything changes. Needs: an open, active drawing with that
        view. Changes: adds a detail view and its circle. Returns: `view` with `name`,
        `label`, `scale`, `parent` and `outline_mm`.

        Args:
            input_data: The detail. `view`, `center`, `radius` and `position` are
                required; `scale` is 2:1 and `label` the next free letter.

        Returns:
            dict[str, Any]: The new view.
        """
        input_data = normalize_input(input_data, CreateDetailViewInput)
        require_capability(
            adapter,
            "create_detail_view",
            "Active adapter does not support create_detail_view; no view was added.",
        )
        result = await adapter.create_detail_view(
            input_data.view,
            input_data.center,
            input_data.radius,
            input_data.position,
            input_data.scale,
            input_data.label,
        )
        require_success(result, "Failed to create detail view")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Added detail view {data.get('label')} of {input_data.view} "
            f"at {data.get('scale')}",
            "view": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def update_sheet_format(input_data: UpdateSheetFormatInput) -> dict[str, Any]:
        """Change the active drawing sheet's format and paper size, keeping every view.

        Give a format name SolidWorks has (e.g. "a2 - iso") or a .slddrt path; the paper
        size comes from the name unless given. The views are checked to be the same
        afterwards, and the title block keeps its values (they are properties). Needs:
        an open, active drawing. Changes: the sheet's format and size. Returns: `sheet`
        with `sheet_format` (the path), `paper_size`, `sheet_mm` and `views`.

        Args:
            input_data: The format. `sheet_format` is required; `paper_size` optional.

        Returns:
            dict[str, Any]: The sheet afterwards.
        """
        input_data = normalize_input(input_data, UpdateSheetFormatInput)
        require_capability(
            adapter,
            "update_sheet_format",
            "Active adapter does not support update_sheet_format; the sheet was "
            "not changed.",
        )
        result = await adapter.update_sheet_format(
            input_data.sheet_format, input_data.paper_size
        )
        require_success(result, "Failed to update sheet format")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Sheet is now {str(data.get('paper_size', '')).upper()} "
            f"({input_data.sheet_format})",
            "sheet": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def auto_dimension_view(input_data: AutoDimensionViewInput) -> dict[str, Any]:
        """Dimension one drawing view with SolidWorks' auto-dimension (baseline or chain).

        It adds reference dimensions measured from the view's edges; prefer
        `insert_model_dimensions`, which shows the model's own (driving) dimensions, and
        use this for a view that has none to bring in. Dimensions may overlap: run
        `arrange_dimensions` after. It fails when nothing is added. Needs: an open,
        active drawing with that view. Changes: adds dimensions. Returns: `data` with
        `added` and the counts before and after.

        Args:
            input_data: The view. `view` is required; `scheme` is baseline.

        Returns:
            dict[str, Any]: The dimensions added.
        """
        input_data = normalize_input(input_data, AutoDimensionViewInput)
        require_capability(
            adapter,
            "auto_dimension_view",
            "Active adapter does not support auto_dimension_view; no dimensions "
            "were added.",
        )
        result = await adapter.auto_dimension_view(input_data.view, input_data.scheme)
        require_success(result, "Failed to auto-dimension view")
        data = result.data or {}
        return {
            "status": "success",
            "message": f"Added {data.get('added')} dimension(s) to {input_data.view}",
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def check_drawing() -> dict[str, Any]:
        """Check the active drawing is complete before exporting it: views, dimensions, title block, BOM.

        Read-only. Findings: `view_off_sheet` (error), `view_not_dimensioned`
        (warning; isometric and detail views excepted), `title_block_field_empty`
        (warning: title, drawn by, revision), `dangling_annotation` (error) and
        `bom_missing` (warning, an assembly with no BOM). Each names the tool that
        fixes it. It checks completeness, not a drafting standard. Needs: an open,
        active drawing. Returns: `passed` (no errors), `errors`, `warnings`,
        `findings` (each `rule`, `severity`, `message`, maybe `view`), `views` and
        `report` (the facts read).
        """
        require_capability(
            adapter,
            "drawing_report",
            "Active adapter can't read a drawing; nothing was checked.",
        )
        result = await adapter.drawing_report()
        require_success(result, "Failed to read the drawing")
        report = result.data or {}
        verdict = check(report)
        return {
            "status": "success",
            "message": (
                "The drawing passed"
                if verdict["passed"]
                else f"The drawing has {verdict['errors']} error(s)"
            )
            + f", {verdict['warnings']} warning(s)",
            **verdict,
            "report": report,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_technical_drawing(
        input_data: DrawingCreationInput,
    ) -> dict[str, Any]:
        """Place a model's three standard views (front, top and side) on the active drawing sheet in one call.

        Use it to start a drawing's views quickly; for one view, use
        `create_drawing_view`, and to create and save a complete drawing from a model
        file, use `generate_drawing_package`. Views are laid out in `projection`
        (third-angle by default). Needs: an open, active drawing and the model file on
        disk. Changes: adds three views to the sheet. Returns: `data` with `views` (the
        names added), `model_path`, `projection` and the view counts.

        Args:
            input_data: The model to draw. Give `model_file`; `projection` is
                third_angle unless you pass first_angle.

        Returns:
            dict[str, Any]: The views added.
        """
        require_capability(
            adapter,
            "create_technical_drawing",
            "Active adapter does not support create_technical_drawing; "
            "no drawing was created.",
        )
        result = await adapter.create_technical_drawing(input_data.model_dump())
        require_success(result, "Failed to create technical drawing")
        return {
            "status": "success",
            "message": "Technical drawing created successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_drawing_view(input_data: DrawingViewInput) -> dict[str, Any]:
        """Place one named view of a part or assembly on the active drawing sheet; the same as `create_drawing_view`.

        Prefer `create_drawing_view`; this tool reaches the same code and is kept for
        existing callers. It only adds views: an `operation` other than "add" is
        refused. Needs: an open, active drawing and the model file on
        disk. Changes: adds a view to the sheet. Returns: `data` with the view's `name`,
        `orientation`, `position`, `scale` and the view counts.

        Args:
            input_data: The view. Give `model_file` and `view_type` (front, back, left, right, top, bottom, isometric (iso), trimetric, dimetric or current);
                `position` ([x, y] mm on the sheet) and `scale` have defaults.

        Returns:
            dict[str, Any]: The placed view.
        """
        if input_data.operation.strip().lower() != "add":
            raise InvalidInputError(
                f"operation '{input_data.operation}' is not supported: "
                "add_drawing_view only adds views, and the drawing was not changed."
            )
        require_capability(
            adapter,
            "add_drawing_view",
            "Active adapter does not support add_drawing_view; no view was added.",
        )
        result = await adapter.add_drawing_view(input_data.model_dump())
        require_success(result, "Failed to add drawing view")
        return {
            "status": "success",
            "message": "Drawing view added successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def update_title_block(input_data: UpdateTitleBlockInput) -> dict[str, Any]:
        """Change the active drawing's title-block fields: title, drawing number, drawn by, date, revision, company.

        Each field is written to the property the sheet format shows (the same mapping
        `generate_drawing_package` uses): the title is the drawn model's Description,
        the others the drawing's own properties. Fields not given keep their values.
        Needs: an open, active drawing of a model. Changes: those properties. Returns:
        `fields`, each with the `property` written, `on` (drawing or model) and `value`.

        Args:
            input_data: At least one of `title`, `drawing_number`, `drawn_by`,
                `drawn_date`, `revision`, `company`.

        Returns:
            dict[str, Any]: The fields written.
        """
        input_data = normalize_input(input_data, UpdateTitleBlockInput)
        require_capability(
            adapter,
            "update_title_block",
            "Active adapter does not support update_title_block; the title block "
            "was not changed.",
        )
        fields = input_data.fields()
        result = await adapter.update_title_block(fields)
        require_success(result, "Failed to update title block")
        return {
            "status": "success",
            "message": "Title block: "
            + ", ".join(f"{k} = {v}" for k, v in fields.items()),
            "fields": (result.data or {}).get("fields", {}),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def list_drawing_views() -> dict[str, Any]:
        """List the views on the active drawing, by name.

        Use it before `auto_center_marks`, `insert_model_dimensions` or any tool that
        takes a view name. Needs: an open, active drawing. Read-only. Returns: `views`
        (names, sheet formats left out) and `count`.
        """
        result = await adapter.list_drawing_views()
        require_success(result, context="Failed to list drawing views")
        views = list(result.data or [])
        return {
            "status": "success",
            "message": (
                f"{len(views)} view(s): {', '.join(views)}"
                if views
                else "The drawing has no views"
            ),
            "views": views,
            "count": len(views),
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def auto_center_marks(
        input_data: AutoCenterMarksInput,
    ) -> dict[str, Any]:
        """Insert centre marks on the holes, slots and (optionally) fillets of one drawing view.

        Use it after placing views, before dimensioning holes. Adding none is still a
        success: the view may have no unmarked circular edges. Needs: an open drawing
        with the named view (see `list_drawing_views`). Changes: adds centre-mark
        annotations to the view. Returns: `data` with `center_marks_added` and the
        counts before and after.

        Args:
            input_data: The view. `view_name` is required; `mark_holes` and
                `mark_slots` default to on, `mark_fillets` to off.

        Returns:
            dict[str, Any]: The marks added.
        """
        require_capability(
            adapter,
            "auto_center_marks",
            "Active adapter does not support auto_center_marks; "
            "no centre marks were inserted.",
        )
        input_data = normalize_input(input_data, AutoCenterMarksInput)
        result = await adapter.auto_center_marks(
            input_data.view_name,
            input_data.mark_holes,
            input_data.mark_fillets,
            input_data.mark_slots,
        )
        require_success(result, context="Failed to insert centre marks")
        data = result.data if isinstance(result.data, dict) else {}
        added = data.get("center_marks_added")
        return {
            "status": "success",
            "message": (
                f"Inserted {added} centre mark(s) on {input_data.view_name}"
                if isinstance(added, int)
                else f"Ran centre-mark insertion on {input_data.view_name}"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    tool_count = 13  # Number of tools registered
    return tool_count
