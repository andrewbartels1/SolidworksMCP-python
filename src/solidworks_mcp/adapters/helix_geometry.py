"""A helix's numbers, worked out the same way by the real and the mock adapter.

A helix is defined by two of height, pitch and revolutions (height = pitch x
revolutions); a flat spiral by pitch and revolutions alone. Lengths are
millimetres and angles degrees. Spec: ``tools/helix``.
"""

from __future__ import annotations

import math

from ..exceptions import InputRefused

#: ``swHelixDefinedBy_e``, from SolidWorks 2026's constants type library.
HELIX_DEFINED_BY: dict[str, int] = {
    "pitch_and_revolutions": 0,
    "height_and_revolutions": 1,
    "height_and_pitch": 2,
    "spiral": 3,
}

#: The two values each ``defined_by`` takes.
_GIVEN: dict[str, tuple[str, str]] = {
    "pitch_and_revolutions": ("pitch", "revolutions"),
    "height_and_revolutions": ("height", "revolutions"),
    "height_and_pitch": ("height", "pitch"),
    "spiral": ("pitch", "revolutions"),
}


def helix_values(
    defined_by: str,
    height: float | None,
    pitch: float | None,
    revolutions: float | None,
) -> tuple[float, float, float]:
    """The helix's height, pitch and revolutions, from the two that define it.

    Args:
        defined_by: One of :data:`HELIX_DEFINED_BY`'s keys.
        height: The height, mm; needed by the ``height_*`` choices.
        pitch: The distance between turns, mm.
        revolutions: The number of turns.

    Returns:
        tuple[float, float, float]: ``(height, pitch, revolutions)``; a
        spiral's height is 0.

    Raises:
        InputRefused: ``defined_by`` is unknown, or one of its two values is
            missing, zero or negative.

    Example::

        helix_values("height_and_pitch", 48, 6, None)  # (48.0, 6.0, 8.0)
    """
    if defined_by not in _GIVEN:
        raise InputRefused(
            f"defined_by '{defined_by}' is not one of: {', '.join(_GIVEN)}."
        )
    given = {"height": height, "pitch": pitch, "revolutions": revolutions}
    for field in _GIVEN[defined_by]:
        value = given[field]
        if value is None:
            raise InputRefused(f"defined_by '{defined_by}' needs {field}.")
        if value <= 0:
            raise InputRefused(f"{field} must be greater than 0 (got {value:g}).")
    if defined_by == "height_and_pitch":
        h, p = float(height or 0), float(pitch or 0)
        return h, p, h / p
    if defined_by == "height_and_revolutions":
        h, n = float(height or 0), float(revolutions or 0)
        return h, h / n, n
    p, n = float(pitch or 0), float(revolutions or 0)
    # A spiral stays in its sketch's plane, so it has no height.
    return (0.0 if defined_by == "spiral" else p * n), p, n


def helix_length(
    diameter: float,
    pitch: float,
    revolutions: float,
    *,
    spiral: bool = False,
    height: float = 0.0,
    taper_angle: float | None = None,
    taper_outward: bool = False,
) -> float:
    """The helix's length, mm, worked out (the fallback when it can't be read).

    A straight helix is ``revolutions`` turns of ``sqrt((pi D)^2 + p^2)``. A
    tapered one uses the mean of its first and last diameters. A spiral's
    radius grows by the pitch every turn, so its length is
    ``pi n (D + n p)``.

    Args:
        diameter: The base circle's diameter, mm.
        pitch: The distance between turns, mm.
        revolutions: The number of turns.
        spiral: A flat spiral rather than a helix.
        height: The helix's height, mm (for a taper).
        taper_angle: The taper, degrees; none for a straight helix.
        taper_outward: The taper widens rather than narrows.

    Returns:
        float: The length, mm.
    """
    if spiral:
        return math.pi * revolutions * (diameter + revolutions * pitch)
    mean = diameter
    if taper_angle:
        change = 2 * height * math.tan(math.radians(taper_angle))
        mean = diameter + (change if taper_outward else -change) / 2
    return revolutions * math.hypot(math.pi * mean, pitch)
