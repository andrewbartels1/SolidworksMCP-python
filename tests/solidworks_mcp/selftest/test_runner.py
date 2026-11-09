"""run_areas: pass, fail, skip, and a bug that is not a SolidWorks failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.selftest.areas import Context
from solidworks_mcp.selftest.results import Check, Outcome, ToolFailed
from solidworks_mcp.selftest.runner import run_areas

from .caller_stub import CallerStub


class _Area:
    def __init__(self, name, needs=(), checks=(), saves=(), error=None) -> None:
        self.name, self.needs = name, tuple(needs)
        self._checks, self._saves, self._error = list(checks), saves, error

    async def run(self, ctx: Context, checks: list[Check]) -> None:
        await ctx.call(f"{self.name}_tool")
        checks.extend(self._checks)
        for key in self._saves:
            ctx.files[key] = f"{key}.SLDPRT"
        if self._error:
            raise self._error


@pytest.mark.asyncio
async def test_outcomes_and_skips(tmp_path: Path) -> None:
    ok = Check("v", 1, 1, passed=True)
    ctx = Context(CallerStub(), tmp_path)
    areas = [
        _Area("part", checks=[ok, Check("w", 1, 2, passed=False)], saves=["block"]),
        _Area("assembly", needs=["block", "pin"]),
        _Area("drawing", needs=["block"], checks=[ok]),
        _Area(
            "export",
            needs=["block"],
            checks=[ok],
            error=ToolFailed("export_step", "no"),
        ),
        _Area("empty"),
    ]

    results = await run_areas(areas, ctx)

    assert [(r.name, r.outcome) for r in results] == [
        ("part", Outcome.FAIL),
        ("assembly", Outcome.SKIP),
        ("drawing", Outcome.PASS),
        ("export", Outcome.FAIL),
        ("empty", Outcome.FAIL),
    ]
    assert results[1].note == "needs the saved pin"
    assert results[2].calls == ["drawing_tool"]
    assert results[3].note == "export_step failed: no"
    assert results[3].checks == [ok]


@pytest.mark.asyncio
async def test_a_bug_in_an_area_propagates(tmp_path: Path) -> None:
    with pytest.raises(ZeroDivisionError):
        await run_areas(
            [_Area("part", error=ZeroDivisionError())], Context(CallerStub(), tmp_path)
        )
