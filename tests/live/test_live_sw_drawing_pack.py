"""The drawing pack (queue item 12), checked on real SolidWorks.

One demo, on the drawing ``generate_drawing_package`` makes of a 60 x 40 x
10 mm plate with a Ø6 hole through its middle:

1. ``check_drawing`` on the finished package;
2. ``update_title_block``: revision B;
3. ``update_sheet_format``: A3 to A2, the views kept (the room on the right
   takes the new views);
4. ``create_section_view`` through the hole, in the plan view;
5. ``create_detail_view`` of the bore in that section, at 3:1;
6. ``add_dimension``: the plate's 60 mm width, and the hole's Ø6;
7. ``auto_dimension_view`` on the section, then ``arrange_dimensions`` to
   space what it added;
8. on purpose: a section line that misses the view is refused;
9. ``check_drawing`` again.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_drawing_pack.py::test_a_drawing_finished_by_hand

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live.evidence import evidence, note, starting
from tests.live.test_live_sw_beta_tools import _sketch
from tests.live.test_live_sw_readme_demo import _role, _tools

pytestmark = pytest.mark.asyncio


def _views(report: dict[str, Any]) -> dict[str, Any]:
    """The check's views by name: outline, dimensions, type."""
    return {v["name"]: v for v in report["report"]["views"]}


def _centre(box: list[float]) -> tuple[float, float]:
    """The middle of an outline (the plate is centred in each view)."""
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


@pytest.mark.timeout(1200)  # paced for a demo: a hold on every step
async def test_a_drawing_finished_by_hand(scratch: Any, tmp_path: Any) -> None:
    """Section, detail, dimensions, title block and format on a package drawing."""
    adapter = scratch.adapter
    tools = await _tools(adapter)

    async def call(label: str, name: str, args: dict[str, Any] | None = None) -> Any:
        text = f"{name}({args or ''})"
        starting(label, text)
        result = await (tools[name](args) if args is not None else tools[name]())
        evidence(label, _caption(result), call=text)
        return result

    note(
        "Prompt",
        "Finish the plate's drawing: revision B on A2, a section through the "
        "hole, a 3:1 detail of the bore, the width and the hole dimensioned, "
        "then check it.",
        seconds=4.0,
    )
    assert (await tools["create_part"]({"name": "pack_plate"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -30, "y1": -20, "x2": 30, "y2": 20})
    assert (await tools["create_extrusion"]({"depth": 10}))["status"] == "success"
    hole = await tools["create_hole"](
        {
            "face_point": [0, 10, 0],
            "hole_type": "simple",
            "size": "6",
            "end_condition": "blind",
            "depth": 10,
        }
    )
    assert hole["status"] == "success", hole
    plate = str(tmp_path / "Pack Plate.SLDPRT")
    assert (await adapter.save_file(plate)).is_success
    scratch.written_files.append(plate)
    out = tmp_path / "drawings"
    package = await tools["generate_drawing_package"](
        {
            "model_path": plate,
            "output_dir": str(out),
            "title": "Pack Plate",
            "drawing_number": "DP-01",
            "author": "solidworks-mcp",
        }
    )
    assert package["status"] == "success", package
    scratch.written_files += [str(out / "DP-01.SLDDRW"), str(out / "DP-01.pdf")]
    top, bottom = (float(n) for n in package["data"]["scale"].split(":"))
    scale = top / bottom
    front, plan = _role(package, "front"), _role(package, "plan")

    first = await call("1. the package, checked", "check_drawing")
    revised = await call("2. revision B", "update_title_block", {"revision": "B"})
    a2 = await call(
        "3. A3 to A2, every view kept",
        "update_sheet_format",
        {"sheet_format": "a2 - iso"},
    )
    adapter._zoom_to_fit(adapter.currentModel)
    views = _views(await tools["check_drawing"]())

    px, py = _centre(views[plan]["outline_mm"])
    box = views[plan]["outline_mm"]
    section = await call(
        "4. a section through the hole",
        "create_section_view",
        {
            "view": plan,
            "line_start": [box[0] - 5, py],
            "line_end": [box[2] + 5, py],
            "position": [500, 300],
        },
    )
    sx, sy = _centre(section["view"]["outline_mm"])
    detail = await call(
        "5. a 3:1 detail of the bore, in the section",
        "create_detail_view",
        {
            "view": section["view"]["name"],
            "center": [sx, sy],
            "radius": 12,
            "position": [500, 120],
            "scale": "3:1",
        },
    )
    fx, fy = _centre(views[front]["outline_mm"])
    left, right = fx - 30 * scale, fx + 30 * scale
    width = await call(
        "6. the width, edge to edge",
        "add_dimension",
        {
            "dimension_type": "horizontal",
            "entity1_point": [left, fy],
            "entity2_point": [right, fy],
            "position": [fx, views[front]["outline_mm"][3] + 8],
        },
    )
    bore = await call(
        "6. the hole's diameter",
        "add_dimension",
        {
            "dimension_type": "diameter",
            "entity1_point": [px + 3 * scale, py],
            "position": [px + 15, py + 15],
        },
    )
    section_name = section["view"]["name"]
    auto = await call(
        "7. auto-dimension the section", "auto_dimension_view", {"view": section_name}
    )
    arranged = await call(
        "7. ... and space its dimensions out",
        "arrange_dimensions",
        {"view_name": section_name},
    )
    note(
        "Next, on purpose: a section line that misses the view",
        "The line runs along the bottom of the sheet, far from the plan view. "
        "The tool should refuse it and change nothing. The error that follows "
        "is the check passing.",
        seconds=5.0,
    )
    missed = await call(
        "8. refused, as intended",
        "create_section_view",
        {
            "view": plan,
            "line_start": [10, 5],
            "line_end": [60, 5],
            "position": [500, 300],
        },
    )
    final = await call("9. the finished drawing, checked", "check_drawing")
    adapter._zoom_to_fit(adapter.currentModel)
    evidence(
        "The drawing: A2, revision B, a section, a detail, checked",
        {
            "views": final.get("views"),
            "width_mm": width.get("dimension", {}).get("value"),
            "hole_mm": bore.get("dimension", {}).get("value"),
            "passed": final.get("passed"),
            "findings": [f["rule"] for f in final.get("findings", [])],
        },
        hold=5.0,
    )

    assert first["passed"] is True, first
    assert revised["status"] == "success", revised
    assert a2["sheet"]["paper_size"] == "a2", a2
    assert section["status"] == "success", section
    assert detail["status"] == "success", detail
    assert width["dimension"]["value"] == pytest.approx(60, abs=0.01), width
    assert bore["dimension"]["value"] == pytest.approx(6, abs=0.01), bore
    assert auto["status"] == "success", auto
    assert arranged["status"] == "success", arranged
    assert (missed["status"], missed["error_type"]) == ("error", "invalid_input")
    assert final["passed"] is True, final
    assert final["report"]["title_block"]["revision"] == "B"


def _caption(result: dict[str, Any]) -> Any:
    """A tool reply cut down for a GIF caption."""
    if result.get("status") != "success":
        return {"status": result.get("status"), "message": result.get("message")}
    keep = {k: result[k] for k in ("message", "passed", "findings") if k in result}
    for key in ("view", "dimension", "sheet", "fields", "data"):
        if key in result:
            keep[key] = result[key]
    return keep
