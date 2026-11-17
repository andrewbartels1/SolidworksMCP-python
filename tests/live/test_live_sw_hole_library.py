"""The Hole Wizard library (queue item 22), checked on real SolidWorks.

1. ``list_hole_sizes`` reads the installed library: ISO simple hole types,
   and an M6 cap screw's counterbore dimensions;
2. ``create_hole`` with ``M6`` (a screw clearance hole), ``6`` (a drilled
   Ø6.0 hole) and ``M6x1.0`` (the coarse tapped M6); an unknown size (M15) is
   refused, with the nearest sizes, and nothing is made.

The block is 40 x 40 x 20 mm on the Top Plane, its top face at y = 20.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_hole_library.py::test_sizes_come_from_the_library

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_part_features import _block, _tools, _volume

pytestmark = pytest.mark.asyncio


async def test_list_hole_sizes_reads_the_installed_library(scratch: Any) -> None:
    """ISO simple hole types, and the M6 cap screw's counterbore."""
    tools = await _tools(scratch.adapter)

    simple = await tools["list_hole_sizes"]({"hole_type": "simple"})
    cap = await tools["list_hole_sizes"](
        {"hole_type": "counterbore", "fastener": "Cap (4762)", "size": "M6"}
    )

    names = {t["name"]: len(t["sizes"]) for t in simple["library"]["hole_types"]}
    evidence(
        "list_hole_sizes: ISO simple hole types (sizes each), M6 cap counterbore",
        {"simple": names, "cap_m6": cap["library"]["dimensions"]},
    )
    assert {"Drill sizes", "Screw Clearances"} <= set(names)
    assert cap["library"]["dimensions"]["cbore_dia"] == 11.0
    assert cap["library"]["dimensions"]["cbore_depth"] == 6.4


async def test_sizes_come_from_the_library(scratch: Any) -> None:
    """M6 clearance, a 6 mm drill and M6x1.0 tapped build; M15 is refused.

    M15 is not in the ISO clearance table (M7 is: the first run assumed not).
    """
    tools = await _tools(scratch.adapter)
    await _block(tools, "hole_sizes")

    def hole(x: float, z: float, hole_type: str, size: str) -> dict[str, Any]:
        return {
            "face_point": [x, 20, z],
            "hole_type": hole_type,
            "size": size,
            "end_condition": "blind",
            "depth": 10,
        }

    clearance = await tools["create_hole"](hole(-10, -10, "simple", "M6"))
    drilled = await tools["create_hole"](hole(10, -10, "simple", "6"))
    tapped = await tools["create_hole"](hole(0, 10, "tapped", "M6x1.0"))
    before = await _volume(tools)
    unknown = await tools["create_hole"](hole(-10, 10, "simple", "M15"))
    after = await _volume(tools)

    def brief(made: dict[str, Any]) -> Any:
        if made["status"] != "success":
            return made["message"]
        h = made["hole"]
        return [h["fastener"], h["size"], round(h["volume_change"], 1)]

    evidence(
        "create_hole sized from the library",
        {
            "M6 simple": brief(clearance),
            "6 simple": brief(drilled),
            "M6x1.0 tapped": brief(tapped),
            "M15 simple": [unknown["status"], unknown["message"]],
            "volume_unchanged_after_M15": round(after - before, 1) == 0,
        },
    )
    assert clearance["hole"]["fastener"] == "Screw Clearances"
    # The normal-fit clearance for M6 is 6.6 mm, the drill exactly 6: the
    # same depth (and drill point) removes (6.6 / 6)² = 1.21 times as much.
    assert drilled["hole"]["size"] == "Ø6.0"
    ratio = clearance["hole"]["volume_change"] / drilled["hole"]["volume_change"]
    assert ratio == pytest.approx(1.21, rel=0.03)
    assert tapped["status"] == "success", tapped
    assert unknown["status"] == "error"
    assert "nearest:" in unknown["message"]
    assert after == pytest.approx(before)
