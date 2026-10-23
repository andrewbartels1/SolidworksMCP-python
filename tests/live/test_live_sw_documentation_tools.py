"""Real-SolidWorks checks for the engineering-data and drawing-automation tools.

None of ``adapters/solidworks/documentation.py`` had run against a live
session when it was written - every signature and enum came from the SW 2025
type libraries, not from a working call. These tests are the proof step. Each
asserts an observable effect (material read back, property read back, volume-
consistent area, dimension count rising on a real view, files on disk), never
just a reported status, following the lesson of com-api-pitfalls #19/#20.

``test_insert_model_dimensions_adds_dimensions`` is the one most likely to
fail: it targets the open question in com-api-pitfalls #18. If it does, the
``views`` entries in the failure message say which path (import or
AutoDimension) produced nothing - record that in #18.

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import os

import pytest


async def _block(adapter, depth_mm: float = 15.0) -> None:  # noqa: ANN001
    """A 30x30mm block, ``depth_mm`` deep, with both sketch sides dimensioned."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Top")).is_success
    bottom = await adapter.add_line(0, 0, 30, 0)
    left = await adapter.add_line(0, 30, 0, 0)
    assert (await adapter.add_line(30, 0, 30, 30)).is_success
    assert (await adapter.add_line(30, 30, 0, 30)).is_success
    assert (await adapter.add_sketch_dimension(bottom.data, None, "linear", 30.0)).is_success
    assert (await adapter.add_sketch_dimension(left.data, None, "linear", 30.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    boss = await adapter.create_extrusion(ExtrusionParameters(depth=depth_mm))
    assert boss.is_success, boss.error


@pytest.mark.asyncio
async def test_material_applies_and_changes_mass(scratch):
    adapter = scratch.adapter
    await _block(adapter)
    listed = await adapter.list_available_materials("1020")
    assert listed.is_success, listed.error
    assert any(m["name"] == "AISI 1020" for m in listed.data)

    result = await adapter.set_material("AISI 1020")
    assert result.is_success, result.error
    assert (await adapter.get_material()).data["material"] == "AISI 1020"

    mass = await adapter.get_mass_properties()
    assert mass.is_success, mass.error
    # 30*30*15 mm = 13.5 cm^3 at ~7.87 g/cm^3 for AISI 1020 -> ~0.106 kg.
    assert 0.09 < float(mass.data.mass) < 0.12, mass.data


@pytest.mark.asyncio
async def test_custom_property_round_trip(scratch):
    adapter = scratch.adapter
    await _block(adapter)
    assert (await adapter.set_custom_property("PartNo", "LIVE-001")).is_success
    props = await adapter.get_custom_properties()
    assert props.is_success, props.error
    assert props.data["properties"]["PartNo"]["value"] == "LIVE-001"


@pytest.mark.asyncio
async def test_dimensions_list_and_measure(scratch):
    adapter = scratch.adapter
    await _block(adapter)
    dims = await adapter.list_model_dimensions()
    assert dims.is_success, dims.error
    names = {d["full_name"] for d in dims.data}
    assert any(n.endswith("@Sketch1") for n in names), names
    assert any("Boss-Extrude1" in n for n in names), names

    top = await adapter.measure_entities(["face:0.015,0.0,-0.015"])
    assert top.is_success, top.error
    assert abs(top.data["area_m2"] - 0.0009) < 1e-6, top.data  # 30 x 30 mm


@pytest.mark.asyncio
async def test_insert_model_dimensions_adds_dimensions(scratch, tmp_path):
    adapter = scratch.adapter
    await _block(adapter)
    part_path = str(tmp_path / "doc_block.SLDPRT")
    assert (await adapter.save_file(part_path)).is_success
    scratch.written_files.append(part_path)

    assert (await adapter.create_drawing()).is_success
    views = await adapter.create_technical_drawing({"model_path": part_path})
    assert views.is_success, views.error

    result = await adapter.insert_model_dimensions()
    assert result.is_success, result.error
    assert result.data["dimensions_added"] > 0, result.data["views"]

    scale = await adapter.set_sheet_scale(1, 2)
    assert scale.is_success, scale.error


@pytest.mark.asyncio
async def test_generate_drawing_package_writes_files(scratch, tmp_path):
    from fastmcp import FastMCP

    from solidworks_mcp.tools.drawing_automation import (
        GenerateDrawingPackageInput,
        register_drawing_automation_tools,
    )

    adapter = scratch.adapter
    await _block(adapter)
    part_path = str(tmp_path / "pkg_block.SLDPRT")
    assert (await adapter.save_file(part_path)).is_success
    scratch.written_files.append(part_path)

    mcp = FastMCP("documentation-live-test")
    await register_drawing_automation_tools(mcp, adapter, {})
    tool = next(t.fn for t in await mcp.list_tools() if t.name == "generate_drawing_package")
    out_dir = tmp_path / "out"
    response = await tool(
        input_data=GenerateDrawingPackageInput(model_path=part_path, output_dir=str(out_dir))
    )
    for path in (response.get("drawing_path"), response.get("pdf_path")):
        if path:
            scratch.written_files.append(path)
    assert response["status"] in {"success", "partial"}, response["steps"]
    assert response["drawing_path"] and os.path.exists(response["drawing_path"])
    assert response["pdf_path"] and os.path.getsize(response["pdf_path"]) > 0
