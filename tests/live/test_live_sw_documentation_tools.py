"""Real-SolidWorks checks for the engineering-data tools (from PR #117).

Each test calls the registered MCP tool (the exact path an MCP client hits)
and asserts an observable effect: a material read back and a mass that matches
it, a property read back, a face area that matches the sketch, the model's own
dimension names. Evidence lines (``tests.live.evidence``) hold SolidWorks on
each proven state during a demo.

The author verified these on SolidWorks 2025; they are the sign-off on 2026.
``export_flat_pattern`` is checked both ways: refusing a solid block, and
exporting a copy of the "Simple Sheet Metal Part" sample SolidWorks installs
(skipped when the samples are not installed).

The drawing-dimension tools (from the same PR) are checked on a drawing of the
same block: each model dimension shown once, then laid out with no overlaps.
So are the drawing-package tools: the sheet scale read back, a BOM for a
two-part assembly, and a complete A3 drawing of the block with its PDF.

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence


async def _block(adapter, depth_mm: float = 15.0) -> None:  # noqa: ANN001
    """A 30x30mm block, ``depth_mm`` deep, with both sketch sides dimensioned."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Top")).is_success
    bottom = await adapter.add_line(0, 0, 30, 0)
    left = await adapter.add_line(0, 30, 0, 0)
    assert (await adapter.add_line(30, 0, 30, 30)).is_success
    assert (await adapter.add_line(30, 30, 0, 30)).is_success
    assert (
        await adapter.add_sketch_dimension(bottom.data, None, "linear", 30.0)
    ).is_success
    assert (
        await adapter.add_sketch_dimension(left.data, None, "linear", 30.0)
    ).is_success
    assert (await adapter.exit_sketch()).is_success
    boss = await adapter.create_extrusion(ExtrusionParameters(depth=depth_mm))
    assert boss.is_success, boss.error


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register the engineering-data tools against ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools

    mcp = FastMCP("engineering-data-live")
    await register_engineering_data_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.mark.asyncio
async def test_material_applies_and_changes_mass(scratch):
    """list -> set -> get material; the mass follows the density."""
    adapter = scratch.adapter
    await _block(adapter)
    tools = await _tools(adapter)

    listed = await tools["list_available_materials"]({"search": "1020"})
    evidence(
        "list_available_materials('1020')",
        {
            "message": listed.get("message"),
            "names": [m["name"] for m in listed.get("data") or []],
        },
    )
    assert listed["status"] == "success", listed
    assert any(m["name"] == "AISI 1020" for m in listed["data"])

    applied = await tools["set_material"]({"material_name": "AISI 1020"})
    read = await tools["get_material"]({})
    evidence("set_material + get_material", read["data"])
    assert applied["status"] == "success", applied
    assert read["data"]["material"] == "AISI 1020"

    mass = await adapter.get_mass_properties()
    assert mass.is_success, mass.error
    evidence("mass of 30x30x15 mm AISI 1020 (expect ~0.106 kg)", mass.data.mass)
    # 30*30*15 mm = 13.5 cm^3 at ~7.87 g/cm^3 for AISI 1020 -> ~0.106 kg.
    assert 0.09 < float(mass.data.mass) < 0.12, mass.data

    wrong = await tools["set_material"]({"material_name": "Unobtainium"})
    evidence("set_material('Unobtainium')", wrong)
    assert wrong["status"] == "error"


@pytest.mark.asyncio
async def test_custom_property_round_trip(scratch):
    """A property written by set_custom_property reads back."""
    adapter = scratch.adapter
    await _block(adapter)
    tools = await _tools(adapter)

    written = await tools["set_custom_property"](
        {"name": "PartNo", "value": "LIVE-001"}
    )
    props = await tools["get_custom_properties"]({})
    evidence("get_custom_properties after set PartNo", props["data"]["properties"])
    assert written["status"] == "success", written
    assert props["data"]["properties"]["PartNo"]["value"] == "LIVE-001"


@pytest.mark.asyncio
async def test_dimensions_list_and_measure(scratch):
    """The model's own dimension names, and a face area matching the sketch."""
    adapter = scratch.adapter
    await _block(adapter)
    tools = await _tools(adapter)

    dims = await tools["list_model_dimensions"]({})
    names = {d["full_name"] for d in dims["data"]}
    evidence("list_model_dimensions", sorted(names))
    assert dims["status"] == "success", dims
    assert any(n.endswith("@Sketch1") for n in names), names
    assert any("Boss-Extrude1" in n for n in names), names

    # Centre of the top face: the Top-plane sketch spans x, y in [0, 30] mm and
    # the boss runs from z = 0 down to z = -15 mm (as in the chamfer live tests).
    top = await tools["measure_entities"]({"entities": ["face:0.015,0.015,0.0"]})
    evidence("measure top face (expect 0.0009 m^2 = 30x30 mm)", top)
    assert top["status"] == "success", top
    assert abs(top["data"]["area_m2"] - 0.0009) < 1e-6, top["data"]

    missing = await tools["list_model_dimensions"]({"feature_name": "Fillet9"})
    evidence("list_model_dimensions('Fillet9')", missing)
    assert missing["error_type"] == "not_found"


@pytest.mark.asyncio
async def test_export_flat_pattern_refuses_a_solid_part(scratch, tmp_path):
    """A part without a sheet-metal body is refused clearly; nothing is written."""
    adapter = scratch.adapter
    await _block(adapter)
    tools = await _tools(adapter)
    target = tmp_path / "flat.dxf"

    result = await tools["export_flat_pattern"]({"file_path": str(target)})
    evidence("export_flat_pattern on a solid block", result)
    assert result["status"] == "error"
    assert result["error_type"] == "not_found"
    assert "sheet-metal" in result["message"]
    assert not target.exists()


_SHEET_METAL_SAMPLE = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn"
    r"\Sheet Metal\Simple Sheet Metal Part.SLDPRT"
)


@pytest.mark.asyncio
async def test_export_flat_pattern_writes_a_dxf(scratch, tmp_path):
    """A real sheet-metal part's flat pattern is written as a DXF."""
    if not _SHEET_METAL_SAMPLE.exists():
        pytest.skip(f"SolidWorks sample not installed: {_SHEET_METAL_SAMPLE}")
    adapter = scratch.adapter
    # Work on a copy: the shared sample is never opened for writing.
    part = tmp_path / "sheet_metal_copy.SLDPRT"
    shutil.copyfile(_SHEET_METAL_SAMPLE, part)
    scratch.written_files.append(str(part))
    opened = await adapter.open_model(str(part))
    assert opened.is_success, opened.error
    tools = await _tools(adapter)
    target = tmp_path / "flat.dxf"

    result = await tools["export_flat_pattern"]({"file_path": str(target)})
    evidence("export_flat_pattern on the sheet-metal sample", result)

    assert result["status"] == "success", result
    assert target.exists() and target.stat().st_size > 0
    text = target.read_text(encoding="latin-1")
    sections = [s for s in ("HEADER", "ENTITIES", "EOF") if s in text]
    evidence("DXF sections written", sections)
    assert "ENTITIES" in sections


async def _drawing_tools(adapter: Any) -> dict[str, Any]:
    """Register the drawing-automation tools against ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.drawing_automation import (
        register_drawing_automation_tools,
    )

    mcp = FastMCP("drawing-automation-live")
    await register_drawing_automation_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _block_drawing(scratch, tmp_path) -> str:  # noqa: ANN001
    """Save the block and lay out its three standard views on a new drawing."""
    adapter = scratch.adapter
    await _block(adapter)
    part = str(tmp_path / "dim_block.SLDPRT")
    assert (await adapter.save_file(part)).is_success
    scratch.written_files.append(part)
    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": part})
    assert views.is_success, views.error
    return part


def _layout_snapshot(adapter: Any) -> dict[str, Any]:
    """What arrange_dimensions reads: view outlines, dimension geometry, overlaps.

    Read-only, through the same calls arrange_dimensions makes, on the
    connect thread via ``_handle_com_operation``. Millimetres on the sheet.
    """
    from solidworks_mcp.adapters.solidworks import dimension_layout as lay
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info, _view_names

    def mm(values: Any) -> list[float]:
        return [round(float(v) * 1000, 1) for v in values]

    def read() -> dict[str, Any]:
        drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
        outlines, geometries, _ = adapter._collect_layout(
            drawing, _view_names(adapter, drawing)
        )
        sheet = adapter._sheet_bounds(drawing)
        return {
            "overlaps": [
                f"{o['dimension']} {o['kind']} {o['conflicts_with']}"
                for o in lay.find_overlaps(geometries, outlines, sheet)
            ],
            "views_mm": {name: mm(box) for name, box in outlines.items()},
            "dimensions": [
                {
                    "key": g.key,
                    "orientation": lay.classify(g.lines)[0],
                    "text_mm": mm(g.text_box),
                    "lines_mm": [mm(line) for line in g.lines],
                }
                for g in geometries
            ],
        }

    snapshot = adapter._handle_com_operation("layout_snapshot", read)
    assert snapshot.is_success, snapshot.error
    return snapshot.data


def _pile_onto_views(adapter: Any) -> None:
    """Drag every dimension's text onto the middle of its view (worst case).

    On this block SolidWorks imports the dimensions cleanly, so the demo
    stages the mess arrange_dimensions exists to fix: every dimension on its
    part and on the others. Same ``IAnnotation::SetPosition`` call the tool
    makes, on the connect thread.
    """
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info, _view_names

    def pile() -> int:
        model = adapter.currentModel
        drawing = _sw_type_info.flagged(model, "IDrawingDoc")
        outlines, geometries, annotations = adapter._collect_layout(
            drawing, _view_names(adapter, drawing)
        )
        moved = 0
        for g in geometries:
            o = outlines[g.view]
            dx = (o[0] + o[2]) / 2 - (g.text_box[0] + g.text_box[2]) / 2
            dy = (o[1] + o[3]) / 2 - (g.text_box[1] + g.text_box[3]) / 2
            an = annotations[g.key]
            z = an.GetPosition()[2]
            moved += bool(an.SetPosition(g.position[0] + dx, g.position[1] + dy, z))
        model.EditRebuild3()
        model.GraphicsRedraw2()
        return moved

    piled = adapter._handle_com_operation("pile_dimensions", pile)
    assert piled.is_success and piled.data, piled.error


@pytest.mark.asyncio
async def test_insert_model_dimensions_shows_each_dimension_once(scratch, tmp_path):
    """Model dimensions land on the views once each; pictorial views are skipped."""
    adapter = scratch.adapter
    part = await _block_drawing(scratch, tmp_path)
    iso = await adapter.create_drawing_view(
        {"model_path": part, "orientation": "isometric", "position": [330.0, 220.0]}
    )
    assert iso.is_success, iso.error
    tools = await _drawing_tools(adapter)

    result = await tools["insert_model_dimensions"]({})
    data = result.get("data") or {}
    evidence(
        "dimensions on the three views, the isometric skipped",
        {
            "message": result.get("message"),
            "views": [
                (v["view"], v["dimensions_added"], v["duplicates_removed"])
                for v in data.get("views", [])
            ],
            "unique_dimensions": data.get("unique_dimensions"),
            "skipped_pictorial_views": data.get("skipped_pictorial_views"),
        },
        call="insert_model_dimensions({})",
    )
    assert result["status"] == "success", result
    assert data["dimensions_added"] > 0
    shown = sum(v["dimensions_after"] for v in data["views"])
    assert shown == data["unique_dimensions"]  # each dimension once on the sheet
    assert iso.data["name"] in data["skipped_pictorial_views"]

    missing = await tools["insert_model_dimensions"]({"view_name": "Side"})
    evidence(
        "an unknown view is not_found",
        missing,
        call='insert_model_dimensions({"view_name": "Side"})',
    )
    assert missing["error_type"] == "not_found"


@pytest.mark.asyncio
async def test_arrange_dimensions_clears_every_overlap(scratch, tmp_path):
    """Dimensions piled on the views are moved off them: zero overlaps after."""
    adapter = scratch.adapter
    await _block_drawing(scratch, tmp_path)
    tools = await _drawing_tools(adapter)
    inserted = await tools["insert_model_dimensions"]({})
    assert inserted["status"] == "success", inserted
    _pile_onto_views(adapter)
    before = _layout_snapshot(adapter)
    evidence("BEFORE: every dimension dragged onto its view (staged)", before)
    assert before["overlaps"], "staging left nothing to fix"

    result = await tools["arrange_dimensions"]({})
    data = result.get("data") or {}
    evidence(
        "every dimension moved off the views",
        {
            "message": result.get("message"),
            "moved": data.get("moved"),
            "unplaced": data.get("unplaced"),
            "remaining_overlaps": data.get("remaining_overlaps"),
        },
        call="arrange_dimensions({})",
    )
    evidence("AFTER arranging", _layout_snapshot(adapter))
    assert result["status"] == "success", result
    assert data["overlaps_after"] == 0
    assert data["moved"] > 0


def _views_mm(adapter: Any) -> dict[str, list[float]]:
    """Each view's outline on the sheet in mm (read-only)."""
    return _layout_snapshot(adapter)["views_mm"]


@pytest.mark.asyncio
async def test_set_sheet_scale_shrinks_the_views(scratch, tmp_path):
    """The sheet reads back 1:2 and every view gets smaller; 0 is refused."""
    adapter = scratch.adapter
    await _block_drawing(scratch, tmp_path)
    tools = await _drawing_tools(adapter)
    before = _views_mm(adapter)
    evidence("views before, at the drawing's own scale (mm)", before)

    result = await tools["set_sheet_scale"]({"numerator": 1, "denominator": 2})
    evidence("the sheet reads back 1:2", result, call="set_sheet_scale(1:2)")
    after = _views_mm(adapter)
    evidence("views after (mm): every one smaller", after)
    assert result["status"] == "success", result
    assert result["data"]["scale"] == "1:2"
    for name, box in after.items():
        assert box[2] - box[0] < before[name][2] - before[name][0], name

    zero = await tools["set_sheet_scale"]({"numerator": 0, "denominator": 2})
    evidence(
        "a zero scale is refused",
        zero,
        call='set_sheet_scale({"numerator": 0, "denominator": 2})',
    )
    assert zero["error_type"] == "invalid_input"


@pytest.mark.asyncio
async def test_insert_bom_table_lists_the_assembly(scratch, tmp_path):
    """A two-part assembly's drawing gets a BOM with a row per part."""
    adapter = scratch.adapter
    parts = []
    for name, depth in (("bom_block", 15.0), ("bom_plate", 5.0)):
        await _block(adapter, depth)
        path = str(tmp_path / f"{name}.SLDPRT")
        assert (await adapter.save_file(path)).is_success
        scratch.written_files.append(path)
        parts.append(path)
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(parts[0], 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(parts[1], 0.05, 0.0, 0.0)).is_success
    assembly = str(tmp_path / "bom_frame.SLDASM")
    assert (await adapter.save_file(assembly)).is_success
    scratch.written_files.append(assembly)
    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": assembly})
    assert views.is_success, views.error
    tools = await _drawing_tools(adapter)

    result = await tools["insert_bom_table"]({"view_name": "Drawing View1"})
    evidence(
        "a BOM for the two-part assembly",
        result,
        call='insert_bom_table({"view_name": "Drawing View1"})',
    )
    assert result["status"] == "success", result
    assert result["data"]["row_count"] >= 3  # the header and one row per part

    missing = await tools["insert_bom_table"]({"view_name": "Side"})
    evidence(
        "an unknown view is not_found",
        missing,
        call='insert_bom_table({"view_name": "Side"})',
    )
    assert missing["error_type"] == "not_found"


@pytest.mark.asyncio
async def test_generate_drawing_package_makes_a_complete_a3_drawing(scratch, tmp_path):
    """One call: A3 sheet, filled title block, views, dimensions, notes, PDF."""
    adapter = scratch.adapter
    await _block(adapter)
    material = await (await _tools(adapter))["set_material"](
        {"material_name": "AISI 1020"}
    )
    assert material["status"] == "success", material
    part = str(tmp_path / "pkg_block.SLDPRT")
    assert (await adapter.save_file(part)).is_success
    scratch.written_files.append(part)
    tools = await _drawing_tools(adapter)
    payload = {
        "model_path": part,
        "output_dir": str(tmp_path / "out"),
        "title": "Demo Block",
        "author": "SolidWorks MCP",
        "notes": ["Break all edges 0.5 mm"],
    }

    result = await tools["generate_drawing_package"](payload)
    data = result.get("data") or {}
    for key in ("drawing_path", "pdf_path"):
        if data.get(key):
            scratch.written_files.append(data[key])
    evidence(
        "a complete A3 drawing of the block",
        {
            "message": result.get("message"),
            "scale": data.get("scale"),
            "views": {n: v["role"] for n, v in (data.get("views") or {}).items()},
            "dimensions_added": (data.get("dimensions") or {}).get("dimensions_added"),
            "overlaps_after": (data.get("overlap_check") or {}).get("overlaps_after"),
            "title_block": data.get("title_block"),
            "failed_steps": [
                s["step"] for s in data.get("steps", []) if s["status"] != "success"
            ],
            "pdf_bytes": Path(data["pdf_path"]).stat().st_size
            if data.get("pdf_path")
            else None,
        },
        call="generate_drawing_package("
        '{"model_path": "pkg_block.SLDPRT", "title": "Demo Block", ...})',
    )
    assert result["status"] == "success", result
    assert Path(data["drawing_path"]).is_file()
    assert Path(data["pdf_path"]).stat().st_size > 0
    assert data["overlap_check"]["overlaps_after"] == 0
    assert data["title_block"]["drawing number"]["fits"] is True
    assert sorted(v["role"] for v in data["views"].values()) == [
        "front",
        "iso",
        "plan",
        "side",
    ]
