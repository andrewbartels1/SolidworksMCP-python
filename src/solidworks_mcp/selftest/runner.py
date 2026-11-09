"""Run the selftest's areas in order and turn each into an ``AreaResult``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .areas import Context
from .results import AreaResult, Check, Outcome, ToolFailed


class Area(Protocol):
    """One part of the selftest: what it needs, and how it runs."""

    name: str
    needs: tuple[str, ...]

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        """Call tools and append a check per value read back.

        Args:
            ctx: The selftest context.
            checks: The area's checks, appended to.
        """


async def run_areas(areas: Iterable[Area], ctx: Context) -> list[AreaResult]:
    """Run each area, skipping one whose files an earlier area didn't save.

    A tool error ends its area as FAIL with the tool's message; the checks
    made before it are kept. Any other exception propagates, so a bug in
    the selftest is never reported as a SolidWorks failure.

    Args:
        areas: The areas, in order.
        ctx: The selftest context.

    Returns:
        list[AreaResult]: One result per area, in order.
    """
    results = []
    for area in areas:
        missing = [need for need in area.needs if need not in ctx.files]
        if missing:
            results.append(
                AreaResult(
                    area.name,
                    Outcome.SKIP,
                    note=f"needs the saved {' and '.join(missing)}",
                )
            )
            continue
        first_call = len(ctx.call.calls)
        checks: list[Check] = []
        note = None
        try:
            await area.run(ctx, checks)
        except ToolFailed as exc:
            note = str(exc)
        passed = note is None and bool(checks) and all(c.passed for c in checks)
        results.append(
            AreaResult(
                area.name,
                Outcome.PASS if passed else Outcome.FAIL,
                checks,
                ctx.call.calls[first_call:],
                note,
            )
        )
    return results
