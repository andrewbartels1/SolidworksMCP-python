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
  plates, so the assembly is 30 mm tall; the distance mate starts at 60 mm
  and is stepped down to 20, so the top plate is seen coming into place;
- assembly drawing: views, an isometric, notes, the same GD&T on the
  bottom plate and a BOM listing the
  plate twice; each drawing's PDF is shown as exported.

Every tool call is an evidence frame, so is each check, and the plate
drawing's seven build steps are shown as the generator fills the sheet. Every call is also written to
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

from tests.live import recorder
from tests.live.evidence import evidence, pdf_page, starting
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
    "1. sketch on Top: 100 x 50 outline from the origin, four Ø5.5 circles",
    "   (one Ø, the rest equal), each located from two edges; extrude 10 mm",
    "2. AISI 1020, then verify_model: 49049.7 mm³, 0.3875 kg, 1 feature",
    "3. plate drawing: A3, model dimensions, centre marks, notes, title block;",
    "   GD&T: datums A, B, C and position Ø0.2 (M) on the holes",
    "4. assembly: the plate twice; Front and Right coincident, Top planes 60",
    "   mm apart, brought down to 20 (a 10 mm gap); verify_model: 2 parts,",
    "   3 mates, no overlap",
    "5. assembly drawing with a BOM (the plate, QTY 2) and the same GD&T",
]

_WIDTH_MM, _DEPTH_MM, _THICKNESS_MM = 100.0, 50.0, 10.0
_HOLE_DIAMETER_MM = 5.5
_EDGE_MM = 10.0
_HOLES_MM3 = 4 * math.pi * (_HOLE_DIAMETER_MM / 2) ** 2 * _THICKNESS_MM
_PLATE_MM3 = _WIDTH_MM * _DEPTH_MM * _THICKNESS_MM - _HOLES_MM3
#: AISI 1020 is 7900 kg/m³ in the SolidWorks material library.
_PLATE_KG = _PLATE_MM3 * 1e-9 * 7900.0
_GAP_MM = 10.0
#: The Top planes' distance mate starts wide and is stepped down to its
#: value, one frame a step, so the GIF shows the top plate coming into place.
_MATE_FROM_MM = 60.0
_MATE_STEPS_MM = [50.0, 40.0, 30.0, 20.0]
#: While recording, 4 mm steps with no hold or caption each: a short slide.
_MATE_STEPS_RECORDED_MM = [float(mm) for mm in range(56, 19, -4)]
#: swStandardViews_e (swconst.tlb, SW 2026): where the camera looks.
_TOP_VIEW, _ISO_VIEW = 5, 7
#: SolidWorks' name for the first distance mate's dimension.
_MATE_DIMENSION = "D1@Distance1"

#: Added after the generator's own lines (material, units, projection, burrs).
PLATE_NOTES = [
    "4 X Ø5.5 THRU, M5 CLEARANCE",
    "GENERAL TOLERANCES ISO 2768-m",
    "QTY 2 PER ASSEMBLY PS-02",
]
ASSEMBLY_NOTES = [
    "2 X DEMO PLATE PS-01, AISI 1020",
    f"PLATES SPACED {_GAP_MM:g} MM APART",
]


class _Session:
    """Calls the registered MCP tools and keeps a transcript of each call.

    Every call is also an evidence frame: SolidWorks as the call left it,
    captioned with the call and its reply's message.
    """

    def __init__(self, tools: dict[str, Any], adapter: Any = None) -> None:
        self.tools = tools
        self.adapter = adapter
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, name: str, args: dict[str, Any] | None = None, quick: bool = False
    ) -> Any:
        """Call one tool, record it, and require success.

        ``quick`` shows the call in a recording only (see ``evidence``).
        """
        tool = self.tools[name]
        shown = f"{name}({json.dumps(args or {}, ensure_ascii=False)})"
        if not quick:
            starting(f"tool call {len(self.calls) + 1}: {name}", shown)
        result = await (tool() if args is None else tool(args))
        status = result.get("status") if isinstance(result, dict) else None
        self.calls.append({"tool": name, "args": args or {}, "status": status})
        assert status == "success", f"{name}: {result.get('message')}"
        evidence(
            f"tool call {len(self.calls)}: {name}",
            {"message": result.get("message")},
            call=shown,
            quick=quick,
        )
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
    _look(call.adapter, _TOP_VIEW)  # the outline fills the screen while sketching

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
        if not dims[2:]:
            await dimension(circle, None, "diameter", _HOLE_DIAMETER_MM, f"{circle} Ø")
            first = circle
        else:
            # One diameter drives all four holes: no repeated Ø5.5.
            await call(
                "add_sketch_constraint",
                {"entity1": first, "entity2": circle, "relation_type": "equal"},
            )
            dims.append(f"{circle} Ø equal to {first}")
        await dimension(edges[side], circle, "linear", e, f"{circle} to {side} edge")
        await dimension(edges[end], circle, "linear", e, f"{circle} to {end} edge")
    await call("exit_sketch")
    return sketch, dims


async def _hole_dimension(call: _Session, sketch: str) -> str:
    """The hole's Ø dimension, found by value: the position tolerance goes on it."""
    listed = await call("list_model_dimensions", {"feature_name": sketch})
    return next(
        d["full_name"]
        for d in listed["data"]
        if abs(float(d["value"]) - _HOLE_DIAMETER_MM) < 1e-6
    )


def _show_pdf(path: Path, label: str) -> None:
    """A frame of the exported PDF's page, as anyone opening the file sees it."""
    assert path.is_file(), path
    evidence(
        label, {"pdf": path.name, "bytes": path.stat().st_size}, picture=pdf_page(path)
    )


def _look(adapter: Any, view: int) -> None:
    """Point the camera for the demo: a standard view, zoomed to fit.

    Staging for the recording, not a tool call: an agent does not need it.
    """
    model = adapter.currentModel
    adapter._attempt(lambda: model.ShowNamedView2("", view), default=None)
    adapter._zoom_to_fit(model)


def _role(package: dict[str, Any], role: str) -> str:
    """The drawing view the generator gave ``role`` (front, plan, side, iso)."""
    views = package["data"]["views"]
    return next(name for name, v in views.items() if v.get("role") == role)


def _part_box_mm(
    adapter: Any, view: str, scale: float, size_mm: tuple[float, float]
) -> tuple[float, float, float, float]:
    """Where a view draws the part on the sheet, in mm.

    The view's outline is centred on the part; the part is ``size_mm`` (its
    width and height in that view) times the sheet scale.
    """
    from solidworks_mcp.adapters.solidworks.io import (
        _resolve_drawing_view,
        _sw_type_info,
    )

    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    x0, y0, x1, y1 = _resolve_drawing_view(adapter, drawing, view).GetOutline()[:4]
    cx, cy = (x0 + x1) * 500.0, (y0 + y1) * 500.0
    w, h = size_mm[0] * scale / 2.0, size_mm[1] * scale / 2.0
    return (cx - w, cy - h, cx + w, cy + h)


async def _gdt(
    call: _Session,
    adapter: Any,
    package: dict[str, Any],
    hole_dim: str,
    height_mm: float = _THICKNESS_MM,
) -> dict[str, Any]:
    """Datums A (bottom face), B (left end), C (near side) and the holes' position.

    A is the face the plate sits on, seen edge-on as the front view's bottom
    line; B the x = 0 end, the front view's left line; C the edge the holes
    are dimensioned from in depth, the side view's left line. On the stack
    (``height_mm`` tall) they go on the bottom plate. The position tolerance
    goes on the Ø5.5 dimension: every hole within Ø0.2 of true position at
    maximum material, to A, B and C.
    """
    num, den = (float(v) for v in str(package["data"]["scale"]).split(":"))
    scale = num / den
    front = _part_box_mm(
        adapter, _role(package, "front"), scale, (_WIDTH_MM, height_mm)
    )
    side = _part_box_mm(adapter, _role(package, "side"), scale, (_DEPTH_MM, height_mm))
    # Halfway up the bottom plate, on the sheet.
    mid_front = front[1] + _THICKNESS_MM * scale / 2.0
    mid_side = side[1] + _THICKNESS_MM * scale / 2.0
    tags = {
        "A": ((front[0] + 30.0, front[1]), (front[0] + 30.0, front[1] - 12.0)),
        "B": ((front[0], mid_front), (front[0] - 14.0, mid_front)),
        "C": ((side[0], mid_side), (side[0] - 14.0, mid_side)),
    }
    placed = {}
    for label, ((ax, ay), (tx, ty)) in tags.items():
        await call(
            "add_datum_tag",
            {
                "label": label,
                "attach_x_mm": round(ax, 2),
                "attach_y_mm": round(ay, 2),
                "x_mm": round(tx, 2),
                "y_mm": round(ty, 2),
            },
        )
        placed[label] = [round(ax, 1), round(ay, 1)]
    frame = await call(
        "add_gtol",
        {
            "characteristic": "position",
            "tolerance": 0.2,
            "diameter_zone": True,
            "material_condition": "mmc",
            "datums": ["A", "B", "C"],
            "dimension_view": _role(package, "plan"),
            "dimension_name": hole_dim,
        },
    )
    return {"datum_tags_on_mm": placed, "position_frame": frame["data"]}


async def _gdt_and_save(
    call: _Session,
    adapter: Any,
    package: dict[str, Any],
    hole_dim: str,
    out: Path,
    number: str = "PS-01",
    step: str = "step 3",
    height_mm: float = _THICKNESS_MM,
) -> None:
    """Add the GD&T to a drawing, then save it and show its exported PDF."""
    gdt = await _gdt(call, adapter, package, hole_dim, height_mm)
    evidence(
        f"{step}: GD&T: datums A, B, C and the holes' position tolerance",
        gdt,
        call=(
            'add_gtol({"characteristic": "position", "tolerance": 0.2, '
            '"diameter_zone": true, "material_condition": "mmc", '
            f'"datums": ["A", "B", "C"], "dimension_name": "{hole_dim}"}})'
        ),
    )
    assert (await adapter.save_file(str(out / f"{number}.SLDDRW"))).is_success
    assert (await adapter.export_file(str(out / f"{number}.pdf"), "pdf")).is_success
    _show_pdf(out / f"{number}.pdf", f"{step}: {number}.pdf, as exported")


async def _stack_and_draw(
    call: _Session, adapter: Any, plate: str, folder: Path, out: Path, hole_dim: str
) -> list[str]:
    """Stack two plates 10 mm apart, check it, and draw it with a BOM.

    Returns:
        list[str]: The files written.
    """
    # Two plates, 10 mm apart.
    assert (await adapter.create_assembly()).is_success
    await call("insert_component", {"file_path": plate})
    await call("insert_component", {"file_path": plate, "y": 40.0})
    a, b = (await call("list_components"))["components"]
    mates = []
    for entity, mate_type, distance in (
        ("Front Plane", "coincident", 0.0),
        ("Right Plane", "coincident", 0.0),
        ("Top Plane", "distance", _MATE_FROM_MM),
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
    # The top plate comes down into place: each step is a frame.
    recording = recorder.asked()
    steps = _MATE_STEPS_RECORDED_MM if recording else _MATE_STEPS_MM
    evidence(
        f"step 4: the top plate comes down, Top planes {_MATE_FROM_MM:g} -> "
        f"{steps[-1]:g} mm",
        {"set_dimension": f"{_MATE_DIMENSION}, {len(steps)} steps"},
    )
    for apart in steps:
        await call(
            "set_dimension",
            {"name": _MATE_DIMENSION, "value": apart},
            quick=recording and apart != steps[-1],
        )
    assert steps[-1] == _GAP_MM + _THICKNESS_MM
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
    # An assembly has no material of its own; the title block shows this.
    await call("set_custom_property", {"name": "Material", "value": "AISI 1020"})
    assembly = str(folder / "Plate Stack.SLDASM")
    assert (await adapter.save_file(assembly)).is_success

    # The assembly drawing: the isometric, with the BOM above it.
    args = {
        "model_path": assembly,
        "output_dir": str(out),
        "title": "Plate Stack",
        "drawing_number": "PS-02",
        "author": "solidworks-mcp",
        "notes": ASSEMBLY_NOTES,
        "include_bom": True,
    }
    with pytest.MonkeyPatch.context() as watching:
        _show_each_build_step(adapter, watching)
        package = await call("generate_drawing_package", args)
    cells = _bom_cells(adapter)
    evidence(
        "step 5: the assembly drawing; the BOM lists the plate twice",
        {
            "table_box_mm": package["data"]["bom"]["table_box_mm"],
            "isometric_scale": package["data"]["isometric_scale"],
            "overlaps_after": package["data"]["overlap_check"]["overlaps_after"],
            "title_block_reads": package["data"]["format_links"],
            "cells": cells,
        },
        call=f"generate_drawing_package({args})",
    )
    stack_mm = 2 * _THICKNESS_MM + _GAP_MM
    await _gdt_and_save(
        call, adapter, package, hole_dim, out, "PS-02", "step 5", stack_mm
    )
    plate_rows = [row for row in cells if any("Demo Plate" in c for c in row)]
    assert plate_rows and plate_rows[0][-1].strip() == "2", cells
    return [assembly, str(out / "PS-02.SLDDRW"), str(out / "PS-02.pdf")]


@pytest.mark.asyncio
@pytest.mark.timeout(1800)  # paced for a demo: a hold on every frame
async def test_plate_stack_from_prompt_to_drawing(scratch, tmp_path, monkeypatch):
    """A fully dimensioned plate and its drawing; two stacked 10 mm apart, with a BOM."""
    adapter = scratch.adapter
    call = _Session(await _tools(adapter), adapter)
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
    relations = sum("equal to" in d for d in dims)
    evidence(
        f"step 1: the sketch, {len(dims) - relations} dimensions and "
        f"{relations} equal relations",
        {
            "definition_state": definition.get("definition_state"),
            "dimensions": "; ".join(dims),
        },
        call=f'check_sketch_fully_defined({{"sketch_name": "{sketch}"}})',
    )
    args = {"sketch_name": sketch, "depth": _THICKNESS_MM}
    boss = await call("create_extrusion", args)
    _look(adapter, _ISO_VIEW)
    evidence(
        f"step 1: extrude 10 mm (expect +{_PLATE_MM3:.1f} mm³, holes and all)",
        boss["measured_change"],
        call=f"create_extrusion({args})",
    )
    assert boss["measured_change"]["volume_delta_mm3"] == pytest.approx(
        _PLATE_MM3, rel=1e-4
    )
    hole_dim = await _hole_dimension(call, sketch)

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
    evidence(
        "step 3: the plate drawing: dimensions, centre marks, AISI 1020",
        {
            "dimensions_on_sheet": detail["data"]["overlap_check"]["dimensions"],
            "overlaps_after": detail["data"]["overlap_check"]["overlaps_after"],
            "centre_marks_added": marks.get("center_marks_added"),
            "hidden_lines_visible": detail["data"]["hidden_lines_visible"],
            "title_block": [t for t in shown if len(t.strip()) > 1][-6:],
        },
        call=f'auto_center_marks({{"view_name": "{plan_view}"}})',
    )
    assert detail["data"]["overlap_check"]["overlaps_after"] == 0
    assert "AISI 1020" in shown

    await _gdt_and_save(call, adapter, detail, hole_dim, out)
    scratch.written_files += await _stack_and_draw(
        call, adapter, plate, tmp_path, out, hole_dim
    )

    evidence(
        f"{len(call.calls)} tool calls from prompt to drawings, all successful",
        " -> ".join(c["tool"] for c in call.calls),
    )
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        transcript = Path(capture_dir) / "plate_stack_calls.json"
        # Paths relative to the test's folder: no local user paths published.
        shown = json.dumps(
            {"prompt": PROMPT, "plan": PLAN, "calls": call.calls},
            indent=2,
            ensure_ascii=False,
        ).replace(json.dumps(str(tmp_path) + os.sep)[1:-1], "")
        transcript.write_text(shown, encoding="utf-8")
