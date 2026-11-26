"""Helices and sweeps: ``create_helix``, ``create_sweep`` and ``create_cut_sweep``.

Queue item 34 (spec ``tools/helix`` and ``tools/swept-features``). Inputs
are millimetres and degrees; COM takes metres and radians. What SolidWorks
2026 does was settled by a live probe on 2026-11-24 (design, "What the live
demo has to settle"):

- ``IModelDoc2.InsertHelix`` takes a closed, selected sketch holding one
  circle and returns nothing; the new feature is the ``Helix`` that wasn't
  in the tree before.
- The helix's start, end and length are read from its curve
  (``IReferenceCurve.GetFirstSegment``), not worked out.
- Both sweeps take the profile under mark 1 and the path under mark 4; with
  ``CircularProfile`` only the path is selected.

Both sweeps are judged by the part's volume (``_measured``): a boss sweep
must add material and a cut sweep remove it, or the feature is deleted
again and the call fails.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any, cast

from ...exceptions import InputRefused
from .. import sw_type_info
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    HelixParameters,
    SolidWorksFeature,
    SweepParameters,
)
from ..helix_geometry import HELIX_DEFINED_BY, helix_length, helix_values
from .com_utils import as_list
from .features import _profile_feature_names, _select_named_feature, _tree_features

#: ``swSketchSegments_e``: the segment kinds, named for an error message.
_SEGMENT_KINDS: dict[int, str] = {
    0: "line",
    1: "arc",
    2: "ellipse",
    3: "spline",
    4: "text",
    5: "parabola",
}
#: ``swSketchSegments_e.swSketchARC``.
_ARC = 1
#: ``swTwistControlType_e``: follow the path, or twist at a constant rate.
_FOLLOW_PATH, _CONSTANT_TWIST = 0, 8
#: Selection marks for a sweep (``IFeatureManager`` sweep contract).
_MARK_PROFILE, _MARK_PATH = 1, 4


def _mm(point: Any) -> list[float] | None:
    """A point in metres, as model mm rounded to a micrometre."""
    values = as_list(point)
    if len(values) < 3:
        return None
    return [round(float(v) * 1000, 3) for v in values[:3]]


def _plural(count: int, word: str) -> str:
    """``"1 line"``, ``"2 lines"``."""
    return f"{count} {word}{'' if count == 1 else 's'}"


class SolidWorksSweptMixin:
    """``create_helix``, ``create_sweep`` and ``create_cut_sweep``."""

    # ── helix ────────────────────────────────────────────────────────────

    def _base_circle_diameter(self, feature: Any, name: str) -> float:
        """The diameter, mm, of the one circle a helix's base sketch holds.

        Args:
            feature: The sketch's ``IFeature``.
            name: The sketch's name, for the error message.

        Returns:
            float: The circle's diameter.

        Raises:
            InputRefused: The sketch holds anything other than one circle.
        """
        adapter: Any = self
        sketch = adapter._attempt(
            lambda: sw_type_info.flagged(
                sw_type_info.flagged(feature, "IFeature").GetSpecificFeature2(),
                "ISketch",
            ),
            default=None,
        )
        segments = as_list(
            adapter._attempt(lambda: sketch.GetSketchSegments(), default=None)
            if sketch is not None
            else None
        )
        radii: list[float] = []
        others: Counter[str] = Counter()
        for segment in segments:
            kind = adapter._attempt(
                lambda s=segment: sw_type_info.flagged(s, "ISketchSegment").GetType(),
                default=None,
            )
            if kind == _ARC:
                arc = sw_type_info.flagged(segment, "ISketchArc")
                if adapter._attempt(lambda a=arc: bool(a.IsCircle()), default=False):
                    radii.append(float(adapter._attempt(arc.GetRadius, default=0.0)))
                    continue
            unknown = "unreadable entity" if kind is None else "other entity"
            others[_SEGMENT_KINDS.get(kind, unknown)] += 1
        if len(radii) == 1 and not others:
            return radii[0] * 2000
        held = [_plural(len(radii), "circle")] if radii else []
        held += [_plural(count, kind) for kind, count in sorted(others.items())]
        raise InputRefused(
            f"A helix's base sketch must hold exactly one circle (its diameter "
            f"and centre set the helix's); '{name}' holds "
            f"{', '.join(held) if held else 'nothing'}."
        )

    def _curve_reading(self, feature: Any) -> dict[str, Any] | None:
        """A helix's start, end and length, read from its curve.

        Args:
            feature: The helix's ``IFeature``.

        Returns:
            dict[str, Any] | None: ``start_point_mm``, ``end_point_mm`` and
            ``length_mm``; None when the curve can't be read.
        """
        adapter: Any = self

        def read() -> dict[str, Any]:
            curve = sw_type_info.flagged(
                sw_type_info.flagged(feature, "IFeature").GetSpecificFeature2(),
                "IReferenceCurve",
            )
            edge = sw_type_info.flagged(curve.GetFirstSegment(), "IEdge")
            params = sw_type_info.flagged(edge.GetCurveParams3(), "ICurveParamData")
            length = sw_type_info.flagged(edge.GetCurve(), "ICurve").GetLength3(
                params.UMinValue, params.UMaxValue
            )
            return {
                "start_point_mm": _mm(params.StartPoint),
                "end_point_mm": _mm(params.EndPoint),
                "length_mm": round(float(length) * 1000, 3),
            }

        return cast("dict[str, Any] | None", adapter._attempt(read, default=None))

    async def create_helix(
        self, params: HelixParameters
    ) -> AdapterResult[dict[str, Any]]:
        """A helix, or a flat spiral, on a sketch holding one circle.

        The circle's diameter is the helix's and its centre is on the
        helix's axis, normal to the sketch. Two of height, pitch and
        revolutions define it (``params.defined_by``); the third is worked
        out. The start point, end point and length are read from the curve,
        so a sweep profile can be drawn where the helix starts.

        Args:
            params: The base sketch, how the helix is defined and its options.

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, ``sketch``,
            ``defined_by``, ``height_mm``, ``pitch_mm``, ``revolutions``,
            ``diameter_mm``, ``length_mm``, ``length_measured``,
            ``start_point_mm``, ``end_point_mm`` and the options used.

        Example::

            await adapter.create_helix(
                HelixParameters(sketch="Sketch1", height=48, pitch=6)
            )  # data["revolutions"] == 8
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )

        def build() -> dict[str, Any]:
            height, pitch, revolutions = helix_values(
                params.defined_by, params.height, params.pitch, params.revolutions
            )
            model = adapter.currentModel
            name = params.sketch.split("@", 1)[0]
            feature = adapter._attempt(lambda: model.FeatureByName(name), default=None)
            if feature is None:
                found = _profile_feature_names(adapter)
                raise InputRefused(
                    f"No sketch named '{name}' for the helix. Sketches: "
                    f"{', '.join(found) if found else 'none'}."
                )
            diameter = self._base_circle_diameter(feature, name)
            spiral = params.defined_by == "spiral"
            tapered = bool(params.taper_angle) and not spiral
            # InsertHelix uses the selected sketch, which must be closed.
            model.ClearSelection2(True)
            if not _select_named_feature(adapter, name, 0, False):
                raise LookupError(f"Couldn't select the sketch '{name}'.")
            before = {feature_name for _, feature_name in _tree_features(adapter)}
            sw_type_info.flagged(model, "IModelDoc2").InsertHelix(
                bool(params.reverse),  # Reversed
                bool(params.clockwise),  # Clockwised
                tapered,  # Tapered
                bool(params.taper_outward),  # Outward
                HELIX_DEFINED_BY[params.defined_by],  # Helixdef
                height / 1000,  # Height (m)
                pitch / 1000,  # Pitch (m)
                revolutions,  # Revolution
                math.radians(params.taper_angle or 0.0) if tapered else 0.0,
                math.radians(params.start_angle),  # Startangle
            )
            model.ClearSelection2(True)
            # InsertHelix returns nothing: the helix is the new Helix feature.
            made = [
                feature_name
                for kind, feature_name in _tree_features(adapter)
                if feature_name not in before and kind == "Helix"
            ]
            if not made:
                raise RuntimeError(
                    f"SolidWorks made no helix on '{name}'; check the circle is "
                    "the sketch's only entity and the values are possible."
                )
            helix = made[-1]
            curve = self._curve_reading(model.FeatureByName(helix))
            worked_out = helix_length(
                diameter,
                pitch,
                revolutions,
                spiral=spiral,
                height=height,
                taper_angle=params.taper_angle if tapered else None,
                taper_outward=params.taper_outward,
            )
            return {
                "name": helix,
                "sketch": name,
                "defined_by": params.defined_by,
                "height_mm": round(height, 6),
                "pitch_mm": round(pitch, 6),
                "revolutions": round(revolutions, 6),
                "diameter_mm": round(diameter, 6),
                "clockwise": bool(params.clockwise),
                "reverse": bool(params.reverse),
                "start_angle": float(params.start_angle),
                "taper_angle": params.taper_angle if tapered else None,
                "taper_outward": bool(params.taper_outward) if tapered else None,
                # Read from the curve; worked out only when it can't be read.
                "length_mm": curve["length_mm"] if curve else round(worked_out, 3),
                "length_measured": curve is not None,
                "start_point_mm": curve["start_point_mm"] if curve else None,
                "end_point_mm": curve["end_point_mm"] if curve else None,
            }

        return adapter._handle_com_operation("create_helix", build)  # type: ignore[no-any-return]

    # ── sweeps ───────────────────────────────────────────────────────────

    def _sweep_sketches(
        self, params: SweepParameters, operation: str
    ) -> tuple[str, str | None]:
        """The path's and the profile's names, as the tree spells them.

        Args:
            params: The sweep's path and profile choice.
            operation: ``create_sweep`` or ``create_cut_sweep``, for messages.

        Returns:
            tuple[str, str | None]: The path and the profile sketch; the
            profile is None for a circular profile.

        Raises:
            InputRefused: The path doesn't exist, the profile is the path or
                doesn't exist, or there is no sketch to use as the profile.
        """
        adapter: Any = self
        sketches = _profile_feature_names(adapter)
        listed = ", ".join(sketches) if sketches else "none"

        def spelled(name: str) -> str:
            bare = name.split("@", 1)[0]
            return next((s for s in sketches if s.lower() == bare.lower()), bare)

        path = spelled(params.path)
        found = adapter._attempt(
            lambda: adapter.currentModel.FeatureByName(path), default=None
        )
        if found is None:
            raise InputRefused(
                f"{operation}: no sketch or curve named '{params.path}' for the "
                f"path. Sketches: {listed}."
            )
        if params.circular_profile_diameter is not None:
            return path, None
        if params.profile:
            profile = spelled(params.profile)
            if profile == path:
                raise InputRefused(
                    f"{operation}: the profile '{params.profile}' is the path "
                    f"itself; name another sketch. Sketches: {listed}."
                )
            if profile not in sketches:
                raise InputRefused(
                    f"{operation}: no sketch named '{params.profile}' for the "
                    f"profile. Sketches: {listed}."
                )
            return path, profile
        # The sketch closed last, unless it is the path; then the latest
        # other one. Latest, not first: a helix's base-circle sketch comes
        # before the profile drawn at its start.
        last = getattr(adapter, "_last_sketch_name", None)
        if last and last != path and last in sketches:
            return path, last
        profile_name = next((s for s in reversed(sketches) if s != path), None)
        if profile_name is None:
            raise InputRefused(
                f"{operation} needs a profile sketch distinct from the path "
                f"'{params.path}' (or circular_profile_diameter). Sketches: "
                f"{listed}."
            )
        return path, profile_name

    async def _sweep(
        self, params: SweepParameters, *, cut: bool
    ) -> AdapterResult[SolidWorksFeature]:
        """A boss or cut sweep, judged by the volume.

        Args:
            params: The path, the profile choice and the twist.
            cut: Remove material (``InsertCutSwept5``) rather than add it
                (``InsertProtrusionSwept4``).

        Returns:
            AdapterResult[SolidWorksFeature]: The sweep, its choices and the
            volume before, after and change in ``parameters``.
        """
        adapter: Any = self
        operation = "create_cut_sweep" if cut else "create_sweep"
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        if not params.path:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"{operation} needs a 'path': a sketch or a curve's name.",
            )
        diameter = params.circular_profile_diameter
        if diameter is not None and diameter <= 0:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"circular_profile_diameter must be greater than 0 (got {diameter:g}).",
            )

        def build() -> dict[str, Any]:
            path, profile = self._sweep_sketches(params, operation)
            model = adapter.currentModel
            adapter._attempt(lambda: model.ClearSelection2(True), default=None)
            if profile is not None and not _select_named_feature(
                adapter, profile, _MARK_PROFILE, False
            ):
                raise LookupError(f"Failed to select sweep profile sketch: {profile}")
            if not _select_named_feature(
                adapter, path, _MARK_PATH, profile is not None
            ):
                raise LookupError(f"Failed to select sweep path: {path}")
            twist = bool(params.twist_along_path)
            twist_rad = math.radians(params.twist_angle) if twist else 0.0
            control = _CONSTANT_TWIST if twist else _FOLLOW_PATH
            circular = diameter is not None
            diameter_m = (diameter or 0.0) / 1000
            manager = model.FeatureManager
            if cut:
                feature = manager.InsertCutSwept5(
                    False,  # Propagate
                    False,  # Alignment
                    control,  # TwistCtrlOption (swTwistControlType_e)
                    False,  # KeepTangency
                    False,  # BAdvancedSmoothing
                    0,  # StartMatchingType
                    0,  # EndMatchingType
                    False,  # IsThinBody
                    0.0,  # Thickness1
                    0.0,  # Thickness2
                    0,  # ThinType
                    0,  # PathAlign
                    True,  # UseFeatScope
                    True,  # UseAutoSelect
                    twist_rad,  # TwistAngle
                    True,  # BMergeSmoothFaces
                    False,  # AssemblyFeatureScope
                    False,  # AutoSelectComponents
                    False,  # PropagateFeatureToParts
                    circular,  # CircularProfile
                    diameter_m,  # CircularProfileDiameter
                    0,  # Direction
                )
            else:
                feature = manager.InsertProtrusionSwept4(
                    False,  # Propagate
                    False,  # Alignment
                    control,  # TwistCtrlOption (swTwistControlType_e)
                    False,  # KeepTangency
                    False,  # BAdvancedSmoothing
                    0,  # StartMatchingType
                    0,  # EndMatchingType
                    False,  # IsThinBody
                    0.0,  # Thickness1
                    0.0,  # Thickness2
                    0,  # ThinType
                    0,  # PathAlign
                    bool(params.merge_result),  # Merge
                    True,  # UseFeatScope
                    True,  # UseAutoSelect
                    twist_rad,  # TwistAngle
                    True,  # BMergeSmoothFaces
                    circular,  # CircularProfile
                    diameter_m,  # CircularProfileDiameter
                    0,  # Direction
                )
            adapter._attempt(lambda: model.ClearSelection2(True), default=None)
            if not feature:
                made_from = f"a {diameter:g} mm circle" if circular else f"'{profile}'"
                raise RuntimeError(
                    f"Failed to create sweep feature: SolidWorks swept nothing "
                    f"from {made_from} along '{path}'. The profile must be "
                    "closed and cross the path's start."
                )
            data: dict[str, Any] = {
                "name": feature.Name,
                "id": adapter._get_feature_id(feature),
                "profile": profile,
                "circular_profile_diameter_mm": diameter,
                "path": path,
                "twist_along_path": twist,
                "twist_angle": float(params.twist_angle),
            }
            if not cut:
                data["merge_result"] = bool(params.merge_result)
            return data

        measured = await adapter._measured(
            operation,
            build,
            # A spring may be the part's first body.
            first_feature=not cut,
            direction=-1 if cut else 1,
        )
        if not measured.is_success:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=measured.error,
                execution_time=measured.execution_time,
            )
        data = dict(measured.data or {})
        name = str(data.pop("name"))
        feature_id = data.pop("id", None)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=SolidWorksFeature(
                name=name,
                type="CutSweep" if cut else "Sweep",
                id=feature_id,
                parameters=data,
                properties={"created": datetime.now().isoformat()},
            ),
            execution_time=measured.execution_time,
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Sweep a closed profile along a path, adding material.

        Uses ``IFeatureManager.InsertProtrusionSwept4``. The profile is a
        circle of ``circular_profile_diameter`` mm, the sketch named
        ``profile``, or the sketch closed last that isn't the path. The
        volume must grow, or the sweep is removed and the call fails.

        Args:
            params: The path, the profile choice, the twist and the merge.

        Returns:
            AdapterResult[SolidWorksFeature]: ``type`` ``"Sweep"``; its
            ``parameters`` hold the profile, the path and ``volume_before``,
            ``volume_after`` and ``volume_change`` (mm³).

        Example::

            await adapter.create_sweep(
                SweepParameters(path="Helix/Spiral1", circular_profile_diameter=2)
            )
        """
        return await self._sweep(params, cut=False)

    async def create_cut_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Sweep a closed profile along a path, removing material.

        Uses ``IFeatureManager.InsertCutSwept5`` with the same profile
        choices as :meth:`create_sweep`. The volume must shrink, or the cut
        is removed and the call fails.

        Args:
            params: The path, the profile choice and the twist
                (``merge_result`` is not used).

        Returns:
            AdapterResult[SolidWorksFeature]: ``type`` ``"CutSweep"``, with
            the volume before, after and change in ``parameters``.
        """
        return await self._sweep(params, cut=True)
