"""Sketch-domain mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

import math
import sys
import time
from typing import Any, cast

from .. import sw_type_info as _sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import as_list, double_array
from .com_utils import flag as _flag_members
from .default_entities import entity_name
from .features import _null_callout

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
    "symmetric": 11,  # swConstraintType_SYMMETRIC — requires entity3 (centerline)
    "equal": 14,  # swConstraintType_SAMELENGTH
    "fix": 17,  # swConstraintType_FIXED
    "collinear": 27,  # swConstraintType_COLINEAR (single-l spelling)
}

#: ``swTangentArcTypes_e.swForward``: a tangent arc that carries on in the
#: direction the entity it starts from was going.
_TANGENT_FORWARD = 1

# Relations that take a third entity (the centerline of symmetry for now).
# All other relations reject a non-null ``entity3``.
_THREE_ENTITY_RELATIONS: frozenset[str] = frozenset({"symmetric"})


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

    async def create_sketch(
        self,
        plane: str | None,
        face_point: tuple[float, float, float] | None = None,
    ) -> AdapterResult[str]:
        return _create_sketch_impl(self, plane, face_point)

    async def add_line(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        return _add_line_impl(self, x1, y1, x2, y2)

    async def add_circle(
        self, center_x: float, center_y: float, radius: float
    ) -> AdapterResult[str]:
        return _add_circle_impl(self, center_x, center_y, radius)

    async def add_rectangle(
        self, x1: float, y1: float, x2: float, y2: float, from_center: bool = False
    ) -> AdapterResult[str]:
        return _add_rectangle_impl(self, x1, y1, x2, y2, from_center)

    async def add_arc(
        self,
        center_x: float,
        center_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        kind: str = "center",
        through: tuple[float, float] | None = None,
    ) -> AdapterResult[str]:
        return _add_arc_impl(
            self, center_x, center_y, start_x, start_y, end_x, end_y, kind, through
        )

    async def add_spline(self, points: list[dict[str, float]]) -> AdapterResult[str]:
        return _add_spline_impl(self, points)

    async def add_centerline(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> AdapterResult[str]:
        return _add_centerline_impl(self, x1, y1, x2, y2)

    async def add_polygon(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        sides: int,
        angle: float = 0.0,
    ) -> AdapterResult[str]:
        return _add_polygon_impl(self, center_x, center_y, radius, sides, angle)

    async def add_ellipse(
        self,
        center_x: float,
        center_y: float,
        major_axis: float,
        minor_axis: float,
        angle: float = 0.0,
    ) -> AdapterResult[str]:
        return _add_ellipse_impl(
            self, center_x, center_y, major_axis, minor_axis, angle
        )

    async def add_sketch_text(
        self,
        text: str,
        x: float = 0.0,
        y: float = 0.0,
        height: float = 3.5,
        center_at: list[float] | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        return _add_sketch_text_impl(self, text, x, y, height, center_at)

    async def set_sketch_text(
        self, sketch_name: str, text: str
    ) -> AdapterResult[dict[str, Any]]:
        return _set_sketch_text_impl(self, sketch_name, text)

    async def add_sketch_constraint(
        self,
        entity1: str,
        entity2: str | None,
        relation_type: str,
        entity3: str | None = None,
    ) -> AdapterResult[str]:
        return _add_sketch_constraint_impl(
            self, entity1, entity2, relation_type, entity3
        )

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
        angle: float,
        count: int,
    ) -> AdapterResult[str]:
        return _sketch_circular_pattern_impl(self, entities, angle, count)

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

    async def add_sketch_fillet(
        self, corners: list[list[float]], radius: float
    ) -> AdapterResult[dict[str, Any]]:
        return _add_sketch_fillet_impl(self, corners, radius)

    async def add_sketch_chamfer(
        self,
        corners: list[list[float]],
        distance: float,
        distance2: float | None = None,
        angle: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        return _add_sketch_chamfer_impl(self, corners, distance, distance2, angle)

    async def add_slot(
        self,
        kind: str,
        width: float,
        start: list[float],
        end: list[float],
        center: list[float] | None = None,
    ) -> AdapterResult[str]:
        return _add_slot_impl(self, kind, width, start, end, center)

    async def sketch_trim(self, point: list[float]) -> AdapterResult[dict[str, Any]]:
        return _sketch_trim_impl(self, point)

    async def sketch_extend(self, point: list[float]) -> AdapterResult[dict[str, Any]]:
        return _sketch_extend_impl(self, point)

    async def set_construction_geometry(
        self, entities: list[str], construction: bool = True
    ) -> AdapterResult[dict[str, Any]]:
        return _set_construction_geometry_impl(self, entities, construction)


def _select_sketch_plane(adapter: Any, plane: str) -> None:
    """Select the reference plane a new sketch opens on.

    A default plane (``Top``, ``Front Plane``, ``XY``...) is found by its
    place in the tree, so it works in every language and template (#262);
    any other name is used as given. The plane is selected by name
    (``FeatureByName`` then ``Select2``), then ``Extension.SelectByID2``
    with type ``"PLANE"``. A plane that isn't found is never swapped for
    another one.

    Args:
        adapter: A connected adapter with a part open.
        plane: The plane's short or full name.

    Raises:
        LookupError: A default plane the document doesn't have.
        Exception: If the plane could not be selected.
    """
    actual_plane = entity_name(adapter, plane) if plane else plane
    selected = False
    selection_error = None

    if actual_plane:
        plane_feature, selection_error = adapter._attempt_with_error(
            lambda: adapter.currentModel.FeatureByName(actual_plane)
        )
        selected = bool(
            plane_feature
            and adapter._attempt(lambda: plane_feature.Select2(False, 0), default=False)
        )

    if not selected:
        # The callout must be a VT_DISPATCH null: a bare None is a type
        # mismatch (runbook #11; "Typenkonflikt" on German, #262).
        selected, selection_error_candidate = adapter._attempt_with_error(
            lambda: adapter.currentModel.Extension.SelectByID2(
                actual_plane, "PLANE", 0, 0, 0, False, 0, _null_callout(), 0
            )
        )
        if selection_error_candidate:
            selection_error = selection_error_candidate

    if not selected:
        if selection_error:
            raise Exception(
                f"Failed to select plane: {actual_plane} ({selection_error})"
            )
        raise LookupError(
            f"Failed to select plane: {actual_plane}: not found in the "
            "document. Use Front, Top, Right, or a plane's name from "
            "list_features."
        )


def _select_sketch_face(adapter: Any, face_point: tuple[float, float, float]) -> None:
    """Select the flat face of the active part at ``face_point`` for a sketch.

    Uses the same face lookup as ``create_reference_plane``'s ``face_point``
    (the body face whose closest point is within 0.01 mm, which must be
    flat). On any failure the selection is cleared, so no sketch opens on a
    stale selection.

    Args:
        adapter: A connected adapter with a part open.
        face_point: ``(x, y, z)`` in mm on the face.

    Raises:
        LookupError: When no flat face lies at the point.
    """
    from .features import _select_face_at_point

    point = [float(c) for c in face_point]
    adapter._attempt(lambda: adapter.currentModel.ClearSelection2(True), default=None)
    try:
        selected = _select_face_at_point(adapter, point, 0)
        reason = "SolidWorks would not select it"
    except LookupError as exc:
        selected, reason = False, str(exc)
    if not selected:
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
        raise LookupError(
            f"face_point {point} mm is not on a flat face of the active part ({reason})"
        )


def _create_sketch_impl(
    adapter: Any,
    plane: str | None,
    face_point: tuple[float, float, float] | None = None,
) -> AdapterResult[str]:
    """Open a new sketch on a named reference plane, or on a flat face.

    With ``face_point``, the flat face of the active part at that point is
    selected (see :func:`_select_sketch_face`) in place of a plane.

    A default plane (``"Top"``, ``"Front"``, ``"Right"``, ``"XY"`` = Front,
    ``"XZ"`` = Top, ``"YZ"`` = Right, or a full English name) is found by its
    place in the feature tree, so it works in every language and template.
    If named lookup fails, ``Extension.SelectByID2`` with entity type
    ``"PLANE"`` is tried.

    When the sketch is successfully opened, ``adapter.currentSketchManager``,
    ``adapter.currentSketch``, ``adapter._sketch_count``, and
    ``adapter._last_sketch_name`` are updated, and ``ISketchManager.AddToDB``
    is set so entities land at exactly the requested coordinates
    (``exit_sketch`` clears it again).

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        plane: Reference-plane identifier.  Accepts short English names
            (``"Top"``, ``"Front"``, ``"Right"``, ``"XY"``, ``"XZ"``,
            ``"YZ"``) or the exact SolidWorks plane name as it appears in
            the FeatureManager tree.  Ignored when ``face_point`` is given.
        face_point: ``(x, y, z)`` in mm on a flat face of the active part.

    Returns:
        AdapterResult[str]: On success, ``data`` is the sketch name string
        (e.g. ``"Sketch1"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when no plane
            candidate can be selected, or (as ``LookupError``) when
            ``face_point`` is not on a flat face.

    Example::

        from solidworks_mcp.adapters import pywin32_sketch_ops

        result = pywin32_sketch_ops.create_sketch(adapter, "Front")
        print(result.data)  # "Sketch1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _sketch_operation() -> str:
        """Inner COM closure that selects the plane or face and opens the sketch.

        Returns:
            str: The resolved SolidWorks sketch name.

        Raises:
            Exception: If no plane candidate could be selected.
            LookupError: If ``face_point`` is not on a flat face.
        """
        if face_point is not None:
            _select_sketch_face(adapter, face_point)
        else:
            _select_sketch_plane(adapter, str(plane or ""))

        adapter.currentSketchManager = adapter.currentModel.SketchManager
        adapter._attempt(
            lambda: _sw_type_info.flag_methods(
                adapter.currentSketchManager, "ISketchManager"
            ),
            default=0,
        )
        adapter._reset_sketch_entity_registry()
        try:
            adapter.currentSketch = adapter.currentSketchManager.InsertSketch(True)
        except Exception:
            adapter.currentSketch = adapter.currentSketchManager.InsertSketch()
        # Without AddToDB every Create* point snaps to nearby inferred
        # alignments: an end at x=5.2915 landed on x=5 (vertical with an
        # earlier point at x=5) and a 22 mm ring came out 23 mm. Writing
        # straight to the sketch database keeps the requested coordinates.
        # DisplayWhenAdded stays on: it only defers drawing, which would hide
        # entities from a user watching SolidWorks until the next redraw.
        adapter.currentSketchManager.AddToDB = True

        if not (adapter.currentSketch and hasattr(adapter.currentSketch, "Name")):
            # ISketchManager.ActiveSketch is the documented property for
            # "whatever sketch is open right now" — more reliable than
            # trusting InsertSketch's return value, which some SW versions
            # return as an empty Sub result. Try it before the GetActiveSketch2
            # method fallbacks: a bare ``swApp.ActiveDoc`` is not flagged, so
            # its ``GetActiveSketch2`` resolves to a non-callable and silently
            # yields ``None`` — which forces the synthetic ``Sketch_N``
            # fallback name and makes the sketch unselectable by later
            # features (create_cut_extrude included).
            adapter.currentSketch = (
                adapter._attempt(lambda: adapter.currentSketchManager.ActiveSketch)
                or adapter._attempt(lambda: adapter.currentModel.GetActiveSketch2())
                or adapter._attempt(lambda: adapter.swApp.ActiveDoc.GetActiveSketch2())
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
        entity_id: str = adapter._register_sketch_entity("Line", line)
        # The midpoint, in mm: where a dimension to this line is placed.
        adapter._sketch_entity_centers[entity_id] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        return entity_id

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
        entity_id: str = adapter._register_sketch_entity("Circle", circle)
        # The centre, in mm: where a dimension to this circle is placed.
        adapter._sketch_entity_centers[entity_id] = (center_x, center_y)
        return entity_id

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_circle", _circle_operation),
    )


def _add_rectangle_impl(
    adapter: Any,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    from_center: bool = False,
) -> AdapterResult[str]:
    """Add a rectangle to the active sketch, from two corners or its centre.

    Calls ``SketchManager.CreateCornerRectangle`` (or, with ``from_center``,
    ``CreateCenterRectangle``), which returns an array of four line
    entities.  The array is registered as a single composite entity.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        x1: First corner X coordinate in **millimetres**.
        y1: First corner Y coordinate in **millimetres**.
        x2: Opposite corner X coordinate in **millimetres**.
        y2: Opposite corner Y coordinate in **millimetres**.
        from_center: When true, ``x1``/``y1`` is the centre and ``x2``/``y2``
            a corner.

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
        create = (
            adapter.currentSketchManager.CreateCenterRectangle
            if from_center
            else adapter.currentSketchManager.CreateCornerRectangle
        )
        lines = create(x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0)
        if not lines:
            raise Exception("Failed to create rectangle")
        entity_id = cast(str, adapter._register_sketch_entity("Rectangle", lines))
        # Like polygons, rectangles register as a SAFEARRAY tuple of segment
        # handles — no single dispatch ``GetCenterPoint`` to recover the
        # geometric centre from later. Stash it now so the rectangle ID is a
        # valid seed for ``sketch_circular_pattern``.
        adapter._sketch_entity_centers[entity_id] = (
            (x1, y1) if from_center else ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        )
        return entity_id

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
    kind: str = "center",
    through: tuple[float, float] | None = None,
) -> AdapterResult[str]:
    """Add a circular arc to the active sketch.

    ``kind`` picks the call: ``center`` is ``SketchManager.CreateArc`` with a
    counter-clockwise direction flag (``1``); ``three_point`` is
    ``Create3PointArc`` from start to end through ``through``; ``tangent``
    is ``CreateTangentArc`` from ``start`` (the end of an existing entity)
    to ``end``, leaving tangent to that entity (``swForward``, 1). All
    coordinates lie in the sketch plane; the Z component is always ``0``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Arc centre X in **millimetres**.
        center_y: Arc centre Y in **millimetres**.
        start_x: Arc start point X in **millimetres**.
        start_y: Arc start point Y in **millimetres**.
        end_x: Arc end point X in **millimetres**.
        end_y: Arc end point Y in **millimetres**.
        kind: ``center`` (the default), ``three_point`` or ``tangent``.
        through: For ``three_point``, a point on the arc, ``(x, y)`` mm.

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
        manager = adapter.currentSketchManager
        start = (start_x / 1000.0, start_y / 1000.0, 0)
        end = (end_x / 1000.0, end_y / 1000.0, 0)
        if kind == "three_point":
            if through is None:
                raise Exception("A three_point arc needs a through point")
            arc = manager.Create3PointArc(
                *start, *end, through[0] / 1000.0, through[1] / 1000.0, 0
            )
        elif kind == "tangent":
            arc = manager.CreateTangentArc(*start, *end, _TANGENT_FORWARD)
        else:
            arc = manager.CreateArc(
                center_x / 1000.0, center_y / 1000.0, 0, *start, *end, 1
            )
        if not arc:
            raise Exception("Failed to create arc")
        return adapter._register_sketch_entity("Arc", arc)  # type: ignore[no-any-return]

    return cast(
        AdapterResult[str], adapter._handle_com_operation("add_arc", _arc_operation)
    )


def _add_spline_impl(
    adapter: Any, points: list[dict[str, float]]
) -> AdapterResult[str]:
    """Add a NURBS spline through the supplied control points.

    Calls ``SketchManager.CreateSpline2(points, simulateNaturalEnds=False)``
    with a flattened XYZ coordinate list. Each point dict must contain
    ``"x"`` and ``"y"`` keys; the Z component is forced to ``0``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        points: Ordered list of control-point dicts with keys ``"x"`` and
            ``"y"`` (in **millimetres**). Minimum 2 points required by
            SolidWorks. Example::

                [{"x": 0, "y": 0}, {"x": 25, "y": 10}, {"x": 50, "y": 0}]

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity
        ID string (e.g. ``"Spline_5"``). On failure, ``status`` is
        ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when fewer
            than two points are supplied or ``CreateSpline2`` returns
            ``None``.

    Example::

        pts = [{"x": 0, "y": 0}, {"x": 20, "y": 15}, {"x": 40, "y": 0}]
        result = pywin32_sketch_ops.add_spline(adapter, pts)
        print(result.data)  # "Spline_1"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _spline_operation() -> str:
        if len(points) < 2:
            raise Exception("add_spline requires at least 2 points")

        spline_points: list[float] = []
        for point in points:
            spline_points.extend([point["x"] / 1000.0, point["y"] / 1000.0, 0.0])

        # pywin32 late binding unpacks a bare list into N positional
        # VARIANTs, so SolidWorks sees 3*N+1 arguments instead of 2 and
        # rejects the call with DISP_E_BADPARAMCOUNT. Wrap the doubles in a
        # SAFEARRAY VARIANT (VT_ARRAY|VT_R8) — the same lazy-import dance as
        # add_sketch_constraint so non-Windows CI still exercises this path.
        try:
            import pythoncom as _pythoncom
            from win32com.client import VARIANT as _VARIANT
        except ImportError:
            _pythoncom = None
            _VARIANT = None

        points_arg: Any
        if _pythoncom is not None and _VARIANT is not None:
            points_arg = _VARIANT(_pythoncom.VT_ARRAY | _pythoncom.VT_R8, spline_points)
        elif sys.platform == "win32":
            raise Exception("pywin32 is required for add_spline on Windows")
        else:
            points_arg = spline_points

        spline = adapter.currentSketchManager.CreateSpline2(points_arg, False)
        if not spline:
            raise Exception("Failed to create spline")

        # ISketchSpline dispatch does not expose Select4 via IDispatch —
        # GetIDsOfNames returns Member not found. Retrieve the entity as
        # ISketchSegment from the active sketch instead; that interface
        # exposes Select4, which mirror/offset require.
        if adapter.currentSketch is not None:
            adapter._attempt(
                lambda: _sw_type_info.flag_methods(adapter.currentSketch, "ISketch"),
                default=0,
            )
            segments = adapter._attempt(
                lambda: adapter.currentSketch.GetSketchSegments(), default=None
            )
            if segments is not None and len(segments) > 0:
                return cast(
                    str, adapter._register_sketch_entity("Spline", segments[-1])
                )

        return cast(str, adapter._register_sketch_entity("Spline", spline))

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
        """Inner COM closure that calls CreateCenterLine and registers
        the resulting entity so it can be referenced by subsequent
        dimension and constraint calls (e.g. as the centerline of a
        ``symmetric`` relation).

        Returns:
            str: Registered entity ID (e.g. ``"Centerline_3"``).

        Raises:
            Exception: If ``CreateCenterLine`` returns ``None``.
        """
        centerline = adapter.currentSketchManager.CreateCenterLine(
            x1 / 1000.0, y1 / 1000.0, 0, x2 / 1000.0, y2 / 1000.0, 0
        )
        if not centerline:
            raise Exception("Failed to create centerline")
        return cast(str, adapter._register_sketch_entity("Centerline", centerline))

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
    angle: float = 0.0,
) -> AdapterResult[str]:
    """Add a regular polygon inscribed in a circle to the active sketch.

    Calls ``SketchManager.CreatePolygon(XC, YC, Zc, Xp, Yp, Zp, Sides,
    Inscribed)``.  All eight arguments are required by the COM API — passing
    fewer arguments surfaces a pywin32 ``"Parameter not optional."`` error at
    the SOLIDWORKS boundary.  The vertex point ``(Xp, Yp, Zp)`` is placed on
    positive X axis at ``radius`` from centre, turned by ``angle`` degrees,
    which fixes the polygon's rotation reproducibly.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Polygon centre X in **millimetres**.
        center_y: Polygon centre Y in **millimetres**.
        radius: Circumradius in **millimetres** (distance from centre to each
            vertex). Corresponds to ``CreatePolygon(..., Inscribed=True)``,
            i.e. the polygon is inscribed in a circle of this radius.
        sides: Number of polygon sides.  SolidWorks accepts 3–40.
        angle: Degrees the vertex point is turned from +X (0 by default).

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        (e.g. ``"Polygon_3"``).  The ID is stored in
        ``adapter._sketch_entities`` so it can be passed back to
        ``sketch_linear_pattern`` / ``sketch_circular_pattern`` /
        ``sketch_mirror`` / ``sketch_offset``.  On failure, ``status`` is
        ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreatePolygon`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_polygon(
            adapter, center_x=0, center_y=0, radius=15.0, sides=6
        )
        print(result.data)  # "Polygon_3"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _polygon_operation() -> str:
        """Inner COM closure that calls CreatePolygon.

        Returns:
            str: Registered entity ID for the polygon (e.g. ``"Polygon_3"``).

        Raises:
            Exception: If ``CreatePolygon`` returns ``None``.
        """
        polygon = adapter.currentSketchManager.CreatePolygon(
            center_x / 1000.0,
            center_y / 1000.0,
            0,
            (center_x + radius * math.cos(math.radians(angle))) / 1000.0,
            (center_y + radius * math.sin(math.radians(angle))) / 1000.0,
            0,
            sides,
            True,
        )
        if not polygon:
            raise Exception("Failed to create polygon")
        # Register so the returned ID is usable by sketch_linear_pattern,
        # sketch_circular_pattern, sketch_mirror, and sketch_offset — without
        # this the polygon string is opaque and every downstream op fails
        # with "Unknown sketch entity 'Polygon_*'".
        entity_id = cast(str, adapter._register_sketch_entity("Polygon", polygon))
        # Polygons register as a SAFEARRAY tuple of segments — there's no
        # single dispatch ``GetCenterPoint`` to recover the center from later.
        # Stash the known center so ``sketch_circular_pattern`` can derive the
        # seed-to-axis offset for polygon seeds.
        adapter._sketch_entity_centers[entity_id] = (center_x, center_y)
        return entity_id

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
    angle: float = 0.0,
) -> AdapterResult[str]:
    """Add an ellipse to the active sketch, its major axis turned by ``angle``.

    Calls ``SketchManager.CreateEllipse`` with the major-axis endpoint
    ``angle`` degrees anticlockwise from the sketch's +X and the minor-axis
    endpoint a quarter turn further.

    The created ellipse is registered in the adapter's sketch-entity
    registry so subsequent constraint and dimension calls can reference it
    by ID, matching the behaviour of ``add_line`` / ``add_circle`` /
    ``add_arc`` and the mock adapter.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        center_x: Ellipse centre X in **millimetres**.
        center_y: Ellipse centre Y in **millimetres**.
        major_axis: Full major-axis length in **millimetres** (half is used
            as the offset from centre).
        minor_axis: Full minor-axis length in **millimetres** (half is used
            as the offset from centre).
        angle: The major axis's turn from +X, in degrees.

    Returns:
        AdapterResult[str]: On success, ``data`` is the registered entity ID
        (e.g. ``"Ellipse_4"``).  On failure, ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``CreateEllipse`` returns ``None``.

    Example::

        result = pywin32_sketch_ops.add_ellipse(
            adapter, center_x=0, center_y=0, major_axis=30.0, minor_axis=15.0
        )
        print(result.data)  # "Ellipse_4"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _ellipse_operation() -> str:
        """Inner COM closure that calls CreateEllipse and registers the entity.

        Returns:
            str: Registered entity ID for the new ellipse.

        Raises:
            Exception: If ``CreateEllipse`` returns ``None``.
        """
        turn = math.radians(angle)
        cos, sin = math.cos(turn), math.sin(turn)
        major, minor = major_axis / 2, minor_axis / 2
        ellipse = adapter.currentSketchManager.CreateEllipse(
            center_x / 1000.0,
            center_y / 1000.0,
            0,
            (center_x + major * cos) / 1000.0,
            (center_y + major * sin) / 1000.0,
            0,
            (center_x - minor * sin) / 1000.0,
            (center_y + minor * cos) / 1000.0,
            0,
        )
        if not ellipse:
            raise Exception("Failed to create ellipse")
        return cast(str, adapter._register_sketch_entity("Ellipse", ellipse))

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_ellipse", _ellipse_operation),
    )


#: ``InsertSketchText``'s width factor and spacing between letters, in per
#: cent; a spacing of 0 stacked every letter on the first (SolidWorks 2026).
_TEXT_NORMAL = 100


def _text_middle(sketch_text: Any) -> list[float]:
    """The middle of a sketch text's extent, model metres, from its edges.

    ``ISketchText.GetEdges2`` gives the letters' outline edges; their start
    and end points bound the text closely enough to centre it.

    Raises:
        Exception: If the text has no edges to measure.
    """
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for edge in as_list(sketch_text.GetEdges2()):
        params = _sw_type_info.flagged(
            _sw_type_info.flagged(edge, "IEdge").GetCurveParams3(), "ICurveParamData"
        )
        for point in (params.StartPoint, params.EndPoint):
            xs.append(float(point[0]))
            ys.append(float(point[1]))
            zs.append(float(point[2]))
    if not xs:
        raise Exception("The sketch text has no edges to centre it by")
    return [(min(v) + max(v)) / 2 for v in (xs, ys, zs)]


def _to_sketch_space(adapter: Any, point_m: list[float]) -> list[float]:
    """A model point (metres) in the open sketch's coordinates (metres)."""
    app = _sw_type_info.flagged(adapter.swApp, "ISldWorks")
    math_utility = _sw_type_info.flagged(app.GetMathUtility(), "IMathUtility")
    point = _sw_type_info.flagged(
        math_utility.CreatePoint(double_array(point_m)), "IMathPoint"
    )
    sketch = _sw_type_info.flagged(adapter.currentSketch, "ISketch")
    moved = _sw_type_info.flagged(
        point.MultiplyTransform(sketch.ModelToSketchTransform), "IMathPoint"
    )
    return [float(v) for v in as_list(moved.ArrayData)[:3]]


def _centre_text(adapter: Any, sketch_text: Any, point_mm: list[float]) -> None:
    """Move ``sketch_text`` so its middle is at model point ``point_mm``.

    ``InsertSketchText``'s centre alignment didn't centre the text (on SW
    2026 it dropped the selected line and started the text at the sketch's
    origin), so the text is measured and moved: its middle, mapped into the
    sketch, and ``SetCoordinates`` shifted by the difference to the point,
    mapped into the sketch the same way (projected onto its plane).
    """
    middle = _to_sketch_space(adapter, _text_middle(sketch_text))
    target = _to_sketch_space(adapter, [c / 1000.0 for c in point_mm])
    at = [float(v) for v in as_list(sketch_text.GetCoordinates())]
    sketch_text.SetCoordinates(
        at[0] + target[0] - middle[0], at[1] + target[1] - middle[1], at[2]
    )


def _add_sketch_text_impl(
    adapter: Any,
    text: str,
    x: float,
    y: float,
    height: float,
    center_at: list[float] | None,
) -> AdapterResult[dict[str, Any]]:
    """Add text to the active sketch, from a point or centred on one.

    ``IModelDoc2.InsertSketchText`` puts the text at the point; the letter
    height is the text format's ``CharHeight``. ``center_at`` measures the
    text and moves it so its middle is at that model point. (A line
    selected first didn't lay the text along it on SolidWorks 2026, nor did
    centre alignment centre it, so neither is used.)

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        text: The text; ``$PRP:"name"`` shows a custom property.
        x: Start x in mm (sketch coordinates).
        y: Start y in mm (the baseline).
        height: Letter height in mm.
        center_at: A model point ``[x, y, z]`` in mm to put the text's middle
            at (projected onto the sketch).

    Returns:
        AdapterResult with ``id``, ``text`` (as SolidWorks shows it, links
        resolved) and ``height`` (mm, read back).
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _text_operation() -> dict[str, Any]:
        model = adapter.currentModel
        model.ClearSelection2(True)
        # Centred text starts at its target, so it never shows elsewhere
        # (at the sketch's origin) before it is moved into place.
        at_x, at_y = x / 1000.0, y / 1000.0
        if center_at is not None:
            at_x, at_y, _z = _to_sketch_space(adapter, [c / 1000.0 for c in center_at])
        inserted = model.InsertSketchText(
            at_x, at_y, 0.0, text, 0, 0, 0, _TEXT_NORMAL, _TEXT_NORMAL
        )
        model.ClearSelection2(True)
        if not inserted:
            raise Exception("SolidWorks added no sketch text")
        sketch_text = _sw_type_info.flagged(inserted, "ISketchText")
        text_format = sketch_text.GetTextFormat()
        text_format.CharHeight = height / 1000.0
        sketch_text.SetTextFormat(False, text_format)
        if center_at is not None:
            _centre_text(adapter, sketch_text, center_at)
        shown = adapter._attempt(lambda: str(sketch_text.Text), default=text)
        read_height = adapter._attempt(
            lambda: float(sketch_text.GetTextFormat().CharHeight) * 1000.0,
            default=height,
        )
        return {
            "id": adapter._register_sketch_entity("Text", inserted),
            "text": shown,
            "height": round(read_height, 4),
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("add_sketch_text", _text_operation),
    )


def _set_sketch_text_impl(
    adapter: Any, sketch_name: str, text: str
) -> AdapterResult[dict[str, Any]]:
    """Rewrite every sketch text in ``sketch_name``, with the sketch open.

    SolidWorks doesn't redraw sketch text when the model rebuilds, not even
    a ``$PRP:`` link whose dimension changed, and writing
    ``ISketchText.Text`` outside the sketch changes the string but not the
    geometry (SolidWorks 2026, 2026-11-18). Written while the sketch is
    open (``EditSketch``), a link is read again; the sketch is then closed
    and the model rebuilt.

    Args:
        adapter: A ``PyWin32Adapter`` with a part open.
        sketch_name: The sketch, e.g. ``Sketch12``.
        text: The new text; ``$PRP:"name"`` shows a custom property.

    Returns:
        AdapterResult with ``sketch``, ``before`` and ``after``: each text's
        string before and after (a ``$PRP:`` link is read when the string
        is asked for, so ``before`` can already show a new value the
        lettering doesn't).
    """

    def _operation() -> dict[str, Any]:
        model = adapter.currentModel
        if not model:
            raise Exception("No active model")
        feature = model.FeatureByName(sketch_name)
        if not feature:
            raise Exception(
                f"Sketch '{sketch_name}' not found; read the names with list_features."
            )
        feature = _sw_type_info.flagged(feature, "IFeature")
        sketch = _sw_type_info.flagged(feature.GetSpecificFeature2(), "ISketch")
        texts = [
            _sw_type_info.flagged(t, "ISketchText")
            for t in as_list(adapter._attempt(lambda: sketch.GetSketchTextSegments()))
        ]
        if not texts:
            raise Exception(f"Sketch '{sketch_name}' has no text to rewrite.")
        before = [str(t.Text) for t in texts]
        model.ClearSelection2(True)
        feature.Select2(False, 0)
        model.EditSketch()
        try:
            open_sketch = _sw_type_info.flagged(model.GetActiveSketch2(), "ISketch")
            texts = [
                _sw_type_info.flagged(t, "ISketchText")
                for t in as_list(open_sketch.GetSketchTextSegments())
            ]
            for sketch_text in texts:
                sketch_text.Text = text
            after = [str(t.Text) for t in texts]
        finally:
            _sw_type_info.flagged(model.SketchManager, "ISketchManager").InsertSketch(
                True
            )
        model.ForceRebuild3(False)
        return {"sketch": sketch_name, "before": before, "after": after}

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("set_sketch_text", _operation),
    )


def _add_sketch_constraint_impl(
    adapter: Any,
    entity1: str,
    entity2: str | None,
    relation_type: str,
    entity3: str | None = None,
) -> AdapterResult[str]:
    """Add a geometric relation (constraint) between sketch entities.

    Resolves ``entity1`` (and ``entity2``/``entity3`` if provided) against the
    adapter's sketch-entity registry, then calls
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

    ``"symmetric"`` is the only relation that takes a third entity
    (``entity3`` — the centerline of symmetry). All other relations reject
    a non-null ``entity3``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch and a valid
            ``currentModel``.
        entity1: Registered entity ID of the primary sketch entity (from a
            prior ``add_line`` / ``add_circle`` call).
        entity2: Registered entity ID of the secondary sketch entity, or
            ``None`` for single-entity relations (horizontal, vertical, fix).
        relation_type: Constraint type string (see above).
        entity3: Registered ID of a third entity. Only meaningful for
            ``"symmetric"`` — pass the centerline ID (from ``add_centerline``)
            as the line of symmetry. Must be ``None`` for every other
            relation type.

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

        rt_norm = (relation_type or "").strip().lower()
        relation_type_enum = RELATION_NAME_MAP.get(rt_norm)
        if relation_type_enum is None:
            supported = ", ".join(sorted(RELATION_NAME_MAP))
            raise Exception(
                f"Unsupported relation type '{relation_type}'. Supported: {supported}"
            )

        # Arity validation per relation type
        if rt_norm in _THREE_ENTITY_RELATIONS:
            if entity2 is None or entity3 is None:
                raise Exception(
                    f"Relation '{relation_type}' requires entity1, entity2, "
                    "and entity3 (the centerline of symmetry)"
                )
        elif entity3 is not None:
            raise Exception(
                f"Relation '{relation_type}' does not accept entity3 — only "
                "'symmetric' takes a third entity (the centerline)"
            )

        entity1_obj = adapter._sketch_entities.get(entity1)
        if entity1_obj is None:
            raise Exception(
                f"Unknown sketch entity '{entity1}'. Use IDs returned by add_line/add_arc/add_circle/add_spline/add_centerline."
            )

        entities = [entity1_obj]
        if entity2:
            entity2_obj = adapter._sketch_entities.get(entity2)
            if entity2_obj is None:
                raise Exception(
                    f"Unknown sketch entity '{entity2}'. Use IDs returned by add_line/add_arc/add_circle/add_spline/add_centerline."
                )
            entities.append(entity2_obj)
        if entity3:
            entity3_obj = adapter._sketch_entities.get(entity3)
            if entity3_obj is None:
                raise Exception(
                    f"Unknown sketch entity '{entity3}'. Use IDs returned by add_line/add_arc/add_circle/add_spline/add_centerline."
                )
            entities.append(entity3_obj)

        # Flag IModelDoc2 + ISketch + ISketchRelationManager so late-binding
        # resolves GetActiveSketch2, RelationManager, and AddRelation as
        # methods/properties correctly.
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
        adapter._attempt(
            lambda: _sw_type_info.flag_methods(active_sketch, "ISketch"),
            default=0,
        )

        relmgr = adapter._attempt(lambda: active_sketch.RelationManager, default=None)
        if relmgr is None:
            raise Exception("Active sketch has no RelationManager")
        adapter._attempt(
            lambda: _sw_type_info.flag_methods(relmgr, "ISketchRelationManager"),
            default=0,
        )

        # pywin32 won't auto-marshal a Python list of CDispatch entities to a
        # SAFEARRAY — the VT_ARRAY|VT_DISPATCH variant is the shape SolidWorks
        # accepts. Mirror the lazy-import dance used for sw_type_info above so
        # non-Windows CI (where pywin32 isn't installed) still exercises this
        # call path; fake adapters used in unit tests accept any sequence.
        try:
            import pythoncom as _pythoncom
            from win32com.client import VARIANT as _VARIANT
        except ImportError:
            _pythoncom = None
            _VARIANT = None

        ents_variant: Any
        if _pythoncom is not None and _VARIANT is not None:
            ents_variant = _VARIANT(
                _pythoncom.VT_ARRAY | _pythoncom.VT_DISPATCH, entities
            )
        elif sys.platform == "win32":
            # On Windows the real adapter feeds entities to a live COM method
            # that requires the SAFEARRAY shape — fail clearly rather than let
            # AddRelation surface a low-level "server threw an exception" COM
            # error from an unwrappable list argument.
            raise Exception("pywin32 is required for add_sketch_constraint on Windows")
        else:
            # Non-Windows: this branch is exercised only by mocked unit tests
            # whose fake AddRelation accepts any sequence.
            ents_variant = entities
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

        # Re-assert per-call: SolidWorks resets swInputDimValOnCreate (10)
        # when entering a new sketch, so the global connect-time suppression
        # is not sufficient. Setting it to False here prevents the Modify
        # dialog from blocking unattended automation.
        _sw = getattr(adapter, "swApp", None)
        if _sw:
            adapter._attempt(lambda: _sw.SetUserPreferenceToggle(10, False))
            adapter._attempt(lambda: _sw.SetUserPreferenceToggle(372, False))
            adapter._attempt(lambda: _sw.SetUserPreferenceToggle(520, False))

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
                f"Unknown sketch entity '{entity1}'. Use IDs returned by add_line/add_arc/add_circle/add_spline/add_centerline."
            )

        if isinstance(entity1_obj, (tuple, list)) and (
            (dimension_type or "").strip().lower() in {"radial", "diameter"}
        ):
            entity1_obj = _polygon_circle(entity1_obj, entity1)

        entity2_obj = None
        if entity2:
            entity2_obj = adapter._sketch_entities.get(entity2)
            if entity2_obj is None:
                raise Exception(
                    f"Unknown sketch entity '{entity2}'. Use IDs returned by add_line/add_arc/add_circle/add_spline/add_centerline."
                )

        dim_type = (dimension_type or "linear").strip().lower()
        if dim_type in ELLIPSE_AXES:
            display_ellipse = _ellipse_axis_dimension(
                adapter, entity1_obj, entity1, dim_type
            )
            _set_dimension_value(adapter, display_ellipse, value / 2 / 1000.0)
            return adapter._register_sketch_entity("Dimension", display_ellipse)  # type: ignore[no-any-return]
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
        elif dim_type == "linear" and entity2_obj is not None:
            adapter.currentModel.ClearSelection2(True)
            if not adapter._select_sketch_entity(entity1_obj, append=False):
                raise Exception(f"Failed to select primary entity '{entity1}'")
            if not adapter._select_sketch_entity(entity2_obj, append=True):
                raise Exception(f"Failed to select secondary entity '{entity2}'")
            display_dim = _two_entity_linear_dimension(
                adapter, (entity1, entity2 or ""), entity1_obj, entity2_obj, direction
            )
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
        _set_dimension_value(adapter, display_dim, value_si)
        return adapter._register_sketch_entity("Dimension", display_dim)  # type: ignore[no-any-return]

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("add_sketch_dimension", _dimension_operation),
    )


def _set_dimension_value(adapter: Any, display_dim: Any, value_si: float) -> None:
    """Set a new dimension's value (metres or radians) in this configuration.

    ``SetSystemValue3``, then ``SetSystemValue2``, then the ``SystemValue``
    property, whichever this SolidWorks accepts.
    """
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
            adapter._attempt(lambda: dim_obj.SetSystemValue2(value_si, 1), default=None)
            is None
        ):
            if hasattr(dim_obj, "SystemValue"):
                dim_obj.SystemValue = value_si


#: ``swSketchSegments_e.swSketchARC``: a circle or arc segment.
_SKETCH_ARC = 1

#: How far beside an ellipse's axis its dimension text goes, in metres.
_AXIS_TEXT_OFFSET = 0.005

#: An ellipse's axis dimensions, and the ``ISketchEllipse`` getter for the
#: point at that axis's end.
ELLIPSE_AXES = {"major_axis": "GetMajorPoint2", "minor_axis": "GetMinorPoint2"}


def _ellipse_axis_dimension(
    adapter: Any, ellipse: Any, entity_id: str, axis: str
) -> Any:
    """An aligned dimension from an ellipse's centre to the end of ``axis``.

    It holds half the axis: an ellipse has a point at one end of each axis
    only. ``AddDimension2`` with the text beside the axis's middle makes it
    aligned, so a turned ellipse gets its true half-axis (SolidWorks 2026,
    2026-11-18: 6.5 mm on an ellipse turned 30°, where a horizontal one
    would read 5.63; ``AddSpecificDimension`` added nothing). A dimension
    that doesn't read the axis's length (horizontal or vertical after all)
    is refused rather than set, which would bend the ellipse.

    Args:
        adapter: The adapter, with the ellipse's sketch open.
        ellipse: The ellipse, as ``CreateEllipse`` returned it.
        entity_id: Its registered id, for messages.
        axis: ``major_axis`` or ``minor_axis``.

    Returns:
        The display dimension.

    Raises:
        Exception: If the entity isn't an ellipse, a point can't be selected,
            or SolidWorks adds no dimension or one that isn't aligned.
    """
    flagged = _sw_type_info.flagged(ellipse, "ISketchEllipse")
    centre = adapter._attempt(lambda: flagged.GetCenterPoint2(), default=None)
    end = adapter._attempt(lambda: getattr(flagged, ELLIPSE_AXES[axis])(), default=None)
    if centre is None or end is None:
        raise Exception(
            f"'{entity_id}' is not an ellipse; {axis} dimensions an ellipse from add_ellipse."
        )
    model = adapter.currentModel
    model.ClearSelection2(True)
    for point, append in ((centre, False), (end, True)):
        if not adapter._attempt(lambda p=point, a=append: bool(p.Select2(a, 0)), False):
            raise Exception(f"Failed to select the {axis} points of '{entity_id}'")
    dx, dy = end.X - centre.X, end.Y - centre.Y
    length = math.hypot(dx, dy)
    side = (-dy / length, dx / length) if length else (0.0, 1.0)
    display = adapter._attempt(
        lambda: model.AddDimension2(
            centre.X + dx / 2 + side[0] * _AXIS_TEXT_OFFSET,
            centre.Y + dy / 2 + side[1] * _AXIS_TEXT_OFFSET,
            0.0,
        ),
        default=None,
    )
    if not display:
        raise Exception(f"SolidWorks added no {axis} dimension to '{entity_id}'")
    measured = adapter._attempt(
        lambda: display.GetDimension2(0).SystemValue, default=None
    )
    if measured is None or abs(float(measured) - length) > 1e-6:
        raise Exception(
            f"The {axis} dimension of '{entity_id}' reads {measured}, not the "
            f"axis's {length:.6f} m: it isn't aligned with the axis."
        )
    return display


def _polygon_circle(segments: Any, entity_id: str) -> Any:
    """A polygon's construction circle, which sizes it across its flats.

    ``CreatePolygon`` returns the polygon's sides and the circle drawn
    inside them; a diameter dimension on that circle drives the polygon.

    Raises:
        Exception: If no segment is a circle.
    """
    for segment in segments:
        flagged = _sw_type_info.flagged(segment, "ISketchSegment")
        if flagged.GetType() == _SKETCH_ARC:
            return segment
    raise Exception(f"Polygon '{entity_id}' has no construction circle to dimension.")


def _sketch_point_xyz(
    adapter: Any, entity_id: str, entity: Any
) -> tuple[float, float, float] | None:
    """A sketch entity's reference point in metres: a circle's centre, a line's midpoint.

    Lines and circles record that point (in mm) when they are created, so it
    is read from ``_sketch_entity_centers`` without a COM call. Reading it
    back from SolidWorks returned nothing on SW 2026; that read stays only as
    the fallback for entities that record no point.

    Args:
        adapter: A ``PyWin32Adapter``.
        entity_id: The entity's registered ID.
        entity: The registered ``ISketchArc`` or ``ISketchLine`` dispatch.

    Returns:
        tuple[float, float, float] | None: The point, or ``None`` when it
        cannot be read.
    """
    cached = adapter._sketch_entity_centers.get(entity_id)
    if cached is not None:
        return (cached[0] / 1000.0, cached[1] / 1000.0, 0.0)
    adapter._attempt(
        lambda: _sw_type_info.flag_methods(entity, "ISketchArc"), default=0
    )
    centre = adapter._attempt(lambda: entity.GetCenterPoint(), default=None)
    if isinstance(centre, (list, tuple)) and len(centre) >= 3:
        return (float(centre[0]), float(centre[1]), float(centre[2]))
    ends = adapter._attempt(
        lambda: adapter._sketch_geometry.read_segment_endpoints(entity), default=None
    )
    if ends is None:
        return None
    (x1, y1, z1), (x2, y2, z2) = ends
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0, (z1 + z2) / 2.0)


#: How far past a line's end a dimension to it is placed, in metres.
_DIMENSION_CLEARANCE_M = 0.008


def _text_beside_line(
    adapter: Any, line: Any, point: tuple[float, float, float]
) -> tuple[float, float, float] | None:
    """Where to put a line-to-point dimension so it sits outside the outline.

    Midway between the line and the point along the measurement, then moved
    along the line past its end nearest the point, so the dimensions to the
    holes of a plate stand clear of the plate instead of piling up inside it.

    Args:
        adapter: A ``PyWin32Adapter``.
        line: The ``ISketchLine`` dispatch.
        point: The other entity's point, in metres.

    Returns:
        tuple[float, float, float] | None: The text position, or ``None``
        when the line's ends cannot be read.
    """
    ends = adapter._attempt(
        lambda: adapter._sketch_geometry.read_segment_endpoints(line), default=None
    )
    if ends is None:
        return None
    (ax, ay, _az), (bx, by, _bz) = ends
    length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    if length <= 1e-9:
        return None
    ux, uy = (bx - ax) / length, (by - ay) / length
    along = (point[0] - ax) * ux + (point[1] - ay) * uy
    foot = (ax + along * ux, ay + along * uy)
    mid = ((foot[0] + point[0]) / 2.0, (foot[1] + point[1]) / 2.0)
    shift = (
        -along - _DIMENSION_CLEARANCE_M
        if along < length / 2.0
        else length - along + _DIMENSION_CLEARANCE_M
    )
    return (mid[0] + shift * ux, mid[1] + shift * uy, point[2])


def _two_entity_linear_dimension(
    adapter: Any, ids: tuple[str, str], entity1: Any, entity2: Any, direction: int
) -> Any:
    """A linear dimension between two sketch entities, e.g. a line and a circle.

    The text goes beside a line, clear of the outline (see
    :func:`_text_beside_line`), or midway between the two entities when the
    first is not a line. ``Extension.AddDimension`` with the
    first entity's single-line placement returned nothing for a line and a
    circle on SW 2026, so the calls are tried in turn until one returns a
    display dimension: ``IModelDoc2::AddDimension2`` with both entities
    selected (what the macro recorder writes for a smart dimension), the same
    with the circle's centre point selected, then ``Extension.AddDimension``.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        ids: The two entities' registered IDs.
        entity1: The first entity, usually a line.
        entity2: The second entity, usually a circle.
        direction: ``swSmartDimensionDirection_e`` for the last attempt.

    Returns:
        Any: The display dimension, or ``None`` when every attempt failed
        (an attempt whose entities cannot be selected is skipped). The caller
        has already checked that both entities can be selected.

    Raises:
        Exception: When the entities' positions cannot be read.
    """
    model = adapter.currentModel
    points = [
        _sketch_point_xyz(adapter, i, e)
        for i, e in zip(ids, (entity1, entity2), strict=True)
    ]
    if points[0] is None or points[1] is None:
        raise Exception("Cannot read where the two entities are to place the dimension")
    text = _text_beside_line(adapter, entity1, points[1]) or tuple(
        (a + b) / 2.0 for a, b in zip(points[0], points[1], strict=True)
    )
    centre = adapter._attempt(
        lambda: adapter._get_attr_or_call(entity2, "GetCenterPoint2"), default=None
    )

    def _selected(second: Any) -> bool:
        adapter._attempt(lambda: model.ClearSelection2(True), default=None)
        return bool(
            adapter._select_sketch_entity(entity1, append=False)
            and adapter._select_sketch_entity(second, append=True)
        )

    attempts = [
        (entity2, lambda: model.AddDimension2(*text)),
        *([(centre, lambda: model.AddDimension2(*text))] if centre is not None else []),
        (entity2, lambda: model.Extension.AddDimension(*text, direction)),
    ]
    for second, create in attempts:
        if not _selected(second):
            continue
        display_dim = adapter._attempt(create, default=None)
        if display_dim:
            return display_dim
    return None


def _select_sketch_entities(adapter: Any, entity_ids: list[str], mark: int) -> None:
    """Select sketch entities from the registry under a specific mark.

    Resolves each ID against ``adapter._sketch_entities`` and calls
    ``ISketchSegment.Select4(Append=True, Data)`` on each — with ``Data``
    being a configured ``ISelectData`` carrying the requested ``mark`` so
    SolidWorks knows how to interpret the selection (e.g. mark=1 sketch
    segments + mark=2 centerline for ``SketchMirror``).

    The ``ISelectionMgr`` dispatch needs ``sw_type_info.flag_methods``
    flagging or pywin32 late binding cannot resolve ``CreateSelectData``
    and surfaces ``"Member not found."`` from the COM boundary.  This
    matches the lazy-import dance used by ``add_sketch_constraint``;
    when ``sw_type_info`` cannot be imported the flagging step is skipped
    but ``ISelectionMgr.CreateSelectData`` and ``ISketchSegment.Select4``
    are still invoked.  Callers must therefore not invoke this helper
    without a live ``ISelectionMgr`` on ``adapter.currentModel``.

    Args:
        adapter: A ``PyWin32Adapter``.  ``adapter.currentModel`` must be a
            live ``IModelDoc2`` dispatch.
        entity_ids: Registry IDs returned by ``add_line`` / ``add_arc`` /
            etc.  Must be non-empty; resolution failure raises.
        mark: ``ISelectData.Mark`` value applied to every selection.

    Raises:
        Exception: If an entity ID is not in the registry or a Select4
            call returns ``False``.
    """
    sel_mgr = adapter.currentModel.SelectionManager
    adapter._attempt(
        lambda: _sw_type_info.flag_methods(sel_mgr, "ISelectionMgr"),
        default=0,
    )
    select_data = sel_mgr.CreateSelectData()
    select_data.Mark = mark
    for ent_id in entity_ids:
        entity = adapter._sketch_entities.get(ent_id)
        if entity is None:
            raise Exception(
                f"Unknown sketch entity '{ent_id}'. Use IDs returned by "
                "add_line/add_arc/add_circle/add_spline/add_centerline."
            )
        # ``ISketchManager::CreatePolygon`` returns the polygon's edges as
        # a SAFEARRAY, which pywin32 unmarshals to a tuple of
        # ``ISketchSegment`` handles — there is no single COM object to
        # ``Select4`` on.  Treat any iterable (tuple/list) as a group of
        # segments and select each, so a polygon ID can flow into
        # sketch_linear_pattern / sketch_circular_pattern / sketch_mirror /
        # sketch_offset the same as any other entity.  Single-segment
        # entities (lines, arcs, splines, ellipses, centerlines) keep the
        # original Select4 path.
        if isinstance(entity, (list, tuple)):
            for segment in entity:
                adapter._attempt(
                    lambda s=segment: _sw_type_info.flag_methods(s, "ISketchSegment"),
                    default=0,
                )
                ok = segment.Select4(True, select_data)
                if not ok:
                    raise Exception(
                        f"Failed to select segment of sketch entity '{ent_id}'"
                    )
        else:
            adapter._attempt(
                lambda e=entity: _sw_type_info.flag_methods(e, "ISketchSegment"),
                default=0,
            )
            ok = entity.Select4(True, select_data)
            if not ok:
                raise Exception(f"Failed to select sketch entity '{ent_id}'")


def _sketch_linear_pattern_impl(
    adapter: Any,
    entities: list[str],
    direction_x: float,
    direction_y: float,
    spacing: float,
    count: int,
) -> AdapterResult[str]:
    """Create a linear sketch pattern from the registered seed entities.

    Selects ``entities`` then calls
    ``ISketchManager::CreateLinearSketchStepAndRepeat(NumX, NumY, SpacingX,
    SpacingY, AngleX, AngleY, DeleteInstances, XSpacingDim, YSpacingDim,
    AngleDim, CreateNumOfInstancesDimInXDir, CreateNumOfInstancesDimInYDir)``.
    The COM API expects spacing in metres and angles in radians; this
    function does both conversions internally.

    The ``(direction_x, direction_y)`` vector defines pattern direction 1
    (``AngleX``).  Direction 2 (``AngleY``) is set perpendicular so the SW
    UI shows a clean axis frame, but ``NumY`` stays at 1 so no second-axis
    instances are produced.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: Registered entity IDs to pattern.  Must be non-empty.
        direction_x: Pattern direction X component (unit-less, any non-zero
            vector is normalised internally via ``atan2``).
        direction_y: Pattern direction Y component.
        spacing: Distance between instances in **millimetres**.
        count: Total number of instances (including the seed).  Must be at
            least 2.

    Returns:
        AdapterResult[str]: On success, ``data`` is a synthesised
        ``"LinearPattern_<count>x<spacing>_<rand>"`` ID — the COM method
        only returns a boolean, so no usable SW handle exists.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            inputs are invalid, an entity isn't registered, or
            ``CreateLinearSketchStepAndRepeat`` returns ``False``.

    Example::

        # 5 copies of Line_1 along +X, 15 mm apart
        result = pywin32_sketch_ops.sketch_linear_pattern(
            adapter, ["Line_1"], direction_x=1.0, direction_y=0.0,
            spacing=15.0, count=5
        )
        print(result.data)  # "LinearPattern_5x15.0_8765"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _linear_pattern_operation() -> str:
        if not entities:
            raise Exception("sketch_linear_pattern requires at least one entity")
        if count < 2:
            raise Exception("sketch_linear_pattern requires count >= 2")
        if spacing <= 0:
            raise Exception("sketch_linear_pattern requires spacing > 0")
        if math.hypot(direction_x, direction_y) < 1e-9:
            raise Exception(
                "sketch_linear_pattern requires a non-zero direction vector"
            )

        # Validate every entity ID exists in the registry before mutating
        # selection state, so an unknown ID doesn't leave SW with a
        # half-built selection.
        for ent_id in entities:
            if ent_id not in adapter._sketch_entities:
                raise Exception(
                    f"Unknown sketch entity '{ent_id}'. Use IDs returned by "
                    "add_line/add_arc/add_circle/add_spline/add_centerline."
                )

        # Clear any pre-existing selection so SW only sees the seed entities.
        adapter.currentModel.ClearSelection2(True)
        try:
            _select_sketch_entities(adapter, entities, mark=0)

            # Angles in [0, 2π): atan2 gives -π/2 for (0, -1), which
            # SolidWorks refuses (#272); the same direction as 3π/2 works.
            angle_x = math.atan2(direction_y, direction_x) % math.tau
            # Direction 2 (Y) goes 90° from direction 1; NumY=1 keeps it
            # single-row so the second-axis spacing/angle aren't actually
            # consumed, but SW still wants well-formed values.
            angle_y = (angle_x + math.pi / 2.0) % math.tau

            ok = adapter.currentSketchManager.CreateLinearSketchStepAndRepeat(
                count,  # NumX
                1,  # NumY
                spacing / 1000.0,  # SpacingX (metres)
                0.0,  # SpacingY
                angle_x,  # AngleX (radians)
                angle_y,  # AngleY (radians)
                "",  # DeleteInstances
                False,  # XSpacingDim
                False,  # YSpacingDim
                False,  # AngleDim
                False,  # CreateNumOfInstancesDimInXDir
                False,  # CreateNumOfInstancesDimInYDir
            )
            if not ok:
                raise Exception("Failed to create linear sketch pattern")
        finally:
            adapter.currentModel.ClearSelection2(True)

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
    angle: float,
    count: int,
) -> AdapterResult[str]:
    """Create a circular sketch pattern from the registered seed entities.

    Selects ``entities`` then calls
    ``ISketchManager::CreateCircularSketchStepAndRepeat(ArcRadius, ArcAngle,
    PatternNum, PatternSpacing, PatternRotate, DeleteInstances, RadiusDim,
    AngleDim, CreateNumOfInstancesDim)``.

    ``ArcRadius`` is the radius at which SW places the pattern instances
    — getting it wrong puts every copy on a tight cluster around the
    seed rather than the intended ring.  We derive it from the first
    registered entity's centre (via ``ISketchArc.GetCenterPoint`` once
    the dispatch is flagged) relative to the sketch origin.  The COM
    API has no pattern-centre parameter — the rotation axis is implied
    by ``(ArcRadius, ArcAngle)`` relative to the seed, so the rotation
    axis is always the **sketch origin**.  Callers who want a different
    pattern centre must position the seed relative to the desired
    centre (then translate the sketch as a whole, or use a sketch
    plane offset).

    ``PatternSpacing`` is the per-instance angle in radians.  For a
    full 360° pattern we use ``angle / count`` so the last instance
    lands one slot before the seed (tiles cleanly).  For partial sweeps
    (< 360°) we use ``angle / (count - 1)`` so the last instance lands
    at the full requested angle.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: Registered entity IDs to pattern.  Must be non-empty.
        angle: Total swept angle in **degrees** (e.g. ``360`` for a full
            ring or ``180`` for a half-circle).  Must be > 0.
        count: Total number of instances (including the seed).  Must be
            at least 2.

    Returns:
        AdapterResult[str]: On success, ``data`` is a synthesised
        ``"CircularPattern_<count>x<angle>deg_<rand>"`` ID — the COM
        method only returns a boolean.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            inputs are invalid, an entity isn't registered, or the COM
            call returns ``False``.

    Example::

        # 6 evenly-spaced copies of Circle_1 around the origin
        result = pywin32_sketch_ops.sketch_circular_pattern(
            adapter, ["Circle_1"], 360.0, 6
        )
        print(result.data)  # "CircularPattern_6x360.0deg_4321"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _circular_pattern_operation() -> str:
        if not entities:
            raise Exception("sketch_circular_pattern requires at least one entity")
        if count < 2:
            raise Exception("sketch_circular_pattern requires count >= 2")
        if angle <= 0:
            raise Exception("sketch_circular_pattern requires angle > 0")

        # Validate every entity ID exists before mutating selection state.
        for ent_id in entities:
            if ent_id not in adapter._sketch_entities:
                raise Exception(
                    f"Unknown sketch entity '{ent_id}'. Use IDs returned by "
                    "add_line/add_arc/add_circle/add_spline/add_centerline."
                )

        adapter.currentModel.ClearSelection2(True)
        try:
            _select_sketch_entities(adapter, entities, mark=0)

            # The COM API doesn't take pattern-centre coordinates directly.
            # Instead:
            #   ``ArcRadius`` = distance from the seed to the rotation axis.
            #   ``ArcAngle``  = angle (radians) **from the seed toward the
            #                   rotation axis**, NOT a starting angle. With
            #                   ArcAngle=0 SW puts the axis at +X relative
            #                   to the seed.
            # We recover both by reading the seed's centre via
            # ``ISketchArc.GetCenterPoint`` (after flagging the dispatch
            # with sw_type_info — pywin32 late binding otherwise resolves
            # the method as a tuple-valued property) and computing the
            # offset to the rotation-axis origin.  Caller-supplied
            # ``(center_x, center_y)`` is rejected above when non-zero, so
            # the rotation axis is always at the sketch origin here.
            #
            # Without this fix, ArcAngle=0 + ArcRadius=1 mm puts every
            # instance on a tiny ring beside the seed instead of the
            # intended pattern (caught by the #17 live screenshot). Falls
            # back to placing the axis at angle π from the seed if
            # GetCenterPoint isn't available; that still works when the
            # user positions the seed on the +X side of the origin.
            first_entity = adapter._sketch_entities.get(entities[0])

            seed_xy: tuple[float, float] | None = None

            # Group entities (polygons via ``CreatePolygon``, rectangles via
            # ``CreateCornerRectangle``) register as a SAFEARRAY of segments
            # — a tuple, not a single dispatch — so the ``GetCenterPoint``
            # path below would silently fall back to a 1 mm placeholder
            # radius. ``_add_polygon_impl`` / ``_add_rectangle_impl`` stash
            # the seed centre in ``_sketch_entity_centers`` at register time;
            # use that. Any future tuple-registering primitive that forgets
            # to populate the cache falls through to the clear-error branch
            # below.
            if isinstance(first_entity, (list, tuple)):
                seed_xy = adapter._sketch_entity_centers.get(entities[0])
                if seed_xy is None:
                    # Polygons and rectangles always reach the cached branch
                    # above, so naming them here would be misleading — the
                    # caller is hitting this with a group seed whose
                    # ``add_*`` writer never stashed a centre. List only the
                    # always-works primitive types.
                    raise Exception(
                        f"sketch_circular_pattern can't derive the seed centre "
                        f"for '{entities[0]}' — this entity type registers as "
                        f"a group (tuple of segments) with no cached centre. "
                        f"Use a circle, arc, or ellipse seed."
                    )

            if seed_xy is None and first_entity is not None:
                # GetCenterPoint lives on multiple sketch-entity interfaces
                # (ISketchArc for arcs/circles, ISketchEllipse for ellipses),
                # all with the same zero-arg signature. Flag every interface
                # we might encounter so the lookup works regardless of seed
                # type — without this, an ellipse seed silently resolves
                # GetCenterPoint as a property and the pattern is laid out
                # at a bogus 1 mm radius.
                adapter._attempt(
                    lambda: _sw_type_info.flag_methods(
                        first_entity,
                        "ISketchArc",
                        "ISketchEllipse",
                    ),
                    default=0,
                )
                point = adapter._attempt(lambda: first_entity.GetCenterPoint())
                if point is not None and hasattr(point, "__len__") and len(point) >= 2:
                    seed_xy = (float(point[0]) * 1000.0, float(point[1]) * 1000.0)

            # Single-dispatch seeds without ``GetCenterPoint`` (line, spline,
            # centerline) used to fall through here with ``seed_xy is None``
            # and silently produce a 1 mm placeholder pattern at the wrong
            # radius — same bug class as the polygon/rectangle tuple case,
            # but quieter because no exception fires. Surface a clear error
            # naming the offending seed instead.
            if seed_xy is None:
                raise Exception(
                    f"sketch_circular_pattern can't derive the seed centre "
                    f"for '{entities[0]}' — this seed type has no "
                    f"GetCenterPoint dispatch on ISketchArc/ISketchEllipse. "
                    f"Use a circle, arc, ellipse, or polygon seed."
                )

            # Rotation axis is always the sketch origin (0, 0) — SW's
            # ``CreateCircularSketchStepAndRepeat`` has no pattern-centre
            # parameter, so dx/dy from seed to axis is just ``-seed``.
            dx_mm = -seed_xy[0]
            dy_mm = -seed_xy[1]
            arc_radius_mm = math.hypot(dx_mm, dy_mm)
            arc_angle_rad = math.atan2(dy_mm, dx_mm) if arc_radius_mm > 0 else 0.0

            # ``CreateCircularSketchStepAndRepeat`` silently returns False on
            # negative ``ArcAngle`` values — the bundled VBA/C# examples all
            # pass positive radians (e.g. ``4.732863934409`` ≈ 271°).  Python's
            # ``atan2`` produces ``-π`` for a seed on the +X axis (because
            # ``-seed_xy[1]`` is ``-0.0``), which is geometrically equivalent
            # to ``+π`` but fails the COM call.  Normalise to ``[0, 2π)``.
            if arc_angle_rad < 0:
                arc_angle_rad += 2.0 * math.pi

            # 1 mm minimum keeps SW from silently rejecting the call when
            # the seed sits right on the pattern centre.
            arc_radius_m = max(arc_radius_mm / 1000.0, 0.001)
            # For a full 360° pattern, ``angle / count`` keeps adjacent
            # instances evenly spaced (instance ``count`` would coincide
            # with the seed). For partial sweeps the last instance should
            # land at the full requested angle, so divide by ``count - 1``
            # instead — otherwise ``angle=180, count=3`` would reach only
            # 120°.
            angle_rad = math.radians(angle)
            if abs(angle - 360.0) < 1e-9:
                pattern_spacing = angle_rad / count
            else:
                pattern_spacing = angle_rad / (count - 1)

            ok = adapter.currentSketchManager.CreateCircularSketchStepAndRepeat(
                arc_radius_m,  # ArcRadius — seed-to-axis distance (metres)
                arc_angle_rad,  # ArcAngle — direction from seed to axis (radians)
                count,  # PatternNum
                pattern_spacing,  # PatternSpacing (radians)
                True,  # PatternRotate
                "",  # DeleteInstances
                False,  # RadiusDim
                False,  # AngleDim
                False,  # CreateNumOfInstancesDim
            )
            if not ok:
                raise Exception("Failed to create circular sketch pattern")
        finally:
            adapter.currentModel.ClearSelection2(True)

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
    """Mirror sketch entities about a registered centreline.

    Selects the ``entities`` under mark **1** and the ``mirror_line``
    centreline under mark **2** — those are the marks SOLIDWORKS expects
    per the ``IModelDoc2::SketchMirror`` documentation — then invokes the
    method with no arguments.  ``SketchMirror`` returns ``void``, so
    success is reported by the absence of a COM error and the resulting
    ID is a synthesised ``"Mirror_<mirror_line_id>_<rand>"`` string.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: Registered entity IDs to mirror.  Must be non-empty.
        mirror_line: Registered entity ID of the centreline.  Must be a
            value previously returned by ``add_centerline``.

    Returns:
        AdapterResult[str]: On success, ``data`` is a synthesised mirror
        ID.  On failure, ``status`` is ``ERROR`` with the COM error or a
        validation message describing the problem.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the
            inputs are invalid, an entity isn't in the registry, or the
            COM call raises.

    Example::

        result = pywin32_sketch_ops.sketch_mirror(
            adapter, ["Line_1", "Line_2"], "Centerline_1"
        )
        print(result.data)  # "Mirror_Centerline_1_3456"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _mirror_operation() -> str:
        if not entities:
            raise Exception("sketch_mirror requires at least one entity")
        if not mirror_line:
            raise Exception(
                "sketch_mirror requires a mirror_line entity ID (add_centerline)"
            )
        if mirror_line not in adapter._sketch_entities:
            raise Exception(
                f"Unknown mirror_line entity '{mirror_line}'. Use the ID "
                "returned by add_centerline."
            )
        # IModelDoc2::SketchMirror specifies that the mirror axis must be
        # a centreline; selecting any other segment under mark=2 silently
        # no-ops on SW. ``add_centerline`` returns IDs prefixed with
        # ``Centerline_``, so reject anything else up front.
        # TODO(#24-followup): replace the prefix-string parse with a
        # proper introspection of the entity's ``ConstructionGeometry``
        # property on the real adapter (still keep the prefix check on
        # the mock, where there's no real dispatch to inspect). The
        # prefix parse is brittle if either side renames its ID scheme;
        # the SW invariant we're really enforcing is "this segment has
        # construction-geometry flagged".
        if not mirror_line.startswith("Centerline_"):
            raise Exception(
                f"mirror_line must be a centerline (from add_centerline), "
                f"got '{mirror_line}'"
            )

        # Validate every source entity ID up front so an unknown ID does
        # not leave SW with a half-built selection state.
        for ent_id in entities:
            if ent_id not in adapter._sketch_entities:
                raise Exception(
                    f"Unknown sketch entity '{ent_id}'. Use IDs returned by "
                    "add_line/add_arc/add_circle/add_spline/add_centerline."
                )

        adapter.currentModel.ClearSelection2(True)
        try:
            # Mark 1 for the source segments per IModelDoc2::SketchMirror docs.
            _select_sketch_entities(adapter, entities, mark=1)
            # Mark 2 for the centreline.
            _select_sketch_entities(adapter, [mirror_line], mark=2)

            # IModelDoc2::SketchMirror is VT_VOID — no return value, so a
            # successful invocation is its own success signal.
            adapter.currentModel.SketchMirror()
        finally:
            adapter.currentModel.ClearSelection2(True)

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
    """Offset selected sketch entities by a fixed distance.

    Selects ``entities`` then calls
    ``ISketchManager::SketchOffset2(Offset, BothDirections, Chain, CapEnds,
    MakeConstruction, AddDimensions)``.

    ``Offset`` is in metres; a negative value flips the offset direction
    per the COM docs, so ``reverse_direction=True`` is implemented by
    negating the value rather than relying on ``BothDirections``.

    The remaining flags are pinned to predictable defaults so the call is
    deterministic for automation: no caps, no auto-conversion to
    construction geometry, no on-canvas dimension, and ``Chain=False`` so
    only the supplied entities are offset (rather than the entire
    contour they belong to).

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        entities: Registered entity IDs to offset.  Must be non-empty.
        offset_distance: Offset distance in **millimetres**.  Must be > 0
            — the direction is controlled by ``reverse_direction``, not
            the sign.
        reverse_direction: When ``True``, offset in the opposite of SW's
            default direction (effectively a negated ``Offset`` argument).

    Returns:
        AdapterResult[str]: On success, ``data`` is a synthesised
        ``"Offset_<distance>_<direction>_<rand>"`` ID.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            inputs are invalid, an entity isn't registered, or the COM
            call returns ``False``.

    Example::

        result = pywin32_sketch_ops.sketch_offset(
            adapter, ["Line_1"], 5.0, reverse_direction=False
        )
        print(result.data)  # "Offset_5.0_outward_9876"
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def _offset_operation() -> str:
        if not entities:
            raise Exception("sketch_offset requires at least one entity")
        if offset_distance <= 0:
            raise Exception(
                "sketch_offset requires offset_distance > 0 — use "
                "reverse_direction to flip the side"
            )

        # Validate every entity ID up front so an unknown ID does not
        # leave SW with a half-built selection.
        for ent_id in entities:
            if ent_id not in adapter._sketch_entities:
                raise Exception(
                    f"Unknown sketch entity '{ent_id}'. Use IDs returned by "
                    "add_line/add_arc/add_circle/add_spline/add_centerline."
                )

        adapter.currentModel.ClearSelection2(True)
        try:
            _select_sketch_entities(adapter, entities, mark=0)

            # Negative Offset flips the side per SketchOffset2 docs.
            offset_m = (
                -offset_distance / 1000.0
                if reverse_direction
                else offset_distance / 1000.0
            )

            adapter._attempt(
                lambda: _sw_type_info.flag_methods(
                    adapter.currentSketchManager, "ISketchManager"
                ),
                default=0,
            )
            ok = adapter.currentSketchManager.SketchOffset2(
                offset_m,  # Offset (metres)
                False,  # BothDirections
                False,  # Chain
                0,  # CapEnds (swSkOffsetCapEndType_e: 0 = no caps)
                0,  # MakeConstruction (swSkOffsetMakeConstructionType_e: 0 = none)
                False,  # AddDimensions
            )
            if not ok:
                raise Exception("Failed to offset sketch entities")
        finally:
            adapter.currentModel.ClearSelection2(True)

        direction = "inward" if reverse_direction else "outward"
        return f"Offset_{offset_distance}_{direction}_{int(time.time() * 1000) % 10000}"

    return cast(
        AdapterResult[str],
        adapter._handle_com_operation("sketch_offset", _offset_operation),
    )


def _exit_sketch_impl(adapter: Any) -> AdapterResult[None]:
    """Exit any sketch-edit mode the active model is in and reset adapter state.

    The previous implementation trusted ``adapter.currentSketchManager`` —
    a Python-side handle populated only by ``create_sketch`` on **this**
    adapter instance.  A fresh adapter pointing at a SolidWorks process
    that already has a sketch open (from a crashed prior run, an
    aborted automation, or a manual user edit) would report
    ``WARNING: "No active sketch to exit"`` while SW was still sitting
    in sketch-edit mode — and every subsequent ``create_sketch`` then
    failed with ``Failed to select plane: Front Plane`` because SW
    can't open a new sketch while one is already active.

    Now queries ``IModelDoc2.GetActiveSketch2`` to find out what SW
    actually has open, and toggles ``SketchManager.InsertSketch(True)``
    when either SW or the adapter thinks a sketch is in edit mode.
    Adapter-side state is always cleared on success.

    Args:
        adapter: A ``PyWin32Adapter`` with a non-``None`` ``currentModel``.

    Returns:
        AdapterResult[None]: On success, ``status`` is ``SUCCESS``.
        When neither SW nor the adapter has an active sketch,
        ``status`` is ``WARNING`` (already-exited is not a failure).
        When ``currentModel`` is ``None``, also returns ``WARNING`` so
        defensive cleanup callers don't see spurious errors.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the
            ``InsertSketch`` call itself raises.

    Example::

        pywin32_sketch_ops.add_line(adapter, 0, 0, 50, 0)
        pywin32_sketch_ops.exit_sketch(adapter)
        # adapter.currentSketch is now None and SW is out of sketch-edit mode
    """
    if adapter.currentModel is None:
        # No document means nothing can be in sketch-edit mode either.
        # Match the legacy "already exited" semantics so cleanup callers
        # that fire exit_sketch defensively don't see spurious errors.
        return AdapterResult(
            status=AdapterResultStatus.WARNING,
            error="No active sketch to exit",
        )

    def _exit_operation() -> str:
        # ``GetActiveSketch2`` is a real zero-arg method on IModelDoc2.
        # Without flagging, pywin32 late binding resolves it as a property
        # and SW returns ``Member not found`` — the same root cause as
        # the cross-thread bugs in runbook #5.
        adapter._attempt(
            lambda: _sw_type_info.flag_methods(adapter.currentModel, "IModelDoc2"),
            default=0,
        )

        sw_active = adapter._attempt(lambda: adapter.currentModel.GetActiveSketch2())
        adapter_active = adapter.currentSketchManager

        # Already out of sketch-edit mode — clean up adapter state so a
        # future create_sketch starts from a known-good baseline, then
        # warn.  Using ``data`` to signal "no_op" lets callers tell the
        # difference between "I exited a sketch" and "nothing was open".
        if sw_active is None and adapter_active is None:
            return "no_active_sketch"

        # Prefer the adapter's SketchManager handle when available (it was
        # captured at create_sketch time on the executor thread, so it's
        # apartment-safe); fall back to a fresh ``currentModel.SketchManager``
        # for the SW-only state case.
        sketch_manager = adapter_active or adapter.currentModel.SketchManager
        adapter._attempt(
            lambda: _sw_type_info.flag_methods(sketch_manager, "ISketchManager"),
            default=0,
        )
        # Hand the document back with SolidWorks' default (inference on) for
        # interactive sketching; create_sketch turned AddToDB on.
        adapter._attempt(lambda: setattr(sketch_manager, "AddToDB", False))
        sketch_manager.InsertSketch(True)
        adapter.currentSketch = None
        adapter.currentSketchManager = None
        adapter._reset_sketch_entity_registry()
        return "exited"

    result = cast(
        AdapterResult[str],
        adapter._handle_com_operation("exit_sketch", _exit_operation),
    )
    # Translate "no sketch was open" into a WARNING so callers that branch
    # on ``is_error`` still treat already-exited as benign.  ``data`` is
    # the operation tag; ``error`` carries the human message.
    if result.is_success and result.data == "no_active_sketch":
        return cast(
            AdapterResult[None],
            AdapterResult(
                status=AdapterResultStatus.WARNING,
                error="No active sketch to exit",
            ),
        )
    if result.is_success:
        return cast(
            AdapterResult[None],
            AdapterResult(status=AdapterResultStatus.SUCCESS, data=None),
        )
    return cast(AdapterResult[None], result)


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

    if "fully" in text_value and "under" not in text_value and "over" not in text_value:
        return True
    if "under" in text_value or "over" in text_value:
        return False

    return _to_bool(raw)


#: ``swConstrainedStatus_e`` -> (definition_state, is_fully_defined).
_CONSTRAINED_STATES: dict[int, tuple[str, bool | None]] = {
    1: ("unknown", None),
    2: ("under_defined", False),
    3: ("fully_defined", True),
    4: ("over_defined", False),
    5: ("no_solution", False),
    6: ("invalid_solution", False),
    7: ("autosolve_off", None),
}


def _constrained_status(adapter: Any, sketch_obj: Any) -> dict[str, Any] | None:
    """The sketch's state from ``ISketch.GetConstrainedStatus`` (#268).

    Returns:
        dict[str, Any] | None: ``is_fully_defined``, ``definition_state``,
        ``source`` and ``raw_status``; ``None`` when it can't be read.
    """
    if sketch_obj is None:
        return None
    _flag_members(adapter, sketch_obj, "GetConstrainedStatus")
    raw = adapter._attempt(lambda: sketch_obj.GetConstrainedStatus(), default=None)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw not in _CONSTRAINED_STATES:
        return None
    state, fully = _CONSTRAINED_STATES[raw]
    return {
        "is_fully_defined": fully,
        "definition_state": state,
        "source": "ISketch.GetConstrainedStatus",
        "raw_status": raw,
    }


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
            _flag_members(adapter, sketch_feature, "GetSpecificFeature2")
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
                _flag_members(adapter, sketch_feature, "GetSpecificFeature2")
                sketch_obj = adapter._attempt(
                    lambda: sketch_feature.GetSpecificFeature2(), default=None
                )
                resolved_name = adapter._last_sketch_name

        if sketch_obj is None and sketch_feature is None:
            raise Exception("No active sketch found")

        constrained = _constrained_status(adapter, sketch_obj)
        if constrained is not None:
            return {"sketch_name": resolved_name, **constrained}

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
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation(
            "check_sketch_fully_defined", _get_sketch_payload
        ),
    )


# --- Sketch essentials (queue item 32) ---------------------------------------
# Corners, slots, trim and extend, and construction geometry. Coordinates are
# sketch mm, as for every other sketch tool.

#: How close (mm) a corner given by the agent must be to a sketch point.
_CORNER_TOLERANCE_MM = 0.01
#: ``swConstrainedCornerAction_e.swConstrainedCornerKeepGeometry``: never ask.
#: ``swConstrainedCornerInteract`` (0) can open a dialog and stall the run.
_KEEP_CONSTRAINED_CORNERS = 1
#: ``swSketchChamferType_e``.
_CHAMFER_DISTANCE_ANGLE = 0
_CHAMFER_DISTANCE_DISTANCE = 1
_CHAMFER_DISTANCE_EQUAL = 2
#: ``swSketchSlotCreationType_e`` by our ``kind``.
_SLOT_CREATION = {"straight": 0, "arc": 2}
#: ``swSketchSlotLengthType_e.swSketchSlotLengthType_CenterCenter``.
_SLOT_CENTER_TO_CENTER = 0
#: ``CreateSketchSlot``'s ``CenterArcDirection``: counter-clockwise.
_SLOT_COUNTER_CLOCKWISE = 1
#: ``swSketchTrimChoice_e.swSketchTrimClosest``.
_TRIM_CLOSEST = 0


def _active_sketch(adapter: Any) -> Any:
    """The open sketch, flagged so its zero-argument methods are methods."""
    return _sw_type_info.flagged(adapter.currentSketchManager.ActiveSketch, "ISketch")


def _segment_count(adapter: Any) -> int:
    """How many segments the open sketch has."""
    sketch = _active_sketch(adapter)
    return len(as_list(adapter._attempt(lambda: sketch.GetSketchSegments(), None)))


def _to_model_space(adapter: Any, point_mm: list[float]) -> list[float]:
    """A point in the open sketch (mm) in model space (metres).

    The inverse of ``ModelToSketchTransform``: ``SketchTrim``,
    ``SketchExtend`` and ``SelectByID2`` take model coordinates.
    """
    app = _sw_type_info.flagged(adapter.swApp, "ISldWorks")
    math_utility = _sw_type_info.flagged(app.GetMathUtility(), "IMathUtility")
    point = _sw_type_info.flagged(
        math_utility.CreatePoint(
            double_array([point_mm[0] / 1000.0, point_mm[1] / 1000.0, 0.0])
        ),
        "IMathPoint",
    )
    sketch = _active_sketch(adapter)
    to_sketch = _sw_type_info.flagged(sketch.ModelToSketchTransform, "IMathTransform")
    moved = _sw_type_info.flagged(
        point.MultiplyTransform(to_sketch.Inverse()), "IMathPoint"
    )
    return [float(v) for v in as_list(moved.ArrayData)[:3]]


def _corner_points(adapter: Any, corners: list[list[float]]) -> list[Any]:
    """The open sketch's point at each corner, every one found before any change.

    Raises:
        Exception: Naming the first corner with no sketch point within
            ``_CORNER_TOLERANCE_MM``.
    """
    sketch = _active_sketch(adapter)
    points = as_list(adapter._attempt(lambda: sketch.GetSketchPoints2(), None))
    found = []
    for corner in corners:
        match = next(
            (
                point
                for point in points
                if abs(float(point.X) * 1000.0 - corner[0]) <= _CORNER_TOLERANCE_MM
                and abs(float(point.Y) * 1000.0 - corner[1]) <= _CORNER_TOLERANCE_MM
            ),
            None,
        )
        if match is None:
            raise Exception(
                f"No sketch point at corner [{corner[0]:g}, {corner[1]:g}] mm in "
                "the open sketch"
            )
        found.append(match)
    return found


def _select_data(adapter: Any, mark: int = 0) -> Any:
    """An ``ISelectData`` carrying ``mark``, for ``Select4``."""
    sel_mgr = adapter.currentModel.SelectionManager
    adapter._attempt(
        lambda: _sw_type_info.flag_methods(sel_mgr, "ISelectionMgr"), default=0
    )
    data = sel_mgr.CreateSelectData()
    data.Mark = mark
    return data


def _treat_corners(
    adapter: Any,
    operation: str,
    corners: list[list[float]],
    prefix: str,
    make: Any,
) -> AdapterResult[dict[str, Any]]:
    """Fillet or chamfer each corner on its own; one registered id per corner.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        operation: The operation name, for the error boundary and the pause.
        corners: ``[x, y]`` sketch mm, each where two entities meet.
        prefix: The id prefix, ``Fillet`` or ``Chamfer``.
        make: Called with the sketch manager once a corner is selected;
            returns the new segment, or nothing when SolidWorks refused.
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def run() -> dict[str, Any]:
        points = _corner_points(adapter, corners)
        manager = _sw_type_info.flagged(adapter.currentSketchManager, "ISketchManager")
        ids = []
        try:
            for corner, point in zip(corners, points, strict=True):
                adapter.currentModel.ClearSelection2(True)
                where = f"[{corner[0]:g}, {corner[1]:g}] mm"
                if not point.Select4(False, _select_data(adapter)):
                    raise Exception(f"Couldn't select the corner at {where}")
                segment = make(manager)
                if not segment:
                    # A point need not be a corner: a centre rectangle's
                    # centre point is a sketch point (seen live, 2026-11-19).
                    raise Exception(
                        f"SolidWorks refused the {prefix.lower()} at corner {where}: "
                        "it isn't where two entities meet"
                    )
                ids.append(adapter._register_sketch_entity(prefix, segment))
        finally:
            adapter.currentModel.ClearSelection2(True)
        return {"ids": ids, "corners": corners}

    return cast(
        AdapterResult[dict[str, Any]], adapter._handle_com_operation(operation, run)
    )


def _add_sketch_fillet_impl(
    adapter: Any, corners: list[list[float]], radius: float
) -> AdapterResult[dict[str, Any]]:
    """Round each corner to ``radius`` mm (``ISketchManager.CreateFillet``)."""
    return _treat_corners(
        adapter,
        "add_sketch_fillet",
        corners,
        "Fillet",
        lambda manager: manager.CreateFillet(
            radius / 1000.0, _KEEP_CONSTRAINED_CORNERS
        ),
    )


def _add_sketch_chamfer_impl(
    adapter: Any,
    corners: list[list[float]],
    distance: float,
    distance2: float | None = None,
    angle: float | None = None,
) -> AdapterResult[dict[str, Any]]:
    """Bevel each corner (``ISketchManager.CreateChamfer``).

    ``distance`` alone is equal distances; with ``distance2``, two
    distances; with ``angle`` (degrees), a distance and an angle.
    """
    if angle is not None:
        kind, second = _CHAMFER_DISTANCE_ANGLE, math.radians(angle)
    elif distance2 is not None:
        kind, second = _CHAMFER_DISTANCE_DISTANCE, distance2 / 1000.0
    else:
        kind, second = _CHAMFER_DISTANCE_EQUAL, distance / 1000.0
    return _treat_corners(
        adapter,
        "add_sketch_chamfer",
        corners,
        "Chamfer",
        lambda manager: manager.CreateChamfer(kind, distance / 1000.0, second),
    )


def _add_slot_impl(
    adapter: Any,
    kind: str,
    width: float,
    start: list[float],
    end: list[float],
    center: list[float] | None = None,
) -> AdapterResult[str]:
    """Draw a straight or arc slot (``ISketchManager.CreateSketchSlot``).

    A straight slot runs between its two arc centres, ``start`` and ``end``.
    An arc slot follows the arc about ``center`` from ``start`` to ``end``,
    counter-clockwise. Length is centre to centre; no dimensions are added.
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def run() -> str:
        if kind == "arc":
            if center is None:
                raise Exception("An arc slot needs its center")
            points = (center, start, end)
        else:
            points = (start, end, end)
        manager = _sw_type_info.flagged(adapter.currentSketchManager, "ISketchManager")
        coordinates = [c for p in points for c in (p[0] / 1000.0, p[1] / 1000.0, 0.0)]
        slot = manager.CreateSketchSlot(
            _SLOT_CREATION[kind],
            _SLOT_CENTER_TO_CENTER,
            width / 1000.0,
            *coordinates,
            _SLOT_COUNTER_CLOCKWISE,
            False,
        )
        if not slot:
            raise Exception("SolidWorks refused the slot")
        return cast(str, adapter._register_sketch_entity("Slot", slot))

    return cast(AdapterResult[str], adapter._handle_com_operation("add_slot", run))


def _segment_lengths(adapter: Any) -> float:
    """The total length (mm) of the open sketch's segments."""
    sketch = _active_sketch(adapter)
    segments = as_list(adapter._attempt(lambda: sketch.GetSketchSegments(), None))
    return sum(
        float(_sw_type_info.flagged(segment, "ISketchSegment").GetLength()) * 1000.0
        for segment in segments
    )


def _change_at_point(
    adapter: Any,
    operation: str,
    point: list[float],
    verb: str,
    change: Any,
    grows: bool,
) -> AdapterResult[dict[str, Any]]:
    """Select the sketch entity at ``point`` and trim or extend it there.

    Whether it worked is measured, not read from the call: ``SketchTrim``
    returned ``False`` live (2026-11-19) after trimming correctly, and a
    retry then trimmed the next entity too. A trim always shortens the
    sketch's total segment length and an extension always lengthens it.

    Args:
        adapter: A ``PyWin32Adapter`` with an open sketch.
        operation: The operation name.
        point: ``[x, y]`` sketch mm on the entity.
        verb: ``trim`` or ``extend``, for the messages.
        change: Called with the sketch manager and the model-space point
            (metres), with the entity selected.
        grows: ``True`` when the change adds length (extend).
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def run() -> dict[str, Any]:
        where = f"[{point[0]:g}, {point[1]:g}] mm"
        before = _segment_count(adapter)
        length_before = _segment_lengths(adapter)
        model_point = _to_model_space(adapter, point)
        manager = _sw_type_info.flagged(adapter.currentSketchManager, "ISketchManager")
        adapter.currentModel.ClearSelection2(True)
        try:
            picked = adapter.currentModel.Extension.SelectByID2(
                "", "SKETCHSEGMENT", *model_point, False, 0, _null_callout(), 0
            )
            if not picked:
                raise Exception(f"No sketch entity at {where} in the open sketch")
            change(manager, model_point)
        finally:
            adapter.currentModel.ClearSelection2(True)
        length_change = _segment_lengths(adapter) - length_before
        worked = length_change > 1e-6 if grows else length_change < -1e-6
        if not worked:
            raise Exception(f"SolidWorks refused to {verb} at {where}")
        return {
            "point": point,
            "segments_before": before,
            "segments_after": _segment_count(adapter),
            "length_change_mm": round(length_change, 4),
        }

    return cast(
        AdapterResult[dict[str, Any]], adapter._handle_com_operation(operation, run)
    )


def _sketch_trim_impl(
    adapter: Any, point: list[float]
) -> AdapterResult[dict[str, Any]]:
    """Remove the piece of an entity nearest ``point`` (``SketchTrim``, closest)."""
    return _change_at_point(
        adapter,
        "sketch_trim",
        point,
        "trim",
        lambda manager, at: manager.SketchTrim(_TRIM_CLOSEST, *at),
        grows=False,
    )


def _sketch_extend_impl(
    adapter: Any, point: list[float]
) -> AdapterResult[dict[str, Any]]:
    """Lengthen the entity at ``point`` from its nearer end (``SketchExtend``)."""
    return _change_at_point(
        adapter,
        "sketch_extend",
        point,
        "extend",
        lambda manager, at: manager.SketchExtend(*at),
        grows=True,
    )


def _set_construction_geometry_impl(
    adapter: Any, entities: list[str], construction: bool = True
) -> AdapterResult[dict[str, Any]]:
    """Make entities construction geometry, or normal again, and read it back.

    Sets ``ISketchSegment.ConstructionGeometry`` on every segment of every
    id (a rectangle's or polygon's id holds several). Setting a property is
    idempotent, unlike ``CreateConstructionGeometry``, which toggles.
    """
    if not adapter.currentSketchManager:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active sketch")

    def run() -> dict[str, Any]:
        for entity_id in entities:
            if entity_id not in adapter._sketch_entities:
                raise Exception(
                    f"Unknown sketch entity '{entity_id}'. Use the ids the "
                    "sketch tools returned."
                )
        states = {}
        for entity_id in entities:
            entity = adapter._sketch_entities[entity_id]
            segments = entity if isinstance(entity, (list, tuple)) else [entity]
            read = []
            for segment in segments:
                segment.ConstructionGeometry = construction
                read.append(bool(segment.ConstructionGeometry))
            states[entity_id] = all(read) if construction else any(read)
        wrong = [e for e, state in states.items() if state != construction]
        if wrong:
            kind = "construction" if construction else "normal"
            raise Exception(
                f"SolidWorks didn't change {', '.join(wrong)} to {kind} geometry"
            )
        return {"entities": states, "construction": construction}

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("set_construction_geometry", run),
    )
