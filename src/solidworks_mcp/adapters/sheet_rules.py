"""Rules for drawing sheets (queue item 37), shared by the adapter and the mock.

- :func:`sheet_entry` turns a sheet's ``GetProperties2`` into a listing entry;
- :func:`resolve_sheet` finds a sheet by name, ignoring case, or refuses by
  listing them;
- :func:`check_new_sheet` refuses a new sheet's name or projection.

``ISheet.GetProperties2`` gives, measured on SolidWorks 2026: paper size,
template, scale numerator and denominator, first angle (1) or third angle
(0), width and height in metres, and a last flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..exceptions import InputRefused

PROJECTIONS = ("first", "third")


def sheet_entry(name: str, props: Any, active: bool) -> dict[str, Any]:
    """One sheet as ``list_sheets`` lists it.

    Args:
        name: The sheet's name.
        props: ``GetProperties2``'s values, or None when unreadable.
        active: Whether it is the active sheet.

    Returns:
        dict[str, Any]: ``name``, ``active``, and when readable
        ``paper_mm`` [width, height], ``scale`` ("1:2") and ``projection``.
    """
    entry: dict[str, Any] = {"name": name, "active": active}
    values = list(props) if isinstance(props, (list, tuple)) else []
    if len(values) >= 7:
        entry["paper_mm"] = [
            round(float(values[5]) * 1000, 1),
            round(float(values[6]) * 1000, 1),
        ]
        entry["scale"] = f"{float(values[2]):g}:{float(values[3]):g}"
        entry["projection"] = "first" if values[4] else "third"
    return entry


def resolve_sheet(names: Sequence[str], wanted: str) -> str:
    """A sheet's name as the drawing spells it.

    Raises:
        InputRefused: No sheet of that name; the message lists them.
    """
    for name in names:
        if name.lower() == wanted.strip().lower():
            return name
    raise InputRefused(
        f"No sheet named '{wanted}'; the drawing has {', '.join(names) or 'none'}."
    )


def check_new_sheet(names: Sequence[str], name: str, projection: str | None) -> None:
    """Refuse a new sheet's name that is empty or taken, or a bad projection.

    Raises:
        InputRefused: Saying which.
    """
    if not name.strip():
        raise InputRefused("A new sheet needs a name.")
    if any(existing.lower() == name.strip().lower() for existing in names):
        raise InputRefused(
            f"The drawing has a sheet named '{name}' already; its sheets are "
            f"{', '.join(names)}."
        )
    if projection is not None and projection not in PROJECTIONS:
        raise InputRefused("projection must be 'first' or 'third'.")
