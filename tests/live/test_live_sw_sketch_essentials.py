"""Sketch essentials (queue item 32), checked on real SolidWorks.

One slotted bracket plate, built with every new sketch operation; after each
step ``verify_model`` checks the volume against the hand calculation:

1. A 120 x 80 mm plate drawn from its centre (``add_rectangle``
   ``from_center``); a corner that isn't there is refused first; the two
   left corners rounded R10 (``add_sketch_fillet``) and the two right
   corners chamfered 10 mm (``add_sketch_chamfer``); extruded 8 mm.
2. A straight slot and an arc slot (``add_slot``) cut through, in a sketch
   with two lines across the plate made construction geometry, one by
   ``add_line``'s ``construction`` (the fix) and one by
   ``set_construction_geometry``: if either were normal geometry the cut
   would differ.
3. A keyhole: a circle and three lines that stop short of it, the two
   sides lengthened to the circle (``sketch_extend``) and the circle's arc
   between them removed (``sketch_trim``), cut through.
4. A stadium window from a line, a tangent arc, a line and a three-point arc
   (``add_arc`` ``kind``), cut through.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_sketch_essentials.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.live.evidence import evidence, starting
from tests.live.test_live_sw_equations import _tools
from tests.live.test_live_sw_equations_wrench import _frame

pytestmark = pytest.mark.asyncio

THICKNESS = 8.0
FILLET_R = 10.0
CHAMFER = 10.0
#: The plate's outline: 120 x 80, two corners rounded, two chamfered.
PLATE_MM2 = 120 * 80 - 2 * FILLET_R**2 * (1 - math.pi / 4) - 2 * CHAMFER**2 / 2
#: Straight slot, 30 mm centre to centre, 10 wide; arc slot, a quarter turn
#: on a 20 mm radius, 8 wide. Each: centreline x width + one end circle.
STRAIGHT_SLOT_MM2 = 30 * 10 + math.pi * 5**2
ARC_SLOT_MM2 = 20 * math.pi / 2 * 8 + math.pi * 4**2
#: Keyhole: a circle r 8 at (0, 10), and a 6 mm wide neck from y = -15 up
#: into it. Circle plus the neck up to the circle's centre line (y = 10),
#: less the neck's part inside the circle's lower half:
#: integral of sqrt(r^2 - x^2) for x from -3 to 3.
_R, _HALF = 8.0, 3.0
_NECK_INSIDE = _HALF * math.sqrt(_R**2 - _HALF**2) + _R**2 * math.asin(_HALF / _R)
KEYHOLE_MM2 = math.pi * _R**2 + 2 * _HALF * (10 + 15) - _NECK_INSIDE
#: Stadium window: 30 mm straight, 10 mm wide, two half-circle ends.
WINDOW_MM2 = 30 * 10 + math.pi * 5**2


async def _volume(tools: dict[str, Any], expected_mm3: float) -> dict[str, Any]:
    """``verify_model`` on the part's volume; the verdict and what it measured."""
    checked = await tools["verify_model"](
        {"volume_mm3": round(expected_mm3, 3), "solid_body_count": 1}
    )
    return {
        "verdict": checked["verdict"],
        "expected_mm3": round(expected_mm3, 2),
        "measured_mm3": checked["measured"].get("volume_mm3"),
    }


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _open(tools: dict[str, Any]) -> str:
    """Open a sketch on the Top plane; its name as create_sketch gives it."""
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    return str(made["sketch"]["name"])


async def _close(tools: dict[str, Any], opened: str) -> str:
    """Close the open sketch; its tree name.

    ``exit_sketch`` names the sketch only when one was asked for, so the
    name ``create_sketch`` gave is kept otherwise.
    """
    closed = await _ok(await tools["exit_sketch"]())
    return str(closed.get("sketch", {"name": opened})["name"])


async def _cut(tools: dict[str, Any], sketch: str) -> None:
    await _ok(
        await tools["create_cut_extrude"](
            {"sketch_name": sketch, "depth": 1, "end_condition": "ThroughAllBoth"}
        )
    )


async def test_a_slotted_bracket_plate(scratch: Any) -> None:
    """Every sketch-essentials operation in one part, each checked by volume."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "bracket"}))

    # 1. The plate: centre rectangle, a refused corner, fillets, chamfers.
    starting("A 120 x 80 plate from its centre, corners rounded and chamfered")
    opened = await _open(tools)
    plate = await _ok(
        await tools["add_rectangle"](
            {"x1": 0, "y1": 0, "x2": 60, "y2": 40, "from_center": True}
        )
    )
    refused = await tools["add_sketch_fillet"]({"corners": [[0, 0]], "radius": 5})
    rounded = await _ok(
        await tools["add_sketch_fillet"](
            {"corners": [[-60, -40], [-60, 40]], "radius": FILLET_R}
        )
    )
    chamfered = await _ok(
        await tools["add_sketch_chamfer"](
            {"corners": [[60, -40], [60, 40]], "distance": CHAMFER}
        )
    )
    outline = await _close(tools, opened)
    await _ok(
        await tools["create_extrusion"]({"sketch_name": outline, "depth": THICKNESS})
    )
    _frame(scratch.adapter)
    plate_volume = PLATE_MM2 * THICKNESS
    built = await _volume(tools, plate_volume)
    evidence(
        "A plate drawn from its centre, two corners rounded, two chamfered",
        {
            "rectangle": {
                k: plate["rectangle"][k]
                for k in ("corner1", "corner2", "width", "height")
            },
            "refused": [
                refused["status"],
                refused.get("error_type"),
                refused["message"],
            ],
            "fillets": rounded["fillet"]["ids"],
            "chamfers": chamfered["chamfer"]["ids"],
            "volume": built,
        },
        call="add_rectangle(from_center), add_sketch_fillet at [0, 0] (refused), "
        "add_sketch_fillet R10 x 2, add_sketch_chamfer 10 x 2, create_extrusion 8",
    )
    assert refused["error_type"] == "invalid_input", refused
    assert built["verdict"] == "pass", built

    # 2. Slots, with two construction lines across them.
    starting("A straight slot and an arc slot, with two construction lines")
    opened = await _open(tools)
    straight = await _ok(
        await tools["add_slot"]({"start": [-40, -15], "end": [-40, 15], "width": 10})
    )
    arc = await _ok(
        await tools["add_slot"](
            {
                "kind": "arc",
                "center": [25, 0],
                "start": [
                    25 + 20 * math.cos(math.radians(-45)),
                    20 * math.sin(math.radians(-45)),
                ],
                "end": [
                    25 + 20 * math.cos(math.radians(45)),
                    20 * math.sin(math.radians(45)),
                ],
                "width": 8,
            }
        )
    )
    across = await _ok(
        await tools["add_line"](
            {"x1": -60, "y1": 0, "x2": 60, "y2": 0, "construction": True}
        )
    )
    upright = await _ok(
        await tools["add_line"]({"x1": 0, "y1": -40, "x2": 0, "y2": 40})
    )
    made = await _ok(
        await tools["set_construction_geometry"]({"entities": [upright["line"]["id"]]})
    )
    await _cut(tools, await _close(tools, opened))
    slotted_volume = plate_volume - (STRAIGHT_SLOT_MM2 + ARC_SLOT_MM2) * THICKNESS
    slotted = await _volume(tools, slotted_volume)
    evidence(
        "A straight slot and an arc slot cut; the two lines across are construction",
        {
            "slot_areas_mm2": [straight["slot"]["area"], arc["slot"]["area"]],
            "construction": {
                "add_line(construction)": across["line"]["construction"],
                "set_construction_geometry": made["construction_geometry"]["entities"],
            },
            "volume": slotted,
        },
        call="add_slot x 2 (straight, arc), add_line(construction), "
        "set_construction_geometry, create_cut_extrude",
    )
    assert straight["slot"]["area"] == pytest.approx(STRAIGHT_SLOT_MM2, abs=1e-3)
    assert arc["slot"]["area"] == pytest.approx(ARC_SLOT_MM2, abs=1e-3)
    assert slotted["verdict"] == "pass", slotted

    # 3. Keyhole: extend two lines to a circle, trim the arc between them.
    starting("A keyhole: two lines extended to a circle, the arc between trimmed")
    opened = await _open(tools)
    await _ok(await tools["add_circle"]({"center_x": 0, "center_y": 10, "radius": _R}))
    for x in (-_HALF, _HALF):
        await _ok(await tools["add_line"]({"x1": x, "y1": -15, "x2": x, "y2": 0}))
    await _ok(
        await tools["add_line"]({"x1": -_HALF, "y1": -15, "x2": _HALF, "y2": -15})
    )
    extended = [
        await _ok(await tools["sketch_extend"]({"point": [x, -0.5]}))
        for x in (-_HALF, _HALF)
    ]
    trimmed = await _ok(await tools["sketch_trim"]({"point": [0, 10 - _R]}))
    await _cut(tools, await _close(tools, opened))
    keyhole_volume = slotted_volume - KEYHOLE_MM2 * THICKNESS
    keyed = await _volume(tools, keyhole_volume)
    evidence(
        "A keyhole: lines extended to the circle, the arc between them trimmed",
        {
            "extend": [e["extend"] for e in extended],
            "trim": trimmed["trim"],
            "keyhole_mm2": round(KEYHOLE_MM2, 3),
            "volume": keyed,
        },
        call="add_circle, add_line x 3, sketch_extend x 2, sketch_trim, "
        "create_cut_extrude",
    )
    assert keyed["verdict"] == "pass", keyed

    # 4. Stadium window: line, tangent arc, line, three-point arc.
    starting("A window from lines, a tangent arc and a three-point arc")
    opened = await _open(tools)
    await _ok(await tools["add_line"]({"x1": -20, "y1": 25, "x2": 10, "y2": 25}))
    tangent = await _ok(
        await tools["add_arc"](
            {"kind": "tangent", "start_x": 10, "start_y": 25, "end_x": 10, "end_y": 35}
        )
    )
    await _ok(await tools["add_line"]({"x1": 10, "y1": 35, "x2": -20, "y2": 35}))
    three = await _ok(
        await tools["add_arc"](
            {
                "kind": "three_point",
                "start_x": -20,
                "start_y": 35,
                "end_x": -20,
                "end_y": 25,
                "through_x": -25,
                "through_y": 30,
            }
        )
    )
    await _cut(tools, await _close(tools, opened))
    final_volume = keyhole_volume - WINDOW_MM2 * THICKNESS
    finished = await _volume(tools, final_volume)
    evidence(
        "A stadium window from a tangent arc and a three-point arc",
        {
            "arcs": [tangent["arc"]["id"], three["arc"]["id"]],
            "window_mm2": round(WINDOW_MM2, 3),
            "volume": finished,
        },
        call="add_line, add_arc(tangent), add_line, add_arc(three_point), "
        "create_cut_extrude",
    )
    assert finished["verdict"] == "pass", finished
    evidence(
        "Sketch essentials demo done",
        {
            "tools": [
                "add_sketch_fillet",
                "add_sketch_chamfer",
                "add_slot",
                "sketch_trim",
                "sketch_extend",
                "set_construction_geometry",
            ],
            "volume_mm3": finished["measured_mm3"],
        },
        call="add_rectangle(from_center), add_arc(tangent, three_point), "
        "add_line(construction)",
    )
