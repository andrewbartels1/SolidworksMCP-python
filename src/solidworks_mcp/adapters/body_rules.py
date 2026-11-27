"""The rules every multi-body operation is held to (queue item 35).

Pure functions, shared by the SolidWorks adapter and the mock so both refuse
the same inputs with the same words and judge a result the same way:

- :func:`resolve_bodies` finds bodies by name, ignoring case, and refuses an
  unknown one by listing the real ones.
- ``check_*`` refuse inputs that can't work before anything is built.
- :func:`judge` decides whether the bodies after an operation are ones its
  kind can produce (a subtract removes volume, a split adds bodies...).
- :func:`measured_reply` gives the reply's before-and-after fields.

Volumes are mm³; a volume counts as unchanged within :data:`SAME`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..exceptions import InputRefused
from .base import (
    CombineBodiesParameters,
    DeleteBodiesParameters,
    MoveCopyBodyParameters,
    ScaleBodyParameters,
)

#: Relative tolerance for "the volume is unchanged".
SAME = 1e-3
#: Relative tolerance for a scaled volume (SolidWorks's tessellation).
SCALED = 5e-3
#: The most copies one move/copy makes.
MAX_COPIES = 50
#: ``combine_bodies`` operations.
COMBINE_OPERATIONS = ("add", "subtract", "common")
#: ``scale_body`` centres.
SCALE_CENTRES = ("centroid", "origin")


@dataclass(frozen=True)
class BodyState:
    """One solid body as measured: its name, volume and bounding box.

    Attributes:
        name: The body's name, as ``list_bodies`` gives it.
        volume: mm³.
        box_min: The box's lowest corner ``(x, y, z)``, mm.
        box_max: The box's highest corner ``(x, y, z)``, mm.
    """

    name: str
    volume: float
    box_min: tuple[float, float, float]
    box_max: tuple[float, float, float]

    def entry(self) -> dict[str, Any]:
        """The body as ``list_bodies`` lists it.

        Returns:
            dict[str, Any]: ``name``, ``volume_mm3`` and ``bounding_box_mm``
            (``min``, ``max`` and ``size``), rounded to 0.001.
        """
        size = [hi - lo for lo, hi in zip(self.box_min, self.box_max, strict=True)]
        return {
            "name": self.name,
            "volume_mm3": round(self.volume, 3),
            "bounding_box_mm": {
                "min": [round(v, 3) for v in self.box_min],
                "max": [round(v, 3) for v in self.box_max],
                "size": [round(v, 3) for v in size],
            },
        }


def listing(bodies: Sequence[BodyState]) -> dict[str, Any]:
    """The ``list_bodies`` reply for these bodies.

    Args:
        bodies: The part's solid bodies, in tree order.

    Returns:
        dict[str, Any]: ``bodies``, ``count`` and ``total_volume_mm3``.
    """
    return {
        "bodies": [body.entry() for body in bodies],
        "count": len(bodies),
        "total_volume_mm3": round(sum(body.volume for body in bodies), 3),
    }


def _names(bodies: Sequence[BodyState]) -> str:
    """The bodies' names for a message, or ``none``."""
    return ", ".join(body.name for body in bodies) or "none"


def resolve_bodies(bodies: Sequence[BodyState], wanted: Sequence[str]) -> list[str]:
    """The real names of the bodies ``wanted`` names, ignoring case.

    Args:
        bodies: The part's solid bodies.
        wanted: The names given.

    Returns:
        list[str]: Each body's name as the part spells it, in the order given.

    Raises:
        InputRefused: No name was given, or one matches no body.

    Example:
        >>> block = BodyState("Boss-Extrude1", 1.0, (0, 0, 0), (1, 1, 1))
        >>> resolve_bodies([block], ["boss-extrude1"])
        ['Boss-Extrude1']
    """
    if not wanted:
        raise InputRefused(
            f"Name at least one body. Bodies in the part: {_names(bodies)}."
        )
    found: list[str] = []
    for name in wanted:
        match = next((b.name for b in bodies if b.name.lower() == name.lower()), None)
        if match is None:
            raise InputRefused(
                f"No body named '{name}'. Bodies in the part: {_names(bodies)}."
            )
        if match not in found:
            found.append(match)
    return found


def check_combine(
    params: CombineBodiesParameters, bodies: Sequence[BodyState]
) -> tuple[str, list[str]]:
    """The main body's and the tool bodies' real names, or a refusal.

    Args:
        params: The operation and the bodies named.
        bodies: The part's solid bodies.

    Returns:
        tuple[str, list[str]]: The main body and the tool bodies.

    Raises:
        InputRefused: An unknown operation or body, no tool body, or the main
            body among the tools.
    """
    if params.operation not in COMBINE_OPERATIONS:
        raise InputRefused(
            f"operation must be one of {', '.join(COMBINE_OPERATIONS)} "
            f"(got '{params.operation}')."
        )
    main = resolve_bodies(bodies, [params.main_body])[0]
    if not params.tool_bodies:
        raise InputRefused(
            f"Name at least one tool body to {params.operation} with "
            f"'{main}'. Bodies in the part: {_names(bodies)}."
        )
    tools = resolve_bodies(bodies, params.tool_bodies)
    if main in tools:
        raise InputRefused(
            f"The main body '{main}' can't also be a tool body; name the "
            f"others. Bodies in the part: {_names(bodies)}."
        )
    return main, tools


def check_move(params: MoveCopyBodyParameters) -> None:
    """Refuse a move that does nothing or copies out of range.

    Args:
        params: The move or copy.

    Raises:
        InputRefused: A vector that isn't three numbers, no translation and
            no rotation, both, or ``copies`` outside 1 to :data:`MAX_COPIES`.
    """
    for field in ("translate", "rotate", "rotation_point"):
        if len(getattr(params, field)) != 3:
            raise InputRefused(f"{field} must be [x, y, z].")
    if not any(params.translate) and not any(params.rotate):
        raise InputRefused(
            "Give a translate or a rotate: a move by [0, 0, 0] does nothing."
        )
    if any(params.translate) and any(params.rotate):
        # SolidWorks applies only the rotation when both are given (probe,
        # 2026-11-26), so one call can't do both.
        raise InputRefused(
            "Give a translate or a rotate, not both: SolidWorks applies only "
            "the rotation. Call move_copy_body twice."
        )
    if params.as_copy and not 1 <= params.copies <= MAX_COPIES:
        raise InputRefused(f"copies must be 1 to {MAX_COPIES} (got {params.copies}).")


def check_delete(
    params: DeleteBodiesParameters, bodies: Sequence[BodyState]
) -> list[str]:
    """The bodies a delete or keep removes, or a refusal.

    Args:
        params: The bodies named and whether to keep them.
        bodies: The part's solid bodies.

    Returns:
        list[str]: The names of the bodies to remove.

    Raises:
        InputRefused: An unknown body, or the call would remove every body
            (or none).
    """
    named = resolve_bodies(bodies, params.bodies)
    removed = [b.name for b in bodies if b.name not in named] if params.keep else named
    if len(removed) == len(bodies):
        raise InputRefused(
            "That would delete every body in the part; keep at least one."
        )
    if not removed:
        raise InputRefused(
            "Keeping every body deletes nothing; name the bodies to keep."
        )
    return removed


def scale_factors(params: ScaleBodyParameters) -> tuple[float, float, float]:
    """The x, y and z factors of a scale, or a refusal.

    Args:
        params: ``scale`` or ``scale_xyz``, and the centre.

    Returns:
        tuple[float, float, float]: The three factors.

    Raises:
        InputRefused: Neither or both of ``scale`` and ``scale_xyz``, a factor
            of 0 or less, every factor 1, or an unknown centre.
    """
    if (params.scale is None) == (params.scale_xyz is None):
        raise InputRefused("Give scale (one factor) or scale_xyz ([x, y, z]).")
    if params.about not in SCALE_CENTRES:
        raise InputRefused(
            f"about must be one of {', '.join(SCALE_CENTRES)} (got '{params.about}')."
        )
    if params.scale is not None:
        factors = (params.scale, params.scale, params.scale)
    else:
        xyz = list(params.scale_xyz or [])
        if len(xyz) != 3:
            raise InputRefused("scale_xyz must be [x, y, z].")
        factors = (xyz[0], xyz[1], xyz[2])
    if min(factors) <= 0:
        raise InputRefused("Scale factors must be greater than 0.")
    if all(factor == 1 for factor in factors):
        raise InputRefused("A scale of 1 on every axis does nothing.")
    return factors


def _total(bodies: Sequence[BodyState]) -> float:
    """The bodies' volume, mm³."""
    return sum(body.volume for body in bodies)


def _same(a: float, b: float, tolerance: float = SAME) -> bool:
    """Whether two volumes agree within ``tolerance`` of the larger."""
    return abs(a - b) <= tolerance * max(abs(a), abs(b), 1e-9)


def _volume_of(bodies: Sequence[BodyState], names: Sequence[str]) -> float:
    """The named bodies' volume, mm³."""
    return sum(body.volume for body in bodies if body.name in names)


def judge(
    operation: str,
    expected: str,
    before: Sequence[BodyState],
    after: Sequence[BodyState],
    *,
    ok: bool,
) -> str | None:
    """The refusal for a result that breaks its rule, or None.

    Args:
        operation: The tool's name, for the message.
        expected: What the operation should have done, e.g. "remove volume".
        before: The bodies before.
        after: The bodies after.
        ok: Whether the result meets the rule.

    Returns:
        str | None: The message, or None when ``ok``.
    """
    if ok:
        return None
    return (
        f"{operation} should {expected} but the part went from "
        f"{len(before)} bodies, {_total(before):.1f} mm³ to {len(after)} "
        f"bodies, {_total(after):.1f} mm³; the feature was removed."
    )


def combine_ok(
    operation: str,
    main: str,
    tools: Sequence[str],
    before: Sequence[BodyState],
    after: Sequence[BodyState],
) -> tuple[str, bool]:
    """What a combine should do, and whether it did.

    The result is judged by its own volume: the part's volume after, less
    the bodies the combine didn't touch. A part's total alone can't tell a
    subtract that cut from one that only consumed a tool lying elsewhere.

    Args:
        operation: ``add``, ``subtract`` or ``common``.
        main: The main body's name.
        tools: The tool bodies' names.
        before: The bodies before.
        after: The bodies after.

    Returns:
        tuple[str, bool]: The expectation in words and the verdict.
    """
    involved = {main, *tools}
    untouched = _total([b for b in before if b.name not in involved])
    result = _total(after) - untouched
    main_volume = _volume_of(before, [main])
    if operation == "add":
        combined = _volume_of(before, list(involved))
        return "join the bodies into one, with no more volume than they had", (
            len(after) < len(before) and result <= combined * (1 + SAME)
        )
    return "leave the main body smaller", result < main_volume * (1 - SAME)


def split_ok(
    before: Sequence[BodyState], after: Sequence[BodyState]
) -> tuple[str, bool]:
    """A split makes more bodies and keeps the volume."""
    return "make more bodies and keep the volume", len(after) > len(before) and _same(
        _total(after), _total(before)
    )


def move_ok(
    params: MoveCopyBodyParameters,
    moved: Sequence[str],
    before: Sequence[BodyState],
    after: Sequence[BodyState],
) -> tuple[str, bool]:
    """A move changes boxes and nothing else; a copy adds bodies and volume.

    Args:
        params: The move or copy.
        moved: The bodies named.
        before: The bodies before.
        after: The bodies after.

    Returns:
        tuple[str, bool]: The expectation in words and the verdict.
    """
    if params.as_copy:
        count = len(before) + params.copies * len(moved)
        volume = _total(before) + params.copies * _volume_of(before, moved)
        return (
            f"add {params.copies * len(moved)} bodies and their volume",
            len(after) == count and _same(_total(after), volume),
        )
    boxes = {(b.box_min, b.box_max) for b in before}
    shifted = any((b.box_min, b.box_max) not in boxes for b in after)
    return "move the bodies and keep the volume", (
        len(after) == len(before) and _same(_total(after), _total(before)) and shifted
    )


def delete_ok(
    removed: Sequence[str],
    before: Sequence[BodyState],
    after: Sequence[BodyState],
) -> tuple[str, bool]:
    """A delete removes those bodies and their volume."""
    volume = _total(before) - _volume_of(before, removed)
    return f"remove {len(removed)} bodies and their volume", (
        len(after) == len(before) - len(removed) and _same(_total(after), volume)
    )


def scale_ok(
    factors: tuple[float, float, float],
    scaled: Sequence[str],
    before: Sequence[BodyState],
    after: Sequence[BodyState],
) -> tuple[str, bool]:
    """A scale multiplies the scaled bodies' volume by the factors' product."""
    product = factors[0] * factors[1] * factors[2]
    part = _volume_of(before, scaled)
    volume = _total(before) - part + part * product
    return f"multiply the scaled volume by {product:g}", (
        len(after) == len(before) and _same(_total(after), volume, SCALED)
    )


def measured_reply(
    feature: str, before: Sequence[BodyState], after: Sequence[BodyState]
) -> dict[str, Any]:
    """The fields every body operation's reply carries.

    Args:
        feature: The new feature's name.
        before: The bodies before.
        after: The bodies after.

    Returns:
        dict[str, Any]: ``name``, the body names, counts and volumes before
        and after, and the volume change.
    """
    return {
        "name": feature,
        "bodies_before": [b.name for b in before],
        "bodies_after": [b.name for b in after],
        "body_count_before": len(before),
        "body_count_after": len(after),
        "volume_before_mm3": round(_total(before), 3),
        "volume_after_mm3": round(_total(after), 3),
        "volume_change_mm3": round(_total(after) - _total(before), 3),
    }
