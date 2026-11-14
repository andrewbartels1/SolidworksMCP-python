"""The monitor-stand follow-ups (issue #206), checked on real SolidWorks.

One bundle, run together after the work is done, then failures are fixed one
at a time:

1. ``list_features`` comes back in tree order, and ``verify_model`` counts
   ``Plane1`` and not ``Front Plane``;
2. a diagnostic of the dimension listing on the monitor stand: how many
   features the old forward-only walk and the shared walk find, and whether
   the full listing holds every dimension the per-feature calls find;
3. ``export_stl`` writes through ``SaveAs2`` with its options (no warning);
4. ``create_sketch`` on a face: the top face works, a point in the air and
   a point on a fillet are refused with ``invalid_input``.

The follow-the-height rebuild is in ``test_live_sw_monitor_stand_demo.py``
(``test_the_pocket_follows_a_raised_height``).

Run one with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_monitor_stand_follow_ups.py::test_feature_order_and_verify_model_with_a_plane

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.live.evidence import evidence
from tests.live.test_live_sw_beta_tools import _sketch
from tests.live.test_live_sw_monitor_stand_demo import _load_script

pytestmark = pytest.mark.asyncio

#: The test block: 40 x 40 mm on the Top Plane, 20 mm tall (top face at y = 20).
_HALF = 20.0
_HEIGHT = 20.0


async def _tools(adapter: Any) -> dict[str, Any]:
    """The tool families these tests use, registered on ``adapter``; name -> fn."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.engineering_data import register_engineering_data_tools
    from solidworks_mcp.tools.export import register_export_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("monitor-stand-follow-ups-live")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_analysis_tools,
        register_engineering_data_tools,
        register_file_management_tools,
        register_export_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _block(tools: dict[str, Any]) -> None:
    """A new part holding the 40 x 40 x 20 mm test block."""
    assert (await tools["create_part"]({"name": "follow_ups"}))["status"] == "success"
    await _sketch(tools, "Top", {"x1": -_HALF, "y1": -_HALF, "x2": _HALF, "y2": _HALF})
    made = await tools["create_extrusion"]({"depth": _HEIGHT})
    assert made["status"] == "success", made


async def _block_with_a_plane_and_a_cut(tools: dict[str, Any]) -> str:
    """The block, ``Plane1`` on its top, and a 10 x 10 x 3 mm cut on Plane1."""
    await _block(tools)
    plane = await tools["create_reference_plane"](
        {"reference": "Top Plane", "offset": _HEIGHT}
    )
    assert plane["status"] == "success", plane
    plane_name = str(plane["plane"]["name"])
    sketch = await _sketch(tools, plane_name, {"x1": -5, "y1": -5, "x2": 5, "y2": 5})
    cut = await tools["create_cut_extrude"](
        {"sketch_name": sketch, "depth": 3, "end_condition": "Blind"}
    )
    assert cut["status"] == "success", cut
    return plane_name


async def test_feature_order_and_verify_model_with_a_plane(scratch: Any) -> None:
    """Rows in tree order; the agent's plane is counted, Front Plane is not."""
    tools = await _tools(scratch.adapter)
    plane_name = await _block_with_a_plane_and_a_cut(tools)

    listed = await tools["list_features"]({})
    rows = [r for r in listed["features"] if r.get("component") is None]
    names = [r["name"] for r in rows]
    positions = [r["position"] for r in rows]
    verified = await tools["verify_model"]({"feature_count": 3})

    evidence(
        "list_features order, and verify_model's counted features",
        {
            "names": names,
            "positions": positions,
            "counted": verified["measured"].get("features"),
            "verdict": verified["verdict"],
        },
    )
    assert positions == sorted(positions)
    assert names.index("Front Plane") < names.index(plane_name)
    assert names.index(plane_name) < names.index("Cut-Extrude1")
    assert verified["verdict"] == "pass", verified
    assert plane_name in verified["measured"]["features"]
    assert "Front Plane" not in verified["measured"]["features"]


def _forward_walk_count(adapter: Any) -> int:
    """How many features the old forward-only walk reaches (test-side COM)."""
    from solidworks_mcp.adapters import sw_type_info

    count = 0
    feature = adapter._attempt(lambda: adapter.currentModel.FirstFeature())
    while feature is not None and count < 10000:
        count += 1
        flagged = sw_type_info.flagged(feature, "IFeature")
        feature = adapter._attempt(lambda f=flagged: f.GetNextFeature())
    return count


async def test_dimension_listing_on_the_monitor_stand(
    scratch: Any, tmp_path: Path
) -> None:
    """The full listing holds every dimension the per-feature calls find."""
    from solidworks_mcp.adapters.solidworks.feature_walk import walk_feature_tree

    script = _load_script()
    adapter = scratch.adapter
    out = tmp_path / "StandDims.SLDPRT"
    scratch.written_files.append(str(out))
    await script.build(
        script.Stand(),
        out,
        replace=False,
        stl=False,
        call=script.Session(await script._tools(adapter)),
    )
    tools = await _tools(adapter)

    walked = walk_feature_tree(adapter, adapter.currentModel)
    full = await tools["list_model_dimensions"]({})
    per_feature: dict[str, list[str]] = {}
    for item in walked:
        one = await tools["list_model_dimensions"]({"feature_name": item.name})
        if one["status"] == "success":
            per_feature[item.name] = [d["full_name"] for d in one["data"]]

    full_names = [d["full_name"] for d in full["data"]]
    found_by_features = {n for names in per_feature.values() for n in names}
    evidence(
        "dimension listing: old walk vs shared walk, full vs per feature",
        {
            "old_forward_walk_features": _forward_walk_count(adapter),
            "shared_walk_features": len(walked),
            "full_listing": full_names,
            "per_feature": per_feature,
        },
    )
    assert full["status"] == "success", full
    assert len(full_names) == len(set(full_names)), "a dimension is listed twice"
    assert found_by_features <= set(full_names)
    for row in full["data"]:
        if row["full_name"] and "@" in row["full_name"]:
            assert row["feature"] == row["full_name"].split("@", 1)[1], row


async def test_export_stl_uses_its_options(scratch: Any, tmp_path: Path) -> None:
    """The STL is written by SaveAs2 with its options: no fallback warning."""
    tools = await _tools(scratch.adapter)
    await _block(tools)
    out = tmp_path / "block.stl"
    scratch.written_files.append(str(out))

    exported = await tools["export_stl"]({"file_path": str(out)})

    evidence(
        "export_stl",
        {
            "status": exported["status"],
            "size_bytes": out.stat().st_size if out.exists() else None,
            "warning": exported.get("warning"),
        },
        call=f'export_stl({{"file_path": "{out.name}"}})',
    )
    assert exported["status"] == "success", exported
    assert out.stat().st_size > 0
    assert "warning" not in exported, exported["warning"]


async def test_create_sketch_on_a_face(scratch: Any) -> None:
    """The top face takes a sketch; the air and a fillet are refused."""
    tools = await _tools(scratch.adapter)
    await _block(tools)

    on_top = await tools["create_sketch"]({"face_point": [0, _HEIGHT, 0]})
    assert on_top["status"] == "success", on_top
    assert (await tools["add_rectangle"]({"x1": -5, "y1": -5, "x2": 5, "y2": 5}))[
        "status"
    ] == "success"
    closed = await tools["exit_sketch"]()
    assert closed["status"] == "success", closed
    cut = await tools["create_cut_extrude"](
        {"sketch_name": on_top["sketch"]["name"], "depth": 3, "end_condition": "Blind"}
    )
    in_air = await tools["create_sketch"]({"face_point": [0, _HEIGHT + 50, 0]})

    # Round one vertical corner (x = z = 20), then point at the fillet's middle.
    fillet = await tools["add_fillet"](
        {"radius": 5, "edge_names": [f"{_HALF / 1000},{_HEIGHT / 2000},{_HALF / 1000}"]}
    )
    assert fillet["status"] == "success", fillet
    on_fillet_mm = _HALF - 5 + 5 * 0.7071068
    on_fillet = await tools["create_sketch"](
        {"face_point": [on_fillet_mm, _HEIGHT / 2, on_fillet_mm]}
    )

    evidence(
        "create_sketch on a face: the top, the air, a fillet",
        {
            "top": on_top["message"],
            "cut_volume_delta_mm3": (cut.get("measured_change") or {}).get(
                "volume_delta_mm3"
            ),
            "air": [in_air["status"], in_air.get("error_type"), in_air["message"]],
            "fillet": [
                on_fillet["status"],
                on_fillet.get("error_type"),
                on_fillet["message"],
            ],
        },
    )
    assert cut["status"] == "success", cut
    assert cut["measured_change"]["volume_delta_mm3"] == pytest.approx(-300, rel=1e-3)
    assert in_air["status"] == "error"
    assert in_air["error_type"] == "invalid_input"
    assert on_fillet["status"] == "error"
    assert on_fillet["error_type"] == "invalid_input"
    assert "not flat" in on_fillet["message"]
