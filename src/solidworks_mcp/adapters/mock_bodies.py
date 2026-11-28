"""The mock adapter's solid bodies, held as boxes (queue item 35).

Each extrusion records a body: a box over its sketch's rectangles and
circles, from z 0 to the depth, with the sketch's area times the depth as
its volume. An extrusion with ``merge_result`` true grows the last body;
one with it false (or the part's first) adds a body named after the feature,
as SolidWorks names it. Sketch planes are ignored: x and y are the sketch's.

The body operations act on those boxes and are judged by the same rules as
the real adapter (:mod:`body_rules`). A combine's overlap is the boxes'
overlap; a split works at the Front (z), Top (y) and Right (x) planes, not
at a sketch; a rotation isn't modelled (a move only translates).
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Sequence
from typing import Any

from ..exceptions import InputRefused
from . import body_rules as rules
from .base import (
    AdapterResult,
    AdapterResultStatus,
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
    SplitBodyParameters,
)
from .body_rules import BodyState

#: A recorded sketch shape: ``("rect", x1, y1, x2, y2, from_center)`` or
#: ``("circle", cx, cy, r)``.
Shape = tuple[Any, ...]
#: The main planes a mock split works at, and the axis each is normal to.
_SPLIT_PLANES = {"front plane": 2, "top plane": 1, "right plane": 0}

Vector = tuple[float, float, float]


def _error(message: str) -> AdapterResult[Any]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _shape_extent(shape: Shape) -> tuple[float, float, float, float, float]:
    """A shape's ``(xmin, ymin, xmax, ymax, area)`` in sketch mm."""
    if shape[0] == "circle":
        _, cx, cy, r = shape
        return cx - r, cy - r, cx + r, cy + r, math.pi * r * r
    _, x1, y1, x2, y2, from_center = shape
    if from_center:
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        x1, y1, x2, y2 = x1 - dx, y1 - dy, x1 + dx, y1 + dy
    lo_x, hi_x = sorted((x1, x2))
    lo_y, hi_y = sorted((y1, y2))
    return lo_x, lo_y, hi_x, hi_y, (hi_x - lo_x) * (hi_y - lo_y)


def _overlap(a: BodyState, b: BodyState) -> float:
    """The volume two box bodies share, at most the smaller body's."""
    size = 1.0
    for axis in range(3):
        lo = max(a.box_min[axis], b.box_min[axis])
        hi = min(a.box_max[axis], b.box_max[axis])
        if hi <= lo:
            return 0.0
        size *= hi - lo
    return min(size, a.volume, b.volume)


def _union_box(bodies: Sequence[BodyState]) -> tuple[Vector, Vector]:
    """The box around several bodies."""
    lo = tuple(min(b.box_min[i] for b in bodies) for i in range(3))
    hi = tuple(max(b.box_max[i] for b in bodies) for i in range(3))
    return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


def _shifted(body: BodyState, by: Sequence[float], name: str) -> BodyState:
    """The body moved by ``by``, renamed."""
    return BodyState(
        name,
        body.volume,
        (body.box_min[0] + by[0], body.box_min[1] + by[1], body.box_min[2] + by[2]),
        (body.box_max[0] + by[0], body.box_max[1] + by[1], body.box_max[2] + by[2]),
    )


class MockBodiesMixin:
    """``list_bodies`` and the five body operations, in memory."""

    _current_model: Any
    _sketches: dict[str, str | None]
    _delays: dict[str, float]
    _operation_count: int

    def _body_store(self) -> dict[int, list[BodyState]]:
        """Each open part's bodies, by the model object's identity."""
        if "_mock_bodies" not in self.__dict__:
            self._mock_bodies: dict[int, list[BodyState]] = {}
        return self._mock_bodies

    def _shapes(self) -> dict[str, list[Shape]]:
        """Each sketch's rectangles and circles, as the sketch tools record them."""
        if "_sketch_shapes" not in self.__dict__:
            self._sketch_shapes: dict[str, list[Shape]] = {}
        return self._sketch_shapes

    def _body_feature_counts(self) -> dict[str, int]:
        """How many of each body feature the mock has made, for their names."""
        if "_body_features" not in self.__dict__:
            self._body_features: dict[str, int] = {}
        return self._body_features

    def _bodies(self) -> list[BodyState]:
        """The active part's bodies."""
        return self._body_store().setdefault(id(self._current_model), [])

    def _note_shape(self, sketch: str | None, shape: Shape) -> None:
        """Record a rectangle or circle drawn in ``sketch``.

        Args:
            sketch: The open sketch, or None (nothing is recorded).
            shape: The shape, as :data:`Shape` describes.
        """
        if sketch:
            self._shapes().setdefault(sketch, []).append(shape)

    def _note_extrusion(
        self, feature: str, sketch: str | None, depth: float, merge: bool
    ) -> None:
        """Record the body an extrusion makes or grows.

        Args:
            feature: The extrusion's name; a new body takes it.
            sketch: The sketch extruded, or None for the last one drawn.
            depth: mm.
            merge: Grow the last body rather than add one.
        """
        name = sketch or next(reversed(self._sketches), None)
        shapes = self._shapes().get(name or "", [])
        if not shapes:
            return
        extents = [_shape_extent(shape) for shape in shapes]
        body = BodyState(
            feature,
            sum(e[4] for e in extents) * depth,
            (min(e[0] for e in extents), min(e[1] for e in extents), 0.0),
            (max(e[2] for e in extents), max(e[3] for e in extents), depth),
        )
        bodies = self._bodies()
        if merge and bodies:
            last = bodies[-1]
            lo, hi = _union_box([last, body])
            bodies[-1] = BodyState(last.name, last.volume + body.volume, lo, hi)
        else:
            bodies.append(body)

    def _next_feature(self, kind: str) -> str:
        """The next name for a body feature, e.g. ``Combine1``."""
        counts = self._body_feature_counts()
        counts[kind] = counts.get(kind, 0) + 1
        return f"{kind}{counts[kind]}"

    async def list_bodies(self) -> AdapterResult[dict[str, Any]]:
        """Mock: the active part's bodies.

        Returns:
            AdapterResult[dict[str, Any]]: As :func:`body_rules.listing`.
        """
        if not self._current_model:
            return _error("No active model")
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data=rules.listing(self._bodies())
        )

    async def _body_operation(
        self,
        kind: str,
        operation: str,
        change: Callable[[list[BodyState], str], list[BodyState]],
        verdict: Callable[[list[BodyState], list[BodyState]], tuple[str, bool]],
        own_fields: Callable[[], dict[str, Any]],
    ) -> AdapterResult[dict[str, Any]]:
        """Apply one body operation and judge it by its rule.

        Args:
            kind: The feature's kind, which names it (``Combine``...).
            operation: The tool's name, for messages.
            change: Gives the bodies after, from those before and the
                feature's name; raises InputRefused to refuse.
            verdict: The rule: the expectation in words and whether it held.
            own_fields: The reply's own fields, read after ``change``.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply, or the
            refusal; a refused or failed operation changes nothing.
        """
        if not self._current_model:
            return _error("No active model")
        before = list(self._bodies())
        feature = f"{kind}{self._body_feature_counts().get(kind, 0) + 1}"
        try:
            after = change(before, feature)
        except InputRefused as refused:
            return _error(str(refused))
        expected, ok = verdict(before, after)
        failed = rules.judge(operation, expected, before, after, ok=ok)
        if failed:
            return _error(failed)
        await asyncio.sleep(self._delays["feature_operation"])
        self._operation_count += 1
        self._next_feature(kind)
        self._body_store()[id(self._current_model)] = after
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={**rules.measured_reply(feature, before, after), **own_fields()},
            execution_time=self._delays["feature_operation"],
        )

    async def combine_bodies(
        self, params: CombineBodiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: add, subtract or keep the common volume of box bodies.

        Args:
            params: The operation, the main body and the tool bodies.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply.
        """

        names: list[str] = []

        def change(before: list[BodyState], feature: str) -> list[BodyState]:
            main_name, tool_names = rules.check_combine(params, before)
            names.extend([main_name, *tool_names])
            main = next(b for b in before if b.name == main_name)
            tools = [b for b in before if b.name in tool_names]
            shared = sum(_overlap(main, tool) for tool in tools)
            if params.operation == "add":
                volume = main.volume + sum(t.volume for t in tools) - shared
                lo, hi = _union_box([main, *tools])
            elif params.operation == "subtract":
                volume, lo, hi = main.volume - shared, main.box_min, main.box_max
            else:
                volume, lo, hi = shared, main.box_min, main.box_max
            result = BodyState(main.name, volume, lo, hi)
            return [
                result if b.name == main.name else b
                for b in before
                if b.name not in tool_names
            ]

        return await self._body_operation(
            "Combine",
            "combine_bodies",
            change,
            lambda before, after: rules.combine_ok(
                params.operation, names[0], names[1:], before, after
            ),
            lambda: {"operation": params.operation},
        )

    async def split_body(
        self, params: SplitBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: split box bodies at the Front, Top or Right Plane.

        Args:
            params: The plane.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``made``,
            the bodies the split made.
        """
        made: list[str] = []

        def change(before: list[BodyState], feature: str) -> list[BodyState]:
            axis = _SPLIT_PLANES.get(params.tool.lower())
            if axis is None:
                raise InputRefused(
                    f"No plane or sketch named '{params.tool}' to split with "
                    "(the mock splits at Front Plane, Top Plane or Right Plane)."
                )
            after: list[BodyState] = []
            for body in before:
                lo, hi = body.box_min[axis], body.box_max[axis]
                if not lo < 0 < hi:
                    after.append(body)
                    continue
                for a, b in ((lo, 0.0), (0.0, hi)):
                    low = list(body.box_min)
                    high = list(body.box_max)
                    low[axis], high[axis] = a, b
                    name = f"{feature}[{len(made) + 1}]"
                    made.append(name)
                    after.append(
                        BodyState(
                            name,
                            body.volume * (b - a) / (hi - lo),
                            (low[0], low[1], low[2]),
                            (high[0], high[1], high[2]),
                        )
                    )
            return after

        return await self._body_operation(
            "Split",
            "split_body",
            change,
            rules.split_ok,
            lambda: {"tool": params.tool, "made": list(made)},
        )

    async def move_copy_body(
        self, params: MoveCopyBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: move box bodies, or copy them, by the translation.

        Args:
            params: The bodies, the translation and the copies.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply.
        """
        moved: list[str] = []

        def change(before: list[BodyState], feature: str) -> list[BodyState]:
            rules.check_move(params)
            moved.extend(rules.resolve_bodies(before, params.bodies))
            step = params.translate
            if not params.as_copy:
                return [
                    _shifted(b, step, b.name) if b.name in moved else b for b in before
                ]
            copies = [
                _shifted(b, [n * v for v in step], f"{feature}[{n}]")
                for n in range(1, params.copies + 1)
                for b in before
                if b.name in moved
            ]
            return [*before, *copies]

        return await self._body_operation(
            "Body-Move/Copy",
            "move_copy_body",
            change,
            lambda before, after: rules.move_ok(params, moved, before, after),
            lambda: {
                "as_copy": params.as_copy,
                "copies": params.copies if params.as_copy else 0,
            },
        )

    async def delete_bodies(
        self, params: DeleteBodiesParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: delete bodies, or keep only them.

        Args:
            params: The bodies and whether to keep them.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``removed``.
        """
        removed: list[str] = []

        def change(before: list[BodyState], feature: str) -> list[BodyState]:
            removed.extend(rules.check_delete(params, before))
            return [b for b in before if b.name not in removed]

        return await self._body_operation(
            "Body-Delete/Keep",
            "delete_bodies",
            change,
            lambda before, after: rules.delete_ok(removed, before, after),
            lambda: {"keep": params.keep, "removed": list(removed)},
        )

    async def scale_body(
        self, params: ScaleBodyParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: scale box bodies about their centroid or the origin.

        Args:
            params: The factors, the centre and the bodies.

        Returns:
            AdapterResult[dict[str, Any]]: The measured reply with ``factors``.
        """
        scaled: list[str] = []
        factors: list[float] = []

        def change(before: list[BodyState], feature: str) -> list[BodyState]:
            factors.extend(rules.scale_factors(params))
            scaled.extend(
                rules.resolve_bodies(before, params.bodies)
                if params.bodies
                else [b.name for b in before]
            )
            product = factors[0] * factors[1] * factors[2]
            after = []
            for body in before:
                if body.name not in scaled:
                    after.append(body)
                    continue
                centre = (
                    [
                        (lo + hi) / 2
                        for lo, hi in zip(body.box_min, body.box_max, strict=True)
                    ]
                    if params.about == "centroid"
                    else [0.0, 0.0, 0.0]
                )
                lo = [
                    centre[i] + (body.box_min[i] - centre[i]) * factors[i]
                    for i in range(3)
                ]
                hi = [
                    centre[i] + (body.box_max[i] - centre[i]) * factors[i]
                    for i in range(3)
                ]
                after.append(
                    BodyState(
                        body.name,
                        body.volume * product,
                        (lo[0], lo[1], lo[2]),
                        (hi[0], hi[1], hi[2]),
                    )
                )
            return after

        return await self._body_operation(
            "Scale",
            "scale_body",
            change,
            lambda before, after: rules.scale_ok(
                (factors[0], factors[1], factors[2]), scaled, before, after
            ),
            lambda: {"factors": list(factors), "about": params.about},
        )
