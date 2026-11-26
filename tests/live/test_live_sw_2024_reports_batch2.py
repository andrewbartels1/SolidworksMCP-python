"""The SolidWorks 2024 reports #265-#275, each by the reporter's own steps.

Run on SolidWorks 2026 they show which reports are about our code (they fail
here too) and which about 2024 (they pass here); kept afterwards as the
regression for each fix. One test per report:

- #265 equations: set, list and delete an equation.
- #266 set_dimension: the first change with ``configurations: "this"`` in a
  non-default configuration stays in that configuration.
- #268 check_sketch_fully_defined: an under-defined rectangle reads
  ``under_defined``, open and after exit_sketch.
- #270 create_extrusion with no sketch_name after a named sketch.
- #271 add_mate: concentric with a Hole Wizard hole's wall.
- #272 sketch_linear_pattern along -Y.
- #273 create_section_view: the view lands at ``position``.
- #274 add_cosmetic_thread: SolidWorks keeps M8x1.25, not M8x1.0.
- #275 add_note: the text starts at ``position_x``.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        tests/live/test_live_sw_2024_reports_batch2.py::test_equations

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool, registered against ``adapter``: name -> function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools import register_tools

    mcp = FastMCP("sw2024-batch2-live")
    await register_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


async def _box(
    tools: dict[str, Any], name: str, x: float, z: float, height: float
) -> None:
    """A part ``name``: an x by z rectangle on Top, centred, extruded ``height``."""
    await _ok(await tools["create_part"]({"name": name}))
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(
        await tools["add_rectangle"](
            {"x1": -x / 2, "y1": -z / 2, "x2": x / 2, "y2": z / 2}
        )
    )
    await _ok(await tools["exit_sketch"]())
    await _ok(
        await tools["create_extrusion"](
            {"sketch_name": made["sketch"]["name"], "depth": height}
        )
    )


async def _saved(scratch: Any, path: Path) -> str:
    saved = await scratch.adapter.save_file(str(path))
    assert saved.is_success, saved.error
    scratch.written_files.append(str(path))
    return str(path)


async def test_equations(scratch: Any) -> None:
    """#265: Member not found on 2024; on 2026 all three work."""
    tools = await _tools(scratch.adapter)
    await _box(tools, "eq_block", 60, 40, 20)

    made = await tools["set_equation"]({"name": "Height", "expression": "18mm"})
    listed = await tools["list_equations"]()
    gone = await tools["delete_equation"]({"name": "Height"})
    evidence(
        "#265: set, list and delete an equation",
        {
            "set": made.get("status"),
            "listed": listed.get("equations") or listed.get("data"),
            "delete": gone.get("status"),
        },
    )
    for reply in (made, listed, gone):
        assert reply["status"] == "success", reply


async def test_a_first_this_change_stays_in_its_configuration(scratch: Any) -> None:
    """#266: the first "this" change went to every configuration."""
    tools = await _tools(scratch.adapter)
    await _box(tools, "cfg_block", 40, 20, 10)
    await _ok(await tools["create_configuration"]({"name": "Tall"}))
    await _ok(await tools["activate_configuration"]({"name": "Tall"}))

    changed = await _ok(
        await tools["set_dimension"]({"name": "D1@Boss-Extrude1", "value": 25})
    )
    tall = await tools["verify_model"]({"bounding_box_mm": [40, 25, 20]})
    await _ok(await tools["activate_configuration"]({"name": "Default"}))
    default = await tools["verify_model"]({"bounding_box_mm": [40, 10, 20]})
    evidence(
        "#266: D1 = 25 in Tall only",
        {
            "reply": changed.get("dimension") or changed.get("data"),
            "tall": tall["verdict"],
            "default": default["verdict"],
            "default_box": default.get("measured", {}).get("bounding_box_mm"),
        },
    )
    assert tall["verdict"] == "pass", tall
    assert default["verdict"] == "pass", default


async def test_an_under_defined_sketch_reads_under_defined(scratch: Any) -> None:
    """#268: the state was always 'unknown'."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "defined"}))
    await _ok(await tools["create_sketch"]({"plane": "Front", "sketch_name": "SK_Def"}))
    lines = []
    for a, b in (
        ((0, 0), (40, 0)),
        ((40, 0), (40, 20)),
        ((40, 20), (0, 20)),
        ((0, 20), (0, 0)),
    ):
        made = await _ok(
            await tools["add_line"]({"x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1]})
        )
        lines.append(made.get("entity_id") or made.get("line", {}).get("id"))
    open_state = await _ok(await tools["check_sketch_fully_defined"]({}))
    await _ok(await tools["exit_sketch"]())
    closed_state = await _ok(
        await tools["check_sketch_fully_defined"]({"sketch_name": "SK_Def"})
    )
    evidence(
        "#268: four free lines, open and after exit",
        {
            "lines": lines,
            "open": open_state["sketch"],
            "closed": closed_state["sketch"],
        },
    )
    assert open_state["sketch"]["definition_state"] == "under_defined"
    assert closed_state["sketch"]["definition_state"] == "under_defined"


async def test_an_extrusion_after_a_named_sketch(scratch: Any) -> None:
    """#270: create_extrusion without sketch_name after create_sketch named it."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "named"}))
    await _ok(await tools["create_sketch"]({"plane": "Top", "sketch_name": "SK_Base"}))
    await _ok(await tools["add_rectangle"]({"x1": -30, "y1": -20, "x2": 30, "y2": 20}))
    exited = await _ok(await tools["exit_sketch"]())
    boss = await tools["create_extrusion"]({"depth": 20})
    checked = await tools["verify_model"]({"volume_mm3": 48000})
    evidence(
        "#270: extruded SK_Base without naming it",
        {
            "exit": exited.get("sketch"),
            "boss": boss.get("status"),
            "verdict": checked["verdict"],
        },
    )
    assert boss["status"] == "success", boss
    assert checked["verdict"] == "pass", checked


async def test_a_pattern_along_minus_y(scratch: Any) -> None:
    """#272: a negative direction component failed."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "pattern"}))
    await _ok(await tools["create_sketch"]({"plane": "Front"}))
    circle = await _ok(
        await tools["add_circle"]({"center_x": 30, "center_y": 0, "radius": 2})
    )
    seed = circle.get("entity_id") or circle.get("circle", {}).get("id")
    down = await tools["sketch_linear_pattern"](
        {
            "entities": [seed],
            "direction_x": 0,
            "direction_y": -1,
            "spacing": 8,
            "count": 3,
        }
    )
    await _ok(await tools["exit_sketch"]())
    boss = await _ok(await tools["create_extrusion"]({"depth": 5}))
    checked = await tools["verify_model"]({"bounding_box_mm": [4, 20, 5]})
    evidence(
        "#272: three circles 8 mm apart going down",
        {"pattern": down.get("status"), "boss": boss.get("status"), "verdict": checked},
    )
    assert down["status"] == "success", down
    assert checked["verdict"] == "pass", checked


async def _drilled_block(tools: dict[str, Any]) -> dict[str, Any]:
    """The reporter's block: 60 x 40 x 20, a Ø6 Hole Wizard hole at (-20, -12)."""
    await _box(tools, "TC_Features", 60, 40, 20)
    return await _ok(
        await tools["create_hole"](
            {"face_point": [-20, 20, -12], "hole_type": "simple", "size": "6"}
        )
    )


async def test_a_pin_concentric_with_a_hole_wizard_hole(
    scratch: Any, tmp_path: Path
) -> None:
    """#271: face_b on the hole's wall was not found."""
    tools = await _tools(scratch.adapter)
    hole = await _drilled_block(tools)
    block = await _saved(scratch, tmp_path / "TC_Features.SLDPRT")
    measured = await tools["measure_entities"](
        {"entities": ["face:-0.017,0.01,-0.012"]}
    )
    await _ok(await tools["create_part"]({"name": "pin6"}))
    made = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_circle"]({"center_x": 0, "center_y": 0, "radius": 3}))
    await _ok(await tools["exit_sketch"]())
    await _ok(
        await tools["create_extrusion"](
            {"sketch_name": made["sketch"]["name"], "depth": 30}
        )
    )
    pin = await _saved(scratch, tmp_path / "pin6.SLDPRT")
    await _ok(await tools["create_assembly"]({"name": "hole_mate"}))
    await _ok(await tools["insert_component"]({"file_path": block}))
    await _ok(await tools["insert_component"]({"file_path": pin, "x": 100}))
    names = (await _ok(await tools["list_components"]()))["components"]
    block_name = next(n for n in names if "TC_Features" in n)
    pin_name = next(n for n in names if "pin6" in n)

    mate = await tools["add_mate"](
        {
            "component_a": pin_name,
            "component_b": block_name,
            "mate_type": "concentric",
            "alignment": "closest",
            "face_a": [3, 15, 0],
            "face_b": [-17, 10, -12],
        }
    )
    evidence(
        "#271: the pin concentric with the Hole Wizard hole",
        {
            "hole": hole.get("hole"),
            "measure": measured.get("measurements") or measured,
            "mate": mate,
        },
    )
    assert mate["status"] == "success", mate


def _hole_cylinders(adapter: Any) -> list[dict[str, Any]]:
    """Every cylindrical face of the part: axis point and radius, mm."""
    from solidworks_mcp.adapters import sw_type_info
    from solidworks_mcp.adapters.solidworks.com_utils import as_list

    def read() -> list[dict[str, Any]]:
        model = sw_type_info.flagged(adapter.currentModel, "IPartDoc")
        out = []
        for body in as_list(model.GetBodies2(0, True)):
            body = sw_type_info.flagged(body, "IBody2")
            for face in as_list(body.GetFaces()):
                face = sw_type_info.flagged(face, "IFace2")
                surface = sw_type_info.flagged(face.GetSurface(), "ISurface")
                if not surface.IsCylinder():
                    continue
                p = [float(v) * 1000 for v in as_list(surface.CylinderParams)]
                out.append(
                    {
                        "axis_point_mm": [round(v, 4) for v in p[:3]],
                        "axis_dir": [round(v, 4) for v in p[3:6]],
                        "radius_mm": round(p[6], 4),
                    }
                )
        return out

    result = adapter._handle_com_operation("probe_hole_cylinders", read)
    assert result.is_success, result.error
    return list(result.data)


async def test_a_hole_wizard_hole_sits_at_its_point(scratch: Any) -> None:
    """A Ø6 hole asked for at (-20, 20, -12) has its axis at x=-20, z=-12."""
    tools = await _tools(scratch.adapter)
    hole = await _drilled_block(tools)
    cylinders = _hole_cylinders(scratch.adapter)
    evidence("hole at (-20, 20, -12), Ø6", {"hole": hole, "cylinders": cylinders})
    assert len(cylinders) == 1, cylinders
    (cylinder,) = cylinders
    x, _y, z = cylinder["axis_point_mm"]
    assert abs(x - -20) < 1e-3 and abs(z - -12) < 1e-3, cylinder


async def test_a_section_view_lands_at_its_position(
    scratch: Any, tmp_path: Path
) -> None:
    """#273: the section view sat on its parent view."""
    from solidworks_mcp.adapters.solidworks.io import (
        _resolve_drawing_view,
        _sw_type_info,
        _view_names,
    )

    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _box(tools, "section_block", 60, 40, 20)
    part = await _saved(scratch, tmp_path / "section_block.SLDPRT")
    await _ok(await tools["create_drawing"]({"name": "section"}))
    await _ok(await tools["create_technical_drawing"]({"model_file": part}))
    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    outlines = {
        n: [
            round(v * 1000, 2)
            for v in _resolve_drawing_view(adapter, drawing, n).GetOutline()
        ]
        for n in _view_names(adapter, drawing)
    }
    top = outlines["Drawing View2"]
    mid_y = (top[1] + top[3]) / 2
    section = await tools["create_section_view"](
        {
            "view": "Drawing View2",
            "line_start": [top[0] - 10, mid_y],
            "line_end": [top[2] + 10, mid_y],
            # Right of the parent, at its height, as the reporter did; the
            # default sheet here is Letter (279.4 x 215.9), not A3.
            "position": [200, mid_y],
        }
    )
    placed = section.get("view") or {}
    outline = placed.get("outline_mm")
    evidence(
        "#273: a section view asked for at x = 200",
        {"views": outlines, "section": section},
    )
    assert section["status"] == "success", section
    assert placed.get("at_position") is True, placed
    assert outline and abs((outline[0] + outline[2]) / 2 - 200) < 1, outline


async def test_a_cosmetic_thread_keeps_its_pitch(scratch: Any) -> None:
    """#274: M8x1.25 was asked for; the drawing callout read M8x1.0."""
    from solidworks_mcp.adapters.solidworks.feature_walk import walk_feature_tree
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _drilled_block(tools)
    thread = await tools["add_cosmetic_thread"](
        {
            "edge_point": [-17, 20, -12],
            "size": "M8x1.25",
            "end_type": "blind",
            "depth": 10,
        }
    )
    stored: dict[str, Any] = {}
    for item in walk_feature_tree(adapter, adapter.currentModel):
        for sub in _sub_features(adapter, item.feature):
            if "Thread" in str(sub.GetTypeName2()):
                data = _sw_type_info.flagged(
                    sub.GetDefinition(), "ICosmeticThreadFeatureData"
                )
                for prop in (
                    "Size",
                    "ThreadCallout",
                    "Standard",
                    "StandardType",
                    "Diameter",
                ):
                    stored[prop] = adapter._attempt(
                        lambda p=prop, d=data: getattr(d, p), "?"
                    )
    evidence("#274: what SolidWorks stored", {"reply": thread, "stored": stored})
    assert thread["status"] == "success", thread
    # ISO names the coarse M8 (pitch 1.25) "M8"; "M8x1.0" is the fine pitch.
    assert stored.get("Size") == "M8", stored
    assert stored.get("ThreadCallout") == "M8", stored
    assert thread["thread"]["callout"] == "M8", thread


def _sub_features(adapter: Any, feature: Any) -> list[Any]:
    """``feature`` and its sub-features (a cosmetic thread sits under its hole)."""
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info

    found = [_sw_type_info.flagged(feature, "IFeature")]
    sub = adapter._attempt(lambda: found[0].GetFirstSubFeature(), None)
    while sub is not None:
        sub = _sw_type_info.flagged(sub, "IFeature")
        found.append(sub)
        sub = adapter._attempt(lambda s=sub: s.GetNextSubFeature(), None)
    return found


async def test_a_note_starts_at_its_position(scratch: Any) -> None:
    """#275: the note was centred on position_x and ran off the sheet."""
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _ok(await tools["create_drawing"]({"name": "notes"}))
    note = await tools["add_note"](
        {
            "text": "TOOL CHECK - TEST DRAWING",
            "position_x": 30,
            "position_y": 40,
            "font_size": 10,
        }
    )
    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    sheet_view = _sw_type_info.flagged(drawing.GetFirstView(), "IView")
    last = None
    found = sheet_view.GetFirstNote()
    while found is not None:
        last = _sw_type_info.flagged(found, "INote")
        found = last.GetNext()
    extent = [round(v * 1000, 1) for v in last.GetExtent()] if last else None
    evidence(
        "#275: a note asked for at x = 30 mm", {"reply": note, "extent_mm": extent}
    )
    assert note["status"] == "success", note
    assert extent and abs(extent[0] - 30) < 1.0, extent


async def test_save_as_a_copy_keeps_the_original(scratch: Any, tmp_path: Path) -> None:
    """#276: as_copy writes a copy and the original stays the open document."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _box(tools, "TC_Original", 40, 20, 10)
    original = await _saved(scratch, tmp_path / "TC_Original.SLDPRT")
    copy = str(tmp_path / "TC_Original_copy.SLDPRT")
    scratch.written_files.append(copy)

    copied = await tools["save_as"]({"file_path": copy, "as_copy": True})
    evidence("#276: save_as with as_copy", copied)
    assert copied["status"] == "success", copied
    assert Path(copy).exists()
    assert copied["kept_original"] is True, copied
    assert Path(copied["current_path"]).name.lower() == Path(original).name.lower()


async def test_a_line_tied_to_the_origin_is_fully_defined(scratch: Any) -> None:
    """#269: a sketch could only be fully defined with Fix."""
    tools = await _tools(scratch.adapter)
    await _ok(await tools["create_part"]({"name": "tied"}))
    await _ok(await tools["create_sketch"]({"plane": "Front"}))
    line = await _ok(await tools["add_line"]({"x1": 0, "y1": 0, "x2": 40, "y2": 0}))
    line_id = line.get("entity_id") or line.get("line", {}).get("id") or "Line_1"
    await _ok(
        await tools["add_sketch_constraint"](
            {"entity1": line_id, "relation_type": "horizontal"}
        )
    )
    await _ok(await tools["add_sketch_dimension"]({"entity1": line_id, "value": 40}))
    before = await _ok(await tools["check_sketch_fully_defined"]({}))
    tied = await tools["add_sketch_constraint"](
        {
            "entity1": f"{line_id}.start",
            "entity2": "origin",
            "relation_type": "coincident",
        }
    )
    after = await _ok(await tools["check_sketch_fully_defined"]({}))
    evidence(
        "#269: a line's start coincident with the origin",
        {
            "before": before["sketch"]["definition_state"],
            "tie": tied.get("status"),
            "after": after["sketch"]["definition_state"],
        },
    )
    assert tied["status"] == "success", tied
    assert before["sketch"]["definition_state"] == "under_defined"
    assert after["sketch"]["definition_state"] == "fully_defined"
