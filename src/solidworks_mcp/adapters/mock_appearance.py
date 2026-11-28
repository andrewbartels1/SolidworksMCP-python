"""The mock adapter's colours (queue item 36).

Colours are held per open part, by level: the part's, each feature's, each
body's and each face's (a face by the point that picked it, on one of the
mock's box bodies, :mod:`mock_bodies`). A face belongs to the body whose box
it lies on, and to the feature of the same name, as the mock names a body
after the feature that made it. Refusals use the real adapter's rules
(:mod:`appearance_rules`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..exceptions import InputRefused
from . import appearance_rules as rules
from . import body_rules
from .base import (
    AdapterResult,
    AdapterResultStatus,
    AppearanceParameters,
    AppearanceTarget,
)
from .body_rules import BodyState

#: A new part's colour, as SolidWorks 2026 reads it.
_DEFAULT_PART = [0.894118, 0.894118, 0.894118, 1.0, 1.0, 0.5, 0.3125, 0.0, 0.0]
#: How close a point must be to a box's face to lie on it, mm.
_ON_FACE = 1e-6


def _error(message: str) -> AdapterResult[Any]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def face_of(bodies: list[BodyState], point: list[float]) -> tuple[BodyState, int, int]:
    """The box face a point lies on: the body, the face's normal axis and side.

    Args:
        bodies: The part's box bodies.
        point: ``[x, y, z]`` mm.

    Returns:
        tuple[BodyState, int, int]: The body, the axis (0-2) the face is
        normal to, and 0 for its low side or 1 for its high side.

    Raises:
        InputRefused: The point lies on no face.
    """
    for body in bodies:
        inside = all(
            body.box_min[i] - _ON_FACE <= point[i] <= body.box_max[i] + _ON_FACE
            for i in range(3)
        )
        if not inside:
            continue
        for axis in range(3):
            for side, plane in enumerate((body.box_min[axis], body.box_max[axis])):
                if abs(point[axis] - plane) <= _ON_FACE:
                    return body, axis, side
    raise InputRefused(
        f"No face at {list(point)} mm; give a point on the face's surface."
    )


class MockAppearanceMixin:
    """``set_appearance`` and ``get_appearance``, in memory."""

    _current_model: Any
    _features: dict[str, Any]
    #: From :class:`MockBodiesMixin`: the active part's box bodies.
    _bodies: Callable[[], list[BodyState]]

    def _colour_store(self) -> dict[tuple[int, str, str], list[float]]:
        """Each part's colours by ``(part, level, key)``."""
        if "_mock_colours" not in self.__dict__:
            self._mock_colours: dict[tuple[int, str, str], list[float]] = {}
        return self._mock_colours

    def _resolve_target(
        self, kind: str, target: AppearanceTarget
    ) -> list[tuple[str, str]]:
        """The target and the levels above it, as ``(level, key)``, nearest first.

        Raises:
            InputRefused: The feature, body or face isn't there.
        """
        if kind == "feature":
            names = [f.name for f in self._features.values()]
            if target.feature not in names:
                raise InputRefused(
                    f"No feature named '{target.feature}'; list_features names them."
                )
            return [("feature", str(target.feature)), ("part", "")]
        if kind == "body":
            real = body_rules.resolve_bodies(self._bodies(), [str(target.body)])[0]
            return [("body", real), ("part", "")]
        if kind == "face":
            point = list(target.face_point or [])
            body, axis, side = face_of(self._bodies(), point)
            return [
                ("face", f"{body.name}:{axis}:{side}"),
                ("feature", body.name),
                ("body", body.name),
                ("part", ""),
            ]
        return [("part", "")]

    def _values(self, level: str, key: str) -> list[float] | None:
        """A level's own colour; the part has the default when unset."""
        own = self._colour_store().get((id(self._current_model), level, key))
        if own is None and level == "part":
            return list(_DEFAULT_PART)
        return own

    def _showing(self, chain: list[tuple[str, str]]) -> dict[str, Any]:
        """The colour that shows, walking up the chain."""
        for level, key in chain:
            color = rules.color_reply(self._values(level, key))
            if color is not None:
                return {**color, "level": level}
        return {"color": None, "hex": None, "transparency": None, "level": None}

    def _named(self, kind: str, target: AppearanceTarget) -> dict[str, Any]:
        """The reply field naming the target."""
        field = {"feature": "feature", "body": "body", "face": "face_point"}.get(kind)
        return {field: getattr(target, field)} if field else {}

    async def set_appearance(
        self, params: AppearanceParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: colour a target, or remove its colour.

        Args:
            params: The target, the colour and transparency, or ``reset``.

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        try:
            kind = rules.check_set(params)
            chain = self._resolve_target(kind, params)
        except InputRefused as refused:
            return _error(str(refused))
        level, key = chain[0]
        store = self._colour_store()
        if params.reset:
            store.pop((id(self._current_model), level, key), None)
            reply: dict[str, Any] = {"reset": True, "showing": self._showing(chain)}
        else:
            rgb = rules.parse_color(params.color)
            store[(id(self._current_model), level, key)] = rules.material_values(
                rgb, params.transparency
            )
            reply = dict(
                rules.color_reply(store[(id(self._current_model), level, key)]) or {}
            )
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"target": kind, **self._named(kind, params), **reply},
        )

    async def get_appearance(
        self, params: AppearanceTarget
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: the colour a target shows and its level.

        Args:
            params: The target; none for the part.

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        try:
            kind = rules.target_kind(params)
            chain = self._resolve_target(kind, params)
        except InputRefused as refused:
            return _error(str(refused))
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"target": kind, **self._named(kind, params), **self._showing(chain)},
        )
