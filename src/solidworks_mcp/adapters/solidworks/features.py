"""Feature-domain mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

import math
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

from .. import sw_type_info
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SolidWorksFeature,
    SweepParameters,
)
from .com_utils import as_list
from .com_utils import attempt as _attempt
from .com_utils import flag as _flag


class SolidWorksFeaturesMixin:
    """Expose SolidWorks feature methods via mixin-local implementation helpers."""

    async def create_extrusion(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        return _create_extrusion_impl(self, params)

    async def create_revolve(
        self, params: RevolveParameters
    ) -> AdapterResult[SolidWorksFeature]:
        return _create_revolve_impl(self, params)

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        return _create_sweep_impl(self, params)

    async def create_loft(
        self, params: LoftParameters
    ) -> AdapterResult[SolidWorksFeature]:
        return _create_loft_impl(self, params)

    async def create_cut_extrude(
        self, params: ExtrusionParameters
    ) -> AdapterResult[SolidWorksFeature]:
        return _create_cut_extrude_impl(self, params)

    async def add_fillet(
        self, radius: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        """Fillet edges, then confirm the model's volume actually changed.

        ``IModelDoc2.FeatureFillet3`` can report success without building
        anything, so besides the feature-count check inside
        :func:`_add_fillet_impl` the volume is compared before and after,
        here in the async layer for the same reason as ``mirror_feature``.
        An unreadable volume is not treated as failure.

        Args:
            radius: Fillet radius in millimetres.
            edge_names: Edge names, ``"x,y,z"`` points or ``"face:x,y,z"``
                specs; see :func:`_add_fillet_impl`.

        Returns:
            AdapterResult[SolidWorksFeature]: The fillet, with
            ``volume_before`` / ``volume_after`` in its properties when they
            could be read. ``ERROR`` when the volume did not change.
        """
        before = await self.get_mass_properties()
        volume_before = (
            before.data.volume if before.is_success and before.data else None
        )

        result = _add_fillet_impl(self, radius, edge_names)
        if not result.is_success or result.data is None or volume_before is None:
            return result

        after = await self.get_mass_properties()
        volume_after = after.data.volume if after.is_success and after.data else None
        if volume_after is None:
            return result
        if abs(volume_after - volume_before) <= 1e-7 * max(volume_before, 1.0):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"The fillet changed nothing (volume stayed at "
                    f"{volume_before:.3f} mm3). SolidWorks accepted the call "
                    "but filleted no edge; check that the specs name edges or "
                    "faces of the body."
                ),
            )
        result.data.properties["volume_before"] = volume_before
        result.data.properties["volume_after"] = volume_after
        return result

    async def add_chamfer(
        self, distance: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        return _add_chamfer_impl(self, distance, edge_names)

    async def delete_feature(self, name: str) -> AdapterResult[dict[str, Any]]:
        return _delete_feature_impl(self, name)

    async def suppress_feature(
        self, name: str, suppress: bool = True
    ) -> AdapterResult[dict[str, Any]]:
        return _suppress_feature_impl(self, name, suppress)

    async def rename_feature(
        self, old_name: str, new_name: str
    ) -> AdapterResult[dict[str, Any]]:
        """Rename a feature on the active model's tree.

        Args:
            old_name: The feature's current name.
            new_name: The name to give it.

        Returns:
            AdapterResult[dict[str, Any]]: Delegates to
            :func:`_rename_feature_impl`; see it for the payload shape.
        """
        return _rename_feature_impl(self, old_name, new_name)

    async def undo(self, count: int = 1) -> AdapterResult[dict[str, Any]]:
        return _undo_impl(self, count)

    async def create_reference_plane(
        self,
        reference: str,
        offset: float = 0.0,
        angle: float = 0.0,
        flip: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        return _create_reference_plane_impl(self, reference, offset, angle, flip)

    async def create_axis(self, reference: str) -> AdapterResult[dict[str, Any]]:
        return _create_axis_impl(self, reference)

    async def create_reference_point(
        self,
        mode: str,
        x: float,
        y: float,
        z: float,
        distance: float | None = None,
        percent: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Create a reference point on the active part.

        Args:
            mode: ``"along_curve"`` or ``"face_center"``.
            x: X of a point on the target edge/face, in millimetres.
            y: Y of a point on the target edge/face, in millimetres.
            z: Z of a point on the target edge/face, in millimetres.
            distance: For ``along_curve``, offset from the edge start in mm.
            percent: For ``along_curve``, position as 0-100 of edge length.

        Returns:
            AdapterResult[dict[str, Any]]: Delegates to
            :func:`_create_reference_point_impl`; see it for the payload shape.
        """
        return _create_reference_point_impl(self, mode, x, y, z, distance, percent)

    async def pattern_circular(
        self,
        features: list[str],
        axis: str,
        count: int,
        angle: float = 360.0,
        equal_spacing: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Pattern features around an axis.

        ``FeatureCircularPattern5`` returns a Feature object whether or not it
        produced anything, so the model volume is measured before and after
        here - in the async layer, using ``get_mass_properties``, which is the
        read path that works. Reading volume inline inside the COM closure
        returns ``None`` while a selection is active.

        Note that instances landing off the parent body are silently dropped
        by SolidWorks, so the volume rises by less than ``count - 1`` times the
        seed. That is correct behaviour, not a failure - only *no* growth at
        all means the pattern did nothing.

        Args:
            features: Names of the features to pattern.
            axis: Name of the axis to rotate about, e.g. ``"Axis1"`` from
                ``create_axis``.
            count: Total number of instances including the original.
            angle: Total angle in degrees to spread them over. Defaults to a
                full 360.
            equal_spacing: Space instances evenly across ``angle``.

        Returns:
            AdapterResult[dict[str, Any]]: What was patterned and the volume
            before and after. ``ERROR`` when nothing could be selected or the
            volume did not grow.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        before = await self.get_mass_properties()
        volume_before = (
            before.data.volume if before.is_success and before.data else None
        )

        result = _pattern_circular_impl(
            self, features, axis, count, angle, equal_spacing
        )
        if not result.is_success:
            return result

        after = await self.get_mass_properties()
        volume_after = after.data.volume if after.is_success and after.data else None

        if volume_before is None or volume_after is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "The pattern call returned a feature but the volume could "
                    "not be read before and after, so whether any instances "
                    "were created is unknown."
                ),
            )
        if volume_after <= volume_before * 1.0001:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"The circular pattern produced no geometry (volume "
                    f"{volume_before:.1f} -> {volume_after:.1f} mm3). "
                    f"SolidWorks returned a feature but patterned nothing. "
                    f"Check that '{axis}' is a real axis in the tree and that "
                    f"the instances land on the parent body."
                ),
            )

        data = dict(result.data or {})
        data["volume_before"] = volume_before
        data["volume_after"] = volume_after
        data["volume_ratio"] = round(volume_after / volume_before, 6)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=data,
            execution_time=result.execution_time,
        )

    async def mirror_feature(
        self,
        features: list[str],
        mirror_plane: str,
        merge: bool = True,
        mirror_bodies: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Mirror solid bodies or features about a plane.

        ``InsertMirrorFeature`` returns a Feature object even when it mirrored
        nothing, so the model's volume is measured before and after and the
        call is reported as failed if the volume did not grow. That check runs
        here rather than inside the COM closure because ``get_mass_properties``
        is the read path known to work - reading ``CreateMassProperty().Volume``
        inline returns ``None`` when a plane is still in the selection set,
        which silently disables the check.

        Args:
            features: Names of the bodies (or features) to mirror. For a body
                mirror these are the names as they appear under Solid Bodies,
                which for a lofted wing is the loft's own name.
            mirror_plane: Plane to mirror about, e.g. ``"Right Plane"``.
            merge: Merge the mirrored result with the original.
            mirror_bodies: Mirror whole solid bodies rather than features.
                Defaults to ``True``, which is what works for anything built
                from a loft or sweep: SolidWorks only resolves a *feature*
                mirror when the feature's own sketch sits on the mirror plane,
                so a wing lofted between stations offset from the centreline
                cannot be feature-mirrored. Measured on SW 2025: body mirroring
                a 1819569 mm^3 wing about the Right Plane gave 3636460 mm^3.

        Returns:
            AdapterResult[dict[str, Any]]: What was mirrored, and the volume
            before and after. ``ERROR`` when nothing was selected, the call
            failed, or the volume did not grow.
        """
        adapter = self._adapter(self)
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        before = await self.get_mass_properties()
        volume_before = (
            before.data.volume if before.is_success and before.data else None
        )

        result = _mirror_feature_impl(
            self, features, mirror_plane, merge, mirror_bodies
        )
        if not result.is_success:
            return result

        after = await self.get_mass_properties()
        volume_after = after.data.volume if after.is_success and after.data else None

        if volume_before is None or volume_after is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    "The mirror call returned a feature but the volume could "
                    "not be read before and after, so whether any geometry was "
                    "produced is unknown."
                ),
            )
        if volume_after <= volume_before * 1.001:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"The mirror produced no new geometry (volume "
                    f"{volume_before:.1f} -> {volume_after:.1f} mm3). "
                    "SolidWorks returned a feature but mirrored nothing. With "
                    "mirror_bodies=False this happens whenever the feature's "
                    "own sketch does not sit on the mirror plane; try "
                    "mirror_bodies=True to mirror the solid body instead."
                ),
            )

        data = dict(result.data or {})
        data["volume_before"] = volume_before
        data["volume_after"] = volume_after
        data["volume_ratio"] = round(volume_after / volume_before, 6)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=data,
            execution_time=result.execution_time,
        )


#: ``end_condition`` spellings accepted by ``create_extrusion``, keyed by the
#: name with case, spaces, ``_`` and ``-`` removed.
_EXTRUSION_END_CONDITIONS = {
    "blind": ("Blind", "swEndCondBlind"),
    "midplane": ("MidPlane", "swEndCondMidPlane"),
    "throughall": ("ThroughAll", "swEndCondThroughAll"),
    "uptonext": ("UpToNext", "swEndCondUpToNext"),
}


def _extrusion_end_condition(
    adapter: Any, end_condition: str, both_directions: bool
) -> tuple[str, int]:
    """Resolve a boss extrusion's first-direction end condition.

    ``both_directions=True`` means mid-plane whatever ``end_condition`` says,
    which is what the thin-wall branch always did. Before this was shared,
    the solid branch passed ``swEndCondBlind`` unconditionally, so a
    "both directions" extrusion silently came out one-sided.

    Args:
        adapter: Adapter whose ``constants`` hold the ``swEndCond*`` values.
        end_condition: Requested condition, e.g. ``"Blind"`` or ``"Mid Plane"``.
        both_directions: Extrude symmetrically about the sketch plane.

    Returns:
        tuple[str, int]: The canonical name and its ``swEndCondition_e`` value.

    Raises:
        ValueError: When ``end_condition`` is not one this call supports.
    """
    if both_directions:
        key = "midplane"
    else:
        key = "".join(c for c in end_condition.lower() if c not in " _-") or "blind"
    if key not in _EXTRUSION_END_CONDITIONS:
        supported = ", ".join(name for name, _ in _EXTRUSION_END_CONDITIONS.values())
        raise ValueError(
            f"Unsupported extrusion end_condition {end_condition!r}; "
            f"use one of: {supported}"
        )
    name, constant = _EXTRUSION_END_CONDITIONS[key]
    return name, adapter.constants[constant]


def _create_extrusion_impl(
    adapter: Any, params: ExtrusionParameters
) -> AdapterResult[SolidWorksFeature]:
    """Create a boss-extrude feature from the active sketch profile.

    Attempts the modern ``FeatureExtrusion3`` COM call first; falls back to the
    legacy ``FeatureExtrusion2`` signature when the newer overload is absent.
    When ``params.thin_feature`` is truthy, the thin-wall variants
    (``FeatureExtrusionThin2`` / ``FeatureExtruThin2``) are used instead.

    All depth and thickness values are provided in millimetres and converted
    to metres internally.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` instance.  Must have a
            non-``None`` ``currentModel`` and a valid ``FeatureManager``.
        params: Extrusion parameter bag.  Relevant fields:
            - ``depth`` (float): Extrude depth in mm.
            - ``draft_angle`` (float): Draft angle in degrees.  Default 0.
            - ``reverse_direction`` (bool): Flip the extrusion direction.
            - ``thin_feature`` (bool): Produce a thin-wall body.
            - ``thin_thickness`` (float | None): Wall thickness in mm when
              ``thin_feature`` is ``True``.
            - ``merge_result`` (bool): Merge with existing bodies.  Default
              ``True``.
            - ``both_directions`` (bool): Extrude symmetrically in both
              directions from the sketch plane (mid-plane): ``depth`` is the
              total thickness, half on each side.
            - ``end_condition`` (str): ``"Blind"`` (default), ``"MidPlane"``,
              ``"ThroughAll"`` or ``"UpToNext"`` - see
              :func:`_extrusion_end_condition`.
            - ``auto_fillet_corners`` (bool): Round sharp thin-wall corners.
            - ``fillet_corners_radius`` (float): Corner fillet radius in mm.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Extrusion"``.  On failure,
        ``status`` is ``ERROR`` and ``error`` contains a descriptive message.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the COM
            call returns ``None`` for the created feature object.

    Example::

        from solidworks_mcp.adapters.base import ExtrusionParameters
        from solidworks_mcp.adapters import pywin32_feature_ops

        params = ExtrusionParameters(depth=25.0, draft_angle=2.0)
        result = pywin32_feature_ops.create_extrusion(adapter, params)
        print(result.data.name)  # e.g. "Boss-Extrude1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _extrusion_operation() -> SolidWorksFeature:
        """Inner COM closure that builds and returns the extrusion feature.

        Normalises ``params`` into a ``SimpleNamespace`` so every attribute
        access is guaranteed safe regardless of the dataclass version.  Picks
        the thin-wall or solid branch, then tries the modern API first before
        falling back to the legacy one.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: If both API variants return ``None``.
        """
        normalized = SimpleNamespace(
            depth=float(getattr(params, "depth", 0.0)),
            draft_angle=float(getattr(params, "draft_angle", 0.0)),
            reverse_direction=bool(getattr(params, "reverse_direction", False)),
            thin_feature=bool(getattr(params, "thin_feature", False)),
            thin_thickness=getattr(params, "thin_thickness", None),
            merge_result=bool(getattr(params, "merge_result", True)),
            both_directions=bool(getattr(params, "both_directions", False)),
            auto_fillet_corners=bool(getattr(params, "auto_fillet_corners", False)),
            fillet_corners_radius=float(getattr(params, "fillet_corners_radius", 0.0)),
        )
        feature_manager = adapter.currentModel.FeatureManager
        t0 = adapter.constants.get("swStartSketchPlane", 0)
        end_name, t1 = _extrusion_end_condition(
            adapter,
            str(getattr(params, "end_condition", "Blind") or "Blind"),
            normalized.both_directions,
        )

        if normalized.thin_feature and normalized.thin_thickness:
            try:
                feature = feature_manager.FeatureExtrusionThin2(
                    True,
                    False,
                    normalized.reverse_direction,
                    t1,
                    adapter.constants["swEndCondBlind"],
                    normalized.depth / 1000.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.draft_angle * 3.14159 / 180.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.merge_result,
                    normalized.thin_thickness / 1000.0,
                    normalized.thin_thickness / 1000.0,
                    0.0,
                    0,
                    0,
                    normalized.auto_fillet_corners,
                    normalized.fillet_corners_radius / 1000.0,
                    False,
                    True,
                    t0,
                    0.0,
                    False,
                )
            except Exception:
                feature = feature_manager.FeatureExtruThin2(
                    normalized.depth / 1000.0,
                    0.0,
                    False,
                    normalized.draft_angle * 3.14159 / 180.0,
                    0.0,
                    False,
                    False,
                    normalized.merge_result,
                    False,
                    True,
                    normalized.thin_thickness / 1000.0,
                    normalized.thin_thickness / 1000.0,
                    False,
                    False,
                    False,
                    adapter.constants["swEndCondBlind"],
                    adapter.constants["swEndCondBlind"],
                )
        else:
            try:
                feature = feature_manager.FeatureExtrusion3(
                    True,
                    False,
                    normalized.reverse_direction,
                    t1,
                    adapter.constants["swEndCondBlind"],
                    normalized.depth / 1000.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.draft_angle * 3.14159 / 180.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.merge_result,
                    False,
                    True,
                    t0,
                    0.0,
                    False,
                )
            except Exception:
                feature = feature_manager.FeatureExtrusion2(
                    True,
                    False,
                    normalized.reverse_direction,
                    t1,
                    adapter.constants["swEndCondBlind"],
                    normalized.depth / 1000.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.draft_angle * 3.14159 / 180.0,
                    0.0,
                    False,
                    False,
                    False,
                    False,
                    normalized.merge_result,
                    False,
                    True,
                    t0,
                    0.0,
                    False,
                )

        if not feature:
            raise Exception("Failed to create extrusion feature")

        return SolidWorksFeature(
            name=feature.Name,
            type="Extrusion",
            id=adapter._get_feature_id(feature),
            parameters={
                "depth": normalized.depth,
                "draft_angle": normalized.draft_angle,
                "reverse_direction": normalized.reverse_direction,
                "thin_feature": normalized.thin_feature,
                "thin_thickness": normalized.thin_thickness,
                "end_condition": end_name,
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_extrusion", _extrusion_operation),
    )


def _create_revolve_impl(
    adapter: Any, params: RevolveParameters
) -> AdapterResult[SolidWorksFeature]:
    """Create a revolve feature from the active sketch profile around a centre axis.

    Uses ``FeatureRevolve2`` from the SolidWorks COM API.  The sketch must
    already contain a centre-line that SolidWorks will use as the rotation axis.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        params: Revolve parameter bag.  Relevant fields:
            - ``angle`` (float): Revolve angle in degrees.  Use 360 for a
              full revolution.
            - ``reverse_direction`` (bool): Flip the revolve direction.
            - ``both_directions`` (bool): Revolve symmetrically in both
              directions.
            - ``thin_feature`` (bool): Produce a thin-wall body.
            - ``thin_thickness`` (float | None): Wall thickness in mm.
            - ``merge_result`` (bool): Merge with existing bodies.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Revolve"``.  On failure,
        ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when
            ``FeatureRevolve2`` returns ``None``.

    Example::

        from solidworks_mcp.adapters.base import RevolveParameters
        from solidworks_mcp.adapters import pywin32_feature_ops

        params = RevolveParameters(angle=360.0, merge_result=True)
        result = pywin32_feature_ops.create_revolve(adapter, params)
        print(result.data.name)  # e.g. "Revolve1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _revolve_operation() -> SolidWorksFeature:
        """Inner COM closure that builds and returns the revolve feature.

        Converts the degree angle to radians and invokes ``FeatureRevolve2``.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: If ``FeatureRevolve2`` returns ``None``.
        """
        # Detect SW major version for FeatureRevolve2 API choice
        revolve_sw_major = 0
        if getattr(adapter, "swApp", None):
            rev = adapter._attempt(
                lambda: adapter._get_attr_or_call(adapter.swApp, "RevisionNumber"),
                default="0",
            )
            try:
                revolve_sw_major = int(str(rev).split(".")[0])
            except (ValueError, IndexError):
                revolve_sw_major = 0

        import math

        if revolve_sw_major == 33:
            # IFeatureManager.FeatureRevolve2 - exact 20-parameter signature
            # read from the live gen_py type library for SW 2025:
            #   SingleDir, IsSolid, IsThin, IsCut, ReverseDir,
            #   BothDirectionUpToSameEntity, Dir1Type, Dir2Type,
            #   Dir1Angle(rad), Dir2Angle(rad), OffsetReverse1, OffsetReverse2,
            #   OffsetDistance1, OffsetDistance2, ThinType,
            #   ThinThickness1(m), ThinThickness2(m), Merge,
            #   UseFeatScope, UseAutoSelect
            # This call passed 19 arguments and put Merge where ThinType
            # belongs, so SolidWorks rejected every revolve with
            # "Parameter not optional".
            feature_manager = adapter.currentModel.FeatureManager
            is_thin = bool(params.thin_feature and params.thin_thickness)
            feature = feature_manager.FeatureRevolve2(
                not params.both_directions,  # SingleDir
                True,  # IsSolid
                is_thin,  # IsThin
                False,  # IsCut
                params.reverse_direction,  # ReverseDir
                False,  # BothDirectionUpToSameEntity
                0,  # Dir1Type (swEndCondBlind)
                0,  # Dir2Type
                params.angle * math.pi / 180.0,  # Dir1Angle (rad)
                (params.angle * math.pi / 180.0)
                if params.both_directions
                else 0.0,  # Dir2Angle
                False,  # OffsetReverse1
                False,  # OffsetReverse2
                0.0,  # OffsetDistance1
                0.0,  # OffsetDistance2
                0,  # ThinType
                (params.thin_thickness or 0.0) / 1000.0,  # ThinThickness1
                0.0,  # ThinThickness2
                params.merge_result,  # Merge
                False,  # UseFeatScope
                True,  # UseAutoSelect
            )
        else:
            feature_manager = adapter.currentModel.FeatureManager
            feature = feature_manager.FeatureRevolve2(
                not params.both_directions,
                True,
                params.thin_feature,
                False,
                params.reverse_direction,
                False,
                adapter.constants["swEndCondBlind"],
                adapter.constants["swEndCondBlind"],
                math.radians(params.angle),
                math.radians(params.angle) if params.both_directions else 0.0,
                False,
                False,
                0.0,
                0.0,
                0,
                (params.thin_thickness or 0.0) / 1000.0,
                0.0,
                params.merge_result,
                False,
                True,
            )

        # IModelDoc2.FeatureRevolve2 returns None (void) on SW 2025
        if not feature and revolve_sw_major != 33:
            raise Exception("Failed to create revolve feature")

        return SolidWorksFeature(
            name=feature.Name if feature else "Revolve-Auto",
            type="Revolve",
            id=adapter._get_feature_id(feature) if feature else "revolve_auto",
            parameters={
                "angle": params.angle,
                "reverse_direction": params.reverse_direction,
                "both_directions": params.both_directions,
                "thin_feature": params.thin_feature,
                "thin_thickness": params.thin_thickness,
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_revolve", _revolve_operation),
    )


def _select_named_feature(
    adapter: Any,
    name: str,
    mark: int,
    append: bool,
) -> bool:
    """Select a named feature under a specific selection mark via ``Select2``.

    Sweep and loft rely on selection marks to tell SolidWorks which selection
    is the profile (1), guide curve (2), or sweep path (4).  We resolve the
    feature with ``IModelDoc2::FeatureByName`` and select it with
    ``IFeature::Select2(append, mark)`` — the same proven path the rest of the
    adapter uses for plane/sketch selection.  ``IModelDocExtension::SelectByID2``
    is avoided deliberately: late-bound ``SelectByID2`` raises
    ``Type mismatch`` on some SolidWorks builds, whereas ``FeatureByName`` +
    ``Select2`` is reliable, works for sketches *and* reference curves such as
    a helix, and needs no entity-type string.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        name: Feature name (e.g. ``"Sketch1"`` or ``"Helix/Spiral1"``).  Any
            ``@document`` qualifier is stripped before lookup.
        mark: Selection mark — 1=profile, 2=guide curve, 4=sweep path.
        append: ``True`` to add to the current selection set, ``False`` to
            replace it.

    Returns:
        bool: ``True`` when the feature was found and selected.
    """
    bare = name.split("@", 1)[0]
    feature = adapter._attempt(
        lambda: adapter.currentModel.FeatureByName(bare), default=None
    )
    if not feature:
        return False
    return bool(adapter._attempt(lambda: feature.Select2(append, mark), default=False))


def _flag_feature_methods(obj: Any, interface: str) -> None:
    """Best-effort method flagging for a COM object via ``sw_type_info``.

    Flagging tells pywin32 late binding to resolve names like ``GetTypeName2``
    / ``GetNextFeature`` / ``FirstFeature`` as methods.  No-ops on plain test
    doubles (and any environment without the gen_py wrapper).

    Args:
        obj: The COM object (or test double) to flag.
        interface: SolidWorks interface name (e.g. ``"IFeature"``).
    """
    sw_type_info.flag_methods(obj, interface)


def _flag_feature_members(obj: Any, *names: str) -> None:
    """Flag only the named members on ``obj``.

    Cheaper than :func:`_flag_feature_methods` inside a loop: flagging a
    whole interface (``IFeature`` is ~100 names, ~27 ms) costs a fixed price
    per object, and ``sw_type_info``'s flag cache is keyed by ``id(obj)``, so
    a walk over fresh dispatches — one per feature — never hits it. Flagging
    just the handful of members about to be read avoids that cost.

    Args:
        obj: The COM object (or test double) to flag.
        *names: Member names about to be read.
    """
    sw_type_info.flag_members(obj, *names)


#: Members read while walking the feature tree in ``_profile_feature_names``.
_TREE_WALK_MEMBERS = ("GetTypeName2", "GetNextFeature", "Name")


def _read_member(obj: Any, name: str) -> Any:
    """Read a COM member that pywin32 may expose as a property *or* a method.

    Late-bound pywin32 dispatches are inconsistent: an unflagged zero-arg
    accessor may come back as a bound method (needing a call) *or* as the
    already-resolved value — and when that value is itself a COM object it is
    also callable, so a naive "call if callable" check wrongly invokes its
    default dispatch (``Member not found``).  This helper calls the member and
    falls back to the raw member if the call raises, so it yields the value in
    every case (flagged method, unflagged method, property-returning-object,
    or plain test double).

    Args:
        obj: The COM object (or test double) to read from.
        name: Member name.

    Returns:
        Any: The member's value, or ``None`` when the attribute is absent.
    """
    member = getattr(obj, name, None)
    if not callable(member):
        return member
    try:
        return member()
    except Exception:
        return member


def _profile_feature_names(adapter: Any) -> list[str]:
    """Return sketch (``ProfileFeature``) names in feature-tree order.

    Walks ``FirstFeature`` -> ``GetNextFeature`` reading ``GetTypeName2`` and
    collecting features whose type is ``"ProfileFeature"`` (a 2D/3D sketch).
    Mirrors the tree walk used by :func:`_create_cut_extrude_impl`, but flags
    each feature for ``IFeature`` and reads members through
    :func:`_read_member` so it is robust to pywin32's method-vs-property
    late-binding ambiguity.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.

    Returns:
        list[str]: Bare sketch names, earliest first.  Empty when the walk
        finds no sketches or the tree is inaccessible.
    """
    names: list[str] = []
    try:
        _flag_feature_methods(adapter.currentModel, "IModelDoc2")
        feat = _read_member(adapter.currentModel, "FirstFeature")
        # Bound the walk so a misbehaving GetNextFeature can't spin forever.
        for _ in range(5000):
            if not feat:
                break
            _flag_feature_members(feat, *_TREE_WALK_MEMBERS)
            try:
                if _read_member(feat, "GetTypeName2") == "ProfileFeature":
                    names.append(str(_read_member(feat, "Name")))
            except Exception:
                pass
            try:
                feat = _read_member(feat, "GetNextFeature")
            except Exception:
                break
    except Exception:
        pass
    return names


def _create_sweep_impl(
    adapter: Any, params: SweepParameters
) -> AdapterResult[SolidWorksFeature]:
    """Create a swept boss/protrusion from a profile sketch along a path sketch.

    Uses ``IFeatureManager::InsertProtrusionSwept4``.  Two sketches are
    required in the active part: a closed **profile** sketch and an open
    **path** sketch named by ``params.path``.  The path is selected under
    mark 4 and the profile under mark 1, per the SolidWorks selection-mark
    contract for sweeps.

    Because :class:`SweepParameters` only names the path, the profile is
    inferred as the first ``ProfileFeature`` sketch in the feature tree whose
    name is **not** the path.  In the common "draw profile, draw path, sweep"
    workflow this is unambiguous (exactly two sketches exist).

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        params: Sweep parameter bag.  Relevant fields:
            - ``path`` (str): Name of the path sketch (e.g. ``"Sketch2"``).
            - ``twist_along_path`` (bool): Apply a constant twist along the
              path.
            - ``twist_angle`` (float): Twist angle in **degrees** (used only
              when ``twist_along_path`` is true).
            - ``merge_result`` (bool): Merge with existing bodies.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Sweep"``.  On failure,
        ``status`` is ``ERROR`` with a descriptive message.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when the
            profile/path cannot be selected or the COM call returns ``None``.

    Example::

        from solidworks_mcp.adapters.base import SweepParameters

        params = SweepParameters(path="Sketch2", merge_result=True)
        result = await adapter.create_sweep(params)
        print(result.data.name)  # e.g. "Sweep1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    if not getattr(params, "path", None):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Sweep requires a 'path' sketch name",
        )

    def _sweep_operation() -> SolidWorksFeature:
        """Inner COM closure that selects profile + path and runs the sweep.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: When selections fail or ``InsertProtrusionSwept4``
                returns ``None``.
        """
        import math

        feature_manager = adapter.currentModel.FeatureManager

        # Resolve the path name against the actual tree sketches so the
        # profile/path comparison is on bare names, then pick the first
        # non-path sketch as the profile.
        sketch_names = _profile_feature_names(adapter)
        path_name = params.path
        for name in sketch_names:
            if name == params.path or name.lower() == params.path.lower():
                path_name = name
                break

        # Profile = the most recently created sketch that isn't the path.
        # Preferring the latest sketch handles both a sketch path (profile is
        # drawn first, so it's the only non-path sketch) and a helix/curve
        # path (the helix's base-circle sketch precedes the profile in the
        # tree, so "first non-path" would wrongly pick the base circle).
        profile_name = None
        last = getattr(adapter, "_last_sketch_name", None)
        if last and last != path_name and last in sketch_names:
            profile_name = last
        if profile_name is None:
            profile_name = next(
                (name for name in reversed(sketch_names) if name != path_name), None
            )
        if profile_name is None:
            raise Exception(
                "Sweep needs a profile sketch distinct from the path "
                f"'{params.path}'. Sketches found: {sketch_names or 'none'}"
            )

        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        if not _select_named_feature(adapter, profile_name, 1, False):
            raise Exception(f"Failed to select sweep profile sketch: {profile_name}")
        if not _select_named_feature(adapter, path_name, 4, True):
            raise Exception(f"Failed to select sweep path: {path_name}")

        twist = bool(getattr(params, "twist_along_path", False))
        twist_angle_deg = float(getattr(params, "twist_angle", 0.0))
        # swTwistControlType_e: 0 = follow path, 8 = constant twist along path.
        twist_ctrl = 8 if twist else 0
        twist_angle_rad = math.radians(twist_angle_deg) if twist else 0.0

        feature = feature_manager.InsertProtrusionSwept4(
            False,  # Propagate to next tangent edge
            False,  # Alignment (go through end faces)
            twist_ctrl,  # TwistCtrlOption (swTwistControlType_e)
            False,  # KeepTangency
            False,  # BAdvancedSmoothing
            0,  # StartMatchingType (swTangencyType_e)
            0,  # EndMatchingType
            False,  # IsThinBody
            0.0,  # Thickness1
            0.0,  # Thickness2
            0,  # ThinType (swThinWallType_e)
            0,  # PathAlign
            bool(getattr(params, "merge_result", True)),  # Merge
            True,  # UseFeatScope
            True,  # UseAutoSelect
            twist_angle_rad,  # TwistAngle (radians)
            True,  # BMergeSmoothFaces
            False,  # CircularProfile
            0.0,  # CircularProfileDiameter
            0,  # Direction
        )

        if not feature:
            raise Exception("Failed to create sweep feature")

        return SolidWorksFeature(
            name=feature.Name,
            type="Sweep",
            id=adapter._get_feature_id(feature),
            parameters={
                "profile": profile_name,
                "path": path_name,
                "twist_along_path": twist,
                "twist_angle": twist_angle_deg,
                "merge_result": bool(getattr(params, "merge_result", True)),
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_sweep", _sweep_operation),
    )


def _create_loft_impl(
    adapter: Any, params: LoftParameters
) -> AdapterResult[SolidWorksFeature]:
    """Create a lofted boss/protrusion between two or more profile sketches.

    Uses ``IFeatureManager::InsertProtrusionBlend2``.  Each profile named in
    ``params.profiles`` is selected under mark 1 (in order — the selection
    order determines the loft direction), and any ``params.guide_curves`` are
    selected under mark 2.  Because a solid is produced, every profile must be
    a closed contour.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        params: Loft parameter bag.  Relevant fields:
            - ``profiles`` (list[str]): Ordered profile sketch names; at least
              two are required.
            - ``guide_curves`` (list[str] | None): Optional guide curve names.
            - ``start_tangent`` / ``end_tangent`` (str | None): ``"normal"``
              tangency at the start/end profile, anything else / ``None`` ->
              no tangency.
            - ``merge_result`` (bool): Merge with existing bodies.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Loft"``.  On failure,
        ``status`` is ``ERROR`` with a descriptive message.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when a profile
            cannot be selected or the COM call returns ``None``.

    Example::

        from solidworks_mcp.adapters.base import LoftParameters

        params = LoftParameters(profiles=["Sketch1", "Sketch2"])
        result = await adapter.create_loft(params)
        print(result.data.name)  # e.g. "Loft1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    profiles = list(getattr(params, "profiles", None) or [])
    if len(profiles) < 2:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="Loft requires at least 2 profile sketches",
        )

    def _loft_operation() -> SolidWorksFeature:
        """Inner COM closure that selects profiles/guides and runs the loft.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: When a profile selection fails or
                ``InsertProtrusionBlend2`` returns ``None``.
        """
        guide_curves = list(getattr(params, "guide_curves", None) or [])

        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        # Profiles under mark 1, in order. First replaces the selection set,
        # the rest append so SW sees them as an ordered profile group.
        for index, profile in enumerate(profiles):
            if not _select_named_feature(adapter, profile, 1, append=index > 0):
                raise Exception(f"Failed to select loft profile sketch: {profile}")

        # Optional guide curves under mark 2 (a sketch or a reference curve).
        for guide in guide_curves:
            if not _select_named_feature(adapter, guide, 2, append=True):
                raise Exception(f"Failed to select loft guide curve: {guide}")

        # swTangencyType_e: 0 = none, 1 = tangent to profile normal.
        def _tangency(value: str | None) -> int:
            return 1 if str(value or "").strip().lower() == "normal" else 0

        start_match = _tangency(getattr(params, "start_tangent", None))
        end_match = _tangency(getattr(params, "end_tangent", None))

        feature_manager = adapter.currentModel.FeatureManager
        feature = feature_manager.InsertProtrusionBlend2(
            False,  # Closed loft
            True,  # KeepTangency
            False,  # ForceNonRational
            1.0,  # TessToleranceFactor
            start_match,  # StartMatchingType (swTangencyType_e)
            end_match,  # EndMatchingType
            1.0,  # StartTangentLength
            1.0,  # EndTangentLength
            True,  # StartTangentDir
            True,  # EndTangentDir
            False,  # IsThinBody
            0.0,  # Thickness1
            0.0,  # Thickness2
            0,  # ThinType
            bool(getattr(params, "merge_result", True)),  # Merge
            True,  # UseFeatScope
            True,  # UseAutoSelect
            2,  # GuideCurveInfluence (swGuideCurveInfluenceNextEdge)
        )

        if not feature:
            raise Exception("Failed to create loft feature")

        return SolidWorksFeature(
            name=feature.Name,
            type="Loft",
            id=adapter._get_feature_id(feature),
            parameters={
                "profiles": profiles,
                "guide_curves": guide_curves or None,
                "start_tangent": getattr(params, "start_tangent", None),
                "end_tangent": getattr(params, "end_tangent", None),
                "merge_result": bool(getattr(params, "merge_result", True)),
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_loft", _loft_operation),
    )


def _create_cut_extrude_impl(
    adapter: Any, params: ExtrusionParameters
) -> AdapterResult[SolidWorksFeature]:
    """Create a cut-extrude feature from an explicit or unambiguously-tracked sketch.

    Sketch resolution never guesses:

    1. ``params.sketch_name``, if given, is matched (case-insensitively)
       against the live feature tree via :func:`_profile_feature_names`. No
       match -> immediate error listing the sketches that do exist. No COM
       cut is attempted.
    2. Otherwise, ``adapter._last_sketch_name`` (set by the most recent
       ``create_sketch``/``exit_sketch`` call in this session) is used only
       if it also matches a real name in the current tree — this catches the
       case where ``create_sketch`` had to fall back to a synthetic
       ``Sketch_N`` guess (SolidWorks didn't hand back a usable sketch object
       synchronously) and that guess doesn't correspond to anything real.
    3. Otherwise: immediate error asking the caller to pass ``sketch_name``
       explicitly, listing available sketches. There is no third guess (no
       "most recent ``ProfileFeature`` in the tree", no blind ``Sketch<N>``
       enumeration) — a wrong silent guess would cut the wrong profile.

    Once resolved, the sketch is explicitly selected via ``SelectByID2``
    *before* any ``FeatureCut`` call — SolidWorks' own "implicit" active-sketch
    state (whatever was last open before this call) is never relied upon,
    since that is exactly the racy behavior that made this feature
    intermittently cut nothing.

    Two COM API variants are attempted in order of preference:

    1. ``FeatureCut4`` — most modern (SolidWorks 2015+).
    2. ``FeatureCut3`` — SolidWorks 2010–2014, and any install lacking
       ``FeatureCut4``. Same 26-parameter order as ``FeatureCut4`` minus the
       trailing ``OptimizeGeometry`` argument (confirmed against SolidWorks
       API help and live macro examples — there is no separate "legacy"
       argument order; an earlier version of this fallback invented one and
       it always raised ``DISP_E_PARAMNOTOPTIONAL`` because it was missing
       the ``NormalCut`` argument and had ``D2`` missing entirely).

    All depth values are in millimetres and converted to metres internally.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        params: Extrusion parameter bag reused for cut parameters:
            - ``depth`` (float): Cut depth in mm.
            - ``draft_angle`` (float): Draft angle in degrees.
            - ``reverse_direction`` (bool): Flip the cut direction. A
              one-direction cut whose requested direction finds no material
              is retried the other way; ``parameters.direction_flipped``
              says so.
            - ``end_condition`` (str): ``"Blind"`` (default),
              ``"ThroughAll"`` / ``"through_all"``, or ``"ThroughAllBoth"`` /
              ``"through_all_both"`` (through all in both directions, cut as a
              double-ended Through All feature).
            - ``both_directions`` (bool): With ``"ThroughAll"``, cut through
              all in both directions (same as ``"ThroughAllBoth"``).
            - ``feature_scope`` (bool): Limit cut to selected bodies.
            - ``auto_select`` (bool): Auto-select bodies in scope.
            - ``sketch_name`` (str | None): Sketch to cut from. See sketch
              resolution above.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Cut-Extrude"``.  On
        failure, ``status`` is ``ERROR`` and ``error`` explains exactly
        which stage failed: sketch-not-found (with the list of sketches that
        do exist), sketch-selection-failed (the resolved name plus why
        ``SelectByID2`` was rejected), or every ``FeatureCut`` COM variant's
        own error text — and, when every COM call returned falsy without
        raising at all, an explicit note that the profile likely isn't a
        valid closed loop intersecting solid geometry, rather than a bare
        "failed" with no diagnostic content.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` for every
            failure stage described above.

    Example::

        from solidworks_mcp.adapters.base import ExtrusionParameters
        from solidworks_mcp.adapters import pywin32_feature_ops

        params = ExtrusionParameters(depth=10.0, end_condition="ThroughAll")
        result = pywin32_feature_ops.create_cut_extrude(adapter, params)
        print(result.data.name)  # e.g. "Cut-Extrude1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _cut_operation() -> SolidWorksFeature:
        """Inner COM closure that locates the active sketch and performs the cut.

        Normalises ``params``, selects the sketch profile, then tries each
        end-condition form against ``FeatureCut4`` and then ``FeatureCut3``.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: When all COM cut variants return ``None``.
        """
        normalized = SimpleNamespace(
            depth=float(getattr(params, "depth", 0.0)),
            draft_angle=float(getattr(params, "draft_angle", 0.0)),
            reverse_direction=bool(getattr(params, "reverse_direction", False)),
            end_condition=str(getattr(params, "end_condition", "Blind")),
            both_directions=bool(getattr(params, "both_directions", False)),
            feature_scope=bool(getattr(params, "feature_scope", False)),
            auto_select=bool(getattr(params, "auto_select", True)),
            sketch_name=getattr(params, "sketch_name", None) or None,
        )
        feature_manager = adapter.currentModel.FeatureManager

        # --- Sketch resolution: explicit > tracked-and-verified > clear
        # error. Never a silent guess — see the docstring above. Resolving
        # this up front (before any FeatureCut attempt) also lets every
        # failure below name the sketch it was actually targeting.
        tree_names = _profile_feature_names(adapter)

        def _match_tree_name(name: str) -> str | None:
            for real in tree_names:
                if real.lower() == name.lower():
                    return real
            return None

        available = ", ".join(tree_names) if tree_names else "(none found)"
        if normalized.sketch_name:
            target_sketch = _match_tree_name(normalized.sketch_name)
            if target_sketch is None:
                raise Exception(
                    f"Sketch '{normalized.sketch_name}' not found in the "
                    f"feature tree. Sketches available to cut from: {available}"
                )
        else:
            last_tracked = getattr(adapter, "_last_sketch_name", None)
            target_sketch = _match_tree_name(last_tracked) if last_tracked else None
            if target_sketch is None:
                hint = (
                    f" (the last create_sketch call returned '{last_tracked}', "
                    "which does not match any real sketch in the model — "
                    "SolidWorks likely didn't hand back a usable sketch "
                    "object synchronously)"
                    if last_tracked
                    else " (no create_sketch/exit_sketch call has run this session)"
                )
                raise Exception(
                    "No sketch_name given, and no reliably-tracked sketch to "
                    f"cut from{hint}. Pass sketch_name explicitly. Sketches "
                    f"available to cut from: {available}"
                )

        # Explicit selection before any FeatureCut attempt. SolidWorks' own
        # "implicit" active-sketch state (whatever was last open) is never
        # relied upon — that is exactly the race that made this feature
        # intermittently cut nothing while reporting no error at all.
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
        # Callout must be an explicit VT_DISPATCH null, not plain None — a
        # bare None marshals as VT_NULL and SolidWorks rejects the whole call
        # with DISP_E_TYPEMISMATCH (runbook item 11). Using
        # _attempt_with_error (not _attempt) here means that error surfaces
        # in the failure message below instead of being swallowed into a
        # generic "selection failed" guess.
        select_result, select_error = adapter._attempt_with_error(
            lambda: adapter.currentModel.Extension.SelectByID2(
                target_sketch,
                "SKETCH",
                0.0,
                0.0,
                0.0,
                False,
                0,
                _null_callout(),
                0,
            )
        )
        sketch_selected = bool(select_result)
        if not sketch_selected:
            reason = (
                f" COM error: {select_error}"
                if select_error is not None
                else " SelectByID2 returned False with no COM error — the "
                "sketch may already be consumed by another feature, be "
                "suppressed, or not be a valid selectable profile."
            )
            raise Exception(
                f"Failed to select sketch '{target_sketch}' via SelectByID2." + reason
            )
        adapter._last_sketch_name = target_sketch

        end_condition = (normalized.end_condition or "Blind").strip().lower()
        blind = adapter.constants["swEndCondBlind"]
        through_all = adapter.constants["swEndCondThroughAll"]
        depth_m = normalized.depth / 1000.0
        through_one = end_condition in {"throughall", "through all", "through_all"}
        through_both = end_condition in {
            "throughallboth",
            "through all both",
            "through_all_both",
        } or (through_one and normalized.both_directions)

        t0 = adapter.constants.get("swStartSketchPlane", 0)
        feature = None
        fallback_errors: list[str] = []

        # Detect the SW major version: it picks OptimizeGeometry below.
        sw_major = 0
        if getattr(adapter, "swApp", None):
            rev = adapter._attempt(
                lambda: adapter._get_attr_or_call(adapter.swApp, "RevisionNumber"),
                default="0",
            )
            try:
                sw_major = int(str(rev).split(".")[0])
            except (ValueError, IndexError):
                sw_major = 0

        # (label, Sd, T1, T2, Dir) forms to try, in order. Sd is True for a
        # single-ended cut, False to also cut Direction 2 with T2. Dir
        # reverses Direction 1.
        reverse = normalized.reverse_direction
        if through_both:
            # Through All in both directions is a double-ended cut with
            # Through All on each side. A single-ended cut with
            # T1=swEndCondThroughAllBoth (9) is accepted by the COM call but
            # SolidWorks 2026 returns no feature for it (seen live on a closed
            # Front Plane sketch), so that form is only a fallback.
            forms = [
                (
                    " [Sd=False, T1=T2=ThroughAll]",
                    False,
                    through_all,
                    through_all,
                    reverse,
                ),
                (
                    " [Sd=True, T1=ThroughAllBoth]",
                    True,
                    adapter.constants["swEndCondThroughAllBoth"],
                    blind,
                    reverse,
                ),
            ]
        else:
            # One direction (Blind or Through All) is single-ended: Sd means
            # "single direction" (#193). Direction 1 follows the sketch
            # normal, so from a sketch on a face, or on the plane of one, the
            # requested direction can point out of the part and the cut finds
            # no material. Only then is the opposite direction tried, which is
            # what the SolidWorks UI does (seen live on SW 2026: a Top Plane
            # sketch under a block cut nothing until Dir was flipped).
            t1 = through_all if through_one else blind
            forms = [
                ("", True, t1, blind, reverse),
                (" [direction flipped]", True, t1, blind, not reverse),
            ]

        def _cut_args(sd: bool, t1: int, t2: int, dir_: bool) -> list[Any]:
            """Build the 26 arguments ``FeatureCut3`` and ``FeatureCut4`` share.

            Signature: Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
            Dang1, Dang2, OffsetReverse1, OffsetReverse2, TranslateSurface1,
            TranslateSurface2, NormalCut, UseFeatScope, UseAutoSelect,
            AssemblyFeatureScope, AutoSelectComponents, PropagateFeatureToParts,
            T0, StartOffset, FlipStartOffset. ``FeatureCut4`` appends
            OptimizeGeometry.

            Args:
                sd: ``True`` for a single-ended cut.
                t1: Direction 1 end condition.
                t2: Direction 2 end condition (used only when ``sd`` is False).
                dir_: Reverse Direction 1.

            Returns:
                list[Any]: Positional arguments in COM order.
            """
            return [
                sd,  # Sd
                False,  # Flip (True would cut outside the profile)
                dir_,  # Dir
                t1,  # T1
                t2,  # T2
                depth_m,  # D1
                0.0,  # D2
                False,
                False,
                False,
                False,  # Dchk1/2, Ddir1/2
                normalized.draft_angle * 3.14159 / 180.0,  # Dang1
                0.0,  # Dang2
                False,
                False,
                False,
                False,  # OffsetRev1/2, TranslateSurf1/2
                False,  # NormalCut
                normalized.feature_scope,  # UseFeatScope
                normalized.auto_select,  # UseAutoSelect
                False,  # AssemblyFeatureScope
                False,  # AutoSelectComponents
                False,  # PropagateFeatureToParts
                t0,  # T0
                0.0,  # StartOffset
                False,  # FlipStartOffset
            ]

        # 1. FeatureCut4 (SW 2015+): 27 params, the 27th being
        # OptimizeGeometry (verified True on SW 2025, False on SW 2026). PFeat
        # is an OUT param (PARAMFLAG_FOUT|FRETVAL), never passed by the caller.
        # 2. FeatureCut3 (SW 2010+, and any install lacking FeatureCut4).
        optimize_geometry = sw_major == 33
        first_call = True
        direction_flipped = False
        for label, sd, t1, t2, dir_ in forms:
            direction_flipped = dir_ != reverse
            args = _cut_args(sd, t1, t2, dir_)
            calls = (
                (
                    "FeatureCut4",
                    lambda a=args: feature_manager.FeatureCut4(*a, optimize_geometry),
                ),
                ("FeatureCut3", lambda a=args: feature_manager.FeatureCut3(*a)),
            )
            for api_name, call in calls:
                if not first_call:
                    # The sketch is already explicitly selected (above) — no
                    # guessing here. A failed FeatureCut can drop it, so
                    # reselect the same sketch before the next variant.
                    adapter._attempt(
                        lambda: adapter.currentModel.Extension.SelectByID2(
                            target_sketch,
                            "SKETCH",
                            0.0,
                            0.0,
                            0.0,
                            False,
                            0,
                            _null_callout(),
                            0,
                        ),
                        default=False,
                    )
                first_call = False
                feature, cut_error = adapter._attempt_with_error(call)
                if cut_error is not None:
                    fallback_errors.append(f"{api_name}{label}: {cut_error}")
                if feature:
                    break
            if feature:
                break

        if not feature:
            if fallback_errors:
                raise Exception(
                    f"Failed to create cut extrude feature from sketch "
                    f"'{target_sketch}' (SolidWorks major version {sw_major}). "
                    + " | ".join(fallback_errors)
                )
            # Name what was tried so the caller doesn't retry the same thing:
            # a one-direction cut has already been tried both ways.
            tried = "; ".join(
                label.strip(" []") or "the requested direction"
                for label, *_rest in forms
            )
            raise Exception(
                f"SolidWorks built no feature from sketch '{target_sketch}' "
                f"(tried: {tried}; SolidWorks major version {sw_major}). The "
                "profile removed no material in any of them. Check that the "
                "sketch is a closed profile, that it overlaps the solid body "
                f"within the {normalized.depth:g} mm depth (or use "
                "end_condition 'ThroughAll'), and that no other feature has "
                "already used the sketch."
            )

        return SolidWorksFeature(
            name=feature.Name,
            type="Cut-Extrude",
            id=adapter._get_feature_id(feature),
            parameters={
                "depth": normalized.depth,
                "draft_angle": normalized.draft_angle,
                "reverse_direction": normalized.reverse_direction,
                "sketch_name": target_sketch,
                # True when the requested direction found no material and the
                # cut went the other way (#193).
                "direction_flipped": direction_flipped,
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_cut_extrude", _cut_operation),
    )


def _parse_edge_spec(
    edge_name: str,
) -> tuple[str, float, float, float, str]:
    """Parse an edge/face specification string into (name, x, y, z, entity_type).

    Supports three formats:
    - ``"Edge<1>"`` — name-based EDGE selection (x=y=z=0.0, SW looks up by
      topology name)
    - ``"x,y,z"`` — coordinate-based EDGE selection (name="", coordinate hint
      in metres)
    - ``"face:x,y,z"`` (case-insensitive prefix) — coordinate-based FACE
      selection. Selecting a whole face and handing it to
      ``InsertFeatureChamfer``/``FeatureFillet3`` chamfers/fillets every
      edge bounding that face in one call. This is more robust than
      targeting a single edge by coordinate: a point exactly on a shared
      boundary between two faces (e.g. a hole rim flush with the top
      surface) can have its nearest-edge resolution silently shift to an
      unrelated edge after another feature is added earlier in the tree,
      picking a face interior point has no such ambiguity. Confirmed live
      2026-09-18: an edge-coordinate hole-rim chamfer silently landed on
      the block's 30mm outer edge instead (volume delta matched the
      straight-edge formula, not the circular-rim one); selecting the face
      instead reliably chamfers the real rim.
    """
    prefix, _, rest = edge_name.partition(":")
    if prefix.strip().lower() == "face":
        parts = rest.split(",")
        if len(parts) == 3:
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                return "", x, y, z, "FACE"
            except ValueError:
                pass
        return rest, 0.0, 0.0, 0.0, "FACE"

    parts = edge_name.split(",")
    if len(parts) == 3:
        try:
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            return "", x, y, z, "EDGE"
        except ValueError:
            pass
    return edge_name, 0.0, 0.0, 0.0, "EDGE"


#: A coordinate pick must lie this close to the edge/face it resolves to.
#: Generous enough for a rounded midpoint, far below any real feature size,
#: so a point that is not on any edge fails instead of grabbing a neighbour.
_PICK_TOLERANCE_M = 5e-4


class _BodyEntityPicker:
    """Find the body edge or face nearest a point, by true closest distance.

    ``SelectByID2("", "EDGE", x, y, z, ...)`` picks along the view direction
    through the point, so on a 12 mm plate seen from the front an edge at
    z=-6 is hidden behind the matching edge at z=+6 and the front one is
    selected instead - silently. This walks every solid body's edges (or
    faces) and measures the distance from the point to the closest point
    *on* each (``IEdge`` / ``IFace2.GetClosestPointOn``), which does not
    depend on the view, vertices or midpoints.

    The entity lists are read once per picker, so one fillet over many edges
    costs one body walk, not one per edge.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self._cache: dict[str, list[Any]] = {}

    def entities(self, getter: str) -> list[Any]:
        """Return every solid body's ``GetEdges()`` or ``GetFaces()``."""
        if getter not in self._cache:
            model = self._adapter.currentModel
            _flag(self._adapter, model, "GetBodies2")
            bodies = as_list(
                _attempt(self._adapter, lambda: model.GetBodies2(0, False))
            )
            found: list[Any] = []
            for body in bodies:
                _flag(self._adapter, body, getter)
                found.extend(
                    as_list(
                        _attempt(self._adapter, lambda b=body: getattr(b, getter)())
                    )
                )
            self._cache[getter] = found
        return self._cache[getter]

    def nearest(
        self, getter: str, point: tuple[float, float, float]
    ) -> tuple[Any, float] | None:
        """Return ``(entity, distance_m)`` for the closest entity, or ``None``."""
        best: tuple[Any, float] | None = None
        for entity in self.entities(getter):
            _flag(self._adapter, entity, "GetClosestPointOn")
            closest = _attempt(
                self._adapter, lambda e=entity: list(e.GetClosestPointOn(*point))
            )
            if not closest or len(closest) < 3:
                continue
            distance = math.dist([float(c) for c in closest[:3]], point)
            if best is None or distance < best[1]:
                best = (entity, distance)
        return best

    def select(self, entity: Any, append: bool, mark: int = 0) -> bool:
        """Select ``entity`` with ``IEntity.Select4`` under ``mark``."""
        model = self._adapter.currentModel
        sel_mgr = _attempt(self._adapter, lambda: model.SelectionManager)
        _flag(self._adapter, sel_mgr, "CreateSelectData")
        select_data = _attempt(self._adapter, lambda: sel_mgr.CreateSelectData())
        if select_data is None:
            return False
        if mark:
            _attempt(self._adapter, lambda: setattr(select_data, "Mark", mark))
        _flag(self._adapter, entity, "Select4")
        return bool(
            _attempt(self._adapter, lambda: entity.Select4(append, select_data), False)
        )


def _select_by_view_pick(
    adapter: Any,
    x: float,
    y: float,
    z: float,
    append: bool,
    mark: int,
    entity_type: str,
) -> bool:
    """Fallback pick through ``SelectByID2`` when no body geometry is readable.

    Tries the point plus small radial/Y offsets. View-dependent (see
    :class:`_BodyEntityPicker`), so only used when the body walk found
    nothing to measure.
    """
    model = adapter.currentModel
    r = math.sqrt(x**2 + z**2)
    if r > 0:
        candidates = [
            (x, y, z),
            (x * 0.999, y, z * 0.999),
            (x * 1.001, y, z * 1.001),
            (x * 0.997, y, z * 0.997),
            (x * 1.003, y, z * 1.003),
            (x, y * 0.999, z),
            (x, y * 1.001, z),
        ]
    else:
        candidates = [(x, y, z), (x, y * 0.999, z), (x, y * 1.001, z)]

    for cx, cy, cz in candidates:
        try:
            selected = bool(
                model.Extension.SelectByID2(
                    "", entity_type, cx, cy, cz, append, mark, _null_callout(), 0
                )
            )
        except Exception:
            selected = False
        if selected:
            return True
    return False


def _select_edge_by_coord(
    adapter: Any,
    x: float,
    y: float,
    z: float,
    append: bool,
    mark: int = 0,
    entity_type: str = "EDGE",
    picker: _BodyEntityPicker | None = None,
) -> bool:
    """Select the edge (or face) nearest to (x, y, z) in metres.

    Calls ``ForceRebuild3`` on the first entity in the selection set so that
    recent features are fully tessellated and selectable, then resolves the
    point with :class:`_BodyEntityPicker` - the entity whose closest point is
    nearest, independent of the view. Only when no body edge/face can be read
    at all does it fall back to the view-dependent ``SelectByID2`` pick.

    ``entity_type`` is normally ``"EDGE"``, but pass ``"FACE"`` to select a
    whole face instead. Any other type (``"VERTEX"`` from
    ``measure_entities``) goes straight to the ``SelectByID2`` pick: a vertex
    lies on its edges at distance 0, so the edge walk would select an edge
    in its place.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        x: X in metres.
        y: Y in metres.
        z: Z in metres.
        append: Add to the current selection instead of replacing it.
        mark: Selection mark.
        entity_type: ``"EDGE"``, ``"FACE"``, or another ``SelectByID2``
            type such as ``"VERTEX"``.
        picker: Reuse a picker (and its body walk) across several picks.

    Returns:
        bool: True if an entity was selected; False otherwise.

    Raises:
        LookupError: When the nearest entity is further than
            ``_PICK_TOLERANCE_M`` from the point - picking it anyway would
            silently act on the wrong edge.
    """
    model = adapter.currentModel

    # Rebuild to tessellate geometry from recent features before the first
    # entity in the selection set (when append=False this is the first one).
    if not append:
        adapter._attempt(lambda: model.ForceRebuild3(True), default=None)

    # Only edges and faces are walked on the body; anything else (a vertex)
    # keeps the SelectByID2 pick, which honours the requested type.
    if entity_type not in ("EDGE", "FACE"):
        return _select_by_view_pick(adapter, x, y, z, append, mark, entity_type)

    picker = picker or _BodyEntityPicker(adapter)
    getter = "GetFaces" if entity_type == "FACE" else "GetEdges"
    nearest = picker.nearest(getter, (x, y, z))
    if nearest is None:
        return _select_by_view_pick(adapter, x, y, z, append, mark, entity_type)

    entity, distance = nearest
    if distance > _PICK_TOLERANCE_M:
        kind = entity_type.lower()
        raise LookupError(
            f"No {kind} passes through ({x * 1000:g}, {y * 1000:g}, "
            f"{z * 1000:g}) mm; the nearest is {distance * 1000:.3f} mm away. "
            f"Give a point on the {kind} itself."
        )
    return picker.select(entity, append, mark)


def _select_face_edges_by_coord(
    adapter: Any,
    x: float,
    y: float,
    z: float,
    append: bool,
    picker: _BodyEntityPicker,
) -> bool:
    """Select every edge bounding the face through (x, y, z) in metres.

    ``IModelDoc2.FeatureFillet3`` (SW 2025+) given a selected *face* returns
    success but builds nothing - no feature, no volume change (seen live on
    SW 2026). Expanding the face to its edges first gives it what it can
    fillet.

    Returns:
        bool: True when the face was found and all of its edges selected.

    Raises:
        LookupError: When no face lies within ``_PICK_TOLERANCE_M``.
    """
    if not append:
        adapter._attempt(lambda: adapter.currentModel.ForceRebuild3(True), default=None)
    nearest = picker.nearest("GetFaces", (x, y, z))
    if nearest is None:
        return False
    face, distance = nearest
    if distance > _PICK_TOLERANCE_M:
        raise LookupError(
            f"No face passes through ({x * 1000:g}, {y * 1000:g}, {z * 1000:g}) "
            f"mm; the nearest is {distance * 1000:.3f} mm away."
        )
    _flag(adapter, face, "GetEdges")
    edges = as_list(_attempt(adapter, lambda: face.GetEdges()))
    if not edges:
        return False
    for index, edge in enumerate(edges):
        if not picker.select(edge, append or index > 0):
            return False
    return True


def _add_fillet_impl(
    adapter: Any, radius: float, edge_names: list[str]
) -> AdapterResult[SolidWorksFeature]:
    """Create a constant-radius fillet on one or more named edges.

    Each edge in ``edge_names`` is selected by name using
    ``Extension.SelectByID2`` with entity type ``"EDGE"``.  After all edges
    are in the selection set, ``FeatureFillet3`` is called to build the
    feature.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        radius: Fillet radius in **millimetres**.  Converted to metres
            internally before the COM call.
        edge_names: List of SolidWorks edge entity names to fillet, e.g.
            ``["Edge<1>", "Edge<2>"]``, coordinate hints in metres
            (``"x,y,z"``), or ``"face:x,y,z"`` to select a whole face and
            fillet every edge bounding it — see :func:`_parse_edge_spec`.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Fillet"``.  On failure,
        ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when an
            edge cannot be selected or ``FeatureFillet3`` returns ``None``.

    Example::

        result = pywin32_feature_ops.add_fillet(
            adapter, radius=3.0, edge_names=["Edge<1>", "Edge<3>"]
        )
        print(result.data.name)  # e.g. "Fillet1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _fillet_operation() -> SolidWorksFeature:
        """Inner COM closure that selects edges and invokes FeatureFillet3.

        Returns:
            SolidWorksFeature: Populated feature descriptor.

        Raises:
            Exception: If any edge selection fails or the feature is ``None``.
        """
        # Detect SW major version for FeatureFillet3 parameter count
        fillet_sw_major = 0
        if getattr(adapter, "swApp", None):
            rev = adapter._attempt(
                lambda: adapter._get_attr_or_call(adapter.swApp, "RevisionNumber"),
                default="0",
            )
            try:
                fillet_sw_major = int(str(rev).split(".")[0])
            except (ValueError, IndexError):
                fillet_sw_major = 0

        # Only touch the selection when edges/faces were explicitly named.
        # An empty edge_names means "use whatever is already selected" --
        # e.g. entities the user hand-picked in the live UI via
        # get_selected_entities. Clearing unconditionally here used to wipe
        # that selection out from under the caller before FeatureFillet3
        # ever ran, so a live multi-edge UI selection silently fell through
        # to "no selection" (SW's own fillet-all-edges fallback) or an
        # earlier partial/stale selection instead of what was actually
        # picked. See com-api-pitfalls.md #22.
        features_before = _feature_count(adapter)

        if edge_names:
            adapter._attempt(
                lambda: adapter.currentModel.ClearSelection2(True), default=None
            )

            picker = _BodyEntityPicker(adapter)
            for idx, edge_name in enumerate(edge_names):
                sel_name, ex, ey, ez, entity_type = _parse_edge_spec(edge_name)
                append = idx > 0  # first edge starts fresh, subsequent ones append
                if sel_name == "" and entity_type == "FACE":
                    # A selected face makes FeatureFillet3 build nothing, so
                    # select the edges bounding it instead.
                    selected = _select_face_edges_by_coord(
                        adapter, ex, ey, ez, append=append, picker=picker
                    )
                elif sel_name == "":
                    # Coordinate-based: traverse body edges and pick the closest one.
                    selected = _select_edge_by_coord(
                        adapter,
                        ex,
                        ey,
                        ez,
                        append=append,
                        entity_type=entity_type,
                        picker=picker,
                    )
                else:
                    selected = adapter._attempt(
                        lambda sn=sel_name, _x=ex, _y=ey, _z=ez, _ap=append, _et=entity_type: (
                            adapter.currentModel.Extension.SelectByID2(
                                sn, _et, _x, _y, _z, _ap, 0, _null_callout(), 0
                            )
                        ),
                        default=False,
                    )
                if not selected:
                    raise Exception(f"Failed to select edge: {edge_name}")

        # SW 2025+ (major >= 33): IModelDoc2.FeatureFillet3 (9 params).
        # Returns a non-zero int on success — NOT an IFeature — so we look up
        # the last modified feature afterwards to get the name/id.
        # Older builds: IFeatureManager.FeatureFillet3 (15 params, returns IFeature).
        if fillet_sw_major >= 33:
            result_code = adapter.currentModel.FeatureFillet3(
                radius / 1000.0,  # R1 in meters
                True,  # Propagate (VT_BOOL)
                0,  # Ftyp (VT_I4)
                False,  # VarRadTyp (VT_BOOL — must be bool, not int)
                0,  # OverflowType (VT_I4)
                0,  # NRadii (VT_I4)
                None,  # Radii (VT_VARIANT)
                False,  # UseHelpPoint (VT_BOOL)
                False,  # UseTangentHoldLine (VT_BOOL)
            )
            if not result_code:
                raise Exception(
                    "Failed to create fillet (IModelDoc2.FeatureFillet3 returned 0)"
                )
            feature = None  # int return — retrieve feature object below
        else:
            feature_manager = adapter.currentModel.FeatureManager
            feature = feature_manager.FeatureFillet3(
                radius / 1000.0,
                0,
                0,
                0,
                0,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                0,
                False,
            )
            if not feature:
                raise Exception("Failed to create fillet")

        # IModelDoc2.FeatureFillet3 returns non-zero for a selection it then
        # builds nothing from (e.g. a bare face, seen live on SW 2026), so a
        # success code alone proves nothing: the tree must have grown. An
        # unreadable count is not evidence either way; the caller also
        # compares volume.
        features_after = _feature_count(adapter)
        if (
            features_before is not None
            and features_after is not None
            and features_after <= features_before
        ):
            raise Exception(
                "FeatureFillet3 reported success but no fillet feature was added "
                f"(feature count stayed at {features_before}); the selected "
                "edges could not be filleted at this radius."
            )

        # Resolve the feature name — FeatureFillet3 on SW 2025+ returns an int,
        # not an IFeature, so we can only report a default name here.
        feature_name = "Fillet"
        if feature is not None:
            # Not hasattr(): it only swallows AttributeError, so a stale COM
            # dispatch raising on Name would fail a fillet that was created.
            try:
                feature_name = feature.Name or "Fillet"
            except Exception:  # noqa: BLE001 - int return / stale dispatch
                pass

        return SolidWorksFeature(
            name=feature_name,
            type="Fillet",
            id=(
                adapter._attempt(lambda: adapter._get_feature_id(feature), default="")
                if feature
                else ""
            ),
            parameters={"radius": radius, "edges": edge_names},
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("add_fillet", _fillet_operation),
    )


def _add_chamfer_impl(
    adapter: Any, distance: float, edge_names: list[str]
) -> AdapterResult[SolidWorksFeature]:
    """Create an equal-distance chamfer on one or more named edges.

    Each edge in ``edge_names`` is selected by name using
    ``Extension.SelectByID2`` with entity type ``"EDGE"``.  After all edges
    are in the selection set, ``IFeatureManager::InsertFeatureChamfer`` is
    called in equal-distance mode (type ``1``). A version-gated
    ``IModelDoc2::FeatureChamferType`` path was tried for SW 2025+ but
    live-verified to silently create an empty, zero-volume feature -- see
    the comment at its call site for how this was confirmed and why
    ``InsertFeatureChamfer`` is used unconditionally instead.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        distance: Chamfer distance in **millimetres**.  Converted to metres
            internally.
        edge_names: List of SolidWorks edge entity names, e.g.
            ``["Edge<2>", "Edge<5>"]``, coordinate hints in metres
            (``"x,y,z"``), or ``"face:x,y,z"`` to select a whole face and
            chamfer every edge bounding it — see :func:`_parse_edge_spec`.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Chamfer"``.  On failure,
        ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when an
            edge cannot be selected or ``InsertFeatureChamfer`` returns
            ``None``.

    Example::

        result = pywin32_feature_ops.add_chamfer(
            adapter, distance=2.0, edge_names=["Edge<2>"]
        )
        print(result.data.name)  # e.g. "Chamfer1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _chamfer_operation() -> SolidWorksFeature:
        """Inner COM closure that selects edges and invokes the chamfer API.

        Returns:
            SolidWorksFeature: Populated feature descriptor.

        Raises:
            Exception: If any edge selection fails or the feature is not created.
        """
        import math

        # Only touch the selection when edges/faces were explicitly named.
        # An empty edge_names means "use whatever is already selected" --
        # see the matching comment in _add_fillet_impl / com-api-pitfalls.md #22.
        if edge_names:
            adapter._attempt(
                lambda: adapter.currentModel.ClearSelection2(True), default=None
            )

            for idx, edge_name in enumerate(edge_names):
                sel_name, cx, cy, cz, entity_type = _parse_edge_spec(edge_name)
                append = idx > 0
                if sel_name == "":
                    selected = _select_edge_by_coord(
                        adapter,
                        cx,
                        cy,
                        cz,
                        append=append,
                        mark=0,
                        entity_type=entity_type,
                    )
                else:
                    selected = adapter._attempt(
                        lambda sn=sel_name, _x=cx, _y=cy, _z=cz, _ap=append, _et=entity_type: (
                            adapter.currentModel.Extension.SelectByID2(
                                sn, _et, _x, _y, _z, _ap, 0, _null_callout(), 0
                            )
                        ),
                        default=False,
                    )
                if not selected:
                    raise Exception(f"Failed to select edge: {edge_name}")

        fm = adapter.currentModel.FeatureManager
        _flag_feature_methods(fm, "IFeatureManager")

        # IModelDoc2.FeatureChamferType (the documented "SW 2025+" call) was
        # tried here previously, gated on RevisionNumber >= 33. Live-verified
        # (2026-09-18, SW major 34 / SW2026): it returns cleanly and a
        # "Chamfer1" feature appears in the tree, but removes zero volume --
        # a silent no-op, not a real chamfer. IFeatureManager.InsertFeatureChamfer
        # was verified on the same install to actually remove material
        # (confirmed via mass-properties volume delta), so it is used
        # unconditionally rather than version-branching to a call that has
        # never been proven to work on any SW version.
        feature_name = "Chamfer"
        feature, insert_err = adapter._attempt_with_error(
            lambda: fm.InsertFeatureChamfer(
                1,  # Options
                1,  # ChamferType = equal distance
                distance / 1000.0,  # Width in metres
                math.pi / 4,  # 45 degree angle
                0.0,
                0.0,
                0.0,
                0.0,
            )
        )
        if feature and hasattr(feature, "Name"):
            feature_name = feature.Name or "Chamfer"
        elif not feature:
            raise Exception(
                f"Failed to create chamfer (InsertFeatureChamfer: {insert_err})"
            )

        return SolidWorksFeature(
            name=feature_name,
            type="Chamfer",
            id=adapter._get_feature_id(feature) if feature else "",
            parameters={"distance": distance, "edges": edge_names},
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("add_chamfer", _chamfer_operation),
    )


def _select_feature_by_name(adapter: Any, name: str, append: bool = False) -> Any:
    """Select a feature or sketch by name and return it.

    Resolves the entity with ``IModelDoc2::FeatureByName`` and selects it with
    ``IFeature::Select2(append, 0)`` - the same path used elsewhere in this
    adapter. ``SelectByID2`` is avoided here because it needs an entity-type
    string that differs between sketches and solid features, and because its
    ``Callout`` argument raises ``Type mismatch`` unless passed an explicit
    ``VT_DISPATCH`` null. Any ``name@document`` qualifier is stripped first.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        name: Feature or sketch name, e.g. ``"Boss-Extrude1"`` or ``"Sketch1"``.
        append: Add to the current selection instead of clearing it first.
            Defaults to False.

    Returns:
        Any: The selected ``IFeature``, or ``None`` when it does not exist or
        could not be selected.
    """
    bare = name.split("@", 1)[0]
    if not append:
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
    feature = adapter._attempt(
        lambda: adapter.currentModel.FeatureByName(bare), default=None
    )
    if not feature:
        return None
    selected = adapter._attempt(lambda: feature.Select2(append, 0), default=False)
    return feature if selected else None


def _feature_count(adapter: Any) -> int | None:
    """Return how many features the active model has, or ``None``.

    Used to confirm an edit changed the tree rather than trusting a COM call
    that reports success without doing anything.

    ``IFeatureManager::GetFeatureCount`` is used rather than walking
    ``FirstFeature``/``GetNextFeature``: the walk needs each dispatch flagged
    for ``IFeature`` before ``Name`` and ``GetNextFeature`` resolve, and on
    SW 2025 it still yields nothing, while the count is a single reliable
    call. ``FeatureByPositionReverse`` was measured returning nothing usable
    on the same document.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.

    Returns:
        int | None: The feature count, or ``None`` when it cannot be read -
        which is deliberately distinct from ``0``.
    """
    manager = adapter._attempt(
        lambda: adapter.currentModel.FeatureManager, default=None
    )
    if manager is None:
        return None
    flagged = sw_type_info.flagged(manager, "IFeatureManager")
    count = adapter._attempt(lambda: flagged.GetFeatureCount(True), default=None)
    return int(count) if isinstance(count, (int, float)) else None


def _is_suppressed(adapter: Any, feature: Any) -> bool | None:
    """Return a feature's suppression state, or ``None`` when unreadable.

    ``None`` is deliberately distinct from ``False``: it means the state could
    not be read, which is not evidence that the feature is unsuppressed.

    Args:
        adapter: A connected adapter.
        feature: An ``IFeature`` dispatch.

    Returns:
        bool | None: ``True`` suppressed, ``False`` not, ``None`` unknown.
    """
    state = adapter._attempt(
        lambda: adapter._get_attr_or_call(feature, "IsSuppressed"), default=None
    )
    if isinstance(state, bool):
        return state
    if isinstance(state, (list, tuple)) and state:
        return bool(state[0])
    if isinstance(state, int):
        return bool(state)
    return None


def _delete_feature_impl(adapter: Any, name: str) -> AdapterResult[dict[str, Any]]:
    """Delete a named feature or sketch from the active model.

    Selects the feature, then removes it with ``IModelDoc2::EditDelete``.
    Deleting a parent also removes its children, which is SolidWorks' normal
    cascade and the intended "erase this and what depends on it" behaviour -
    so the number of features removed is reported, not assumed to be one.

    ``EditDelete`` returns nothing useful, so success is confirmed by the
    feature being absent from the tree afterwards.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        name: Name of the feature or sketch to delete.

    Returns:
        AdapterResult[dict[str, Any]]: What was deleted and how the tree
        changed. ``ERROR`` when there is no model or the feature is absent.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _delete_operation() -> dict[str, Any]:
        before = _feature_count(adapter)
        if _select_feature_by_name(adapter, name) is None:
            raise Exception(f"Feature not found: {name}")

        adapter._attempt(
            lambda: adapter._get_attr_or_call(adapter.currentModel, "EditDelete"),
            default=None,
        )
        adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), default=None)

        # EditDelete reports nothing useful, so confirm by lookup: the
        # feature must no longer resolve by name.
        bare = name.split("@", 1)[0]
        still_there = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(bare), default=None
        )
        if still_there:
            raise Exception(f"EditDelete did not remove feature: {name}")

        after = _feature_count(adapter)
        return {
            "deleted": name,
            "features_before": before,
            "features_after": after,
            # Deleting a parent takes its children too, so this is often
            # more than one.
            "features_removed": (
                before - after if before is not None and after is not None else None
            ),
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("delete_feature", _delete_operation),
    )


def _suppress_feature_impl(
    adapter: Any, name: str, suppress: bool
) -> AdapterResult[dict[str, Any]]:
    """Suppress or unsuppress a named feature in the active model.

    Suppressing rolls a feature and its children out of the model without
    deleting it - the reversible way to turn off a bad feature.

    ``EditSuppress2`` and ``EditUnsuppress2`` report through the error channel
    only, so the resulting state is read back from ``IFeature::IsSuppressed``
    rather than inferred from the call returning quietly.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        name: Feature name to toggle.
        suppress: ``True`` to suppress, ``False`` to unsuppress.

    Returns:
        AdapterResult[dict[str, Any]]: The feature and its state afterwards.
        ``suppressed`` is ``None`` when the state could not be read back,
        which is not the same as "not suppressed".

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _suppress_operation() -> dict[str, Any]:
        feature = _select_feature_by_name(adapter, name)
        if feature is None:
            raise Exception(f"Feature not found: {name}")

        was = _is_suppressed(adapter, feature)
        # EditSuppress2/EditUnsuppress2 take no arguments, and late binding
        # resolves them as properties on some dispatches: calling with ()
        # performs the edit and *then* raises "'bool' object is not callable",
        # so the operation succeeds while the caller sees a failure.
        member = "EditSuppress2" if suppress else "EditUnsuppress2"
        _, err = adapter._attempt_with_error(
            lambda: adapter._get_attr_or_call(adapter.currentModel, member)
        )
        if err is not None:
            action = "suppress" if suppress else "unsuppress"
            raise Exception(f"Failed to {action} {name}: {err}")

        adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), default=None)

        # Re-resolve: the dispatch held above can go stale across a rebuild.
        refreshed = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(name.split("@", 1)[0]),
            default=None,
        )
        now = _is_suppressed(adapter, refreshed) if refreshed is not None else None
        if now is not None and now != suppress:
            action = "suppressed" if suppress else "unsuppressed"
            raise Exception(
                f"{name} reports suppressed={now} after being {action}; the "
                "call was accepted but the feature state did not change."
            )

        return {
            "feature": name,
            "requested": suppress,
            "suppressed": now,
            "was_suppressed": was,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("suppress_feature", _suppress_operation),
    )


def _rename_feature_impl(
    adapter: Any, old_name: str, new_name: str
) -> AdapterResult[dict[str, Any]]:
    """Rename a named feature in the active model.

    ``IFeature::Name`` is a settable property, not a method - it is assigned
    directly, never called (see the property-vs-method flagging note in the
    COM threading section of ``CLAUDE.md``). SolidWorks silently refuses a
    rename onto a name another feature already uses, so a clash is checked
    for first and the new name is read back afterwards; a mismatch is
    reported as a failure rather than a quiet success.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        old_name: The feature's current name. Any ``name@document`` qualifier
            is stripped.
        new_name: The name to give it.

    Returns:
        AdapterResult[dict[str, Any]]: ``renamed`` (bool), ``old_name`` and
        ``new_name``. ``renamed`` is ``False`` with a ``reason`` when the two
        names are the same. ``ERROR`` when there is no model, the feature is
        absent, the target name is taken, or the rename did not take.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    # Resync from ActiveDoc: the user may have switched documents in the
    # SolidWorks UI since the last tool call (issue #91).
    sync = getattr(adapter, "_sync_current_model_from_active", None)
    if callable(sync):
        adapter._attempt(sync, default=None)
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    new = new_name.split("@", 1)[0].strip()
    if not new:
        return AdapterResult(
            status=AdapterResultStatus.ERROR, error="new_name must not be empty"
        )

    def _rename_operation() -> dict[str, Any]:
        bare = old_name.split("@", 1)[0]
        feature = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(bare), default=None
        )
        if not feature:
            raise Exception(f"Feature not found: {old_name}")

        if new == bare:
            return {
                "renamed": False,
                "old_name": bare,
                "new_name": new,
                "reason": "old and new names are the same",
            }

        # SolidWorks silently ignores a rename onto an existing feature name,
        # which would otherwise look like a success. Catch it up front.
        clash = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(new), default=None
        )
        if clash:
            raise Exception(
                f"Cannot rename to {new!r}: a feature with that name already exists"
            )

        _, err = adapter._attempt_with_error(lambda: setattr(feature, "Name", new))
        if err is not None:
            raise Exception(f"Failed to rename {bare} to {new}: {err}")

        adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), default=None)

        refreshed = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(new), default=None
        )
        if refreshed is None:
            raise Exception(
                f"Rename to {new} was accepted but no feature resolves by that "
                "name afterwards; the call did not take."
            )
        actual = adapter._attempt(
            lambda: adapter._get_attr_or_call(refreshed, "Name"), default=None
        )
        return {
            "renamed": True,
            "old_name": bare,
            "new_name": actual if isinstance(actual, str) and actual else new,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("rename_feature", _rename_operation),
    )


def _undo_impl(adapter: Any, count: int) -> AdapterResult[dict[str, Any]]:
    """Undo the last ``count`` operations in the active model.

    ``IModelDoc2::EditUndo2(Steps)`` is a ``Sub`` - it returns nothing - so a
    quiet call means only that it was made, not that anything was undone.
    SolidWorks accepts an undo with an empty stack without complaint. The
    feature tree is therefore compared before and after, and the payload says
    plainly whether it changed.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        count: Number of operations to undo; values below 1 are clamped.

    Returns:
        AdapterResult[dict[str, Any]]: How many steps were requested and
        whether the feature tree actually changed.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    steps = max(1, int(count))

    def _undo_operation() -> dict[str, Any]:
        before = _feature_count(adapter)

        _, err = adapter._attempt_with_error(
            lambda: adapter.currentModel.EditUndo2(steps)
        )
        if err is not None:
            # Older builds expose only the unsuffixed overload.
            _, legacy_err = adapter._attempt_with_error(
                lambda: adapter.currentModel.EditUndo(steps)
            )
            if legacy_err is not None:
                raise Exception(f"Undo failed: {err} | legacy: {legacy_err}")

        adapter._attempt(lambda: adapter.currentModel.EditRebuild3(), default=None)
        after = _feature_count(adapter)

        # None means the count could not be read, which is not evidence that
        # nothing happened - so tree_changed stays None rather than False.
        changed = None if before is None or after is None else before != after
        return {
            "requested_steps": steps,
            "features_before": before,
            "features_after": after,
            # False means the call was accepted and the tree is unchanged -
            # an undo with nothing left to undo. Reported rather than dressed
            # up as a success.
            "tree_changed": changed,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("undo", _undo_operation),
    )


#: ``swRefPlaneReferenceConstraints_e`` members used by ``InsertRefPlane``.
_REF_PLANE_DISTANCE = 8
_REF_PLANE_ANGLE = 16
_REF_PLANE_OPTION_FLIP = 256

#: Plane pairs whose intersection defines each principal axis. ``InsertAxis2``
#: builds an axis from two selected planes, so "x" means the line where the
#: Top and Front planes meet.
_AXIS_PLANE_PAIRS: dict[str, tuple[str, str]] = {
    "x": ("Top Plane", "Front Plane"),
    "y": ("Front Plane", "Right Plane"),
    "z": ("Top Plane", "Right Plane"),
}

#: ``swRefPointType_e`` members used by ``IFeatureManager::InsertReferencePoint``.
_SW_REF_POINT_ALONG_CURVE = 2
_SW_REF_POINT_FACE_CENTER = 4
#: ``swRefPointAlongCurveType_e``.
_SW_REF_POINT_ALONG_CURVE_DISTANCE = 0
_SW_REF_POINT_ALONG_CURVE_PERCENT = 1


def _offset_plane_distance(offset_mm: float, base_flip: bool) -> tuple[float, int]:
    """Resolve an offset-plane Distance constraint to ``(distance_m, flip_bits)``.

    ``IFeatureManager.InsertRefPlane``'s Distance constraint takes a positive
    magnitude; the *side* of the base plane is chosen by the ``OptionFlip``
    bit, not by the sign of the distance. Passing a negative distance does
    not place the plane on the opposite side - SolidWorks clamps it to 0,
    collapsing the new plane onto the base. So a negative ``offset_mm`` must
    be converted to a positive magnitude with the flip bit toggled relative
    to the caller's ``flip`` request (a negative offset plus ``flip=True``
    cancel out).

    Credit: this fix (and the pure-helper extraction for direct unit
    coverage) ports the sign-resolution logic independently found and fixed
    by contributor @pedropaulovc in their fork (commit ``3c091fd``). See
    issue #84.

    Args:
        offset_mm: Signed offset from the base plane, in millimetres.
        base_flip: Whether the caller requested ``flip``.

    Returns:
        tuple[float, int]: A non-negative distance in metres, and the flip
        bits (``_REF_PLANE_OPTION_FLIP`` or 0) to OR into the constraint.
    """
    distance_m = float(offset_mm) / 1000.0
    flip_bits = _REF_PLANE_OPTION_FLIP if base_flip else 0
    if distance_m < 0.0:
        distance_m = -distance_m
        flip_bits ^= _REF_PLANE_OPTION_FLIP
    return distance_m, flip_bits


class _NullCalloutSentinel:
    """Stand-in for ``VARIANT(VT_DISPATCH, None)`` when pywin32 is absent.

    Never passed to a real COM call (if pywin32 isn't importable, no live
    SolidWorks call can happen either), but must still be distinguishable
    from a bare ``None`` so callers can't accidentally regress to passing
    plain ``None`` as ``SelectByID2``'s ``Callout`` argument.
    """

    def __repr__(self) -> str:
        return "<null callout: pywin32 unavailable>"


_NULL_CALLOUT_SENTINEL = _NullCalloutSentinel()


def _null_callout() -> Any:
    """Return a VT_DISPATCH null for ``SelectByID2``'s ``Callout`` parameter.

    A plain Python ``None`` marshals as ``VT_NULL``, which SolidWorks rejects
    with ``DISP_E_TYPEMISMATCH`` - measured as
    ``(-2147352571, 'Type mismatch.', None, 8)``. See runbook item 11.

    Returns:
        Any: A ``VARIANT(VT_DISPATCH, None)``, or a non-``None`` sentinel
        when pywin32 is unavailable (mock/Linux runs, where no real COM call
        will be made anyway, but the value must still never be bare ``None``).
    """
    try:
        import pythoncom
        import win32com.client as _win32com
    except ImportError:
        return _NULL_CALLOUT_SENTINEL
    return _win32com.VARIANT(pythoncom.VT_DISPATCH, None)


def _select_reference_entity(
    adapter: Any, reference: str, mark: int, append: bool
) -> bool:
    """Select a named plane or planar face under a given selection mark.

    Prefers ``FeatureByName`` + ``IFeature::Select2``, which is reliable
    across builds, and falls back to ``SelectByID2`` for planar faces that are
    not named tree features.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        reference: Plane or face name, e.g. ``"Front Plane"`` or ``"Plane1"``.
        mark: Selection mark the SolidWorks call expects for this role.
        append: Add to the current selection rather than replacing it.

    Returns:
        bool: True when the entity was selected.
    """
    if _select_named_feature(adapter, reference, mark, append=append):
        return True

    callout = _null_callout()
    for entity_type in ("PLANE", "FACE"):
        selected = adapter._attempt(
            lambda t=entity_type: adapter.currentModel.Extension.SelectByID2(
                reference, t, 0.0, 0.0, 0.0, append, mark, callout, 0
            ),
            default=False,
        )
        if selected:
            return True
    return False


def _create_reference_plane_impl(
    adapter: Any,
    reference: str,
    offset: float,
    angle: float,
    flip: bool,
) -> AdapterResult[dict[str, Any]]:
    """Create a reference plane offset from, or angled to, an existing plane.

    Wraps ``IFeatureManager::InsertRefPlane(FirstConstraint,
    FirstConstraintAngleOrDistance, Second, 0, Third, 0)``. The reference
    entity must be selected under **mark 0** first, which is what the
    SolidWorks documentation example does before the identical call.

    This is what lets a sketch be opened anywhere other than the six built-in
    planes. ``create_sketch`` already accepts a plane by its tree name, so the
    name returned here can be passed straight to it - verified live: a plane
    76.2 mm off the Front Plane came back as ``"Plane1"``, and a circle
    sketched on it extruded to exactly the expected volume.

    Args:
        adapter: A connected ``PyWin32Adapter`` with a valid ``currentModel``.
        reference: Name of the reference plane or planar face.
        offset: Offset distance in **millimetres**, converted to metres.
        angle: Angle in **degrees**; used instead of ``offset`` when non-zero.
        flip: Reverse the offset or angle direction.

    Returns:
        AdapterResult[dict[str, Any]]: The new plane's name and the parameters
        used. ``ERROR`` when there is no model, the reference cannot be
        selected, or no plane was added to the tree.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.

    Example::

        plane = await adapter.create_reference_plane("Front Plane", offset=76.2)
        await adapter.create_sketch(plane.data["name"])
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    if not reference:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="create_reference_plane requires a reference plane/face name",
        )

    if angle:
        # Measured on SW 2025: InsertRefPlane with the angle constraint and a
        # single selected plane adds nothing to the tree and reports no error.
        # An angled plane is under-defined by one reference - SolidWorks needs
        # a second entity (an axis or edge) under mark 1 to rotate about.
        # Refusing is better than returning a plane name that does not exist.
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=(
                "create_reference_plane does not support 'angle' yet: an "
                "angled plane needs a second reference (an axis or edge to "
                "rotate about) which this signature cannot take. Use 'offset' "
                "for parallel planes."
            ),
        )

    if not offset:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=(
                "create_reference_plane requires a non-zero offset - a plane "
                "coincident with its reference is not useful"
            ),
        )

    def _plane_operation() -> dict[str, Any]:
        before = _feature_count(adapter)
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        if not _select_reference_entity(adapter, reference, 0, append=False):
            raise Exception(
                f"Failed to select reference plane/face: {reference}. "
                "Use an existing plane name (e.g. 'Front Plane') or a planar "
                "face."
            )

        value, flip_bits = _offset_plane_distance(offset, flip)
        constraint = _REF_PLANE_DISTANCE | flip_bits

        feature_manager = sw_type_info.flagged(
            adapter.currentModel.FeatureManager, "IFeatureManager"
        )
        plane = adapter._attempt(
            lambda: feature_manager.InsertRefPlane(constraint, value, 0, 0.0, 0, 0.0),
            default=None,
        )

        after = _feature_count(adapter)
        if before is not None and after is not None and after <= before:
            raise Exception(
                f"No reference plane was added from '{reference}' - the "
                f"feature tree still has {after} feature(s)."
            )
        if plane is None:
            raise Exception(
                f"InsertRefPlane returned nothing for reference '{reference}'"
            )

        name = adapter._attempt(
            lambda: adapter._get_attr_or_call(plane, "Name"), default=None
        )
        if not name:
            # No invented fallback: a caller needs the real name to sketch on
            # the plane, and a made-up one fails later and further away.
            raise Exception(
                "The reference plane was created but its name could not be "
                "read, so it cannot be referenced by create_sketch."
            )

        return {
            "name": str(name),
            "reference": reference,
            "offset": offset or None,
            "angle": angle or None,
            "flip": flip,
            "features_before": before,
            "features_after": after,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("create_reference_plane", _plane_operation),
    )


def _create_axis_impl(adapter: Any, reference: str) -> AdapterResult[dict[str, Any]]:
    """Create a reference axis along a principal direction.

    Wraps ``IModelDoc2::InsertAxis2(AutoSize)`` - note the interface: it is on
    ``IModelDoc2``, **not** ``IFeatureManager``. It builds an axis from two
    selected planes, so an axis is requested by naming the direction and the
    matching plane pair is selected here.

    ``InsertAxis2`` returns a plain boolean rather than the axis, so success is
    confirmed by the feature count rising.

    Args:
        adapter: A connected ``PyWin32Adapter`` with a valid ``currentModel``.
        reference: ``"x"``, ``"y"`` or ``"z"``.

    Returns:
        AdapterResult[dict[str, Any]]: The planes used and how the tree
        changed. ``ERROR`` for an unknown direction or when no axis appeared.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    key = str(reference or "").strip().lower().lstrip("+-")
    if key not in _AXIS_PLANE_PAIRS:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=(
                f"Unknown axis reference '{reference}'. "
                f"Use one of: {', '.join(sorted(_AXIS_PLANE_PAIRS))}."
            ),
        )

    plane_a, plane_b = _AXIS_PLANE_PAIRS[key]

    def _axis_operation() -> dict[str, Any]:
        before = _feature_count(adapter)
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        for index, plane in enumerate((plane_a, plane_b)):
            if not _select_reference_entity(adapter, plane, 0, append=index > 0):
                raise Exception(f"Failed to select '{plane}' for the axis")

        adapter._attempt(lambda: adapter.currentModel.InsertAxis2(True), default=None)

        after = _feature_count(adapter)
        if before is None or after is None:
            raise Exception(
                "The feature count could not be read, so whether an axis was "
                "created is unknown."
            )
        if after <= before:
            raise Exception(
                f"No reference axis was created from {plane_a} + {plane_b}. "
                "InsertAxis2 reports only a boolean and the feature tree is "
                "unchanged."
            )

        return {
            "reference": key,
            "planes": [plane_a, plane_b],
            "features_before": before,
            "features_after": after,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("create_axis", _axis_operation),
    )


def _create_reference_point_impl(
    adapter: Any,
    mode: str,
    x: float,
    y: float,
    z: float,
    distance: float | None,
    percent: float | None,
) -> AdapterResult[dict[str, Any]]:
    """Create a reference point on the active part.

    Two modes:

    * ``"along_curve"`` - selects the edge under the millimetre coordinate
      ``(x, y, z)`` and places a point ``distance`` mm, or ``percent``
      (0-100) of the edge length, from the edge start.
    * ``"face_center"`` - selects the face under ``(x, y, z)`` and places a
      point at its centroid.

    Coordinate selection uses ``IModelDocExtension::SelectByID2``; per this
    repo's runbook a ``ForceRebuild3`` is issued first so freshly created
    edges are tessellated, and the ``Callout`` argument is passed an explicit
    ``VT_DISPATCH`` null. ``InsertReferencePoint`` returns a Feature whether
    or not it produced anything, so the feature count is compared before and
    after.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.
        mode: ``"along_curve"`` or ``"face_center"``.
        x: X of a point on the target edge/face, in millimetres.
        y: Y of a point on the target edge/face, in millimetres.
        z: Z of a point on the target edge/face, in millimetres.
        distance: For ``along_curve``, offset from the edge start in mm.
        percent: For ``along_curve``, position as 0-100 of the edge length.
            Exactly one of ``distance`` / ``percent`` is required.

    Returns:
        AdapterResult[dict[str, Any]]: The mode, the coordinate and resolved
        parameter, and how the feature tree changed. ``ERROR`` for an unknown
        mode, a bad distance/percent combination, a failed selection, or when
        no new feature appeared.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    key = str(mode or "").strip().lower()
    if key not in ("along_curve", "face_center"):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=f"Unknown mode {mode!r}. Use 'along_curve' or 'face_center'.",
        )

    along_type = 0
    along_value = 0.0
    if key == "along_curve":
        if (distance is None) == (percent is None):
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="along_curve needs exactly one of distance or percent",
            )
        if distance is not None:
            if float(distance) <= 0.0:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error="distance must be positive",
                )
            along_type = _SW_REF_POINT_ALONG_CURVE_DISTANCE
            along_value = float(distance) / 1000.0
        else:
            if not 0.0 < float(percent) < 100.0:
                return AdapterResult(
                    status=AdapterResultStatus.ERROR,
                    error="percent must be between 0 and 100 (exclusive)",
                )
            along_type = _SW_REF_POINT_ALONG_CURVE_PERCENT
            along_value = float(percent) / 100.0

    def _point_operation() -> dict[str, Any]:
        model = adapter.currentModel
        before = _feature_count(adapter)
        adapter._attempt(lambda: model.ForceRebuild3(True), default=None)
        adapter._attempt(lambda: model.ClearSelection2(True), default=None)

        entity_type = "EDGE" if key == "along_curve" else "FACE"
        callout = _null_callout()
        selected = adapter._attempt(
            lambda: model.Extension.SelectByID2(
                "",
                entity_type,
                float(x) / 1000.0,
                float(y) / 1000.0,
                float(z) / 1000.0,
                False,
                0,
                callout,
                0,
            ),
            default=False,
        )
        if not selected:
            raise Exception(
                f"No {entity_type.lower()} found at ({x}, {y}, {z}) mm - the "
                "coordinate must lie on the target entity."
            )

        manager = sw_type_info.flagged(
            adapter._attempt(lambda: model.FeatureManager, default=None),
            "IFeatureManager",
        )
        if manager is None:
            raise Exception("Part has no FeatureManager")

        if key == "along_curve":
            adapter._attempt(
                lambda: manager.InsertReferencePoint(
                    _SW_REF_POINT_ALONG_CURVE, along_type, along_value, 1
                ),
                default=None,
            )
        else:
            adapter._attempt(
                lambda: manager.InsertReferencePoint(
                    _SW_REF_POINT_FACE_CENTER, 0, 0.0, 1
                ),
                default=None,
            )

        adapter._attempt(lambda: model.EditRebuild3(), default=None)
        after = _feature_count(adapter)
        if before is None or after is None:
            raise Exception(
                "The feature count could not be read, so whether a reference "
                "point was created is unknown."
            )
        if after <= before:
            raise Exception(
                "InsertReferencePoint added no feature - the selected entity "
                "may not support a reference point in this mode."
            )
        return {
            "mode": key,
            "at_mm": [x, y, z],
            "distance_mm": distance if key == "along_curve" else None,
            "percent": percent if key == "along_curve" else None,
            "features_before": before,
            "features_after": after,
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("create_reference_point", _point_operation),
    )


#: Selection marks ``InsertMirrorFeature`` expects, per the SolidWorks API
#: reference: features 1, faces 128, bodies 256, and the mirror plane 2.
#: Wrong marks and the call reports a feature while mirroring nothing.
_MIRROR_MARK_FEATURES = 1
_MIRROR_MARK_BODIES = 256
_MIRROR_MARK_PLANE = 2


def _mirror_feature_impl(
    adapter: Any,
    features: list[str],
    mirror_plane: str,
    merge: bool,
    mirror_bodies: bool,
) -> AdapterResult[dict[str, Any]]:
    """Select the sources and the plane, then call InsertMirrorFeature.

    Wraps ``IFeatureManager::InsertMirrorFeature(BMirrorBody,
    BGeometryPattern, BMerge, BKnit)``. There is no ``...2`` overload of this
    call. Everything it acts on must be pre-selected under the right mark, so
    the marks are the whole game - see ``_MIRROR_MARK_*``.

    Whether the mirror actually produced geometry is checked by the caller,
    which can read volume through ``get_mass_properties``.

    Args:
        adapter: A connected ``PyWin32Adapter`` with a valid ``currentModel``.
        features: Body or feature names to mirror.
        mirror_plane: Plane name to mirror about.
        merge: Merge the result with the original.
        mirror_bodies: Select and mirror whole bodies rather than features.

    Returns:
        AdapterResult[dict[str, Any]]: The mirror feature's name and inputs.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    names = [n for n in (features or []) if n]
    if not names:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="mirror_feature requires at least one body or feature name",
        )
    if not mirror_plane:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="mirror_feature requires a mirror plane name",
        )

    source_mark = _MIRROR_MARK_BODIES if mirror_bodies else _MIRROR_MARK_FEATURES
    entity_type = "SOLIDBODY" if mirror_bodies else None

    def _mirror_operation() -> dict[str, Any]:
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
        callout = _null_callout()

        for index, name in enumerate(names):
            append = index > 0
            selected = False
            if entity_type is not None:
                selected = bool(
                    adapter._attempt(
                        lambda n=name, a=append: (
                            adapter.currentModel.Extension.SelectByID2(
                                n,
                                entity_type,
                                0.0,
                                0.0,
                                0.0,
                                a,
                                source_mark,
                                callout,
                                0,
                            )
                        ),
                        default=False,
                    )
                )
            if not selected:
                selected = _select_named_feature(
                    adapter, name, source_mark, append=append
                )
            if not selected:
                kind = "body" if mirror_bodies else "feature"
                raise Exception(f"Failed to select {kind} to mirror: {name}")

        if not _select_reference_entity(
            adapter, mirror_plane, _MIRROR_MARK_PLANE, append=True
        ):
            raise Exception(f"Failed to select mirror plane: {mirror_plane}")

        feature_manager = sw_type_info.flagged(
            adapter.currentModel.FeatureManager, "IFeatureManager"
        )
        feature = adapter._attempt(
            lambda: feature_manager.InsertMirrorFeature(
                bool(mirror_bodies),  # BMirrorBody
                False,  # BGeometryPattern - solve the whole feature
                bool(merge),  # BMerge
                False,  # BKnit
            ),
            default=None,
        )
        if feature is None:
            raise Exception(
                f"InsertMirrorFeature returned nothing (sources={names}, "
                f"plane={mirror_plane})"
            )

        name = adapter._attempt(
            lambda: adapter._get_attr_or_call(feature, "Name"), default=None
        )
        return {
            # No invented fallback: an unreadable name is reported as None
            # rather than as the literal "Mirror", which would not resolve.
            "name": str(name) if name else None,
            "mirrored": names,
            "mirror_plane": mirror_plane,
            "merge": bool(merge),
            "mirror_bodies": bool(mirror_bodies),
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("mirror_feature", _mirror_operation),
    )


#: Selection marks ``FeatureCircularPattern5`` expects, per the SolidWorks API
#: reference: the direction axis is mark 1 and the features to pattern are
#: mark 4. These differ from the mirror marks - reusing those silently
#: produces a feature that patterns nothing.
_PATTERN_MARK_AXIS = 1
_PATTERN_MARK_FEATURES = 4


def _pattern_circular_impl(
    adapter: Any,
    features: list[str],
    axis: str,
    count: int,
    angle: float,
    equal_spacing: bool,
) -> AdapterResult[dict[str, Any]]:
    """Select the axis and features, then call FeatureCircularPattern5.

    This build exposes FeatureCircularPattern through ...5; v5 is used, with
    the 14 arguments it declares. ``DName`` is a direction *name string*, so
    the axis is both selected under mark 1 and named in the call.

    Whether anything was produced is checked by the caller, which can read
    volume through ``get_mass_properties``.

    Args:
        adapter: A connected ``PyWin32Adapter`` with a valid ``currentModel``.
        features: Feature names to pattern.
        axis: Axis name to rotate about.
        count: Total instances including the original.
        angle: Total spread in degrees.
        equal_spacing: Space instances evenly across ``angle``.

    Returns:
        AdapterResult[dict[str, Any]]: The pattern's name and inputs.

    Raises:
        Exception: Propagated through ``_handle_com_operation``.
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    names = [n for n in (features or []) if n]
    if not names:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="pattern_circular requires at least one feature name",
        )
    if not axis:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="pattern_circular requires an axis name to rotate about",
        )
    if int(count) < 2:
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error=(
                f"pattern_circular needs a count of at least 2 (got {count}); "
                "a pattern of one is just the original feature"
            ),
        )

    def _pattern_operation() -> dict[str, Any]:
        import math

        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
        callout = _null_callout()

        axis_selected = bool(
            adapter._attempt(
                lambda: adapter.currentModel.Extension.SelectByID2(
                    axis, "AXIS", 0.0, 0.0, 0.0, False, _PATTERN_MARK_AXIS, callout, 0
                ),
                default=False,
            )
        )
        if not axis_selected:
            raise Exception(
                f"Failed to select axis '{axis}'. Create one with create_axis "
                "first, and pass the name it returns."
            )

        for name in names:
            selected = bool(
                adapter._attempt(
                    lambda n=name: adapter.currentModel.Extension.SelectByID2(
                        n,
                        "BODYFEATURE",
                        0.0,
                        0.0,
                        0.0,
                        True,
                        _PATTERN_MARK_FEATURES,
                        callout,
                        0,
                    ),
                    default=False,
                )
            )
            if not selected:
                selected = _select_named_feature(
                    adapter, name, _PATTERN_MARK_FEATURES, append=True
                )
            if not selected:
                raise Exception(f"Failed to select feature to pattern: {name}")

        feature_manager = sw_type_info.flagged(
            adapter.currentModel.FeatureManager, "IFeatureManager"
        )
        feature = adapter._attempt(
            lambda: feature_manager.FeatureCircularPattern5(
                int(count),  # Number
                math.radians(float(angle)),  # Spacing (radians)
                False,  # FlipDirection
                axis,  # DName
                False,  # GeometryPattern
                bool(equal_spacing),  # EqualSpacing
                False,  # VaryInstance
                False,  # SyncSubAssemblies
                False,  # BDir2
                False,  # BSymmetric
                0,  # Number2
                0.0,  # Spacing2
                "",  # DName2
                False,  # EqualSpacing2
            ),
            default=None,
        )
        if feature is None:
            raise Exception(
                f"FeatureCircularPattern5 returned nothing (features={names}, "
                f"axis={axis})"
            )

        pattern_name = adapter._attempt(
            lambda: adapter._get_attr_or_call(feature, "Name"), default=None
        )
        return {
            "name": str(pattern_name) if pattern_name else None,
            "patterned": names,
            "axis": axis,
            "count": int(count),
            "angle": float(angle),
            "equal_spacing": bool(equal_spacing),
        }

    return cast(
        AdapterResult[dict[str, Any]],
        adapter._handle_com_operation("pattern_circular", _pattern_operation),
    )
