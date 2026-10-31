"""Modeling tools for SolidWorks MCP Server.

Provides tools for creating and manipulating SolidWorks models, including parts,
assemblies, drawings, and features like extrusions, revolves, etc.
"""

from typing import Any

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

    name: str = Field(description="Name for the new part")
    template: str | None = Field(
        default=None, description="Template file path for the new part"
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
        direction (str): The direction value.
        draft_angle (float): The draft angle value.
        end_condition (str): The end condition value.
        merge_result (bool): The merge result value.
        reverse (bool | None): The reverse value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str): The sketch name value.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
    """

    sketch_name: str = Field(description="Sketch name to extrude")
    depth: float = Field(description="Extrusion depth in millimeters")
    direction: str = Field(default="blind", description="Extrusion direction")
    reverse: bool | None = Field(default=None, description="Reverse direction alias")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(
        default=False, description="Reverse extrusion direction"
    )
    both_directions: bool = Field(
        default=False, description="Extrude in both directions"
    )
    thin_feature: bool = Field(default=False, description="Create as thin wall feature")
    thin_thickness: float | None = Field(
        default=None, description="Thickness for thin wall feature in mm"
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
            ValueError: Sketch_name is required.
        """
        if self.depth <= 0:
            raise ValueError("depth must be positive")
        if not self.sketch_name.strip():
            raise ValueError("sketch_name is required")
        if self.reverse is not None:
            self.reverse_direction = self.reverse


class CreateRevolveInput(CompatInput):
    """Input schema for creating a revolve feature.

    Attributes:
        angle (float): The angle value.
        axis_entity (str): The axis entity value.
        both_directions (bool): The both directions value.
        direction (str): The direction value.
        merge_result (bool): The merge result value.
        reverse_direction (bool): The reverse direction value.
        sketch_name (str): The sketch name value.
        thin_feature (bool): The thin feature value.
        thin_thickness (float | None): The thin thickness value.
    """

    sketch_name: str = Field(description="Sketch name to revolve")
    axis_entity: str = Field(description="Axis entity for the revolve")
    angle: float = Field(description="Revolve angle in degrees")
    direction: str = Field(default="one_direction", description="Revolve direction")
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
        sketch_name (str | None): Sketch to cut from.
    """

    depth: float = Field(description="Cut depth in millimeters")
    draft_angle: float = Field(default=0.0, description="Draft angle in degrees")
    reverse_direction: bool = Field(default=False, description="Reverse cut direction")
    end_condition: str = Field(default="Blind", description="End condition type")
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
    """Input schema for adding an equal-distance chamfer feature.

    Attributes:
        distance (float): Chamfer distance in millimeters.
        edge_names (list[str]): Edge names to chamfer.
    """

    distance: float = Field(description="Chamfer distance in millimeters")
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


class CreateAssemblyInput(CompatInput):
    """Input schema for creating a new assembly.

    Attributes:
        components (list[str]): The components value.
        name (str): The name value.
        template (str | None): The template value.
    """

    name: str = Field(description="Name for the new assembly")
    template: str | None = Field(
        default=None, description="Assembly template file path"
    )
    components: list[str] = Field(default_factory=list, description="Component list")


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
    entity_a: str = Field(
        default="Front Plane",
        description=(
            "Named feature on the first component. Only tree features "
            "(reference planes and axes) can be selected"
        ),
    )
    entity_b: str = Field(
        default="Front Plane", description="Named feature on the second component"
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


class CreateReferencePlaneInput(CompatInput):
    """Input schema for creating a reference plane.

    Attributes:
        reference (str): Name of the reference plane or planar face.
        offset (float): Offset distance in millimetres.
        angle (float): Angle in degrees.
        flip (bool): Reverse the offset or angle direction.
    """

    reference: str = Field(
        description="Name of the reference plane or planar face to offset "
        "from, e.g. 'Front Plane'"
    )
    offset: float = Field(
        default=0.0,
        description="Offset distance in millimetres. Must be non-zero — a "
        "plane coincident with its reference is not useful",
    )
    angle: float = Field(
        default=0.0,
        description="Angle in degrees. Not yet supported: an angled plane "
        "needs a second reference this tool cannot take, so a non-zero "
        "value errors. Use offset for parallel planes",
    )
    flip: bool = Field(default=False, description="Reverse the offset direction")

    def model_post_init(self, __context: Any) -> None:
        if not self.reference.strip():
            raise ValueError("reference is required")


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
        model_path (str | None): The model path value.
        name (str): The name value.
        sheet_format (str | None): The sheet format value.
        template (str | None): The template value.
    """

    name: str = Field(description="Name for the new drawing")
    template: str | None = Field(default=None, description="Drawing template file path")
    model_path: str | None = Field(default=None, description="Source model path")
    sheet_format: str | None = Field(default=None, description="Sheet format template")


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
        """Open a SolidWorks model (part, assembly, or drawing).

        Opens an existing SolidWorks file and makes it the active document for further
        operations. Supports all standard SolidWorks file formats and provides detailed model
        information upon successful opening.

        Args:
            input_data (OpenModelInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await open_model({
                                "file_path": "C:/Models/bracket.sldprt"
                            })

                            if result["status"] == "success":
                                model = result["model"]
                                print(f"Opened {model['type']}: {model['name']}")
                                print(f"Configuration: {model['configuration']}")
                            ```

                        Note:
                            File path must be absolute and accessible to SolidWorks.
                            Model becomes the active document for subsequent operations.
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
        """Create a new SolidWorks part document.

        Creates a new SolidWorks part document using the default part template. The new part
        becomes the active document and is ready for modeling operations such as sketch creation
        and feature addition.

        Args:
            input_data (CreatePartInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await create_part()

                            if result["status"] == "success":
                                part = result["model"]
                                print(f"Created new part: {part['name']}")
                                # Ready for sketching and feature creation
                            ```

                        Note:
                            - Uses default SolidWorks part template
                            - Part document is created in memory (not saved)
                            - Use save operations to persist to disk
                            - Subsequent modeling operations will apply to this part
        """
        input_data = normalize_input(input_data, CreatePartInput)
        result = await adapter.create_part(input_data.name, input_data.units)

        require_success(result, context="Failed to create part")
        model = result.data
        part_name = _result_value(model, "name", default=input_data.name)
        units = _result_value(model, "units", default=input_data.units or "mm")
        return {
            "status": "success",
            "message": f"Created new part: {part_name}",
            "part": {
                "name": part_name,
                "units": units,
                "material": input_data.material,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_assembly(input_data: CreateAssemblyInput) -> dict[str, Any]:
        """Create a new SolidWorks assembly document.

        Creates a new SolidWorks assembly document using the default assembly template. The new
        assembly becomes the active document and is ready for component insertion, mating, and
        assembly-level operations.

        Args:
            input_data (CreateAssemblyInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            result = await create_assembly()

                            if result["status"] == "success":
                                assembly = result["model"]
                                print(f"Created new assembly: {assembly['name']}")
                                # Ready for component insertion and mating
                            ```

                        Note:
                            - Uses default SolidWorks assembly template
                            - Assembly document is created in memory (not saved)
                            - Use save operations to persist to disk
                            - Ready for component insertion and mate creation
                            - Assembly tree will initially be empty

                        This tool creates a new assembly document using the default assembly template.
                        The new assembly will become the active document.
        """
        input_data = normalize_input(input_data, CreateAssemblyInput)
        result = await adapter.create_assembly(input_data.name)

        require_success(result, context="Failed to create assembly")
        model = result.data
        assembly_name = _result_value(model, "name", default=input_data.name)
        return {
            "status": "success",
            "message": f"Created new assembly: {assembly_name}",
            "assembly": {
                "name": assembly_name,
                "components": input_data.components,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_drawing(input_data: CreateDrawingInput) -> dict[str, Any]:
        """Create a new SolidWorks drawing document.

        This tool creates a new drawing document using the default drawing template. The new
        drawing will become the active document.

        Args:
            input_data (CreateDrawingInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
        input_data = normalize_input(input_data, CreateDrawingInput)
        result = await adapter.create_drawing(input_data.name)

        require_success(result, context="Failed to create drawing")
        model = result.data
        drawing_name = _result_value(model, "name", default=input_data.name)
        sheet_format = _result_value(
            model, "sheet_format", default=input_data.sheet_format
        )
        return {
            "status": "success",
            "message": f"Created new drawing: {drawing_name}",
            "drawing": {
                "name": drawing_name,
                "model_path": input_data.model_path,
                "sheet_format": sheet_format,
                "template": input_data.template,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def close_model(input_data: CloseModelInput) -> dict[str, Any]:
        """Close the current SolidWorks model.

        Closes the currently active SolidWorks document with an option to save changes before
        closing. This is essential for proper model lifecycle management and preventing data
        loss.

        Args:
            input_data (CloseModelInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Close without saving
                            result = await close_model({"save": False})

                            # Save and close
                            result = await close_model({"save": True})

                            if result["status"] == "success":
                                print(f"Model closed, saved: {result['saved']}")
                            ```

                        Note:
                            - Unsaved changes will be lost if save=False
                            - Always save important work before closing
                            - Model must be open to close it
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
        """Create an extrusion feature from the active sketch.

        Creates a 3D extrusion feature (boss or cut) from the currently active 2D sketch.
        Supports advanced options like draft angles, thin features, bidirectional extrusion, and
        various end conditions for professional modeling workflows.

        Args:
            input_data (CreateExtrusionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Simple boss extrusion
                            result = await create_extrusion({
                                "depth": 25.0,
                                "merge_result": True
                            })

                            # Cut with draft angle
                            result = await create_extrusion({
                                "depth": 10.0,
                                "reverse_direction": True,
                                "draft_angle": 2.0
                            })

                            # Thin wall feature
                            result = await create_extrusion({
                                "depth": 50.0,
                                "thin_feature": True,
                                "thin_thickness": 2.0
                            })
                            ```
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
            end_condition=input_data.end_condition,
            merge_result=input_data.merge_result,
            feature_scope=False,
            auto_select=True,
        )

        before = await _read_summary(adapter)
        result = await adapter.create_extrusion(params)

        require_success(result, context="Failed to create extrusion")
        after = await _read_summary(adapter) if before is not None else None
        feature = result.data
        reply = {
            "status": "success",
            "message": f"Created extrusion: {_result_value(feature, 'feature_name', 'name', default='Extrusion')}",
            "extrusion": {
                "name": _result_value(
                    feature, "feature_name", "name", default="Extrusion"
                ),
                "sketch": input_data.sketch_name,
                "depth": input_data.depth,
                "direction": input_data.direction,
            },
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def create_revolve(input_data: CreateRevolveInput) -> dict[str, Any]:
        """Create a revolve feature from the active sketch.

        Creates a 3D revolve feature by rotating the active 2D sketch profile around a specified
        axis of revolution. Supports full and partial revolves, thin features, and bidirectional
        revolution for comprehensive rotational modeling.

        Args:
            input_data (CreateRevolveInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Full revolution (cylinder)
                            result = await create_revolve({
                                "angle": 360.0,
                                "merge_result": True
                            })

                            # Partial revolution (arc section)
                            result = await create_revolve({
                                "angle": 120.0,
                                "both_directions": True
                            })

                            # Thin wall revolution (pipe)
                            result = await create_revolve({
                                "angle": 360.0,
                                "thin_feature": True,
                                "thin_thickness": 3.0
                            })
                            ```
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
        )

        before = await _read_summary(adapter)
        result = await adapter.create_revolve(params)

        require_success(result, context="Failed to create revolve")
        after = await _read_summary(adapter) if before is not None else None
        feature = result.data
        reply = {
            "status": "success",
            "message": f"Created revolve: {_result_value(feature, 'feature_name', 'name', default='Revolve')}",
            "revolve": {
                "name": _result_value(
                    feature, "feature_name", "name", default="Revolve"
                ),
                "sketch": input_data.sketch_name,
                "axis_entity": input_data.axis_entity,
                "angle": input_data.angle,
                "direction": input_data.direction,
            },
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def get_dimension(input_data: GetDimensionInput) -> dict[str, Any]:
        """Get the value of a dimension from the current model.

        Retrieves the current value of a named dimension from the active SolidWorks model.
        Dimensions can be from sketches, features, or global dimensions. Useful for parametric
        modeling and design validation.

        Args:
            input_data (GetDimensionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.

        Example:
                            ```python
                            # Get sketch dimension
                            result = await get_dimension({
                                "name": "D1@Sketch1"
                            })

                            if result["status"] == "success":
                                dim = result["dimension"]
                                print(f"Dimension {dim['name']}: {dim['value']} {dim['units']}")

                            # Get feature dimension
                            result = await get_dimension({
                                "name": "D1@Boss-Extrude1"
                            })
                            ```
        """
        input_data = normalize_input(input_data, GetDimensionInput)
        result = await adapter.get_dimension(input_data.name)

        require_success(result, context="Failed to get dimension")
        value = result.data
        dimension_value = _result_value(value, "value", default=value)
        dimension_units = _result_value(value, "units", default="mm")
        return {
            "status": "success",
            "message": f"Dimension {input_data.name} = {dimension_value} {dimension_units}",
            "dimension": {
                "name": input_data.name,
                "value": dimension_value,
                "units": dimension_units,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def set_dimension(input_data: SetDimensionInput) -> dict[str, Any]:
        """Set the value of a dimension in the current model.

        This tool modifies the value of a named dimension and rebuilds the model. Use this to
        parametrically modify your model dimensions.

        Args:
            input_data (SetDimensionInput): The input data value.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
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
        """Set the active document's linear unit system.

        Accepts ``mm``, ``cm``, ``m``, ``in`` or ``ft`` (plus common aliases
        such as ``inch`` or ``millimeters``). The setting is applied and then
        read back from the document; if the readback disagrees the tool
        reports an error rather than a false success.

        Args:
            input_data (SetUnitsInput): The target unit system.

        Returns:
            dict[str, Any]: Status and what was applied.

        Example:
            ```python
            await set_units({"unit_system": "in"})
            ```
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
        """Cut material from a sketch profile in the active model.

        Creates a Cut-Extrude feature (Insert > Cut > Extrude). Use this after
        exit_sketch when you want to remove material — e.g. to create windows,
        holes, slots, or any through/blind cut in an existing solid body.

        Sketch selection is never a silent guess: pass ``sketch_name``
        explicitly whenever you're not certain which sketch this should act
        on (e.g. more than one sketch could be unconsumed, or other tool
        calls ran in between). If omitted, only the sketch most recently
        created/exited in this same session is used, and only when it still
        exists in the model — there is no further fallback. Any ambiguity or
        mismatch is reported back as an error naming the sketch(es) actually
        found in the model, rather than cutting the wrong profile.

        Args:
            input_data (CreateCutExtrudeInput): Depth, direction, draft, and
                optional sketch_name parameters.

        Returns:
            dict[str, Any]: Status and feature details. On error, ``message``
                identifies exactly which stage failed (sketch not found,
                sketch selection rejected by SolidWorks, or the specific
                FeatureCut COM error) rather than a generic failure string.

        Example:
            ```python
            # Cut a blind pocket 10 mm deep from a named sketch
            result = await create_cut_extrude({"depth": 10.0, "sketch_name": "Sketch3"})

            # Through-all cut using the most recently exited sketch
            result = await create_cut_extrude({"depth": 200.0})
            ```
        """
        input_data = normalize_input(input_data, CreateCutExtrudeInput)
        params = ExtrusionParameters(
            depth=input_data.depth,
            draft_angle=input_data.draft_angle,
            reverse_direction=input_data.reverse_direction,
            both_directions=False,
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
        reply = {
            "status": "success",
            "message": f"Created cut-extrude: {_result_value(feature, 'feature_name', 'name', default='Cut-Extrude')}",
            "cut_extrude": {
                "name": _result_value(
                    feature, "feature_name", "name", default="Cut-Extrude"
                ),
                "depth": input_data.depth,
                "sketch_name": sketch_used,
            },
            "execution_time": result.execution_time,
        }
        return _attach_measured_change(reply, before, after)

    @mcp.tool()
    async def add_fillet(input_data: AddFilletInput) -> dict[str, Any]:
        """Add a fillet (rounded edge) to selected edges of the current model.

        Rounds the specified named edges with the given radius. Edge names use the
        SolidWorks convention, e.g. 'Edge<1>', or you can leave edge_names empty to
        fillet all edges if the adapter supports it.

        Args:
            input_data (AddFilletInput): Radius and edge names.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Fillet two specific edges with 2 mm radius
            result = await add_fillet({"radius": 2.0, "edge_names": ["Edge<1>", "Edge<2>"]})
            ```
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
        """Add an equal-distance chamfer to selected edges of the current model.

        Chamfers the specified named edges with the given distance. Edge names use
        the SolidWorks convention, e.g. 'Edge<1>', or you can leave edge_names empty
        to chamfer all edges if the adapter supports it.

        Args:
            input_data (AddChamferInput): Distance and edge names.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Chamfer two specific edges with a 1.5 mm distance
            result = await add_chamfer({"distance": 1.5, "edge_names": ["Edge<1>", "Edge<2>"]})
            ```
        """
        input_data = normalize_input(input_data, AddChamferInput)
        result = await adapter.add_chamfer(input_data.distance, input_data.edge_names)
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
                "edges": input_data.edge_names,
            },
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def create_sweep(input_data: CreateSweepInput) -> dict[str, Any]:
        """Sweep the active profile sketch along a named path sketch.

        Creates a swept boss/protrusion (Insert > Boss/Base > Sweep). Requires
        two sketches in the active part: a closed profile sketch and an open
        path sketch named by ``path``. The profile is inferred as the sketch
        that is not the path (in the usual "draw profile, draw path, sweep"
        flow this is unambiguous). Optionally applies a constant twist along
        the path.

        Args:
            input_data (CreateSweepInput): Path name and twist/merge options.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Sweep a circular profile along "Sketch2"
            result = await create_sweep({"path": "Sketch2"})

            # Sweep with a 90-degree twist along the path
            result = await create_sweep({
                "path": "Sketch2",
                "twist_along_path": True,
                "twist_angle": 90.0,
            })
            ```
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
        """Loft a solid between two or more profile sketches.

        Creates a lofted boss/protrusion (Insert > Boss/Base > Loft) blending
        the listed profile sketches in order. Each profile must be a closed
        contour. Optional guide curves shape the transition between profiles.

        Args:
            input_data (CreateLoftInput): Profile names, optional guide curves,
                and tangency/merge options.

        Returns:
            dict[str, Any]: Status and feature details.

        Example:
            ```python
            # Loft between two profiles (e.g. a tapered bevel)
            result = await create_loft({"profiles": ["Sketch1", "Sketch2"]})

            # Loft with guide curves
            result = await create_loft({
                "profiles": ["Sketch1", "Sketch2"],
                "guide_curves": ["Sketch3"],
            })
            ```
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
        """Insert a part or sub-assembly into the active assembly.

        Call ``create_assembly`` first. Position is in millimetres from the
        assembly origin.

        **The component file must contain solid geometry** — SolidWorks
        silently refuses to insert an empty part, so a missing or empty
        component surfaces as an error rather than a fabricated success.

        Args:
            input_data (InsertComponentInput): File path and position.

        Returns:
            dict[str, Any]: Status, the component's instance name and counts.

        Example:
            ```python
            await create_assembly({"name": "bracket_asm"})
            await insert_component({"file_path": "C:/parts/plate.sldprt"})
            await insert_component({"file_path": "C:/parts/plate.sldprt", "x": 100.0})
            ```
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
        """Mate two components in the active assembly.

        Positions components relative to one another — coincident planes to
        stack or align them, concentric to line up axes, distance to hold a
        gap.

        Entities are selected by feature name, so only each component's
        reference planes and axes can be mated. Mating to a specific face or
        edge needs entity names this adapter cannot enumerate.

        Args:
            input_data (AddMateInput): Components, entities and mate type.

        Returns:
            dict[str, Any]: Status and mate details.

        Example:
            ```python
            components = await list_components()
            await add_mate({
                "component_a": components["components"][0],
                "component_b": components["components"][1],
                "mate_type": "coincident",
            })
            ```
        """
        input_data = normalize_input(input_data, AddMateInput)
        result = await adapter.add_mate(
            input_data.component_a,
            input_data.component_b,
            input_data.entity_a,
            input_data.entity_b,
            input_data.mate_type,
            input_data.alignment,
            input_data.distance,
            input_data.angle,
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
    async def list_components() -> dict[str, Any]:
        """List the top-level components of the active assembly.

        Returns:
            dict[str, Any]: Status and the component instance names.
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
        """Delete a feature or sketch from the active model.

        Deleting a parent feature also removes everything that depends on it —
        SolidWorks' normal cascade — so the response lists every feature that
        went, not just the one named.

        Args:
            input_data (DeleteFeatureInput): The feature to delete.

        Returns:
            dict[str, Any]: Status and what was removed.

        Example:
            ```python
            await delete_feature({"name": "Boss-Extrude1"})
            ```
        """
        input_data = normalize_input(input_data, DeleteFeatureInput)
        result = await adapter.delete_feature(input_data.name)
        require_success(result, context="Failed to delete feature")
        data = result.data if isinstance(result.data, dict) else {}
        removed = data.get("removed_features") or [input_data.name]
        return {
            "status": "success",
            "message": (
                f"Deleted {input_data.name}"
                + (
                    f" and {len(removed) - 1} dependent feature(s)"
                    if len(removed) > 1
                    else ""
                )
            ),
            "data": data,
            "execution_time": result.execution_time,
        }

    @mcp.tool()
    async def suppress_feature(input_data: SuppressFeatureInput) -> dict[str, Any]:
        """Suppress or unsuppress a feature in the active model.

        Suppressing rolls a feature and its children out of the model without
        deleting it — the reversible way to turn off a feature that is causing
        trouble.

        Args:
            input_data (SuppressFeatureInput): The feature and desired state.

        Returns:
            dict[str, Any]: Status and the resulting suppression state.

        Example:
            ```python
            await suppress_feature({"name": "Fillet1"})
            await suppress_feature({"name": "Fillet1", "suppress": False})
            ```
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
        """Rename a feature on the feature tree.

        SolidWorks silently refuses a rename onto a name another feature
        already uses, so the new name is read back and a mismatch is reported
        as an error rather than a quiet success. Renaming a feature to its
        current name is a no-op success.

        Args:
            input_data (RenameFeatureInput): The feature and its new name.

        Returns:
            dict[str, Any]: Status and the old and new names.

        Example:
            ```python
            await rename_feature({"old_name": "Fillet1", "new_name": "EdgeBreak"})
            ```
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
        """Select a named feature, sketch, plane or component.

        Replaces the current selection by default; pass ``append: true`` to
        add to it (e.g. to select several features in turn). A name that
        cannot be selected is an error, never a quiet success.

        Args:
            input_data (SelectFeatureInput): The feature name and append flag.

        Returns:
            dict[str, Any]: Status, the matched name and how many entities are
            now selected.

        Example:
            ```python
            await select_feature({"feature_name": "Boss-Extrude1"})
            await select_feature({"feature_name": "Sketch1", "append": True})
            ```
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
        """Select every edge of one face of the active part (multi-select).

        Identify the face with exactly one of ``point`` (a point on it, mm),
        ``side`` (``top``/``bottom``/``front``/``back``/``right``/``left`` or
        ``+X``..``-Z``; top=+Y, front=+Z, right=+X as in SolidWorks' default
        views - the furthest flat face facing that way) or ``plane`` (a
        reference plane name - the body face lying on it). ``edge_type``
        narrows to ``linear`` or ``circular`` edges (e.g. hole rims).

        The edges become the live SolidWorks selection, so the next
        ``add_chamfer`` / ``add_fillet`` call with an empty ``edge_names``
        acts on exactly them. Anything that changes the selection in between
        (including the user clicking in SolidWorks) changes what is used.

        Args:
            input_data (SelectFaceEdgesInput): Face identifier, edge filter and
                append flag.

        Returns:
            dict[str, Any]: Status plus ``data.face`` (centre, normal, area),
            ``data.edges`` (one entry per selected edge: curve type,
            endpoints/length or centre/radius) and ``data.selection_count``.

        Example:
            ```python
            # Chamfer the hole rims on the top face
            await select_face_edges({"side": "top", "edge_type": "circular"})
            await add_chamfer({"distance": 0.5, "edge_names": []})
            ```
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
        """Force a rebuild of the active model and report what is wrong.

        Use after programmatic edits (``set_dimension``, feature edits) to
        confirm the model rebuilds cleanly. When features fail, the response
        is an error whose ``data.errors`` names each failing feature with its
        SolidWorks error code, the features/sketches it depends on, and a
        concrete ``hint`` for fixing it. Warnings alone still succeed.

        Args:
            input_data (RebuildModelInput | None): ``top_level_only`` for
                assemblies; omit for a full rebuild.

        Returns:
            dict[str, Any]: Status, a one-line summary, and ``data`` with
            ``errors``, ``error_count`` and ``warning_count``.

        Example:
            ```python
            await rebuild_model()
            ```
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
        """Undo the last operations in the active model.

        SolidWorks accepts an undo with nothing left to undo without
        complaining, so the response reports whether the feature tree actually
        changed rather than assuming it did.

        Args:
            input_data (UndoInput | None): How many steps to undo.

        Returns:
            dict[str, Any]: Status and whether the tree changed.

        Example:
            ```python
            await undo({"count": 1})
            ```
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
        """Create a reference plane offset from an existing plane or planar face.

        Adds a new plane to the feature tree, parallel to and offset from the
        named reference. The returned plane name can be passed straight to
        ``create_sketch`` to sketch anywhere other than the six built-in
        planes.

        Angled planes are not supported by this tool: an angled plane needs a
        second reference (an axis or edge) to rotate about, which this
        signature cannot take. Use ``offset`` for parallel planes. An
        ``offset`` of zero is rejected — a plane coincident with its
        reference is not useful.

        Args:
            input_data (CreateReferencePlaneInput): Reference name, offset,
                angle and flip.

        Returns:
            dict[str, Any]: Status and the new plane's details.

        Example:
            ```python
            plane = await create_reference_plane(
                {"reference": "Front Plane", "offset": 76.2}
            )
            await create_sketch({"plane": plane["plane"]["name"]})
            ```
        """
        input_data = normalize_input(input_data, CreateReferencePlaneInput)
        result = await adapter.create_reference_plane(
            input_data.reference,
            input_data.offset,
            input_data.angle,
            input_data.flip,
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
        """Create a reference axis along a principal direction.

        Builds an axis from the intersection of two built-in planes: x from
        Top + Front, y from Front + Right, z from Top + Right.

        Args:
            input_data (CreateAxisInput): The principal direction ('x', 'y'
                or 'z').

        Returns:
            dict[str, Any]: Status and the axis details (planes used).

        Example:
            ```python
            result = await create_axis({"reference": "z"})
            ```
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
        """Create a reference point on the active part.

        Two modes:

        - ``along_curve`` — a point on the edge under ``(x, y, z)`` mm, placed
          ``distance`` mm from the edge start, or at ``percent`` (0–100) of
          its length. Give exactly one of ``distance`` / ``percent``.
        - ``face_center`` — a point at the centroid of the face under
          ``(x, y, z)`` mm.

        The coordinate must lie on the target edge/face; SolidWorks resolves
        it with a coordinate pick. ``InsertReferencePoint`` always returns a
        feature, so success is confirmed by the feature tree growing.

        Args:
            input_data (CreateReferencePointInput): Mode, coordinate, and the
                along-curve parameter.

        Returns:
            dict[str, Any]: Status and the point details (feature counts).

        Example:
            ```python
            await create_reference_point({
                "mode": "along_curve", "x": 25, "y": 0, "z": 10, "percent": 50
            })
            ```
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
        """Mirror solid bodies or features about a plane.

        Selects the named sources and the mirror plane, then mirrors them.
        The mirror is verified by comparing model volume before and after:
        SolidWorks can report a feature even when it mirrored nothing, so a
        volume that did not grow is reported as an error rather than a
        false success.

        Args:
            input_data (MirrorFeatureInput): Source names, mirror plane, and
                merge/mirror_bodies flags.

        Returns:
            dict[str, Any]: Status and the mirror feature's details,
            including volume before/after and the resulting ratio.

        Example:
            ```python
            result = await mirror_feature(
                {"features": ["Loft1"], "mirror_plane": "Right Plane"}
            )
            ```
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
        """Pattern features around an axis.

        Selects the named axis and features, then creates a circular
        pattern. The pattern is verified by comparing model volume before
        and after: SolidWorks can report a feature even when it patterned
        nothing, so a volume that did not grow is reported as an error
        rather than a false success.

        Args:
            input_data (PatternCircularInput): Feature names, axis, count,
                angle, and equal_spacing.

        Returns:
            dict[str, Any]: Status and the pattern's details, including
            volume before/after and the resulting ratio.

        Example:
            ```python
            result = await pattern_circular(
                {"features": ["Boss-Extrude1"], "axis": "Axis1", "count": 4}
            )
            ```
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
