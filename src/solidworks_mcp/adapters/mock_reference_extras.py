"""The mock adapter's reference and analysis extras (queue item 39).

Worked out from the mock's box bodies (:mod:`mock_bodies`):

- the centre of mass is the volume-weighted centre of the boxes;
- the bounding box is the box around them;
- a face's section is a rectangle (the box face the point lies on), its
  second moments those of a rectangle about its centroid;
- a coordinate system has the model's axes.

A part has one Center of Mass point and one bounding box at most, as on
SolidWorks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..exceptions import InputRefused
from . import appearance_rules as rules
from .base import (
    AdapterResult,
    AdapterResultStatus,
    BoundingBoxParameters,
    CoordinateSystemParameters,
    SectionPropertiesParameters,
)
from .body_rules import BodyState
from .mock_appearance import face_of


def _error(message: str) -> AdapterResult[Any]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _ok(data: dict[str, Any]) -> AdapterResult[dict[str, Any]]:
    """A success result."""
    return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


def rectangle_section(body: BodyState, axis: int, side: int) -> dict[str, Any]:
    """A box face's section properties, in mm, as ``section_reply`` gives them.

    Args:
        body: The box.
        axis: The axis the face is normal to.
        side: 0 for the box's low face, 1 for its high face.

    Returns:
        dict[str, Any]: ``area_mm2``, ``centroid_mm``, the six moments,
        ``polar_moment_mm4`` and ``principal_moments_mm4``.
    """
    lengths = [body.box_max[i] - body.box_min[i] for i in range(3)]
    lengths[axis] = 0.0
    centroid = [(body.box_min[i] + body.box_max[i]) / 2 for i in range(3)]
    centroid[axis] = (body.box_min[axis], body.box_max[axis])[side]
    area = 1.0
    for i in range(3):
        if i != axis:
            area *= lengths[i]
    # S_j: the integral of the squared distance along axis j over the face.
    spread = [area * length**2 / 12 for length in lengths]
    moments = [sum(spread[j] for j in range(3) if j != i) for i in range(3)]
    in_plane = sorted(moments[i] for i in range(3) if i != axis)
    return {
        "area_mm2": round(area, 4),
        "centroid_mm": [round(v, 4) for v in centroid],
        "ixx": round(moments[0], 2),
        "iyy": round(moments[1], 2),
        "izz": round(moments[2], 2),
        "ixy": 0.0,
        "izx": 0.0,
        "iyz": 0.0,
        "polar_moment_mm4": round(moments[axis], 2),
        "principal_moments_mm4": [round(v, 2) for v in in_plane],
    }


class MockReferenceExtrasMixin:
    """Coordinate system, centre of mass, bounding box, section properties."""

    _current_model: Any
    #: From :class:`MockBodiesMixin`: the active part's box bodies.
    _bodies: Callable[[], list[BodyState]]

    def _reference_store(self) -> dict[int, dict[str, Any]]:
        """Each part's coordinate-system count, COM point and bounding box."""
        if "_mock_reference" not in self.__dict__:
            self._mock_reference: dict[int, dict[str, Any]] = {}
        return self._mock_reference

    def _part_reference(self) -> dict[str, Any]:
        """The active part's entry."""
        return self._reference_store().setdefault(
            id(self._current_model), {"systems": 0}
        )

    async def create_coordinate_system(
        self, params: CoordinateSystemParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: a coordinate system at a point.

        Args:
            params: The origin (mm).

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        if len(params.origin) != 3:
            return _error("origin must be [x, y, z] in mm.")
        entry = self._part_reference()
        entry["systems"] += 1
        count = entry["systems"]
        return _ok(
            {
                "name": f"Coordinate System{count}",
                "sketch": f"3DSketch{count}",
                "origin_mm": [float(v) for v in params.origin],
                **rules.model_axes(),
            }
        )

    async def create_center_of_mass_point(self) -> AdapterResult[dict[str, Any]]:
        """Mock: the Center of Mass point.

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        bodies = self._bodies()
        if not bodies:
            return _error("The part has no solid body, so no centre of mass.")
        entry = self._part_reference()
        if entry.get("com"):
            return _error(
                "The part has a Center of Mass point already ('Center of Mass'); "
                "a part has one at most."
            )
        entry["com"] = True
        total = sum(b.volume for b in bodies)
        centre = [
            sum(b.volume * (b.box_min[i] + b.box_max[i]) / 2 for b in bodies) / total
            for i in range(3)
        ]
        return _ok(
            {
                "name": "Center of Mass",
                "center_of_mass_mm": [round(v, 4) for v in centre],
            }
        )

    async def create_bounding_box(
        self, params: BoundingBoxParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: the Bounding Box feature.

        Args:
            params: Whether to include hidden bodies (the mock has none).

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        bodies = self._bodies()
        if not bodies:
            return _error("The part has no solid body to box.")
        entry = self._part_reference()
        if entry.get("box"):
            return _error(
                "The part has a bounding box already ('Bounding Box'); a part "
                "has one at most."
            )
        entry["box"] = True
        low = [min(b.box_min[i] for b in bodies) for i in range(3)]
        high = [max(b.box_max[i] for b in bodies) for i in range(3)]
        return _ok(
            {
                "name": "Bounding Box",
                "size_mm": [round(high[i] - low[i], 4) for i in range(3)],
                "min_mm": low,
                "max_mm": high,
            }
        )

    async def get_section_properties(
        self, params: SectionPropertiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: a box face's section properties.

        Args:
            params: A point on the face (mm).

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        if len(params.face_point) != 3:
            return _error("face_point must be [x, y, z] in mm.")
        try:
            body, axis, side = face_of(self._bodies(), list(params.face_point))
        except InputRefused as refused:
            return _error(str(refused))
        return _ok(
            {
                "face_point": list(params.face_point),
                **rectangle_section(body, axis, side),
            }
        )
