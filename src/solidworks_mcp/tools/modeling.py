"""Modeling tools for SolidWorks MCP Server.

Provides tools for creating and manipulating SolidWorks models, including parts,
assemblies, drawings, and features like extrusions, revolves, etc.
"""

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..adapters.base import (
    AdapterResult,
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SolidWorksAdapter,
    SweepParameters,
)
from .input_compat import CompatInput
from .tool_boundary import (
    normalize_input,
    require_success,
    with_tool_boundary,
)

# Input schemas using Python 3.14 built-in types


def _result_value(data: Any, *keys: str, default: Any = None) -> Any:
    """Build internal result value.

    Args:
        data (Any): The data value.
        *keys (str): Additional positional arguments forwarded to the call.
        default (Any): Fallback value returned when the operation fails. Defaults to None.

    Returns:
        Any: The result produced by the operation.
    """
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    for key in keys:
        if hasattr(data, key):
            value = getattr(data, key)
            if value is not None:
                return value
    return default


async def _read_summary(adapter: Any) -> AdapterResult[dict[str, Any]] | None:
    """Read the geometry summary, or ``None`` if the adapter has no such read.

    Args:
        adapter: The active adapter.

    Returns:
        AdapterResult[dict[str, Any]] | None: The summary result.
    """
    reader = getattr(adapter, "get_model_geometry_summary", None)
    if reader is None:
        return None
    result: AdapterResult[dict[str, Any]] = await reader()
    return result


def _box_size(summary: dict[str, Any]) -> Any:
    """Return a summary's bounding-box size ``[x, y, z]``, or ``None``."""
    box = summary.get("bounding_box_mm")
    return box.get("size") if isinstance(box, dict) else None


def _attach_measured_change(
    reply: dict[str, Any],
    before: AdapterResult[dict[str, Any]] | None,
    after: AdapterResult[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Add the feature's measured volume and size change to its reply.

    Best-effort: when the "before" read failed (or the adapter has none) the
    reply is returned unchanged; anything else unmeasurable is ``None`` with a
    ``note``. A feature that succeeded without changing the volume gets a
    ``warning``, since that is how SolidWorks reports a silent no-op.

    Args:
        reply: The feature tool's success reply.
        before: Summary read before the feature.
        after: Summary read after the feature.

    Returns:
        dict[str, Any]: ``reply``, with ``measured_change`` when measurable.
    """
    if before is None or not before.is_success:
        return reply
    old = before.data or {}
    new = (after.data or {}) if after is not None and after.is_success else None
    volume_before = old.get("volume_mm3")
    volume_after = new.get("volume_mm3") if new is not None else None
    numbers = (int, float)
    delta = (
        round(volume_after - volume_before, 4)
        if isinstance(volume_before, numbers) and isinstance(volume_after, numbers)
        else None
    )
    change: dict[str, Any] = {
        "volume_before_mm3": volume_before,
        "volume_after_mm3": volume_after,
        "volume_delta_mm3": delta,
        "bounding_box_before_mm": _box_size(old),
        "bounding_box_after_mm": _box_size(new) if new is not None else None,
        "solid_body_count_before": old.get("solid_body_count"),
        "solid_body_count_after": (
            new.get("solid_body_count") if new is not None else None
        ),
    }
    if new is None:
        error = after.error if after is not None else None
        change["note"] = f"Could not read the model after the feature: {error}"
    elif delta is None:
        change["note"] = "Volume is not determinable with the active adapter"
    reply["measured_change"] = change
    if delta == 0:
        reply["warning"] = (
            "The feature reported success but changed no volume; SolidWorks "
            "may have accepted it without doing anything. Check the sketch, "
            "the direction and the depth."
        )
    return reply


class OpenModelInput(BaseModel):
    """Input schema for opening a SolidWorks model.

    Attributes:
        file_path (str): The file path value.
    """

    file_path: str = Field(
        description="Full path to the SolidWorks file (.sldprt, .sldasm, .slddrw)"
    )


class CreatePartInput(CompatInput):
    """Input schema for creating a new SolidWorks part.

    Attributes:
        material (str | None): The material value.
        name (str): The name value.
        template (str | None): The template value.
        units (str | None): The units value.
    """

    name: str = Field(
        description=(
            "A label for your own reference; SolidWorks names the new part "
            "itself (Part1, ...) and the file takes the name of the path "
            "you save it to with save_part"
        )
    )
    template: str | None = Field(
        default=None,
        description=(
            "Part template (.prtdot) path; omit to use the SolidWorks default"
        ),
    )
    units: str | None = Field(default=None, description="Document units")
    material: str | None = Field(default=None, description="Material name")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create part input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if not self.name.strip():
            raise ValueError("name is required")


class CreateExtrusionInput(CompatInput):
    """Input schema for creating an extrusion feature.

    Attributes:
        both_directions (bool): The both directions value.
        depth (float): The depth value.
        draft_angle (float): The draft angle value.
        end_condition (str): The end condition value.
        merge_result (bool): The merge result value.
        reverse (bool | None): The reverse value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str | None): The sketch to extrude; None for the last closed.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
        thin_side (str): The side a thin wall grows on.
    """

    sketch_name: str | None = Field(
        default=None,
        description=(
            'Sketch to use, by its name in the feature tree (e.g. "Sketch2"); omit to use the sketch `exit_sketch` closed last'
        ),
    )
    depth: float = Field(description="Extrusion depth in millimeters")
    reverse: bool | None = Field(default=None, description="Reverse direction alias")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(
        default=False, description="Reverse extrusion direction"
    )
    both_directions: bool = Field(
        default=False,
        description=(
            "Extrude symmetrically about the sketch plane (mid-plane): `depth` is "
            "the total thickness, half on each side"
        ),
    )
    thin_feature: bool = Field(
        default=False,
        description=(
            "Make a thin wall of `thin_thickness` from the sketch's outline; the "
            "sketch may be an open chain (a bent plate's centreline)"
        ),
    )
    thin_thickness: float | None = Field(
        default=None, description="Wall thickness in mm; required with thin_feature"
    )
    thin_side: Literal["one_side", "other_side", "mid_plane"] = Field(
        default="one_side",
        description=(
            "Which side of the sketch line the thin wall grows on: one_side, "
            "other_side, or mid_plane (half each side)"
        ),
    )
    end_condition: str = Field(default="Blind", description="End condition type")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create extrusion input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: A non-positive depth, or a thin wall without thickness.
        """
        if self.depth <= 0:
            raise ValueError("depth must be positive")
        if self.reverse is not None:
            self.reverse_direction = self.reverse
        if self.thin_feature and not (self.thin_thickness and self.thin_thickness > 0):
            raise ValueError("thin_feature needs a positive thin_thickness (mm)")


class CreateRevolveInput(CompatInput):
    """Input schema for creating a revolve feature.

    Attributes:
        angle (float): The angle value.
        axis_entity (str | None): A reference axis to revolve about.
        both_directions (bool): The both directions value.
        merge_result (bool): The merge result value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str | None): The sketch to revolve; None for the last closed.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
    """

    sketch_name: str | None = Field(
        default=None,
        description=(
            'Sketch to use, by its name in the feature tree (e.g. "Sketch2"); omit to use the sketch `exit_sketch` closed last'
        ),
    )
    axis_entity: str | None = Field(
        default=None,
        description=(
            "A reference axis to revolve about, by its name in the feature tree "
            '(e.g. "Axis1" from `create_axis`); omit to use the centreline '
            "drawn in the sketch"
        ),
    )
    angle: float = Field(description="Revolve angle in degrees")
    reverse_direction: bool = Field(
        default=False, description="Reverse revolve direction"
    )
    both_directions: bool = Field(
        default=False, description="Revolve in both directions"
    )
    thin_feature: bool = Field(default=False, description="Create as thin wall feature")
    thin_thickness: float | None = Field(
        default=None, description="Thickness for thin wall feature in mm"
    )
    merge_result: bool = Field(default=True, description="Merge with existing geometry")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the create revolve input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Angle must be positive.
        """
        if self.angle <= 0:
            raise ValueError("angle must be positive")


class CreateSweepInput(BaseModel):
    """Input schema for creating a sweep feature.

    Attributes:
        merge_result (bool): The merge result value.
        path (str): The path value.
        twist_along_path (bool): The twist along path value.
        twist_angle (float): The twist angle value.
    """

    path: str = Field(description="Name or ID of the sweep path")
    twist_along_path: bool = Field(default=False, description="Twist along path")
    twist_angle: float = Field(default=0.0, description="Twist angle in degrees")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")


class CreateLoftInput(BaseModel):
    """Input schema for creating a loft feature.

    Attributes:
        end_tangent (str | None): The end tangent value.
        guide_curves (list[str] | None): The guide curves value.
        merge_result (bool): The merge result value.
        profiles (list[str]): The profiles value.
        start_tangent (str | None): The start tangent value.
    """

    profiles: list[str] = Field(description="List of profile names or IDs")
    guide_curves: list[str] | None = Field(
        default=None, description="List of guide curve names or IDs"
    )
    start_tangent: str | None = Field(
        default=None, description="Start tangent condition"
    )
    end_tangent: str | None = Field(default=None, description="End tangent condition")
    merge_result: bool = Field(default=True, description="Merge with existing geometry")


class GetDimensionInput(CompatInput):
    """Input schema for getting a dimension value.

    Attributes:
        dimension_name (str | None): The dimension name value.
        name (str | None): The name value.
    """

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the get dimension input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class SetDimensionInput(CompatInput):
    """Input schema for setting a dimension value.

    Attributes:
        dimension_name (str | None): The dimension name value.
        name (str | None): The name value.
        units (str | None): The units value.
        value (float): The value value.
    """

    name: str | None = Field(
        default=None,
        description="Dimension name (e.g., 'D1@Sketch1', 'D1@Boss-Extrude1')",
    )
    dimension_name: str | None = Field(default=None, description="Dimension name alias")
    value: float = Field(description="New dimension value in millimeters")
    units: str | None = Field(default=None, description="Units alias")

    def model_post_init(self, __context: Any) -> None:
        """Provide model post init support for the set dimension input.

        Args:
            __context (Any): The context value.

        Returns:
            None: None.

        Raises:
            ValueError: Name is required.
        """
        if self.name is None:
            self.name = self.dimension_name
        if not self.name:
            raise ValueError("name is required")


class SetUnitsInput(CompatInput):
    """Input schema for setting the active document's unit system.

    Attributes:
        unit_system (str): Target linear unit - ``mm``, ``cm``, ``m``, ``in``
            or ``ft`` (aliases such as ``inch`` / ``millimeters`` accepted).
    """

    unit_system: str = Field(description="Linear unit system: mm, cm, m, in, or ft")

    def model_post_init(self, __context: Any) -> None:
        if not self.unit_system.strip():
            raise ValueError("unit_system is required")


class CloseModelInput(BaseModel):
    """Input schema for closing a model.

    Attributes:
        save (bool): The save value.
    """

    save: bool = Field(default=False, description="Save the model before closing")


class CreateCutExtrudeInput(CompatInput):
    """Input schema for creating a cut-extrude feature.

    Attributes:
        depth (float): Cut depth in millimeters.
        draft_angle (float): Draft angle in degrees.
        end_condition (str): End condition type.
        reverse_direction (bool): Reverse cut direction.
        both_directions (bool): With ``"ThroughAll"``, cut both ways.
        sketch_name (str | None): Sketch to cut from.
    """

    depth: float = Field(description="Cut depth in millimeters")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(
        default=False,
        description=(
            "Cut against the sketch normal instead of along it. Usually not "
            "needed: if the requested direction finds no material, the cut is "
            "retried the other way and the reply sets direction_flipped"
        ),
    )
    end_condition: str = Field(
        default="Blind",
        description=(
            "'Blind' (cut 'depth' mm), 'ThroughAll' (through the body, one "
            "way) or 'ThroughAllBoth' (through the body both ways, for a "
            "sketch inside the body)"
        ),
    )
    both_directions: bool = Field(
        default=False,
        description=(
            "With end_condition 'ThroughAll', cut through the body both ways "
            "(same as 'ThroughAllBoth')"
        ),
    )
    sketch_name: str | None = Field(
        default=None,
        description=(
            "Sketch to cut from, e.g. 'Sketch3'. If omitted, the sketch most "
            "recently created/exited in this session is used, but only if it "
            "still exists in the model — there is no other fallback. Pass "
            "this explicitly whenever more than one unconsumed sketch could "
            "exist, or after any operation that might have changed the "
            "active sketch."
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        if self.depth <= 0:
            raise ValueError("depth must be positive")


class AddFilletInput(CompatInput):
    """Input schema for adding a fillet feature.

    Attributes:
        edge_names (list[str]): Edge names to fillet.
        radius (float): Fillet radius in millimeters.
    """

    radius: float = Field(description="Fillet radius in millimeters")
    edge_names: list[str] = Field(
        default_factory=list,
        description=(
            "Edges (or faces) to fillet. Accepts a topology name (e.g. "
            "'Edge<1>'), a coordinate hint in metres ('x,y,z') to select the "
            "nearest edge, or 'face:x,y,z' to select a whole face — which "
            "fillets every edge bounding it in one call. Prefer 'face:' over "
            "a coordinate on an edge that sits exactly on a shared boundary "
            "between two faces (e.g. a hole rim flush with a flat face): the "
            "nearest-edge match there can silently resolve to a different, "
            "unrelated edge. Leave empty to use whatever is *currently "
            "selected* in the live SolidWorks UI (e.g. entities read back "
            "via get_selected_entities and left selected) without touching "
            "the selection — this is the most reliable option when the user "
            "has hand-picked specific edges, since it never round-trips "
            "through coordinates. Falls back to filleting all edges only if "
            "nothing at all is selected."
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        if self.radius <= 0:
            raise ValueError("radius must be positive")


class AddChamferInput(CompatInput):
    """Input schema for adding a chamfer feature.

    Attributes:
        distance (float): Chamfer distance in millimeters.
        edge_names (list[str]): Edge names to chamfer.
        angle (float): Chamfer angle in degrees.
        flip (bool): Measure the distance along the other face.
    """

    distance: float = Field(
        description="Chamfer distance in millimeters, along one of the edge's faces"
    )
    angle: float = Field(
        default=45.0,
        description=(
            "Chamfer angle in degrees, between 0 and 90; 45 makes both legs "
            "equal to distance"
        ),
    )
    flip: bool = Field(
        default=False,
        description=(
            "Measure distance along the edge's other face (swaps the long and "
            "short legs of an angled chamfer)"
        ),
    )
    edge_names: list[str] = Field(
        default_factory=list,
        description=(
            "Edges (or faces) to chamfer. Accepts a topology name (e.g. "
            "'Edge<1>'), a coordinate hint in metres ('x,y,z') to select the "
            "nearest edge, or 'face:x,y,z' to select a whole face — which "
            "chamfers every edge bounding it in one call. Prefer 'face:' over "
            "a coordinate on an edge that sits exactly on a shared boundary "
            "between two faces (e.g. a hole rim flush with a flat face): the "
            "nearest-edge match there can silently resolve to a different, "
            "unrelated edge. Leave empty to use whatever is *currently "
            "selected* in the live SolidWorks UI (e.g. entities read back "
            "via get_selected_entities and left selected) without touching "
            "the selection — this is the most reliable option when the user "
            "has hand-picked specific edges, since it never round-trips "
            "through coordinates. Falls back to chamfering all edges only if "
            "nothing at all is selected."
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        if self.distance <= 0:
            raise ValueError("distance must be positive")
        if not 0 < self.angle < 90:
            raise ValueError("angle must be between 0 and 90 degrees")


class CreateAssemblyInput(CompatInput):
    """Input schema for creating a new assembly.

    Attributes:
        name (str): The name value.
        template (str | None): The template value.
    """

    name: str = Field(
        description=(
            "A label for your own reference; SolidWorks names the new assembly "
            "itself (Assem1, ...) and the file takes the name of the path "
            "you save it to with save_assembly"
        )
    )
    template: str | None = Field(
        default=None,
        description=(
            "Assembly template (.asmdot) path; omit to use the SolidWorks default"
        ),
    )


class InsertComponentInput(CompatInput):
    """Input schema for inserting a component into an assembly.

    Attributes:
        file_path (str): Path to the part or sub-assembly.
        x (float): X position in millimetres.
        y (float): Y position in millimetres.
        z (float): Z position in millimetres.
    """

    file_path: str = Field(
        description="Absolute path to the .sldprt or .sldasm to insert"
    )
    x: float = Field(default=0.0, description="X position in millimetres")
    y: float = Field(default=0.0, description="Y position in millimetres")
    z: float = Field(default=0.0, description="Z position in millimetres")

    def model_post_init(self, __context: Any) -> None:
        if not self.file_path.strip():
            raise ValueError("file_path is required")


class DeleteFeatureInput(CompatInput):
    """Input schema for deleting a feature.

    Attributes:
        name (str): Feature or sketch name to delete.
    """

    name: str = Field(
        description="Feature or sketch name, e.g. 'Boss-Extrude1' or 'Sketch1'"
    )


class SuppressFeatureInput(CompatInput):
    """Input schema for suppressing or unsuppressing a feature.

    Attributes:
        name (str): Feature name to toggle.
        suppress (bool): True to suppress, False to unsuppress.
    """

    name: str = Field(description="Feature name, e.g. 'Fillet1'")
    suppress: bool = Field(
        default=True, description="True to suppress, False to unsuppress"
    )


class RenameFeatureInput(CompatInput):
    """Input schema for renaming a feature.

    Attributes:
        old_name (str): Current feature name.
        new_name (str): New feature name.
    """

    old_name: str = Field(description="Current feature name, e.g. 'Fillet1'")
    new_name: str = Field(description="New feature name, e.g. 'MountingEdgeFillet'")

    def model_post_init(self, __context: Any) -> None:
        if not self.old_name.strip():
            raise ValueError("old_name is required")
        if not self.new_name.strip():
            raise ValueError("new_name is required")


class SelectFeatureInput(CompatInput):
    """Input schema for selecting a named feature.

    Attributes:
        feature_name (str): Feature, sketch, plane or component name.
        append (bool): Add to the current selection instead of replacing it.
    """

    feature_name: str = Field(
        description="Feature, sketch, plane or component name, e.g. "
        "'Boss-Extrude1', 'Sketch1', 'Front Plane' (an '@Part1' suffix is ok)"
    )
    append: bool = Field(
        default=False,
        description="Add to the current selection instead of replacing it",
    )

    def model_post_init(self, __context: Any) -> None:
        self.feature_name = self.feature_name.strip()
        if not self.feature_name:
            raise ValueError("feature_name is required")


class SelectFaceEdgesInput(CompatInput):
    """Input schema for multi-selecting every edge of one face.

    Attributes:
        point (list[float] | None): A point on the face, [x, y, z] in mm.
        side (str | None): Which way the face points.
        plane (str | None): Reference plane the face lies on.
        edge_type (str): Edge filter: all, linear or circular.
        append (bool): Add to the current selection instead of replacing it.
    """

    point: list[float] | None = Field(
        default=None, description="A point on the face, [x, y, z] in mm"
    )
    side: str | None = Field(
        default=None,
        description="Outward direction of the face: +X/-X/+Y/-Y/+Z/-Z or "
        "right/left/top/bottom/front/back (top=+Y, front=+Z, right=+X, as in "
        "SolidWorks' default views); picks the furthest flat face that way",
    )
    plane: str | None = Field(
        default=None,
        description="Reference plane name, e.g. 'Front Plane'; picks the body "
        "face(s) lying on it",
    )
    edge_type: str = Field(
        default="all", description="'all', 'linear' or 'circular' (e.g. hole rims)"
    )
    append: bool = Field(
        default=False,
        description="Add to the current selection instead of replacing it",
    )

    def model_post_init(self, __context: Any) -> None:
        from ..adapters.solidworks.face_selection import validate_face_query

        self.edge_type = str(self.edge_type or "all").strip().lower()
        problem = validate_face_query(self.point, self.side, self.plane, self.edge_type)
        if problem:
            raise ValueError(problem)


class RebuildModelInput(CompatInput):
    """Input schema for forcing a model rebuild.

    Attributes:
        top_level_only (bool): Rebuild only the top level of an assembly.
    """

    top_level_only: bool = Field(
        default=False,
        description="Rebuild only the top level of an assembly (default: full "
        "rebuild including sub-assemblies)",
    )


class UndoInput(CompatInput):
    """Input schema for undoing model operations.

    Attributes:
        count (int): Number of operations to undo.
    """

    count: int = Field(default=1, ge=1, description="Number of operations to undo")


class AddMateInput(CompatInput):
    """Input schema for mating two assembly components.

    Attributes:
        component_a (str): First component instance name.
        component_b (str): Second component instance name.
        entity_a (str): Named feature on the first component.
        entity_b (str): Named feature on the second component.
        mate_type (str): Mate type.
        alignment (str): Mate alignment.
        distance (float): Distance in millimetres for a distance mate.
        angle (float): Angle in degrees for an angle mate.
    """

    component_a: str = Field(
        description="First component instance name, as reported by list_components"
    )
    component_b: str = Field(description="Second component instance name")
    entity_a: str | None = Field(
        default=None,
        description=(
            "Named reference plane or axis on the first component, e.g. 'Front "
            "Plane'; defaults to 'Front Plane' when face_a is not given either"
        ),
    )
    entity_b: str | None = Field(
        default=None,
        description=(
            "Named reference plane or axis on the second component; defaults "
            "to 'Front Plane' when face_b is not given either"
        ),
    )
    face_a: list[float] | None = Field(
        default=None,
        description=(
            "[x, y, z] in mm on a face of the first component, in that part's "
            "own coordinates (as it was modelled), instead of entity_a: e.g. a "
            "point on a pin's round face for a concentric mate"
        ),
    )
    face_b: list[float] | None = Field(
        default=None,
        description=(
            "[x, y, z] in mm on a face of the second component, in its own "
            "part coordinates, instead of entity_b"
        ),
    )
    mate_type: str = Field(
        default="coincident",
        description=(
            "coincident, concentric, perpendicular, parallel, tangent, "
            "distance or angle"
        ),
    )
    alignment: str = Field(
        default="aligned", description="aligned, anti_aligned or closest"
    )
    distance: float = Field(
        default=0.0, description="Distance in millimetres, for a distance mate"
    )
    angle: float = Field(default=0.0, description="Angle in degrees, for an angle mate")

    def model_post_init(self, __context: Any) -> None:
        if not self.component_a.strip() or not self.component_b.strip():
            raise ValueError("component_a and component_b are required")
        for side in ("a", "b"):
            entity, face = (
                getattr(self, f"entity_{side}"),
                getattr(self, f"face_{side}"),
            )
            if entity and face is not None:
                raise ValueError(f"give entity_{side} or face_{side}, not both")
            if face is not None and len(face) != 3:
                raise ValueError(f"face_{side} must be [x, y, z] in millimetres")


class SetComponentStateInput(CompatInput):
    """Input schema for fixing, floating and flexing a component.

    Attributes:
        component (str): Component instance name.
        fixed (bool | None): True fixes it, False floats it.
        flexible (bool | None): True flexible, False rigid.
    """

    component: str = Field(
        description="Component instance name, as reported by list_components"
    )
    fixed: bool | None = Field(
        default=None,
        description=(
            "true fixes the component in place; false floats it so mates can "
            "move it; leave it out to keep it as it is"
        ),
    )
    flexible: bool | None = Field(
        default=None,
        description=(
            "For a sub-assembly: true lets its own mates move inside this "
            "assembly (a crank that turns); false makes it rigid; leave it out "
            "to keep it as it is"
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.component.strip():
            raise ValueError("component is required")
        if self.fixed is None and self.flexible is None:
            raise ValueError("give fixed, flexible or both")


class CreateReferencePlaneInput(CompatInput):
    """Input schema for creating a reference plane.

    Attributes:
        reference (str): Name of the reference plane.
        face_point (list[float] | None): A point on a flat face to use instead.
        offset (float): Offset distance in millimetres.
        angle (float): Angle in degrees.
        axis (str | None): Axis to rotate about, for an angle.
        flip (bool): Reverse the offset or angle direction.
    """

    reference: str = Field(
        default="",
        description=(
            "Name of the reference plane, e.g. 'Front Plane' or 'Plane1'; leave "
            "it out when giving face_point"
        ),
    )
    face_point: list[float] | None = Field(
        default=None,
        description=(
            "[x, y, z] in mm on a flat face of the part (sloped or not), to use "
            "that face as the reference instead of a named plane"
        ),
    )
    offset: float = Field(
        default=0.0,
        description=(
            "Offset distance in millimetres. Non-zero for a named plane; 0 with "
            "face_point puts the plane on the face"
        ),
    )
    angle: float = Field(
        default=0.0,
        description="Angle in degrees between the new plane and the reference, about axis",
    )
    axis: str | None = Field(
        default=None,
        description=(
            "Name of the axis the plane rotates about, e.g. 'Axis1' from "
            "create_axis; required with angle"
        ),
    )
    flip: bool = Field(
        default=False, description="Reverse the offset side or the angle direction"
    )

    def model_post_init(self, __context: Any) -> None:
        if bool(self.reference.strip()) == (self.face_point is not None):
            raise ValueError("give exactly one of reference or face_point")
        if self.face_point is not None and len(self.face_point) != 3:
            raise ValueError("face_point must be [x, y, z] in millimetres")
        if self.angle and not self.axis:
            raise ValueError("an angled plane needs axis, the axis to rotate about")


class CreateAxisInput(CompatInput):
    """Input schema for creating a reference axis.

    Attributes:
        reference (str): Principal axis direction.
    """

    reference: str = Field(
        description="Principal axis direction: 'x', 'y' or 'z' "
        "(case-insensitive; a leading +/- is stripped)"
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.reference.strip():
            raise ValueError("reference is required")


class CreateReferencePointInput(CompatInput):
    """Input schema for creating a reference point.

    Attributes:
        mode (str): "along_curve" or "face_center".
        x (float): X of a point on the target edge/face, in millimetres.
        y (float): Y of a point on the target edge/face, in millimetres.
        z (float): Z of a point on the target edge/face, in millimetres.
        distance (float | None): For "along_curve", offset from the edge
            start in millimetres.
        percent (float | None): For "along_curve", position as 0-100 of the
            edge length.
    """

    mode: str = Field(
        description="'along_curve' (a point on an edge) or 'face_center' "
        "(the centroid of a face)"
    )
    x: float = Field(description="X of a point on the target edge/face, in mm")
    y: float = Field(description="Y of a point on the target edge/face, in mm")
    z: float = Field(description="Z of a point on the target edge/face, in mm")
    distance: float | None = Field(
        default=None,
        description="along_curve only: offset from the edge start in mm "
        "(give exactly one of distance or percent)",
    )
    percent: float | None = Field(
        default=None,
        description="along_curve only: position as 0-100 of the edge length",
    )

    def model_post_init(self, __context: Any) -> None:
        if str(self.mode or "").strip().lower() not in (
            "along_curve",
            "face_center",
        ):
            raise ValueError("mode must be 'along_curve' or 'face_center'")


class MirrorFeatureInput(CompatInput):
    """Input schema for mirroring solid bodies or features.

    Attributes:
        features (list[str]): Body or feature names to mirror.
        mirror_plane (str): Plane name to mirror about.
        merge (bool): Merge the mirrored result with the original.
        mirror_bodies (bool): Mirror whole bodies rather than features.
    """

    features: list[str] = Field(
        default_factory=list,
        description="Body or feature names to mirror. At least one required. "
        "For a body mirror these are the names as they appear under Solid "
        "Bodies, which for a lofted wing is the loft's own name",
    )
    mirror_plane: str = Field(
        description="Plane name to mirror about, e.g. 'Right Plane'"
    )
    merge: bool = Field(
        default=True,
        description="Merge the mirrored result with the original body",
    )
    mirror_bodies: bool = Field(
        default=True,
        description="Mirror whole solid bodies rather than individual "
        "features. Defaults to True, which is what works for anything "
        "built from a loft or sweep - a feature mirror only resolves when "
        "the feature's own sketch sits on the mirror plane",
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.features:
            raise ValueError("features must contain at least one name")
        if not self.mirror_plane.strip():
            raise ValueError("mirror_plane is required")


class PatternCircularInput(CompatInput):
    """Input schema for patterning features around an axis.

    Attributes:
        features (list[str]): Names of the features to pattern.
        axis (str): Name of the axis to rotate about.
        count (int): Total number of instances including the original.
        angle (float): Total angle in degrees to spread instances over.
        equal_spacing (bool): Space instances evenly across angle.
    """

    features: list[str] = Field(
        default_factory=list,
        description="Names of the features to pattern. At least one required.",
    )
    axis: str = Field(
        description="Name of the axis to rotate about, e.g. 'Axis1' as "
        "created by create_axis"
    )
    count: int = Field(
        description="Total number of instances including the original. "
        "Must be at least 2 - a pattern of one is just the original feature"
    )
    angle: float = Field(
        default=360.0,
        description="Total angle in degrees to spread the instances over. "
        "Defaults to a full 360",
    )
    equal_spacing: bool = Field(
        default=True,
        description="Space instances evenly across 'angle'",
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.features:
            raise ValueError("features must contain at least one name")
        if not self.axis.strip():
            raise ValueError("axis is required")
        if self.count < 2:
            raise ValueError("count must be at least 2")


class CreateDrawingInput(CompatInput):
    """Input schema for creating a new drawing.

    Attributes:
        name (str): The name value.
        template (str | None): The template value.
    """

    name: str = Field(
        description=(
            "A label for your own reference; SolidWorks names the new drawing "
            "itself (Draw1, ...) and the file takes the name of the path "
            "you save it to with save_file"
        )
    )
    template: str | None = Field(
        default=None,
        description=(
            "Drawing template (.drwdot) path; omit to use the SolidWorks default"
        ),
    )


async def register_modeling_tools(
    mcp: FastMCP, adapter: SolidWorksAdapter, config: dict[str, Any]
) -> int:
    """Register modeling tools with FastMCP.

    Registers comprehensive modeling tools for SolidWorks automation including model
    creation, feature creation, and model management operations.

    Args:
        mcp (FastMCP): The mcp value.
        adapter (SolidWorksAdapter): Adapter instance used for the operation.
        config (dict[str, Any]): Configuration values for the operation.

    Returns:
        int: The computed numeric result.

    Example:
                        ```python
                        from solidworks_mcp.tools.modeling import register_modeling_tools

                        tool_count = await register_modeling_tools(mcp, adapter, config)
                        print(f"Registered {tool_count} modeling tools")
                        ```
    """
    mcp = with_tool_boundary(mcp)
    tool_count = 0

    @mcp.tool()
    async def open_model(input_data: OpenModelInput) -> dict[str, Any]:
        """Open a part, assembly or drawing from disk and make it the active document.

        Use it to start work on an existing file. To switch to a document that is
        already open, use `activate_document`. Needs: the file on disk (a vault file
        must be checked out). Changes: opens the document; nothing is written. Returns:
        `model` with `title`, `type`, `path` and `configuration`.

        Args:
            input_data: The file. `file_path` (.sldprt, .sldasm or .slddrw) is
                required.

        Returns:
            dict[str, Any]: The opened document.
        """
        input_data = normalize_input(input_data, OpenModelInput)
        result = await adapter.open_model(input_data.file_path)

        require_success(result, context="Failed to open model")
        model = result.data
        title = _result_value(model, "title", "name", default=input_data.file_path)
        model_type = _result_value(model, "type", default="Part")
        path = _result_value(model, "path", "file_path", default=input_data.file_path)
        configuration = _result_value(model, "configuration", default="Default")
        return {
            "status": "success",
            "message": f"Opened {model_type}: {title}",
            "model": {
                "title": title,
                "name": title,
                "type": model_type,
                "path": path,
                "configuration": configuration,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_part(input_data: CreatePartInput) -> dict[str, Any]:
        """Create a new, empty part document and make it active, ready for `create_sketch`.

        Uses `template` (a .prtdot) or the default part template, then sets `units` if
        given, and assigns `material` if given. The part is not saved until
        `save_part`. Needs: SolidWorks running. Changes: opens a new part document.
        Returns: `part` with `name`, `units`, `template` and `material` (the one
        assigned, or null), plus a `warning` when the material couldn't be assigned;
        the part is created either way.

        Args:
            input_data: The part. `name` is required but only a label: the reply
                gives SolidWorks' own name (Part1, ...); `template`, `units` (mm, cm, m, in, ft) and
                `material` (a name from `list_available_materials`) are optional.

        Returns:
            dict[str, Any]: The new part.
        """
        input_data = normalize_input(input_data, CreatePartInput)
        result = await adapter.create_part(
            input_data.name, input_data.units, input_data.template
        )

        require_success(result, context="Failed to create part")
        model = result.data
        part_name = _result_value(model, "name", default=input_data.name)
        units = _result_value(model, "units", default=input_data.units or "mm")
        material = None
        warning = None
        if input_data.material:
            assigned = await adapter.set_material(input_data.material)
            if assigned.is_success:
                material = input_data.material
            else:
                warning = (
                    f"The part was created without a material: "
                    f"'{input_data.material}' could not be assigned "
                    f"({assigned.error}). Use list_available_materials, then "
                    "set_material."
                )
        reply: dict[str, Any] = {
            "status": "success",
            "message": f"Created new part: {part_name}",
            "part": {
                "name": part_name,
                "units": units,
                "material": material,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }
        if warning:
            reply["warning"] = warning
        return reply

    @mcp.tool()
    async def create_assembly(input_data: CreateAssemblyInput) -> dict[str, Any]:
        """Create a new, empty assembly document and make it active, ready for `insert_component`.

        Uses `template` (an .asmdot) or the default assembly template. It is not saved
        until `save_assembly`. Needs: SolidWorks running. Changes: opens a new assembly
        document. Returns: `assembly` with `name` and `template`. Then call
        `insert_component` for each part.

        Args:
            input_data: The assembly. `name` is required but only a label: the
                reply gives SolidWorks' own name (Assem1, ...); `template` has a
                default.

        Returns:
            dict[str, Any]: The new assembly.
        """
        input_data = normalize_input(input_data, CreateAssemblyInput)
        result = await adapter.create_assembly(input_data.name, input_data.template)

        require_success(result, context="Failed to create assembly")
        model = result.data
        assembly_name = _result_value(model, "name", default=input_data.name)
        return {
            "status": "success",
            "message": f"Created new assembly: {assembly_name}",
            "assembly": {
                "name": assembly_name,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_drawing(input_data: CreateDrawingInput) -> dict[str, Any]:
        """Create a new, empty drawing document and make it active.

        Uses `template` (a .drwdot) or the default drawing template. Then place views
        with `create_drawing_view`; for a whole drawing from a model in one call, use
        `generate_drawing_package` instead. Needs: SolidWorks running. Changes: opens a
        new drawing document. Returns: `drawing` with `name` and `template`.

        Args:
            input_data: The drawing. `name` is required but only a label: the
                reply gives SolidWorks' own name (Draw1, ...); `template` has a
                default.

        Returns:
            dict[str, Any]: The new drawing.
        """
        input_data = normalize_input(input_data, CreateDrawingInput)
        result = await adapter.create_drawing(input_data.name, input_data.template)

        require_success(result, context="Failed to create drawing")
        model = result.data
        drawing_name = _result_value(model, "name", default=input_data.name)
        return {
            "status": "success",
            "message": f"Created new drawing: {drawing_name}",
            "drawing": {
                "name": drawing_name,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def close_model(input_data: CloseModelInput) -> dict[str, Any]:
        """Close the active document, saving it first only if asked.

        Use it when you are done with a document. Unsaved changes are lost unless `save`
        is on. Needs: an open, active document. Changes: closes the document, and with
        `save` writes it first. Returns: `saved`, whether a save was asked for.

        Args:
            input_data: The close. Nothing is required: `save` is off.

        Returns:
            dict[str, Any]: The close result.
        """
        input_data = normalize_input(input_data, CloseModelInput)
        result = await adapter.close_model(input_data.save)

        require_success(result, context="Failed to close model")
        return {
            "status": "success",
            "message": "Model closed successfully",
            "saved": input_data.save,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_extrusion(input_data: CreateExtrusionInput) -> dict[str, Any]:
        """Extrude the sketch you just closed into a solid boss, added to the active part.

        Use it after `exit_sketch`; to remove material, use `create_cut_extrude`. It
        extrudes the sketch `sketch_name` names, or the one `exit_sketch` closed last;
        a name that isn't in the feature tree fails before anything is built. End
        conditions: Blind (default), MidPlane, ThroughAll, UpToNext; `both_directions`
        means MidPlane. With `thin_feature` and `thin_thickness` it makes a wall from the
        sketch's outline, and an open chain works (a bent plate from its centreline).
        Needs: an open part and a closed profile (open is fine when thin). Changes:
        adds a Boss-Extrude feature. Returns: `extrusion` (`name`, `sketch` when one
        was named, `depth`, the `end_condition` SolidWorks used, `both_directions`,
        and `thin` when thin) and
        `measured_change` (volume, bounding box and solid-body count before and after;
        left out when the model can't be read).

        Args:
            input_data: The extrusion. `depth` (mm) is required; `sketch_name`,
                `end_condition`, `both_directions`, `reverse_direction`,
                `draft_angle`, `thin_feature`/`thin_thickness` and `merge_result`
                have defaults.

        Returns:
            dict[str, Any]: The created feature.
        """
        input_data = normalize_input(input_data, CreateExtrusionInput)
        # Convert input to ExtrusionParameters
        params = ExtrusionParameters(
            depth=input_data.depth,
            draft_angle=input_data.draft_angle,
            reverse_direction=input_data.reverse_direction,
            both_directions=input_data.both_directions,
            thin_feature=input_data.thin_feature,
            thin_thickness=input_data.thin_thickness,
            thin_side=input_data.thin_side,
            end_condition=input_data.end_condition,
            merge_result=input_data.merge_result,
            feature_scope=False,
            auto_select=True,
            sketch_name=input_data.sketch_name,
        )

        before = await _read_summary(adapter)
        result = await adapter.create_extrusion(params)

        require_success(result, context="Failed to create extrusion")
        after = await _read_summary(adapter) if before is not None else None
        feature = result.data
        name = _result_value(feature, "feature_name", "name", default="Extrusion")
        applied = _result_value(feature, "parameters", default=None) or {}
        extrusion: dict[str, Any] = {
            "name": name,
            "sketch": applied.get("sketch_name"),
            "depth": input_data.depth,
            "end_condition": applied.get("end_condition")
            or ("MidPlane" if input_data.both_directions else input_data.end_condition),
            "both_directions": input_data.both_directions,
        }
        if input_data.thin_feature:
            extrusion["thin"] = {
                "thickness": input_data.thin_thickness,
                "side": input_data.thin_side,
            }
        reply = {
            "status": "success",
            "message": f"Created extrusion: {name}",
            "extrusion": extrusion,
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def create_revolve(input_data: CreateRevolveInput) -> dict[str, Any]:
        """Revolve a closed sketch around an axis, adding a solid to the active part.

        Use it for turned shapes (shafts, knobs). It revolves the sketch `sketch_name`
        names, or the one `exit_sketch` closed last, about the reference axis
        `axis_entity` names (from `create_axis`), or about the centreline drawn in the
        sketch with `add_centerline`. A sketch or axis that isn't in the model fails
        before anything is built. Needs: an open part and a closed profile with a
        centreline or a reference axis. Changes: adds a Revolve feature. Returns:
        `revolve` (`name`, `sketch` and `axis_entity` when named, `angle`) and
        `measured_change` (volume, bounding box and solid-body count before and
        after; left out when the model can't be read).

        Args:
            input_data: The revolve. `angle` (degrees, 360 for a full turn) is
                required; `sketch_name`, `axis_entity`, `both_directions`,
                `reverse_direction`, `thin_feature` and `merge_result` have defaults.

        Returns:
            dict[str, Any]: The created feature.
        """
        input_data = normalize_input(input_data, CreateRevolveInput)
        # Convert input to RevolveParameters
        params = RevolveParameters(
            angle=input_data.angle,
            reverse_direction=input_data.reverse_direction,
            both_directions=input_data.both_directions,
            thin_feature=input_data.thin_feature,
            thin_thickness=input_data.thin_thickness,
            merge_result=input_data.merge_result,
            sketch_name=input_data.sketch_name,
            axis_entity=input_data.axis_entity,
        )

        before = await _read_summary(adapter)
        result = await adapter.create_revolve(params)

        require_success(result, context="Failed to create revolve")
        after = await _read_summary(adapter) if before is not None else None
        feature = result.data
        name = _result_value(feature, "feature_name", "name", default="Revolve")
        applied = _result_value(feature, "parameters", default=None) or {}
        reply = {
            "status": "success",
            "message": f"Created revolve: {name}",
            "revolve": {
                "name": name,
                "sketch": applied.get("sketch_name"),
                "axis_entity": applied.get("axis_entity"),
                "angle": input_data.angle,
            },
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def get_dimension(input_data: GetDimensionInput) -> dict[str, Any]:
        """Read one dimension of the active model by its full name, e.g. "D1@Sketch1".

        Find names with `list_model_dimensions`. Needs: an open part or assembly.
        Read-only. Returns: `dimension` with `name`, `value` and `units`: "mm" for a
        length, "deg" for an angle, and null for a count (such as a pattern's
        instance count).

        Args:
            input_data: The dimension. Give `name` (or `dimension_name`), e.g.
                "D1@Boss-Extrude1".

        Returns:
            dict[str, Any]: The dimension's value.
        """
        input_data = normalize_input(input_data, GetDimensionInput)
        result = await adapter.get_dimension(input_data.name)

        require_success(result, context="Failed to get dimension")
        reading = result.data or {}
        dimension_value = reading.get("value")
        dimension_units = reading.get("units")
        unit_text = f" {dimension_units}" if dimension_units else ""
        return {
            "status": "success",
            "message": f"Dimension {input_data.name} = {dimension_value}{unit_text}",
            "dimension": {
                "name": input_data.name,
                "value": dimension_value,
                "units": dimension_units,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_dimension(input_data: SetDimensionInput) -> dict[str, Any]:
        """Change one length dimension of the active model, in mm, and rebuild.

        Use it to resize an existing model; find the full name with
        `list_model_dimensions` and check the result with `rebuild_model` or
        `verify_model`. The value is always millimetres. Needs: an open part or
        assembly. Changes: the dimension and the geometry it drives. Returns:
        `dimension_update` with `name`, `old_value` and `new_value`.

        Args:
            input_data: The change. `value` (mm) is required, with `name` (or
                `dimension_name`) such as "D1@Sketch1"; `units` is not used.

        Returns:
            dict[str, Any]: The old and new values.
        """
        input_data = normalize_input(input_data, SetDimensionInput)
        result = await adapter.set_dimension(input_data.name, input_data.value)

        require_success(result, context="Failed to set dimension")
        payload = result.data
        return {
            "status": "success",
            "message": f"Set dimension {input_data.name} = {input_data.value} mm",
            "dimension_update": {
                "name": input_data.name,
                "old_value": _result_value(payload, "old_value"),
                "new_value": _result_value(
                    payload, "new_value", default=input_data.value
                ),
                "units": input_data.units or "mm",
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_units(input_data: SetUnitsInput) -> dict[str, Any]:
        """Set the active document's length units: mm, cm, m, in or ft.

        Use it on a new part before sketching if you want other than the template's
        units. Aliases such as "inch" are accepted. The setting is read back, so success
        means it applied. Tool inputs stay in mm whatever the document shows. Needs: an
        open, active document. Changes: the document's unit system. Returns: `data` with
        `unit_system`, the values applied and observed, and `verified`.

        Args:
            input_data: The units. `unit_system` (mm, cm, m, in or ft) is
                required.

        Returns:
            dict[str, Any]: The units set.
        """
        input_data = normalize_input(input_data, SetUnitsInput)
        result = await adapter.set_units(input_data.unit_system)
        require_success(result, context="Failed to set units")
        data = result.data if isinstance(result.data, dict) else {}
        applied = data.get("unit_system", input_data.unit_system)
        message = f"Set document units to {applied}"
        if data.get("verified") is None:
            message += " (could not be read back to confirm)"
        return {
            "status": "success",
            "message": message,
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_cut_extrude(input_data: CreateCutExtrudeInput) -> dict[str, Any]:
        """Cut material from the active part with a closed sketch profile: holes, slots, windows.

        Use it after `exit_sketch`. Pass `sketch_name` unless the sketch you just closed
        is the one: with no name only that sketch is used, and any doubt is an error
        naming the sketches found. A one-way cut that finds no material is retried the
        other way (`direction_flipped`). For a sketch inside the body, use
        ThroughAllBoth. Needs: an open part with a solid body. Changes: adds a
        Cut-Extrude feature. Returns: `cut_extrude` (`name`, `sketch_name`,
        `direction_flipped`) and `measured_change` (volume, bounding box and solid-body
        count before and after; left out when the model can't be read).

        Args:
            input_data: The cut. `depth` (mm) is required; `sketch_name`,
                `end_condition` (Blind, ThroughAll, ThroughAllBoth),
                `both_directions`, `reverse_direction` and `draft_angle` have
                defaults.

        Returns:
            dict[str, Any]: The created cut.
        """
        input_data = normalize_input(input_data, CreateCutExtrudeInput)
        params = ExtrusionParameters(
            depth=input_data.depth,
            draft_angle=input_data.draft_angle,
            reverse_direction=input_data.reverse_direction,
            both_directions=input_data.both_directions,
            thin_feature=False,
            thin_thickness=None,
            end_condition=input_data.end_condition,
            merge_result=False,
            feature_scope=False,
            auto_select=True,
            sketch_name=input_data.sketch_name,
        )
        before = await _read_summary(adapter)
        result = await adapter.create_cut_extrude(params)
        require_success(result, context="Failed to create cut-extrude")
        after = await _read_summary(adapter) if before is not None else None
        feature = result.data
        feature_params = _result_value(feature, "parameters", default={})
        sketch_used = (
            feature_params.get("sketch_name")
            if isinstance(feature_params, dict)
            else None
        ) or input_data.sketch_name
        flipped = bool(
            isinstance(feature_params, dict) and feature_params.get("direction_flipped")
        )
        name = _result_value(feature, "feature_name", "name", default="Cut-Extrude")
        message = f"Created cut-extrude: {name}"
        if flipped:
            message += (
                " (the requested direction found no material, so it cut the other way)"
            )
        reply = {
            "status": "success",
            "message": message,
            "cut_extrude": {
                "name": name,
                "depth": input_data.depth,
                "sketch_name": sketch_used,
                "direction_flipped": flipped,
            },
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def add_fillet(input_data: AddFilletInput) -> dict[str, Any]:
        """Round edges of the active part with a constant-radius fillet.

        Name the edges as "Edge<1>", a point "x,y,z" (metres) or "face:x,y,z" for every
        edge of a face; or leave `edge_names` empty to use the current selection (e.g.
        from `select_face_edges`). A fillet that leaves the volume unchanged is an
        error. Needs: an open part with a solid body. Changes: adds a Fillet feature.
        Returns: `fillet` with `name`, `radius` and `edges`.

        Args:
            input_data: The fillet. `radius` (mm) is required; `edge_names`
                defaults to the current selection.

        Returns:
            dict[str, Any]: The created fillet.
        """
        input_data = normalize_input(input_data, AddFilletInput)
        result = await adapter.add_fillet(input_data.radius, input_data.edge_names)
        require_success(result, context="Failed to add fillet")
        feature = result.data
        return {
            "status": "success",
            "message": f"Created fillet: {_result_value(feature, 'feature_name', 'name', default='Fillet')}",
            "fillet": {
                "name": _result_value(
                    feature, "feature_name", "name", default="Fillet"
                ),
                "radius": input_data.radius,
                "edges": input_data.edge_names,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_chamfer(input_data: AddChamferInput) -> dict[str, Any]:
        """Bevel edges of the active part with a chamfer: `distance` along one face at `angle` (45 by default).

        Name the edges as "Edge<1>", a point "x,y,z" (metres) or "face:x,y,z" for every
        edge of a face; or leave `edge_names` empty to use the current selection (e.g.
        from `select_face_edges`). At 45 degrees both legs equal `distance`; at another
        angle, `flip` swaps which face `distance` is measured on. Needs: an open part
        with a solid body. Changes: adds a Chamfer feature. Returns: `chamfer` with
        `name`, `distance`, `angle`, `flip` and `edges`.

        Args:
            input_data: The chamfer. `distance` (mm) is required; `edge_names`
                defaults to the current selection.

        Returns:
            dict[str, Any]: The created chamfer.
        """
        input_data = normalize_input(input_data, AddChamferInput)
        result = await adapter.add_chamfer(
            input_data.distance,
            input_data.edge_names,
            input_data.angle,
            input_data.flip,
        )
        require_success(result, context="Failed to add chamfer")
        feature = result.data
        return {
            "status": "success",
            "message": f"Created chamfer: {_result_value(feature, 'feature_name', 'name', default='Chamfer')}",
            "chamfer": {
                "name": _result_value(
                    feature, "feature_name", "name", default="Chamfer"
                ),
                "distance": input_data.distance,
                "angle": input_data.angle,
                "flip": input_data.flip,
                "edges": input_data.edge_names,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_sweep(input_data: CreateSweepInput) -> dict[str, Any]:
        """Sweep a closed profile sketch along a path sketch to make a solid (Insert > Boss/Base > Sweep).

        Draw the closed profile and the open path as two sketches first. The profile is
        the sketch you closed last that isn't the path. Needs: an open part with both
        sketches. Changes: adds a Sweep feature. Returns: `sweep` with `name`, `path`,
        `twist_along_path` and `twist_angle`.

        Args:
            input_data: The sweep. `path` (the path sketch's name) is required;
                `twist_along_path`, `twist_angle` (degrees) and `merge_result` have
                defaults.

        Returns:
            dict[str, Any]: The created sweep.
        """
        input_data = normalize_input(input_data, CreateSweepInput)
        params = SweepParameters(
            path=input_data.path,
            twist_along_path=input_data.twist_along_path,
            twist_angle=input_data.twist_angle,
            merge_result=input_data.merge_result,
        )
        result = await adapter.create_sweep(params)
        require_success(result, context="Failed to create sweep")
        feature = result.data
        return {
            "status": "success",
            "message": f"Created sweep: {_result_value(feature, 'feature_name', 'name', default='Sweep')}",
            "sweep": {
                "name": _result_value(feature, "feature_name", "name", default="Sweep"),
                "path": input_data.path,
                "twist_along_path": input_data.twist_along_path,
                "twist_angle": input_data.twist_angle,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_loft(input_data: CreateLoftInput) -> dict[str, Any]:
        """Loft a solid through two or more closed profile sketches, in order (Insert > Boss/Base > Loft).

        Use it for shapes that change section, such as a wing or a transition duct. Put
        each profile on its own plane (see `create_reference_plane`). Needs: an open
        part with the profile sketches. Changes: adds a Loft feature. Returns: `loft`
        with `name`, `profiles` and `guide_curves`.

        Args:
            input_data: The loft. `profiles` (sketch names, in order) is required;
                `guide_curves`, `start_tangent`, `end_tangent` and `merge_result`
                have defaults.

        Returns:
            dict[str, Any]: The created loft.
        """
        input_data = normalize_input(input_data, CreateLoftInput)
        params = LoftParameters(
            profiles=input_data.profiles,
            guide_curves=input_data.guide_curves,
            start_tangent=input_data.start_tangent,
            end_tangent=input_data.end_tangent,
            merge_result=input_data.merge_result,
        )
        result = await adapter.create_loft(params)
        require_success(result, context="Failed to create loft")
        feature = result.data
        return {
            "status": "success",
            "message": f"Created loft: {_result_value(feature, 'feature_name', 'name', default='Loft')}",
            "loft": {
                "name": _result_value(feature, "feature_name", "name", default="Loft"),
                "profiles": input_data.profiles,
                "guide_curves": input_data.guide_curves,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def insert_component(input_data: InsertComponentInput) -> dict[str, Any]:
        """Insert a part or sub-assembly file into the active assembly at a position in mm.

        Use it after `create_assembly`, then position components with `add_mate`. The
        file must contain solid geometry; an empty or missing file is an error. Needs:
        an open, active assembly and the file on disk. Changes: adds a component.
        Returns: `component` with its instance name (`component`, which `add_mate`
        takes), `file_path`, `position` and the counts before and after.

        Args:
            input_data: The component. `file_path` is required; `x`, `y`, `z` (mm
                from the assembly origin) default to 0.

        Returns:
            dict[str, Any]: The inserted component.
        """
        input_data = normalize_input(input_data, InsertComponentInput)
        result = await adapter.insert_component(
            input_data.file_path, input_data.x, input_data.y, input_data.z
        )
        require_success(result, context="Failed to insert component")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": f"Inserted {data.get('component', 'component')}",
            "component": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def add_mate(input_data: AddMateInput) -> dict[str, Any]:
        """Mate two components of the active assembly: coincident, concentric, parallel, perpendicular, tangent, distance or angle.

        Each side is a named reference plane or axis (`entity_a`, e.g. "Front Plane"),
        or a face given by a point on it (`face_a`, mm, in that part's own coordinates):
        a pin's round face and a hole's face make a concentric mate. Get instance names
        from `list_components`. Needs: an open assembly with both components. Changes:
        adds a mate and may move components. Returns: `mate` with `mate_type`,
        `components`, `entities`, `geometry_moved` and `moved_components`.

        Args:
            input_data: The mate. `component_a` and `component_b` are required;
                each side takes `entity_*` or `face_*` (default "Front Plane");
                `mate_type` (coincident), `alignment`, `distance` (mm) and `angle`
                (degrees) have defaults.

        Returns:
            dict[str, Any]: The mate added.
        """
        input_data = normalize_input(input_data, AddMateInput)
        result = await adapter.add_mate(
            input_data.component_a,
            input_data.component_b,
            input_data.entity_a or "Front Plane",
            input_data.entity_b or "Front Plane",
            input_data.mate_type,
            input_data.alignment,
            input_data.distance,
            input_data.angle,
            input_data.face_a,
            input_data.face_b,
        )
        require_success(result, context="Failed to add mate")
        data = result.data if isinstance(result.data, dict) else {}
        message = (
            f"Added {input_data.mate_type} mate between "
            f"{input_data.component_a} and {input_data.component_b}"
        )
        # SolidWorks accepts a mate whose constraint is already
        # satisfied and moves nothing. That is a real success, but
        # saying so plainly beats leaving the caller to infer it.
        if data.get("geometry_moved") is False:
            message += " (no component moved - the constraint was already satisfied)"
        return {
            "status": "success",
            "message": message,
            "mate": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_component_state(input_data: SetComponentStateInput) -> dict[str, Any]:
        """Fix or float a component of the active assembly, or make a sub-assembly rigid or flexible.

        Float a part so mates can position it (the first part inserted is fixed); fix
        one to hold it still. Make a sub-assembly flexible so its own mates move in
        this assembly (a crank whose knob turns). Only what you pass changes: the
        component's suppression, visibility and configuration are kept. Needs: an
        open assembly. Changes: the component's fixed or solving state. Returns:
        `state` with `component`, `before` and `after` (`fixed`, `flexible` and the
        properties kept).

        Args:
            input_data: The component and what to change: `fixed`, `flexible` or
                both.

        Returns:
            dict[str, Any]: The state before and after.
        """
        input_data = normalize_input(input_data, SetComponentStateInput)
        result = await adapter.set_component_state(
            input_data.component, input_data.fixed, input_data.flexible
        )
        require_success(result, context="Failed to set the component state")
        data = result.data if isinstance(result.data, dict) else {}
        after = data.get("after", {})
        words = []
        if input_data.fixed is not None:
            words.append("fixed" if after.get("fixed") else "floating")
        if input_data.flexible is not None:
            words.append("flexible" if after.get("flexible") else "rigid")
        return {
            "status": "success",
            "message": f"{input_data.component} is now {' and '.join(words)}",
            "state": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def list_components() -> dict[str, Any]:
        """List the top-level components of the active assembly by instance name, e.g. "bracket-1".

        Use it before `add_mate`, which takes these names. Needs: an open, active
        assembly. Read-only. Returns: `components` (instance names).
        """
        result = await adapter.list_components()
        require_success(result, context="Failed to list components")
        components = result.data if isinstance(result.data, list) else []
        return {
            "status": "success",
            "message": f"{len(components)} component(s) in the assembly",
            "components": components,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def delete_feature(input_data: DeleteFeatureInput) -> dict[str, Any]:
        """Delete a feature or sketch from the active model, along with the features that depend on it.

        Ask the user before you call it: deleting a sketch also deletes every feature
        built from it (a cut, a boss), and deleting a feature deletes everything that
        depends on it. Use `suppress_feature` instead when you might want it back. Find
        names and dependents with `list_features`. Needs: an open part or assembly.
        Changes: removes the feature and its dependents (`undo` can restore them).
        Returns: `data` with `deleted`, `removed_features` (every feature that went,
        dependents included), `features_before` and `features_after`; the message names
        the dependents, and a `warning` says so whenever more than the named feature
        went: tell the user.

        Args:
            input_data: The feature. `name` (e.g. "Fillet1") is required.

        Returns:
            dict[str, Any]: What was deleted.
        """
        input_data = normalize_input(input_data, DeleteFeatureInput)
        result = await adapter.delete_feature(input_data.name)
        require_success(result, context="Failed to delete feature")
        data = result.data if isinstance(result.data, dict) else {}
        removed = data.get("removed_features") or [input_data.name]
        dependents = [n for n in removed if n != input_data.name.split("@", 1)[0]]
        reply: dict[str, Any] = {
            "status": "success",
            "message": (
                f"Deleted {input_data.name}"
                + (
                    f" and its dependents: {', '.join(dependents)}"
                    if dependents
                    else ""
                )
            ),
            "data": data,
            "execution_time": result.execution_time,
        }
        if dependents:
            reply["warning"] = (
                f"Deleting {input_data.name} also deleted {', '.join(dependents)}. "
                "Tell the user; `undo` restores them."
            )
        return reply

    @mcp.tool()
    async def suppress_feature(input_data: SuppressFeatureInput) -> dict[str, Any]:
        """Suppress or unsuppress a feature of the active model; suppressed features stay in the tree but are not built.

        Use it to turn off a feature that breaks the rebuild without deleting it. Needs:
        an open part or assembly. Changes: the feature's suppression state, and its
        children's. Returns: `data` with `feature`, `requested`, `suppressed` (read
        back; null when unreadable) and `was_suppressed`.

        Args:
            input_data: The feature. `name` is required; `suppress` defaults to on
                (pass false to unsuppress).

        Returns:
            dict[str, Any]: The new state.
        """
        input_data = normalize_input(input_data, SuppressFeatureInput)
        result = await adapter.suppress_feature(input_data.name, input_data.suppress)
        require_success(result, context="Failed to suppress feature")
        data = result.data if isinstance(result.data, dict) else {}
        verb = "Suppressed" if input_data.suppress else "Unsuppressed"
        message = f"{verb} {input_data.name}"
        if data.get("suppressed") is None:
            message += " (state could not be read back)"
        return {
            "status": "success",
            "message": message,
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def rename_feature(input_data: RenameFeatureInput) -> dict[str, Any]:
        """Rename a feature in the active model's feature tree.

        Use it to give features meaningful names (e.g. "MountingHoles"). The new name is
        read back: a name another feature already uses is an error. Renaming to the
        current name succeeds with no change. Needs: an open part or assembly. Changes:
        the feature's name. Returns: `data` with `old_name`, `new_name`, `renamed` and,
        when unchanged, `reason`.

        Args:
            input_data: The rename. `old_name` and `new_name` are required.

        Returns:
            dict[str, Any]: The rename.
        """
        input_data = normalize_input(input_data, RenameFeatureInput)
        result = await adapter.rename_feature(input_data.old_name, input_data.new_name)
        require_success(result, context="Failed to rename feature")
        data = result.data if isinstance(result.data, dict) else {}
        if data.get("renamed") is False:
            return {
                "status": "success",
                "message": (
                    f"{input_data.old_name} unchanged: "
                    + str(data.get("reason") or "no change")
                ),
                "data": data,
                "execution_time": result.execution_time,
            }
        return {
            "status": "success",
            "message": (
                f"Renamed {data.get('old_name', input_data.old_name)} to "
                f"{data.get('new_name', input_data.new_name)}"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def select_feature(input_data: SelectFeatureInput) -> dict[str, Any]:
        """Select a feature, sketch, plane or component by name in the active document.

        Use it to set up a selection that the next SolidWorks operation acts on.
        `append` adds to the selection instead of replacing it. A name that can't be
        selected is an error. Needs: an open document. Changes: the selection only.
        Returns: `data` with `selected_name` and `selection_count`.

        Args:
            input_data: The selection. `feature_name` is required; `append` is off.

        Returns:
            dict[str, Any]: The selection.
        """
        input_data = normalize_input(input_data, SelectFeatureInput)
        result = await adapter.select_feature(
            input_data.feature_name, input_data.append
        )
        require_success(result)
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": (
                f"Selected {data.get('selected_name', input_data.feature_name)} "
                f"({data.get('selection_count', '?')} selected)"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def select_face_edges(input_data: SelectFaceEdgesInput) -> dict[str, Any]:
        """Select every edge of one face of the active part, ready for `add_fillet` or `add_chamfer` with no edge names.

        Pick the face with one of `point` (a point on it, mm), `side` (top, bottom,
        front, back, right, left or +X..-Z; the furthest flat face that way) or `plane`
        (the face lying on that plane). `edge_type` narrows to linear or circular edges
        (hole rims). Needs: an open part. Changes: the selection only. Returns: `data`
        with `face`, `edges`, `selected_edges` and `selection_count`.

        Args:
            input_data: The face. Give exactly one of `point`, `side` or `plane`;
                `edge_type` (all) and `append` (off) have defaults.

        Returns:
            dict[str, Any]: The edges selected.
        """
        input_data = normalize_input(input_data, SelectFaceEdgesInput)
        result = await adapter.select_face_edges(
            input_data.point,
            input_data.side,
            input_data.plane,
            input_data.edge_type,
            input_data.append,
        )
        require_success(result)
        data = result.data if isinstance(result.data, dict) else {}
        kinds = sorted({e.get("curve", "other") for e in data.get("edges", [])})
        return {
            "status": "success",
            "message": (
                f"Selected {data.get('selected_edges', 0)} edge(s) "
                f"({', '.join(kinds)}) on the face at "
                f"{data.get('face', {}).get('center_mm')} mm"
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def rebuild_model(
        input_data: RebuildModelInput | None = None,
    ) -> dict[str, Any]:
        """Rebuild the active model and report each feature that fails, with the reason and a fix.

        Use it after `set_dimension` or other edits to confirm the model is sound.
        Failing features make the call an error whose `data.errors` names each one, its
        SolidWorks error, what it depends on and a `hint`; warnings alone still succeed.
        Needs: an open part or assembly. Changes: rebuilds the model. Returns: `data`
        with `rebuilt`, `errors`, `error_count`, `warning_count` and `summary`.

        Args:
            input_data: Nothing is required: `top_level_only` is off (a full
                rebuild).

        Returns:
            dict[str, Any]: The rebuild report.
        """
        input_data = normalize_input(input_data or {}, RebuildModelInput)
        result = require_success(
            await adapter.rebuild_model(input_data.top_level_only), with_data=True
        )
        data = result.data if isinstance(result.data, dict) else None
        response: dict[str, Any] = {
            "status": "success",
            "message": (data or {}).get("summary") or "Rebuilt",
            "execution_time": result.execution_time,
        }
        if data is not None:
            response["data"] = data
        return response

    @mcp.tool()
    async def undo(input_data: UndoInput | None = None) -> dict[str, Any]:
        """Undo the last operations in the active model (Edit > Undo).

        Use it to step back after a feature went wrong. SolidWorks accepts an undo with
        nothing to undo, so the reply says whether the feature tree changed. Needs: an
        open document. Changes: reverts the last `count` operations. Returns: `data`
        with `requested_steps`, `features_before`, `features_after` and `tree_changed`.

        Args:
            input_data: Nothing is required: `count` defaults to 1.

        Returns:
            dict[str, Any]: What changed.
        """
        input_data = normalize_input(input_data or UndoInput(), UndoInput)
        result = await adapter.undo(input_data.count)
        require_success(result, context="Failed to undo")
        data = result.data if isinstance(result.data, dict) else {}
        changed = data.get("tree_changed")
        if changed is False:
            message = (
                f"Undo of {input_data.count} step(s) left the feature "
                "tree unchanged - there was nothing to undo"
            )
        else:
            message = f"Undid {input_data.count} step(s)"
        return {
            "status": "success",
            "message": message,
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_reference_plane(
        input_data: CreateReferencePlaneInput,
    ) -> dict[str, Any]:
        """Add a reference plane offset from, at an angle to, or on a plane or flat face.

        Use it to sketch somewhere other than the three default planes: pass the new
        plane's name to `create_sketch`. Offset: `reference` and a non-zero `offset`
        (mm). Angle: `reference`, `angle` (degrees) and `axis`, an axis lying in the
        reference (make one with `create_axis`). Face: `face_point`, a point on a flat
        face (sloped or not), with an `offset` or 0 for a plane on the face. Needs: an
        open part. Changes: adds a plane feature. Returns: `plane` with `name` and the
        inputs used.

        Args:
            input_data: The plane. Exactly one of `reference` and `face_point`;
                then `offset`, or `angle` with `axis`; `flip` is off.

        Returns:
            dict[str, Any]: The new plane.
        """
        input_data = normalize_input(input_data, CreateReferencePlaneInput)
        result = await adapter.create_reference_plane(
            input_data.reference,
            input_data.offset,
            input_data.angle,
            input_data.flip,
            input_data.axis,
            input_data.face_point,
        )
        require_success(result, context="Failed to create reference plane")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": f"Created reference plane: {data.get('name', 'Plane')}",
            "plane": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_axis(input_data: CreateAxisInput) -> dict[str, Any]:
        """Add a reference axis along the model's x, y or z direction, through the origin.

        Use it before `pattern_circular`, which rotates features about an axis. It is
        built where two default planes meet. Needs: an open part. Changes: adds an axis
        feature. Returns: `axis` with `name` (e.g. "Axis1", for
        `create_reference_plane`'s `axis`), `reference`, `planes` and the feature counts.

        Args:
            input_data: The axis. `reference` ("x", "y" or "z") is required.

        Returns:
            dict[str, Any]: The new axis.
        """
        input_data = normalize_input(input_data, CreateAxisInput)
        result = await adapter.create_axis(input_data.reference)
        require_success(result, context="Failed to create axis")
        data = result.data if isinstance(result.data, dict) else {}
        axis_name = data.get("reference", input_data.reference)
        return {
            "status": "success",
            "message": f"Created {axis_name} axis",
            "axis": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_reference_point(
        input_data: CreateReferencePointInput,
    ) -> dict[str, Any]:
        """Add a reference point on an edge (at a distance or percentage along it) or at the centre of a face.

        Use it to mark a position for a later feature or measurement. Pick the edge or
        face with a point on it in mm. Needs: an open part with that edge or face.
        Changes: adds a point feature. Returns: `point` with `mode`, `at_mm`,
        `distance_mm` or `percent`, and the feature counts.

        Args:
            input_data: The point. `mode` (along_curve or face_center) and `x`,
                `y`, `z` (mm) are required; for along_curve give one of `distance`
                (mm) or `percent`.

        Returns:
            dict[str, Any]: The new point.
        """
        input_data = normalize_input(input_data, CreateReferencePointInput)
        result = await adapter.create_reference_point(
            input_data.mode,
            input_data.x,
            input_data.y,
            input_data.z,
            input_data.distance,
            input_data.percent,
        )
        require_success(result, context="Failed to create reference point")
        data = result.data if isinstance(result.data, dict) else {}
        where = (
            f"{data.get('percent')}% along a curve"
            if data.get("percent") is not None
            else (
                f"{data.get('distance_mm')} mm along a curve"
                if data.get("distance_mm") is not None
                else "a face centre"
            )
        )
        return {
            "status": "success",
            "message": f"Created a reference point at {where}",
            "point": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def mirror_feature(input_data: MirrorFeatureInput) -> dict[str, Any]:
        """Mirror solid bodies or features of the active part about a plane.

        Use it for symmetric parts: model one half, then mirror. Body mirroring (the
        default) is what works for lofts and sweeps; to mirror a cut, name the cut and
        set `mirror_bodies` off. It fails when the volume doesn't change, which means
        nothing was mirrored. Needs: an open part with the named bodies or features.
        Changes: adds a Mirror feature. Returns: `mirror` with `name`, `mirrored`,
        `mirror_plane`, `merge`, `mirror_bodies`, and `volume_before`,
        `volume_after` and `volume_change` (mm³, negative for a cut).

        Args:
            input_data: The mirror. `features` (at least one name) and
                `mirror_plane` (e.g. "Right Plane") are required; `merge` and
                `mirror_bodies` are on.

        Returns:
            dict[str, Any]: The mirror created.
        """
        input_data = normalize_input(input_data, MirrorFeatureInput)
        result = await adapter.mirror_feature(
            input_data.features,
            input_data.mirror_plane,
            input_data.merge,
            input_data.mirror_bodies,
        )
        require_success(result, context="Failed to mirror feature")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": f"Mirrored {', '.join(input_data.features)} "
            f"about {input_data.mirror_plane}",
            "mirror": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def pattern_circular(input_data: PatternCircularInput) -> dict[str, Any]:
        """Repeat features of the active part around an axis, e.g. a ring of bosses or ribs.

        Create the axis first with `create_axis`. Bosses and cuts both work (a ring of
        holes is a patterned cut). It fails when the volume doesn't change, which
        means no instance landed on the part. Needs: an open part with the named
        features and axis. Changes: adds a circular pattern feature. Returns:
        `pattern` with `name`, `patterned`, `axis`, `count`, `angle`,
        `equal_spacing`, and `volume_before`, `volume_after` and `volume_change`
        (mm³, negative for cuts).

        Args:
            input_data: The pattern. `features` (at least one), `axis` and `count`
                (2 or more, the original included) are required; `angle` (360) and
                `equal_spacing` (on) have defaults.

        Returns:
            dict[str, Any]: The pattern created.
        """
        input_data = normalize_input(input_data, PatternCircularInput)
        result = await adapter.pattern_circular(
            input_data.features,
            input_data.axis,
            input_data.count,
            input_data.angle,
            input_data.equal_spacing,
        )
        require_success(result, context="Failed to pattern feature")
        data = result.data if isinstance(result.data, dict) else {}
        return {
            "status": "success",
            "message": f"Patterned {', '.join(input_data.features)} "
            f"around {input_data.axis} ({input_data.count} instances)",
            "pattern": data,
            "execution_time": result.execution_time,
        }

    # Counted from the registry rather than hand-maintained. The literal that
    # used to live here had drifted: it read 15 while 16 tools were actually
    # registered, so the function misreported its own work and the test
    # enshrined the wrong number.
    tool_count = len(await mcp.list_tools())
    return tool_count
