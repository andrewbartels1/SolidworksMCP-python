"""Multi-body tools (queue item 35), checked on real SolidWorks.

1. Boolean logic: a 40 mm cube (blue) and a 20 mm sphere (orange) centred
   on its top edge, so a quarter of the sphere, 8,377.6 mm³, is shared.
   Union (89,132.7 mm³), cube minus sphere (55,622.4), sphere minus cube
   (25,132.7) and intersection (8,377.6), each shown, then deleted. Then the
   exclusive or, from copies, two subtracts and a move back: two pieces,
   80,755.2 mm³.
   On purpose: an unknown body, and an intersection of bodies that don't
   touch.
2. A split and a keep: the block split at the Right Plane into two halves of
   8,000 mm³; one half kept. On purpose: a split at a plane that doesn't
   exist is refused.
3. Copies and a scale: a 20 x 20 x 10 block (4,000 mm³) copied three times
   30 mm apart (16,000 mm³ in four bodies), one copy scaled by 2 (x 8:
   44,000 mm³). On purpose: a move with both a translation and a rotation
   is refused (SolidWorks would apply only the rotation).

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_multi_body.py::test_boolean_logic_on_a_cube_and_a_sphere

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.live.evidence import evidence, starting
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


# A 40 mm cube on the Top Plane (x and z -20..20, y 0..40) and a sphere of
# radius 20 centred on the middle of its top right edge, (20, 40, 0). The
# edge cuts the sphere into quarters, so exactly one quarter is inside.
CUBE_MM3 = 40.0**3
SPHERE_MM3 = 4 / 3 * math.pi * 20**3
SHARED_MM3 = SPHERE_MM3 / 4
COPY_OFFSET_MM = 100.0
_ISO_VIEW = 7  # swStandardViews_e.swIsometricView
_BLUE = [0.15, 0.45, 0.85]
_ORANGE = [0.95, 0.55, 0.1]


def _show(adapter: Any, bodies: list[dict[str, Any]]) -> None:
    """Colour each body by where it came from, then turn the camera isometric.

    Staging for the viewer, not a tool call: a body holding cube material is
    blue, one that is all sphere is orange. A body's box tells them apart:
    the cube's starts at x = -20 (or -20 plus the copy offset).
    """
    from solidworks_mcp.adapters import sw_type_info

    model = adapter.currentModel
    cube_like = {
        b["name"]
        for b in bodies
        if abs((b["bounding_box_mm"]["min"][0] + 20) % COPY_OFFSET_MM) < 0.5
    }

    def paint() -> None:
        part = sw_type_info.flagged(model, "IPartDoc")
        for found in part.GetBodies2(0, False) or ():
            body = sw_type_info.flagged(found, "IBody2")
            rgb = _BLUE if body.Name in cube_like else _ORANGE
            body.MaterialPropertyValues2 = [*rgb, 1.0, 1.0, 0.3, 0.3, 0.0, 0.0]

    adapter._attempt(paint, default=None)
    adapter._attempt(lambda: model.ShowNamedView2("", _ISO_VIEW), default=None)
    adapter._zoom_to_fit(model)


async def _bodies(tools: dict[str, Any]) -> list[dict[str, Any]]:
    """The part's bodies, as list_bodies gives them."""
    return list((await _ok(await tools["list_bodies"]()))["bodies"])


def _brief(bodies: list[dict[str, Any]]) -> dict[str, Any]:
    """Body names and volumes, for a caption."""
    return {
        "bodies": {b["name"]: round(b["volume_mm3"], 1) for b in bodies},
        "total_mm3": round(sum(b["volume_mm3"] for b in bodies), 1),
    }


async def _cube_and_sphere(tools: dict[str, Any], adapter: Any) -> tuple[str, str]:
    """Build the cube and, unmerged, the sphere; return their body names."""
    await _ok(await tools["create_part"]({"name": "boolean-logic"}))
    await _extrude(tools, BLOCK, 40, merge=True)
    await _ok(await tools["create_sketch"]({"plane": "Front"}))
    centreline = {"x1": 20, "y1": 15, "x2": 20, "y2": 65}
    await _ok(await tools["add_centerline"](centreline))
    arc = {
        "kind": "three_point",
        "start_x": 20,
        "start_y": 20,
        "end_x": 20,
        "end_y": 60,
        "through_x": 40,
        "through_y": 40,
    }
    await _ok(await tools["add_arc"](arc))
    await _ok(await tools["add_line"]({"x1": 20, "y1": 60, "x2": 20, "y2": 20}))
    await _ok(await tools["exit_sketch"]())
    await _ok(await tools["create_revolve"]({"angle": 360, "merge_result": False}))
    bodies = await _bodies(tools)
    _show(adapter, bodies)
    evidence(
        "a 40 mm cube (blue) and a 20 mm sphere (orange), not merged; "
        f"a quarter of the sphere, {SHARED_MM3:,.1f} mm³, is inside the cube",
        _brief(bodies),
        call="list_bodies()",
    )
    assert sorted(b["volume_mm3"] for b in bodies) == pytest.approx(
        [SPHERE_MM3, CUBE_MM3], rel=1e-4
    )
    cube = next(b["name"] for b in bodies if b["volume_mm3"] > SPHERE_MM3 * 1.5)
    sphere = next(b["name"] for b in bodies if b["name"] != cube)
    return cube, sphere


async def _combine_and_undo(
    tools: dict[str, Any],
    adapter: Any,
    label: str,
    call: dict[str, Any],
    expected: float,
) -> None:
    """One boolean, held on screen and checked, then deleted to restore both."""
    starting(label, f"combine_bodies({call})")
    made = await _ok(await tools["combine_bodies"](call))
    bodies = await _bodies(tools)
    _show(adapter, bodies)
    evidence(
        f"{label} (expect {expected:,.1f} mm³)",
        {**_brief(bodies), "feature": made["combine"]["name"]},
        call=f"combine_bodies({call})",
    )
    assert made["combine"]["volume_after_mm3"] == pytest.approx(expected, rel=1e-4)
    gone = {"name": made["combine"]["name"]}
    await _ok(await tools["delete_feature"](gone))
    restored = await _bodies(tools)
    _show(adapter, restored)
    evidence(
        f"{gone['name']} deleted: the cube and the sphere are back",
        _brief(restored),
        call=f"delete_feature({gone})",
    )
    assert len(restored) == 2


async def test_boolean_logic_on_a_cube_and_a_sphere(scratch: Any) -> None:
    """Every boolean of a cube and a sphere, each shown, measured and undone.

    Union, cube minus sphere, sphere minus cube and intersection are one
    ``combine_bodies`` each. The exclusive or (keep what only one of them
    holds, drop the shared quarter) has no SolidWorks feature, so it is
    built from tools: copy both bodies aside, take the cube minus the sphere
    on one pair and the sphere minus the cube on the other, then move the
    sphere's piece back: the two pieces left are the answer.
    """
    adapter = scratch.adapter
    tools = await _tools(adapter)
    cube, sphere = await _cube_and_sphere(tools, adapter)

    # On purpose: a body that doesn't exist.
    refused = await tools["combine_bodies"](
        {"operation": "subtract", "main_body": cube, "tool_bodies": ["Sphere9"]}
    )
    evidence("an unknown body is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    booleans = (
        ("union: one body", "add", cube, sphere, CUBE_MM3 + SPHERE_MM3 - SHARED_MM3),
        ("cube minus sphere: a bite out of the cube", "subtract", cube, sphere,
         CUBE_MM3 - SHARED_MM3),
        ("sphere minus cube: three quarters of the sphere", "subtract", sphere,
         cube, SPHERE_MM3 - SHARED_MM3),
        ("intersection: only the shared quarter", "common", cube, sphere,
         SHARED_MM3),
    )  # fmt: skip
    for label, operation, main, tool, expected in booleans:
        call = {"operation": operation, "main_body": main, "tool_bodies": [tool]}
        await _combine_and_undo(tools, adapter, label, call, expected)

    # Exclusive or, step 1: copy both bodies 100 mm along x.
    copy = {"bodies": [cube, sphere], "translate": [COPY_OFFSET_MM, 0, 0]}
    copy["as_copy"] = True
    copied = await _ok(await tools["move_copy_body"](copy))
    bodies = await _bodies(tools)
    _show(adapter, bodies)
    evidence(
        "exclusive or, step 1: both bodies copied 100 mm along x",
        _brief(bodies),
        call=f"move_copy_body({copy})",
    )
    assert copied["move"]["body_count_after"] == 4
    far = [b for b in bodies if b["bounding_box_mm"]["min"][0] > 50]
    cube_copy = next(b["name"] for b in far if b["volume_mm3"] > SPHERE_MM3 * 1.5)
    sphere_copy = next(b["name"] for b in far if b["name"] != cube_copy)

    # On purpose: an intersection of bodies 100 mm apart shares nothing.
    apart = {"operation": "common", "main_body": cube, "tool_bodies": [sphere_copy]}
    refused = await tools["combine_bodies"](apart)
    evidence("an intersection of bodies that don't touch is refused", refused)
    assert refused["status"] == "error", refused
    assert refused["error_type"] == "feature_not_built", refused

    # Each pair is cut within itself: the copies are 100 mm from the originals.
    steps = (
        ("step 2: on the left, the cube minus the sphere", cube, sphere),
        ("step 3: on the right, the sphere minus the cube", sphere_copy, cube_copy),
    )
    for label, main, tool in steps:
        call = {"operation": "subtract", "main_body": main, "tool_bodies": [tool]}
        await _ok(await tools["combine_bodies"](call))
        bodies = await _bodies(tools)
        _show(adapter, bodies)
        evidence(
            f"exclusive or, {label}", _brief(bodies), call=f"combine_bodies({call})"
        )

    # Step 4: slide the sphere's three quarters back onto the bitten cube.
    caps = next(b["name"] for b in bodies if b["bounding_box_mm"]["min"][0] > 50)
    back = {"bodies": [caps], "translate": [-COPY_OFFSET_MM, 0, 0]}
    await _ok(await tools["move_copy_body"](back))
    bodies = await _bodies(tools)
    _show(adapter, bodies)
    evidence(
        "exclusive or, step 4: the sphere's three quarters moved back onto the cube",
        _brief(bodies),
        call=f"move_copy_body({back})",
    )

    expected = CUBE_MM3 + SPHERE_MM3 - 2 * SHARED_MM3
    evidence(
        "exclusive or: the bitten cube and three quarters of the sphere, "
        f"two bodies, the shared quarter gone (expect {expected:,.1f} mm³)",
        _brief(bodies),
    )
    assert len(bodies) == 2
    total = sum(b["volume_mm3"] for b in bodies)
    assert total == pytest.approx(expected, rel=1e-4)

    # Pull the sphere's piece up 30 mm so both pieces show.
    piece = next(b["name"] for b in bodies if b["volume_mm3"] < SPHERE_MM3)
    lift = {"bodies": [piece], "translate": [0, 30, 0]}
    await _ok(await tools["move_copy_body"](lift))
    bodies = await _bodies(tools)
    _show(adapter, bodies)
    evidence(
        "the two pieces pulled 30 mm apart to show them",
        _brief(bodies),
        call=f"move_copy_body({lift})",
    )

    checked = await tools["verify_model"](
        {"volume_mm3": expected, "solid_body_count": 2}
    )
    evidence("verify_model on the two pieces", {"verdict": checked.get("verdict")})
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
