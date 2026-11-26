"""Default planes, the origin and standard views by identity (#262), on real SolidWorks.

A part's default plane names come from its template, not from the UI
language, so a part whose planes and origin are renamed to the French names
is what a French template makes. These run on an English install:

1. A translated part: its planes renamed ``Plan de face``, ``Plan de
   dessus``, ``Plan de droite`` and its origin ``Origine``; then a sketch on
   ``Top`` (the box proves it is the Top plane), a hole mirrored about
   ``Right``, an axis from two default planes, ``select_feature`` on ``Front
   Plane``, and a plane that doesn't exist, which fails rather than being
   swapped for a default one.
2. The standard view list: the first ten names of ``GetModelViewNames`` are
   the standard views in the order the lookup assumes, and a drawing view
   of the translated part is placed by them.
3. A BOM placed by the sheet format's anchor, with no position, lies inside
   the drawing border (10 mm in) on SolidWorks 2026 too.

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_default_entities.py::test_a_translated_part

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence

pytestmark = pytest.mark.asyncio

FRENCH = ("Plan de face", "Plan de dessus", "Plan de droite", "Origine")


async def _tools(adapter: Any) -> dict[str, Any]:
    """Every tool, registered against ``adapter``: name -> function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools import register_tools

    mcp = FastMCP("default-entities-live")
    await register_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _ok(reply: dict[str, Any]) -> dict[str, Any]:
    assert reply["status"] == "success", reply
    return reply


def _translate(adapter: Any) -> dict[str, Any]:
    """Rename the active part's default planes and origin to the French names,
    as a French template names them; what the tree says before and after."""
    from solidworks_mcp.adapters import sw_type_info
    from solidworks_mcp.adapters.solidworks.default_entities import read_defaults

    model = adapter.currentModel
    before = read_defaults(adapter, model)
    assert len(before.planes) >= 3 and before.origin, before
    for old, new in zip((*before.planes[:3], before.origin), FRENCH, strict=True):
        feature = sw_type_info.flagged(model.FeatureByName(old), "IFeature")
        feature.Name = new
    after = read_defaults(adapter, model)
    return {
        "before": [*before.planes[:3], before.origin],
        "after": [*after.planes[:3], after.origin],
    }


async def _translated_plate(tools: dict[str, Any], adapter: Any) -> dict[str, Any]:
    """A French-named part with a 100 x 60 x 10 mm plate sketched on ``Top``."""
    await _ok(await tools["create_part"]({"name": "plaque"}))
    renamed = _translate(adapter)
    sketch = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_rectangle"]({"x1": -50, "y1": -30, "x2": 50, "y2": 30}))
    await _ok(await tools["exit_sketch"]())
    await _ok(
        await tools["create_extrusion"](
            {"sketch_name": sketch["sketch"]["name"], "depth": 10}
        )
    )
    return renamed


async def test_a_translated_part(scratch: Any) -> None:
    """Every default-plane tool finds the French-named planes."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    renamed = await _translated_plate(tools, adapter)
    evidence("the part's default planes and origin, renamed", renamed)
    assert renamed["after"] == list(FRENCH), renamed

    # On Top (XZ) the plate is 100 x 10 x 60; on Front it would be 100 x 60 x 10.
    on_top = await tools["verify_model"]({"bounding_box_mm": [100, 10, 60]})
    evidence(
        "a sketch on 'Top' opened on 'Plan de dessus'",
        {"verdict": on_top["verdict"], "measured": on_top.get("measured")},
        call='create_sketch({"plane": "Top"}) then a 10 mm extrusion',
    )
    assert on_top["verdict"] == "pass", on_top

    hole = await _ok(await tools["create_sketch"]({"plane": "Top"}))
    await _ok(await tools["add_circle"]({"center_x": 30, "center_y": 0, "radius": 3}))
    await _ok(await tools["exit_sketch"]())
    cut = await _ok(
        await tools["create_cut_extrude"](
            {
                "sketch_name": hole["sketch"]["name"],
                "depth": 10.0,
                "end_condition": "ThroughAll",
            }
        )
    )
    mirror_call = {
        "features": [cut["cut_extrude"]["name"]],
        "mirror_plane": "Right",
        "mirror_bodies": False,
    }
    mirrored = await tools["mirror_feature"](mirror_call)
    expected = -math.pi * 3**2 * 10
    evidence(
        f"a hole mirrored about 'Right' (expect {expected:,.1f} mm³)",
        {
            "status": mirrored["status"],
            "volume_change": mirrored.get("mirror", {}).get("volume_change"),
        },
        call=f"mirror_feature({mirror_call})",
    )
    assert mirrored["status"] == "success", mirrored
    assert mirrored["mirror"]["volume_change"] == pytest.approx(expected, rel=1e-3)

    axis = await tools["create_axis"]({"reference": "y"})
    evidence("an axis from the Front and Right planes", axis, call="create_axis(y)")
    assert axis["status"] == "success", axis

    picked = await tools["select_feature"]({"feature_name": "Front Plane"})
    evidence("select_feature('Front Plane')", picked)
    assert picked["status"] == "success", picked

    # A relation to the origin ('Origine' here): the origin's point is found
    # by the origin feature's place in the tree, not by its name ('Point1'
    # on English; translated on other installs).
    await _ok(await tools["create_sketch"]({"plane": "Front"}))
    line = await _ok(await tools["add_line"]({"x1": 5, "y1": 5, "x2": 20, "y2": 5}))
    line_id = line["line"]["id"]
    tied = await tools["add_sketch_constraint"](
        {
            "entity1": f"{line_id}.start",
            "entity2": "origin",
            "relation_type": "coincident",
        }
    )
    evidence("a line's start tied to the origin ('Origine')", tied)
    assert tied["status"] == "success", tied
    await _ok(await tools["exit_sketch"]())

    missing = await tools["create_sketch"]({"plane": "Plane7"})
    evidence("a plane that doesn't exist is an error, not a default plane", missing)
    assert missing["status"] == "error", missing
    assert "Plane7" in missing["message"], missing


async def test_the_standard_view_list(scratch: Any, tmp_path: Path) -> None:
    """The view list starts with the ten standard views, in the assumed order,
    and a drawing view of the translated part is placed from it."""
    from solidworks_mcp.adapters.solidworks.com_utils import as_list, flag
    from solidworks_mcp.adapters.solidworks.default_entities import STANDARD_VIEWS

    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _translated_plate(tools, adapter)
    model = adapter.currentModel
    flag(adapter, model, "GetModelViewNames")
    names = [str(n) for n in as_list(model.GetModelViewNames())]
    language = adapter.swApp.GetCurrentLanguage()
    evidence(
        "GetModelViewNames on this install",
        {"language": language, "names": names},
    )
    assert names[: len(STANDARD_VIEWS)] == list(STANDARD_VIEWS), names

    part = str(tmp_path / "plaque.SLDPRT")
    saved = await adapter.save_file(part)
    assert saved.is_success, saved.error
    scratch.written_files.append(part)
    await _ok(await tools["create_drawing"]({"name": "plaque-vues"}))
    iso = await tools["create_drawing_view"](
        {"model_path": part, "view_type": "isometric", "position_x": 200}
    )
    evidence("an isometric view of the translated part", iso.get("data") or iso)
    assert iso["status"] == "success", iso


async def test_a_bom_inside_the_border(scratch: Any, tmp_path: Path) -> None:
    """With no position, the sheet format's anchor decides where the BOM goes;
    it ends up inside the border (10 mm in) on SolidWorks 2026 too."""
    from solidworks_mcp.adapters.solidworks import drawing_standard
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info
    from tests.live.test_live_sw_drawing_package_tools import (
        _drawing_tools,
        _saved_block,
        _view_widths,
    )

    adapter = scratch.adapter
    plate = await _saved_block(scratch, tmp_path / "border_plate.SLDPRT", 5.0)
    block = await _saved_block(scratch, tmp_path / "border_block.SLDPRT", 20.0)
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(plate, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(block, 0.0, 0.0, 0.05)).is_success
    assembly = str(tmp_path / "border_assembly.SLDASM")
    assert (await adapter.save_file(assembly)).is_success
    scratch.written_files.append(assembly)
    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": assembly})
    assert views.is_success, views.error
    tools = await _drawing_tools(adapter)
    view = next(iter(_view_widths(adapter)))

    result = await tools["insert_bom_table"]({"view_name": view})
    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    sheet = adapter._sheet_bounds(drawing)
    sheet_mm = [round(v * 1000, 1) for v in sheet]
    inset = drawing_standard.BORDER_INSET * 1000
    evidence(
        "a BOM with no position: its box against the border",
        {
            "table_box_mm": result.get("data", {}).get("table_box_mm"),
            "moved_onto_sheet": result.get("data", {}).get("moved_onto_sheet"),
            "sheet_mm": sheet_mm,
            "border_inset_mm": inset,
        },
        call=f'insert_bom_table({{"view_name": "{view}"}})',
    )
    assert result["status"] == "success", result
    box = result["data"]["table_box_mm"]
    assert box[0] >= inset - 0.1 and box[1] >= inset - 0.1, box
    assert box[2] <= sheet_mm[2] - inset + 0.1, box
    assert box[3] <= sheet_mm[3] - inset + 0.1, box
