"""Colours and reference extras (queue items 36 and 39), checked on real SolidWorks.

1. Colours: a 40 x 40 x 10 mm block. Its feature green, its top face blue, its
   body orange: the top face shows blue (face), a side face green (the
   feature shows over the body). The face's colour removed: green again. On
   purpose: two targets at once are refused.
2. Reference extras on the same block: the top face's section (1,600 mm²,
   centroid (0, 10, 0), 40⁴/12 = 213,333.3 mm⁴ about x and z), a coordinate
   system at the corner (20, 10, 20), the centre of mass
   (0, 5, 0) and the bounding box 40 x 10 x 40. On purpose: a second Center
   of Mass point is refused.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_appearance_and_reference.py::test_colours_on_a_block

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_material_properties import _tools as _base_tools

pytestmark = pytest.mark.asyncio

GREEN = "#1fcc33"
BLUE = [25, 76, 242]
ORANGE = "#f28c1a"
_ISO_VIEW = 7  # swStandardViews_e.swIsometricView


async def _tools(adapter: Any) -> dict[str, Any]:
    """The modelling tools plus the body, appearance and reference tools."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.appearance import register_appearance_tools
    from solidworks_mcp.tools.bodies import register_body_tools
    from solidworks_mcp.tools.reference_extras import (
        register_reference_extras_tools,
    )

    tools = await _base_tools(adapter)
    mcp = FastMCP("appearance-live")
    for register in (
        register_body_tools,
        register_appearance_tools,
        register_reference_extras_tools,
    ):
        await register(mcp, adapter, {})
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


async def _block(tools: dict[str, Any], name: str) -> None:
    """A 40 x 40 x 10 mm block on the Top Plane: y 0 to 10."""
    await _ok(await tools["create_part"]({"name": name}))
    await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_rectangle"]({"x1": -20, "y1": -20, "x2": 20, "y2": 20}))
    await _ok(await tools["exit_sketch"]())
    await _ok(await tools["create_extrusion"]({"depth": 10}))


async def test_colours_on_a_block(scratch: Any) -> None:
    """Feature, face and body colours, which one shows, and a reset."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _block(tools, "colours")
    body = (await _ok(await tools["list_bodies"]()))["bodies"][0]["name"]

    call = {"feature": "Boss-Extrude1", "color": GREEN}
    green = await _ok(await tools["set_appearance"](call))
    _iso(adapter)
    evidence("the feature green", green["appearance"], call=f"set_appearance({call})")
    assert green["appearance"]["hex"] == GREEN

    call = {"face_point": [0, 10, 0], "color": BLUE}
    blue = await _ok(await tools["set_appearance"](call))
    _iso(adapter)
    evidence("the top face blue", blue["appearance"], call=f"set_appearance({call})")
    assert blue["appearance"]["color"] == BLUE

    call = {"body": body, "color": ORANGE}
    orange = await _ok(await tools["set_appearance"](call))
    _iso(adapter)
    evidence(
        "the body orange: the feature's green still shows on the sides",
        orange["appearance"],
        call=f"set_appearance({call})",
    )
    assert orange["appearance"]["hex"] == ORANGE

    top = await _ok(await tools["get_appearance"]({"face_point": [0, 10, 0]}))
    side = await _ok(await tools["get_appearance"]({"face_point": [20, 5, 0]}))
    evidence(
        "what shows: the top face's own blue, a side face's feature green",
        {"top": top["appearance"], "side": side["appearance"]},
    )
    assert top["appearance"]["level"] == "face"
    assert side["appearance"]["level"] == "feature"
    assert side["appearance"]["hex"] == GREEN

    # On purpose: two targets.
    refused = await tools["set_appearance"](
        {"feature": "Boss-Extrude1", "face_point": [0, 10, 0], "color": BLUE}
    )
    evidence("two targets are refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    call = {"face_point": [0, 10, 0], "reset": True}
    reset = await _ok(await tools["set_appearance"](call))
    _iso(adapter)
    evidence(
        "the top face's colour removed: the feature's green shows",
        reset["appearance"],
        call=f"set_appearance({call})",
    )
    assert reset["appearance"]["showing"]["level"] == "feature"
    assert reset["appearance"]["showing"]["hex"] == GREEN


async def test_reference_extras_on_a_block(scratch: Any) -> None:
    """Section, coordinate systems, centre of mass and bounding box of a block."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _block(tools, "reference")
    _iso(adapter)

    call = {"face_point": [0, 10, 0]}
    section = await _ok(await tools["get_section_properties"](call))
    evidence(
        "the top face's section (expect 1,600 mm², 213,333.3 mm⁴)",
        section["section"],
        call=f"get_section_properties({call})",
    )
    data = section["section"]
    assert data["area_mm2"] == pytest.approx(1600, rel=1e-6)
    assert data["centroid_mm"] == pytest.approx([0, 10, 0], abs=1e-6)
    assert data["ixx"] == pytest.approx(40**4 / 12, rel=1e-4)
    assert data["izz"] == pytest.approx(40**4 / 12, rel=1e-4)
    assert data["polar_moment_mm4"] == pytest.approx(40**4 / 6, rel=1e-4)

    call = {"origin": [20, 10, 20]}
    corner = await _ok(await tools["create_coordinate_system"](call))
    _iso(adapter)
    evidence(
        "a coordinate system at the corner (20, 10, 20)",
        corner["coordinate_system"],
        call=f"create_coordinate_system({call})",
    )
    assert corner["coordinate_system"]["origin_mm"] == pytest.approx(
        [20, 10, 20], abs=1e-6
    )
    assert corner["coordinate_system"]["x_axis"] == pytest.approx([1, 0, 0])

    com = await _ok(await tools["create_center_of_mass_point"]())
    _iso(adapter)
    evidence(
        "the Center of Mass point (expect (0, 5, 0))",
        com["center_of_mass"],
        call="create_center_of_mass_point()",
    )
    assert com["center_of_mass"]["center_of_mass_mm"] == pytest.approx(
        [0, 5, 0], abs=1e-6
    )

    # On purpose: a second one.
    refused = await tools["create_center_of_mass_point"]()
    evidence("a second Center of Mass point is refused", refused)
    assert refused["status"] == "error" and refused["error_type"] == "invalid_input"

    box = await _ok(await tools["create_bounding_box"]())
    _iso(adapter)
    evidence(
        "the bounding box (expect 40 x 10 x 40)",
        box["bounding_box"],
        call="create_bounding_box()",
    )
    assert box["bounding_box"]["size_mm"] == pytest.approx([40, 10, 40], abs=1e-6)
