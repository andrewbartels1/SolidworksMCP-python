"""Modelled threads (queue item 43), checked on real SolidWorks.

1. A bolt-like rod: the metric sizes listed (M3 to M6 coarse); a 6 mm rod
   25 mm long; on purpose, M10x1.5 on it is refused (the rod is 6 mm); then
   M6x1.0 cut 12 mm from its end: material removed, 12 turns, runout 2.5 mm.
   And a 1/4-20 inch thread on a 6.35 mm rod.
2. A tapped hole: a 20 x 20 x 15 mm block, an M6 tapped hole from
   ``create_hole`` (its 5 mm tap drill), and an internal M6x1.0 thread 10 mm
   into it.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_threads.py::test_a_bolt_like_rod

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_material_properties import _tools as _base_tools

pytestmark = pytest.mark.asyncio

_ISO_VIEW = 7  # swStandardViews_e.swIsometricView


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modelling tools plus the thread tools."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.threads import register_thread_tools

    tools = await _base_tools(adapter)
    mcp = FastMCP("threads-live")
    await register_thread_tools(mcp, adapter, {})
    tools.update({t.name: t.fn for t in await mcp.list_tools()})
    return tools


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


def _iso(adapter: Any) -> None:
    """Turn the camera isometric, zoomed to fit (staging, not a tool call)."""
    model = adapter.currentModel
    adapter._attempt(lambda: model.ClearSelection2(True), default=None)
    adapter._attempt(lambda: model.ShowNamedView2("", _ISO_VIEW), default=None)
    adapter._zoom_to_fit(model)


async def _rod(tools: dict[str, Any], name: str, radius: float, length: float) -> None:
    """A rod on the Top Plane, its end edge at y = length."""
    await _ok(await tools["create_part"]({"name": name}))
    await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(
        await tools["add_circle"]({"center_x": 0, "center_y": 0, "radius": radius})
    )
    await _ok(await tools["exit_sketch"]())
    await _ok(await tools["create_extrusion"]({"depth": length}))


async def test_a_bolt_like_rod(scratch: Any) -> None:
    """Metric sizes, a refused size, an M6 thread and a 1/4-20 thread."""
    adapter = scratch.adapter
    tools = await _tools(adapter)

    listed = await _ok(await tools["list_thread_sizes"]({"standard": "metric"}))
    common = [
        s for s in listed["sizes"] if s["diameter_mm"] in (3.0, 4.0, 5.0, 6.0, 8.0)
    ]
    evidence(
        "metric sizes M3 to M8 from SolidWorks's profile",
        {"count": listed["count"], "sizes": common, "runout": listed["runout_basis"]},
        call='list_thread_sizes({"standard": "metric"})',
    )
    by_size = {s["size"]: s for s in listed["sizes"]}
    assert by_size["M6x1.0"]["pitch_class"] == "coarse"
    assert by_size["M8x1.0"]["pitch_class"] == "fine"

    await _rod(tools, "m6-rod", 3, 25)
    _iso(adapter)

    # On purpose: a size the rod can't take.
    refused = await tools["create_thread"](
        {"size": "M10x1.5", "edge_point": [3, 25, 0], "length": 12}
    )
    evidence("M10 on a 6 mm rod is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    call = {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 12}
    made = await _ok(await tools["create_thread"](call))
    _iso(adapter)
    evidence(
        "M6x1.0 cut 12 mm from the rod's end",
        made["thread"],
        call=f"create_thread({call})",
    )
    thread = made["thread"]
    assert thread["volume_change"] < 0
    assert thread["turns"] == pytest.approx(12)
    assert thread["runout_mm"]["normal"] == pytest.approx(2.5)

    await _rod(tools, "quarter-twenty", 3.175, 25)
    call = {
        "standard": "inch",
        "size": "1/4-20",
        "edge_point": [3.175, 25, 0],
        "length": 12.7,
    }
    inch = await _ok(await tools["create_thread"](call))
    _iso(adapter)
    evidence(
        "1/4-20 on a 6.35 mm rod (runout by the ISO rule on 1/20 in)",
        inch["thread"],
        call=f"create_thread({call})",
    )
    assert inch["thread"]["size"] == "0.2500-20"
    assert inch["thread"]["volume_change"] < 0


async def test_a_tapped_hole(scratch: Any) -> None:
    """create_hole's M6 tapped hole, then an internal M6x1.0 thread in it."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _ok(await tools["create_part"]({"name": "tapped-block"}))
    await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_rectangle"]({"x1": -10, "y1": -10, "x2": 10, "y2": 10}))
    await _ok(await tools["exit_sketch"]())
    await _ok(await tools["create_extrusion"]({"depth": 15}))
    hole = await _ok(
        await tools["create_hole"](
            {"face_point": [0, 15, 0], "hole_type": "tapped", "size": "M6"}
        )
    )
    _iso(adapter)
    evidence("an M6 tapped hole (its 5 mm tap drill)", hole["hole"])

    call = {
        "kind": "internal",
        "size": "M6x1.0",
        "edge_point": [2.5, 15, 0],
        "length": 10,
    }
    made = await _ok(await tools["create_thread"](call))
    _iso(adapter)
    evidence(
        "an internal M6x1.0 thread 10 mm into the hole",
        made["thread"],
        call=f"create_thread({call})",
    )
    assert made["thread"]["profile"] == "Metric Tap"
    assert made["thread"]["edge_diameter_mm"] == pytest.approx(5.0, abs=0.2)
    assert made["thread"]["volume_change"] < 0
