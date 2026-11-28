"""The rules for modelled threads (queue item 43), shared by the adapter and the mock.

Pure functions:

- :func:`parse_size` reads a profile size (``M6x1.0``, ``1/4-20``,
  ``#10-32``) into its nominal diameter and pitch in mm;
- :func:`size_table` lists sizes with coarse or fine, the ISO 68-1 basic
  depth and the ISO 3508 runout;
- :func:`check_diameter` refuses a cylinder whose diameter doesn't suit the
  size;
- :func:`match_size` finds a size by name, ignoring case, or refuses with the
  nearest names.

Sources (research note ``openspec/research/modelled-threads.md``):

- ISO 68-1: H = √3/2 P; the basic depth of engagement H1 = 5/8 H.
- ISO 3508 (read in IS 1369 Part 1): runout x, normal ≈ 2.5P, short
  ≈ 1.25P. For inch threads the same rule on P = 25.4/TPI is a reasoned
  default, not a standard (the user's decision 6).
- Numbered inch sizes: #N is 0.060 + 0.013 N inch (ASME B1.1).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ..exceptions import InputRefused
from .base import ThreadParameters

#: The standards and their profile names.
STANDARDS = ("metric", "inch")
#: ``(standard, kind) -> profile`` in the Thread Profiles folder.
PROFILES = {
    ("metric", "external"): "Metric Die",
    ("metric", "internal"): "Metric Tap",
    ("inch", "external"): "Inch Die",
    ("inch", "internal"): "Inch Tap",
}
#: ISO 68-1: the basic depth of engagement over the pitch, 5/8 × √3/2.
BASIC_DEPTH = 5 / 8 * math.sqrt(3) / 2
#: ISO 3508 runout over the pitch.
RUNOUT = {"normal": 2.5, "short": 1.25}
#: Where each standard's runout rule comes from.
RUNOUT_BASIS = {
    "metric": "ISO 3508 (normal 2.5P, short 1.25P)",
    "inch": (
        "the ISO 3508 rule on the inch pitch (P = 25.4/TPI): a reasoned "
        "default, as no free inch standard gives a runout length"
    ),
}
MM_PER_INCH = 25.4
_METRIC = re.compile(r"^M(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$", re.IGNORECASE)
_INCH = re.compile(r"^(#\d+|\d+-\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")
_NEAREST = 6


@dataclass(frozen=True)
class ThreadSize:
    """One thread size.

    Attributes:
        size: The profile's name for it, e.g. ``M6x1.0``.
        diameter_mm: The nominal (major) diameter.
        pitch_mm: The pitch.
        tpi: Threads per inch (inch sizes), else None.
    """

    size: str
    diameter_mm: float
    pitch_mm: float
    tpi: float | None = None


def _inch_diameter(text: str) -> float:
    """A nominal inch size in inches: ``#10``, ``1/4``, ``1-1/2`` or ``0.2500``."""
    if text.startswith("#"):
        return 0.060 + 0.013 * int(text[1:])
    if "/" not in text:
        return float(text)
    whole, _, fraction = text.rpartition("-")
    numerator, denominator = fraction.split("/")
    return (float(whole) if whole else 0.0) + int(numerator) / int(denominator)


def inch_label(diameter_in: float, tpi: float) -> str | None:
    """A fractional name, e.g. ``1/4-20``, for a size in 64ths of an inch.

    Args:
        diameter_in: The nominal diameter, inches.
        tpi: Threads per inch.

    Returns:
        str | None: ``1/4-20`` or ``1-1/2-6``; None when the diameter isn't
        a whole number of 64ths.
    """
    sixty_fourths = diameter_in * 64
    if abs(sixty_fourths - round(sixty_fourths)) > 1e-6:
        return None
    whole, part = divmod(round(sixty_fourths), 64)
    turns = f"{tpi:g}"
    if part == 0:
        return f"{whole}-{turns}"
    fraction = Fraction(part, 64)
    text = f"{fraction.numerator}/{fraction.denominator}"
    return f"{whole}-{text}-{turns}" if whole else f"{text}-{turns}"


def parse_size(size: str) -> ThreadSize | None:
    """A profile size read as diameter and pitch, or None if it isn't one.

    Args:
        size: ``M6x1.0``, ``1/4-20``, ``#10-32`` or ``1-1/2-6``.

    Returns:
        ThreadSize | None: The size, or None for a name in another form.

    Example:
        >>> parse_size("1/4-20").pitch_mm
        1.27
    """
    text = size.strip()
    metric = _METRIC.match(text)
    if metric:
        return ThreadSize(text, float(metric.group(1)), float(metric.group(2)))
    inch = _INCH.match(text)
    if inch:
        tpi = float(inch.group(2))
        return ThreadSize(
            text,
            round(_inch_diameter(inch.group(1)) * MM_PER_INCH, 4),
            round(MM_PER_INCH / tpi, 4),
            tpi,
        )
    return None


def runout(pitch_mm: float) -> dict[str, float]:
    """The ISO 3508 runout for a pitch: normal and short, mm."""
    return {name: round(factor * pitch_mm, 2) for name, factor in RUNOUT.items()}


def size_entry(size: ThreadSize, pitch_class: str) -> dict[str, Any]:
    """One size as ``list_thread_sizes`` lists it."""
    entry: dict[str, Any] = {
        "size": size.size,
        "diameter_mm": size.diameter_mm,
        "pitch_mm": size.pitch_mm,
        "pitch_class": pitch_class,
        "basic_depth_mm": round(BASIC_DEPTH * size.pitch_mm, 4),
        "runout_mm": runout(size.pitch_mm),
    }
    if size.tpi is not None:
        entry["tpi"] = size.tpi
        # Decimal names ("0.2500-20") also go by their fraction ("1/4-20");
        # numbered sizes ("#5-40") keep their own name.
        label = inch_label(size.diameter_mm / MM_PER_INCH, size.tpi)
        if label and not size.size.startswith("#") and label != size.size:
            entry["also"] = label
    return entry


def size_table(
    names: Sequence[str], coarse: dict[float, float] | None = None
) -> list[dict[str, Any]]:
    """Sizes by diameter then pitch, each classed coarse, fine or only.

    With ``coarse`` (nominal diameter -> coarse pitch, e.g. from the Hole
    Wizard's plain ``M6`` rows), a size at a known diameter is ``coarse``
    when its pitch is that one and ``fine`` otherwise. Elsewhere the list
    decides: at one diameter the coarsest pitch is ``coarse`` and the others
    ``fine``, and a diameter with one size is ``only``. Names that aren't
    sizes are left out.

    Args:
        names: The profile's configuration names.
        coarse: Known coarse pitches by diameter, mm.

    Returns:
        list[dict[str, Any]]: :func:`size_entry` for each size.
    """
    known = coarse or {}
    sizes = [parsed for name in names if (parsed := parse_size(str(name)))]
    by_diameter: dict[float, list[ThreadSize]] = {}
    for size in sizes:
        by_diameter.setdefault(size.diameter_mm, []).append(size)
    table = []
    for diameter in sorted(by_diameter):
        group = sorted(by_diameter[diameter], key=lambda s: -s.pitch_mm)
        for index, size in enumerate(group):
            if diameter in known:
                same = abs(size.pitch_mm - known[diameter]) < 1e-6
                pitch_class = "coarse" if same else "fine"
            elif len(group) == 1:
                pitch_class = "only"
            else:
                pitch_class = "coarse" if index == 0 else "fine"
            table.append(size_entry(size, pitch_class))
    return table


def match_size(names: Sequence[str], wanted: str) -> ThreadSize:
    """The size ``wanted`` names, ignoring case, as the profile spells it.

    Args:
        names: The profile's sizes.
        wanted: The size asked for.

    Returns:
        ThreadSize: The size.

    Raises:
        InputRefused: No such size; the message names the nearest ones.
    """
    folded = wanted.strip().lower().replace(" ", "")
    for name in names:
        if str(name).lower() == folded:
            parsed = parse_size(str(name))
            if parsed:
                return parsed
    asked = parse_size(wanted)
    sizes = [parsed for name in names if (parsed := parse_size(str(name)))]
    for size in sizes:
        if (
            asked
            and abs(size.diameter_mm - asked.diameter_mm) < 1e-3
            and abs(size.pitch_mm - asked.pitch_mm) < 1e-3
        ):
            return size
    if asked:
        sizes.sort(
            key=lambda s: (
                abs(s.diameter_mm - asked.diameter_mm),
                abs(s.pitch_mm - asked.pitch_mm),
            )
        )
    nearest = ", ".join(s.size for s in sizes[:_NEAREST]) or "none"
    raise InputRefused(
        f"No thread size '{wanted}' in the profile; nearest: {nearest}. "
        "list_thread_sizes names them all."
    )


def expected_diameter(size: ThreadSize, kind: str) -> float:
    """The cylinder diameter a thread wants: nominal, or about the tap drill."""
    if kind == "internal":
        return round(size.diameter_mm - size.pitch_mm, 4)
    return size.diameter_mm


def check_diameter(size: ThreadSize, kind: str, edge_diameter_mm: float) -> None:
    """Refuse an edge whose diameter doesn't suit the size, within one pitch.

    Args:
        size: The thread size.
        kind: ``external`` or ``internal``.
        edge_diameter_mm: The picked edge's diameter.

    Raises:
        InputRefused: The diameter is more than one pitch off.
    """
    want = expected_diameter(size, kind)
    if abs(edge_diameter_mm - want) > size.pitch_mm:
        what = "rod" if kind == "external" else "hole (about the tap drill)"
        raise InputRefused(
            f"The edge is {edge_diameter_mm:g} mm across but {size.size} "
            f"{kind} wants a {what} of about {want:g} mm. Pick the right "
            "edge or size (list_thread_sizes)."
        )


_PLAIN_METRIC = re.compile(r"^M(\d+(?:\.\d+)?)$", re.IGNORECASE)


def coarse_from_hole_rows(rows: Sequence[dict[str, Any]]) -> dict[float, float]:
    """Coarse pitches by diameter from the Hole Wizard's ISO tapped-hole rows.

    The library names the coarse series plainly (``M6``) and the fine ones
    with their pitch (``M8x1.0``); the plain rows give each diameter's
    coarse pitch.

    Args:
        rows: :meth:`HoleLibrary.size_rows` rows (``size``, ``dimensions``).

    Returns:
        dict[float, float]: Nominal diameter -> coarse pitch, mm.
    """
    coarse: dict[float, float] = {}
    for row in rows:
        match = _PLAIN_METRIC.match(str(row.get("size") or ""))
        pitch = (row.get("dimensions") or {}).get("pitch")
        if match and isinstance(pitch, (int, float)):
            coarse[float(match.group(1))] = float(pitch)
    return coarse


def check_inputs(params: ThreadParameters) -> None:
    """Refuse a kind, standard, hand, point or length that can't work."""
    if params.standard not in STANDARDS:
        raise InputRefused(f"standard must be one of {', '.join(STANDARDS)}.")
    if params.kind not in ("external", "internal"):
        raise InputRefused("kind must be 'external' or 'internal'.")
    if params.hand not in ("right", "left"):
        raise InputRefused("hand must be 'right' or 'left'.")
    if len(params.edge_point) != 3:
        raise InputRefused("edge_point must be [x, y, z] in mm.")
    if params.length <= 0:
        raise InputRefused("length must be greater than 0 mm.")
