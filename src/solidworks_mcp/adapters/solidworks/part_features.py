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
from .com_utils import as_list, double_array
from .features import (
    _PICK_TOLERANCE_M,
    _BodyEntityPicker,
    _null_callout,
    _select_edge_by_coord,
    _select_named_feature,
    _with_volume_change,
)
from .hole_library import (
    HoleLibraryError,
    HoleSizeError,
    ResolvedHole,
    describe,
    find_library,
    unchecked,
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
HOLE_STANDARDS: dict[str, int] = {
    "ansi_inch": 0,
    "ansi_metric": 1,
    "din": 4,
    "iso": 8,
    "jis": 9,
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

#: The deepest a blind tapped hole's thread may go, as a share of the hole
#: depth. A thread ending exactly at the bottom leaves a zero-length line in
#: the hole's profile sketch, which SolidWorks refuses to solve (seen live).
_THREAD_SHARE = 0.8


def _mm(value: float) -> float:
    """Millimetres to metres."""
    return float(value) / 1000.0


def _cap_thread_depth(
    adapter: Any, model: Any, feature: Any, depth_m: float
) -> float | None:
    """Keep a blind tapped hole's thread inside the hole, in metres.

    ``HoleWizard5`` takes the thread depth from the size table (about twice
    the diameter), which SolidWorks then refuses when the blind hole is
    shallower: "The Tap Thread Depth cannot be larger than Blind Hole Depth"
    (seen live on SolidWorks 2026). A thread exactly as deep as the hole is
    refused too (a zero-length line in the hole's sketch), so the thread is
    capped at :data:`_THREAD_SHARE` of the hole depth: the hole's
    ``IWizardHoleFeatureData2`` is opened, ``ThreadDepth`` lowered, and the
    definition saved.

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
    cap = depth_m * _THREAD_SHARE
    if thread is None or thread <= cap:
        return thread
    adapter._attempt(lambda: data.AccessSelections(model, _null_callout()), None)
    data.ThreadDepth = cap
    saved = adapter._attempt(
        lambda: hole.ModifyDefinition(data, model, _null_callout()), False
    )
    if not saved:
        adapter._attempt(lambda: data.ReleaseSelectionAccess(), None)
        return thread
    return cap


def _through_depth_m(adapter: Any, model: Any) -> float:
    """A blind depth that passes through the part: its box diagonal + 1 mm.

    SolidWorks refuses ``through_all`` for a simple Hole Wizard hole (seen
    live, every argument variant), so such a hole is made blind this deep.

    Args:
        adapter: The connected adapter.
        model: The active part.

    Returns:
        The depth in metres; 1 m when the part box can't be read.
    """
    part = sw_type_info.flagged(model, "IPartDoc")
    box = as_list(adapter._attempt(lambda: part.GetPartBox(True), default=None))
    if len(box) < 6:
        return 1.0
    corners = [float(v) for v in box[:6]]
    return math.dist(corners[:3], corners[3:]) + 0.001


def _to_sketch(adapter: Any, sketch: Any, point_m: list[float]) -> list[float]:
    """A model point (metres) in ``sketch``'s coordinates.

    Args:
        adapter: The connected adapter (its ``swApp`` gives the math utility).
        sketch: An ``ISketch``.
        point_m: ``[x, y, z]`` in metres, model space.

    Returns:
        ``[x, y, z]`` in the sketch's space; ``z`` is 0 on the sketch plane.
    """
    app = sw_type_info.flagged(adapter.swApp, "ISldWorks")
    math_utility = sw_type_info.flagged(app.GetMathUtility(), "IMathUtility")
    point = sw_type_info.flagged(
        math_utility.CreatePoint(double_array(point_m)), "IMathPoint"
    )
    moved = sw_type_info.flagged(
        point.MultiplyTransform(sketch.ModelToSketchTransform), "IMathPoint"
    )
    return [float(v) for v in as_list(moved.ArrayData)[:3]]


def _sketch_points(adapter: Any, sketch: Any) -> list[list[float]]:
    """The points of an ``ISketch``, ``[x, y, z]`` in sketch metres."""
    points = as_list(adapter._attempt(lambda: sketch.GetSketchPoints2(), default=None))
    return [[float(p.X), float(p.Y), float(p.Z)] for p in points]


def _position_sketch(adapter: Any, feature: Any, first_m: list[float]) -> Any:
    """The hole's position sketch feature: its sketch has a point at ``first_m``.

    Args:
        adapter: The connected adapter.
        feature: The new Hole Wizard feature.
        first_m: The first hole's point, metres, model space.

    Returns:
        ``(sketch_feature, sketch)``.

    Raises:
        LookupError: When no sub-feature sketch holds that point.
    """
    hole = sw_type_info.flagged(feature, "IFeature")
    sub = adapter._attempt(lambda: hole.GetFirstSubFeature(), default=None)
    while sub is not None:
        sub = sw_type_info.flagged(sub, "IFeature")
        kind = adapter._attempt(lambda s=sub: s.GetTypeName2(), default="")
        if kind in ("ProfileFeature", "3DProfileFeature"):
            sketch = sw_type_info.flagged(
                adapter._attempt(lambda s=sub: s.GetSpecificFeature2(), None),
                "ISketch",
            )
            if sketch is not None:
                at = _to_sketch(adapter, sketch, first_m)
                if any(
                    math.dist(at, p) <= _PICK_TOLERANCE_M
                    for p in _sketch_points(adapter, sketch)
                ):
                    return sub, sketch
        sub = adapter._attempt(lambda s=sub: s.GetNextSubFeature(), default=None)
    raise LookupError("The hole's position sketch couldn't be found.")


def _add_hole_positions(
    adapter: Any,
    model: Any,
    feature: Any,
    first_mm: list[float],
    positions_mm: list[list[float]],
) -> int:
    """Put a hole at every point of ``positions_mm`` (Hole Wizard positions).

    Each point is added to the hole's position sketch, as clicking sketch
    points on the Hole Wizard's Positions tab does; closing the sketch
    rebuilds the hole at every point.

    Args:
        adapter: The connected adapter.
        model: The active part.
        feature: The new Hole Wizard feature.
        first_mm: The first hole's point, mm.
        positions_mm: The further points, mm, on the same face.

    Returns:
        The number of points in the position sketch afterwards.

    Raises:
        ValueError: A point that is off the face's plane.
        RuntimeError: When the sketch didn't take every point.
    """
    sketch_feature, sketch = _position_sketch(
        adapter, feature, [_mm(v) for v in first_mm]
    )
    local = [_to_sketch(adapter, sketch, [_mm(v) for v in p]) for p in positions_mm]
    for point, at in zip(positions_mm, local, strict=True):
        if abs(at[2]) > _PICK_TOLERANCE_M:
            raise ValueError(
                f"Position {list(point)} mm is {abs(at[2]) * 1000:.3f} mm off the "
                "face the hole is on; give points on that face."
            )
    model.ClearSelection2(True)
    sw_type_info.flagged(sketch_feature, "IFeature").Select2(False, 0)
    model.EditSketch()
    manager = sw_type_info.flagged(model.SketchManager, "ISketchManager")
    manager.AddToDB = True  # no snapping onto the first hole
    try:
        for x, y, _z in local:
            manager.CreatePoint(x, y, 0.0)
    finally:
        manager.AddToDB = False
        manager.InsertSketch(True)
    count = len(_sketch_points(adapter, sketch))
    expected = 1 + len(positions_mm)
    if count != expected:
        raise RuntimeError(
            f"The hole's position sketch has {count} points after adding "
            f"{len(positions_mm)}; expected {expected}."
        )
    return count


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

    def __init__(self, adapter: Any, *, rebuild: bool = True) -> None:
        """Start a pick set.

        Args:
            adapter: The connected adapter.
            rebuild: Rebuild before the first pick; False inside an open
                sketch, which a rebuild would close.
        """
        self._adapter = adapter
        self._picker = _BodyEntityPicker(adapter)
        self._first = True
        self._rebuild = rebuild

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
            rebuild=self._rebuild,
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
        first_feature: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Run ``build`` on the COM thread and judge it by the volume.

        Args:
            operation: The operation's name (logs, circuit breaker).
            build: The COM closure; returns the feature's data with ``name``.
            must_change: True for solid features; False for a cosmetic
                thread, which must leave the volume alone.
            first_feature: The part may have no body yet (a base flange), so
                an unreadable volume before counts as zero.

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
        if first_feature:
            # The part may have no body: the summary reads 0 where the mass
            # properties fail.
            summary = await self.get_model_geometry_summary()  # type: ignore[attr-defined]
            before = (summary.data or {}).get("volume_mm3") or 0.0
        else:
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
                    "FeatureLinearPattern5 returned nothing. SolidWorks picks "
                    "which way an edge points, so an instance may have landed "
                    "off the part: try reverse (or reverse2). Also check the "
                    "features, and that each direction is a straight edge or an "
                    "axis."
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

    async def list_hole_sizes(
        self,
        standard: str,
        hole_type: str,
        fastener: str | None = None,
        size: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """The Hole Wizard hole types and sizes, read from the installed library.

        A file read (:mod:`.hole_library`), no COM: it works whether or not
        SolidWorks is running.

        Args:
            standard: A key of :data:`HOLE_STANDARDS`.
            hole_type: ``simple``, ``counterbore``, ``countersink`` or ``tapped``.
            fastener: One hole type's name, to list only its sizes.
            size: One size, to read its dimensions.

        Returns:
            The hole types with their sizes, or one size's dimensions; an
            error naming where the library was looked for, or the nearest
            sizes.
        """
        try:
            data = describe(find_library(), standard, hole_type, fastener, size)
        except (HoleLibraryError, HoleSizeError) as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)

    async def create_hole(
        self,
        face_point: list[float],
        hole_type: str,
        standard: str,
        size: str,
        end_condition: str = "through_all",
        depth: float | None = None,
        positions: list[list[float]] | None = None,
        fastener: str | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Hole Wizard holes at points on a flat face (``HoleWizard5``).

        The face is selected at ``face_point`` with ``SelectByID2``, and the
        hole is placed at that selection point. Dimensions not given are -1,
        which leaves them to the standard's table for the size. Each point of
        ``positions`` is added to the hole's position sketch, so one feature
        holds every hole (:func:`_add_hole_positions`). A simple hole that
        SolidWorks won't make through all is made blind through the part
        (:func:`_through_depth_m`).

        Args:
            face_point: ``[x, y, z]`` mm on the face, where the first hole goes.
            hole_type: A key of :data:`HOLE_TYPES`.
            standard: A key of :data:`HOLE_STANDARDS`.
            size: The size as the library lists it (``M6``, ``#10``); a bare
                diameter or a pitch is matched to the table's spelling.
            end_condition: A key of :data:`HOLE_END_CONDITIONS`.
            depth: Hole depth for a blind hole, mm.
            positions: Further ``[x, y, z]`` mm points on the same face.
            fastener: The hole type's name from ``list_hole_sizes``; the
                default for the kind and size when ``None``.

        Returns:
            The hole's name, inputs, ``fastener``, ``hole_count``,
            ``end_condition_used`` and volume change. A size the library
            lacks is refused before any COM call, with the nearest sizes.
            When adding the positions fails, the hole is removed again and
            the error says why.
        """
        adapter: Any = self
        try:
            chosen = _resolve_hole(standard, hole_type, size, fastener)
        except HoleSizeError as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))
        extra = [list(p) for p in positions or []]
        made: dict[str, str | None] = {}

        def build() -> dict[str, Any]:
            model = adapter.currentModel
            model.ClearSelection2(True)
            adapter._attempt(lambda: model.ForceRebuild3(True), default=None)
            x, y, z = (_mm(v) for v in face_point)
            manager = sw_type_info.flagged(model.FeatureManager, "IFeatureManager")

            def make(end: str, depth_m: float) -> Any:
                model.ClearSelection2(True)
                if not model.Extension.SelectByID2(
                    "", "FACE", x, y, z, False, 0, _null_callout(), 0
                ):
                    raise LookupError(
                        f"No face at {list(face_point)} mm to put the hole on."
                    )
                return manager.HoleWizard5(
                    HOLE_TYPES[hole_type],  # GenericHoleType
                    HOLE_STANDARDS[standard],  # StandardIndex
                    chosen.code,  # FastenerTypeIndex
                    chosen.size,  # SSize
                    HOLE_END_CONDITIONS[end],  # EndType
                    -1.0,  # Diameter (from the size table)
                    depth_m,  # Depth
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

            blind_depth = _mm(depth) if depth is not None else -1.0
            end_used = end_condition
            warnings = [chosen.warning] if chosen.warning else []
            feature = make(end_condition, blind_depth)
            if feature is None and hole_type == "simple" and end_condition != "blind":
                blind_depth = _through_depth_m(adapter, model)
                end_used = "blind"
                feature = make("blind", blind_depth)
                warnings.append(
                    "SolidWorks makes no simple hole through all, so this one is "
                    f"blind, {blind_depth * 1000:.1f} mm deep (through the part). "
                    "If the part is made thicker, deepen the hole."
                )
            if feature is None:
                raise RuntimeError(
                    f"HoleWizard5 made no hole ({hole_type}, {standard}, "
                    f'"{chosen.fastener}" {chosen.size}); check the face is flat '
                    "and the hole fits on it."
                )
            name = _feature_name(adapter, feature)
            made["name"] = name
            thread_m = (
                _cap_thread_depth(adapter, model, feature, blind_depth)
                if hole_type == "tapped" and end_condition == "blind" and depth
                else None
            )
            count = (
                _add_hole_positions(adapter, model, feature, list(face_point), extra)
                if extra
                else 1
            )
            made["name"] = None  # finished: nothing to clean up
            data: dict[str, Any] = {
                "name": name,
                "hole_count": count,
                "thread_depth_mm": None if thread_m is None else thread_m * 1000,
                "hole_type": hole_type,
                "standard": standard,
                "fastener": chosen.fastener,
                "size": chosen.size,
                "end_condition": end_condition,
                "end_condition_used": end_used,
                "depth_mm": depth if end_used == end_condition else blind_depth * 1000,
                "at_mm": list(face_point),
                "positions_mm": extra,
            }
            if warnings:
                data["warnings"] = warnings
            return data

        result = await self._measured("create_hole", build)
        orphan = made.get("name")
        if not result.is_success and orphan:
            await adapter.delete_feature(orphan)
            return AdapterResult(
                status=AdapterResultStatus.ERROR,
                error=f"{result.error} The hole {orphan} was removed again.",
            )
        return result

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
            # Flagged, or GetSketchSegments reads as a property and calling
            # its tuple fails, so every count is 0 (seen live).
            sketch = sw_type_info.flagged(
                adapter.currentSketchManager.ActiveSketch, "ISketch"
            )
            return as_list(
                adapter._attempt(lambda: sketch.GetSketchSegments(), default=None)
            )

        def build() -> dict[str, Any]:
            before = len(segments())
            adapter.currentModel.ClearSelection2(True)
            # No rebuild: it would close the sketch being copied into.
            picks = _Picks(adapter, rebuild=False)
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


def _resolve_hole(
    standard: str, hole_type: str, size: str, fastener: str | None
) -> ResolvedHole:
    """The hole type, index and size to ask ``HoleWizard5`` for.

    Checked against the installed library; when it can't be read, the
    default hole type is tried with a warning (design decision 7).

    Raises:
        HoleSizeError: For a size or hole type the library lacks.
    """
    try:
        library = find_library()
    except HoleLibraryError as exc:
        return unchecked(standard, hole_type, size, fastener, str(exc))
    return library.resolve(standard, hole_type, size, fastener)
