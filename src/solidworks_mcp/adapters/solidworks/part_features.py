"""Part features beyond extrude and revolve: holes, threads, patterns, shell, draft, rib.

Also ``sketch_convert_entities``, which copies model edges into the open
sketch. Every face and edge is picked by a point in millimetres, through
the same helpers the chamfer and fillet tools use (rebuild first, then the
nearest face or edge on the body; runbook #11 and #13).

The solid features share one rule (spec ``tools/measured-feature-change``):
the volume is read before and after through ``get_mass_properties``, and a
feature that left the volume unchanged is deleted again and reported as a
failure, so a no-op never stays in the tree. A cosmetic thread is the
exception: it must leave the volume alone.

COM argument lists and enum values come from the installed type libraries
(``sldworks.tlb`` and ``swconst.tlb``, SolidWorks 2026).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, cast

from .. import sw_type_info
from ..base import AdapterResult, AdapterResultStatus
from .com_utils import as_list
from .features import (
    _BodyEntityPicker,
    _null_callout,
    _select_edge_by_coord,
    _select_named_feature,
    _with_volume_change,
)
from .rebuild_diagnostics import explain
from .rebuild_inspector import collect_rebuild_issues

#: ``swWzdGeneralHoleTypes_e``.
HOLE_TYPES: dict[str, int] = {
    "counterbore": 0,
    "countersink": 1,
    "simple": 2,
    "tapped": 4,
}

#: ``swWzdHoleStandards_e``.
HOLE_STANDARDS: dict[str, int] = {"ansi_inch": 0, "iso": 8}

#: ``(hole_type, standard) -> swWzdHoleStandardFastenerTypes_e``: the
#: fastener list each hole type is sized from.
HOLE_FASTENERS: dict[tuple[str, str], int] = {
    ("simple", "iso"): 143,  # swStandardISODrillSizes
    ("simple", "ansi_inch"): 18,  # swStandardAnsiInchAllDrillSizes
    ("counterbore", "iso"): 139,  # swStandardISOSocketHeadCap
    ("counterbore", "ansi_inch"): 9,  # swStandardAnsiInchSocketCapScrew
    ("countersink", "iso"): 141,  # swStandardISOCTSKFlatHead
    ("countersink", "ansi_inch"): 15,  # swStandardAnsiInchFlatHead82
    ("tapped", "iso"): 147,  # swStandardISOTappedHole
    ("tapped", "ansi_inch"): 27,  # swStandardAnsiInchTappedHole
}

#: ``swEndConditions_e`` for holes.
HOLE_END_CONDITIONS: dict[str, int] = {"blind": 0, "through_all": 1}

#: ``swCosmeticThreadType_e``.
THREAD_END_TYPES: dict[str, int] = {"blind": 0, "up_to_next": 1, "through": 2}

#: Selection marks.
_MARK_DIR1 = 1
_MARK_DIR2 = 2
_MARK_FEATURES = 4
_MARK_NEUTRAL = 1
_MARK_DRAFT_FACES = 2

#: A volume change smaller than this share of the volume counts as none.
_NO_CHANGE = 1e-4


def _mm(value: float) -> float:
    """Millimetres to metres."""
    return float(value) / 1000.0


def _cap_thread_depth(
    adapter: Any, model: Any, feature: Any, depth_m: float
) -> float | None:
    """Cap a blind tapped hole's thread depth at its hole depth, in metres.

    ``HoleWizard5`` takes the thread depth from the size table (about twice
    the diameter), which SolidWorks then refuses when the blind hole is
    shallower: "The Tap Thread Depth cannot be larger than Blind Hole Depth"
    (seen live on SolidWorks 2026). The hole's ``IWizardHoleFeatureData2`` is
    opened, ``ThreadDepth`` lowered, and the definition saved.

    Args:
        adapter: The connected adapter.
        model: The active ``IModelDoc2``.
        feature: The new hole feature.
        depth_m: The blind hole's depth, metres.

    Returns:
        The thread depth in metres after the call, or ``None`` when the
        definition couldn't be read (the rebuild check then reports why).
    """
    hole = sw_type_info.flagged(feature, "IFeature")
    data = adapter._attempt(lambda: hole.GetDefinition(), None)
    if data is None:
        return None
    data = sw_type_info.flagged(data, "IWizardHoleFeatureData2")
    thread = adapter._attempt(lambda: float(data.ThreadDepth), None)
    if thread is None or thread <= depth_m:
        return thread
    adapter._attempt(lambda: data.AccessSelections(model, _null_callout()), None)
    data.ThreadDepth = depth_m
    saved = adapter._attempt(
        lambda: hole.ModifyDefinition(data, model, _null_callout()), False
    )
    if not saved:
        adapter._attempt(lambda: data.ReleaseSelectionAccess(), None)
        return thread
    return depth_m


def _feature_name(adapter: Any, feature: Any) -> str | None:
    """A COM feature's name, or ``None``."""
    name = adapter._attempt(
        lambda: adapter._get_attr_or_call(feature, "Name"), default=None
    )
    return str(name) if name else None


def _last_feature_name(adapter: Any) -> str | None:
    """The newest feature's name, for calls that return nothing (rib, shell)."""
    model = adapter.currentModel
    feature = adapter._attempt(lambda: model.FeatureByPositionReverse(0), default=None)
    return _feature_name(adapter, feature) if feature is not None else None


class _Picks:
    """Picks faces and edges by points (mm), sharing one body walk."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self._picker = _BodyEntityPicker(adapter)
        self._first = True

    def pick(self, point: list[float], kind: str, mark: int) -> None:
        """Select the ``kind`` ("FACE" or "EDGE") at ``point`` under ``mark``.

        Raises:
            LookupError: When nothing of that kind lies at the point.
        """
        x, y, z = (_mm(v) for v in point)
        selected = _select_edge_by_coord(
            self._adapter,
            x,
            y,
            z,
            append=not self._first,
            mark=mark,
            entity_type=kind,
            picker=self._picker,
        )
        self._first = False
        if not selected:
            raise LookupError(
                f"Couldn't select the {kind.lower()} at {list(point)} mm; give a "
                f"point on the {kind.lower()} itself."
            )


class SolidWorksPartFeaturesMixin:
    """Holes, threads, linear patterns, shell, draft, rib and convert entities."""

    async def _volume(self) -> float | None:
        """The part's volume in mm³, or ``None`` when it can't be read."""
        result = await self.get_mass_properties()  # type: ignore[attr-defined]
        return result.data.volume if result.is_success and result.data else None

    async def _measured(
        self,
        operation: str,
        build: Callable[[], dict[str, Any]],
        *,
        must_change: bool = True,
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` on the COM thread and judge it by the volume.

        Args:
            operation: The operation's name (logs, circuit breaker).
            build: The COM closure; returns the feature's data with ``name``.
            must_change: True for solid features; False for a cosmetic
                thread, which must leave the volume alone.

        Returns:
            The feature's data plus the volume before, after and change; an
            error when the volume can't be read or moved the wrong way (a
            solid feature that changed nothing is deleted first).
        """
        adapter: Any = self
        if not adapter.currentModel:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active model"
            )
        before = await self._volume()
        result = cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation(operation, build),
        )
        if not result.is_success:
            return result
        after = await self._volume()
        if before is None or after is None:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"{operation} returned a feature but the volume could not be "
                    "read before and after, so whether it did anything is unknown."
                ),
            )
        unchanged = abs(after - before) <= before * _NO_CHANGE
        if must_change and unchanged:
            name = (result.data or {}).get("name")
            if name:
                await adapter.delete_feature(name)
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"{operation} made no change to the part (volume "
                    f"{before:.1f} mm³ before and after); SolidWorks built "
                    f"nothing, so the feature{f' {name}' if name else ''} was "
                    "removed again. Check the picked faces, edges or sketch."
                ),
            )
        if not must_change and not unchanged:
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"{operation} changed the part's volume ({before:.1f} -> "
                    f"{after:.1f} mm³); a cosmetic thread must not."
                ),
            )
        name = (result.data or {}).get("name")
        issues = self._rebuild_issues(operation, name)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            if name:
                await adapter.delete_feature(name)
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=(
                    f"{operation}: SolidWorks reports {errors[0]['code_name']} on "
                    f"{name}: {errors[0]['description']} {errors[0]['hint']} The "
                    "feature was removed again."
                ),
            )
        measured = _with_volume_change(result, before, after)
        if issues:
            data = dict(measured.data or {})
            data["rebuild_warnings"] = issues
            measured = AdapterResult(
                status=AdapterResultStatus.SUCCESS,
                data=data,
                execution_time=measured.execution_time,
            )
        return measured

    def _rebuild_issues(self, operation: str, name: str | None) -> list[dict[str, Any]]:
        """The new feature's rebuild errors and warnings, explained.

        Args:
            operation: The operation's name (for the COM call's log).
            name: The new feature's name; nothing is read without one.

        Returns:
            One explained entry (``severity``, ``code_name``, ``description``,
            ``hint``) per issue SolidWorks reports on that feature.
        """
        adapter: Any = self
        if not name:
            return []
        read = adapter._handle_com_operation(
            f"{operation}_rebuild_check",
            lambda: [
                explain(issue)
                for issue in collect_rebuild_issues(adapter, adapter.currentModel)
                if issue.feature == name
            ],
        )
        return list(read.data or []) if read.is_success else []

    async def pattern_linear(
        self,
        features: list[str],
        direction: list[float] | str,
        count: int,
        spacing: float,
        direction2: list[float] | str | None = None,
        count2: int = 1,
        spacing2: float = 0.0,
        reverse: bool = False,
        reverse2: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Repeat features along one or two directions (``FeatureLinearPattern5``).

        A direction is a point (mm) on a straight edge, or the name of an
        axis or edge.

        Args:
            features: Names of the features to repeat.
            direction: The first direction.
            count: Instances along it, the original included.
            spacing: Distance between instances, mm.
            direction2: The second direction, or None for one direction.
            count2: Instances along the second direction.
            spacing2: Spacing along the second direction, mm.
            reverse: Flip the first direction.
            reverse2: Flip the second direction.

        Returns:
            The pattern's name, inputs and volume change.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            picks = _Picks(adapter)
            names = ["", ""]
            for index, (where, mark) in enumerate(
                ((direction, _MARK_DIR1), (direction2, _MARK_DIR2))
            ):
                if where is None:
                    continue
                if isinstance(where, str):
                    names[index] = where
                    if not _select_named_feature(
                        adapter, where, mark, append=index > 0
                    ):
                        raise LookupError(f"Couldn't select the direction '{where}'.")
                    picks._first = False
                else:
                    picks.pick(where, "EDGE", mark)
            for name in features:
                if not _select_named_feature(
                    adapter, name, _MARK_FEATURES, append=True
                ):
                    raise LookupError(
                        f"Couldn't select the feature '{name}' to pattern."
                    )
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            two = direction2 is not None
            feature = manager.FeatureLinearPattern5(
                int(count),  # Num1
                _mm(spacing),  # Spacing1
                int(count2) if two else 1,  # Num2
                _mm(spacing2) if two else 0.0,  # Spacing2
                bool(reverse),  # FlipDir1
                bool(reverse2),  # FlipDir2
                names[0],  # DName1
                names[1],  # DName2
                False,  # GeometryPattern
                False,  # VaryInstance
                False,  # HasOffset1
                False,  # HasOffset2
                False,  # CtrlByNum1
                False,  # CtrlByNum2
                False,  # FromCentroid1
                False,  # FromCentroid2
                False,  # RevOffset1
                False,  # RevOffset2
                0.0,  # Offset1
                0.0,  # Offset2
                False,  # D2PatternSeedOnly
                False,  # SyncSubAssemblies
            )
            if feature is None:
                raise RuntimeError(
                    "FeatureLinearPattern5 returned nothing; check the features "
                    "and that the direction is a straight edge or an axis."
                )
            return {
                "name": _feature_name(adapter, feature),
                "patterned": list(features),
                "count": int(count),
                "spacing_mm": float(spacing),
                "count2": int(count2) if two else None,
                "spacing2_mm": float(spacing2) if two else None,
            }

        return await self._measured("pattern_linear", build)

    async def create_shell(
        self, thickness: float, faces: list[list[float]], outward: bool = False
    ) -> AdapterResult[dict[str, Any]]:
        """Hollow the body to a wall thickness, removing the faces picked.

        Args:
            thickness: Wall thickness, mm.
            faces: A point (mm) on each face to remove; empty for a closed shell.
            outward: Add the wall outside the body instead of inside.

        Returns:
            The shell's name and volume change.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            picks = _Picks(adapter)
            for point in faces:
                picks.pick(point, "FACE", 0)
            doc = sw_type_info.flagged(model, "IModelDoc2")
            doc.InsertFeatureShell(_mm(thickness), bool(outward))
            return {
                "name": _last_feature_name(adapter),
                "thickness_mm": float(thickness),
                "faces_removed": len(faces),
                "outward": bool(outward),
            }

        return await self._measured("create_shell", build)

    async def add_draft(
        self,
        angle: float,
        faces: list[list[float]],
        neutral_face: list[float],
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Draft faces by an angle against a neutral face (``InsertMultiFaceDraft``).

        Args:
            angle: Draft angle, degrees.
            faces: A point (mm) on each face to draft.
            neutral_face: A point (mm) on the neutral face.
            reverse: Draft the other way.

        Returns:
            The draft's name and volume change.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            picks = _Picks(adapter)
            picks.pick(neutral_face, "FACE", _MARK_NEUTRAL)
            for point in faces:
                picks.pick(point, "FACE", _MARK_DRAFT_FACES)
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.InsertMultiFaceDraft(
                math.radians(float(angle)),  # Angle
                bool(reverse),  # FlipDir
                False,  # EdgeDraft
                0,  # PropType (swNeutralPlaneDraft... propagation: none)
                False,  # IsStepDraft
                False,  # IsBodyDraft
            )
            if feature is None:
                raise RuntimeError(
                    "InsertMultiFaceDraft returned nothing; check that the faces "
                    "meet the neutral face and that the angle is small enough."
                )
            return {
                "name": _feature_name(adapter, feature),
                "angle": float(angle),
                "faces_drafted": len(faces),
            }

        return await self._measured("add_draft", build)

    async def create_rib(
        self,
        sketch: str,
        thickness: float,
        both_sides: bool = True,
        flip_material: bool = False,
        normal_to_sketch: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """A rib from an open sketch (``InsertRib``).

        Args:
            sketch: The rib sketch's name.
            thickness: Rib thickness, mm.
            both_sides: Add the thickness to both sides of the sketch.
            flip_material: Extend the rib the other way.
            normal_to_sketch: Extrude normal to the sketch instead of parallel.

        Returns:
            The rib's name and volume change.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            if not _select_named_feature(adapter, sketch, 0, append=False):
                raise LookupError(f"Couldn't select the sketch '{sketch}' for the rib.")
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            manager.InsertRib(
                bool(both_sides),  # Is2Sided
                False,  # ReverseThicknessDir
                _mm(thickness),  # Thickness
                0,  # ReferenceEdgeIndex
                bool(flip_material),  # ReverseMaterialDir
                False,  # IsDrafted
                False,  # DraftOutward
                0.0,  # DraftAngle
                bool(normal_to_sketch),  # IsNormToSketch
                False,  # IsDraftedFromWall
            )
            return {
                "name": _last_feature_name(adapter),
                "sketch": sketch,
                "thickness_mm": float(thickness),
                "both_sides": bool(both_sides),
            }

        return await self._measured("create_rib", build)

    async def create_hole(
        self,
        face_point: list[float],
        hole_type: str,
        standard: str,
        size: str,
        end_condition: str = "through_all",
        depth: float | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """A Hole Wizard hole at a point on a flat face (``HoleWizard5``).

        The face is selected at ``face_point`` with ``SelectByID2``, and the
        hole is placed at that selection point. Dimensions not given are -1,
        which leaves them to the standard's table for the size.

        Args:
            face_point: ``[x, y, z]`` mm on the face, where the hole goes.
            hole_type: A key of :data:`HOLE_TYPES`.
            standard: A key of :data:`HOLE_STANDARDS`.
            size: The size as SolidWorks lists it (``M6``, ``M6x1.0``, ``#10``).
            end_condition: A key of :data:`HOLE_END_CONDITIONS`.
            depth: Hole depth for a blind hole, mm.

        Returns:
            The hole's name, inputs and volume change.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            adapter._attempt(lambda: model.ForceRebuild3(True), default=None)
            x, y, z = (_mm(v) for v in face_point)
            if not model.Extension.SelectByID2(
                "", "FACE", x, y, z, False, 0, _null_callout(), 0
            ):
                raise LookupError(
                    f"No face at {list(face_point)} mm to put the hole on."
                )
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            blind_depth = _mm(depth) if depth is not None else -1.0
            feature = manager.HoleWizard5(
                HOLE_TYPES[hole_type],  # GenericHoleType
                HOLE_STANDARDS[standard],  # StandardIndex
                HOLE_FASTENERS[(hole_type, standard)],  # FastenerTypeIndex
                size,  # SSize
                HOLE_END_CONDITIONS[end_condition],  # EndType
                -1.0,  # Diameter (from the size table)
                blind_depth,  # Depth
                -1.0,  # Length
                *([-1.0] * 12),  # Value1..Value12 (from the size table)
                "",  # ThreadClass
                False,  # RevDir
                True,  # FeatureScope
                True,  # AutoSelect
                True,  # AssemblyFeatureScope
                True,  # AutoSelectComponents
                False,  # PropagateFeatureToParts
            )
            if feature is None:
                raise RuntimeError(
                    f"HoleWizard5 made no hole ({hole_type}, {standard}, {size}); "
                    "check the size is one SolidWorks lists for that standard."
                )
            thread_m = (
                _cap_thread_depth(adapter, model, feature, blind_depth)
                if hole_type == "tapped" and end_condition == "blind" and depth
                else None
            )
            return {
                "name": _feature_name(adapter, feature),
                "thread_depth_mm": None if thread_m is None else thread_m * 1000,
                "hole_type": hole_type,
                "standard": standard,
                "size": size,
                "end_condition": end_condition,
                "depth_mm": depth,
                "at_mm": list(face_point),
            }

        return await self._measured("create_hole", build)

    async def add_cosmetic_thread(
        self,
        edge_point: list[float],
        size: str,
        diameter: float,
        end_type: str = "blind",
        depth: float | None = None,
        standard: str = "iso",
    ) -> AdapterResult[dict[str, Any]]:
        """A cosmetic thread on a circular edge (``InsertCosmeticThread3``).

        Args:
            edge_point: A point (mm) on the circular edge.
            size: The thread size, e.g. ``M10x1.5``.
            diameter: The major diameter, mm.
            end_type: A key of :data:`THREAD_END_TYPES`.
            depth: Thread length for a blind thread, mm.
            standard: A key of :data:`HOLE_STANDARDS`.

        Returns:
            The thread's name; the volume is unchanged.
        """
        adapter: Any = self

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            _Picks(adapter).pick(edge_point, "EDGE", 0)
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")
            feature = manager.InsertCosmeticThread3(
                HOLE_STANDARDS[standard],  # Standard
                "Machine Threads",  # StandardType
                size,  # Size
                _mm(diameter),  # Diameter
                THREAD_END_TYPES[end_type],  # EndType
                _mm(depth) if depth is not None else 0.0,  # Depth
                size,  # Note
            )
            if feature is None:
                raise RuntimeError(
                    "InsertCosmeticThread3 made no thread; pick a point on a "
                    "circular edge of a hole or shaft."
                )
            return {
                "name": _feature_name(adapter, feature),
                "size": size,
                "diameter_mm": float(diameter),
                "end_type": end_type,
                "depth_mm": depth,
            }

        return await self._measured("add_cosmetic_thread", build, must_change=False)

    async def sketch_convert_entities(
        self,
        edge_points: list[list[float]] | None = None,
        face_point: list[float] | None = None,
        construction: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Copy model edges, or a face's outline, into the open sketch.

        ``SketchUseEdge3`` returns only a Boolean, so the sketch's segments
        are read before and after and the new ones registered under ids the
        other sketch tools accept.

        Args:
            edge_points: A point (mm) on each edge to copy.
            face_point: A point (mm) on a face whose outline to copy.
            construction: Make the copies construction geometry.

        Returns:
            The new entities' ids.
        """
        adapter: Any = self
        if not adapter.currentSketchManager:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error="No active sketch"
            )

        def segments() -> list[Any]:
            sketch = adapter.currentSketchManager.ActiveSketch
            return as_list(
                adapter._attempt(lambda: sketch.GetSketchSegments(), default=None)
            )

        def build() -> dict[str, Any]:
            before = len(segments())
            adapter.currentModel.ClearSelection2(True)
            picks = _Picks(adapter)
            for point in edge_points or []:
                picks.pick(point, "EDGE", 0)
            if face_point is not None:
                picks.pick(face_point, "FACE", 0)
            manager = sw_type_info.flagged(
                adapter.currentSketchManager, "ISketchManager"
            )
            if not manager.SketchUseEdge3(False, False):
                raise RuntimeError(
                    "SketchUseEdge3 copied nothing; the picked edges may already "
                    "be in the sketch."
                )
            new = segments()[before:]
            ids: list[str] = []
            for segment in new:
                if construction:
                    segment.ConstructionGeometry = True
                entity_id = f"Converted_{len(adapter._sketch_entities) + 1}"
                adapter._sketch_entities[entity_id] = segment
                ids.append(entity_id)
            return {"entities": ids, "count": len(ids), "construction": construction}

        return cast(
            AdapterResult[dict[str, Any]],
            adapter._handle_com_operation("sketch_convert_entities", build),
        )
