"""Multi-body tools (queue item 35), checked on real SolidWorks.

1. A mould core: a 40 x 40 x 10 mm block and, unmerged, a 10 mm pin 20 mm
   tall through it. ``list_bodies`` names both; subtracting the pin leaves
   one body of 16,000 - pi x 5² x 10 = 15,214.6 mm³. On purpose: a combine
   naming a body that doesn't exist is refused.
2. A split and a keep: the block split at the Right Plane into two halves of
   8,000 mm³; one half kept. On purpose: a split at a plane that doesn't
   exist is refused.
3. Copies and a scale: a 20 x 20 x 10 block (4,000 mm³) copied three times
   30 mm apart (16,000 mm³ in four bodies), one copy scaled by 2 (x 8:
   44,000 mm³). On purpose: a move with both a translation and a rotation
   is refused (SolidWorks would apply only the rotation).

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_multi_body.py::test_a_mould_core

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_material_properties import _tools as _base_tools

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modelling and analysis tools plus the body tools."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.bodies import register_body_tools

    tools = await _base_tools(adapter)
    mcp = FastMCP("bodies-live")
    await register_body_tools(mcp, adapter, {})
    tools.update({t.name: t.fn for t in await mcp.list_tools()})
    return tools


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _extrude(
    tools: dict[str, Any], shape: dict[str, Any], depth: float, merge: bool
) -> None:
    """A sketch on Top holding one rectangle or circle, extruded."""
    await _ok(await tools["create_sketch"]({"plane": "Top"}))
    if "radius" in shape:
        await _ok(await tools["add_circle"](shape))
    else:
        await _ok(await tools["add_rectangle"](shape))
    await _ok(await tools["exit_sketch"]())
    await _ok(await tools["create_extrusion"]({"depth": depth, "merge_result": merge}))


BLOCK = {"x1": -20, "y1": -20, "x2": 20, "y2": 20}


async def test_a_mould_core(scratch: Any) -> None:
    """A block minus a pin through it: one body, the pin's volume gone."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "mould-core"}))
    await _extrude(tools, BLOCK, 10, merge=True)
    await _extrude(tools, {"center_x": 0, "center_y": 0, "radius": 5}, 20, merge=False)

    listed = await _ok(await tools["list_bodies"]())
    evidence("two bodies", {k: listed[k] for k in ("bodies", "count")})
    volumes = sorted(b["volume_mm3"] for b in listed["bodies"])
    assert volumes == pytest.approx([math.pi * 25 * 20, 16000], rel=1e-4)
    pin = next(b["name"] for b in listed["bodies"] if b["volume_mm3"] < 16000)
    block = next(b["name"] for b in listed["bodies"] if b["name"] != pin)

    # On purpose: a body that doesn't exist.
    refused = await tools["combine_bodies"](
        {"operation": "subtract", "main_body": block, "tool_bodies": ["Pin9"]}
    )
    evidence("an unknown body is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    call = {"operation": "subtract", "main_body": block, "tool_bodies": [pin]}
    core = await _ok(await tools["combine_bodies"](call))
    expected = 16000 - math.pi * 25 * 10
    evidence(
        f"the pin subtracted (expect {expected:,.1f} mm³)",
        core["combine"],
        call=f"combine_bodies({call})",
    )
    assert core["combine"]["body_count_after"] == 1
    assert core["combine"]["volume_after_mm3"] == pytest.approx(expected, rel=1e-4)

    checked = await tools["verify_model"](
        {"volume_mm3": expected, "solid_body_count": 1}
    )
    evidence("verify_model on the core", {"verdict": checked.get("verdict")})
    assert checked.get("verdict") == "pass", checked


async def test_a_split_and_a_keep(scratch: Any) -> None:
    """A block split at the Right Plane, one half kept."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "split-block"}))
    await _extrude(tools, BLOCK, 10, merge=True)

    # On purpose: a plane that doesn't exist.
    refused = await tools["split_body"]({"tool": "Plane9"})
    evidence("a missing plane is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    split = await _ok(await tools["split_body"]({"tool": "Right Plane"}))
    evidence(
        "split at the Right Plane",
        split["split"],
        call="split_body({'tool': 'Right Plane'})",
    )
    assert len(split["split"]["made"]) == 2
    halves = (await _ok(await tools["list_bodies"]()))["bodies"]
    assert [b["volume_mm3"] for b in halves] == pytest.approx([8000, 8000], rel=1e-4)

    keep = {"bodies": [split["split"]["made"][0]], "keep": True}
    kept = await _ok(await tools["delete_bodies"](keep))
    evidence("one half kept", kept["delete"], call=f"delete_bodies({keep})")
    assert kept["delete"]["body_count_after"] == 1
    assert kept["delete"]["volume_after_mm3"] == pytest.approx(8000, rel=1e-4)


async def test_copies_and_a_scale(scratch: Any) -> None:
    """A block copied three times, then one copy scaled by 2."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "copies"}))
    await _extrude(tools, {"x1": -10, "y1": -10, "x2": 10, "y2": 10}, 10, merge=True)
    block = (await _ok(await tools["list_bodies"]()))["bodies"][0]["name"]

    # On purpose: a translation and a rotation together.
    refused = await tools["move_copy_body"](
        {"bodies": [block], "translate": [30, 0, 0], "rotate": [0, 90, 0]}
    )
    evidence("translate and rotate together are refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    call = {"bodies": [block], "translate": [30, 0, 0], "as_copy": True, "copies": 3}
    copied = await _ok(await tools["move_copy_body"](call))
    evidence(
        "three copies 30 mm apart (expect 16,000 mm³)",
        copied["move"],
        call=f"move_copy_body({call})",
    )
    assert copied["move"]["body_count_after"] == 4
    assert copied["move"]["volume_after_mm3"] == pytest.approx(16000, rel=1e-4)

    one = next(n for n in copied["move"]["bodies_after"] if n != block)
    scale = {"scale": 2, "bodies": [one]}
    scaled = await _ok(await tools["scale_body"](scale))
    evidence(
        "one copy scaled by 2 (expect 44,000 mm³)",
        scaled["scale"],
        call=f"scale_body({scale})",
    )
    assert scaled["scale"]["volume_after_mm3"] == pytest.approx(44000, rel=1e-3)

    checked = await tools["verify_model"]({"volume_mm3": 44000, "solid_body_count": 4})
    evidence("verify_model on the four bodies", {"verdict": checked.get("verdict")})
    assert checked.get("verdict") == "pass", checked
