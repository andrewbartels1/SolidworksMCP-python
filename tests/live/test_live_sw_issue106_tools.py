"""Real-SolidWorks sign-off tests for #106: select_feature, select_face_edges,
rebuild_model and list_drawing_views, called through the registered MCP tools
(the exact path an MCP client hits).

Gating, the ``scratch`` fixture and scratch-doc cleanup come from
``tests/live/conftest.py``. Run with ``SW_TEST_PACE_SECONDS=4`` so leftover
documents are drained between tests (a long unpaced probe session crashed
SolidWorks on 2026-10-13). Each test prints an ``[evidence]`` line; run with
``-s`` to capture them for review.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_wave3 import _box_part, _plate_with_hole_drawing

_HOLE_R_MM = 4.0
_CHAMFER_MM = 0.5


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register modeling + drawing tools against ``adapter``; return name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.drawing import register_drawing_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("issue-106-live")
    await register_modeling_tools(mcp, adapter, {})
    await register_drawing_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _plate_with_through_hole(adapter: Any) -> None:
    """60 x 40 x 10 mm plate sketched on Top with a Ø8 hole in the same
    profile: a through-hole along Y, so both +Y and -Y faces carry a rim."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success
    assert (await adapter.create_sketch("Top")).is_success
    assert (await adapter.add_rectangle(0.0, 0.0, 60.0, 40.0)).is_success
    assert (await adapter.add_circle(30.0, 20.0, _HOLE_R_MM)).is_success
    assert (await adapter.exit_sketch()).is_success
    assert (await adapter.create_extrusion(ExtrusionParameters(depth=10.0))).is_success


def _sel_count(adapter: Any) -> int:
    from solidworks_mcp.adapters import sw_type_info

    mgr = adapter.currentModel.SelectionManager
    sw_type_info.flag_members(mgr, "GetSelectedObjectCount2")
    return int(mgr.GetSelectedObjectCount2(-1))


def _evidence(label: str, payload: Any) -> None:
    evidence(label, payload)


# ---- select_feature ---------------------------------------------------------


@pytest.mark.asyncio
async def test_select_feature_live(scratch):
    """Bare, sketch, qualified and appended selections really select; unknown errors."""
    adapter = scratch.adapter
    await _box_part(adapter)
    tools = await _tools(adapter)
    select = tools["select_feature"]

    boss = await select({"feature_name": "Boss-Extrude1"})
    _evidence("select Boss-Extrude1", boss)
    assert boss["status"] == "success", boss
    assert boss["data"]["entity_type"] == "feature-name"
    assert _sel_count(adapter) == 1

    sketch = await select({"feature_name": "Sketch1"})
    assert sketch["status"] == "success", sketch
    assert _sel_count(adapter) == 1  # replaced, not appended

    title = str(adapter._get_attr_or_call(adapter.currentModel, "GetTitle"))
    qualified = await select(
        {"feature_name": f"Boss-Extrude1@{title.rsplit('.', 1)[0]}", "append": True}
    )
    _evidence("qualified + append", qualified)
    assert qualified["status"] == "success", qualified
    assert qualified["data"]["selection_count"] == 2
    assert _sel_count(adapter) == 2

    plane = await select({"feature_name": "Front Plane"})
    assert plane["status"] == "success", plane

    missing = await select({"feature_name": "NoSuchFeature"})
    _evidence("select NoSuchFeature", missing)
    assert missing["status"] == "error"
    assert "NoSuchFeature" in missing["message"]


# ---- select_face_edges --------------------------------------------------------


@pytest.mark.asyncio
async def test_select_face_edges_side_point_plane_live(scratch):
    """side / point / plane each resolve the right face and select its edges."""
    adapter = scratch.adapter
    await _plate_with_through_hole(adapter)
    tool = (await _tools(adapter))["select_face_edges"]

    rim = await tool({"side": "top", "edge_type": "circular"})
    _evidence("side=top circular", rim)
    assert rim["status"] == "success", rim
    assert rim["data"]["face"]["normal"] == [0.0, 1.0, 0.0]
    assert [e["curve"] for e in rim["data"]["edges"]] == ["circular"]
    assert rim["data"]["edges"][0]["radius_mm"] == pytest.approx(_HOLE_R_MM, abs=1e-6)
    assert _sel_count(adapter) == 1

    cx, cy, cz = rim["data"]["face"]["center_mm"]  # bbox centre = hole centre
    on_face = await tool({"point": [cx + 15.0, cy, cz]})
    _evidence("point on top face, all edges", on_face)
    assert on_face["status"] == "success", on_face
    kinds = sorted(e["curve"] for e in on_face["data"]["edges"])
    assert kinds == ["circular", "linear", "linear", "linear", "linear"]
    assert _sel_count(adapter) == 5

    side = await tool({"side": "+X", "append": True})
    assert side["status"] == "success", side
    assert side["data"]["selected_edges"] == 4
    assert _sel_count(adapter) >= 7  # appended; shared edges count once

    by_plane = await tool({"plane": "Top Plane"})
    _evidence("plane=Top Plane", by_plane)
    assert by_plane["status"] == "success", by_plane
    assert by_plane["data"]["face"]["center_mm"][1] == pytest.approx(0.0, abs=1e-6)
    assert by_plane["data"]["selected_edges"] == 5

    none = await tool({"side": "+X", "edge_type": "circular"})
    _evidence("side=+X circular (none)", none)
    assert none["status"] == "error"
    assert "no circular edges" in none["message"]

    off = await tool({"point": [1000.0, 1000.0, 1000.0]})
    assert off["status"] == "error" and "No face found" in off["message"]


@pytest.mark.asyncio
async def test_select_face_edges_chains_into_add_chamfer_live(scratch):
    """select_face_edges -> add_chamfer(edge_names=[]) chamfers exactly the rim."""
    adapter = scratch.adapter
    await _plate_with_through_hole(adapter)
    tools = await _tools(adapter)

    # Measure BEFORE selecting: get_mass_properties rebuilds, which clears the
    # selection (com-api-pitfalls #23).
    before = await adapter.get_mass_properties()
    assert before.is_success, before.error

    picked = await tools["select_face_edges"]({"side": "top", "edge_type": "circular"})
    assert picked["status"] == "success", picked
    chamfer = await tools["add_chamfer"]({"distance": _CHAMFER_MM, "edge_names": []})
    assert chamfer["status"] == "success", chamfer

    after = await adapter.get_mass_properties()
    removed = before.data.volume - after.data.volume
    r, w = _HOLE_R_MM, _CHAMFER_MM
    expected_rim = math.pi * (((r + w) ** 3 - r**3) / 3.0 - r * r * w)
    expected_outer_edge = 0.5 * w * w * 60.0  # what a wrong-edge chamfer removes
    _evidence(
        "chain volume",
        {"removed_mm3": round(removed, 4), "expected_rim_mm3": round(expected_rim, 4)},
    )
    assert removed == pytest.approx(expected_rim, rel=0.05), (
        f"removed {removed:.4f} mm^3; rim chamfer should remove {expected_rim:.4f}, "
        f"a 60 mm outer edge would remove {expected_outer_edge:.4f}"
    )


# ---- rebuild_model -------------------------------------------------------------


def _empty_sketch(adapter: Any, sketch_name: str) -> None:
    """Delete every segment of ``sketch_name`` so its child feature fails."""
    from solidworks_mcp.adapters import sw_type_info

    model = adapter.currentModel
    feature = model.FeatureByName(sketch_name)
    sw_type_info.flag_members(feature, "Select2")
    assert feature.Select2(False, 0)
    model.EditSketch()
    manager = model.SketchManager
    sketch = manager.ActiveSketch
    sw_type_info.flag_members(sketch, "GetSketchSegments")
    sel_mgr = model.SelectionManager
    sw_type_info.flag_members(sel_mgr, "CreateSelectData")
    data = sel_mgr.CreateSelectData()
    model.ClearSelection2(True)
    for segment in sketch.GetSketchSegments() or []:
        sw_type_info.flag_members(segment, "Select4")
        segment.Select4(True, data)
    model.EditDelete()
    sw_type_info.flag_members(manager, "InsertSketch")
    manager.InsertSketch(True)


@pytest.mark.asyncio
async def test_rebuild_model_clean_and_broken_live(scratch):
    """Clean part -> success; a boss whose sketch was emptied -> error naming it."""
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    await _box_part(adapter)
    rebuild = (await _tools(adapter))["rebuild_model"]

    clean = await rebuild()
    _evidence("rebuild clean", clean)
    assert clean["status"] == "success", clean
    assert clean["data"]["error_count"] == 0

    assert (await adapter.create_sketch("Front")).is_success
    assert (await adapter.add_circle(20.0, 12.0, 3.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    boss2 = await adapter.create_extrusion(
        ExtrusionParameters(depth=5.0, reverse_direction=True)
    )
    assert boss2.is_success, boss2.error
    _empty_sketch(adapter, "Sketch2")

    broken = await rebuild()
    _evidence("rebuild broken", broken)
    assert broken["status"] == "error", broken
    assert "Boss-Extrude2" in broken["message"]
    entry = next(e for e in broken["data"]["errors"] if e["feature"] == "Boss-Extrude2")
    assert entry["severity"] == "error"
    assert entry["code_name"].startswith("swFeatureError")
    assert any(p["name"] == "Sketch2" for p in entry["parents"])
    assert "Sketch2" in entry["hint"]


# ---- list_drawing_views --------------------------------------------------------


@pytest.mark.asyncio
async def test_list_drawing_views_live(scratch, tmp_path):
    """A generated drawing lists its views; a part is refused."""
    adapter = scratch.adapter
    part_path, first_view = await _plate_with_hole_drawing(adapter, tmp_path)
    scratch.written_files.append(part_path)
    tool = (await _tools(adapter))["list_drawing_views"]

    views = await tool()
    _evidence("list_drawing_views", views)
    assert views["status"] == "success", views
    assert first_view in views["views"]
    assert views["count"] == len(views["views"]) >= 1

    assert (await adapter.create_part()).is_success
    refused = await tool()
    _evidence("list_drawing_views on a part", refused)
    assert refused["status"] == "error"
    assert "drawing" in refused["message"]
