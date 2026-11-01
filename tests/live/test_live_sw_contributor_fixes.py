"""Real-SolidWorks checks for the fixes in PRs #188-#192 and issue #193.

Each test builds geometry whose answer is worked out by hand and asserts
against what SolidWorks measures, so a fix that only satisfies the fake-COM
unit tests fails here. Run against a branch with all of them merged:

* #188  sketch points land where asked (``AddToDB``), and an explicit
        template is used or refused.
* #189  attaching for docs discovery and the start-up COM check never start
        a second SolidWorks.
* #190  sketch patterns work through ``ConnectionPoolAdapter``.
* #191  mid-plane extrusions, the true-distance edge picker (hidden edges,
        ``face:`` specs, points off every edge), sized image export, and
        vertex picks in ``measure_entities``.
* #192  Through All in both directions removes exactly the through-hole,
        through the adapter or the tool's ``both_directions`` field.
* #193  a blind cut from a sketch inside the body cuts one way, and Through
        All one way cuts half the hole.

Geometry: sketches on the Front plane extrude along Z. A 40 x 20 rectangle
extruded mid-plane 12 mm is the block x in [-20, 20], y in [-10, 10],
z in [-6, 6] mm (9600 mm³).

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``). Run with ``SW_TEST_PACE_SECONDS=4``.
"""

from __future__ import annotations

import math
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence

#: A 1 mm fillet on a straight 90° edge removes (1 - pi/4) mm² per mm.
_FILLET_MM2_PER_MM = 1.0 - math.pi / 4.0


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register the modelling tools against ``adapter``; name -> function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("contributor-fixes-live")
    await register_modeling_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _summary(adapter: Any) -> dict[str, Any]:
    """The active model's volume (mm³), box (mm) and body count."""
    result = await adapter.get_model_geometry_summary()
    assert result.is_success, result.error
    return result.data


async def _center_of_mass(adapter: Any) -> list[float]:
    """The active model's centre of mass, in the adapter's units."""
    result = await adapter.get_mass_properties()
    assert result.is_success, result.error
    return list(result.data.center_of_mass)


async def _rectangle_sketch(
    adapter: Any, x1: float, y1: float, x2: float, y2: float
) -> str:
    """A closed rectangle sketch on the Front plane; returns its name."""
    sketch = await adapter.create_sketch("Front")
    assert sketch.is_success, sketch.error
    assert (await adapter.add_rectangle(x1, y1, x2, y2)).is_success
    assert (await adapter.exit_sketch()).is_success
    return sketch.data


async def _midplane_block(adapter: Any, tools: dict[str, Any]) -> None:
    """The 40 x 20 x 12 mm block centred on the origin (see module docstring)."""
    assert (await adapter.create_part()).is_success
    sketch = await _rectangle_sketch(adapter, -20.0, -10.0, 20.0, 10.0)
    boss = await tools["create_extrusion"](
        {"sketch_name": sketch, "depth": 12.0, "both_directions": True}
    )
    assert boss["status"] == "success", boss


def _solidworks_process_count() -> int:
    """Running SLDWORKS.exe processes (tasklist; no COM, never launches)."""
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return sum(1 for line in out.splitlines() if "sldworks.exe" in line.lower())


def _png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG header."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", data[16:24])


# --------------------------------------------------------------------- #188


@pytest.mark.asyncio
async def test_sketch_points_land_where_asked(scratch):
    """A line end 0.29 mm from an earlier vertical stays put (#188).

    The trapezoid (0,0) (5,0) (5.2915,6) (0,6) has area (5 + 5.2915) / 2 x 6
    = 30.8745 mm². Snapped to x=5 by sketch inference it would be a 30 mm²
    rectangle. Drawn line by line, its corners must also join into a closed
    profile, or the extrusion fails: AddToDB must not stop that.
    """
    adapter = scratch.adapter
    tools = await _tools(adapter)
    assert (await adapter.create_part()).is_success
    sketch = await adapter.create_sketch("Front")
    assert sketch.is_success, sketch.error
    corners = [(0.0, 0.0), (5.0, 0.0), (5.2915, 6.0), (0.0, 6.0)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1], strict=True):
        assert (await adapter.add_line(x1, y1, x2, y2)).is_success

    sketch_manager = adapter.currentModel.SketchManager
    assert (await adapter.exit_sketch()).is_success
    # exit_sketch hands the document back with inference on.
    assert not bool(sketch_manager.AddToDB)

    boss = await tools["create_extrusion"]({"sketch_name": sketch.data, "depth": 10.0})
    assert boss["status"] == "success", boss
    summary = await _summary(adapter)
    evidence("trapezoid with a 5.2915 mm corner, extruded 10 mm", summary)
    assert summary["volume_mm3"] == pytest.approx(308.745, abs=0.01)
    assert summary["bounding_box_mm"]["size"][0] == pytest.approx(5.2915, abs=1e-3)


@pytest.mark.asyncio
async def test_create_part_uses_an_explicit_template_and_refuses_a_bad_one(
    scratch, tmp_path
):
    """The template argument reaches SolidWorks, and a bad one is an error (#188)."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    template = adapter._resolve_template_path([8, 0, 1, 2, 3], ".prtdot")
    if not template:
        pytest.skip("No part template is configured in SolidWorks")

    made = await tools["create_part"]({"name": "from-template", "template": template})
    evidence("create_part with an explicit template", made)
    assert made["status"] == "success", made

    not_a_template = tmp_path / "notes.txt"
    not_a_template.write_text("not a template")
    wrong_type = await tools["create_part"](
        {"name": "bad", "template": str(not_a_template)}
    )
    missing = await tools["create_part"](
        {"name": "bad", "template": str(tmp_path / "missing.prtdot")}
    )
    assert wrong_type["status"] == "error", wrong_type
    assert ".prtdot" in wrong_type["message"], wrong_type
    assert missing["status"] == "error", missing
    assert "not found" in missing["message"].lower(), missing


# --------------------------------------------------------------------- #189


@pytest.mark.asyncio
async def test_docs_discovery_and_com_check_attach_without_launching(live_adapter):
    """With SolidWorks open, attaching works and no second instance starts (#189)."""
    from solidworks_mcp.config import SolidWorksMCPConfig
    from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery
    from solidworks_mcp.utils.validation import _validate_solidworks_installation

    before = _solidworks_process_count()
    assert before >= 1

    discovery = SolidWorksDocsDiscovery()
    assert discovery.connect_to_solidworks()
    assert discovery.sw_app is not None
    await _validate_solidworks_installation(SolidWorksMCPConfig())

    assert _solidworks_process_count() == before


# --------------------------------------------------------------------- #190


@pytest.mark.asyncio
async def test_sketch_pattern_works_through_the_connection_pool(scratch):
    """A linear sketch pattern through ConnectionPoolAdapter makes real circles (#190).

    Three Ø4 circles 10 mm apart extruded 5 mm: 3 x pi x 2² x 5 = 188.50 mm³.
    Before the fix the pool answered "not implemented" without touching COM.
    """
    from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

    pool = ConnectionPoolAdapter(
        adapter_factory=lambda: PyWin32Adapter({}), pool_size=1
    )
    await pool.connect()
    try:
        tools = await _tools(pool)
        assert (await pool.create_part()).is_success
        sketch = await pool.create_sketch("Front")
        assert sketch.is_success, sketch.error
        circle = await pool.add_circle(0.0, 0.0, 2.0)
        assert circle.is_success, circle.error
        pattern = await pool.sketch_linear_pattern([circle.data], 1.0, 0.0, 10.0, 3)
        evidence("sketch_linear_pattern through the pool", pattern.data)
        assert pattern.is_success, pattern.error
        assert (await pool.exit_sketch()).is_success

        boss = await tools["create_extrusion"](
            {"sketch_name": sketch.data, "depth": 5.0}
        )
        assert boss["status"] == "success", boss
        summary = await _summary(pool)
        assert summary["volume_mm3"] == pytest.approx(3 * math.pi * 4 * 5, rel=1e-4)
        assert summary["solid_body_count"] == 3
    finally:
        await pool.disconnect()


# --------------------------------------------------------------------- #191


@pytest.mark.asyncio
async def test_both_directions_extrudes_mid_plane(scratch):
    """``both_directions`` centres the block on the sketch plane (#191)."""
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))

    summary = await _summary(adapter)
    center = await _center_of_mass(adapter)
    evidence("40 x 20 rectangle, both_directions, 12 mm", {**summary, "com": center})
    assert summary["volume_mm3"] == pytest.approx(9600.0, rel=1e-6)
    assert summary["bounding_box_mm"]["min"] == pytest.approx([-20, -10, -6], abs=1e-3)
    assert summary["bounding_box_mm"]["max"] == pytest.approx([20, 10, 6], abs=1e-3)
    assert center[2] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_fillet_picks_the_hidden_edge_not_its_twin(scratch):
    """A point on the back edge fillets the back edge (#191).

    Seen from the front, the bottom-back edge (y=-10, z=-6) hides behind the
    bottom-front edge (y=-10, z=+6). Both fillets remove the same volume,
    (1 - pi/4) x 40 = 8.584 mm³, so the side is told by the centre of mass:
    taking material from the back moves it forwards (+z).
    """
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))

    result = await adapter.add_fillet(1.0, ["0,-0.010,-0.006"])
    assert result.is_success, result.error
    summary = await _summary(adapter)
    center = await _center_of_mass(adapter)
    evidence("1 mm fillet on the hidden bottom-back edge", {**summary, "com": center})
    assert 9600.0 - summary["volume_mm3"] == pytest.approx(
        _FILLET_MM2_PER_MM * 40.0, rel=0.01
    )
    assert center[2] > 0


@pytest.mark.asyncio
async def test_face_fillet_rounds_the_face_edges(scratch):
    """``face:`` fillets the edges around the front face and moves mass back (#191).

    The four edges around the z=+6 face total 120 mm, so the removed volume
    is about (1 - pi/4) x 120 = 25.75 mm³, a little less where the fillets
    meet at the corners. Before the fix SolidWorks built nothing and the tool
    still reported success.
    """
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))

    result = await adapter.add_fillet(1.0, ["face:0,0,0.006"])
    assert result.is_success, result.error
    removed = 9600.0 - (await _summary(adapter))["volume_mm3"]
    center = await _center_of_mass(adapter)
    evidence("face: fillet on the front face", {"removed_mm3": removed, "com": center})
    assert 20.0 < removed < 26.0
    assert center[2] < 0


@pytest.mark.asyncio
async def test_a_point_off_every_edge_is_refused(scratch):
    """A fillet point 44 mm from the block is an error, not a guess (#191)."""
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))

    result = await adapter.add_fillet(1.0, ["0,0,0.050"])
    evidence("fillet at a point off every edge", {"error": result.error})
    assert not result.is_success
    assert (await _summary(adapter))["volume_mm3"] == pytest.approx(9600.0, rel=1e-9)


@pytest.mark.asyncio
async def test_measure_picks_vertices_not_edges(scratch):
    """``vertex:`` specs measure between opposite corners (#191 review).

    Corner to corner is sqrt(40² + 20² + 12²) = 46.19 mm. If the picker
    resolved the points to edges through them instead, the distance would be
    one of the edge-to-edge distances (23.3, 41.8 or 44.7 mm and smaller), never
    46.19 mm: those are the only edges through either corner.
    """
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))

    result = await adapter.measure_entities(
        ["vertex:-0.020,-0.010,0.006", "vertex:0.020,0.010,-0.006"]
    )
    evidence("measure between two corners", result.data or {"error": result.error})
    assert result.is_success, result.error
    assert result.data["distance_m"] == pytest.approx(
        math.sqrt(40**2 + 20**2 + 12**2) / 1000, abs=1e-6
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(640, 480), (400, 600)])
async def test_export_image_writes_the_requested_size(scratch, tmp_path, size):
    """The PNG on disk has the requested width and height (#191)."""
    adapter = scratch.adapter
    await _midplane_block(adapter, await _tools(adapter))
    width, height = size
    target = tmp_path / f"block_{width}x{height}.png"
    scratch.written_files.append(str(target))

    result = await adapter.export_image(
        {"file_path": str(target), "width": width, "height": height}
    )
    evidence(f"export_image {width}x{height}", result.data or {"error": result.error})
    assert result.is_success, result.error
    assert _png_size(target) == (width, height)
    assert result.data["dimensions"] == f"{width}x{height}"


# --------------------------------------------------------------------- #192


async def _through_hole_block(adapter: Any, tools: dict[str, Any]) -> str:
    """A 20 x 20 x 10 mm block centred on Front, and a Ø4 circle sketch on Front."""
    assert (await adapter.create_part()).is_success
    block = await _rectangle_sketch(adapter, -10.0, -10.0, 10.0, 10.0)
    boss = await tools["create_extrusion"](
        {"sketch_name": block, "depth": 10.0, "both_directions": True}
    )
    assert boss["status"] == "success", boss
    sketch = await adapter.create_sketch("Front")
    assert sketch.is_success, sketch.error
    assert (await adapter.add_circle(0.0, 0.0, 2.0)).is_success
    assert (await adapter.exit_sketch()).is_success
    return sketch.data


_HOLE_MM3 = math.pi * 2.0**2 * 10.0


@pytest.mark.asyncio
async def test_through_all_both_cuts_the_whole_hole(scratch):
    """ThroughAllBoth from the mid plane removes pi x 2² x 10 = 125.66 mm³ (#192)."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    sketch = await _through_hole_block(adapter, tools)

    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 1.0, "end_condition": "ThroughAllBoth"}
    )
    assert cut["status"] == "success", cut
    removed = 4000.0 - (await _summary(adapter))["volume_mm3"]
    center = await _center_of_mass(adapter)
    evidence("Ø4 cut Through All both ways", {"removed_mm3": removed, "com": center})
    assert removed == pytest.approx(_HOLE_MM3, rel=1e-6)
    assert center[2] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_through_all_with_both_directions_matches(scratch):
    """``ThroughAll`` + ``both_directions`` through the MCP tool cuts both ways (#192)."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    sketch = await _through_hole_block(adapter, tools)

    cut = await tools["create_cut_extrude"](
        {
            "sketch_name": sketch,
            "depth": 1.0,
            "end_condition": "ThroughAll",
            "both_directions": True,
        }
    )
    assert cut["status"] == "success", cut
    removed = 4000.0 - (await _summary(adapter))["volume_mm3"]
    assert removed == pytest.approx(_HOLE_MM3, rel=1e-6)


@pytest.mark.asyncio
async def test_through_all_cuts_one_way(scratch):
    """Through All from the mid plane cuts one half: pi x 2² x 5 = 62.83 mm³."""
    adapter = scratch.adapter
    tools = await _tools(adapter)
    sketch = await _through_hole_block(adapter, tools)

    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 1.0, "end_condition": "ThroughAll"}
    )
    assert cut["status"] == "success", cut
    removed = 4000.0 - (await _summary(adapter))["volume_mm3"]
    evidence("Ø4 cut Through All one way", {"removed_mm3": removed})
    assert removed == pytest.approx(_HOLE_MM3 / 2, rel=1e-6)


@pytest.mark.asyncio
async def test_blind_cut_still_cuts_one_way(scratch):
    """A 3 mm blind cut from a sketch inside the body removes pi x 2² x 3 = 37.70 mm³.

    Before #193 was fixed this returned no feature on SW 2025+: the cut was
    sent as double-ended (Sd=False) with a zero-depth Direction 2.
    """
    adapter = scratch.adapter
    tools = await _tools(adapter)
    sketch = await _through_hole_block(adapter, tools)

    cut = await tools["create_cut_extrude"]({"sketch_name": sketch, "depth": 3.0})
    assert cut["status"] == "success", cut
    removed = 4000.0 - (await _summary(adapter))["volume_mm3"]
    assert removed == pytest.approx(math.pi * 4.0 * 3.0, rel=1e-6)
