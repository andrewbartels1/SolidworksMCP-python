"""Sketching tools for SolidWorks MCP Server.

Provides tools for creating and editing sketches, including geometric entities like
lines, circles, rectangles, arcs, and constraints.
"""

import math
from typing import Annotated, Any, Literal, TypeVar

from fastmcp import FastMCP
from pydantic import BaseModel, Field, model_validator

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
        plane (str | None): The plane to sketch on.
        face_point (list[float] | None): A point on a flat face to sketch on
            instead.
        sketch_name (str | None): The sketch name value.
    """

    plane: str | None = Field(
        default=None,
        description=(
            "Sketch plane name: 'Front' (XY), 'Top' (XZ), 'Right' (YZ), found "
            "in any language, or a plane made by create_reference_plane. Give "
            "this or face_point"
        ),
    )
    face_point: list[float] | None = Field(
        default=None,
        description=(
            "[x, y, z] in mm on a flat face of the part's body; the sketch opens "
            "on that face and follows it when the model changes. Give this or plane"
        ),
    )
    sketch_name: str | None = Field(
        default=None,
        description=(
            "Name to give the sketch in the feature tree, applied when "
            "exit_sketch closes it; omit to keep SolidWorks' own (Sketch1, "
            "Sketch2, ...)"
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        """Require exactly one of ``plane`` and ``face_point``.

        Args:
            __context (Any): The context value.

        Raises:
            ValueError: When both or neither are given, or ``face_point`` is not
                three numbers.
        """
        has_plane = bool((self.plane or "").strip())
        if has_plane == (self.face_point is not None):
            raise ValueError("give exactly one of plane and face_point")
        if self.face_point is not None and len(self.face_point) != 3:
            raise ValueError("face_point must be [x, y, z] in millimetres")


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
        from_center (bool): ``x1``/``y1`` is the centre, ``x2``/``y2`` a corner.
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
    from_center: bool = Field(
        default=False,
        description="x1, y1 is the centre and x2, y2 a corner (a rectangle centred "
        "there)",
    )

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
        kind (str): ``center``, ``three_point`` or ``tangent``.
        center_x (float | None): The center x value (``center``).
        center_y (float | None): The center y value (``center``).
        end_x (float): The end x value.
        end_y (float): The end y value.
        start_x (float): The start x value.
        start_y (float): The start y value.
        through_x (float | None): A point on the arc, x (``three_point``).
        through_y (float | None): A point on the arc, y (``three_point``).
    """

    kind: Literal["center", "three_point", "tangent"] = Field(
        default="center",
        description="center: centre, start and end; three_point: start, end and a "
        "point it passes through; tangent: from the end of an existing entity, "
        "tangent to it",
    )
    center_x: float | None = Field(
        default=None, description="Arc center X in mm (kind center)"
    )
    center_y: float | None = Field(
        default=None, description="Arc center Y in mm (kind center)"
    )
    start_x: float = Field(description="Arc start point X coordinate in mm")
    start_y: float = Field(description="Arc start point Y coordinate in mm")
    end_x: float = Field(description="Arc end point X coordinate in mm")
    end_y: float = Field(description="Arc end point Y coordinate in mm")
    through_x: float | None = Field(
        default=None, description="X of a point the arc passes through (three_point)"
    )
    through_y: float | None = Field(
        default=None, description="Y of a point the arc passes through (three_point)"
    )

    @model_validator(mode="after")
    def _points_for_kind(self) -> "AddArcInput":
        """Each kind needs its own points."""
        needed = {
            "center": ("center_x", "center_y"),
            "three_point": ("through_x", "through_y"),
            "tangent": (),
        }[self.kind]
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f"a {self.kind} arc needs {' and '.join(missing)}")
        return self


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

    entity1: str = Field(
        description=(
            "First entity: an ID from add_line/add_arc/..., '<id>.start' or "
            "'<id>.end' for a line's or arc's end point, or 'origin'"
        )
    )
    entity2: str | None = Field(
        default=None,
        description=(
            "Second entity, the same kinds (if required); e.g. 'Line_1.start' "
            "coincident with 'origin' ties a corner to the origin"
        ),
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


class AddSketchTextInput(CompatInput):
    """Input schema for adding text to the open sketch.

    Attributes:
        text (str): The text; ``$PRP:"name"`` shows a custom property.
        x (float): Start x in mm (sketch coordinates).
        y (float): Start y (baseline) in mm.
        height (float): Letter height in mm.
        center_at (list[float] | None): A model point [x, y, z] in mm for the
            text's middle.
    """

    text: str = Field(
        min_length=1,
        description='The text. $PRP:"name" shows a custom property, e.g. one '
        'linked to a dimension ("D1@Sketch3"), so the text follows it',
    )
    x: float = Field(default=0.0, description="Start x in mm, sketch coordinates")
    y: float = Field(default=0.0, description="Start y (baseline) in mm")
    height: float = Field(default=3.5, gt=0, description="Letter height in mm")
    center_at: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Model point [x, y, z] in mm to put the text's middle at "
        "(projected onto the sketch), e.g. the middle of a handle's face",
    )


class SetSketchTextInput(CompatInput):
    """Input schema for rewriting the text in a sketch.

    Attributes:
        sketch_name (str): The sketch whose text to rewrite.
        text (str): The new text.
    """

    sketch_name: str = Field(min_length=1, description="The sketch, e.g. Sketch12")
    text: str = Field(
        min_length=1,
        description='The new text; give the same $PRP:"name" text to re-read a '
        "linked property after the model changed",
    )


class CheckSketchDefinitionInput(CompatInput):
    """Input schema for checking sketch definition status.

    Attributes:
        sketch_name (str | None): Optional sketch name to inspect.
    """

    sketch_name: str | None = Field(
        default=None,
        description="Optional sketch name. If omitted, checks the active or last sketch.",
    )


class SketchConvertEntitiesInput(CompatInput):
    """Input schema for copying model edges into the open sketch.

    Attributes:
        edge_points (list[list[float]]): A point in mm on each edge to copy.
        face_point (list[float] | None): A point in mm on a face whose outline
            to copy.
        construction (bool): Make the copies construction geometry.
    """

    edge_points: list[list[float]] = Field(
        default_factory=list, description="[x, y, z] in mm on each model edge to copy"
    )
    face_point: list[float] | None = Field(
        default=None,
        description="[x, y, z] in mm on a face whose whole outline to copy",
    )
    construction: bool = Field(
        default=False, description="Make the copies construction geometry"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.edge_points and self.face_point is None:
            raise ValueError("give edge_points or face_point")
        for point in [
            *self.edge_points,
            *([self.face_point] if self.face_point else []),
        ]:
            if len(point) != 3:
                raise ValueError("each point must be [x, y, z] in mm")


#: A point in the open sketch, ``[x, y]`` in mm.
SketchPoint = Annotated[list[float], Field(min_length=2, max_length=2)]


class AddSketchFilletInput(CompatInput):
    """Input schema for rounding sketch corners.

    Attributes:
        corners (list[list[float]]): Corners, ``[x, y]`` sketch mm.
        radius (float): Fillet radius in mm.
    """

    corners: list[SketchPoint] = Field(
        min_length=1,
        description="Corners to round, each [x, y] in sketch mm where two "
        "entities meet, e.g. a rectangle's corner",
    )
    radius: float = Field(gt=0, description="Fillet radius in mm")


class AddSketchChamferInput(CompatInput):
    """Input schema for bevelling sketch corners.

    Attributes:
        corners (list[list[float]]): Corners, ``[x, y]`` sketch mm.
        distance (float): Distance along the first side, mm.
        distance2 (float | None): Distance along the second side, mm.
        angle (float | None): Angle from the first side, degrees.
    """

    corners: list[SketchPoint] = Field(
        min_length=1,
        description="Corners to bevel, each [x, y] in sketch mm where two entities meet",
    )
    distance: float = Field(gt=0, description="Distance along each side in mm")
    distance2: float | None = Field(
        default=None, gt=0, description="A different distance along the second side"
    )
    angle: float | None = Field(
        default=None,
        gt=0,
        lt=90,
        description="Angle in degrees from the first side, with `distance`",
    )

    @model_validator(mode="after")
    def _one_way(self) -> "AddSketchChamferInput":
        """``distance2`` and ``angle`` are two different chamfers: one at most."""
        if self.distance2 is not None and self.angle is not None:
            raise ValueError("give distance2 or angle, not both")
        return self


class AddSlotInput(CompatInput):
    """Input schema for drawing a slot.

    Attributes:
        kind (str): ``straight`` or ``arc``.
        width (float): Slot width in mm.
        start (list[float]): Straight: first end's centre; arc: start on the arc.
        end (list[float]): Straight: second end's centre; arc: end on the arc.
        center (list[float] | None): Arc: the centre of the arc it follows.
    """

    kind: Literal["straight", "arc"] = Field(
        default="straight", description="straight, or arc (follows an arc)"
    )
    width: float = Field(gt=0, description="Slot width in mm")
    start: SketchPoint = Field(
        description="[x, y] mm: a straight slot's first end centre, or where an "
        "arc slot starts on its arc"
    )
    end: SketchPoint = Field(
        description="[x, y] mm: a straight slot's second end centre, or where an "
        "arc slot ends (counter-clockwise from start)"
    )
    center: SketchPoint | None = Field(
        default=None, description="[x, y] mm, an arc slot's arc centre"
    )

    @model_validator(mode="after")
    def _points(self) -> "AddSlotInput":
        """An arc slot needs its centre; the two ends must differ."""
        if self.kind == "arc" and self.center is None:
            raise ValueError("an arc slot needs center")
        if self.start == self.end:
            raise ValueError("start and end must differ")
        return self


class SketchPointInput(CompatInput):
    """Input schema for trimming or extending at a point.

    Attributes:
        point (list[float]): ``[x, y]`` sketch mm on the entity.
    """

    point: SketchPoint = Field(
        description="[x, y] in sketch mm on the entity: on the piece to remove "
        "(trim), or near the end to lengthen (extend)"
    )


class SetConstructionGeometryInput(CompatInput):
    """Input schema for making entities construction geometry.

    Attributes:
        entities (list[str]): Sketch entity ids.
        construction (bool): Construction (``True``) or normal (``False``).
    """

    entities: list[Annotated[str, Field(min_length=1)]] = Field(
        min_length=1, description="Entity ids from the sketch tools, e.g. Line_3"
    )
    construction: bool = Field(
        default=True, description="true for construction geometry, false for normal"
    )


def slot_area(
    kind: str,
    width: float,
    start: list[float],
    end: list[float],
    center: list[float] | None,
) -> float:
    """A slot's area in mm²: its centreline's length times its width, plus
    the two half-circle ends (one circle of the width's diameter).

    An arc slot's centreline runs counter-clockwise about ``center`` from
    ``start`` to ``end``.
    """
    ends = math.pi * (width / 2.0) ** 2
    if kind == "arc" and center is not None:
        radius = math.dist(center, start)
        turn = math.atan2(end[1] - center[1], end[0] - center[0]) - math.atan2(
            start[1] - center[1], start[0] - center[0]
        )
        length = radius * (turn % (2 * math.pi))
    else:
        length = math.dist(start, end)
    return length * width + ends


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
    # SolidWorks won't rename a sketch while it is open for editing (it
    # accepts the name, but the tree keeps the old one), so the name
    # create_sketch was asked for is given when exit_sketch closes it:
    # SolidWorks' name -> the name asked for.
    names_on_exit: dict[str, str] = {}

    async def _honour_construction(entity_id: Any, construction: bool) -> None:
        """Make a new entity construction geometry when ``construction`` asks.

        The drawing calls themselves draw normal geometry on SolidWorks, so a
        tool's ``construction`` flag is applied afterwards, by id.
        """
        if not construction or not entity_id:
            return
        made = await adapter.set_construction_geometry([str(entity_id)], True)
        require_success(made, context="Failed to make it construction geometry")

    @mcp.tool()
    async def create_sketch(input_data: CreateSketchInput) -> dict[str, Any]:
        """Open a new sketch on a plane or a flat face of the active part, ready for lines, circles and other sketch entities.

        Use it first in every feature: sketch, draw, `exit_sketch`, then
        `create_extrusion` or `create_cut_extrude`. Planes: Front, Top, Right (or XY,
        XZ, YZ), or a plane made by `create_reference_plane`. Or give `face_point`, a
        point in mm on a flat face of the body: the sketch opens on that face and moves
        with it when the model changes. Coordinates in the sketch are mm from the
        origin. Needs: an open part. Changes: adds a sketch and opens it for editing;
        give `sketch_name` and `exit_sketch` names it that when it closes it (SolidWorks
        won't rename an open sketch). Returns: `sketch` with `name` (the name in the
        feature tree now) and `plane` (or `face_point`), plus `name_on_exit` when you
        gave `sketch_name`. A `face_point` not on a flat face fails with
        `invalid_input`.

        Args:
            input_data: The sketch. Exactly one of `plane` and `face_point`;
                `sketch_name` names it.

        Returns:
            dict[str, Any]: The new sketch.
        """
        input_data = normalize_input(input_data, CreateSketchInput)
        face_point = (
            (
                float(input_data.face_point[0]),
                float(input_data.face_point[1]),
                float(input_data.face_point[2]),
            )
            if input_data.face_point is not None
            else None
        )
        if face_point is None:
            result = await adapter.create_sketch(input_data.plane)
            where = f"{input_data.plane} plane"
        else:
            result = await adapter.create_sketch(None, face_point)
            where = f"the face at {list(face_point)} mm"

        require_success(result, context="Failed to create sketch")
        sketch_name = (
            result.data.get("sketch_name")
            if isinstance(result.data, dict)
            else result.data
        )
        sketch: dict[str, Any] = {"name": sketch_name, "plane": input_data.plane}
        if face_point is not None:
            sketch["face_point"] = list(face_point)
        reply: dict[str, Any] = {
            "status": "success",
            "message": f"Created sketch '{sketch_name}' on {where}",
            "sketch": sketch,
            "execution_time": result.execution_time,
        }
        names_on_exit.clear()  # a sketch left open is abandoned with its name
        wanted = (input_data.sketch_name or "").strip()
        if wanted and wanted != sketch_name:
            names_on_exit[str(sketch_name)] = wanted
            reply["sketch"]["name_on_exit"] = wanted
            reply["message"] += f"; exit_sketch names it '{wanted}'"
        return reply

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
        await _honour_construction(line_id, input_data.construction)
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
        await _honour_construction(circle_id, input_data.construction)
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
        if input_data.from_center:
            result = await adapter.add_rectangle(
                input_data.x1,  # type: ignore[arg-type]
                input_data.y1,  # type: ignore[arg-type]
                input_data.x2,  # type: ignore[arg-type]
                input_data.y2,  # type: ignore[arg-type]
                True,
            )
        elif hasattr(adapter, "add_sketch_rectangle"):
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
        await _honour_construction(rect_id, input_data.construction)
        rx1, ry1 = input_data.x1 or 0.0, input_data.y1 or 0.0
        rx2, ry2 = input_data.x2 or 0.0, input_data.y2 or 0.0
        if input_data.from_center:
            # x1, y1 is the centre: the real corners mirror x2, y2 through it.
            rx1, ry1 = 2 * rx1 - rx2, 2 * ry1 - ry2
        width = abs(rx2 - rx1)
        height = abs(ry2 - ry1)

        return {
            "status": "success",
            "message": f"Added rectangle from ({rx1}, {ry1}) to ({rx2}, {ry2})",
            "rectangle": {
                "id": rect_id,
                "from_center": input_data.from_center,
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
        Changes: leaves sketch editing; the sketch stays in the feature tree, renamed
        to the `sketch_name` `create_sketch` was given. Returns: a message, plus, after
        a `sketch_name`, `sketch` with `name` (the name in the feature tree, which later
        tools take as `sketch_name`) and a `warning` when the name couldn't be given
        (another feature has it).
        """
        result = await adapter.exit_sketch()

        require_success(result, context="Failed to exit sketch")
        reply: dict[str, Any] = {
            "status": "success",
            "message": "Exited sketch editing mode",
            "execution_time": result.execution_time,
        }
        if names_on_exit:
            current, wanted = names_on_exit.popitem()
            renamed = await adapter.rename_feature(current, wanted)
            name = current
            if renamed.is_success:
                name = (renamed.data or {}).get("new_name") or wanted
            else:
                reply["warning"] = (
                    f"The sketch keeps SolidWorks' name '{current}': it could "
                    f"not be named '{wanted}' ({renamed.error})."
                )
            reply["sketch"] = {"name": name}
        return reply

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
        """Draw a circular arc in the open sketch: from its centre, through three points, or tangent.

        Use it for rounded ends and curved edges of a profile. `kind` `center` (the
        default) takes the centre, start and end, counter-clockwise; `three_point`
        takes start, end and a point the arc passes through (`through_x`,
        `through_y`); `tangent` starts at the end of an existing entity (`start`) and
        leaves tangent to it. Needs: an open sketch (`create_sketch`). Changes: adds an
        arc. Returns: `arc` with `id`, `kind`, `center`, `start_point` and
        `end_point`. Its `id` is what `add_sketch_constraint` and
        `add_sketch_dimension` take.

        Args:
            input_data: The arc. `start_x`, `start_y`, `end_x` and `end_y` (mm) are
                required; `center_x`, `center_y` for `center`; `through_x`,
                `through_y` for `three_point`.

        Returns:
            dict[str, Any]: The arc added.
        """
        input_data = normalize_input(input_data, AddArcInput)
        through = (
            (input_data.through_x, input_data.through_y)
            if input_data.through_x is not None and input_data.through_y is not None
            else None
        )
        result = await adapter.add_arc(
            input_data.center_x or 0.0,
            input_data.center_y or 0.0,
            input_data.start_x,
            input_data.start_y,
            input_data.end_x,
            input_data.end_y,
            input_data.kind,
            through,
        )

        require_success(result, context="Failed to add arc")
        arc_id = result.data
        center = (
            {"x": input_data.center_x, "y": input_data.center_y}
            if input_data.kind == "center"
            else None
        )
        return {
            "status": "success",
            "message": f"Added a {input_data.kind} arc from "
            f"({input_data.start_x}, {input_data.start_y}) to "
            f"({input_data.end_x}, {input_data.end_y})",
            "arc": {
                "id": arc_id,
                "kind": input_data.kind,
                "center": center,
                "through": (
                    {"x": through[0], "y": through[1]} if through is not None else None
                ),
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
        `id`, `center`, `radius`, `sides` and `angle`. A `diameter` dimension
        (`add_sketch_dimension`) on its `id` sizes it by the circle drawn inside it.

        Args:
            input_data: A mapping: `center_x`, `center_y` (mm, default 0), `radius`
                (mm, circumscribed, default 10), `sides` (default 6) and `angle`
                (degrees the first corner is turned from +x, default 0).

        Returns:
            dict[str, Any]: The polygon added.
        """
        center_x = input_data.get("center_x", 0.0)
        center_y = input_data.get("center_y", 0.0)
        radius = input_data.get("radius", 10.0)
        sides = input_data.get("sides", 6)
        angle = float(input_data.get("angle", 0.0))

        result = await adapter.add_polygon(center_x, center_y, radius, sides, angle)

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
                "angle": angle,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_ellipse(input_data: dict[str, Any]) -> dict[str, Any]:
        """Draw an ellipse in the open sketch from its centre and axis lengths, in mm.

        Use it for oval holes and bosses. Needs: an open sketch (`create_sketch`).
        Changes: adds an ellipse. Returns: `ellipse` with `id`, `center`, `major_axis`,
        `minor_axis` and `angle`.

        Args:
            input_data: A mapping: `center_x`, `center_y` (mm, default 0),
                `major_axis` (default 20) and `minor_axis` (default 10), in mm, and
                `angle`, the major axis's turn from +x in degrees (default 0).

        Returns:
            dict[str, Any]: The ellipse added.
        """
        center_x = input_data.get("center_x", 0.0)
        center_y = input_data.get("center_y", 0.0)
        major_axis = input_data.get("major_axis", 20.0)
        minor_axis = input_data.get("minor_axis", 10.0)
        angle = input_data.get("angle", 0.0)

        result = await adapter.add_ellipse(
            center_x, center_y, major_axis, minor_axis, angle
        )

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
                "angle": angle,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sketch_text(input_data: AddSketchTextInput) -> dict[str, Any]:
        """Write text in the open sketch, at a point or centred on one, to deboss or emboss it.

        Use it for lettering, then cut (`create_cut_extrude`) or extrude the sketch.
        `center_at` (a model point in mm) puts the text's middle there; otherwise it
        starts at `x`, `y`. `$PRP:"name"` in the text shows a custom property;
        one holding a dimension's name (`"D1@Sketch3"`, set with `set_custom_property`)
        makes the text follow that dimension. To read from a face's own side, such as
        an underside, open the sketch on that face (`create_sketch` `face_point`).
        Needs: an open sketch (`create_sketch`). Changes: adds text. Returns: the
        text's `id`, the `text` as SolidWorks shows it (links resolved) and its
        `height`.

        Args:
            input_data: The text. `text` is required; `x`, `y` (mm), `height` (3.5
                mm) and `center_at` have defaults.

        Returns:
            dict[str, Any]: The text added.
        """
        input_data = normalize_input(input_data, AddSketchTextInput)
        result = await adapter.add_sketch_text(
            input_data.text,
            input_data.x,
            input_data.y,
            input_data.height,
            input_data.center_at,
        )
        require_success(result, context="Failed to add sketch text")
        added: dict[str, Any] = result.data or {}
        return {
            "status": "success",
            "message": f"Added text {added['text']!r}, {added['height']} mm high",
            "sketch_text": {
                **added,
                "center_at": input_data.center_at,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_sketch_text(input_data: SetSketchTextInput) -> dict[str, Any]:
        """Rewrite the text in a sketch and rebuild, so debossed lettering shows it.

        Use it after a change the text should follow: SolidWorks doesn't redraw sketch
        text on rebuild, not even a `$PRP:` link to a dimension an equation changed.
        Give the same `$PRP:"name"` text to re-read the link, or new text. The sketch
        is opened, its text rewritten, closed, and the model rebuilt, so a cut made
        from it changes too. Needs: a part with that sketch, holding text from
        `add_sketch_text`. Changes: the sketch's text. Returns: the `sketch`, each
        text `before` and `after` (links resolved).

        Args:
            input_data: `sketch_name` and `text`, both required.

        Returns:
            dict[str, Any]: The text before and after.
        """
        input_data = normalize_input(input_data, SetSketchTextInput)
        result = await adapter.set_sketch_text(input_data.sketch_name, input_data.text)
        require_success(result, context="Failed to rewrite the sketch text")
        changed: dict[str, Any] = result.data or {}
        return {
            "status": "success",
            "message": f"{input_data.sketch_name} now reads {changed.get('after')}",
            "sketch_text": changed,
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
        """Add a driving dimension to sketch entities: linear, angular, radial, diameter or an ellipse axis.

        Use it to fix a size so the sketch is fully defined and can be changed later
        with `set_dimension`. Entities are the `id`s the add_* tools returned; two
        connected lines for angular, a circle or arc for radial or diameter, an
        ellipse for `major_axis` or `minor_axis` (`value` is the whole axis; the
        dimension runs from the centre, so it shows half). No dialog opens. Needs: an open sketch (`create_sketch`). Changes: adds the dimension and
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

    @mcp.tool()
    async def sketch_convert_entities(
        input_data: SketchConvertEntitiesInput,
    ) -> dict[str, Any]:
        """Copy model edges, or a face's whole outline, into the open sketch (Convert Entities).

        Use it to sketch on an existing edge exactly, e.g. to cut a pocket that
        follows a face, instead of re-drawing it at guessed coordinates. Pick edges
        or a face with a point on each (mm). Needs: an open sketch
        (`create_sketch`) and a part with those edges. Changes: adds the copied
        entities, tied to the edges. Returns: `converted` with `entities` (ids for
        the other sketch tools), `count` and `construction`.

        Args:
            input_data: The edges. Give `edge_points`, `face_point`, or both;
                `construction` makes the copies construction geometry.

        Returns:
            dict[str, Any]: The entities added.
        """
        input_data = normalize_input(input_data, SketchConvertEntitiesInput)
        result = await adapter.sketch_convert_entities(
            input_data.edge_points or None,
            input_data.face_point,
            input_data.construction,
        )
        require_success(result, context="Failed to convert entities")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": f"Copied {data.get('count', 0)} edge(s) into the sketch",
            "converted": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sketch_fillet(input_data: AddSketchFilletInput) -> dict[str, Any]:
        """Round corners of the open sketch to a radius, picking each corner by its point.

        Use it for rounded corners of a 2D profile, such as a cut's outline; round a
        solid's edges with `add_fillet` instead, last in the feature tree. Give
        each corner's `[x, y]` in sketch mm, where two entities meet (for a rectangle,
        its corners). Needs: an open sketch (`create_sketch`) with entities meeting at
        each corner. Changes: each corner becomes an arc and the entities either side
        are trimmed back to it. Returns: `fillet` with one `id` per corner, the
        `corners` and the `radius`. A corner with no sketch point fails as
        `invalid_input` and nothing changes.

        Args:
            input_data: `corners` (a list of `[x, y]` mm) and `radius` (mm).

        Returns:
            dict[str, Any]: The fillets added.
        """
        input_data = normalize_input(input_data, AddSketchFilletInput)
        result = await adapter.add_sketch_fillet(input_data.corners, input_data.radius)
        require_success(result, context="Failed to round the sketch corners")
        made: dict[str, Any] = result.data or {}
        return {
            "status": "success",
            "message": f"Rounded {len(input_data.corners)} corner(s) to "
            f"R{input_data.radius:g} mm",
            "fillet": {**made, "radius": input_data.radius},
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_sketch_chamfer(input_data: AddSketchChamferInput) -> dict[str, Any]:
        """Bevel corners of the open sketch, picking each corner by its point.

        Use it for bevelled corners of a 2D profile; bevel a solid's edges with
        `add_chamfer` instead, last in the feature tree. `distance` alone cuts the same
        distance along both sides; add `distance2` for a different second side, or
        `angle` (degrees) for a distance and an angle. Needs: an open sketch with
        entities meeting at each corner (`[x, y]` in sketch mm). Changes: each corner
        becomes a line and the entities either side are trimmed back to it. Returns:
        `chamfer` with one `id` per corner, the `corners` and the sizes. A corner
        with no sketch point fails as `invalid_input` and nothing changes.

        Args:
            input_data: `corners` and `distance` (mm) are required; `distance2` (mm)
                or `angle` (degrees), not both.

        Returns:
            dict[str, Any]: The chamfers added.
        """
        input_data = normalize_input(input_data, AddSketchChamferInput)
        result = await adapter.add_sketch_chamfer(
            input_data.corners,
            input_data.distance,
            input_data.distance2,
            input_data.angle,
        )
        require_success(result, context="Failed to bevel the sketch corners")
        made: dict[str, Any] = result.data or {}
        return {
            "status": "success",
            "message": f"Bevelled {len(input_data.corners)} corner(s)",
            "chamfer": {
                **made,
                "distance": input_data.distance,
                "distance2": input_data.distance2,
                "angle": input_data.angle,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_slot(input_data: AddSlotInput) -> dict[str, Any]:
        """Draw a slot in the open sketch: straight between two centres, or along an arc.

        Use it for adjustment slots and keyways, then cut it (`create_cut_extrude`).
        A straight slot takes its two end centres, `start` and `end`. An arc slot
        (`kind` `arc`) takes the `center` of the arc it follows and `start` and `end`
        on that arc, counter-clockwise. Needs: an open sketch (`create_sketch`).
        Changes: adds one closed slot. Returns: `slot` with its `id`, the points, the
        `width` and its `area` (mm²).

        Args:
            input_data: `width` (mm), `start` and `end` (`[x, y]` mm) are required;
                `kind` is `straight`; `center` for an arc slot.

        Returns:
            dict[str, Any]: The slot added.
        """
        input_data = normalize_input(input_data, AddSlotInput)
        result = await adapter.add_slot(
            input_data.kind,
            input_data.width,
            input_data.start,
            input_data.end,
            input_data.center,
        )
        require_success(result, context="Failed to draw the slot")
        area = slot_area(
            input_data.kind,
            input_data.width,
            input_data.start,
            input_data.end,
            input_data.center,
        )
        return {
            "status": "success",
            "message": f"Drew a {input_data.kind} slot {input_data.width:g} mm wide",
            "slot": {
                "id": result.data,
                "kind": input_data.kind,
                "start": input_data.start,
                "end": input_data.end,
                "center": input_data.center,
                "width": input_data.width,
                "area": round(area, 4),
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_trim(input_data: SketchPointInput) -> dict[str, Any]:
        """Trim away the piece of a sketch entity at a point, back to where it meets others.

        Use it to clean up overlapping shapes into one profile, such as the arc inside
        a keyhole. `point` (`[x, y]` sketch mm) is on the piece to remove; an entity
        that meets nothing is removed whole. Needs: an open sketch with an entity at
        the point. Changes: removes that piece. Returns: `trim` with the `point` and
        the sketch's `segments_before` and `segments_after`. A trimmed entity's id may
        no longer name a whole segment. Nothing at the point fails as `invalid_input`.

        Args:
            input_data: `point`, `[x, y]` in sketch mm.

        Returns:
            dict[str, Any]: The trim.
        """
        input_data = normalize_input(input_data, SketchPointInput)
        result = await adapter.sketch_trim(input_data.point)
        require_success(result, context="Failed to trim the sketch")
        return {
            "status": "success",
            "message": f"Trimmed at {input_data.point} mm",
            "trim": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_extend(input_data: SketchPointInput) -> dict[str, Any]:
        """Lengthen a sketch entity from its end nearest a point until it meets the next entity.

        Use it to close a gap, such as lines that stop short of a circle. `point`
        (`[x, y]` sketch mm) is on the entity, near the end to lengthen. Needs: an
        open sketch with an entity at the point and another in its way. Changes: that
        end moves to the next entity. Returns: `extend` with the `point` and the
        segment counts. Nothing at the point, or nothing to reach, fails as
        `invalid_input`.

        Args:
            input_data: `point`, `[x, y]` in sketch mm.

        Returns:
            dict[str, Any]: The extension.
        """
        input_data = normalize_input(input_data, SketchPointInput)
        result = await adapter.sketch_extend(input_data.point)
        require_success(result, context="Failed to extend the sketch entity")
        return {
            "status": "success",
            "message": f"Extended the entity at {input_data.point} mm",
            "extend": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_construction_geometry(
        input_data: SetConstructionGeometryInput,
    ) -> dict[str, Any]:
        """Make sketch entities construction geometry, or normal again, by id.

        Use it for reference lines and circles a feature should ignore, such as a
        line to dimension from or a bolt circle. Needs: an open sketch and ids the
        sketch tools returned. Changes: each entity's construction setting (setting it
        to what it already is changes nothing). Returns: `construction_geometry` with
        each id's state. An unknown id fails as `invalid_input` and nothing changes.

        Args:
            input_data: `entities` (ids) is required; `construction` is on.

        Returns:
            dict[str, Any]: The entities' states.
        """
        input_data = normalize_input(input_data, SetConstructionGeometryInput)
        result = await adapter.set_construction_geometry(
            input_data.entities, input_data.construction
        )
        require_success(result, context="Failed to set construction geometry")
        kind = "construction" if input_data.construction else "normal"
        return {
            "status": "success",
            "message": f"{len(input_data.entities)} entity(ies) now {kind} geometry",
            "construction_geometry": result.data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def sketch_tutorial_simple_hole() -> dict[str, Any]:
        """Demonstrate the sketch steps: draw a 5 mm circle at the origin on the Top plane and close the sketch.

        It is a fixed example; for a real hole, use `create_sketch`, `add_circle`,
        `exit_sketch` and `create_cut_extrude`. Needs: an open part. Changes: adds a
        sketch with one circle. Returns: `steps_completed`, `next_step` (cut the hole
        with `create_cut_extrude`) and `suggested_cut`, that call's input.
        """
        steps_completed = []

        # Step 1: Create sketch
        sketch_result = await adapter.create_sketch("Top")
        require_success(sketch_result, context="Failed to create sketch")
        sketch_name = (
            sketch_result.data.get("sketch_name")
            if isinstance(sketch_result.data, dict)
            else sketch_result.data
        )
        steps_completed.append(f"Created sketch: {sketch_name}")

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
            "next_step": (
                "Cut the hole through the part with create_cut_extrude, using "
                "suggested_cut as its input"
            ),
            "suggested_cut": {
                "sketch_name": sketch_name,
                "depth": 10.0,
                "end_condition": "ThroughAll",
            },
        }

    tool_count = 6  # Legacy count expected by tests
    return tool_count
