"""The mock adapter's sheet metal: a 100 x 60 mm plate, flanges and its blank.

The base flange is always the plate the live check builds (100 x 60 mm in
x and z, ``thickness`` thick); edge flanges go on its edges at
``|x| = 50`` or ``|z| = 30``. The flat blank uses the bend deduction from
the K-factor, the value SolidWorks measured live (78.712 mm for a 20 mm
flange on a 2 mm sheet with a 2 mm radius and K = 0.5).
"""

from __future__ import annotations

import math
from typing import Any

from .base import AdapterResult, AdapterResultStatus

#: The mock plate's size in x and z, mm.
_PLATE_X, _PLATE_Z = 100.0, 60.0
#: How close an edge point must be to an edge, mm.
_EDGE_TOLERANCE = 1.0
_START_WITH = "Start with create_base_flange, which makes a part sheet metal."


def bend_deduction(thickness: float, radius: float, k_factor: float) -> float:
    """A 90° bend's deduction, mm: twice the outside setback less the allowance.

    Args:
        thickness: Sheet thickness, mm.
        radius: Inside bend radius, mm.
        k_factor: The K-factor.

    Returns:
        float: The bend deduction.
    """
    allowance = math.pi / 2 * (radius + k_factor * thickness)
    return 2 * (radius + thickness) - allowance


def _error(message: str) -> AdapterResult[dict[str, Any]]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _ok(data: dict[str, Any]) -> AdapterResult[dict[str, Any]]:
    """A success result."""
    return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


class MockSheetMetalMixin:
    """Base flange, edge flanges, sketched bends and the flat blank, in memory."""

    _current_model: Any

    def _sheets(self) -> dict[str, dict[str, Any]]:
        """Each part's sheet metal, by path."""
        if "_sheet_state" not in self.__dict__:
            self._sheet_state: dict[str, dict[str, Any]] = {}
        return self._sheet_state

    def _sheet(self, operation: str) -> tuple[dict[str, Any] | None, str | None]:
        """The active part's sheet, or why there is none."""
        model = self._current_model
        if model is None:
            return None, "No active model"
        sheet = self._sheets().get(str(model.path))
        if sheet is None:
            return None, (
                f"{operation} needs a sheet-metal part; this part has no "
                f"sheet-metal body. {_START_WITH}"
            )
        return sheet, None

    def _box(self, sheet: dict[str, Any]) -> dict[str, Any]:
        """The plate's bounding box, folded or flat."""
        t = sheet["thickness"]
        if sheet["flat"]:
            deduction = bend_deduction(t, sheet["radius"], sheet["k_factor"])
            z = _PLATE_Z + sum(f + t - deduction for f in sheet["flanges"])
            height = t
        else:
            z = _PLATE_Z
            height = t + max(sheet["flanges"], default=0.0)
        return {
            "min": [-_PLATE_X / 2, -t, -_PLATE_Z / 2],
            "max": [_PLATE_X / 2, height - t, z - _PLATE_Z / 2],
            "size": [_PLATE_X, height, z],
        }

    async def create_base_flange(
        self,
        thickness: float,
        bend_radius: float,
        k_factor: float = 0.5,
        depth: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Make the active part the mock plate."""
        model = self._current_model
        if model is None or getattr(model, "type", None) != "Part":
            return _error("create_base_flange needs an active part document")
        volume = _PLATE_X * _PLATE_Z * thickness
        self._sheets()[str(model.path)] = {
            "thickness": float(thickness),
            "radius": float(bend_radius),
            "k_factor": float(k_factor),
            "flanges": [],
            "flat": False,
            "volume": volume,
        }
        return _ok(
            {
                "name": "Base-Flange1",
                "sketch": sketch or "Sketch1",
                "thickness_mm": float(thickness),
                "bend_radius_mm": float(bend_radius),
                "k_factor": float(k_factor),
                "read_back": True,
                "volume_before": 0.0,
                "volume_after": volume,
                "volume_change": volume,
                "volume_ratio": None,
            }
        )

    async def add_edge_flange(
        self,
        edge_point: list[float],
        length: float,
        angle: float = 90.0,
        bend_radius: float | None = None,
        flip: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Add a flange on one of the plate's long edges (``|z| = 30``)."""
        sheet, refusal = self._sheet("add_edge_flange")
        if sheet is None:
            return _error(str(refusal))
        x, _y, z = edge_point
        if abs(abs(z) - _PLATE_Z / 2) > _EDGE_TOLERANCE or abs(x) > _PLATE_X / 2:
            return _error(
                f"No sheet edge at {list(edge_point)} mm; give a point on the "
                "edge itself."
            )
        before = sheet["volume"]
        added = _PLATE_X * float(length) * sheet["thickness"]
        sheet["volume"] += added
        sheet["flanges"].append(float(length))
        return _ok(
            {
                "name": f"Edge-Flange{len(sheet['flanges'])}",
                "edge_length_mm": _PLATE_X,
                "length_mm": float(length),
                "angle_deg": float(angle),
                "volume_before": before,
                "volume_after": sheet["volume"],
                "volume_change": added,
                "volume_ratio": round(sheet["volume"] / before, 6),
            }
        )

    async def create_sketched_bend(
        self,
        angle: float = 90.0,
        bend_radius: float | None = None,
        sketch: str | None = None,
        reverse: bool = False,
    ) -> AdapterResult[dict[str, Any]]:
        """Fold half the plate up, as SolidWorks does (it keeps the +x half)."""
        sheet, refusal = self._sheet("create_sketched_bend")
        if sheet is None:
            return _error(str(refusal))
        t = sheet["thickness"]
        rise = _PLATE_X / 2 + t
        return _ok(
            {
                "name": "Sketched Bend1",
                "sketch": sketch or "Sketch2",
                "angle_deg": float(angle),
                "bounding_box_mm": {
                    "min": [0.0, -t, -_PLATE_Z / 2],
                    "max": [_PLATE_X / 2, rise - t, _PLATE_Z / 2],
                    "size": [_PLATE_X / 2, rise, _PLATE_Z],
                },
            }
        )

    async def set_flat_pattern(self, flat: bool) -> AdapterResult[dict[str, Any]]:
        """Flatten or fold the plate, and give its box."""
        sheet, refusal = self._sheet("set_flat_pattern")
        if sheet is None:
            return _error(str(refusal))
        sheet["flat"] = bool(flat)
        return _ok(
            {
                "flat": bool(flat),
                "feature": "Flat-Pattern1",
                "bounding_box_mm": self._box(sheet),
            }
        )
