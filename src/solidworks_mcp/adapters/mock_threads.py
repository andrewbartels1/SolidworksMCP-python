"""The mock adapter's modelled threads (queue item 43).

The mock has no thread profiles; it serves a few sizes of each standard, as
SolidWorks 2026's Die profiles name them, and the coarse pitches its Hole
Wizard library gives. A thread needs an open part with a body; the edge's
diameter is taken to be the one the size wants (the mock has no edges), and
the volume removed is the thread's groove: the basic depth over half the
circumference, times the length. Refusals use :mod:`thread_rules`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from ..exceptions import InputRefused
from . import thread_rules as rules
from .base import AdapterResult, AdapterResultStatus, ThreadParameters
from .body_rules import BodyState

#: Sizes the mock's profiles hold.
MOCK_SIZES: dict[str, list[str]] = {
    "metric": [
        "M3x0.5",
        "M4x0.7",
        "M5x0.8",
        "M6x1.0",
        "M8x1.25",
        "M8x1.0",
        "M10x1.5",
        "M10x1.25",
    ],
    "inch": ["#4-40", "#10-24", "#10-32", "0.2500-20", "0.2500-28"],
}
#: Coarse pitches by diameter, as the Hole Wizard's plain rows give them.
MOCK_COARSE = {3.0: 0.5, 4.0: 0.7, 5.0: 0.8, 6.0: 1.0, 8.0: 1.25, 10.0: 1.5}


def _error(message: str) -> AdapterResult[Any]:
    """An error result."""
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


class MockThreadsMixin:
    """``list_thread_sizes`` and ``create_thread``, in memory."""

    _current_model: Any
    #: From :class:`MockBodiesMixin`: the active part's box bodies.
    _bodies: Callable[[], list[BodyState]]

    async def list_thread_sizes(self, standard: str) -> AdapterResult[dict[str, Any]]:
        """Mock: the sizes the mock's profiles hold.

        Args:
            standard: ``metric`` or ``inch``.

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if standard not in rules.STANDARDS:
            return _error(f"standard must be one of {', '.join(rules.STANDARDS)}.")
        coarse = MOCK_COARSE if standard == "metric" else {}
        sizes = rules.size_table(MOCK_SIZES[standard], coarse)
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "standard": standard,
                "profile": rules.PROFILES[(standard, "external")],
                "sizes": sizes,
                "count": len(sizes),
                "runout_basis": rules.RUNOUT_BASIS[standard],
            },
        )

    async def create_thread(
        self, params: ThreadParameters
    ) -> AdapterResult[dict[str, Any]]:
        """Mock: a modelled thread, its groove's volume removed.

        Args:
            params: The kind, standard, size, edge, length and hand.

        Returns:
            AdapterResult[dict[str, Any]]: As the real adapter's.
        """
        if not self._current_model:
            return _error("No active model")
        try:
            rules.check_inputs(params)
            size = rules.match_size(MOCK_SIZES[params.standard], params.size)
            if not self._bodies():
                raise InputRefused(
                    f"No edge at {list(params.edge_point)} mm; the part has no body."
                )
        except InputRefused as refused:
            return _error(str(refused))
        diameter = rules.expected_diameter(size, params.kind)
        entry = rules.size_entry(size, "")
        depth = entry["basic_depth_mm"]
        removed = math.pi * diameter * depth / 2 * params.length
        before = sum(body.volume for body in self._bodies())
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={
                "name": "Thread1",
                "kind": params.kind,
                "standard": params.standard,
                "profile": rules.PROFILES[(params.standard, params.kind)],
                "size": size.size,
                "pitch_mm": size.pitch_mm,
                "basic_depth_mm": depth,
                "runout_mm": entry["runout_mm"],
                "runout_basis": rules.RUNOUT_BASIS[params.standard],
                "length_mm": params.length,
                "hand": params.hand,
                "edge_diameter_mm": diameter,
                "turns": round(params.length / size.pitch_mm, 2),
                "volume_before": before,
                "volume_after": before - removed,
                "volume_change": -removed,
            },
        )
