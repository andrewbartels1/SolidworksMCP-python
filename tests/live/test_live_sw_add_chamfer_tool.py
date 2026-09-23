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

Whole-face selection, not single-edge coordinates
--------------------------------------------------
An earlier version of this suite targeted the hole's rim edge directly by
coordinate (``"0.01775,0.015,0.0"``). That coordinate sits exactly on the
shared boundary between the hole's cylindrical wall and the block's flat
top face. Live testing (2026-09-18) proved it was silently resolving to
the **wrong** edge: the measured volume removed by "chamfering the hole
rim" matched the formula for a straight 30mm block edge (3.75 mm³) almost
exactly, not the circular hole rim's expected ~2.29 mm³. The chamfer
reported success and looked structurally fine (a real "Chamfer1" feature,
real volume removed) while silently working on the wrong geometry — worse
than the earlier zero-volume no-op bug, because a non-zero volume delta
alone isn't enough to catch it.

The fix (also applied in ``_parse_edge_spec``/``_select_edge_by_coord``,
``features.py``): ``edge_names`` entries now accept a ``"face:x,y,z"``
prefix to select a whole face instead of hunting for one edge by nearest-
point coordinate. ``InsertFeatureChamfer``/``FeatureFillet3`` then
chamfer/fillet every edge bounding that face — for the hole, that is
exactly its one rim edge; for the top face as a whole, it's the hole rim
*and* the four 30mm outer edges in a single, unambiguous feature. A point
safely inside a face's interior has no boundary-sharing ambiguity the way
an edge coordinate does.

Chamfer (top face, which carries the hole) and fillet (bottom face) are
also kept on different faces rather than crowded near each other: a real
part uses one treatment or the other on a given region, and this also
sidesteps a related, separate live-confirmed bug — after one edge/face
feature is added, an unrelated edge's coordinate-based nearest-point match
can shift by as much as 1mm normal to the search plane, so a coordinate
that resolved correctly before another feature was added may resolve
differently (or to nothing) afterward. Face selection on a distinct,
already-flat face is not subject to that shift.

Note on what "success" actually means here: a prior implementation
(``IModelDoc2::FeatureChamferType``, gated to SW 2025+) was found live
(2026-09-18) to report success and add a real "Chamfer1" entry to the
feature tree while removing **zero volume** — a silent no-op. The whole-
face bug above is a second, independent way "success" can be misleading:
real volume removed, wrong geometry. Neither the tool's reported status,
the feature name, nor "some volume changed" is sufficient proof on its
own — these tests check the *feature is present*, *volume decreased*, and
compare the decrease against a geometrically-derived expectation (not just
"less than before") wherever precision is cheap enough to compute.

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).
"""

from __future__ import annotations

import math

import pytest

_TOP_FACE = "face:0.005,0.005,0.0"  # top 30x30mm face; carries the hole
_BOTTOM_FACE = "face:0.005,0.005,-0.015"  # bottom 30x30mm face
_VERTICAL_CORNER_EDGE = "0.0,0.0,-0.0075"  # a block corner edge, unambiguous

_HOLE_RADIUS_MM = 2.75
_BLOCK_EDGE_LENGTH_MM = 30.0


def _expected_circular_chamfer_volume(radius_mm: float, width_mm: float) -> float:
    """Volume removed widening a circular hole's rim by a 45deg equal-distance chamfer."""
    r, w = radius_mm, width_mm
    return math.pi * (((r + w) ** 3 - r**3) / 3.0 - r * r * w)


def _expected_straight_chamfer_volume(length_mm: float, width_mm: float) -> float:
    """Volume removed by a 45deg equal-distance chamfer along one straight edge."""
    return 0.5 * width_mm * width_mm * length_mm


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
async def test_add_chamfer_tool_whole_top_face(scratch):
    """The realistic case: a lead-in chamfer on the whole top face (the
    hole rim plus the block's outer perimeter), called through the actual
    registered MCP tool via ``"face:x,y,z"`` — not a coordinate aimed at a
    single edge, which was proven to silently land on the wrong edge for a
    boundary-shared edge like this hole's rim.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    mp_before = await adapter.get_mass_properties()
    assert mp_before.is_success, mp_before.error

    response = await add_chamfer(
        AddChamferInput(distance=0.5, edge_names=[_TOP_FACE])
    )
    assert response["status"] == "success", response
    assert response["chamfer"]["distance"] == 0.5
    assert response["chamfer"]["name"] == "Chamfer1"

    features = await adapter.list_features()
    assert features.is_success
    assert any(f["name"] == response["chamfer"]["name"] for f in features.data)

    # The whole top face = the hole rim + 4 outer 30mm edges. Corner overlap
    # between adjacent chamfered edges means the true value is a little
    # below the naive sum, so assert a safe lower bound rather than an
    # exact match -- the point is confirming it's the *combined* geometry,
    # not just one edge's worth (which would be ~2.29 or ~3.75 mm^3 alone).
    naive_expected = _expected_circular_chamfer_volume(
        _HOLE_RADIUS_MM, 0.5
    ) + 4 * _expected_straight_chamfer_volume(_BLOCK_EDGE_LENGTH_MM, 0.5)

    mp_after = await adapter.get_mass_properties()
    assert mp_after.is_success, mp_after.error
    removed = mp_before.data.volume - mp_after.data.volume
    assert removed > naive_expected * 0.8, (
        "add_chamfer on the whole top face removed far less material than "
        f"expected for the hole rim + 4 outer edges combined: removed="
        f"{removed:.4f} mm^3, naive expectation={naive_expected:.4f} mm^3. "
        "This is the exact failure shape of a chamfer silently landing on "
        "the wrong edge instead of the whole face."
    )


@pytest.mark.asyncio
async def test_add_chamfer_tool_multiple_entries_mixed_face_and_edge(scratch):
    """``edge_names`` with more than one entry, mixing a ``"face:"`` entry
    and a plain coordinate-edge entry, chamfers all of them in one feature
    — verifies the append-selection loop works across mixed syntaxes.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    mp_before = await adapter.get_mass_properties()
    assert mp_before.is_success, mp_before.error

    response = await add_chamfer(
        AddChamferInput(
            distance=0.5, edge_names=[_TOP_FACE, _VERTICAL_CORNER_EDGE]
        )
    )
    assert response["status"] == "success", response
    assert response["chamfer"]["edges"] == [_TOP_FACE, _VERTICAL_CORNER_EDGE]

    features = await adapter.list_features()
    assert features.is_success
    assert any(f["name"] == response["chamfer"]["name"] for f in features.data)

    mp_after = await adapter.get_mass_properties()
    assert mp_after.is_success, mp_after.error
    assert mp_after.data.volume < mp_before.data.volume, (
        "add_chamfer with a mixed face+edge entry list reported success but "
        f"removed no material (before={mp_before.data.volume}, after={mp_after.data.volume})"
    )


@pytest.mark.asyncio
async def test_add_chamfer_and_add_fillet_on_different_largest_faces(scratch):
    """A real part uses chamfer OR fillet on a given region, not both — this
    demonstrates the two tools applied to the two distinct largest
    (30x30mm) faces via whole-face selection: a lead-in chamfer on the top
    face (hole rim + outer edges) and a fillet on the bottom face's outer
    edges.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    mp_before = await adapter.get_mass_properties()
    assert mp_before.is_success, mp_before.error

    chamfer_response = await add_chamfer(
        AddChamferInput(distance=0.5, edge_names=[_TOP_FACE])
    )
    assert chamfer_response["status"] == "success", chamfer_response

    fillet_result = await adapter.add_fillet(radius=1.0, edge_names=[_BOTTOM_FACE])
    assert fillet_result.is_success, fillet_result.error

    features = await adapter.list_features()
    assert features.is_success
    names = [f["name"] for f in features.data]
    assert any("Chamfer" in n for n in names), names
    assert any("Fillet" in n for n in names), names

    mp_after = await adapter.get_mass_properties()
    assert mp_after.is_success, mp_after.error
    assert mp_after.data.volume < mp_before.data.volume, (
        "chamfer + fillet on the two largest faces reported success but "
        f"removed no material (before={mp_before.data.volume}, "
        f"after={mp_after.data.volume})"
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
    """One good (whole-face) entry plus one bad entry in the same call must
    still fail as a whole — the tool must not silently create a partial
    chamfer.
    """
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await _heat_insert_coupon(adapter)
    add_chamfer = await _add_chamfer_tool(adapter)

    response = await add_chamfer(
        AddChamferInput(
            distance=0.5,
            edge_names=[_TOP_FACE, "Edge_that_does_not_exist<99>"],
        )
    )
    assert response["status"] == "error"

    features = await adapter.list_features()
    assert features.is_success
    assert not any("Chamfer" in f["name"] for f in features.data)
