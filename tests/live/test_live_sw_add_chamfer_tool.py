"""Real-SolidWorks regression tests for the add_chamfer MCP tool (issue #104).

The adapter's ``_add_chamfer_impl`` was already live-proven by
``scripts/demo_features.py``. What issue #104 actually added was the
``@mcp.tool()`` wrapper (``AddChamferInput`` -> ``add_chamfer`` in
``modeling.py``) plus the previously-missing pass-through on
``CircuitBreakerAdapter``/``ConnectionPoolAdapter`` and the base-adapter
default. These tests exercise the *tool* surface directly — the same
``AddChamferInput(distance, edge_names)`` args an MCP client actually
sends — against a real SolidWorks session, using the M4 heat-set-insert
validation coupon (30x30x15mm block, centered Ø5.5mm hole) from the
original bug report.

Edge coordinates below were confirmed against a live session before being
hardcoded here (coordinate-based selection is used throughout, not
topology names like "Edge<1>", since topology names vary across SW
versions and rebuild order — see ``scripts/demo_features.py``):

- Block top outer edge (mid-side, Y=0): (0.015, 0.0, 0.0)
- Hole rim edge (top opening, +X side): (0.01775, 0.015, 0.0)

Note on what "success" actually means here: a prior implementation
(``IModelDoc2::FeatureChamferType``, gated to SW 2025+) was found live
(2026-09-18) to report success and add a real "Chamfer1" entry to the
feature tree while removing **zero volume** — a silent no-op, not a real
chamfer. Detecting that required checking actual geometry (mass-properties
volume), not just the tool's reported status or the feature tree. The tests
below assert both: a real feature is added *and* material was actually
removed, specifically to catch a regression of that bug shape (feature
"created" but geometrically inert).

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).
"""

from __future__ import annotations

import pytest

_BLOCK_TOP_EDGE = "0.015,0.0,0.0"
_HOLE_RIM_EDGE = "0.01775,0.015,0.0"


async def _heat_insert_coupon(adapter) -> None:  # noqa: ANN001
    """Build the M4 heat-set-insert validation coupon: 30x30x15mm block,
    centered Ø5.5mm hole cut 6mm deep. Mirrors
    ``scripts/build_m4_heat_insert_coupon.py`` and the cut-extrude live
    regression helper.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    assert (await adapter.create_part()).is_success

    assert (await adapter.create_sketch("Top")).is_success
    bottom = await adapter.add_line(0, 0, 30, 0)
    assert bottom.is_success
    left = await adapter.add_line(0, 30, 0, 0)
    assert left.is_success
    assert (await adapter.add_line(30, 0, 30, 30)).is_success
    assert (await adapter.add_line(30, 30, 0, 30)).is_success

    width_dim = await adapter.add_sketch_dimension(bottom.data, None, "linear", 30.0)
    assert width_dim.is_success, width_dim.error
    height_dim = await adapter.add_sketch_dimension(left.data, None, "linear", 30.0)
    assert height_dim.is_success, height_dim.error

    assert (await adapter.exit_sketch()).is_success
    boss = await adapter.create_extrusion(ExtrusionParameters(depth=15.0))
    assert boss.is_success, boss.error

    assert (await adapter.create_sketch("Top")).is_success
    circle = await adapter.add_circle(15.0, 15.0, 2.75)
    assert circle.is_success, circle.error
    diameter_dim = await adapter.add_sketch_dimension(
        circle.data, None, "diameter", 5.5
    )
    assert diameter_dim.is_success, diameter_dim.error
    assert (await adapter.exit_sketch()).is_success

    features = await adapter.list_features()
    assert features.is_success, features.error
    sketch_names = [
        f["name"] for f in features.data if f.get("type") == "ProfileFeature"
    ]
    unconsumed = [n for n in sketch_names if n != "Sketch1"]
    assert len(unconsumed) == 1, f"expected one unconsumed sketch, got {sketch_names}"
    hole_sketch_name = unconsumed[0]

    cut = await adapter.create_cut_extrude(
        ExtrusionParameters(depth=6.0, sketch_name=hole_sketch_name)
    )
    assert cut.is_success, cut.error


async def _add_chamfer_tool(adapter):  # noqa: ANN001
    """Register modeling tools against ``adapter`` and return the callable
    ``add_chamfer`` tool function — the exact code path an MCP client hits.
    """
    from fastmcp import FastMCP

    from solidworks_mcp.tools.modeling import register_modeling_tools

    mcp = FastMCP("add-chamfer-live-test")
    await register_modeling_tools(mcp, adapter, {})
    tools = {t.name: t.fn for t in await mcp.list_tools()}
    assert "add_chamfer" in tools, "add_chamfer tool did not register"
    return tools["add_chamfer"]


@pytest.mark.asyncio
async def test_add_chamfer_tool_single_edge_on_heat_insert_hole_rim(scratch):
    """The realistic single-edge case: a lead-in chamfer on the insert hole's
    top rim, called through the actual registered MCP tool (not just the
    adapter function).
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    mp_before = await adapter.get_mass_properties()
    assert mp_before.is_success, mp_before.error

    response = await add_chamfer(
        AddChamferInput(distance=0.5, edge_names=[_HOLE_RIM_EDGE])
    )
    assert response["status"] == "success", response
    assert response["chamfer"]["distance"] == 0.5
    assert response["chamfer"]["edges"] == [_HOLE_RIM_EDGE]
    assert response["chamfer"]["name"] == "Chamfer1"

    features = await adapter.list_features()
    assert features.is_success
    assert any(f["name"] == response["chamfer"]["name"] for f in features.data)

    # The critical check: real material must actually be removed. A prior
    # implementation reported this exact success shape while cutting nothing.
    mp_after = await adapter.get_mass_properties()
    assert mp_after.is_success, mp_after.error
    assert mp_after.data.volume < mp_before.data.volume, (
        "add_chamfer reported success and added a tree entry, but no "
        f"material was removed (before={mp_before.data.volume}, "
        f"after={mp_after.data.volume})"
    )


@pytest.mark.asyncio
async def test_add_chamfer_tool_multiple_edges_in_one_call(scratch):
    """``edge_names`` with more than one entry chamfers every edge in a
    single feature — verifies the append-selection loop, not just a
    single-edge selection.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    mp_before = await adapter.get_mass_properties()
    assert mp_before.is_success, mp_before.error

    response = await add_chamfer(
        AddChamferInput(
            distance=0.3, edge_names=[_BLOCK_TOP_EDGE, _HOLE_RIM_EDGE]
        )
    )
    assert response["status"] == "success", response
    assert response["chamfer"]["edges"] == [_BLOCK_TOP_EDGE, _HOLE_RIM_EDGE]

    features = await adapter.list_features()
    assert features.is_success
    assert any(f["name"] == response["chamfer"]["name"] for f in features.data)

    mp_after = await adapter.get_mass_properties()
    assert mp_after.is_success, mp_after.error
    assert mp_after.data.volume < mp_before.data.volume, (
        "add_chamfer with multiple edges reported success but removed no "
        f"material (before={mp_before.data.volume}, after={mp_after.data.volume})"
    )


@pytest.mark.asyncio
async def test_add_chamfer_tool_unresolvable_edge_fails_clearly(scratch):
    """An edge_names entry that doesn't resolve to any real edge must fail
    with a descriptive error through the tool, not crash or silently no-op.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    response = await add_chamfer(
        AddChamferInput(distance=0.5, edge_names=["Edge_that_does_not_exist<99>"])
    )
    assert response["status"] == "error"
    assert "Edge_that_does_not_exist<99>" in response["message"]

    # And nothing was actually created.
    features = await adapter.list_features()
    assert features.is_success
    assert not any("Chamfer" in f["name"] for f in features.data)


@pytest.mark.asyncio
async def test_add_chamfer_tool_partial_edge_list_fails_before_creating_anything(
    scratch,
):
    """One good edge plus one bad edge in the same call must still fail as a
    whole — the tool must not silently create a partial chamfer.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    response = await add_chamfer(
        AddChamferInput(
            distance=0.5,
            edge_names=[_HOLE_RIM_EDGE, "Edge_that_does_not_exist<99>"],
        )
    )
    assert response["status"] == "error"

    features = await adapter.list_features()
    assert features.is_success
    assert not any("Chamfer" in f["name"] for f in features.data)
