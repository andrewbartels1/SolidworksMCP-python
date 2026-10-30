"""Real-SolidWorks checks for ``verify_model`` and ``measured_change`` (#173).

Each test calls the registered MCP tools (the path an MCP client hits) and
asserts against numbers worked out by hand: a 100 x 50 x 10 mm block is
50 000 mm³, a Ø20 x 40 mm cylinder is 12 566 mm³, a Ø5.5 x 6 mm hole removes
142.5 mm³. Evidence lines (``tests.live.evidence``) hold SolidWorks on each
proven state during a demo and caption the GIF frames for the pull request.

These are the live tasks of the OpenSpec change
``verify-model-against-expectations`` (section 7): the extreme-point
bounding box and the no-rebuild volume read, the selection surviving a
read, mate counting on SolidWorks 2026, and the before/after numbers on
extrude, revolve and cut.

Sizes are in model axes. A sketch on the Top plane extrudes along Y, so a
100 x 50 rectangle extruded 10 mm is ``[100, 10, 50]``.

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence

_BLOCK_MM3 = 100.0 * 50.0 * 10.0
_SHAFT_MM3 = math.pi * 10.0**2 * 40.0
_HOLE_MM3 = math.pi * 2.75**2 * 6.0
#: AISI 1020 is 7900 kg/m³ in the SolidWorks material library.
_BLOCK_KG = _BLOCK_MM3 * 1e-9 * 7900.0


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register the modelling and analysis tools against ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("verify-model-live")
    await register_modeling_tools(mcp, adapter, {})
    await register_analysis_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


def _brief(result: dict[str, Any]) -> dict[str, Any]:
    """A ``verify_model`` reply cut down to fit a GIF caption."""
    if result.get("status") != "success":
        return result
    return {
        "verdict": result["verdict"],
        "message": result["message"],
        "checks": [
            {
                k: c[k]
                for k in ("name", "expected", "actual", "passed", "note")
                if c.get(k) is not None
            }
            for c in result["checks"]
        ],
    }


async def _extruded_block(adapter: Any, tools: dict[str, Any]) -> dict[str, Any]:
    """A 100 x 50 x 10 mm block extruded through the ``create_extrusion`` tool."""
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Top")
    assert sketch.is_success, sketch.error
    assert (await adapter.add_rectangle(-50.0, -25.0, 50.0, 25.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    boss = await tools["create_extrusion"]({"sketch_name": sketch.data, "depth": 10.0})
    assert boss["status"] == "success", boss
    return boss


@pytest.mark.asyncio
async def test_verify_model_passes_a_block_and_names_what_is_wrong(scratch):
    """Exact expectations pass; a wrong volume and a mis-oriented size fail."""
    adapter = scratch.adapter
    tools = await _tools(adapter)

    boss = await _extruded_block(adapter, tools)
    change = boss["measured_change"]
    evidence(
        "extrude 100 x 50 rectangle 10 mm (expect +50000 mm³)",
        change,
        call='create_extrusion({"sketch_name": "Sketch1", "depth": 10})',
    )
    assert change["volume_delta_mm3"] == pytest.approx(_BLOCK_MM3, rel=1e-6)
    assert change["bounding_box_after_mm"] == pytest.approx([100, 10, 50], abs=1e-3)
    assert "warning" not in boss

    assert (await adapter.set_material("AISI 1020")).is_success
    expected = {
        "volume_mm3": 50000,
        "mass_kg": round(_BLOCK_KG, 4),
        "bounding_box_mm": [100, 10, 50],
        "feature_count": 1,
        "solid_body_count": 1,
    }
    good = await tools["verify_model"](expected)
    evidence("the block as built", _brief(good), call=f"verify_model({expected})")
    assert good["verdict"] == "pass", good
    assert good["measured"]["bounding_box_method"] == "extreme_points", good
    assert good["measured"]["features"] == ["Boss-Extrude1"], good

    wrong = {"volume_mm3": 60000, "bounding_box_mm": [100, 50, 10]}
    bad = await tools["verify_model"](wrong)
    evidence("the wrong expectations", _brief(bad), call=f"verify_model({wrong})")
    assert bad["status"] == "success", bad
    assert bad["verdict"] == "fail", bad
    failed = {c["name"]: c for c in bad["checks"] if c["passed"] is False}
    assert set(failed) == {"volume_mm3", "bounding_box_mm"}, bad
    assert "oriented differently" in failed["bounding_box_mm"]["note"], bad


@pytest.mark.asyncio
async def test_round_part_size_is_exact(scratch):
    """A Ø20 x 40 mm cylinder's size from extreme points, beside SolidWorks' part box."""
    from solidworks_mcp.adapters import sw_type_info

    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Top")
    assert sketch.is_success, sketch.error
    assert (await adapter.add_circle(0.0, 0.0, 10.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    shaft = await tools["create_extrusion"]({"sketch_name": sketch.data, "depth": 40.0})
    assert shaft["status"] == "success", shaft

    expected = {"volume_mm3": round(_SHAFT_MM3, 1), "bounding_box_mm": [20, 40, 20]}
    result = await tools["verify_model"](expected)
    part = sw_type_info.flagged(adapter.currentModel, "IPartDoc")
    raw = adapter._attempt(lambda: part.GetPartBox(True), default=None)
    part_box = (
        [round((raw[i + 3] - raw[i]) * 1000.0, 3) for i in range(3)] if raw else None
    )
    evidence(
        "Ø20 x 40 cylinder: extreme points vs part box",
        {
            **_brief(result),
            "extreme_point_size": result["measured"]["bounding_box_mm"]["size"],
            "part_box_size": part_box,
        },
        call=f"verify_model({expected})",
    )
    assert result["verdict"] == "pass", result
    assert result["measured"]["bounding_box_method"] == "extreme_points", result


@pytest.mark.asyncio
async def test_reading_the_model_keeps_the_selection(scratch):
    """``verify_model`` (no rebuild) leaves the user's edge selection alone."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    await _extruded_block(adapter, tools)

    picked = await adapter.select_face_edges(side="top")
    assert picked.is_success, picked.error
    before = await adapter.get_selected_entities()
    assert before.is_success and len(before.data) == 4, before

    report = await tools["verify_model"]({})
    after = await adapter.get_selected_entities()
    evidence(
        "selected edges before and after a read-back",
        {
            "verdict": report["verdict"],
            "volume_mm3": report["measured"]["volume_mm3"],
            "selected_before": len(before.data),
            "selected_after": len(after.data),
        },
        call="verify_model({})",
    )
    assert report["verdict"] == "report_only", report
    assert report["measured"]["volume_mm3"] == pytest.approx(_BLOCK_MM3, rel=1e-6)
    assert after.is_success and len(after.data) == len(before.data), after


@pytest.mark.asyncio
async def test_revolve_reports_the_volume_it_added(scratch):
    """A 360° revolve of a 10 x 40 mm profile adds a Ø20 x 40 mm cylinder."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Front")
    assert sketch.is_success, sketch.error
    axis = await adapter.add_centerline(0.0, -5.0, 0.0, 45.0)
    assert axis.is_success, axis.error
    assert (await adapter.add_rectangle(0.0, 0.0, 10.0, 40.0)).is_success
    assert (await adapter.exit_sketch()).is_success

    call = {"sketch_name": sketch.data, "axis_entity": axis.data, "angle": 360}
    revolve = await tools["create_revolve"](call)
    evidence(
        "revolve 10 x 40 profile 360° (expect +12566 mm³)",
        revolve.get("measured_change", revolve),
        call=f"create_revolve({call})",
    )
    assert revolve["status"] == "success", revolve
    change = revolve["measured_change"]
    assert change["volume_delta_mm3"] == pytest.approx(_SHAFT_MM3, rel=1e-4)
    assert change["bounding_box_after_mm"] == pytest.approx([20, 40, 20], abs=0.01)


@pytest.mark.asyncio
async def test_cut_reports_the_volume_it_removed(scratch):
    """A Ø5.5 x 6 mm hole in a 30 x 30 x 15 mm block removes 142.5 mm³."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    block = await adapter.create_sketch("Top")
    assert block.is_success, block.error
    assert (await adapter.add_rectangle(0.0, 0.0, 30.0, 30.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    boss = await tools["create_extrusion"]({"sketch_name": block.data, "depth": 15.0})
    assert boss["status"] == "success", boss
    hole = await adapter.create_sketch("Top")
    assert hole.is_success, hole.error
    assert (await adapter.add_circle(15.0, 15.0, 2.75)).is_success
    assert (await adapter.exit_sketch()).is_success

    call = {"sketch_name": hole.data, "depth": 6.0}
    cut = await tools["create_cut_extrude"](call)
    evidence(
        "cut a Ø5.5 hole 6 mm deep (expect -142.5 mm³)",
        cut.get("measured_change", cut),
        call=f"create_cut_extrude({call})",
    )
    assert cut["status"] == "success", cut
    change = cut["measured_change"]
    assert change["volume_delta_mm3"] == pytest.approx(-_HOLE_MM3, rel=1e-4)
    assert change["bounding_box_after_mm"] == change["bounding_box_before_mm"]
    assert "warning" not in cut


async def _saved_block(scratch: Any, tools: dict[str, Any], path: Path) -> str:
    """Build the 100 x 50 x 10 mm block and save it to ``path``."""
    await _extruded_block(scratch.adapter, tools)
    saved = await scratch.adapter.save_file(str(path))
    assert saved.is_success, saved.error
    scratch.written_files.append(str(path))
    return str(path)


@pytest.mark.asyncio
async def test_assembly_counts_components_mates_and_interference(scratch, tmp_path):
    """Two blocks held 20 mm apart by two mates: 2 components, 2 mates, no overlap."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    first = await _saved_block(scratch, tools, tmp_path / "verify_block_a.SLDPRT")
    second = await _saved_block(scratch, tools, tmp_path / "verify_block_b.SLDPRT")
    assert (await adapter.create_assembly()).is_success
    assert (await adapter.insert_component(first, 0.0, 0.0, 0.0)).is_success
    assert (await adapter.insert_component(second, 0.0, 0.05, 0.0)).is_success
    assembly = str(tmp_path / "verify_assembly.SLDASM")
    scratch.written_files.append(assembly)
    names = await adapter.list_components()
    assert names.is_success and len(names.data) == 2, names
    a, b = names.data

    front = await adapter.add_mate(a, b, "Front Plane", "Front Plane", "coincident")
    assert front.is_success, front.error
    apart = await adapter.add_mate(
        a, b, "Top Plane", "Top Plane", "distance", distance=20.0
    )
    assert apart.is_success, apart.error

    expected = {"component_count": 2, "mate_count": 2, "no_interference": True}
    result = await tools["verify_model"](expected)
    evidence(
        "two blocks, coincident + 20 mm distance mates",
        {**_brief(result), "box_mm": result["measured"]["bounding_box_mm"]["size"]},
        call=f"verify_model({expected})",
    )
    assert result["verdict"] == "pass", result
    assert result["measured"]["bounding_box_method"] == "assembly_box", result
