"""Sheet metal: base flange, edge flange, sketched bend, flat pattern (#57).

Queue item 15. Positions are millimetres in model space; COM takes metres
and radians. Each feature is judged by the volume before and after
(``_measured`` from the part-features mixin), because SolidWorks can
report success and build nothing.
"""

from __future__ import annotations

import math
from typing import Any, cast

from ...exceptions import InputRefused
from .. import sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import as_list, dispatch_array
from .features import _BodyEntityPicker, _null_callout, _select_named_feature

#: ``swBendAllowanceTypes_e.swBendAllowanceKFactor``.
_K_FACTOR = 2
#: ``swSheetMetalReliefTypes_e.swSheetMetalReliefRectangular``.
_RELIEF_RECTANGULAR = 1
#: ``swEndConditions_e.swEndCondBlind``.
_BLIND = 0
#: ``swFeatureNameID_e.swFmSketchBend``.
_SKETCH_BEND = 35
#: ``swFlangePositionTypes_e.swFlangePositionTypeMaterialInside``.
_MATERIAL_INSIDE = 1
#: ``swFlangeDimTypes_e.swFlangeDimTypeOuterVirtualSharp``.
_OUTER_VIRTUAL_SHARP = 1
#: ``swInsertEdgeFlangeOptions_e``: use the sheet's radius, flip the side.
_EDGE_DEFAULT_RADIUS, _EDGE_FLIP = 1, 2
#: An edge point further than this from every edge picks nothing (metres).
_EDGE_TOLERANCE_M = 0.001
#: Told to the agent whenever a later tool finds no sheet metal.
_START_WITH = "Start with create_base_flange, which makes a part sheet metal."


def _m(mm: float) -> float:
    """Millimetres to metres."""
    return float(mm) / 1000.0


class SolidWorksSheetMetalMixin:
    """``create_base_flange``, ``add_edge_flange``, ``create_sketched_bend``, ``set_flat_pattern``."""

    def _is_sheet_metal(self) -> bool:
        """Whether the active part has a sheet-metal body."""
        adapter: Any = self
        model = adapter.currentModel
        bodies = as_list(
            adapter._attempt(lambda: model.GetBodies2(0, False), default=None)
        )
        return any(
            adapter._attempt(
                lambda b=b: sw_type_info.flagged(b, "IBody2").IsSheetMetal(),
                default=False,
            )
            for b in bodies
        )

    def _sheet_metal_refusal(self, operation: str) -> AdapterResult[Any] | None:
        """An error unless a sheet-metal part is active."""
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        if not self._is_sheet_metal():
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"{operation} needs a sheet-metal part; this part has no "
                f"sheet-metal body. {_START_WITH}",
            )
        return None

    def _sketch_is_closed(self, sketch: str) -> bool | None:
        """Whether every contour of ``sketch`` is closed; ``None`` if unreadable."""
        adapter: Any = self
        model = adapter.currentModel
        feature = adapter._attempt(lambda: model.FeatureByName(sketch), default=None)
        if feature is None:
            return None
        body = adapter._attempt(lambda: feature.GetSpecificFeature2(), default=None)
        contours = as_list(
            adapter._attempt(
                lambda: sw_type_info.flagged(body, "ISketch").GetSketchContours(),
                default=None,
            )
        )
        if not contours:
            return None
        return all(
            bool(
                adapter._attempt(
                    lambda c=c: sw_type_info.flagged(c, "ISketchContour").IsClosed(),
                    default=False,
                )
            )
            for c in contours
        )

    async def create_base_flange(
        self,
        thickness: float,
        bend_radius: float,
        k_factor: float = 0.5,
        depth: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """A base flange from a sketch: a plate, or an open profile extruded by ``depth``.

        Args:
            thickness: Sheet thickness, mm.
            bend_radius: Inside bend radius, mm.
            k_factor: The bend allowance's K-factor.
            depth: How far an open profile is extruded, mm; not used for a
                closed one.
            sketch: The sketch's name; the last closed sketch when omitted.
            reverse: Thicken to the other side of the sketch.

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, ``thickness_mm``,
            ``bend_radius_mm``, ``k_factor`` (read back from the feature) and
            the volume before, after and change.
        """
        adapter: Any = self
        name = sketch or getattr(adapter, "_last_sketch_name", None)
        if not name:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No sketch to make the base flange from; sketch a profile "
                "and close it with exit_sketch first.",
            )

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            closed = self._sketch_is_closed(name)
            if closed is False and depth is None:
                raise InputRefused(
                    f"The sketch '{name}' is an open profile, so it needs depth "
                    "(how far to extrude it)."
                )
            model.ClearSelection2(True)
            if not _select_named_feature(adapter, name, 0, append=False):
                raise LookupError(f"Couldn't select the sketch '{name}'.")
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            allowance = sw_type_info.flagged(
                manager.CreateCustomBendAllowance(), "ICustomBendAllowance"
            )
            allowance.Type = _K_FACTOR
            allowance.KFactor = float(k_factor)
            feature = manager.InsertSheetMetalBaseFlange2(
                _m(thickness),  # Thickness
                bool(reverse),  # ThickenDir
                _m(bend_radius),  # Radius
                _m(depth or 0.0),  # ExtrudeDist1
                0.0,  # ExtrudeDist2
                False,  # FlipExtruDir
                _BLIND,  # EndCondition1
                _BLIND,  # EndCondition2
                1,  # DirToUse: 0 builds nothing (seen live, SolidWorks 2026)
                allowance,  # PCBA
                False,  # UseDefaultRelief
                0,  # ReliefType
                0.0,  # ReliefWidth
                0.0,  # ReliefDepth
                0.5,  # ReliefRatio
                True,  # UseReliefRatio
                False,  # Merge
                True,  # UseFeatScope
                True,  # UseAutoSelect
            )
            if feature is None:
                raise RuntimeError(
                    f"SolidWorks made no base flange from '{name}'; check the "
                    "sketch is one profile on a plane."
                )
            return {
                "name": adapter._attempt(lambda: feature.Name, default=None),
                "sketch": name,
                **self._flange_values(feature, thickness, bend_radius, k_factor),
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            await adapter._measured("create_base_flange", build, first_feature=True),
        )

    def _flange_values(
        self, feature: Any, thickness: float, bend_radius: float, k_factor: float
    ) -> dict[str, Any]:
        """The thickness, radius and K-factor read back from a base flange.

        Args:
            feature: The base-flange feature.
            thickness: The asked thickness, mm (used when it can't be read).
            bend_radius: The asked radius, mm.
            k_factor: The asked K-factor.

        Returns:
            dict[str, Any]: ``thickness_mm``, ``bend_radius_mm``, ``k_factor``
            and ``read_back`` (whether they came from the feature).
        """
        adapter: Any = self
        data = adapter._attempt(
            lambda: sw_type_info.flagged(
                sw_type_info.flagged(feature, "IFeature").GetDefinition(),
                "IBaseFlangeFeatureData",
            ),
            default=None,
        )
        thick = adapter._attempt(lambda: data.Thickness, default=None)
        radius = adapter._attempt(lambda: data.BendRadius, default=None)
        k = adapter._attempt(lambda: data.KFactor, default=None)
        read = all(isinstance(v, (int, float)) for v in (thick, radius, k))
        return {
            "thickness_mm": round(thick * 1000, 6) if read else float(thickness),
            "bend_radius_mm": round(radius * 1000, 6) if read else float(bend_radius),
            "k_factor": float(k) if read else float(k_factor),
            "read_back": read,
        }

    async def add_edge_flange(
        self,
        edge_point: list[float],
        length: float,
        angle: float = 90.0,
        bend_radius: float | None = None,
        flip: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """A flange off the sheet edge nearest ``edge_point``.

        Args:
            edge_point: ``[x, y, z]`` mm on the edge.
            length: The flange's length, mm.
            angle: The flange's angle from the sheet, degrees.
            bend_radius: Inside bend radius, mm; the sheet's when omitted.
            flip: Put the flange on the other side.

        Returns:
            AdapterResult[dict[str, Any]]: ``name``, ``edge_length_mm`` and the
            volume change.
        """
        refusal = self._sheet_metal_refusal("add_edge_flange")
        if refusal is not None:
            return refusal
        adapter: Any = self

        def build() -> dict[str, Any]:
            # The sequence of SolidWorks' "Insert Sheet Metal Edge Flange"
            # example: the edge selected, its profile sketch made with
            # InsertSketchForEdgeFlange, the edge converted into that sketch
            # and the profile drawn from its ends, then the flange.
            model = adapter.currentModel
            x, y, z = (_m(v) for v in edge_point)
            point = (x, y, z)
            picker = _BodyEntityPicker(adapter)
            found = picker.nearest("GetEdges", point)
            if found is None or found[1] > _EDGE_TOLERANCE_M:
                raise InputRefused(
                    f"No sheet edge at {list(edge_point)} mm; give a point on "
                    "the edge itself."
                )
            model.ClearSelection2(True)
            if not picker.select(found[0], append=False):
                raise LookupError(f"Couldn't select the edge at {list(edge_point)} mm.")
            selections = sw_type_info.flagged(model.SelectionManager, "ISelectionMgr")
            edge = selections.GetSelectedObject6(1, -1)
            edge_length = self._edge_span_mm(edge)
            sketch = self._flange_profile(edge, angle, flip, length)
            options = (_EDGE_DEFAULT_RADIUS if bend_radius is None else 0) | (
                _EDGE_FLIP if flip else 0
            )
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.InsertSheetMetalEdgeFlange2(
                dispatch_array([edge]),  # FlangeEdges
                dispatch_array([sketch]),  # SketchFeats: the profile sketch
                options,  # BooleanOptions
                math.radians(angle),  # FlangeAngle
                _m(bend_radius or 0.0),  # FlangeRadius
                _MATERIAL_INSIDE,  # BendPosition
                _m(length),  # FlangeOffsetDist
                _RELIEF_RECTANGULAR,  # ReliefType
                0.5,  # FlangeReliefRatio
                0.0,  # FlangeReliefWidth
                0.0,  # FlangeReliefDepth
                _OUTER_VIRTUAL_SHARP,  # FlangeSharpType
                _null_callout(),  # CustomBendAllowance: the sheet's
            )
            if feature is None:
                raise RuntimeError(
                    f"SolidWorks made no edge flange on the edge at "
                    f"{list(edge_point)} mm."
                )
            return {
                "name": adapter._attempt(lambda: feature.Name, default=None),
                "edge_length_mm": edge_length,
                "length_mm": float(length),
                "angle_deg": float(angle),
            }

        return cast(
            "AdapterResult[dict[str, Any]]",
            await adapter._measured("add_edge_flange", build),
        )

    def _flange_profile(
        self, edge: Any, angle: float, flip: bool, length: float
    ) -> Any:
        """The edge flange's profile sketch: the edge, and a rectangle off it.

        Args:
            edge: The selected flange edge.
            angle: The flange's angle, degrees.
            flip: Put the flange on the other side.
            length: The flange's length, mm.

        Returns:
            Any: The profile's ``ISketch``, closed.

        Raises:
            RuntimeError: When SolidWorks makes no profile sketch.
        """
        adapter: Any = self
        model = adapter.currentModel
        feature = model.InsertSketchForEdgeFlange(edge, math.radians(angle), bool(flip))
        if feature is None:
            raise RuntimeError("SolidWorks made no profile sketch for the flange.")
        sw_type_info.flagged(feature, "IFeature").Select2(False, 0)
        model.EditSketch()
        sketch = sw_type_info.flagged(model.GetActiveSketch2(), "ISketch")
        sw_type_info.flagged(edge, "IEntity").Select4(False, _null_callout())
        manager = sw_type_info.flagged(model.SketchManager, "ISketchManager")
        manager.SketchUseEdge(False)
        line = sw_type_info.flagged(
            as_list(sketch.GetSketchSegments())[0], "ISketchLine"
        )
        start = sw_type_info.flagged(line.GetStartPoint2(), "ISketchPoint")
        end = sw_type_info.flagged(line.GetEndPoint2(), "ISketchPoint")
        rise = _m(length)
        manager.AddToDB = True
        manager.CreateLine(start.X, start.Y, 0.0, start.X, start.Y + rise, 0.0)
        manager.CreateLine(start.X, start.Y + rise, 0.0, end.X, end.Y + rise, 0.0)
        manager.CreateLine(end.X, end.Y + rise, 0.0, end.X, end.Y, 0.0)
        manager.AddToDB = False
        manager.InsertSketch(True)
        return sketch

    async def create_sketched_bend(
        self,
        angle: float = 90.0,
        bend_radius: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Bend the sheet along a sketched line.

        SolidWorks chooses which side of the line stays put:
        ``ISketchedBendFeatureData.SetFixedFace`` made no difference live on
        SolidWorks 2026, with or without the face selected. The reply's
        bounding box shows which side moved.

        Args:
            angle: The bend angle, degrees.
            bend_radius: Inside bend radius, mm; the sheet's when omitted.
            sketch: The bend line's sketch; the last closed sketch when omitted.
            reverse: Bend the other way.

        Returns:
            AdapterResult[dict[str, Any]]: ``name`` and the bounding box after.
        """
        refusal = self._sheet_metal_refusal("create_sketched_bend")
        if refusal is not None:
            return refusal
        adapter: Any = self
        name = sketch or getattr(adapter, "_last_sketch_name", None)
        if not name:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error="No sketch with a bend line; sketch a line on a face of the "
                "sheet and close it with exit_sketch first.",
            )

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            data = sw_type_info.flagged(
                manager.CreateDefinition(_SKETCH_BEND), "ISketchedBendFeatureData"
            )
            data.BendAngle = math.radians(angle)
            data.UseDefaultBendRadius = bend_radius is None
            if bend_radius is not None:
                data.BendRadius = _m(bend_radius)
            data.ReverseDirection = bool(reverse)
            model.ClearSelection2(True)
            if not _select_named_feature(adapter, name, 0, append=False):
                raise LookupError(f"Couldn't select the sketch '{name}'.")
            feature = manager.CreateFeature(data)
            if feature is None:
                raise RuntimeError(
                    f"SolidWorks made no sketched bend from '{name}'; the sketch "
                    "must be a line across a face of the sheet."
                )
            return {
                "name": adapter._attempt(lambda: feature.Name, default=None),
                "sketch": name,
                "angle_deg": float(angle),
            }

        return await self._with_box("create_sketched_bend", build)

    async def _with_box(
        self, operation: str, build: Any
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` and add the bounding box after (a bend keeps the volume).

        Args:
            operation: The operation's name.
            build: The COM closure.

        Returns:
            AdapterResult[dict[str, Any]]: ``build``'s data and ``bounding_box_mm``.
        """
        adapter: Any = self
        result = cast(
            "AdapterResult[dict[str, Any]]",
            adapter._handle_com_operation(operation, build),
        )
        if not result.is_success:
            return result
        summary = await adapter.get_model_geometry_summary()
        data = dict(result.data or {})
        data["bounding_box_mm"] = (summary.data or {}).get("bounding_box_mm")
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    async def set_flat_pattern(self, flat: bool) -> AdapterResult[dict[str, Any]]:
        """Flatten the sheet-metal part, or fold it back, and measure it.

        As SolidWorks' Flatten command does, this unsuppresses the part's
        Flat-Pattern feature (suppresses it to fold). ``IModelDoc2.SetBendState``
        returned success and changed nothing (seen live, SolidWorks 2026).

        Args:
            flat: True to flatten, False to fold.

        Returns:
            AdapterResult[dict[str, Any]]: ``flat``, ``feature`` (the flat
            pattern's name) and ``bounding_box_mm`` in that state (flattened:
            the blank's size).
        """
        refusal = self._sheet_metal_refusal("set_flat_pattern")
        if refusal is not None:
            return refusal
        adapter: Any = self
        found = cast(
            "AdapterResult[str]",
            adapter._handle_com_operation("set_flat_pattern", self._flat_pattern_name),
        )
        if not found.is_success:
            return cast("AdapterResult[dict[str, Any]]", found)
        name = str(found.data)
        changed = await adapter.suppress_feature(name, suppress=not flat)
        if not changed.is_success:
            return cast("AdapterResult[dict[str, Any]]", changed)
        summary = await adapter.get_model_geometry_summary()
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "flat": bool(flat),
                "feature": name,
                "bounding_box_mm": (summary.data or {}).get("bounding_box_mm"),
            },
        )

    def _flat_pattern_name(self) -> str:
        """The part's Flat-Pattern feature name.

        Returns:
            str: Its name, e.g. ``Flat-Pattern1``.

        Raises:
            LookupError: When the part has no flat pattern.
        """
        adapter: Any = self
        manager = sw_type_info.flagged(
            adapter.currentModel.FeatureManager, "IFeatureManager"
        )
        folder = sw_type_info.flagged(
            manager.GetFlatPatternFolder(), "IFlatPatternFolder"
        )
        patterns = as_list(folder.GetFlatPatterns())
        if not patterns:
            raise LookupError(f"The part has no flat pattern. {_START_WITH}")
        return str(sw_type_info.flagged(patterns[0], "IFeature").Name)

    def _edge_span_mm(self, edge: Any) -> float | None:
        """The distance between an edge's ends, mm (its length when straight).

        Args:
            edge: The edge.

        Returns:
            float | None: The span, or ``None`` when the ends can't be read.
        """
        adapter: Any = self
        params = as_list(
            adapter._attempt(
                lambda: sw_type_info.flagged(edge, "IEdge").GetCurveParams2(),
                default=None,
            )
        )
        if len(params) < 6:
            return None
        start, end = params[0:3], params[3:6]
        return round(math.dist(start, end) * 1000, 3)
