"""Assembly depth (queue item 33), checked on real SolidWorks.

A pinned base, built with every new assembly tool and drawn as a shop would
get it: exploded, with a BOM and numbered balloons. After each step the
component count and the assembly's bounding box are checked against what the
step should have done:

1. Four parts saved: a 120 x 60 x 8 base, a 30 mm and a 45 mm pin (8 mm
   across), and a 10 x 6 x 60 foot.
2. An assembly: the base, one pin standing on it at x = -45, a foot under
   its right end. ``create_axis`` x, then ``pattern_components``: four pins,
   30 mm apart.
3. ``mirror_components``: the foot mirrored about the Right Plane.
4. ``replace_component``: every pin swapped for the 45 mm pin (15 mm
   taller); a file that doesn't exist is refused first.
5. ``set_component_state``: the base hidden, shown again, made transparent
   and opaque.
6. ``create_exploded_view``: the pins lifted 40 mm; ``set_exploded_view``
   collapses and explodes it again.
7. A drawing: an exploded isometric view (``create_drawing_view``
   ``exploded``), a BOM, and ``add_balloons``: one balloon per part.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_assembly_depth.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, starting

pytestmark = pytest.mark.asyncio

#: The least a recording's GIF shows each result caption: long enough to read.
READ_SECONDS = 5.0
BASE = (120.0, 8.0, 60.0)
PIN_DIAMETER = 8.0
SHORT_PIN, LONG_PIN = 30.0, 45.0
FOOT = (10.0, 6.0, 60.0)
PIN_X, PIN_SPACING, PIN_COUNT = -45.0, 30.0, 4
LIFT = 40.0


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool, registered against ``adapter``: name -> function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools import register_tools

    mcp = FastMCP("assembly-depth-live")
    await register_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _part(
    tools: dict[str, Any], scratch: Any, path: Path, draw: dict[str, Any], height: float
) -> str:
    """A part from one Top-plane profile extruded ``height`` mm up; saved."""
    await _ok(await tools["create_part"]({"name": path.stem}))
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    shape = "add_circle" if "radius" in draw else "add_rectangle"
    await _ok(await tools[shape](draw))
    await _ok(await tools["exit_sketch"]())
    await _ok(
        await tools["create_extrusion"](
            {"sketch_name": made["sketch"]["name"], "depth": height}
        )
    )
    saved = await scratch.adapter.save_file(str(path))
    assert saved.is_success, saved.error
    scratch.written_files.append(str(path))
    return str(path)


async def _measure(tools: dict[str, Any]) -> dict[str, Any]:
    """The assembly's component count and bounding box size (mm)."""
    checked = await tools["verify_model"]({"component_count": 0})
    measured = checked["measured"]
    box = measured.get("bounding_box_mm") or {}
    size = box.get("size") if isinstance(box, dict) else box
    return {
        "components": measured.get("component_count"),
        "size_mm": [round(v, 2) for v in size] if size else None,
    }


async def _components(tools: dict[str, Any]) -> list[str]:
    listed = await _ok(await tools["list_components"]())
    return [str(n) for n in listed["components"]]


async def test_a_pinned_base_drawn_exploded_with_balloons(
    scratch: Any, tmp_path: Path
) -> None:
    """Every assembly-depth tool, each step checked by count and size."""
    tools = await _tools(scratch.adapter)

    # 1. The parts.
    starting("Four parts: a base, a short pin, a long pin and a foot")
    base = await _part(
        tools,
        scratch,
        tmp_path / "base.SLDPRT",
        {"x1": 0, "y1": 0, "x2": BASE[0] / 2, "y2": BASE[2] / 2, "from_center": True},
        BASE[1],
    )
    pin = await _part(
        tools,
        scratch,
        tmp_path / "pin30.SLDPRT",
        {"center_x": 0, "center_y": 0, "radius": PIN_DIAMETER / 2},
        SHORT_PIN,
    )
    long_pin = await _part(
        tools,
        scratch,
        tmp_path / "pin45.SLDPRT",
        {"center_x": 0, "center_y": 0, "radius": PIN_DIAMETER / 2},
        LONG_PIN,
    )
    foot = await _part(
        tools,
        scratch,
        tmp_path / "foot.SLDPRT",
        {"x1": 0, "y1": 0, "x2": FOOT[0] / 2, "y2": FOOT[2] / 2, "from_center": True},
        FOOT[1],
    )

    # 2. The assembly, and the pin patterned along x.
    starting("An assembly: the base, a pin and a foot; the pin patterned to four")
    await _ok(await tools["create_assembly"]({"name": "pinned-base"}))
    await _ok(await tools["insert_component"]({"file_path": base}))
    await _ok(
        await tools["insert_component"]({"file_path": pin, "x": PIN_X, "y": BASE[1]})
    )
    await _ok(
        await tools["insert_component"](
            {"file_path": foot, "x": BASE[0] / 2 - FOOT[0] / 2, "y": -FOOT[1]}
        )
    )
    names = await _components(tools)
    pin_name = next(n for n in names if n.startswith("pin30"))
    foot_name = next(n for n in names if n.startswith("foot"))
    axis = await _ok(await tools["create_axis"]({"reference": "x"}))
    pattern = await _ok(
        await tools["pattern_components"](
            {
                "components": [pin_name],
                "axis": axis["axis"]["name"],
                "count": PIN_COUNT,
                "spacing": PIN_SPACING,
            }
        )
    )
    patterned = await _measure(tools)
    evidence(
        "Four pins in a row: one pin patterned along the x axis, 30 mm apart",
        {"pattern": pattern["pattern"], "assembly": patterned},
        call="create_assembly, insert_component x 3, create_axis(x), "
        "pattern_components(count 4, spacing 30)",
        hold=READ_SECONDS,
    )
    assert patterned["components"] == 3 + PIN_COUNT - 1, patterned
    assert patterned["size_mm"][1] == pytest.approx(
        FOOT[1] + BASE[1] + SHORT_PIN, abs=0.01
    )

    # 3. The foot mirrored.
    starting("The foot mirrored about the Right Plane")
    mirror = await _ok(
        await tools["mirror_components"](
            {"components": [foot_name], "plane": "Right Plane"}
        )
    )
    mirrored = await _measure(tools)
    evidence(
        "A second foot under the left end, mirrored about the Right Plane",
        {"mirror": mirror["mirror"], "assembly": mirrored},
        call=f'mirror_components({{"components": ["{foot_name}"], '
        '"plane": "Right Plane"})',
        hold=READ_SECONDS,
    )
    assert mirrored["components"] == patterned["components"] + 1, mirrored

    # 4. Every pin swapped for the long pin; a missing file refused first.
    starting("Every pin swapped for the 45 mm pin")
    refused = await tools["replace_component"](
        {"component": pin_name, "file_path": str(tmp_path / "no-such-pin.SLDPRT")}
    )
    replaced = await _ok(
        await tools["replace_component"](
            {"component": pin_name, "file_path": long_pin, "all_instances": True}
        )
    )
    taller = await _measure(tools)
    evidence(
        "All four pins swapped for the 45 mm pin: 15 mm taller",
        {
            "refused": [refused["status"], refused.get("error_type")],
            "replaced": sorted(replaced["replace"]["replaced"]),
            "assembly": taller,
        },
        call="replace_component(missing file: refused), "
        "replace_component(all_instances)",
        hold=READ_SECONDS,
    )
    assert refused["error_type"] == "invalid_input", refused
    assert len(replaced["replace"]["replaced"]) == PIN_COUNT, replaced
    assert taller["size_mm"][1] == pytest.approx(FOOT[1] + BASE[1] + LONG_PIN, abs=0.01)

    # 5. The base hidden, shown, transparent, opaque.
    starting("The base hidden and shown, then transparent")
    base_name = next(n for n in await _components(tools) if n.startswith("base"))
    hidden = await _ok(
        await tools["set_component_state"]({"component": base_name, "visible": False})
    )
    shown = await _ok(
        await tools["set_component_state"]({"component": base_name, "visible": True})
    )
    clear = await _ok(
        await tools["set_component_state"](
            {"component": base_name, "transparent": True}
        )
    )
    evidence(
        "The base hidden, shown again, then transparent",
        {
            "hidden": hidden["message"],
            "shown": shown["message"],
            "transparent": clear["message"],
        },
        call="set_component_state(visible false), (visible true), (transparent true)",
        hold=READ_SECONDS,
    )
    await _ok(
        await tools["set_component_state"](
            {"component": base_name, "transparent": False}
        )
    )
    assert hidden["state"]["appearance"]["visible"] is False
    assert shown["state"]["appearance"]["visible"] is True

    # 6. The pins exploded upward; collapsed and exploded again.
    starting("The pins exploded 40 mm up")
    pins = [n for n in await _components(tools) if n.startswith("pin")]
    exploded = await _ok(
        await tools["create_exploded_view"](
            {"steps": [{"components": pins, "direction": "y", "distance": LIFT}]}
        )
    )
    collapsed = await _ok(await tools["set_exploded_view"]({"exploded": False}))
    again = await _ok(await tools["set_exploded_view"]({"exploded": True}))
    view = exploded["exploded_view"]
    evidence(
        "The pins lifted 40 mm; collapsed and exploded again",
        {
            "exploded_view": view,
            "collapsed_mm": collapsed["exploded_view"]["size_mm"],
            "exploded_mm": again["exploded_view"]["size_mm"],
        },
        call=f'create_exploded_view(pins, "y", {LIFT:g}), set_exploded_view(false), '
        "set_exploded_view(true)",
        hold=READ_SECONDS,
    )
    grown = view["size_after_mm"][1] - view["size_before_mm"][1]
    assert grown == pytest.approx(LIFT, abs=0.01), view
    assert collapsed["exploded_view"]["exploded"] is False
    assert again["exploded_view"]["exploded"] is True

    # 7. The drawing: exploded isometric view, BOM, balloons.
    starting("A drawing: the exploded view, a BOM and balloons")
    assembly = str(tmp_path / "pinned-base.SLDASM")
    saved = await scratch.adapter.save_file(assembly)
    assert saved.is_success, saved.error
    scratch.written_files.append(assembly)
    await _ok(await tools["create_drawing"]({"name": "pinned-base"}))
    placed = await _ok(
        await tools["create_drawing_view"](
            {
                "model_path": assembly,
                "view_type": "isometric",
                "orientation": "isometric",
                "position_x": 150,
                "position_y": 150,
                "exploded": True,
            }
        )
    )
    view_name = placed["data"]["name"]
    bom = await _ok(await tools["insert_bom_table"]({"view_name": view_name}))
    balloons = await _ok(
        await tools["add_balloons"]({"view_name": view_name, "layout": "square"})
    )
    evidence(
        "An exploded isometric view, a BOM and one balloon per part",
        {
            "view": {"name": view_name, "exploded": placed["data"].get("exploded")},
            "bom_rows": bom.get("bom", bom.get("data", {})).get("row_count"),
            "balloons": balloons["balloons"],
        },
        call="create_drawing_view(isometric, exploded), insert_bom_table, "
        'add_balloons(layout "square")',
        hold=READ_SECONDS,
    )
    assert placed["data"].get("exploded") is True, placed
    assert balloons["balloons"]["count"] == 3, balloons
    evidence(
        "Assembly depth demo done",
        {
            "tools": [
                "pattern_components",
                "mirror_components",
                "replace_component",
                "create_exploded_view",
                "set_exploded_view",
                "add_balloons",
            ],
            "also": "set_component_state(visible, transparent), "
            "create_drawing_view(exploded)",
        },
        call="a pinned base, patterned, mirrored, swapped, exploded and ballooned",
        hold=READ_SECONDS,
    )
