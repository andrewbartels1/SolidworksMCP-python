"""The README demo: a prompt, the tool calls that answer it, and the result.

One live test, recorded as one GIF for the top of the README. The prompt
asks for a drilled steel plate, two of them stacked 10 mm apart, checked, and
drawn. The test replays the tool calls an agent makes for that prompt,
through the registered MCP tools (the path an MCP client hits), and checks
every number against a hand calculation:

- plate: one sketch, every size and position dimensioned: a 100 x 50 mm
  outline from the origin and four Ø5.5 holes 10 mm in from two edges each,
  extruded 10 mm: 50 000 - 4 x 237.6 = 49 049.7 mm³, 0.3875 kg of AISI 1020
  (7900 kg/m³);
- plate drawing: A3, the sketch and extrude dimensions (100, 50, 10, Ø5.5 and
  the hole positions), centre marks on the holes, AISI 1020 in the title block;
- stack: the Top planes 20 mm apart leave a 10 mm gap between the 10 mm
  plates, so the assembly is 30 mm tall;
- assembly drawing: views, notes and a BOM listing the plate twice.

Each step is an evidence frame, and the plate drawing's seven build steps are
shown as the generator fills the sheet. Every call is also written to
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
)

PROMPT = (
    "Make a 100 x 50 x 10 mm AISI 1020 mounting plate with four M5 clearance "
    "holes, 10 mm in from each edge, and draw it fully dimensioned. Stack two "
    "of them 10 mm apart, check the result, and draw the assembly with a BOM."
)

#: The directions an agent works out from the prompt before calling anything.
PLAN = [
    "1. sketch on Top: 100 x 50 outline from the origin, four Ø5.5 circles,",
    "   every size and position dimensioned; extrude 10 mm",
    "2. AISI 1020, then verify_model: 49049.7 mm³, 0.3875 kg, 1 feature",
    "3. plate drawing: A3, model dimensions, centre marks, notes, title block",
    "4. assembly: the plate twice; Front and Right coincident, Top planes 20",
    "   mm apart (a 10 mm gap); verify_model: 2 parts, 3 mates, no overlap",
    "5. assembly drawing with a BOM: the plate, QTY 2",
]

_WIDTH_MM, _DEPTH_MM, _THICKNESS_MM = 100.0, 50.0, 10.0
_HOLE_DIAMETER_MM = 5.5
_EDGE_MM = 10.0
_HOLES_MM3 = 4 * math.pi * (_HOLE_DIAMETER_MM / 2) ** 2 * _THICKNESS_MM
_PLATE_MM3 = _WIDTH_MM * _DEPTH_MM * _THICKNESS_MM - _HOLES_MM3
#: AISI 1020 is 7900 kg/m³ in the SolidWorks material library.
_PLATE_KG = _PLATE_MM3 * 1e-9 * 7900.0
_GAP_MM = 10.0

#: Added after the generator's own lines (material, units, projection, burrs).
PLATE_NOTES = ["4 X Ø5.5 THRU, M5 CLEARANCE", "QTY 2 PER ASSEMBLY PS-02"]
ASSEMBLY_NOTES = [
    "2 X DEMO PLATE PS-01, AISI 1020",
    f"PLATES SPACED {_GAP_MM:g} MM APART",
]
#: The BOM's bottom-left corner on the assembly sheet, in mm: the top-right
#: cell, left empty by drawing the assembly without an isometric view.
_BOM_AT_MM = (240.0, 255.0)


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
    from solidworks_mcp.tools.drawing import register_drawing_tools
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
        register_drawing_tools,
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


async def _plate_sketch(call: _Session) -> tuple[str, list[str]]:
    """Sketch the plate with every size and hole position dimensioned.

    Returns:
        tuple: The sketch name, and each dimension as ``"what = value"``.
    """
    sketch = (await call("create_sketch", {"plane": "Top"}))["sketch"]["name"]
    w, d = _WIDTH_MM, _DEPTH_MM
    corners = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    edges = {}
    for name, (x1, y1), (x2, y2) in zip(
        ("bottom", "right", "top", "left"),
        corners,
        corners[1:] + corners[:1],
        strict=True,
    ):
        line = await call("add_line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        edges[name] = line["line"]["id"]

    dims = []

    async def dimension(
        entity1: str, entity2: str | None, kind: str, value: float, what: str
    ) -> None:
        await call(
            "add_sketch_dimension",
            {
                "entity1": entity1,
                "entity2": entity2,
                "dimension_type": kind,
                "value": value,
            },
        )
        dims.append(f"{what} = {value:g}")

    await dimension(edges["bottom"], None, "linear", w, "width")
    await dimension(edges["left"], None, "linear", d, "depth")
    e = _EDGE_MM
    for x, y, side, end in (
        (e, e, "left", "bottom"),
        (w - e, e, "right", "bottom"),
        (w - e, d - e, "right", "top"),
        (e, d - e, "left", "top"),
    ):
        hole = await call(
            "add_circle",
            {"center_x": x, "center_y": y, "radius": _HOLE_DIAMETER_MM / 2},
        )
        circle = hole["circle"]["id"]
        await dimension(circle, None, "diameter", _HOLE_DIAMETER_MM, f"{circle} Ø")
        await dimension(edges[side], circle, "linear", e, f"{circle} to {side} edge")
        await dimension(edges[end], circle, "linear", e, f"{circle} to {end} edge")
    await call("exit_sketch")
    return sketch, dims


def _role(package: dict[str, Any], role: str) -> str:
    """The drawing view the generator gave ``role`` (front, plan, side, iso)."""
    views = package["data"]["views"]
    return next(name for name, v in views.items() if v.get("role") == role)


@pytest.mark.asyncio
async def test_plate_stack_from_prompt_to_drawing(scratch, tmp_path, monkeypatch):
    """A fully dimensioned plate and its drawing; two stacked 10 mm apart, with a BOM."""
    adapter = scratch.adapter
    call = _Session(await _tools(adapter))
    out = tmp_path / "drawings"
    evidence(
        "the prompt, and the plan worked out from it", {"prompt": PROMPT, "plan": PLAN}
    )

    # The plate: one sketch, fully dimensioned, then one extrude.
    assert (await adapter.create_part()).is_success
    sketch, dims = await _plate_sketch(call)
    definition = (await call("check_sketch_fully_defined", {"sketch_name": sketch}))[
        "sketch"
    ]
    evidence(
        f"step 1: the sketch, {len(dims)} dimensions",
        {
            "definition_state": definition.get("definition_state"),
            "dimensions": "; ".join(dims),
        },
        call=f'check_sketch_fully_defined({{"sketch_name": "{sketch}"}})',
    )
    args = {"sketch_name": sketch, "depth": _THICKNESS_MM}
    boss = await call("create_extrusion", args)
    evidence(
        f"step 1: extrude 10 mm (expect +{_PLATE_MM3:.1f} mm³, holes and all)",
        boss["measured_change"],
        call=f"create_extrusion({args})",
    )
    assert boss["measured_change"]["volume_delta_mm3"] == pytest.approx(
        _PLATE_MM3, rel=1e-4
    )

    await call("set_material", {"material_name": "AISI 1020"})
    expected = {
        "volume_mm3": round(_PLATE_MM3, 1),
        "mass_kg": round(_PLATE_KG, 4),
        "bounding_box_mm": [_WIDTH_MM, _THICKNESS_MM, _DEPTH_MM],
        "feature_count": 1,
        "solid_body_count": 1,
    }
    plate_check = await call("verify_model", expected)
    evidence(
        "step 2: AISI 1020, then check the plate",
        _brief(plate_check),
        call=f"verify_model({expected})",
    )
    assert plate_check["verdict"] == "pass", plate_check
    plate = str(tmp_path / "Demo Plate.SLDPRT")
    assert (await adapter.save_file(plate)).is_success
    scratch.written_files.append(plate)

    # The plate's drawing; each of the generator's build steps is a frame.
    with monkeypatch.context() as watching:
        _show_each_build_step(adapter, watching)
        args = {
            "model_path": plate,
            "output_dir": str(out),
            "title": "Demo Plate",
            "drawing_number": "PS-01",
            "author": "solidworks-mcp",
            "notes": PLATE_NOTES,
        }
        detail = await call("generate_drawing_package", args)
    scratch.written_files += [str(out / "PS-01.SLDDRW"), str(out / "PS-01.pdf")]
    plan_view = _role(detail, "plan")
    marks = await call("auto_center_marks", {"view_name": plan_view})
    shown = _sheet_texts(adapter)
    assert (await adapter.save_file(str(out / "PS-01.SLDDRW"))).is_success
    assert (await adapter.export_file(str(out / "PS-01.pdf"), "pdf")).is_success
    evidence(
        "step 3: the plate drawing: dimensions, centre marks, AISI 1020",
        {
            "dimensions_on_sheet": detail["data"]["overlap_check"]["dimensions"],
            "overlaps_after": detail["data"]["overlap_check"]["overlaps_after"],
            "centre_marks_added": marks.get("center_marks_added"),
            "title_block": [t for t in shown if len(t.strip()) > 1][-6:],
        },
        call=f'auto_center_marks({{"view_name": "{plan_view}"}})',
    )
    assert detail["data"]["overlap_check"]["overlaps_after"] == 0
    assert "AISI 1020" in shown

    # Two plates, 10 mm apart.
    assert (await adapter.create_assembly()).is_success
    await call("insert_component", {"file_path": plate})
    await call("insert_component", {"file_path": plate, "y": 40.0})
    a, b = (await call("list_components"))["components"]
    mates = []
    for entity, mate_type, distance in (
        ("Front Plane", "coincident", 0.0),
        ("Right Plane", "coincident", 0.0),
        ("Top Plane", "distance", _GAP_MM + _THICKNESS_MM),
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
    expected = {"component_count": 2, "mate_count": 3, "no_interference": True}
    stack = await call("verify_model", expected)
    height = stack["measured"]["bounding_box_mm"]["size"][1]
    evidence(
        "step 4: two plates, three mates; the gap is the height less two plates",
        {
            **_brief(stack),
            "stack_height_mm": height,
            "gap_mm": round(height - 2 * _THICKNESS_MM, 3),
        },
        call=f"verify_model({expected})",
    )
    assert stack["verdict"] == "pass", stack
    assert height - 2 * _THICKNESS_MM == pytest.approx(_GAP_MM, abs=0.01)
    assembly = str(tmp_path / "Plate Stack.SLDASM")
    assert (await adapter.save_file(assembly)).is_success
    scratch.written_files.append(assembly)

    # The assembly drawing, and its BOM where the isometric view would be.
    args = {
        "model_path": assembly,
        "output_dir": str(out),
        "title": "Plate Stack",
        "drawing_number": "PS-02",
        "author": "solidworks-mcp",
        "notes": ASSEMBLY_NOTES,
        "include_isometric": False,
    }
    package = await call("generate_drawing_package", args)
    scratch.written_files += [str(out / "PS-02.SLDDRW"), str(out / "PS-02.pdf")]
    x, y = _BOM_AT_MM
    bom_args = {"view_name": _role(package, "front"), "x_mm": x, "y_mm": y}
    bom = await call("insert_bom_table", bom_args)
    cells = _bom_cells(adapter)
    assert (await adapter.save_file(str(out / "PS-02.SLDDRW"))).is_success
    assert (await adapter.export_file(str(out / "PS-02.pdf"), "pdf")).is_success
    evidence(
        "step 5: the assembly drawing; the BOM lists the plate twice",
        {"table_box_mm": bom["data"]["table_box_mm"], "cells": cells},
        call=f"insert_bom_table({bom_args})",
    )
    plate_rows = [row for row in cells if any("Demo Plate" in c for c in row)]
    assert plate_rows and plate_rows[0][-1].strip() == "2", cells

    evidence(
        f"{len(call.calls)} tool calls from prompt to drawings, all successful",
        " -> ".join(c["tool"] for c in call.calls),
    )
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        transcript = Path(capture_dir) / "plate_stack_calls.json"
        transcript.write_text(
            json.dumps({"prompt": PROMPT, "plan": PLAN, "calls": call.calls}, indent=2),
            encoding="utf-8",
        )
