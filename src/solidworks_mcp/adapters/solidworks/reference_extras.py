"""Reference and analysis extras on SolidWorks (queue item 39).

A coordinate system at a point, the Center of Mass point, the Bounding Box
feature and a face's section properties. How each call behaves was measured
on SolidWorks 2026 (design.md of the ``appearance-and-reference-tools``
change):

- ``InsertCoordinateSystem(xFlip, yFlip, zFlip)`` takes its origin selected
  with mark 1; with no axes selected they lie along the model's, and the
  three flip flags are ignored (checked live: ``True`` for z left +z). The origin
  is a point in a 3D sketch drawn for it, selected as ``Point1@<sketch>``.
  The transform reads back via ``GetCoordinateSystemTransformByName``.
- ``InsertCenterOfMass()``; the centre from ``CreateMassProperty`` on the
  flagged extension.
- ``InsertGlobalBoundingBox(0, hidden, surfaces, status)`` with ``status``
  passed by reference.
- ``GetSectionProperties2(None)`` reads the selected face.

Every call runs inside :meth:`_handle_com_operation`, on the connect thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from ...exceptions import InputRefused
from .. import appearance_rules as rules
from .. import sw_type_info
from ..base import (
    AdapterResult,
    AdapterResultStatus,
    BoundingBoxParameters,
    CoordinateSystemParameters,
    SectionPropertiesParameters,
)
from .appearance import select_face_at
from .com_utils import long_ref
from .features import _null_callout

#: ``swGlobalBoundingBoxFitOptions_e.swBoundingBoxType_BestFit``.
_BEST_FIT = 0
#: The selection mark ``InsertCoordinateSystem`` reads its origin by.
_MARK_ORIGIN = 1
#: ``IFeature.GetTypeName2`` of the Center of Mass point.
_CENTER_OF_MASS_TYPE = "CenterOfMass"
#: ``IFeature.GetTypeName2`` of the Bounding Box feature.
_BOUNDING_BOX_TYPE = "BoundingBoxProfileFeat"


class SolidWorksReferenceExtrasMixin:
    """Coordinate system, centre of mass, bounding box, section properties."""

    def _reference_call(
        self, operation: str, build: Callable[[], dict[str, Any]]
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` inside the COM boundary, on an open document."""
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(operation, build),
        )

    def _extension(self) -> Any:
        """The model's ``IModelDocExtension``, flagged (unflagged, its methods
        read as properties)."""
        adapter: Any = self
        return sw_type_info.flagged(
            adapter.currentModel.Extension, "IModelDocExtension"
        )

    def _features_of_type(self, type_name: str) -> list[str]:
        """The names of the features whose ``GetTypeName2`` is ``type_name``."""
        adapter: Any = self
        found: list[str] = []
        feature = adapter._attempt(lambda: adapter.currentModel.FirstFeature())
        while feature is not None:
            flagged = sw_type_info.flagged(feature, "IFeature")
            if adapter._attempt(lambda f=flagged: f.GetTypeName2()) == type_name:
                found.append(str(adapter._attempt(lambda f=flagged: f.Name)))
            feature = adapter._attempt(lambda f=flagged: f.GetNextFeature())
        return found

    async def create_coordinate_system(
        self, params: CoordinateSystemParameters
    ) -> AdapterResult[dict[str, Any]]:
        """A coordinate system at a point, with the model's axes.

        Args:
            params: The origin (mm).

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, ``sketch`` (the 3D sketch
            holding the origin point), and the transform read back:
            ``origin_mm`` and ``x_axis``, ``y_axis``, ``z_axis``.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            if len(params.origin) != 3:
                raise InputRefused("origin must be [x, y, z] in mm.")
            model = adapter.currentModel
            sketcher = sw_type_info.flagged(model.SketchManager, "ISketchManager")
            x, y, z = (float(v) / 1000.0 for v in params.origin)
            sketcher.Insert3DSketch(True)
            point = adapter._attempt(lambda: sketcher.CreatePoint(x, y, z))
            sketcher.Insert3DSketch(True)
            last = adapter._attempt(lambda: model.FeatureByPositionReverse(0))
            sketch = str(
                adapter._attempt(lambda: sw_type_info.flagged(last, "IFeature").Name)
            )
            if point is None or not sketch:
                raise RuntimeError(
                    "SolidWorks drew no origin point for the coordinate system."
                )
            adapter._attempt(lambda: model.ClearSelection2(True))
            extension = self._extension()
            extension.SelectByID2(
                f"Point1@{sketch}",
                "EXTSKETCHPOINT",
                0,
                0,
                0,
                False,
                _MARK_ORIGIN,
                _null_callout(),
                0,
            )
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.InsertCoordinateSystem(False, False, False)
            adapter._attempt(lambda: model.ClearSelection2(True))
            if feature is None:
                raise RuntimeError("SolidWorks made no coordinate system.")
            name = str(sw_type_info.flagged(feature, "IFeature").Name)
            transform = extension.GetCoordinateSystemTransformByName(name)
            return {
                "name": name,
                "sketch": sketch,
                **rules.transform_reply(adapter._attempt(lambda: transform.ArrayData)),
            }

        return self._reference_call("create_coordinate_system", build)

    async def create_center_of_mass_point(self) -> AdapterResult[dict[str, Any]]:
        """SolidWorks's Center of Mass point on the active part.

        Returns:
            AdapterResult[dict[str, Any]]: ``name`` and
            ``center_of_mass_mm``.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            if not adapter._measure_bodies():
                raise InputRefused("The part has no solid body, so no centre of mass.")
            existing = self._features_of_type(_CENTER_OF_MASS_TYPE)
            if existing:
                raise InputRefused(
                    f"The part has a Center of Mass point already ("
                    f"'{existing[0]}'); a part has one at most."
                )
            model = adapter.currentModel
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.InsertCenterOfMass()
            if feature is None:
                raise RuntimeError("SolidWorks made no Center of Mass point.")
            mass = sw_type_info.flagged(
                self._extension().CreateMassProperty(), "IMassProperty"
            )
            centre = adapter._attempt(lambda: mass.CenterOfMass)
            return {
                "name": str(sw_type_info.flagged(feature, "IFeature").Name),
                "center_of_mass_mm": [round(float(v) * 1000, 4) for v in centre]
                if isinstance(centre, (list, tuple))
                else None,
            }

        return self._reference_call("create_center_of_mass_point", build)

    async def create_bounding_box(
        self, params: BoundingBoxParameters
    ) -> AdapterResult[dict[str, Any]]:
        """SolidWorks's Bounding Box feature around the part's bodies.

        Args:
            params: Whether to include hidden bodies.

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, ``size_mm`` and the box's
            ``min_mm`` and ``max_mm`` corners (the bodies' box in model axes).
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            measured = adapter._measure_bodies()
            if not measured:
                raise InputRefused("The part has no solid body to box.")
            existing = self._features_of_type(_BOUNDING_BOX_TYPE)
            if existing:
                raise InputRefused(
                    f"The part has a bounding box already ('{existing[0]}'); a "
                    "part has one at most."
                )
            model = adapter.currentModel
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            status = long_ref(0)
            feature = manager.InsertGlobalBoundingBox(
                _BEST_FIT, params.include_hidden, False, status
            )
            if feature is None:
                code = adapter._attempt(lambda: status.value, default=status)
                raise RuntimeError(f"SolidWorks made no bounding box (status {code}).")
            states = [state for state, _ in measured]
            low = [min(s.box_min[i] for s in states) for i in range(3)]
            high = [max(s.box_max[i] for s in states) for i in range(3)]
            return {
                "name": str(sw_type_info.flagged(feature, "IFeature").Name),
                "size_mm": [round(high[i] - low[i], 4) for i in range(3)],
                "min_mm": [round(v, 4) for v in low],
                "max_mm": [round(v, 4) for v in high],
            }

        return self._reference_call("create_bounding_box", build)

    async def get_section_properties(
        self, params: SectionPropertiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Area, centroid and second moments of area of a planar face.

        Args:
            params: A point on the face (mm).

        Returns:
            AdapterResult[dict[str, Any]]: ``face_point`` and the properties
            from :func:`..appearance_rules.section_reply`.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            if len(params.face_point) != 3:
                raise InputRefused("face_point must be [x, y, z] in mm.")
            select_face_at(adapter, params.face_point)
            # GetSectionProperties2 reads the selection; an array of the
            # face returned status 1 and zeros (probe, SolidWorks 2026).
            values = adapter._attempt(
                lambda: self._extension().GetSectionProperties2(None)
            )
            adapter._attempt(lambda: adapter.currentModel.ClearSelection2(True))
            return {
                "face_point": list(params.face_point),
                **rules.section_reply(values),
            }

        return self._reference_call("get_section_properties", build)
