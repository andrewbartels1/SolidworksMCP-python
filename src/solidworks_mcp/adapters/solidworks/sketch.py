"""Sketch-domain mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

import time
from typing import Any, cast

from ..base import AdapterResult, AdapterResultStatus

# swConstraintType_e values per the official SolidWorks API enum docs
# (SolidWorks.Interop.swconst). The legacy IModelDoc2.SketchAddConstraints
# API takes string identifiers but on SW 2026/3DEXPERIENCE silently no-ops
# without adding the relation. ISketchRelationManager.AddRelation takes
# these integer enum values and works reliably.
RELATION_NAME_MAP: dict[str, int] = {
    "horizontal": 4,
    "vertical": 5,
    "tangent": 6,
    "parallel": 7,
    "perpendicular": 8,
    "coincident": 9,
    "concentric": 10,
    "equal": 14,  # swConstraintType_SAMELENGTH
    "fix": 17,  # swConstraintType_FIXED
    "collinear": 27,  # swConstraintType_COLINEAR (single-l spelling)
    # NOTE: swConstraintType_SYMMETRIC (11) is intentionally omitted — it
    # requires a third selection (the centerline of symmetry) and the
    # AddRelationInput schema only carries entity1/entity2. A future API
    # extension that accepts a centerline ID can add it back.
}


class SolidWorksSketchMixin:
    """Expose sketch creation and editing methods via mixin-local implementation."""

    @staticmethod
    def _adapter(obj: Any) -> Any:
        """Return the runtime adapter object for dynamic attribute access."""
        return cast(Any, obj)

    def _point_xyz(self, point_obj: Any) -> tuple[float, float, float] | None:
        adapter = self._adapter(self)
        return cast(
            tuple[float, float, float] | None,
            adapter._sketch_geometry.point_xyz(point_obj),
        )

    def _set_point_xyz(self, point_obj: Any, x: float, y: float, z: float) -> bool:
        adapter = self._adapter(self)
        return cast(bool, adapter._sketch_geometry.set_point_xyz(point_obj, x, y, z))

    def _read_segment_endpoints(
        self, entity: Any
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        adapter = self._adapter(self)
        return cast(
            tuple[tuple[float, float, float], tuple[float, float, float]] | None,
            adapter._sketch_geometry.read_segment_endpoints(entity),
        )

    def _segment_point_objects(self, entity: Any) -> tuple[Any | None, Any | None]:
        adapter = self._adapter(self)
        return cast(
            tuple[Any | None, Any | None],
            adapter._sketch_geometry.segment_point_objects(entity),
        )

    def _shared_segment_vertex(
        self, entity1: Any, entity2: Any
    ) -> tuple[Any, Any, Any] | None:
        adapter = self._adapter(self)
        return cast(
            tuple[Any, Any, Any] | None,
            adapter._sketch_geometry.shared_segment_vertex(entity1, entity2),
        )

    def _smart_dimension_direction(self, dx: float, dy: float) -> int:
        adapter = self._adapter(self)
        return cast(int, adapter._sketch_geometry.smart_dimension_direction(dx, dy))

    def _single_line_dimension_placement(
        self, entity: Any
    ) -> tuple[float, float, float, int] | None:
        adapter = self._adapter(self)
        return cast(
            tuple[float, float, float, int] | None,
            adapter._sketch_geometry.single_line_dimension_placement(entity),
        )

    def _angular_dimension_placement(
        self, entity1: Any, entity2: Any
    ) -> tuple[float, float, float, int] | None:
        adapter = self._adapter(self)
        return cast(
            tuple[float, float, float, int] | None,
            adapter._sketch_geometry.angular_dimension_placement(entity1, entity2),
        )

    async def create_sketch(self, plane: str) -> AdapterResult[str]:
        return _create_sketch_impl(self, plane)

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        return _add_line_impl(self, x1, y1, x2, y2)

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        return _add_circle_impl(self, center_x, center_y, radius)

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        return _add_rectangle_impl(self, x1, y1, x2, y2)

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> AdapterResult[str]:
        return _add_arc_impl(self, center_x, center_y, start_x, start_y, end_x, end_y)

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        return _add_spline_impl(self, points)

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        return _add_centerline_impl(self, x1, y1, x2, y2)

    async def add_polygon(
        self, center_x: float, center_y: float, radius: float, sides: int
    ) -> AdapterResult[str]:
        return _add_polygon_impl(self, center_x, center_y, radius, sides)

    async def add_ellipse(
        self, center_x: float, center_y: float, major_axis: float, minor_axis: float
    ) -> AdapterResult[str]:
        return _add_ellipse_impl(self, center_x, center_y, major_axis, minor_axis)

    async def add_sketch_constraint(
        self, entity1: str, entity2: str | None, relation_type: str
    ) -> AdapterResult[str]:
        return _add_sketch_constraint_impl(self, entity1, entity2, relation_type)

    async def add_sketch_dimension(
        self, entity1: str, entity2: str | None, dimension_type: str, value: float
    ) -> AdapterResult[str]:
        return _add_sketch_dimension_impl(self, entity1, entity2, dimension_type, value)

    async def sketch_linear_pattern(
        self,
        entities: list[str],
        direction_x: float,
        direction_y: float,
        spacing: float,
        count: int,
    ) -> AdapterResult[str]:
        return _sketch_linear_pattern_impl(
            self, entities, direction_x, direction_y, spacing, count
        )

    async def sketch_circular_pattern(
        self,
        entities: list[str],
        center_x: float,
        center_y: float,
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        return _sketch_circular_pattern_impl(
            self, entities, center_x, center_y, angle, count
        )

    async def sketch_mirror(
        self, entities: list[str], mirror_line: str
    ) -> AdapterResult[str]:
        return _sketch_mirror_impl(self, entities, mirror_line)

    async def sketch_offset(
        self, entities: list[str], offset_distance: float, reverse_direction: bool
    ) -> AdapterResult[str]:
        return _sketch_offset_impl(self, entities, offset_distance, reverse_direction)

    async def exit_sketch(self) -> AdapterResult[None]:
        return _exit_sketch_impl(self)

    async def check_sketch_fully_defined(
        self, sketch_name: str | None = None
    ) -> AdapterResult[dict[str, Any]]:
        return _check_sketch_fully_defined_impl(self, sketch_name)


def _create_sketch_impl(adapter: Any, plane: str) -> AdapterResult[str]:
    """Open a new sketch on a named reference plane.

    The function resolves English short-hand names (``"Top"``, ``"Front"``,
    ``"Right"``, ``"XY"``, ``"XZ"``, ``"YZ"``) to their full SolidWorks plane
    names and also tries Spanish locale aliases (``"Planta"``, ``"Alzado"``,
    ``"Vista lateral"``).  If named lookup fails, ``Extension.SelectByID2``
    with entity type ``"PLANE"`` is attempted with three different callout
    variants.

    When the sketch is successfully opened, ``adapter.currentSketchManager``,
    ``adapter.currentSketch``, ``adapter._sketch_count``, and
    ``adapter._last_sketch_name`` are updated.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        plane: Reference-plane identifier.  Accepts short English names
            (``"Top"``, ``"Front"``, ``"Right"``, ``"XY"``, ``"XZ"``,
            ``"YZ"``) or the exact SolidWorks plane name as it appears in
            the FeatureManager tree.

    Returns:
        AdapterResult[str]: On success, ``data`` is the sketch name string
        (e.g. ``"Sketch1"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when no plane
            candidate can be selected.

    Example::

        from solidworks_mcp.adapters import pywin32_sketch_ops

        result = pywin32_sketch_ops.create_sketch(adapter, "Front")
        print(result.data)  # "Sketch1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _sketch_operation() -> str:
        """Inner COM closure that selects the plane and opens the sketch.

        Iterates through all locale aliases and ``SelectByID2`` fallbacks.
        Updates adapter sketch state on success.

        Returns:
            str: The resolved SolidWorks sketch name.

        Raises:
            Exception: If no plane candidate could be selected.
        """
        plane_name_map = {
            "Top": "Top Plane",
            "Front": "Front Plane",
            "Right": "Right Plane",
            "XY": "Top Plane",
            "XZ": "Front Plane",
            "YZ": "Right Plane",
        }

        semantic_plane_aliases = {
            "Top": ["Top Plane", "Planta"],
            "Front": ["Front Plane", "Alzado"],
            "Right": ["Right Plane", "Vista lateral"],
            "XY": ["Top Plane", "Planta"],
            "XZ": ["Front Plane", "Alzado"],
            "YZ": ["Right Plane", "Vista lateral"],
        }

        actual_plane = plane_name_map.get(plane, plane)
        selected = False
        selection_error = None

        plane_candidates = [
            *semantic_plane_aliases.get(plane, []),
            actual_plane,
            plane,
            "Top Plane",
            "Front Plane",
            "Right Plane",
            "Planta",
            "Alzado",
            "Vista lateral",
        ]
        for candidate in plane_candidates:
            if not candidate:
                continue
            plane_feature, selection_error_candidate = adapter._attempt_with_error(
                lambda c=candidate: adapter.currentModel.FeatureByName(c)
            )
            if selection_error_candidate:
                selection_error = selection_error_candidate
                continue
            selected = bool(
                plane_feature
                and adapter._attempt(
                    lambda pf=plane_feature: pf.Select2(False, 0), default=False
                )
            )
            if selected:
                break

        if not selected:
            for callout in ("", None, 0):
                selected, selection_error_candidate = adapter._attempt_with_error(
                    lambda co=callout: adapter.currentModel.Extension.SelectByID2(
                        actual_plane,
                        "PLANE",
                        0,
                        0,
                        0,
                        False,
                        0,
                        co,
                        0,
                    )
                )
                if selection_error_candidate:
                    selection_error = selection_error_candidate
                    continue
                if selected:
                    break

        if not selected:
            if selection_error:
                raise Exception(
                    f"Failed to select plane: {actual_plane} ({selection_error})"
                )
            raise Exception(f"Failed to select plane: {actual_plane}")

        adapter.currentSketchManager = adapter.currentModel.SketchManager
        adapter._reset_sketch_entity_registry()
        try:
            adapter.currentSketch = adapter.currentSketchManager.InsertSketch(True)
        except Exception:
            adapter.currentSketch = adapter.currentSketchManager.InsertSketch()

        if not adapter.currentSketch:
            adapter.currentSketch = adapter._attempt(
                lambda: adapter.currentModel.GetActiveSketch2()
            )

        adapter._sketch_count += 1

        if adapter.currentSketch and hasattr(adapter.currentSketch, "Name"):
            sketch_name = str(adapter.currentSketch.Name)
            adapter._last_sketch_name = sketch_name
            return sketch_name

        sketch_name = f"Sketch_{adapter._sketch_count}"
        adapter._last_sketch_name = sketch_name
        return sketch_name

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("create_sketch", _sketch_operation),
    )


def _add_line_impl(
    adapter: Any, x1: float, y1: float, x2: float, y2: float
) -> AdapterResult[str]:
    """Add a straight line segment to the active sketch.

    Calls ``SketchManager.CreateLine`` and registers the resulting entity in
    the adapter\'s internal sketch-entity registry so it can be referenced by
    subsequent dimension and constraint calls.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch
            (``currentSketchManager`` must be non-``None``).
        x1: Start X coordinate in **millimetres**.
        y1: Start Y coordinate in **millimetres**.
        x2: End X coordinate in **millimetres**.
        y2: End Y coordinate in **millimetres**.

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        string (e.g. ``"Line_1"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateLine`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_line(adapter, 0, 0, 50, 0)
        print(result.data)  # "Line_1"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _line_operation() -> str:
        """Inner COM closure that calls CreateLine and registers the entity.

        Returns:
            str: Registered entity ID for the new line.

        Raises:
            Exception: If ``CreateLine`` returns ``None``.
        """
        line = adapter.currentSketchManager.CreateLine(
            x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
        )
        if not line:
            raise Exception("Failed to create line")
        return cast(AdapterResult[str], adapter._register_sketch_entity("Line", line))

    return cast(
        AdapterResult[str], adapter._handle_com_operation("add_line", _line_operation)
    )


def _add_circle_impl(
    adapter: Any, center_x: float, center_y: float, radius: float
) -> AdapterResult[str]:
    """Add a circle to the active sketch defined by centre and radius.

    Calls ``SketchManager.CreateCircleByRadius`` and registers the entity.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Circle centre X coordinate in **millimetres**.
        center_y: Circle centre Y coordinate in **millimetres**.
        radius: Circle radius in **millimetres**.

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        (e.g. ``"Circle_2"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateCircleByRadius`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_circle(adapter, 25.0, 0.0, 10.0)
        print(result.data)  # "Circle_2"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _circle_operation() -> str:
        """Inner COM closure that calls CreateCircleByRadius and registers the entity.

        Returns:
            str: Registered entity ID for the new circle.

        Raises:
            Exception: If ``CreateCircleByRadius`` returns ``None``.
        """
        circle = adapter.currentSketchManager.CreateCircleByRadius(
            center_x / 1000.0, center_y / 1000.0, 0, radius / 1000.0
        )
        if not circle:
            raise Exception("Failed to create circle")
        return cast(
            AdapterResult[str], adapter._register_sketch_entity("Circle", circle)
        )

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_circle", _circle_operation),
    )


def _add_rectangle_impl(
    adapter: Any, x1: float, y1: float, x2: float, y2: float
) -> AdapterResult[str]:
    """Add a corner-defined rectangle to the active sketch.

    Calls ``SketchManager.CreateCornerRectangle`` which returns an array of
    four line entities.  The array is registered as a single composite entity.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        x1: First corner X coordinate in **millimetres**.
        y1: First corner Y coordinate in **millimetres**.
        x2: Opposite corner X coordinate in **millimetres**.
        y2: Opposite corner Y coordinate in **millimetres**.

    Returns:
        AdapterResult[str]: On success, ``data`` is the composite entity ID
        (e.g. ``"Rectangle_3"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateCornerRectangle`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_rectangle(adapter, 0, 0, 40, 20)
        print(result.data)  # "Rectangle_3"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _rectangle_operation() -> str:
        """Inner COM closure that calls CreateCornerRectangle and registers the entity.

        Returns:
            str: Registered entity ID for the new rectangle.

        Raises:
            Exception: If ``CreateCornerRectangle`` returns ``None``.
        """
        lines = adapter.currentSketchManager.CreateCornerRectangle(
            x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
        )
        if not lines:
            raise Exception("Failed to create rectangle")
        return cast(
            AdapterResult[str], adapter._register_sketch_entity("Rectangle", lines)
        )

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_rectangle", _rectangle_operation),
    )


def _add_arc_impl(
    adapter: Any,
    center_x: float,
    center_y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> AdapterResult[str]:
    """Add a circular arc to the active sketch.

    Calls ``SketchManager.CreateArc`` with a counter-clockwise direction
    flag (``1``).  All coordinates must lie in the sketch plane; the Z
    component is always forced to ``0``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Arc centre X in **millimetres**.
        center_y: Arc centre Y in **millimetres**.
        start_x: Arc start point X in **millimetres**.
        start_y: Arc start point Y in **millimetres**.
        end_x: Arc end point X in **millimetres**.
        end_y: Arc end point Y in **millimetres**.

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        (e.g. ``"Arc_4"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateArc`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_arc(
            adapter,
            center_x=0, center_y=0,
            start_x=10, start_y=0,
            end_x=0, end_y=10,
        )
        print(result.data)  # "Arc_4"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _arc_operation() -> str:
        """Inner COM closure that calls CreateArc and registers the entity.

        Returns:
            str: Registered entity ID for the new arc.

        Raises:
            Exception: If ``CreateArc`` returns ``None``.
        """
        arc = adapter.currentSketchManager.CreateArc(
            center_x / 1000.0,
            center_y / 1000.0,
            0,
            start_x / 1000.0,
            start_y / 1000.0,
            0,
            end_x / 1000.0,
            end_y / 1000.0,
            0,
            1,
        )
        if not arc:
            raise Exception("Failed to create arc")
        return cast(AdapterResult[str], adapter._register_sketch_entity("Arc", arc))

    return cast(
        AdapterResult[str], adapter._handle_com_operation("add_arc", _arc_operation)
    )


def _add_spline_impl(
    adapter: Any, points: list[dict[str, float]]
) -> AdapterResult[str]:
    """Add a NURBS spline through the supplied control points.

    Calls ``SketchManager.CreateSpline2`` with the flattened XYZ coordinate
    list.  Each point dict must contain ``"x"`` and ``"y"`` keys; the Z
    component is forced to ``0``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        points: Ordered list of control-point dicts with keys ``"x"`` and
            ``"y"`` (in **millimetres**).  Minimum 2 points required by
            SolidWorks.  Example::

                [{"x": 0, "y": 0}, {"x": 25, "y": 10}, {"x": 50, "y": 0}]

    Returns:
        AdapterResult[str]: On success, ``data`` is a timestamped entity ID
        string (e.g. ``"Spline_7832"``).  On failure, ``status`` is
        ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateSpline2`` returns ``None``.

    Example::

        pts = [{"x": 0, "y": 0}, {"x": 20, "y": 15}, {"x": 40, "y": 0}]
        result = pywin32_sketch_ops.add_spline(adapter, pts)
        print(result.data)  # "Spline_5412"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _spline_operation() -> str:
        """Inner COM closure that flattens the point list and calls CreateSpline2.

        Returns:
            str: A timestamped unique spline ID (not registered in entity
            registry because splines do not support individual selection by
            the current dimension API).

        Raises:
            Exception: If ``CreateSpline2`` returns ``None``.
        """
        spline_points = []
        for point in points:
            spline_points.extend([point["x"] / 1000.0, point["y"] / 1000.0, 0])

        spline = adapter.currentSketchManager.CreateSpline2(spline_points, True, None)
        if not spline:
            raise Exception("Failed to create spline")
        return f"Spline_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_spline", _spline_operation),
    )


def _add_centerline_impl(
    adapter: Any, x1: float, y1: float, x2: float, y2: float
) -> AdapterResult[str]:
    """Add a construction centre-line to the active sketch.

    Centre-lines are used as rotation axes for revolve features and as
    mirror lines for symmetric sketches.  Calls
    ``SketchManager.CreateCenterLine``; the resulting entity is not
    registered in the entity registry because it cannot be dimensioned
    independently.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        x1: Start X in **millimetres**.
        y1: Start Y in **millimetres**.
        x2: End X in **millimetres**.
        y2: End Y in **millimetres**.

    Returns:
        AdapterResult[str]: On success, ``data`` is a timestamped ID string
        (e.g. ``"Centerline_9341"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateCenterLine`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_centerline(adapter, 0, -20, 0, 20)
        print(result.data)  # "Centerline_9341"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _centerline_operation() -> str:
        """Inner COM closure that calls CreateCenterLine.

        Returns:
            str: Timestamped unique ID string.

        Raises:
            Exception: If ``CreateCenterLine`` returns ``None``.
        """
        centerline = adapter.currentSketchManager.CreateCenterLine(
            x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
        )
        if not centerline:
            raise Exception("Failed to create centerline")
        return f"Centerline_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_centerline", _centerline_operation),
    )


def _add_polygon_impl(
    adapter: Any,
    center_x: float,
    center_y: float,
    radius: float,
    sides: int,
) -> AdapterResult[str]:
    """Add a regular polygon inscribed in a circle to the active sketch.

    Calls ``SketchManager.CreatePolygon``.  The polygon is inscribed so that
    all vertices lie on a circle of the given ``radius``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Polygon centre X in **millimetres**.
        center_y: Polygon centre Y in **millimetres**.
        radius: Circumscribed circle radius in **millimetres**.
        sides: Number of polygon sides.  SolidWorks accepts 3–40.

    Returns:
        AdapterResult[str]: On success, ``data`` is a descriptive timestamped
        ID (e.g. ``"Polygon_6sided_1234"``).  On failure, ``status`` is
        ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreatePolygon`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_polygon(
            adapter, center_x=0, center_y=0, radius=15.0, sides=6
        )
        print(result.data)  # "Polygon_6sided_4321"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _polygon_operation() -> str:
        """Inner COM closure that calls CreatePolygon.

        Returns:
            str: Descriptive timestamped ID for the polygon.

        Raises:
            Exception: If ``CreatePolygon`` returns ``None``.
        """
        polygon = adapter.currentSketchManager.CreatePolygon(
            center_x / 1000.0,
            center_y / 1000.0,
            0,
            radius / 1000.0,
            sides,
            0,
        )
        if not polygon:
            raise Exception("Failed to create polygon")
        return f"Polygon_{sides}sided_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_polygon", _polygon_operation),
    )


def _add_ellipse_impl(
    adapter: Any,
    center_x: float,
    center_y: float,
    major_axis: float,
    minor_axis: float,
) -> AdapterResult[str]:
    """Add an axis-aligned ellipse to the active sketch.

    Calls ``SketchManager.CreateEllipse`` with the major-axis endpoint on the
    positive X direction from the centre and the minor-axis endpoint on the
    positive Y direction.  The ellipse is therefore axis-aligned and cannot
    be rotated via this function.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Ellipse centre X in **millimetres**.
        center_y: Ellipse centre Y in **millimetres**.
        major_axis: Full major-axis length in **millimetres** (half is used
            as the offset from centre).
        minor_axis: Full minor-axis length in **millimetres** (half is used
            as the offset from centre).

    Returns:
        AdapterResult[str]: On success, ``data`` is a timestamped ID string
        (e.g. ``"Ellipse_6789"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateEllipse`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_ellipse(
            adapter, center_x=0, center_y=0, major_axis=30.0, minor_axis=15.0
        )
        print(result.data)  # "Ellipse_2345"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _ellipse_operation() -> str:
        """Inner COM closure that calls CreateEllipse.

        Returns:
            str: Timestamped unique ID for the ellipse.

        Raises:
            Exception: If ``CreateEllipse`` returns ``None``.
        """
        ellipse = adapter.currentSketchManager.CreateEllipse(
            center_x / 1000.0,
            center_y / 1000.0,
            0,
            (center_x + major_axis / 2) / 1000.0,
            center_y / 1000.0,
            0,
            center_x / 1000.0,
            (center_y + minor_axis / 2) / 1000.0,
            0,
        )
        if not ellipse:
            raise Exception("Failed to create ellipse")
        return f"Ellipse_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_ellipse", _ellipse_operation),
    )


def _add_sketch_constraint_impl(
    adapter: Any,
    entity1: str,
    entity2: str | None,
    relation_type: str,
) -> AdapterResult[str]:
    """Add a geometric relation (constraint) between sketch entities.

    Resolves ``entity1`` (and ``entity2`` if provided) against the adapter's
    sketch-entity registry, then calls
    ``ISketchRelationManager.AddRelation(entities, relation_type_enum)`` on
    the active sketch. Entity handles are passed as a
    ``VARIANT(VT_ARRAY | VT_DISPATCH, [...])`` — pywin32 will not marshal a
    plain Python list of CDispatch objects to a SAFEARRAY by itself.

    The legacy ``IModelDoc2.SketchAddConstraints`` API silently no-ops on
    SW 2026/3DEXPERIENCE despite accepting the call, so this implementation
    uses the modern ``ISketchRelationManager.AddRelation`` per the official
    SolidWorks API docs.

    Supported ``relation_type`` strings (case-insensitive): ``"horizontal"``,
    ``"vertical"``, ``"parallel"``, ``"perpendicular"``, ``"tangent"``,
    ``"coincident"``, ``"concentric"``, ``"equal"``, ``"symmetric"``,
    ``"collinear"``, ``"fix"``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch and a valid
            ``currentModel``.
        entity1: Registered entity ID of the primary sketch entity (from a
            prior ``add_line`` / ``add_circle`` call).
        entity2: Registered entity ID of the secondary sketch entity, or
            ``None`` for single-entity relations (horizontal, vertical, fix).
        relation_type: Constraint type string (see above).

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        of the new constraint object (e.g. ``"Constraint_3"``). On failure,
        ``status`` is ``ERROR``.
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _constraint_operation() -> str:
        if not adapter.currentModel:
            raise Exception("No active model")

        relation_type_enum = RELATION_NAME_MAP.get(
            (relation_type or "").strip().lower()
        )
        if relation_type_enum is None:
            supported = ", ".join(sorted(RELATION_NAME_MAP))
            raise Exception(
                f"Unsupported relation type '{relation_type}'. Supported: {supported}"
            )

        entity1_obj = adapter._sketch_entities.get(entity1)
        if entity1_obj is None:
            raise Exception(
                f"Unknown sketch entity '{entity1}'. Use IDs returned by add_line/add_arc/add_circle."
            )

        entities = [entity1_obj]
        if entity2:
            entity2_obj = adapter._sketch_entities.get(entity2)
            if entity2_obj is None:
                raise Exception(
                    f"Unknown sketch entity '{entity2}'. Use IDs returned by add_line/add_arc/add_circle."
                )
            entities.append(entity2_obj)

        # Flag IModelDoc2 + ISketch + ISketchRelationManager so late-binding
        # resolves GetActiveSketch2, RelationManager, and AddRelation as
        # methods/properties correctly.
        try:
            from .. import sw_type_info as _sw_type_info
        except ImportError:
            _sw_type_info = None  # type: ignore[assignment]
        if _sw_type_info is not None:
            adapter._attempt(
                lambda: _sw_type_info.flag_methods(adapter.currentModel, "IModelDoc2"),
                default=0,
            )

        active_sketch = adapter._attempt(
            lambda: adapter.currentModel.GetActiveSketch2(), default=None
        )
        if active_sketch is None:
            raise Exception(
                "No active sketch on the model — create_sketch first or "
                "open the existing sketch for edit."
            )
        if _sw_type_info is not None:
            adapter._attempt(
                lambda: _sw_type_info.flag_methods(active_sketch, "ISketch"),
                default=0,
            )

        relmgr = adapter._attempt(lambda: active_sketch.RelationManager, default=None)
        if relmgr is None:
            raise Exception("Active sketch has no RelationManager")
        if _sw_type_info is not None:
            adapter._attempt(
                lambda: _sw_type_info.flag_methods(relmgr, "ISketchRelationManager"),
                default=0,
            )

        # pywin32 won't auto-marshal a Python list of CDispatch entities to a
        # SAFEARRAY. The VT_ARRAY|VT_DISPATCH variant is the shape SolidWorks
        # accepts. Import is lazy so the module still imports in mock/CI
        # environments without pywin32.
        try:
            import pythoncom as _pythoncom
            from win32com.client import VARIANT as _VARIANT
        except ImportError as exc:  # pragma: no cover
            raise Exception(
                "pywin32 is required for add_sketch_constraint on a real adapter"
            ) from exc

        ents_variant = _VARIANT(_pythoncom.VT_ARRAY | _pythoncom.VT_DISPATCH, entities)
        sketch_relation, add_err = adapter._attempt_with_error(
            lambda: relmgr.AddRelation(ents_variant, relation_type_enum)
        )
        if add_err is not None or sketch_relation is None:
            target = f"'{entity1}'" + (f" and '{entity2}'" if entity2 else "")
            detail = f": {add_err}" if add_err else ""
            raise Exception(
                f"SolidWorks rejected '{relation_type}' relation on {target}{detail}"
            )

        return cast(
            str,
            adapter._register_sketch_entity("Constraint", sketch_relation),
        )

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_sketch_constraint", _constraint_operation),
    )


def _add_sketch_dimension_impl(
    adapter: Any,
    entity1: str,
    entity2: str | None,
    dimension_type: str,
    value: float,
) -> AdapterResult[str]:
    """Add a driven dimension to one or two registered sketch entities.

        Supports linear, angular, radial, and diameter dimensions:

    * **linear** — places a horizontal or vertical smart dimension on a single
      entity.  The text-placement point is computed by
      ``adapter._single_line_dimension_placement``.
    * **angular** — places an angular dimension between two connected line
      segments sharing a common vertex.  The vertex is found via
      ``adapter._shared_segment_vertex`` and multiple direction/segment
      combinations are tried until one succeeds.
    * **radial** / **diameter** — places a radius or diameter dimension on a
      selected sketch arc or circle using ``IModelDoc2.AddRadialDimension2`` or
      ``IModelDoc2.AddDiameterDimension2``.

    SolidWorks can otherwise enter the interactive ``Modify`` approval flow
    during sketch dimension creation. The adapter keeps the relevant
    sketch-input preferences disabled for the full automation session in
    ``_ComSessionCoordinator.set_automation_preferences`` and uses the dedicated
    radial/diameter APIs here because that path is more reliable in unattended
    COM sessions.

    Dimensional values for **linear** dimensions are in **millimetres**;
    for **angular** dimensions they are in **degrees**.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch and a valid
            ``currentModel`` and ``swApp``.
        entity1: Registered entity ID of the primary sketch entity.
        entity2: Registered entity ID of a secondary sketch entity (required
            for angular dimensions), or ``None``.
        dimension_type: ``"linear"``, ``"angular"``, ``"radial"``, or
            ``"diameter"`` (case-insensitive).
        value: Dimension value. Millimetres for linear, radial, and diameter;
            degrees for angular.

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        of the new dimension object.  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the
            entity IDs cannot be resolved, the placement cannot be computed,
            or the SolidWorks ``AddDimension`` call fails.

    Example::

        # Dimension a line to 50 mm
        result = pywin32_sketch_ops.add_sketch_dimension(
            adapter, "Line_1", None, "linear", 50.0
        )
        print(result.data)  # "Dimension_7"

        # Angular dimension between two intersecting lines
        result = pywin32_sketch_ops.add_sketch_dimension(
            adapter, "Line_1", "Line_2", "angular", 45.0
        )
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _dimension_operation() -> str:
        """Inner COM closure that resolves entities, places and values the dimension.

        Resolves entity objects from the adapter registry, computes the
        placement point, suppresses the interactive value dialog, calls
        ``AddDimension``, then sets the dimensional value via
        ``SetSystemValue3`` / ``SetSystemValue2`` / ``SystemValue`` fallbacks.

        Returns:
            str: Registered entity ID for the new dimension display object.

        Raises:
            Exception: If entity IDs are unknown, placement cannot be
                determined, or the COM call fails.
        """
        import math as _math_dim

        def _radial_dimension_placement() -> tuple[float, float, float, int]:
            """Compute a deterministic placement for radial/diameter dimensions.

            Avoids additional COM geometry reads that can block on some live sessions.
            """
            offset = max(0.01, min(0.05, abs(value) / 1000.0 + 0.01))
            return (
                offset,
                offset,
                0.0,
                adapter.constants["swSmartDimensionDirectionUp"],
            )

        if not adapter.currentModel:
            return f"Dimension_{int(time.time() * 1000) % 10000}"

        entity1_obj = adapter._sketch_entities.get(entity1)
        if entity1_obj is None:
            raise Exception(
                f"Unknown sketch entity '{entity1}'. Use IDs returned by add_line/add_arc/add_circle."
            )

        entity2_obj = None
        if entity2:
            entity2_obj = adapter._sketch_entities.get(entity2)
            if entity2_obj is None:
                raise Exception(
                    f"Unknown sketch entity '{entity2}'. Use IDs returned by add_line/add_arc/add_circle."
                )

        dim_type = (dimension_type or "linear").strip().lower()
        placement = None
        if dim_type == "angular" and entity2_obj is not None:
            placement = adapter._angular_dimension_placement(entity1_obj, entity2_obj)
        elif dim_type == "linear":
            placement = adapter._single_line_dimension_placement(entity1_obj)
        elif dim_type in {"radial", "diameter"}:
            placement = _radial_dimension_placement()

        if placement is None:
            raise Exception(
                f"Unsupported or ambiguous dimension placement for type '{dim_type}'"
            )

        text_x, text_y, text_z, direction = placement

        def _try_create_angular_dimension() -> Any:
            """Attempt to create an angular dimension between two line segments.

            Finds the shared vertex between ``entity1_obj`` and
            ``entity2_obj``, then iterates through every (segment, vertex,
            direction) combination until SolidWorks accepts the placement.

            Returns:
                Any: The SolidWorks display-dimension COM object on success,
                or ``None`` if all attempts fail.
            """
            shared_vertex = adapter._shared_segment_vertex(entity1_obj, entity2_obj)
            if shared_vertex is None:
                return None

            _, vertex1, vertex2 = shared_vertex
            segment_attempts = ((entity1_obj, vertex1), (entity2_obj, vertex2))
            direction_attempts = [direction] + [
                candidate
                for candidate in (
                    adapter.constants["swSmartDimensionDirectionRight"],
                    adapter.constants["swSmartDimensionDirectionUp"],
                    adapter.constants["swSmartDimensionDirectionLeft"],
                    adapter.constants["swSmartDimensionDirectionDown"],
                )
                if candidate != direction
            ]

            for segment_obj, vertex_obj in segment_attempts:
                for candidate_direction in direction_attempts:
                    adapter.currentModel.ClearSelection2(True)
                    if not adapter._select_sketch_entity(segment_obj, append=False):
                        continue
                    if not adapter._attempt(
                        lambda vo=vertex_obj: bool(vo.Select2(True, 0)), default=False
                    ):
                        continue
                    display_dim = adapter._attempt(
                        lambda d=candidate_direction: (
                            adapter.currentModel.Extension.AddDimension(
                                text_x, text_y, text_z, d
                            )
                        ),
                        default=None,
                    )
                    if display_dim:
                        return display_dim
            return None

        if dim_type == "angular":
            display_dim = _try_create_angular_dimension()
        else:
            adapter.currentModel.ClearSelection2(True)
            if not adapter._select_sketch_entity(entity1_obj, append=False):
                raise Exception(f"Failed to select primary entity '{entity1}'")
            if entity2_obj is not None and not adapter._select_sketch_entity(
                entity2_obj, append=True
            ):
                raise Exception(f"Failed to select secondary entity '{entity2}'")

            if dim_type == "radial":
                display_dim = adapter._attempt(
                    lambda: adapter.currentModel.AddRadialDimension2(
                        text_x, text_y, text_z
                    ),
                    default=None,
                )
            elif dim_type == "diameter":
                display_dim = adapter._attempt(
                    lambda: adapter.currentModel.AddDiameterDimension2(
                        text_x, text_y, text_z
                    ),
                    default=None,
                )
            else:
                # Use a single deterministic AddDimension call for non-angular
                # dimensions that require extension-line direction.
                display_dim = adapter._attempt(
                    lambda: adapter.currentModel.Extension.AddDimension(
                        text_x, text_y, text_z, direction
                    ),
                    default=None,
                )

            if not display_dim:
                raise Exception("SolidWorks failed to create sketch dimension")

            if dim_type == "angular":
                value_si = value * _math_dim.pi / 180.0
            else:
                value_si = value / 1000.0

            dim_obj = (
                adapter._attempt(lambda: display_dim.GetDimension2(0), default=None)
                or adapter._attempt(lambda: display_dim.GetDimension(), default=None)
                or display_dim
            )
            if (
                adapter._attempt(
                    lambda: dim_obj.SetSystemValue3(value_si, 1, None), default=None
                )
                is None
            ):
                if (
                    adapter._attempt(
                        lambda: dim_obj.SetSystemValue2(value_si, 1), default=None
                    )
                    is None
                ):
                    if hasattr(dim_obj, "SystemValue"):
                        dim_obj.SystemValue = value_si

        return cast(
            AdapterResult[str],
            adapter._register_sketch_entity("Dimension", display_dim),
        )

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_sketch_dimension", _dimension_operation),
    )


def _sketch_linear_pattern_impl(
    adapter: Any,
    entities: list[str],
    direction_x: float,
    direction_y: float,
    spacing: float,
    count: int,
) -> AdapterResult[str]:
    """Create a linear sketch pattern — placeholder, not yet fully implemented.

    Retained for interface compatibility.  Currently returns a descriptive
    placeholder ID without invoking SolidWorks.  Full implementation will call
    ``SketchManager.CreateLinearSketchStepAndRepeat``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: List of registered entity IDs to pattern (currently unused).
        direction_x: Pattern direction X component (currently unused).
        direction_y: Pattern direction Y component (currently unused).
        spacing: Distance between instances in **millimetres**.
        count: Number of instances (including the seed).

    Returns:
        AdapterResult[str]: ``data`` is a placeholder ID string such as
        ``"LinearPattern_4x10.0_1234"``.

    Example::

        result = pywin32_sketch_ops.sketch_linear_pattern(
            adapter, ["Line_1"], 1, 0, 10.0, 4
        )
        print(result.data)  # "LinearPattern_4x10.0_8765"
    """
    _ = entities, direction_x, direction_y
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _linear_pattern_operation() -> str:
        return f"LinearPattern_{count}x{spacing}_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation(
            "sketch_linear_pattern", _linear_pattern_operation
        ),
    )


def _sketch_circular_pattern_impl(
    adapter: Any,
    entities: list[str],
    center_x: float,
    center_y: float,
    angle: float,
    count: int,
) -> AdapterResult[str]:
    """Create a circular sketch pattern — placeholder, not yet fully implemented.

    Retained for interface compatibility.  Currently returns a descriptive
    placeholder ID.  Full implementation will call
    ``SketchManager.CreateCircularSketchStepAndRepeat``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: List of registered entity IDs to pattern (currently unused).
        center_x: Pattern centre X in **millimetres** (currently unused).
        center_y: Pattern centre Y in **millimetres** (currently unused).
        angle: Angular spacing between instances in **degrees**.
        count: Number of instances (including the seed).

    Returns:
        AdapterResult[str]: ``data`` is a placeholder ID such as
        ``"CircularPattern_6x60.0deg_2345"``.

    Example::

        result = pywin32_sketch_ops.sketch_circular_pattern(
            adapter, ["Circle_2"], 0, 0, 60.0, 6
        )
        print(result.data)  # "CircularPattern_6x60.0deg_2345"
    """
    _ = entities, center_x, center_y
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _circular_pattern_operation() -> str:
        return f"CircularPattern_{count}x{angle}deg_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation(
            "sketch_circular_pattern", _circular_pattern_operation
        ),
    )


def _sketch_mirror_impl(
    adapter: Any, entities: list[str], mirror_line: str
) -> AdapterResult[str]:
    """Mirror sketch entities across a centre-line — placeholder, not yet fully implemented.

    Retained for interface compatibility.  Full implementation will select the
    mirror line entity, append the source entities, and call
    ``SketchManager.SketchMirror``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: List of registered entity IDs to mirror (currently unused).
        mirror_line: Registered entity ID of the centre-line to mirror across.

    Returns:
        AdapterResult[str]: ``data`` is a placeholder ID such as
        ``"Mirror_Centerline_1_3456"``.

    Example::

        result = pywin32_sketch_ops.sketch_mirror(
            adapter, ["Line_1", "Line_2"], "Centerline_1"
        )
        print(result.data)  # "Mirror_Centerline_1_3456"
    """
    _ = entities
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _mirror_operation() -> str:
        return f"Mirror_{mirror_line}_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("sketch_mirror", _mirror_operation),
    )


def _sketch_offset_impl(
    adapter: Any,
    entities: list[str],
    offset_distance: float,
    reverse_direction: bool,
) -> AdapterResult[str]:
    """Offset sketch entities by a fixed distance — placeholder, not yet fully implemented.

    Retained for interface compatibility.  Full implementation will select the
    source entities and call ``SketchManager.SketchOffset``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: List of registered entity IDs to offset (currently unused).
        offset_distance: Offset distance in **millimetres**.
        reverse_direction: When ``True``, offset inwards; when ``False``,
            offset outwards.

    Returns:
        AdapterResult[str]: ``data`` is a placeholder ID such as
        ``"Offset_5.0_inward_9876"``.

    Example::

        result = pywin32_sketch_ops.sketch_offset(
            adapter, ["Line_1"], 5.0, reverse_direction=False
        )
        print(result.data)  # "Offset_5.0_outward_9876"
    """
    _ = entities
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _offset_operation() -> str:
        direction = "inward" if reverse_direction else "outward"
        return f"Offset_{offset_distance}_{direction}_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("sketch_offset", _offset_operation),
    )


def _exit_sketch_impl(adapter: Any) -> AdapterResult[None]:
    """Exit the current sketch editing mode and return to the part/assembly context.

    Calls ``SketchManager.InsertSketch(True)`` which toggles the sketch editor
    off.  After the call succeeds, ``adapter.currentSketch``,
    ``adapter.currentSketchManager``, and the sketch entity registry are all
    cleared.

    Args:
        adapter: A ``PyWin32Adapter`` that is currently in sketch-edit mode
            (``currentSketchManager`` must be non-``None``).

    Returns:
        AdapterResult[None]: On success, ``status`` is ``SUCCESS`` and
        ``data`` is ``None``.  When no sketch is active, ``status`` is
        ``WARNING`` (not an error, already exited).

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the COM
            call raises unexpectedly.

    Example::

        pywin32_sketch_ops.add_line(adapter, 0, 0, 50, 0)
        pywin32_sketch_ops.exit_sketch(adapter)
        # adapter.currentSketch is now None
    """
    if not adapter.currentSketchManager:
        return AdapterResult(
            status=AdapterResultStatus.WARNING, error="No active sketch to exit"
        )

    def _exit_operation() -> None:
        """Inner COM closure that toggles the sketch editor off and clears state.

        Returns:
            None: Always returns ``None`` on success.
        """
        adapter.currentSketchManager.InsertSketch(True)
        adapter.currentSketch = None
        adapter.currentSketchManager = None
        adapter._reset_sketch_entity_registry()
        return None

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("exit_sketch", _exit_operation),
    )


def _check_sketch_fully_defined_impl(
    adapter: Any,
    sketch_name: str | None = None,
) -> AdapterResult[dict[str, Any]]:
    """Check whether a sketch is fully constrained (fully defined).

    Queries the SolidWorks sketch object through multiple probe methods
    because different API versions expose this information differently:

    * ``ISketch.IsFullyConstrained`` (SolidWorks 2018+)
    * ``ISketch.GetStatus`` returning a status integer
    * ``ISketch.FullyDefined`` property

    All raw values are normalised through ``_probe_to_flag`` which handles
    bool, int, float, and string representations.  When the targeted sketch
    cannot be found, the active model\'s current sketch is probed instead.

    Args:
        adapter: A ``PyWin32Adapter`` with a non-``None`` ``currentModel``.
        sketch_name: Name of the sketch feature as it appears in the
            FeatureManager tree (e.g. ``"Sketch1"``).  When ``None``, the
            adapter\'s ``_last_sketch_name`` is used, then the currently open
            sketch.

    Returns:
        AdapterResult[dict[str, Any]]: On success, ``data`` is a dict:

        .. code-block:: python

            {
                "sketch_name": "Sketch1",
                "fully_defined": True,          # bool or None
                "state": "fully_defined",        # or "not_fully_defined" / "unknown"
                "source_api": "IsFullyConstrained",  # probe that succeeded
            }

        On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` on unexpected
            COM errors.

    Example::

        result = pywin32_sketch_ops.check_sketch_fully_defined(adapter, "Sketch1")
        if result.data["fully_defined"]:
            print("Sketch is fully constrained")
        else:
            print("Sketch state:", result.data["state"])
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _to_bool(value: Any) -> bool | None:
        """Normalise an arbitrary raw value to a Python bool.

        Handles booleans, 0/1 integers and floats, truthy/falsy strings, and
        single-element sequences.

        Args:
            value: Raw value from a SolidWorks COM attribute or method return.

        Returns:
            bool | None: ``True``, ``False``, or ``None`` when the value is
            ambiguous or unrecognised.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and int(value) in (0, 1):
            return bool(int(value))
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "fully_defined", "fully defined"}:
                return True
            if normalized in {
                "false",
                "no",
                "under_defined",
                "under defined",
                "over_defined",
                "over defined",
            }:
                return False
        if isinstance(value, (list, tuple)) and value:
            return _to_bool(value[0])
        return None

    def _to_number(value: Any) -> float | None:
        """Normalise an arbitrary raw value to a float.

        Args:
            value: Raw value from a COM attribute or method return.

        Returns:
            float | None: Numeric value, or ``None`` when conversion fails.
        """
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        if isinstance(value, (list, tuple)) and value:
            return _to_number(value[0])
        return None

    def _probe_to_flag(source: str, raw: Any) -> bool | None:
        """Interpret a raw probe result according to the property-name semantics.

        The SolidWorks API uses both positive and negative naming conventions
        (``IsFullyConstrained`` vs ``IsUnderDefined``) so the source name is
        used as a hint when interpreting the raw value.

        Args:
            source: The name of the API attribute that produced ``raw``, e.g.
                ``"IsFullyConstrained"`` or ``"IsUnderDefined"``.
            raw: The raw return value from the COM attribute.

        Returns:
            bool | None: ``True`` if the sketch is fully defined, ``False`` if
            not, or ``None`` when interpretation is impossible.
        """
        source_lower = source.lower()
        text_value = str(raw).strip().lower() if raw is not None else ""
        numeric_value = _to_number(raw)

        if "underdefined" in source_lower or "under_defined" in source_lower:
            if numeric_value is not None:
                return numeric_value == 0
            bool_value = _to_bool(raw)
            if bool_value is not None:
                return not bool_value

        if "overdefined" in source_lower or "over_defined" in source_lower:
            if numeric_value is not None and numeric_value > 0:
                return False
            bool_value = _to_bool(raw)
            if bool_value is True:
                return False

        if "fullydefined" in source_lower or "fully_defined" in source_lower:
            bool_value = _to_bool(raw)
            if bool_value is not None:
                return bool_value

        if (
            "fully" in text_value
            and "under" not in text_value
            and "over" not in text_value
        ):
            return True
        if "under" in text_value or "over" in text_value:
            return False

        return _to_bool(raw)

    def _state_from_bool(flag: bool | None) -> str:
        """Convert a nullable bool flag to a descriptive state string.

        Args:
            flag: The fully-defined flag value.

        Returns:
            str: ``"fully_defined"``, ``"not_fully_defined"``, or
            ``"unknown"``.
        """
        if flag is True:
            return "fully_defined"
        if flag is False:
            return "not_fully_defined"
        return "unknown"

    def _get_sketch_payload() -> dict[str, Any]:
        """Main inner closure that locates the sketch and probes its constraint status.

        Resolves the sketch feature by name (falling back to the last-known
        name and then the currently open sketch).  Iterates through multiple
        API probes in priority order, stops at the first conclusive result.

        Returns:
            dict[str, Any]: Payload dict with keys ``sketch_name``,
            ``fully_defined``, ``state``, and ``source_api``.

        Raises:
            Exception: On unexpected COM errors during feature lookup.
        """
        sketch_feature = None
        sketch_obj = None
        resolved_name = sketch_name

        if sketch_name:
            sketch_feature = adapter._attempt(
                lambda: adapter.currentModel.FeatureByName(sketch_name), default=None
            )
            if not sketch_feature:
                raise Exception(f"Sketch not found: {sketch_name}")
            sketch_obj = adapter._attempt(
                lambda: sketch_feature.GetSpecificFeature2(), default=None
            )
        else:
            sketch_obj = adapter.currentSketch or adapter._attempt(
                lambda: adapter.currentModel.GetActiveSketch2(), default=None
            )
            if sketch_obj is None and adapter._last_sketch_name:
                sketch_feature = adapter._attempt(
                    lambda: adapter.currentModel.FeatureByName(
                        adapter._last_sketch_name
                    ),
                    default=None,
                )
                sketch_obj = adapter._attempt(
                    lambda: sketch_feature.GetSpecificFeature2(), default=None
                )
                resolved_name = adapter._last_sketch_name

        if sketch_obj is None and sketch_feature is None:
            raise Exception("No active sketch found")

        if resolved_name is None and sketch_feature is not None:
            resolved_name = adapter._attempt(
                lambda: str(sketch_feature.Name), default=None
            )

        probes: list[tuple[str, Any]] = []

        for label, obj in (("sketch", sketch_obj), ("feature", sketch_feature)):
            if obj is None:
                continue
            for attr_name in (
                "GetFullyDefined",
                "IsFullyDefined",
                "FullyDefined",
                "GetFullyDefinedStatus",
                "GetSketchStatus",
                "GetStatus",
                "GetUnderDefined",
                "IsUnderDefined",
                "UnderDefined",
                "GetUnderDefinedCount",
                "UnderDefinedCount",
                "GetUnderDefinedEntitiesCount",
                "GetUnderDefinedSketchEntitiesCount",
                "GetOverDefinedCount",
                "OverDefinedCount",
                "GetFullyDefineStatus",
            ):
                value = adapter._attempt(
                    lambda o=obj, a=attr_name: adapter._get_attr_or_call(o, a),
                    default=None,
                )
                if value is None:
                    continue
                probes.append((f"{label}.{attr_name}", value))

        for source, raw in probes:
            flag = _probe_to_flag(source, raw)
            if flag is None:
                continue

            return {
                "sketch_name": resolved_name,
                "is_fully_defined": flag,
                "definition_state": _state_from_bool(flag),
                "source": source,
                "raw_status": raw,
            }

        return {
            "sketch_name": resolved_name,
            "is_fully_defined": None,
            "definition_state": "unknown",
            "source": "unavailable",
            "raw_status": None,
        }

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation(
            "check_sketch_fully_defined", _get_sketch_payload
        ),
    )
