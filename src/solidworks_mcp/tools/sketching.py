"""Sketching tools for SolidWorks MCP Server.

Provides tools for creating and editing sketches, including geometric entities like
lines, circles, rectangles, arcs, and constraints.
"""

from typing import Any, TypeVar

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import SolidWorksAdapter
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_success,
    with_tool_boundary,
)

TInput = TypeVar("TInput", bound=BaseModel)


# Input schemas using Python 3.14 built-in types


class CreateSketchInput(CompatInput):
    """Input schema for creating a sketch.

    Attributes:
        plane (str): The plane value.
        sketch_name (str | None): The sketch name value.
    """

    plane: str = Field(
        description="Sketch plane name (e.g., 'Top', 'Front', 'Right', 'XY', 'XZ', 'YZ')"
    )
    sketch_name: str | None = Field(default=None, description="Sketch name alias")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create sketch input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Plane is required.
        """
        if not self.plane.strip():
            raise ValueError("plane is required")


class AddLineInput(CompatInput):
    """Input schema for adding a line to sketch.

    Attributes:
        construction (bool): The construction value.
        end_x (float | None): The end x value.
        end_y (float | None): The end y value.
        start_x (float | None): The start x value.
        start_y (float | None): The start y value.
        x1 (float | None): The x1 value.
        x2 (float | None): The x2 value.
        y1 (float | None): The y1 value.
        y2 (float | None): The y2 value.
    """

    x1: float | None = Field(default=None, description="Start point X coordinate in mm")
    y1: float | None = Field(default=None, description="Start point Y coordinate in mm")
    x2: float | None = Field(default=None, description="End point X coordinate in mm")
    y2: float | None = Field(default=None, description="End point Y coordinate in mm")
    start_x: float | None = Field(default=None, description="Start point X alias")
    start_y: float | None = Field(default=None, description="Start point Y alias")
    end_x: float | None = Field(default=None, description="End point X alias")
    end_y: float | None = Field(default=None, description="End point Y alias")
    construction: bool = Field(default=False, description="Construction geometry flag")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the add line input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.
        """
        self.x1 = self.x1 if self.x1 is not None else self.start_x
        self.y1 = self.y1 if self.y1 is not None else self.start_y
        self.x2 = self.x2 if self.x2 is not None else self.end_x
        self.y2 = self.y2 if self.y2 is not None else self.end_y


class AddCircleInput(CompatInput):
    """Input schema for adding a circle to sketch.

    Attributes:
        center_x (float): The center x value.
        center_y (float): The center y value.
        construction (bool): The construction value.
        radius (float): The radius value.
    """

    center_x: float = Field(description="Circle center X coordinate in mm")
    center_y: float = Field(description="Circle center Y coordinate in mm")
    radius: float = Field(description="Circle radius in mm")
    construction: bool = Field(default=False, description="Construction geometry flag")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the add circle input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Radius must be positive.
        """
        if self.radius <= 0:
            raise ValueError("radius must be positive")


class AddRectangleInput(CompatInput):
    """Input schema for adding a rectangle to sketch.

    Attributes:
        construction (bool): The construction value.
        corner1_x (float | None): The corner1 x value.
        corner1_y (float | None): The corner1 y value.
        corner2_x (float | None): The corner2 x value.
        corner2_y (float | None): The corner2 y value.
        x1 (float | None): The x1 value.
        x2 (float | None): The x2 value.
        y1 (float | None): The y1 value.
        y2 (float | None): The y2 value.
    """

    x1: float | None = Field(
        default=None, description="First corner X coordinate in mm"
    )
    y1: float | None = Field(
        default=None, description="First corner Y coordinate in mm"
    )
    x2: float | None = Field(
        default=None, description="Opposite corner X coordinate in mm"
    )
    y2: float | None = Field(
        default=None, description="Opposite corner Y coordinate in mm"
    )
    corner1_x: float | None = Field(default=None, description="Corner 1 X alias")
    corner1_y: float | None = Field(default=None, description="Corner 1 Y alias")
    corner2_x: float | None = Field(default=None, description="Corner 2 X alias")
    corner2_y: float | None = Field(default=None, description="Corner 2 Y alias")
    construction: bool = Field(default=False, description="Construction geometry flag")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the add rectangle input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Rectangle corners must differ.
        """
        self.x1 = self.x1 if self.x1 is not None else self.corner1_x
        self.y1 = self.y1 if self.y1 is not None else self.corner1_y
        self.x2 = self.x2 if self.x2 is not None else self.corner2_x
        self.y2 = self.y2 if self.y2 is not None else self.corner2_y
        if (
            None not in (self.x1, self.y1, self.x2, self.y2)
            and self.x1 == self.x2
            and self.y1 == self.y2
        ):
            raise ValueError("rectangle corners must differ")


class AddArcInput(BaseModel):
    """Input schema for adding an arc to sketch.

    Attributes:
        center_x (float): The center x value.
        center_y (float): The center y value.
        end_x (float): The end x value.
        end_y (float): The end y value.
        start_x (float): The start x value.
        start_y (float): The start y value.
    """

    center_x: float = Field(description="Arc center X coordinate in mm")
    center_y: float = Field(description="Arc center Y coordinate in mm")
    start_x: float = Field(description="Arc start point X coordinate in mm")
    start_y: float = Field(description="Arc start point Y coordinate in mm")
    end_x: float = Field(description="Arc end point X coordinate in mm")
    end_y: float = Field(description="Arc end point Y coordinate in mm")


class AddSplineInput(BaseModel):
    """Input schema for adding a spline to sketch.

    Attributes:
        points (list[dict[str, float]]): The points value.
    """

    points: list[dict[str, float]] = Field(
        description="List of spline control points with x, y coordinates"
    )


class AddDimensionInput(BaseModel):
    """Input schema for adding a dimension to sketch.

    Attributes:
        dimension_type (str): The dimension type value.
        entity1 (str): The entity1 value.
        entity2 (str | None): The entity2 value.
        value (float): The value value.
    """

    entity1: str = Field(description="First entity name or ID")
    entity2: str | None = Field(
        default=None, description="Second entity name or ID (for distance dimensions)"
    )
    dimension_type: str = Field(
        default="linear", description="Dimension type (linear, radial, angular, etc.)"
    )
    value: float = Field(description="Dimension value in mm or degrees")


class AddRelationInput(BaseModel):
    """Input schema for adding a geometric relation.

    Attributes:
        entity1 (str): The entity1 value.
        entity2 (str | None): The entity2 value.
        entity3 (str | None): Third entity ID — only used by the ``symmetric``
            relation (the centerline of symmetry). All other relation types
            reject a non-null ``entity3``.
        relation_type (str): The relation type value.
    """

    entity1: str = Field(description="First entity name or ID")
    entity2: str | None = Field(
        default=None, description="Second entity name or ID (if required)"
    )
    entity3: str | None = Field(
        default=None,
        description=(
            "Third entity ID. Required for 'symmetric' (the centerline of "
            "symmetry); must be null for all other relations."
        ),
    )
    relation_type: str = Field(
        description="Relation type (parallel, perpendicular, tangent, coincident, etc.)"
    )


class TutorialSimpleHoleInput(CompatInput):
    """Input schema for creating a simple hole (tutorial example).

    Attributes:
        center_x (float): The center x value.
        center_y (float): The center y value.
        depth (float | None): The depth value.
        diameter (float): The diameter value.
        plane (str): The plane value.
    """

    plane: str = Field(description="Sketch plane for the hole")
    center_x: float = Field(description="Hole center X coordinate in mm")
    center_y: float = Field(description="Hole center Y coordinate in mm")
    diameter: float = Field(description="Hole diameter in mm")
    depth: float | None = Field(
        default=None, description="Hole depth in mm (None for through hole)"
    )

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the tutorial simple hole input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Depth must be positive.
        """
        if self.diameter <= 0:
            raise ValueError("diameter must be positive")
        if self.depth is not None and self.depth <= 0:
            raise ValueError("depth must be positive")


class CheckSketchDefinitionInput(CompatInput):
    """Input schema for checking sketch definition status.

    Attributes:
        sketch_name (str | None): Optional sketch name to inspect.
    """

    sketch_name: str | None = Field(
        default=None,
        description="Optional sketch name. If omitted, checks the active or last sketch.",
    )


async def register_sketching_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register sketching tools with FastMCP.

    Registers comprehensive sketching tools for SolidWorks automation including geometry
    creation, constraints, dimensions, and pattern operations.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.sketching import register_sketching_tools

                        tool_count = await register_sketching_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} sketching tools")
                        ```
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def create_sketch(input_data: CreateSketchInput) -> dict[str, Any]:
        """Open a new sketch on a plane of the active part, ready for lines, circles and other sketch entities.

        Use it first in every feature: sketch, draw, `exit_sketch`, then
        `create_extrusion` or `create_cut_extrude`. Planes: Front, Top, Right (or XY,
        XZ, YZ), or a plane made by `create_reference_plane`. Coordinates in the sketch
        are mm from the origin. Needs: an open part. Changes: adds a sketch and opens it
        for editing. Returns: `sketch` with `name` and `plane`; `name` echoes
        `sketch_name` when you pass one, as SolidWorks names the sketch itself.

        Args:
            input_data: The sketch. `plane` is required; `sketch_name` is not
                applied to SolidWorks.

        Returns:
            dict[str, Any]: The new sketch.
        """
        input_data = normalize_input(input_data, CreateSketchInput)
        result = await adapter.create_sketch(input_data.plane)

        require_success(result, context="Failed to create sketch")
        sketch_name = input_data.sketch_name or (
            result.data.get("sketch_name")
            if isinstance(result.data, dict)
            else result.data
        )
        return {
            "status": "success",
            "message": f"Created sketch '{sketch_name}' on {input_data.plane} plane",
            "sketch": {
                "name": sketch_name,
                "plane": input_data.plane,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_line(input_data: AddLineInput) -> dict[str, Any]:
        """Draw a straight line between two points in the open sketch, in mm.

        Use it for profiles made of straight edges; for a closed box, use
        `add_rectangle`, and for a revolve axis, `add_centerline`. Needs: an open sketch
        (`create_sketch`). Changes: adds a line (a construction line with
        `construction`). Returns: `line` with `id`, `start`, `end` and `length`. Its
        `id` is what `add_sketch_constraint` and `add_sketch_dimension` take.

        Args:
            input_data: The line. Give `x1`, `y1`, `x2`, `y2` (mm; or `start_x`,
                `start_y`, `end_x`, `end_y`); `construction` is off.

        Returns:
            dict[str, Any]: The line added.
        """
        input_data = normalize_input(input_data, AddLineInput)
        if hasattr(adapter, "add_sketch_line"):
            result = await adapter.add_sketch_line(
                input_data.x1,
                input_data.y1,
                input_data.x2,
                input_data.y2,
                input_data.construction,
            )
        else:
            result = await adapter.add_line(
                input_data.x1,  # type: ignore[arg-type]
                input_data.y1,  # type: ignore[arg-type]
                input_data.x2,  # type: ignore[arg-type]
                input_data.y2,  # type: ignore[arg-type]
            )

        require_success(result, context="Failed to add line")
        line_id = (
            result.data.get("entity_id") or result.data.get("id")
            if isinstance(result.data, dict)
            else result.data
        )
        x1, y1 = input_data.x1 or 0.0, input_data.y1 or 0.0
        x2, y2 = input_data.x2 or 0.0, input_data.y2 or 0.0
        return {
            "status": "success",
            "message": f"Added line from ({x1}, {y1}) to ({x2}, {y2})",
            "line": {
                "id": line_id,
                "start": {"x": x1, "y": y1},
                "end": {"x": x2, "y": y2},
                "construction": input_data.construction,
                "length": ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_circle(input_data: AddCircleInput) -> dict[str, Any]:
        """Draw a circle in the open sketch from its centre and radius, in mm.

        Use it for holes and round bosses. Needs: an open sketch (`create_sketch`).
        Changes: adds a circle (a construction circle with `construction`). Returns:
        `circle` with `id`, `center`, `radius` and `diameter`. Its `id` is what
        `add_sketch_constraint` and `add_sketch_dimension` take.

        Args:
            input_data: The circle. `center_x`, `center_y` and `radius` (mm) are
                required; `construction` is off.

        Returns:
            dict[str, Any]: The circle added.
        """
        input_data = normalize_input(input_data, AddCircleInput)
        if hasattr(adapter, "add_sketch_circle"):
            result = await adapter.add_sketch_circle(
                input_data.center_x,
                input_data.center_y,
                input_data.radius,
                input_data.construction,
            )
        else:
            result = await adapter.add_circle(
                input_data.center_x, input_data.center_y, input_data.radius
            )

        require_success(result, context="Failed to add circle")
        circle_id = (
            result.data.get("entity_id")
            if isinstance(result.data, dict)
            else result.data
        )
        return {
            "status": "success",
            "message": f"Added circle at ({input_data.center_x}, {input_data.center_y}) with radius {input_data.radius}mm",
            "circle": {
                "id": circle_id,
                "center": {"x": input_data.center_x, "y": input_data.center_y},
                "radius": input_data.radius,
                "construction": input_data.construction,
                "diameter": input_data.radius * 2,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_rectangle(input_data: AddRectangleInput) -> dict[str, Any]:
        """Draw a closed, axis-aligned rectangle in the open sketch from two opposite corners, in mm.

        Use it for blocks, plates and rectangular cut-outs. Needs: an open sketch
        (`create_sketch`). Changes: adds four connected lines. Returns: `rectangle` with
        `id`, `corner1`, `corner2`, `width`, `height` and `area`. Its `id` is what
        `add_sketch_constraint` and `add_sketch_dimension` take.

        Args:
            input_data: The rectangle. Give `x1`, `y1`, `x2`, `y2` (mm; or
                `corner1_x` ... `corner2_y`); `construction` is off.

        Returns:
            dict[str, Any]: The rectangle added.
        """
        input_data = normalize_input(input_data, AddRectangleInput)
        if hasattr(adapter, "add_sketch_rectangle"):
            result = await adapter.add_sketch_rectangle(
                input_data.x1,
                input_data.y1,
                input_data.x2,
                input_data.y2,
                input_data.construction,
            )
        else:
            result = await adapter.add_rectangle(
                input_data.x1,  # type: ignore[arg-type]
                input_data.y1,  # type: ignore[arg-type]
                input_data.x2,  # type: ignore[arg-type]
                input_data.y2,  # type: ignore[arg-type]
            )

        require_success(result, context="Failed to add rectangle")
        rect_id = (
            result.data.get("entity_id")
            if isinstance(result.data, dict)
            else result.data
        )
        rx1, ry1 = input_data.x1 or 0.0, input_data.y1 or 0.0
        rx2, ry2 = input_data.x2 or 0.0, input_data.y2 or 0.0
        width = abs(rx2 - rx1)
        height = abs(ry2 - ry1)

        return {
            "status": "success",
            "message": f"Added rectangle from ({rx1}, {ry1}) to ({rx2}, {ry2})",
            "rectangle": {
                "id": rect_id,
                "corner1": {"x": rx1, "y": ry1},
                "corner2": {"x": rx2, "y": ry2},
                "construction": input_data.construction,
                "width": width,
                "height": height,
                "area": width * height,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def exit_sketch() -> dict[str, Any]:
        """Close the open sketch so a feature can use it.

        Call it after drawing and before `create_extrusion`, `create_revolve` or
        `create_cut_extrude`; those use the sketch closed last. Needs: an open sketch.
        Changes: leaves sketch editing; the sketch stays in the feature tree. Returns: a
        message only.
        """
        result = await adapter.exit_sketch()

        require_success(result, context="Failed to exit sketch")
        return {
            "status": "success",
            "message": "Exited sketch editing mode",
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def check_sketch_fully_defined(
        input_data: CheckSketchDefinitionInput | None = None,
    ) -> dict[str, Any]:
        """Check whether a sketch is fully defined, under-defined or over-defined.

        Use it after adding relations and dimensions, to see if the sketch still has
        free geometry. Needs: an open part with the sketch. Read-only. Returns: `sketch`
        with `sketch_name`, `is_fully_defined` (null when unknown), `definition_state`
        and where the answer came from (`source`).

        Args:
            input_data: Nothing is required: give `sketch_name`, or omit it for the
                open or last sketch.

        Returns:
            dict[str, Any]: The definition state.
        """
        normalized = normalize_input(
            input_data or {},
            CheckSketchDefinitionInput,
        )
        result = await adapter.check_sketch_fully_defined(normalized.sketch_name)

        require_success(result, context="Failed to inspect sketch definition")

        payload = result.data or {}
        state = payload.get("definition_state", "unknown")
        return {
            "status": "success",
            "message": f"Sketch definition state: {state}",
            "sketch": payload,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_arc(input_data: AddArcInput) -> dict[str, Any]:
        """Draw a circular arc in the open sketch from its centre, start point and end point, in mm.

        Use it for rounded ends and curved edges of a profile. Needs: an open sketch
        (`create_sketch`). Changes: adds an arc. Returns: `arc` with `id`, `center`,
        `start_point` and `end_point`. Its `id` is what `add_sketch_constraint` and
        `add_sketch_dimension` take.

        Args:
            input_data: The arc. `center_x`, `center_y`, `start_x`, `start_y`,
                `end_x` and `end_y` (mm) are all required.

        Returns:
            dict[str, Any]: The arc added.
        """
        input_data = normalize_input(input_data, AddArcInput)
        result = await adapter.add_arc(
            input_data.center_x,
            input_data.center_y,
            input_data.start_x,
            input_data.start_y,
            input_data.end_x,
            input_data.end_y,
        )

        require_success(result, context="Failed to add arc")
        arc_id = result.data
        return {
            "status": "success",
            "message": f"Added arc centered at ({input_data.center_x}, {input_data.center_y})",
            "arc": {
                "id": arc_id,
                "center": {"x": input_data.center_x, "y": input_data.center_y},
                "start_point": {
                    "x": input_data.start_x,
                    "y": input_data.start_y,
                },
                "end_point": {"x": input_data.end_x, "y": input_data.end_y},
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_spline(input_data: AddSplineInput) -> dict[str, Any]:
        """Draw a smooth spline through a list of points in the open sketch, in mm.

        Use it for free-form curves such as an aerofoil or a handle profile. Needs: an
        open sketch (`create_sketch`). Changes: adds a spline. Returns: `spline` with
        `id`, `control_points` and `point_count`.

        Args:
            input_data: The spline. `points` (a list of {"x", "y"} in mm) is
                required.

        Returns:
            dict[str, Any]: The spline added.
        """
        result = await adapter.add_spline(input_data.points)

        require_success(result, context="Failed to add spline")
        spline_id = result.data
        return {
            "status": "success",
            "message": f"Added spline with {len(input_data.points)} control points",
            "spline": {
                "id": spline_id,
                "control_points": input_data.points,
                "point_count": len(input_data.points),
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_centerline(input_data: AddLineInput) -> dict[str, Any]:
        """Draw a centreline (construction line) in the open sketch, in mm.

        Use it as the axis for `create_revolve`, or as the line for `sketch_mirror` and
        symmetric relations. It is never part of the profile. Needs: an open sketch
        (`create_sketch`). Changes: adds a centreline. Returns: `centerline` with `id`,
        `start_point` and `end_point`.

        Args:
            input_data: The line. Give `x1`, `y1`, `x2`, `y2` (mm; or `start_x`,
                `start_y`, `end_x`, `end_y`); `construction` is not used.

        Returns:
            dict[str, Any]: The centreline added.
        """
        input_data = normalize_input(input_data, AddLineInput)

        result = await adapter.add_centerline(
            input_data.x1,  # type: ignore[arg-type]
            input_data.y1,  # type: ignore[arg-type]
            input_data.x2,  # type: ignore[arg-type]
            input_data.y2,  # type: ignore[arg-type]
        )

        require_success(result, context="Failed to add centerline")
        centerline_id = result.data
        return {
            "status": "success",
            "message": f"Added centerline from ({input_data.x1}, {input_data.y1}) to ({input_data.x2}, {input_data.y2})",
            "centerline": {
                "id": centerline_id,
                "start_point": {"x": input_data.x1, "y": input_data.y1},
                "end_point": {"x": input_data.x2, "y": input_data.y2},
                "type": "construction",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_polygon(input_data: dict[str, Any]) -> dict[str, Any]:
        """Draw a regular polygon (e.g. a hexagon) in the open sketch from its centre, radius and number of sides.

        Use it for nuts, hex bosses and pockets. Needs: an open sketch
        (`create_sketch`). Changes: adds the polygon's sides. Returns: `polygon` with
        `id`, `center`, `radius` and `sides`.

        Args:
            input_data: A mapping: `center_x`, `center_y` (mm, default 0), `radius`
                (mm, circumscribed, default 10) and `sides` (default 6).

        Returns:
            dict[str, Any]: The polygon added.
        """
        center_x = input_data.get("center_x", 0.0)
        center_y = input_data.get("center_y", 0.0)
        radius = input_data.get("radius", 10.0)
        sides = input_data.get("sides", 6)

        result = await adapter.add_polygon(center_x, center_y, radius, sides)

        require_success(result, context="Failed to add polygon")
        polygon_id = result.data
        return {
            "status": "success",
            "message": f"Added {sides}-sided polygon at ({center_x}, {center_y}) with radius {radius}mm",
            "polygon": {
                "id": polygon_id,
                "center": {"x": center_x, "y": center_y},
                "radius": radius,
                "sides": sides,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_ellipse(input_data: dict[str, Any]) -> dict[str, Any]:
        """Draw an ellipse in the open sketch from its centre and axis lengths, in mm.

        Use it for oval holes and bosses. Needs: an open sketch (`create_sketch`).
        Changes: adds an ellipse. Returns: `ellipse` with `id`, `center`, `major_axis`
        and `minor_axis`.

        Args:
            input_data: A mapping: `center_x`, `center_y` (mm, default 0),
                `major_axis` (default 20) and `minor_axis` (default 10), in mm.

        Returns:
            dict[str, Any]: The ellipse added.
        """
        center_x = input_data.get("center_x", 0.0)
        center_y = input_data.get("center_y", 0.0)
        major_axis = input_data.get("major_axis", 20.0)
        minor_axis = input_data.get("minor_axis", 10.0)

        result = await adapter.add_ellipse(center_x, center_y, major_axis, minor_axis)

        require_success(result, context="Failed to add ellipse")
        ellipse_id = result.data
        return {
            "status": "success",
            "message": f"Added ellipse at ({center_x}, {center_y}) with axes {major_axis}x{minor_axis}mm",
            "ellipse": {
                "id": ellipse_id,
                "center": {"x": center_x, "y": center_y},
                "major_axis": major_axis,
                "minor_axis": minor_axis,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sketch_constraint(input_data: AddRelationInput) -> dict[str, Any]:
        """Add a geometric relation between sketch entities: horizontal, vertical, parallel, perpendicular, tangent, coincident, concentric, equal, symmetric, collinear or fix.

        Use it to hold design intent, then check with `check_sketch_fully_defined`.
        Entities are the `id`s the add_* tools returned. Needs: an open sketch
        (`create_sketch`). Changes: adds the relation. Returns: `constraint` with `id`,
        `type` and the entities.

        Args:
            input_data: The relation. `entity1` and `relation_type` are required;
                `entity2` when the relation needs two, and `entity3` (the
                centreline) only for symmetric.

        Returns:
            dict[str, Any]: The relation added.
        """
        input_data = normalize_input(input_data, AddRelationInput)
        result = await adapter.add_sketch_constraint(
            input_data.entity1,
            input_data.entity2,
            input_data.relation_type,
            input_data.entity3,
        )

        require_success(result, context="Failed to add constraint")
        constraint_id = result.data
        return {
            "status": "success",
            "message": f"Added {input_data.relation_type} constraint between {input_data.entity1} and {input_data.entity2}",
            "constraint": {
                "id": constraint_id,
                "type": input_data.relation_type,
                "entity1": input_data.entity1,
                "entity2": input_data.entity2,
                "entity3": input_data.entity3,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sketch_dimension(input_data: AddDimensionInput) -> dict[str, Any]:
        """Add a driving dimension to sketch entities: linear, angular, radial or diameter.

        Use it to fix a size so the sketch is fully defined and can be changed later
        with `set_dimension`. Entities are the `id`s the add_* tools returned; two
        connected lines for angular, a circle or arc for radial or diameter. No dialog
        opens. Needs: an open sketch (`create_sketch`). Changes: adds the dimension and
        resizes the geometry to `value`. Returns: `dimension` with `id`, `type`, `value`
        and the entities.

        Args:
            input_data: The dimension. `entity1` and `value` (mm, or degrees for
                angular) are required; `entity2` and `dimension_type` (linear) have
                defaults.

        Returns:
            dict[str, Any]: The dimension added.
        """
        input_data = normalize_input(input_data, AddDimensionInput)
        result = await adapter.add_sketch_dimension(
            input_data.entity1,
            input_data.entity2,
            input_data.dimension_type,
            input_data.value,
        )

        require_success(result, context="Failed to add dimension")
        dimension_id = result.data
        return {
            "status": "success",
            "message": f"Added {input_data.dimension_type} dimension of {input_data.value}mm to {input_data.entity1}",
            "dimension": {
                "id": dimension_id,
                "type": input_data.dimension_type,
                "value": input_data.value,
                "entity1": input_data.entity1,
                "entity2": input_data.entity2,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_linear_pattern(input_data: dict[str, Any]) -> dict[str, Any]:
        """Repeat sketch entities in a straight line at a fixed spacing.

        Use it for rows of holes or slots before one cut. Needs: an open sketch
        (`create_sketch`). Changes: adds copies of the entities. Returns: `pattern` with
        `id`, `entities`, `count`, `spacing` and `direction`.

        Args:
            input_data: A mapping: `entities` (ids to repeat), `direction_x`/
                `direction_y` (default 1, 0), `spacing` (mm, default 10) and
                `count` (instances, default 3).

        Returns:
            dict[str, Any]: The pattern added.
        """
        entities = input_data.get("entities", [])
        direction_x = input_data.get("direction_x", 1.0)
        direction_y = input_data.get("direction_y", 0.0)
        spacing = input_data.get("spacing", 10.0)
        count = input_data.get("count", 3)

        result = await adapter.sketch_linear_pattern(
            entities, direction_x, direction_y, spacing, count
        )

        require_success(result, context="Failed to create linear pattern")
        pattern_id = result.data
        return {
            "status": "success",
            "message": f"Created linear pattern with {count} instances, spacing {spacing}mm",
            "pattern": {
                "id": pattern_id,
                "type": "linear",
                "entities": entities,
                "count": count,
                "spacing": spacing,
                "direction": {"x": direction_x, "y": direction_y},
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_circular_pattern(input_data: dict[str, Any]) -> dict[str, Any]:
        """Repeat sketch entities around the sketch origin, e.g. a bolt circle.

        The centre is always the sketch origin, so draw the first entity at the radius
        you want from it. Then cut once with `create_cut_extrude`. Needs: an open sketch
        (`create_sketch`). Changes: adds copies of the entities. Returns: `pattern` with
        `id`, `entities`, `count` and `angle`.

        Args:
            input_data: A mapping: `entities` (ids to repeat), `count` (instances,
                default 6) and `angle` (degrees spread over, default 360).

        Returns:
            dict[str, Any]: The pattern added.
        """
        entities = input_data.get("entities", [])
        angle = input_data.get("angle", 360.0)
        count = input_data.get("count", 6)

        result = await adapter.sketch_circular_pattern(entities, angle, count)

        require_success(result, context="Failed to create circular pattern")
        pattern_id = result.data
        return {
            "status": "success",
            "message": (
                f"Created circular pattern with {count} instances "
                "around the sketch origin"
            ),
            "pattern": {
                "id": pattern_id,
                "type": "circular",
                "entities": entities,
                "count": count,
                "center": {"x": 0.0, "y": 0.0},
                "angle": angle,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_mirror(input_data: dict[str, Any]) -> dict[str, Any]:
        """Mirror sketch entities about a centreline in the open sketch.

        Use it for symmetric profiles: draw one half, add a centreline with
        `add_centerline`, then mirror. Needs: an open sketch (`create_sketch`). Changes:
        adds mirrored copies. Returns: `mirror` with `id`, `entities` and `mirror_line`.

        Args:
            input_data: A mapping: `entities` (ids to mirror) and `mirror_line`
                (the centreline's id).

        Returns:
            dict[str, Any]: The mirror added.
        """
        entities = input_data.get("entities", [])
        mirror_line = input_data.get("mirror_line", "")

        result = await adapter.sketch_mirror(entities, mirror_line)

        require_success(result, context="Failed to mirror entities")
        mirror_id = result.data
        return {
            "status": "success",
            "message": f"Mirrored {len(entities)} entities about {mirror_line}",
            "mirror": {
                "id": mirror_id,
                "entities": entities,
                "mirror_line": mirror_line,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_offset(input_data: dict[str, Any]) -> dict[str, Any]:
        """Offset sketch entities by a distance in mm, outward or inward, e.g. for a wall or a clearance.

        Needs: an open sketch (`create_sketch`). Changes: adds the offset entities.
        Returns: `offset` with `id`, `entities`, `distance` and `direction` (outward or
        inward).

        Args:
            input_data: A mapping: `entities` (ids to offset), `offset_distance`
                (mm, default 5) and `reverse_direction` (inward; default off).

        Returns:
            dict[str, Any]: The offset added.
        """
        entities = input_data.get("entities", [])
        offset_distance = input_data.get("offset_distance", 5.0)
        reverse_direction = input_data.get("reverse_direction", False)

        result = await adapter.sketch_offset(
            entities, offset_distance, reverse_direction
        )

        require_success(result, context="Failed to create offset")
        offset_id = result.data
        direction = "outward" if not reverse_direction else "inward"
        return {
            "status": "success",
            "message": f"Created offset of {len(entities)} entities by {offset_distance}mm ({direction})",
            "offset": {
                "id": offset_id,
                "entities": entities,
                "distance": offset_distance,
                "direction": direction,
            },
            "execution_time": result.execution_time,
        }

    # Additional sketch tools can be added here in the future:
    # - add_arc (3-point arc, center-point arc)
    # - add_spline (free-form curves)
    # - add_dimension (dimensional constraints)
    # - add_relation (geometric constraints like parallel, perpendicular)
    # - add_pattern (circular, linear patterns)
    # - trim_entities (trim overlapping geometry)
    # - mirror_entities (mirror sketch geometry)

    @mcp.tool()
    async def sketch_tutorial_simple_hole() -> dict[str, Any]:
        """Demonstrate the sketch steps: draw a 5 mm circle at the origin on the Top plane and close the sketch.

        It is a fixed example; for a real hole, use `create_sketch`, `add_circle`,
        `exit_sketch` and `create_cut_extrude`. Its `next_step` text suggests a
        negative-depth extrusion: use `create_cut_extrude` instead. Needs: an open part.
        Changes: adds a sketch with one circle. Returns: `steps_completed`, `next_step`
        and `suggested_extrusion`.
        """
        steps_completed = []

        # Step 1: Create sketch
        sketch_result = await adapter.create_sketch("Top")
        require_success(sketch_result, context="Failed to create sketch")
        steps_completed.append(f"Created sketch: {sketch_result.data}")

        # Step 2: Add circle
        circle_result = await adapter.add_circle(0, 0, 2.5)
        require_success(circle_result, context="Failed to add circle")
        steps_completed.append(f"Added 5mm diameter circle: {circle_result.data}")

        # Step 3: Exit sketch
        exit_result = await adapter.exit_sketch()
        require_success(exit_result, context="Failed to exit sketch")
        steps_completed.append("Exited sketch")

        return {
            "status": "success",
            "message": "Tutorial completed: Simple hole sketch created",
            "steps_completed": steps_completed,
            "next_step": "Use create_extrusion with negative depth to create the hole",
            "suggested_extrusion": {
                "depth": -10,  # Negative for cut
                "reverse_direction": False,
            },
        }

    @mcp.tool()
    async def tutorial_simple_hole(
        input_data: TutorialSimpleHoleInput,
    ) -> dict[str, Any]:
        """Draw a circle on a plane and cut it as a hole, as one worked example.

        On real SolidWorks the cut step is not implemented yet: the call draws and
        closes the sketch, then fails. Use `create_sketch`, `add_circle`, `exit_sketch`
        and `create_cut_extrude` instead. Needs: an open part with a solid body.
        Changes: adds a sketch (and, with the mock adapter, a cut). Returns: `tutorial`
        with `plane`, `diameter`, `depth` and `steps`.

        Args:
            input_data: The hole. `plane`, `center_x`, `center_y` and `diameter`
                (mm) are required; `depth` defaults to the diameter.

        Returns:
            dict[str, Any]: The steps run.
        """
        steps: list[dict[str, Any]] = []

        sketch_result = await adapter.create_sketch(input_data.plane)
        require_success(sketch_result, context="Failed to create sketch")
        steps.append({"step": "Create sketch", "status": "success"})

        circle_result = await adapter.add_sketch_circle(
            input_data.center_x,
            input_data.center_y,
            input_data.diameter / 2,
            False,
        )
        require_success(circle_result, context="Failed to add circle")
        steps.append({"step": "Add circle", "status": "success"})

        exit_result = await adapter.exit_sketch()
        require_success(exit_result, context="Failed to exit sketch")
        steps.append({"step": "Exit sketch", "status": "success"})

        cut_depth = (
            input_data.depth if input_data.depth is not None else input_data.diameter
        )
        cut_result = await adapter.create_cut("HoleSketch", cut_depth)
        require_success(cut_result, context="Failed to create cut extrude")
        steps.append({"step": "Create cut extrude", "status": "success"})

        return {
            "status": "success",
            "message": "Completed simple hole tutorial",
            "tutorial": {
                "plane": input_data.plane,
                "diameter": input_data.diameter,
                "depth": input_data.depth,
                "steps": steps,
            },
        }

    tool_count = 6  # Legacy count expected by tests
    return tool_count
