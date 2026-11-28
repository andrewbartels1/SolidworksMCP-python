"""Rules shared by the appearance and reference-extras adapters (queue items 36, 39).

Pure functions, used by the SolidWorks adapter and the mock alike, so both
refuse the same inputs with the same words and shape replies the same way:

- :func:`target_kind` says which one target a call names, refusing two.
- :func:`parse_color` reads ``[r, g, b]`` or ``#rrggbb``;
  :func:`material_values` and :func:`color_reply` convert to and from
  SolidWorks's nine material values.
- :func:`section_reply` and :func:`transform_reply` read SolidWorks's
  section-property and coordinate-system arrays (metres) into mm.

The array layouts were measured on SolidWorks 2026 (design.md).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..exceptions import InputRefused
from .base import AppearanceParameters, AppearanceTarget

#: SolidWorks's shading values a new colour keeps: ambient, diffuse,
#: specular, shininess (read from a new part's colour on SolidWorks 2026).
SHADING = (1.0, 1.0, 0.5, 0.3125)
#: The levels a colour can come from, the one that shows first: SolidWorks's
#: appearance hierarchy (a face over its feature over its body over the part).
LEVELS = ("face", "feature", "body", "part")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
#: ``GetSectionProperties2``'s status for a section it computed.
SECTION_OK = 0


def target_kind(target: AppearanceTarget) -> str:
    """The one target a call names: ``part``, ``feature``, ``body`` or ``face``.

    Args:
        target: The call's target fields.

    Returns:
        str: The target's kind; ``part`` when none is given.

    Raises:
        InputRefused: More than one target, or a ``face_point`` that isn't
            three numbers.

    Example:
        >>> target_kind(AppearanceTarget(feature="Boss-Extrude1"))
        'feature'
    """
    given = [
        kind
        for kind, value in (
            ("feature", target.feature),
            ("body", target.body),
            ("face", target.face_point),
        )
        if value is not None
    ]
    if len(given) > 1:
        raise InputRefused(
            f"Give one target, not {' and '.join(given)}: a feature, a body, "
            "a face_point, or none for the whole part."
        )
    if target.face_point is not None and len(target.face_point) != 3:
        raise InputRefused("face_point must be [x, y, z] in mm.")
    return given[0] if given else "part"


def parse_color(value: Sequence[int] | str | None) -> tuple[int, int, int]:
    """An ``[r, g, b]`` (0-255) or ``#rrggbb`` colour as three ints.

    Args:
        value: The colour as the caller gave it.

    Returns:
        tuple[int, int, int]: Red, green and blue, 0-255.

    Raises:
        InputRefused: No colour, or one that isn't three 0-255 values or a
            six-digit hex string.

    Example:
        >>> parse_color("#1fcc33")
        (31, 204, 51)
    """
    if value is None:
        raise InputRefused(
            "Give a color, [r, g, b] 0-255 or '#rrggbb', or reset: true to remove one."
        )
    if isinstance(value, str):
        match = _HEX.match(value.strip())
        if not match:
            raise InputRefused(f"color '{value}' is not '#rrggbb'.")
        digits = match.group(1)
        red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
        return red, green, blue
    if len(value) != 3 or not all(0 <= int(v) <= 255 for v in value):
        raise InputRefused(f"color {list(value)} must be [r, g, b], each 0 to 255.")
    return int(value[0]), int(value[1]), int(value[2])


def check_set(params: AppearanceParameters) -> str:
    """Refuse a ``set_appearance`` call that can't work; return its target kind.

    Args:
        params: The call.

    Returns:
        str: The target's kind.

    Raises:
        InputRefused: Two targets, a reset of the whole part, a colour with
            a reset, no colour without one, or a transparency outside 0-1.
    """
    kind = target_kind(params)
    if params.reset:
        if kind == "part":
            raise InputRefused(
                "reset removes a feature's, body's or face's own colour; the "
                "part's colour is the base. Give the part a colour instead."
            )
        if params.color is not None:
            raise InputRefused("Give a color or reset: true, not both.")
        return kind
    parse_color(params.color)
    if not 0.0 <= params.transparency <= 1.0:
        raise InputRefused(
            f"transparency must be 0 (opaque) to 1 (clear), not {params.transparency}."
        )
    return kind


def material_values(rgb: tuple[int, int, int], transparency: float) -> list[float]:
    """SolidWorks's nine material values for a colour.

    Args:
        rgb: Red, green and blue, 0-255.
        transparency: 0 to 1.

    Returns:
        list[float]: R, G, B (0-1), ambient, diffuse, specular, shininess,
        transparency, emission.
    """
    return [c / 255.0 for c in rgb] + [*SHADING, float(transparency), 0.0]


def color_reply(values: Any) -> dict[str, Any] | None:
    """A colour read from SolidWorks, or None when the target has none.

    SolidWorks gives no colour as ``None`` (a face) or nine ``-1`` (a
    feature).

    Args:
        values: The nine material values, or None.

    Returns:
        dict[str, Any] | None: ``color`` ``[r, g, b]`` 0-255, ``hex`` and
        ``transparency``; None when there is no colour.

    Example:
        >>> color_reply([0.1, 0.8, 0.2, 1, 1, 0.5, 0.3125, 0, 0])["hex"]
        '#1acc33'
    """
    if not isinstance(values, (list, tuple)) or len(values) < 8:
        return None
    if all(float(v) < 0 for v in values[:3]):
        return None
    rgb = [round(float(v) * 255) for v in values[:3]]
    return {
        "color": rgb,
        "hex": "#{:02x}{:02x}{:02x}".format(*rgb),
        "transparency": round(float(values[7]), 3),
    }


def section_reply(values: Any) -> dict[str, Any]:
    """A face's section properties, in mm, from ``GetSectionProperties2``.

    Args:
        values: SolidWorks's array: status, area (m²), centroid (m), six
            moments at the centroid (m⁴), the polar moment, the principal
            axes' angle, the two principal moments.

    Returns:
        dict[str, Any]: ``area_mm2``, ``centroid_mm``, ``ixx`` ... ``iyz``
        (mm⁴), ``polar_moment_mm4`` and ``principal_moments_mm4``.

    Raises:
        InputRefused: SolidWorks returned nothing or a status other than ok.
    """
    if not isinstance(values, (list, tuple)) or len(values) < 15:
        raise InputRefused(
            "SolidWorks gave no section properties for that face; pick a "
            "point on a planar face."
        )
    if int(values[0]) != SECTION_OK:
        raise InputRefused(
            f"SolidWorks couldn't take a section of that face (status "
            f"{int(values[0])}); pick a point on a planar face."
        )
    mm4 = 1e12
    names = ("ixx", "iyy", "izz", "ixy", "izx", "iyz")
    reply: dict[str, Any] = {
        "area_mm2": round(float(values[1]) * 1e6, 4),
        "centroid_mm": [round(float(v) * 1000, 4) for v in values[2:5]],
    }
    reply.update(
        {
            name: round(float(v) * mm4, 2)
            for name, v in zip(names, values[5:11], strict=True)
        }
    )
    reply["polar_moment_mm4"] = round(float(values[11]) * mm4, 2)
    reply["principal_moments_mm4"] = [round(float(v) * mm4, 2) for v in values[13:15]]
    return reply


def transform_reply(array: Any) -> dict[str, Any]:
    """A coordinate system's origin and axes from its transform's ``ArrayData``.

    Args:
        array: SolidWorks's 16 values: the 3x3 rotation by rows, the origin
            (m), the scale and three unused.

    Returns:
        dict[str, Any]: ``origin_mm`` and ``x_axis``, ``y_axis``, ``z_axis``.

    Raises:
        RuntimeError: The transform couldn't be read.
    """
    if not isinstance(array, (list, tuple)) or len(array) < 12:
        raise RuntimeError("Could not read the coordinate system's transform.")
    axes = [[round(float(v), 6) + 0.0 for v in array[i : i + 3]] for i in (0, 3, 6)]
    return {
        "origin_mm": [round(float(v) * 1000, 4) for v in array[9:12]],
        "x_axis": axes[0],
        "y_axis": axes[1],
        "z_axis": axes[2],
    }


def model_axes() -> dict[str, list[float]]:
    """The axes of a coordinate system along the model's.

    Returns:
        dict[str, list[float]]: ``x_axis``, ``y_axis`` and ``z_axis``.
    """
    return {
        "x_axis": [1.0, 0.0, 0.0],
        "y_axis": [0.0, 1.0, 0.0],
        "z_axis": [0.0, 0.0, 1.0],
    }
