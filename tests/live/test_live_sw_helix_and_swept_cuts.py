"""Helices and swept cuts (queue item 34), checked on real SolidWorks.

1. A compression spring: a 20 mm circle on Top, ``create_helix`` 48 mm
   tall at a 6 mm pitch (8 turns, about 504.9 mm long), then
   ``create_sweep`` of a 2 mm wire with ``circular_profile_diameter``. The
   wire's volume is the circle's area times the helix's reported length,
   pi x 1^2 x 504.92 = 1,586.2 mm³. On purpose: a helix on a sketch holding
   a rectangle is refused.
2. A threaded rod: a 10 mm rod 40 mm long, a helix on it (30 mm at a 2 mm
   pitch, 15 turns, starting on the Front plane), a triangular thread
   profile at the helix's start, then ``create_cut_sweep``. The volume
   removed is checked by Pappus: the triangle's area times the distance
   its centroid travels, 0.4 mm² x 2 pi x 4.733 mm x 15 = 178.4 mm³ (within
   5%: the first half-turn starts at the rod's end). On purpose: a profile
   that is the path itself is refused.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_helix_and_swept_cuts.py::test_a_compression_spring

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_material_properties import _tools

pytestmark = pytest.mark.asyncio

#: The thread profile on the Front plane at the helix's start (5, 0): its
#: base on the rod's surface, its tip 0.8 mm in.
THREAD = [(5.0, -0.5), (5.0, 0.5), (4.2, 0.0)]
THREAD_AREA = 0.5 * 1.0 * 0.8
THREAD_CENTROID = sum(x for x, _ in THREAD) / 3


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _circle_sketch(tools: dict[str, Any], radius: float) -> str:
    """A closed sketch on Top holding one circle at the origin."""
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(
        await tools["add_circle"]({"center_x": 0, "center_y": 0, "radius": radius})
    )
    closed = await _ok(await tools["exit_sketch"]())
    return str(closed.get("sketch", {}).get("name") or made["sketch"]["name"])


async def test_a_compression_spring(scratch: Any) -> None:
    """A helix and a 2 mm wire swept along it; the wire's volume by its length."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "spring"}))
    base = await _circle_sketch(tools, 10)

    helix_call = {"sketch": base, "height": 48, "pitch": 6}
    helix = await _ok(await tools["create_helix"](helix_call))
    evidence(
        "a helix 48 mm tall at a 6 mm pitch",
        helix["helix"],
        call=f"create_helix({helix_call})",
    )
    data = helix["helix"]
    assert data["revolutions"] == pytest.approx(8)
    assert data["diameter_mm"] == pytest.approx(20)
    assert data["length_measured"] is True
    assert data["length_mm"] == pytest.approx(504.92, rel=1e-3)

    sweep_call = {"path": data["name"], "circular_profile_diameter": 2}
    wire = await _ok(await tools["create_sweep"](sweep_call))
    expected = math.pi * 1.0**2 * data["length_mm"]
    evidence(
        f"a 2 mm wire along it (expect {expected:,.1f} mm³)",
        wire["sweep"],
        call=f"create_sweep({sweep_call})",
    )
    assert wire["sweep"]["volume_change"] == pytest.approx(expected, rel=5e-3)

    checked = await tools["verify_model"](
        {"volume_mm3": expected, "solid_body_count": 1}
    )
    evidence("verify_model on the spring", {"verdict": checked.get("verdict")})
    assert checked.get("verdict") == "pass", checked

    # On purpose: a base sketch that isn't one circle.
    square = (await _ok(await tools["create_sketch"]({"plane": "Front"})))["sketch"][
        "name"
    ]
    await _ok(await tools["add_rectangle"]({"x1": 30, "y1": 0, "x2": 40, "y2": 10}))
    await _ok(await tools["exit_sketch"]())
    refused = await tools["create_helix"]({"sketch": square, "height": 10, "pitch": 2})
    evidence("a helix on a rectangle is refused", refused)
    assert refused["status"] == "error"
    assert "exactly one circle" in refused["message"]


async def test_a_threaded_rod(scratch: Any) -> None:
    """A thread cut along a helix on a rod; the volume removed by Pappus."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "threaded-rod"}))
    rod = await _circle_sketch(tools, 5)
    await _ok(await tools["create_extrusion"]({"sketch_name": rod, "depth": 40}))
    base = await _circle_sketch(tools, 5)

    helix_call = {"sketch": base, "height": 30, "pitch": 2, "start_angle": 90}
    helix = (await _ok(await tools["create_helix"](helix_call)))["helix"]
    evidence("a helix on the rod, 15 turns", helix, call=f"create_helix({helix_call})")
    start = helix["start_point_mm"]
    assert start is not None and start[2] == pytest.approx(0, abs=1e-3), start
    assert math.hypot(start[0], start[2]) == pytest.approx(5, abs=1e-3), start

    # The triangle on the Front plane, its base on the rod at the start.
    profile = await _ok(await tools["create_sketch"]({"plane": "Front"}))
    x0 = start[0]
    points = [(x - 5.0 + x0, y + start[1]) for x, y in THREAD]
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        await _ok(await tools["add_line"]({"x1": x1, "y1": y1, "x2": x2, "y2": y2}))
    await _ok(await tools["exit_sketch"]())
    profile_name = profile["sketch"]["name"]

    # On purpose: the profile is the path itself.
    same = await tools["create_cut_sweep"](
        {"path": helix["name"], "profile": helix["name"]}
    )
    evidence("a profile that is the path is refused", same)
    assert same["status"] == "error"

    cut_call = {"path": helix["name"], "profile": profile_name}
    cut = await _ok(await tools["create_cut_sweep"](cut_call))
    expected = THREAD_AREA * 2 * math.pi * THREAD_CENTROID * helix["revolutions"]
    evidence(
        f"the thread cut (expect about -{expected:,.1f} mm³)",
        cut["cut_sweep"],
        call=f"create_cut_sweep({cut_call})",
    )
    assert cut["cut_sweep"]["volume_change"] == pytest.approx(-expected, rel=0.05)
