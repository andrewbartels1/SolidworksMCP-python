"""The mock adapter's helices and sweeps, with the real adapter's input errors.

A helix's numbers come from :mod:`helix_geometry`, as the real adapter's
fallback does; its start point is the base circle's radius along +x (the
mock has no sketch planes). Sweeps refuse what the real adapter refuses (no
path, a profile that is the path, no profile at all, a diameter of 0) and
report no volumes, since the mock has no solid.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from ..exceptions import InputRefused
from .base import (
    AdapterResult,
    AdapterResultStatus,
    HelixParameters,
    SolidWorksFeature,
    SweepParameters,
)
from .helix_geometry import helix_length, helix_values


def _error(message: str) -> AdapterResult[Any]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


class MockSweptMixin:
    """``create_helix``, ``create_sweep`` and ``create_cut_sweep``, in memory."""

    _current_model: Any
    _sketches: dict[str, str | None]
    _features: dict[str, SolidWorksFeature]
    _delays: dict[str, float]
    _operation_count: int

    def _circles(self) -> dict[str, list[float]]:
        """Each sketch's circle radii, mm, as ``add_circle`` records them."""
        if "_sketch_circles" not in self.__dict__:
            self._sketch_circles: dict[str, list[float]] = {}
        return self._sketch_circles

    def _curves(self) -> set[str]:
        """The helices made so far, which a sweep may use as its path."""
        if "_helix_names" not in self.__dict__:
            self._helix_names: set[str] = set()
        return self._helix_names

    def _spelled(self, name: str) -> str | None:
        """The sketch or helix ``name`` matches, without regard to case."""
        bare = name.split("@", 1)[0].lower()
        known = [*self._sketches, *sorted(self._curves())]
        return next((real for real in known if real.lower() == bare), None)

    async def create_helix(
        self, params: HelixParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock a helix on a sketch holding one circle.

        Args:
            params: The base sketch and the values that define the helix.

        Returns:
            AdapterResult[dict[str, Any]]: The real adapter's fields; the
            length is worked out and the start point is on +x.
        """
        if not self._current_model:
            return _error("No active model")
        try:
            height, pitch, revolutions = helix_values(
                params.defined_by, params.height, params.pitch, params.revolutions
            )
        except InputRefused as refused:
            return _error(str(refused))
        sketch = self._spelled(params.sketch)
        if sketch is None or sketch not in self._sketches:
            listed = ", ".join(self._sketches) or "none"
            return _error(
                f"No sketch named '{params.sketch}' for the helix. Sketches: {listed}."
            )
        radii = self._circles().get(sketch, [])
        if len(radii) != 1:
            return _error(
                "A helix's base sketch must hold exactly one circle (its "
                f"diameter and centre set the helix's); '{sketch}' holds "
                f"{len(radii)} circles."
            )
        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1
        spiral = params.defined_by == "spiral"
        tapered = bool(params.taper_angle) and not spiral
        diameter = radii[0] * 2
        name = f"Helix/Spiral{len(self._curves()) + 1}"
        self._curves().add(name)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": name,
                "sketch": sketch,
                "defined_by": params.defined_by,
                "height_mm": round(height, 6),
                "pitch_mm": round(pitch, 6),
                "revolutions": round(revolutions, 6),
                "diameter_mm": round(diameter, 6),
                "clockwise": params.clockwise,
                "reverse": params.reverse,
                "start_angle": float(params.start_angle),
                "taper_angle": params.taper_angle if tapered else None,
                "taper_outward": params.taper_outward if tapered else None,
                "length_mm": round(
                    helix_length(
                        diameter,
                        pitch,
                        revolutions,
                        spiral=spiral,
                        height=height,
                        taper_angle=params.taper_angle if tapered else None,
                        taper_outward=params.taper_outward,
                    ),
                    3,
                ),
                "length_measured": False,
                "start_point_mm": [round(diameter / 2, 3), 0.0, 0.0],
                "end_point_mm": None,
                "mock": True,
            },
            execution_time=self._delays["feature_operation"],
        )

    async def _mock_sweep(
        self, params: SweepParameters, *, cut: bool
    ) -> AdapterResult[SolidWorksFeature]:
        """A boss or cut sweep, after the real adapter's input checks.

        Args:
            params: The path, the profile choice and the twist.
            cut: A cut sweep rather than a boss.

        Returns:
            AdapterResult[SolidWorksFeature]: The sweep, or the refusal.
        """
        if not self._current_model:
            return _error("No active model")
        if not params.path:
            return _error("A sweep needs a 'path': a sketch or a curve's name.")
        diameter = params.circular_profile_diameter
        if diameter is not None and diameter <= 0:
            return _error(
                f"circular_profile_diameter must be greater than 0 (got {diameter:g})."
            )
        listed = ", ".join(self._sketches) or "none"
        path = self._spelled(params.path)
        if path is None:
            return _error(
                f"Found no sketch or curve named '{params.path}' for the "
                f"path. Sketches: {listed}."
            )
        profile: str | None = None
        if diameter is None:
            if params.profile:
                profile = self._spelled(params.profile)
                if profile == path:
                    return _error(
                        f"The profile '{params.profile}' is the path "
                        f"itself; name another sketch. Sketches: {listed}."
                    )
                if profile is None or profile not in self._sketches:
                    return _error(
                        f"Found no sketch named '{params.profile}' for the "
                        f"profile. Sketches: {listed}."
                    )
            else:
                last = getattr(self, "_last_sketch_name", None)
                others = [s for s in self._sketches if s != path]
                profile = last if last in others else (others[-1] if others else None)
                if profile is None:
                    return _error(
                        f"A sweep needs a profile sketch distinct from the "
                        f"path '{params.path}' (or circular_profile_diameter). "
                        f"Sketches: {listed}."
                    )
        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1
        kind = "CutSweep" if cut else "Sweep"
        parameters: dict[str, Any] = {
            "profile": profile,
            "circular_profile_diameter_mm": diameter,
            "path": path,
            "twist_along_path": params.twist_along_path,
            "twist_angle": params.twist_angle,
        }
        if not cut:
            parameters["merge_result"] = params.merge_result
        feature = SolidWorksFeature(
            name=f"{'Cut-Sweep' if cut else 'Boss-Sweep'}{len(self._features) + 1}",
            type=kind,
            id=str(uuid.uuid4()),
            parameters=parameters,
            properties={"created": datetime.now().isoformat(), "mock": True},
        )
        self._features[feature.id or feature.name] = feature
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=feature,
            execution_time=self._delays["feature_operation"],
        )

    async def create_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock a sweep that adds material.

        Args:
            params: The path, the profile choice, the twist and the merge.

        Returns:
            AdapterResult[SolidWorksFeature]: A ``Sweep`` feature.
        """
        return await self._mock_sweep(params, cut=False)

    async def create_cut_sweep(
        self, params: SweepParameters
    ) -> AdapterResult[SolidWorksFeature]:
        """Mock a sweep that removes material.

        Args:
            params: The path, the profile choice and the twist.

        Returns:
            AdapterResult[SolidWorksFeature]: A ``CutSweep`` feature.
        """
        return await self._mock_sweep(params, cut=True)
