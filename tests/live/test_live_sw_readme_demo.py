"""The README demo: a prompt, the tool calls that answer it, and the result.

One live test, recorded as one GIF for the top of the README. The prompt
asks for two drilled steel plates stacked 10 mm apart, checked, and drawn.
The test replays the tool calls an agent makes for that prompt, through the
registered MCP tools (the path an MCP client hits), and checks every number
against a hand calculation:

- plate: 100 x 50 x 10 mm = 50 000 mm³, less four Ø5.5 x 10 mm holes
  (4 x 237.6 mm³) = 49 049.7 mm³, 0.3875 kg of AISI 1020 (7900 kg/m³);
- stack: the Top planes 20 mm apart leave a 10 mm gap between the 10 mm
  plates, so the assembly is 30 mm tall;
- drawing: A3, title block and notes filled, a BOM listing the plate twice.

Each step is an evidence frame, and the drawing generator's seven build steps
are shown as it fills the sheet. Every call is also written to
``plate_stack_calls.json`` beside the frames when capturing, as the
transcript the README shows. This is a replay of the calls, not a recorded
model session; recording one is part of the bracket demo (#147).

Run it as a demo with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_readme_demo.py `
        -CaptureDir docs/assets/demos/readme

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_drawing_package_tools import (
    _bom_cells,
    _sheet_texts,
    _show_each_build_step,
    _view_widths,
)

PROMPT = (
    "Make a 100 x 50 x 10 mm AISI 1020 mounting plate with four M5 clearance "
    "holes, 10 mm in from each edge. Stack two of them 10 mm apart, check the "
    "result, and draw the assembly with notes, a title block and a BOM."
)

#: The directions an agent works out from the prompt before calling anything.
PLAN = [
    "1. plate: sketch 100 x 50 on Top, extrude 10 mm (expect +50000 mm³)",
    "2. holes: four Ø5.5 at (±40, ±15), cut 10 mm (expect -950.3 mm³)",
    "3. AISI 1020, then verify_model: 49049.7 mm³, 0.3875 kg, 2 features",
    "4. assembly: insert the plate twice",
    "5. mates: Front and Right coincident, Top planes 20 mm apart (10 mm gap)",
    "6. verify_model: 2 components, 3 mates, no interference, 30 mm tall",
    "7. generate_drawing_package: A3, views, dimensions, notes, title block",
    "8. insert_bom_table: the plate, QTY 2",
]

_PLATE_MM = (100.0, 50.0, 10.0)
_HOLE_RADIUS_MM = 2.75
_HOLES_MM = [(-40.0, -15.0), (40.0, -15.0), (40.0, 15.0), (-40.0, 15.0)]
_HOLES_MM3 = len(_HOLES_MM) * math.pi * _HOLE_RADIUS_MM**2 * _PLATE_MM[2]
_PLATE_MM3 = math.prod(_PLATE_MM) - _HOLES_MM3
#: AISI 1020 is 7900 kg/m³ in the SolidWorks material library.
_PLATE_KG = _PLATE_MM3 * 1e-9 * 7900.0
_GAP_MM = 10.0

#: Added after the generator's own lines (material, units, projection, burrs).
NOTES = [
    "PLATES: AISI 1020 STEEL, QTY 2",
    "4 X Ø5.5 THRU IN EACH PLATE, M5 CLEARANCE",
    f"PLATES SPACED {_GAP_MM:g} MM APART",
]


class _Session:
    """Calls the registered MCP tools and keeps a transcript of each call."""

    def __init__(self, tools: dict[str, Any]) -> None:
        self.tools = tools
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Call one tool, record it, and require success."""
        tool = self.tools[name]
        result = await (tool() if args is None else tool(args))
        status = result.get("status") if isinstance(result, dict) else None
        self.calls.append({"tool": name, "args": args or {}, "status": status})
        assert status == "success", (name, result)
        return result


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register every tool the demo uses against ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.drawing_automation import (
        register_drawing_automation_tools,
    )
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("readme-demo-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_engineering_data_tools,
        register_analysis_tools,
        register_drawing_automation_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


def _brief(result: dict[str, Any]) -> dict[str, Any]:
    """A ``verify_model`` reply cut down to fit a GIF caption."""
    return {
        "verdict": result["verdict"],
        "message": result["message"],
        "checks": [
            {k: c[k] for k in ("name", "expected", "actual", "passed") if k in c}
            for c in result["checks"]
        ],
    }


async def _plate(call: _Session) -> None:
    """Sketch, extrude and drill the plate, showing each measured change."""
    sketch = await call("create_sketch", {"plane": "Top"})
    width, depth, thickness = _PLATE_MM
    await call(
        "add_rectangle",
        {"x1": -width / 2, "y1": -depth / 2, "x2": width / 2, "y2": depth / 2},
    )
    await call("exit_sketch")
    args = {"sketch_name": sketch["sketch"]["name"], "depth": thickness}
    boss = await call("create_extrusion", args)
    evidence(
        "step 1: the plate, 100 x 50 x 10 mm (expect +50000 mm³)",
        boss["measured_change"],
        call=f"create_extrusion({args})",
    )
    assert boss["measured_change"]["volume_delta_mm3"] == pytest.approx(
        math.prod(_PLATE_MM), rel=1e-6
    )

    holes = await call("create_sketch", {"plane": "Top"})
    for x, y in _HOLES_MM:
        await call(
            "add_circle", {"center_x": x, "center_y": y, "radius": _HOLE_RADIUS_MM}
        )
    await call("exit_sketch")
    args = {"sketch_name": holes["sketch"]["name"], "depth": thickness}
    cut = await call("create_cut_extrude", args)
    evidence(
        f"step 2: four Ø5.5 holes (expect -{_HOLES_MM3:.1f} mm³)",
        cut["measured_change"],
        call=f"create_cut_extrude({args})",
    )
    assert cut["measured_change"]["volume_delta_mm3"] == pytest.approx(
        -_HOLES_MM3, rel=1e-4
    )
    assert "warning" not in cut


@pytest.mark.asyncio
async def test_plate_stack_from_prompt_to_drawing(scratch, tmp_path, monkeypatch):
    """Two drilled plates, stacked 10 mm apart, checked, drawn with a BOM."""
    adapter = scratch.adapter
    call = _Session(await _tools(adapter))
    evidence(
        "the prompt, and the plan worked out from it", {"prompt": PROMPT, "plan": PLAN}
    )

    # The plate.
    assert (await adapter.create_part()).is_success
    await _plate(call)
    await call("set_material", {"material_name": "AISI 1020"})
    expected = {
        "volume_mm3": round(_PLATE_MM3, 1),
        "mass_kg": round(_PLATE_KG, 4),
        "bounding_box_mm": [100, 10, 50],
        "feature_count": 2,
        "solid_body_count": 1,
    }
    plate_check = await call("verify_model", expected)
    evidence(
        "step 3: AISI 1020, then check the plate",
        _brief(plate_check),
        call=f"verify_model({expected})",
    )
    assert plate_check["verdict"] == "pass", plate_check
    plate = str(tmp_path / "Demo Plate.SLDPRT")
    assert (await adapter.save_file(plate)).is_success
    scratch.written_files.append(plate)

    # Two of them, 10 mm apart.
    assert (await adapter.create_assembly()).is_success
    await call("insert_component", {"file_path": plate})
    await call("insert_component", {"file_path": plate, "y": 40.0})
    a, b = (await call("list_components"))["components"]
    mates = []
    for entity, mate_type, distance in (
        ("Front Plane", "coincident", 0.0),
        ("Right Plane", "coincident", 0.0),
        ("Top Plane", "distance", _GAP_MM + _PLATE_MM[2]),
    ):
        args = {
            "component_a": a,
            "component_b": b,
            "entity_a": entity,
            "entity_b": entity,
            "mate_type": mate_type,
            "distance": distance,
        }
        mates.append((await call("add_mate", args))["message"])
    evidence(
        "step 4-5: the plate twice, held 10 mm apart by three mates",
        {"components": [a, b], "mates": mates},
        call=f"add_mate({args})",
    )

    expected = {"component_count": 2, "mate_count": 3, "no_interference": True}
    stack = await call("verify_model", expected)
    height = stack["measured"]["bounding_box_mm"]["size"][1]
    evidence(
        "step 6: check the stack; the gap is the height less two plates",
        {
            **_brief(stack),
            "stack_height_mm": height,
            "gap_mm": round(height - 2 * _PLATE_MM[2], 3),
        },
        call=f"verify_model({expected})",
    )
    assert stack["verdict"] == "pass", stack
    assert height - 2 * _PLATE_MM[2] == pytest.approx(_GAP_MM, abs=0.01)
    assembly = str(tmp_path / "Plate Stack.SLDASM")
    assert (await adapter.save_file(assembly)).is_success
    scratch.written_files.append(assembly)

    # The drawing: each of the generator's build steps is a frame.
    out = tmp_path / "drawings"
    _show_each_build_step(adapter, monkeypatch)
    args = {
        "model_path": assembly,
        "output_dir": str(out),
        "title": "Plate Stack",
        "drawing_number": "PS-01",
        "author": "solidworks-mcp",
        "notes": NOTES,
    }
    package = await call("generate_drawing_package", args)
    drawing = out / "PS-01.SLDDRW"
    scratch.written_files += [str(drawing), str(out / "PS-01.pdf")]
    shown = _sheet_texts(adapter)
    evidence(
        "step 7: the A3 drawing, notes and title block",
        {
            "message": package.get("message"),
            "views": package["data"].get("views"),
            "overlaps_after": package["data"]["overlap_check"]["overlaps_after"],
            "title_block": [t for t in shown if len(t.strip()) > 1],
        },
        call='generate_drawing_package({"model_path": "Plate Stack.SLDASM", ...})',
    )
    assert package["data"]["overlap_check"]["overlaps_after"] == 0
    assert "Plate Stack" in shown

    view = next(iter(_view_widths(adapter)))
    bom = await call("insert_bom_table", {"view_name": view})
    cells = _bom_cells(adapter)
    evidence(
        "step 8: the BOM lists the plate twice",
        {"table_box_mm": bom["data"]["table_box_mm"], "cells": cells},
        call=f'insert_bom_table({{"view_name": "{view}"}})',
    )
    plate_rows = [row for row in cells if any("Demo Plate" in c for c in row)]
    assert plate_rows and plate_rows[0][-1].strip() == "2", cells
    assert (await adapter.save_file(str(drawing))).is_success

    evidence(
        f"{len(call.calls)} tool calls from prompt to drawing, all successful",
        " -> ".join(c["tool"] for c in call.calls),
    )
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        transcript = Path(capture_dir) / "plate_stack_calls.json"
        transcript.write_text(
            json.dumps({"prompt": PROMPT, "plan": PLAN, "calls": call.calls}, indent=2),
            encoding="utf-8",
        )
