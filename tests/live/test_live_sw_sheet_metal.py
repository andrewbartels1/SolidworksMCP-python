"""Sheet metal (queue item 15, #57), checked on real SolidWorks.

1. ``create_base_flange``: a 100 x 60 x 2 mm plate (2 mm radius, K 0.5),
   12,000 mm³, the values read back;
2. ``add_edge_flange``: 20 mm on a long edge;
3. ``set_flat_pattern``: the blank is 60 + (20 + 2) - 3.288 = 78.712 mm
   wide (the bend deduction from K 0.5); folded back to 22 mm tall;
4. ``export_flat_pattern`` writes the DXF;
5. ``create_sketched_bend`` on a second plate: no longer flat;
6. on purpose: an extruded block is refused.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_sheet_metal.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence, note
from tests.live.test_live_sw_material_properties import _tools

pytestmark = pytest.mark.asyncio

#: 60 mm plate + (20 mm flange + 2 mm sheet) - the bend deduction for a
#: 2 mm radius and K 0.5: 2(2 + 2) - pi/2 (2 + 0.5 x 2).
BLANK_MM = 78.712


async def _plate(tools: dict[str, Any], name: str) -> dict[str, Any]:
    """A new part, a 100 x 60 mm rectangle on Top, and the 2 mm base flange."""
    assert (await tools["create_part"]({"name": name}))["status"] == "success"
    await tools["create_sketch"]({"plane": "Top"})
    await tools["add_rectangle"]({"x1": -50, "y1": -30, "x2": 50, "y2": 30})
    await tools["exit_sketch"]()
    base = await tools["create_base_flange"]({"thickness": 2, "bend_radius": 2})
    assert base["status"] == "success", base
    return base


async def test_a_plate_to_a_dxf(scratch: Any, tmp_path: Path) -> None:
    """Base flange, edge flange, the blank measured, the DXF, a bend, a refusal."""
    tools = await _tools(scratch.adapter)
    note(
        "Sheet metal",
        "A 100 x 60 x 2 mm plate, a 20 mm flange on a long edge, flattened to "
        "its blank (78.712 mm by hand), exported, and a bend across a second plate.",
        seconds=4.0,
    )
    base = await _plate(tools, "sm_bracket")
    evidence("create_base_flange: the plate", base["flange"])

    # The plate is thickened downward: its top face is y = 0.
    flange = await tools["add_edge_flange"]({"edge_point": [0, 0, 30], "length": 20})
    evidence("add_edge_flange: 20 mm on the long edge", flange.get("flange", flange))
    flat = await tools["set_flat_pattern"]({"flat": True})
    evidence(
        f"set_flat_pattern: the blank ({BLANK_MM} mm by hand)",
        {"message": flat["message"], "box": flat.get("bounding_box_mm")},
    )
    dxf = str(tmp_path / "bracket.dxf")
    part_file = str(tmp_path / "bracket.SLDPRT")
    scratch.written_files += [dxf, part_file]
    assert (await scratch.adapter.save_file(part_file)).is_success
    exported = await tools["export_flat_pattern"]({"file_path": dxf})
    evidence(
        "export_flat_pattern: the DXF",
        {"status": exported["status"], "written": os.path.isfile(dxf)},
    )
    folded = await tools["set_flat_pattern"]({"flat": False})
    evidence("set_flat_pattern: folded back", folded["message"])

    await _plate(tools, "sm_bend")
    await tools["create_sketch"]({"face_point": [20, 0, 0]})
    await tools["add_line"]({"x1": 0, "y1": -40, "x2": 0, "y2": 40})
    await tools["exit_sketch"]()
    bend = await tools["create_sketched_bend"]({"angle": 90})
    evidence("create_sketched_bend: across the middle", bend.get("bend", bend))

    assert (await tools["create_part"]({"name": "sm_block"}))["status"] == "success"
    await tools["create_sketch"]({"plane": "Top"})
    await tools["add_rectangle"]({"x1": -20, "y1": -20, "x2": 20, "y2": 20})
    await tools["exit_sketch"]()
    assert (await tools["create_extrusion"]({"depth": 10}))["status"] == "success"
    note(
        "Next, on purpose: a flange on an extruded block",
        "The block isn't sheet metal, so the tool refuses and changes nothing.",
        seconds=4.0,
    )
    refused = await tools["add_edge_flange"]({"edge_point": [0, 10, 20], "length": 10})
    evidence(
        "add_edge_flange on a block: refused, as intended",
        {k: refused[k] for k in ("status", "error_type", "message")},
    )

    assert base["flange"]["volume_after"] == pytest.approx(12000, abs=0.01)
    assert (base["flange"]["thickness_mm"], base["flange"]["k_factor"]) == (2.0, 0.5)
    assert flange["status"] == "success", flange
    assert flange["flange"]["edge_length_mm"] == pytest.approx(100)
    assert flat["bounding_box_mm"]["size"][2] == pytest.approx(BLANK_MM, abs=0.1)
    assert folded["bounding_box_mm"]["size"][1] == pytest.approx(22, abs=0.01)
    assert exported["status"] == "success" and os.path.isfile(dxf)
    assert bend["status"] == "success", bend
    assert bend["bend"]["bounding_box_mm"]["size"][1] > 40
    assert refused["error_type"] == "wrong_document_type"
    assert "create_base_flange" in refused["message"]
