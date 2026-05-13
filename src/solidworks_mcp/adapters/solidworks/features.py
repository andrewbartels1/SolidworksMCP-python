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

    def _revolve_operation() -> SolidWorksFeature:
        """Inner COM closure that builds and returns the revolve feature.

        Converts the degree angle to radians and invokes ``FeatureRevolve2``.

        Returns:
            SolidWorksFeature: Populated feature descriptor on success.

        Raises:
            Exception: If ``FeatureRevolve2`` returns ``None``.
        """
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

        if not feature:
            raise Exception("Failed to create revolve feature")

        return SolidWorksFeature(
            name=feature.Name,
            type="Revolve",
            id=adapter._get_feature_id(feature),
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


def _create_sweep_impl(
    adapter: Any, params: SweepParameters
) -> AdapterResult[SolidWorksFeature]:
    """Placeholder for sweep feature creation — not yet implemented.

    Retained for interface compatibility with the base ``SolidWorksAdapter``
    contract.  Callers that need a sweep should use a VBA macro via
    ``execute_macro`` until native support is added.

    Args:
        adapter: The active adapter instance (unused).
        params: Sweep parameter bag (unused).

    Returns:
        AdapterResult[SolidWorksFeature]: Always returns ``ERROR`` status with
        an explanatory message.

    Example::

        result = pywin32_feature_ops.create_sweep(adapter, params)
        # result.status == AdapterResultStatus.ERROR
        # result.error  == "Sweep feature not implemented ..."
    """
    _ = params
    return AdapterResult(
        status=AdapterResultStatus.ERROR,
        error="Sweep feature not implemented in basic pywin32 adapter",
    )


def _create_loft_impl(
    adapter: Any, params: LoftParameters
) -> AdapterResult[SolidWorksFeature]:
    """Placeholder for loft feature creation — not yet implemented.

    Retained for interface compatibility with the base ``SolidWorksAdapter``
    contract.  Callers that need a loft should use a VBA macro via
    ``execute_macro`` until native support is added.

    Args:
        adapter: The active adapter instance (unused).
        params: Loft parameter bag (unused).

    Returns:
        AdapterResult[SolidWorksFeature]: Always returns ``ERROR`` status with
        an explanatory message.

    Example::

        result = pywin32_feature_ops.create_loft(adapter, params)
        # result.status == AdapterResultStatus.ERROR
    """
    _ = params
    return AdapterResult(
        status=AdapterResultStatus.ERROR,
        error="Loft feature not implemented in basic pywin32 adapter",
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

    1. ``FeatureCut4`` — most modern (SolidWorks 2015+).
    2. ``FeatureCut3`` modern signature — SolidWorks 2010–2014.
    3. ``FeatureCut3`` legacy argument order — older installs.

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

    def _cut_operation() -> SolidWorksFeature:
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

        t0 = adapter.constants.get("swStartSketchPlane", 0)
        adapter._attempt(
            lambda: adapter.currentModel.ClearSelection2(True), default=None
        )
        sketch_selected = False

        try:
            feat_iter = adapter.currentModel.FirstFeature
            last_profile_feature = None
            while feat_iter:
                try:
                    type_name = feat_iter.GetTypeName2
                    if type_name == "ProfileFeature":
                        last_profile_feature = feat_iter
                except Exception:
                    pass
                try:
                    feat_iter = feat_iter.GetNextFeature
                except Exception:
                    break
            if last_profile_feature:
                sketch_selected = bool(
                    adapter._attempt(
                        lambda pf=last_profile_feature: pf.Select2(False, 0),
                        default=False,
                    )
                )
        except Exception:
            pass

        if not sketch_selected:
            for candidate in (
                [adapter._last_sketch_name] if adapter._last_sketch_name else []
            ) + [f"Sketch{n}" for n in range(adapter._sketch_count, 0, -1)]:
                sel_result = adapter._attempt(
                    lambda c=candidate: adapter.currentModel.Extension.SelectByID2(
                        c, "SKETCH", 0.0, 0.0, 0.0, False, 0, "", 0
                    ),
                    default=False,
                )
                sketch_selected = bool(sel_result)
                if sketch_selected:
                    adapter._last_sketch_name = candidate
                    break

        feature = None
        fallback_errors: list[str] = []

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
            feature, cut3_modern_error = adapter._attempt_with_error(
                lambda: feature_manager.FeatureCut3(
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
                )
            )
            if cut3_modern_error is not None:
                fallback_errors.append(f"FeatureCut3 modern: {cut3_modern_error}")

        if not feature:
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

    def _fillet_operation() -> SolidWorksFeature:
        """Inner COM closure that selects edges and invokes FeatureFillet3.

        Returns:
            SolidWorksFeature: Populated feature descriptor.

        Raises:
            Exception: If any edge selection fails or the feature is ``None``.
        """
        for edge_name in edge_names:
            selected = adapter.currentModel.Extension.SelectByID2(
                edge_name,
                "EDGE",
                0,
                0,
                0,
                True,
                0,
                None,
                0,
            )
            if not selected:
                raise Exception(f"Failed to select edge: {edge_name}")

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

        return SolidWorksFeature(
            name=feature.Name,
            type="Fillet",
            id=adapter._get_feature_id(feature),
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

    def _chamfer_operation() -> SolidWorksFeature:
        """Inner COM closure that selects edges and invokes FeatureChamfer.

        Returns:
            SolidWorksFeature: Populated feature descriptor.

        Raises:
            Exception: If any edge selection fails or the feature is ``None``.
        """
        for edge_name in edge_names:
            selected = adapter.currentModel.Extension.SelectByID2(
                edge_name, "EDGE", 0, 0, 0, True, 0, None, 0
            )
            if not selected:
                raise Exception(f"Failed to select edge: {edge_name}")

        feature_manager = adapter.currentModel.FeatureManager
        feature = feature_manager.FeatureChamfer(
            1,
            distance / 1000.0,
            distance / 1000.0,
            0,
            0,
            False,
            False,
            False,
            False,
        )

        if not feature:
            raise Exception("Failed to create chamfer")

        return SolidWorksFeature(
            name=feature.Name,
            type="Chamfer",
            id=adapter._get_feature_id(feature),
            parameters={"distance": distance, "edges": edge_names},
            properties={"created": datetime.now().isoformat()},
        )

    return cast(
        AdapterResult[SolidWorksFeature],
        adapter._handle_com_operation("add_chamfer", _chamfer_operation),
    )
