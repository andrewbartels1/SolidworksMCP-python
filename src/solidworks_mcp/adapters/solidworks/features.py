"""Feature-domain mixin for PyWin32 SolidWorks operations."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

from ..base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
    LoftParameters,
    RevolveParameters,
    SolidWorksFeature,
    SweepParameters,
)


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
        return _add_fillet_impl(self, radius, edge_names)

    async def add_chamfer(
        self, distance: float, edge_names: list[str]
    ) -> AdapterResult[SolidWorksFeature]:
        return _add_chamfer_impl(self, distance, edge_names)

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
        volume_before = before.data.volume if before.is_success and before.data else None

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
              directions from the sketch plane.
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

    def _extrusion_operation() -> SolidWorksFeature:  # pragma: no cover
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

        if normalized.thin_feature and normalized.thin_thickness:
            t0 = adapter.constants.get("swStartSketchPlane", 0)
            t1 = (
                adapter.constants["swEndCondMidPlane"]
                if normalized.both_directions
                else adapter.constants["swEndCondBlind"]
            )
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
            t0 = adapter.constants.get("swStartSketchPlane", 0)
            try:
                feature = feature_manager.FeatureExtrusion3(
                    True,
                    False,
                    normalized.reverse_direction,
                    adapter.constants["swEndCondBlind"],
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
                    adapter.constants["swEndCondBlind"],
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

    def _revolve_operation() -> SolidWorksFeature:  # pragma: no cover
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

        if revolve_sw_major == 33:  # pragma: no cover
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
                params.angle * 3.14159 / 180.0,
                (params.angle * 3.14159 / 180.0) if params.both_directions else 0.0,
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


def _flag_feature_methods(obj: Any, interface: str) -> None:  # pragma: no cover
    """Best-effort method flagging for a COM object via ``sw_type_info``.

    Flagging tells pywin32 late binding to resolve names like ``GetTypeName2``
    / ``GetNextFeature`` / ``FirstFeature`` as methods.  No-ops on plain test
    doubles (and any environment without the gen_py wrapper).

    Args:
        obj: The COM object (or test double) to flag.
        interface: SolidWorks interface name (e.g. ``"IFeature"``).
    """
    try:
        from solidworks_mcp.adapters import sw_type_info

        sw_type_info.flag_methods(obj, interface)
    except Exception:
        pass


def _flag_feature_members(obj: Any, *names: str) -> None:  # pragma: no cover
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
    try:
        from solidworks_mcp.adapters import sw_type_info

        sw_type_info.flag_members(obj, *names)
    except Exception:
        pass


#: Members read while walking the feature tree in ``_profile_feature_names``.
_TREE_WALK_MEMBERS = ("GetTypeName2", "GetNextFeature", "Name")


def _read_member(obj: Any, name: str) -> Any:  # pragma: no cover
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


def _profile_feature_names(adapter: Any) -> list[str]:  # pragma: no cover
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

    def _sweep_operation() -> SolidWorksFeature:  # pragma: no cover
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

    def _loft_operation() -> SolidWorksFeature:  # pragma: no cover
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
        def _tangency(value: str | None) -> int:  # pragma: no cover
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
    """Create a cut-extrude feature from the active sketch profile.

    The function first attempts to locate and select the sketch profile that
    should be cut.  It walks the feature tree looking for the most recent
    ``ProfileFeature``; if that fails, it falls back to the ``_last_sketch_name``
    tracker and then to an enumerated ``Sketch<N>`` name search.

    Three COM API variants are attempted in order of preference:

    1. ``FeatureCut4`` ΓÇö most modern (SolidWorks 2015+).
    2. ``FeatureCut3`` modern signature ΓÇö SolidWorks 2010ΓÇô2014.
    3. ``FeatureCut3`` legacy argument order ΓÇö older installs.

    All depth values are in millimetres and converted to metres internally.

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        params: Extrusion parameter bag reused for cut parameters:
            - ``depth`` (float): Cut depth in mm.
            - ``draft_angle`` (float): Draft angle in degrees.
            - ``reverse_direction`` (bool): Flip the cut direction.
            - ``end_condition`` (str): ``"Blind"`` (default) or
              ``"ThroughAll"`` / ``"through_all"``.
            - ``feature_scope`` (bool): Limit cut to selected bodies.
            - ``auto_select`` (bool): Auto-select bodies in scope.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Cut-Extrude"``.  On
        failure, ``status`` is ``ERROR`` and ``error`` lists every API
        variant that was tried.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when all
            three COM variants fail.

    Example::

        from solidworks_mcp.adapters.base import ExtrusionParameters
        from solidworks_mcp.adapters import pywin32_feature_ops

        params = ExtrusionParameters(depth=10.0, end_condition="ThroughAll")
        result = pywin32_feature_ops.create_cut_extrude(adapter, params)
        print(result.data.name)  # e.g. "Cut-Extrude1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _cut_operation() -> SolidWorksFeature:  # pragma: no cover
        """Inner COM closure that locates the active sketch and performs the cut.

        Normalises ``params``, resolves the end-condition constant, selects the
        sketch profile, then cascades through three ``FeatureCut`` overloads.

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
            feature_scope=bool(getattr(params, "feature_scope", False)),
            auto_select=bool(getattr(params, "auto_select", True)),
        )
        feature_manager = adapter.currentModel.FeatureManager

        end_condition = (normalized.end_condition or "Blind").strip().lower()
        t1 = adapter.constants["swEndCondBlind"]
        depth_m = normalized.depth / 1000.0
        if end_condition in {"throughall", "through all", "through_all"}:
            t1 = adapter.constants["swEndCondThroughAll"]
        elif end_condition in {
            "throughallboth",
            "through all both",
            "through_all_both",
        }:
            t1 = adapter.constants["swEndCondThroughAllBoth"]

        t0 = adapter.constants.get("swStartSketchPlane", 0)
        feature = None
        fallback_errors: list[str] = []
        is_through = end_condition in {
            "throughall",
            "through all",
            "through_all",
            "throughallboth",
            "through all both",
            "through_all_both",
        }

        # Detect SW major version for FeatureCut4 parameter count
        # SW 2025 (major=33) verified with 27 params; other versions use 28.
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

        # 1. FeatureCut4 (SW 2015+)
        # SW 2025 (major=33): 27 params, the 27th being OptimizeGeometry.
        # It was omitted here, so the call passed 26 and SolidWorks answered
        # "Parameter not optional" for every cut.
        # SW 2026+ (major>=34): 28 params — adds OptimizeGeometry + PFeat.
        if sw_major == 33:
            feature, cut4_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut4(
                    is_through,  # Sd
                    False,  # Flip
                    normalized.reverse_direction,  # Dir
                    t1,  # T1
                    adapter.constants["swEndCondBlind"],  # T2
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
                    True,  # OptimizeGeometry
                )
            )
        elif sw_major >= 34:
            # SW 2026+ adds OptimizeGeometry as a 27th INPUT param.
            # PFeat is an OUT param (PARAMFLAG_FOUT|FRETVAL) — not passed by caller.
            feature, cut4_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut4(
                    is_through,  # Sd
                    False,  # Flip
                    normalized.reverse_direction,  # Dir
                    t1,  # T1
                    adapter.constants["swEndCondBlind"],  # T2
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
                    False,  # OptimizeGeometry (added in SW 2026)
                )
            )
        else:
            feature, cut4_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut4(
                    True,
                    False,
                    normalized.reverse_direction,
                    t1,
                    adapter.constants["swEndCondBlind"],
                    depth_m,
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
                    False,
                    normalized.feature_scope,
                    normalized.auto_select,
                    False,
                    False,
                    False,
                    t0,
                    0.0,
                    False,
                    False,
                )
            )
        if cut4_error is not None:
            fallback_errors.append(f"FeatureCut4: {cut4_error}")

        if not feature:
            # Implicit sketch context (from exit_sketch) was not picked up.
            # Try selecting the sketch explicitly before falling back to older API.
            adapter._attempt(
                lambda: adapter.currentModel.ClearSelection2(True), default=None
            )
            for candidate in (
                [adapter._last_sketch_name] if adapter._last_sketch_name else []
            ) + [f"Sketch{n}" for n in range(adapter._sketch_count, 0, -1)]:
                sel_ok = bool(
                    adapter._attempt(
                        lambda c=candidate: adapter.currentModel.Extension.SelectByID2(
                            c, "SKETCH", 0.0, 0.0, 0.0, False, 0, None, 0
                        ),
                        default=False,
                    )
                )
                if sel_ok:
                    adapter._last_sketch_name = candidate
                    break

        if not feature:
            # 2. FeatureCut3 modern (SW 2010+, 26 params, corrected for SW 2022)
            # Signature: Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
            #   Dang1, Dang2, OffsetReverse1, OffsetReverse2, TranslateSurface1,
            #   TranslateSurface2, NormalCut, UseFeatScope, UseAutoSelect,
            #   AssemblyFeatureScope, AutoSelectComponents, PropagateFeatureToParts,
            #   T0, StartOffset, FlipStartOffset
            feature, cut3_modern_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut3(
                    is_through,
                    normalized.reverse_direction,
                    False,
                    t1,
                    0,
                    normalized.depth / 1000.0,
                    normalized.depth / 1000.0,
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
                    False,
                    normalized.feature_scope,
                    normalized.auto_select,
                    False,
                    False,
                    False,
                    t0,
                    0.0,
                    False,
                )
            )
            if cut3_modern_error is not None:
                fallback_errors.append(f"FeatureCut3 modern: {cut3_modern_error}")

        if not feature:
            # 3. FeatureCut3 legacy (older installs, alternate arg order)
            feature, cut3_legacy_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut3(
                    True,
                    False,
                    normalized.reverse_direction,
                    adapter.constants["swEndCondBlind"],
                    adapter.constants["swEndCondBlind"],
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
                    False,
                    normalized.feature_scope,
                    normalized.auto_select,
                    normalized.depth / 1000.0,
                    0.0,
                )
            )
            if cut3_legacy_error is not None:
                fallback_errors.append(f"FeatureCut3 legacy: {cut3_legacy_error}")

        if not feature:
            if fallback_errors:
                raise Exception(
                    "Failed to create cut extrude feature. "
                    + " | ".join(fallback_errors)
                )
            raise Exception("Failed to create cut extrude feature")

        return SolidWorksFeature(
            name=feature.Name,
            type="Cut-Extrude",
            id=adapter._get_feature_id(feature),
            parameters={
                "depth": normalized.depth,
                "draft_angle": normalized.draft_angle,
                "reverse_direction": normalized.reverse_direction,
            },
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("create_cut_extrude", _cut_operation),
    )


def _parse_edge_spec(  # pragma: no cover
    edge_name: str,
) -> tuple[str, float, float, float]:
    """Parse an edge specification string into (SelectByID2 name, x, y, z).

    Supports two formats:
    - ``"Edge<1>"`` — name-based selection (x=y=z=0.0, SW looks up by topology name)
    - ``"x,y,z"`` — coordinate-based selection (name="", coordinate hint in metres)
    """
    parts = edge_name.split(",")
    if len(parts) == 3:
        try:
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            return "", x, y, z
        except ValueError:
            pass
    return edge_name, 0.0, 0.0, 0.0


def _select_edge_by_coord(  # pragma: no cover
    adapter: Any,
    x: float,
    y: float,
    z: float,
    append: bool,
    mark: int = 0,
) -> bool:
    """Select the edge nearest to (x, y, z) in metres via ``SelectByID2``.

    Calls ``ForceRebuild3`` on the first edge in the selection set so that
    recent features are fully tessellated and their edges are selectable.
    Tries the primary coordinate and several small radial/Y offsets to
    improve hit probability on curved edges.

    The ``Callout`` parameter of ``SelectByID2`` requires a VT_DISPATCH null
    VARIANT — passing plain Python ``None`` triggers DISP_E_TYPEMISMATCH.

    Returns True if an edge was successfully selected; False otherwise.
    """
    import math

    model = adapter.currentModel

    # Rebuild to tessellate geometry from recent features before the first
    # edge in the selection set (when append=False this is the first edge).
    if not append:
        adapter._attempt(lambda: model.ForceRebuild3(True), default=None)

    r = math.sqrt(x**2 + z**2)
    if r > 0:
        # Candidates: exact point plus small radial scale-in/out and Y offsets.
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
        candidates = [
            (x, y, z),
            (x, y * 0.999, z),
            (x, y * 1.001, z),
        ]

    # VT_DISPATCH null pointer — required by SelectByID2's Callout parameter.
    # Plain Python None marshals as VT_NULL which SW rejects with DISP_E_TYPEMISMATCH.
    try:
        import pythoncom
        import win32com.client as _win32com

        null_callout = _win32com.VARIANT(pythoncom.VT_DISPATCH, None)
    except Exception:
        null_callout = None  # fallback: may fail on some SW versions

    for cx, cy, cz in candidates:
        try:
            selected = bool(
                model.Extension.SelectByID2(
                    "", "EDGE", cx, cy, cz, append, mark, null_callout, 0
                )
            )
        except Exception:
            selected = False
        if selected:
            return True

    return False


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
            ``["Edge<1>", "Edge<2>"]``.

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

    def _fillet_operation() -> SolidWorksFeature:  # pragma: no cover
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

        # Clear any prior selection so the edge set is clean.
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        for idx, edge_name in enumerate(edge_names):
            sel_name, ex, ey, ez = _parse_edge_spec(edge_name)
            append = idx > 0  # first edge starts fresh, subsequent ones append
            if sel_name == "":
                # Coordinate-based: traverse body edges and pick the closest one.
                selected = _select_edge_by_coord(adapter, ex, ey, ez, append=append)
            else:
                selected = adapter._attempt(
                    lambda sn=sel_name, _x=ex, _y=ey, _z=ez, _ap=append: (
                        adapter.currentModel.Extension.SelectByID2(
                            sn, "EDGE", _x, _y, _z, _ap, 0, None, 0
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

        # Resolve the feature name — FeatureFillet3 on SW 2025+ returns an int,
        # not an IFeature, so we can only report a default name here.
        feature_name = "Fillet"
        if feature is not None and hasattr(feature, "Name"):
            try:
                feature_name = feature.Name or "Fillet"
            except Exception:
                pass

        return SolidWorksFeature(
            name=feature_name,
            type="Fillet",
            id=adapter._get_feature_id(feature) if feature else "",
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
    are in the selection set, ``FeatureChamfer`` is called in
    equal-distance mode (type ``1``).

    Args:
        adapter: A fully connected ``PyWin32Adapter`` with a non-``None``
            ``currentModel``.
        distance: Chamfer distance in **millimetres**.  Converted to metres
            internally.
        edge_names: List of SolidWorks edge entity names, e.g.
            ``["Edge<2>", "Edge<5>"]``.

    Returns:
        AdapterResult[SolidWorksFeature]: On success, ``data`` is a
        ``SolidWorksFeature`` whose ``type`` is ``"Chamfer"``.  On failure,
        ``status`` is ``ERROR``.

    Raises:
        Exception: Propagated through ``_handle_com_operation`` when an
            edge cannot be selected or ``FeatureChamfer`` returns ``None``.

    Example::

        result = pywin32_feature_ops.add_chamfer(
            adapter, distance=2.0, edge_names=["Edge<2>"]
        )
        print(result.data.name)  # e.g. "Chamfer1"
    """
    if not adapter.currentModel:
        return AdapterResult(status=AdapterResultStatus.ERROR, error="No active model")

    def _chamfer_operation() -> SolidWorksFeature:  # pragma: no cover
        """Inner COM closure that selects edges and invokes the chamfer API.

        Returns:
            SolidWorksFeature: Populated feature descriptor.

        Raises:
            Exception: If any edge selection fails or the feature is not created.
        """
        import math

        # Detect SW major version (same pattern as fillet).
        chamfer_sw_major = 0
        if getattr(adapter, "swApp", None):
            rev = adapter._attempt(
                lambda: adapter._get_attr_or_call(adapter.swApp, "RevisionNumber"),
                default="0",
            )
            try:
                chamfer_sw_major = int(str(rev).split(".")[0])
            except (ValueError, IndexError):
                chamfer_sw_major = 0

        # Clear any prior selection so the edge set is clean.
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )

        for idx, edge_name in enumerate(edge_names):
            sel_name, cx, cy, cz = _parse_edge_spec(edge_name)
            append = idx > 0
            if sel_name == "":
                selected = _select_edge_by_coord(
                    adapter, cx, cy, cz, append=append, mark=0
                )
            else:
                selected = adapter._attempt(
                    lambda sn=sel_name, _x=cx, _y=cy, _z=cz, _ap=append: (
                        adapter.currentModel.Extension.SelectByID2(
                            sn, "EDGE", _x, _y, _z, _ap, 0, None, 0
                        )
                    ),
                    default=False,
                )
            if not selected:
                raise Exception(f"Failed to select edge: {edge_name}")

        fm = adapter.currentModel.FeatureManager
        _flag_feature_methods(fm, "IFeatureManager")
        count_before = adapter._attempt(
            lambda: int(fm.GetFeatureCount(True) or 0), default=0
        )

        feature_name = "Chamfer"
        feature = None

        if chamfer_sw_major >= 33:
            # SW 2025+ (major >= 33): IModelDoc2.FeatureChamferType (8 params,
            # VT_VOID). Detect success via feature count change.
            adapter.currentModel.FeatureChamferType(
                0,  # ChamferType: 0 = swChamferType_EqualDistance
                distance / 1000.0,  # Width in metres
                math.pi / 4,  # 45° angle
                False,  # Flip
                0.0,  # OtherDist
                0.0,  # VertexChamDist1
                0.0,  # VertexChamDist2
                0.0,  # VertexChamDist3
            )
            count_after = adapter._attempt(
                lambda: int(fm.GetFeatureCount(True) or 0), default=0
            )
            if count_after <= count_before:
                raise Exception(
                    "Failed to create chamfer (IModelDoc2.FeatureChamferType;"
                    " feature count unchanged)"
                )
        else:
            # Older SW: IFeatureManager.InsertFeatureChamfer returns IFeature.
            feature, insert_err = adapter._attempt_with_error(
                lambda: fm.InsertFeatureChamfer(
                    1,  # Options
                    1,  # ChamferType = equal distance
                    distance / 1000.0,  # Width in metres
                    math.pi / 4,  # 45° angle
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


def _null_callout() -> Any:
    """Return a VT_DISPATCH null for ``SelectByID2``'s ``Callout`` parameter.

    A plain Python ``None`` marshals as ``VT_NULL``, which SolidWorks rejects
    with ``DISP_E_TYPEMISMATCH`` - measured as
    ``(-2147352571, 'Type mismatch.', None, 8)``. See runbook item 11.

    Returns:
        Any: A ``VARIANT(VT_DISPATCH, None)``, or ``None`` when pywin32 is
        unavailable (mock/Linux runs, where no COM call will be made anyway).
    """
    try:
        import pythoncom
        import win32com.client as _win32com
    except ImportError:  # pragma: no cover - Windows-only path
        return None
    return _win32com.VARIANT(pythoncom.VT_DISPATCH, None)


def _feature_count(adapter: Any) -> int | None:
    """Return how many features the active model has, or ``None``.

    Used to confirm an edit changed the tree rather than trusting a COM call
    that reports success without doing anything.

    ``IFeatureManager::GetFeatureCount`` is used rather than walking
    ``FirstFeature``/``GetNextFeature``: on SW 2025 that walk yields nothing
    even with each dispatch flagged for ``IFeature``, which makes the tree
    look empty instead of raising - so a "did anything change" check built on
    it would silently answer "no" every time.

    Args:
        adapter: A connected adapter with a valid ``currentModel``.

    Returns:
        int | None: The feature count, or ``None`` when it cannot be read -
        deliberately distinct from ``0``.
    """
    from .. import sw_type_info

    manager = adapter._attempt(
        lambda: adapter.currentModel.FeatureManager, default=None
    )
    if manager is None:
        return None
    flagged = sw_type_info.flagged(manager, "IFeatureManager")
    count = adapter._attempt(lambda: flagged.GetFeatureCount(True), default=None)
    return int(count) if isinstance(count, (int, float)) else None


def _select_reference_entity(adapter: Any, reference: str, mark: int, append: bool) -> bool:
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

        constraint = _REF_PLANE_DISTANCE
        value = float(offset) / 1000.0
        if flip:
            constraint |= _REF_PLANE_OPTION_FLIP

        from .. import sw_type_info

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
                                n, entity_type, 0.0, 0.0, 0.0, a, source_mark,
                                callout, 0,
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

        from .. import sw_type_info

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
