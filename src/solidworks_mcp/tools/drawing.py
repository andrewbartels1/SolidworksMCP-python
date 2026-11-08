"""Drawing tools for SolidWorks MCP Server.

Provides tools for creating drawing views, adding dimensions, annotations, and managing
technical drawings in SolidWorks.
"""

from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    UnsupportedOperationError,
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


class AddDimensionInput(BaseModel):
    """Input schema for adding dimensions.

    Attributes:
        dimension_type (str): The dimension type value.
        entity1 (str): The entity1 value.
        entity2 (str | None): The entity2 value.
        position_x (float): The position x value.
        position_y (float): The position y value.
        precision (int): The precision value.
    """

    dimension_type: str = Field(
        description="Type of dimension (linear, radial, angular, diameter)"
    )
    entity1: str = Field(description="First entity to dimension (edge, face, point)")
    entity2: str | None = Field(
        default=None, description="Second entity for linear/angular dimensions"
    )
    position_x: float = Field(description="X position for dimension text")
    position_y: float = Field(description="Y position for dimension text")
    precision: int = Field(default=2, description="Number of decimal places")


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


class CreateSectionViewInput(BaseModel):
    """Input schema for creating section views.

    Attributes:
        label (str): The label value.
        scale (float): The scale value.
        section_line_end (list[float]): The section line end value.
        section_line_start (list[float]): The section line start value.
        view_position_x (float): The view position x value.
        view_position_y (float): The view position y value.
    """

    section_line_start: list[float] = Field(
        description="Start point of section line as [x, y]",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    section_line_end: list[float] = Field(
        description="End point of section line as [x, y]",
        min_length=2,
        max_length=2,
        json_schema_extra={"items": {"type": "number"}},
    )
    view_position_x: float = Field(description="X position for section view")
    view_position_y: float = Field(description="Y position for section view")
    scale: float = Field(default=1.0, description="Section view scale")
    label: str = Field(default="A", description="Section view label")


class CreateDetailViewInput(BaseModel):
    """Input schema for creating detail views.

    Attributes:
        center_x (float): The center x value.
        center_y (float): The center y value.
        label (str): The label value.
        radius (float): The radius value.
        scale (float): The scale value.
        view_position_x (float): The view position x value.
        view_position_y (float): The view position y value.
    """

    center_x: float = Field(description="X center of detail circle")
    center_y: float = Field(description="Y center of detail circle")
    radius: float = Field(description="Radius of detail circle")
    view_position_x: float = Field(description="X position for detail view")
    view_position_y: float = Field(description="Y position for detail view")
    scale: float = Field(default=2.0, description="Detail view scale")
    label: str = Field(default="A", description="Detail view label")


class UpdateSheetFormatInput(BaseModel):
    """Input schema for updating sheet format.

    Attributes:
        approved_by (str): The approved by value.
        checked_by (str): The checked by value.
        drawing_number (str): The drawing number value.
        drawn_by (str): The drawn by value.
        format_file (str): The format file value.
        sheet_size (str): The sheet size value.
        title (str): The title value.
    """

    format_file: str = Field(description="Path to sheet format template (.slddrt)")
    sheet_size: str = Field(default="A3", description="Sheet size (A4, A3, A2, A1, A0)")
    title: str = Field(default="", description="Drawing title")
    drawn_by: str = Field(default="", description="Drawn by field")
    checked_by: str = Field(default="", description="Checked by field")
    approved_by: str = Field(default="", description="Approved by field")
    drawing_number: str = Field(default="", description="Drawing number")


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
    """Input schema for creating a new drawing.

    Attributes:
        auto_populate_views (bool): The auto populate views value.
        model_file (str | None): The model file value.
        output_path (str | None): The output path value.
        scale (str): The scale value.
        sheet_format (str | None): The sheet format value.
        sheet_size (str): The sheet size value.
        template (str | None): The template value.
        title (str): The title value.
    """

    template: str | None = Field(default=None, description="Drawing template file path")
    model_file: str | None = Field(
        default=None, description="Model file to create drawing from"
    )
    sheet_size: str = Field(default="A3", description="Sheet size")
    title: str = Field(default="", description="Drawing title")
    output_path: str | None = Field(default=None, description="Output drawing path")
    sheet_format: str | None = Field(default=None, description="Sheet format")
    scale: str = Field(default="1:1", description="Drawing scale")
    auto_populate_views: bool = Field(
        default=False, description="Automatically populate standard views"
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
        default="add", description="Operation to perform (create, update, delete)"
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


class AnnotationInput(CompatInput):
    """Input schema for annotation operations.

    Attributes:
        annotation_type (str): The annotation type value.
        approved_by (str): The approved by value.
        checked_by (str): The checked by value.
        drawing_number (str): The drawing number value.
        drawing_path (str | None): The drawing path value.
        drawn_by (str): The drawn by value.
        font_size (float): The font size value.
        leader_attachment (str | None): The leader attachment value.
        position (list[float] | None): The position value.
        position_x (float | None): The position x value.
        position_y (float | None): The position y value.
        text (str): The text value.
    """

    drawing_path: str | None = Field(default=None, description="Path to drawing file")
    annotation_type: str = Field(
        description="Type of annotation (note, balloon, surface_finish, etc.)"
    )
    text: str = Field(description="Annotation text content")
    position_x: float | None = Field(
        default=None, description="X position for annotation"
    )
    position_y: float | None = Field(
        default=None, description="Y position for annotation"
    )
    position: list[float] | None = Field(
        default=None, description="Annotation position"
    )
    font_size: float = Field(default=12.0, description="Font size in points")
    leader_attachment: str | None = Field(
        default=None, description="Entity to attach leader line to"
    )
    drawn_by: str = Field(default="", description="Drawn by field")
    checked_by: str = Field(default="", description="Checked by field")
    approved_by: str = Field(default="", description="Approved by field")
    drawing_number: str = Field(default="", description="Drawing number")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the annotation input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        if self.position is not None and len(self.position) >= 2:
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
        `generate_drawing_package`. `add_drawing_view` does the same as this tool.
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
        """Add one dimension between drawing entities at a position on the sheet.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. To bring the
        model's own dimensions into a drawing today, use `insert_model_dimensions`.
        Changes: once available, adds a dimension to the drawing. Returns: once
        available, the dimension under `data`.

        Args:
            input_data: The dimension. `dimension_type`, `entity1`, `position_x`
                and `position_y` are required; `entity2` and `precision` have
                defaults.

        Returns:
            dict[str, Any]: The dimension, or a `not_supported` error.
        """
        payload = input_data.model_dump()
        dimension_type = payload["dimension_type"]

        require_capability(
            adapter,
            "add_dimension",
            f"Active adapter does not support add_dimension; no "
            f"{dimension_type} dimension was added.",
        )
        result = await adapter.add_dimension(payload)
        require_success(result, "Failed to add dimension")
        return {
            "status": "success",
            "message": "Dimension added successfully",
            "data": result.data,
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
        """Cut a section view along a line across a drawing view.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Use
        SolidWorks directly (Insert > Drawing View > Section). Changes: once available,
        adds a section view. Returns: once available, the view under `data`.

        Args:
            input_data: The section. `section_line_start`, `section_line_end`,
                `view_position_x` and `view_position_y` are required; `scale` and
                `label` have defaults.

        Returns:
            dict[str, Any]: The view, or a `not_supported` error.
        """
        raise UnsupportedOperationError(
            "No adapter capability exists for cutting a section view "
            "along a section line; create_section_view cannot compute "
            "the cut geometry, so no view was created. Use SolidWorks "
            "directly (Insert > Drawing View > Section) instead."
        )

    @mcp.tool()
    async def create_detail_view(input_data: CreateDetailViewInput) -> dict[str, Any]:
        """Magnify a circular area of a drawing view as a detail view.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Use
        SolidWorks directly (Insert > Drawing View > Detail). Changes: once available,
        adds a detail view. Returns: once available, the view under `data`.

        Args:
            input_data: The detail. `center_x`, `center_y`, `radius`,
                `view_position_x` and `view_position_y` are required; `scale` and
                `label` have defaults.

        Returns:
            dict[str, Any]: The view, or a `not_supported` error.
        """
        raise UnsupportedOperationError(
            "No adapter capability exists for magnifying the "
            "geometry inside a detail circle; create_detail_view "
            "cannot compute the detail geometry, so no view was "
            "created. Use SolidWorks directly (Insert > Drawing "
            "View > Detail) instead."
        )

    @mcp.tool()
    async def update_sheet_format(input_data: UpdateSheetFormatInput) -> dict[str, Any]:
        """Change the active drawing's sheet format file and title-block fields.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release.
        `generate_drawing_package` sets the sheet format and fills the title block when
        it creates a drawing. Changes: once available, replaces the sheet format.
        Returns: once available, the new format under `data`.

        Args:
            input_data: The format. `format_file` is required; `sheet_size` and
                the title-block fields have defaults.

        Returns:
            dict[str, Any]: The format, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "update_sheet_format",
            "Active adapter does not support update_sheet_format; the "
            "sheet format and title block were not changed.",
        )
        result = await adapter.update_sheet_format(input_data.model_dump())
        require_success(result, "Failed to update sheet format")
        return {
            "status": "success",
            "message": f"Updated sheet format to {input_data.sheet_size}",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def auto_dimension_view(input_data: dict[str, Any]) -> dict[str, Any]:
        """Dimension a drawing view automatically with SolidWorks' auto-dimension scheme.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. Use
        `insert_model_dimensions` and then `arrange_dimensions` today. Changes: once
        available, adds dimensions to the view. Returns: once available, the dimensions
        added under `data`.

        Args:
            input_data: A mapping with the `view_name` to dimension.

        Returns:
            dict[str, Any]: The dimensions, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "auto_dimension_view",
            "Active adapter does not support auto_dimension_view; no "
            "dimensions were added.",
        )
        result = await adapter.auto_dimension_view(input_data)
        require_success(result, "Failed to auto-dimension view")
        return {
            "status": "success",
            "message": "Auto-dimensioned drawing view",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def check_drawing_standards(input_data: dict[str, Any]) -> dict[str, Any]:
        """Check the active drawing against a drafting standard and score it.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. SolidWorks
        Design Checker does this today. Read-only. Returns: once available, the findings
        under `data`.

        Args:
            input_data: A mapping with the `standard` to check against.

        Returns:
            dict[str, Any]: The findings, or a `not_supported` error.
        """
        raise UnsupportedOperationError(
            "No adapter capability exists for checking drafting "
            "standards compliance; check_drawing_standards cannot "
            "inspect the drawing, so no compliance score was "
            "computed. Use SolidWorks Design Checker for this."
        )

    @mcp.tool()
    async def create_technical_drawing(
        input_data: DrawingCreationInput,
    ) -> dict[str, Any]:
        """Place a model's three standard views (front, top and side) on the active drawing sheet in one call.

        Use it to start a drawing's views quickly; for one view, use
        `create_drawing_view`, and to create and save a complete drawing from a model
        file, use `generate_drawing_package`. Views are laid out in third-angle
        projection. The template, sheet size, title and output path fields are not used
        yet. Needs: an open, active drawing and the model file on disk. Changes: adds
        three views to the sheet. Returns: `data` with `views` (the names added),
        `model_path`, `projection` and the view counts.

        Args:
            input_data: The model to draw. Give `model_file`; the other fields have
                defaults and are not used yet.

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
        existing callers. It only adds views: `operation` values to update or remove a
        view are not acted on. Needs: an open, active drawing and the model file on
        disk. Changes: adds a view to the sheet. Returns: `data` with the view's `name`,
        `orientation`, `position`, `scale` and the view counts.

        Args:
            input_data: The view. Give `model_file` and `view_type` (front, back, left, right, top, bottom, isometric (iso), trimetric, dimetric or current);
                `position` ([x, y] mm on the sheet) and `scale` have defaults.

        Returns:
            dict[str, Any]: The placed view.
        """
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
    async def add_annotation(input_data: AnnotationInput) -> dict[str, Any]:
        """Add an annotation (a note, balloon or surface-finish symbol) to the active drawing.

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release. For a text
        note today, use `add_note`; for GD&T, use `add_gtol` and `add_datum_tag`.
        Changes: once available, adds the annotation. Returns: once available, the
        annotation under `data`.

        Args:
            input_data: The annotation. `annotation_type` and `text` are required;
                the position and font fields have defaults.

        Returns:
            dict[str, Any]: The annotation, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "add_annotation",
            "Active adapter does not support add_annotation; no annotation was added.",
        )
        result = await adapter.add_annotation(input_data.model_dump())
        require_success(result, "Failed to add annotation")
        return {
            "status": "success",
            "message": "Annotation added successfully",
            "data": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def update_title_block(input_data: dict[str, Any]) -> dict[str, Any]:
        """Fill in the active drawing's title-block fields (title, drawn by, drawing number and so on).

        Not available yet: no adapter implements it, so every call returns an error with
        `error_type: "not_supported"`. It is planned for a future release.
        `generate_drawing_package` fills the title block when it creates a drawing, and
        `set_custom_property` sets the properties a title block reads. Changes: once
        available, rewrites the title-block fields. Returns: once available, the fields
        set under `data`.

        Args:
            input_data: A mapping of title-block field names to values.

        Returns:
            dict[str, Any]: The fields, or a `not_supported` error.
        """
        require_capability(
            adapter,
            "update_title_block",
            "Active adapter does not support update_title_block; the "
            "title block was not changed.",
        )
        result = await adapter.update_title_block(input_data)
        require_success(result, "Failed to update title block")
        return {
            "status": "success",
            "message": "Title block updated successfully",
            "data": result.data,
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

    tool_count = 14  # Number of tools registered
    return tool_count
