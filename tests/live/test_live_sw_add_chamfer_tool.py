"""Real-SolidWorks tests: add_chamfer and add_fillet treat exactly what they're given (#104, #199).

Each test here builds the M4 heat-set-insert coupon (``tests/live/coupon.py``:
a 30x30x15 mm block with a centred Ø5.5 mm hole), creates one real chamfer
or fillet, and checks the material removed against the exact volume for the
edges it means to treat, within 0.001 mm³. A treatment on the wrong face,
or on one edge too many or too few, misses by far more than that. The
calls that should be refused are in ``test_live_sw_edge_pick_refusals.py``.

What an ``edge_names`` entry treats
-----------------------------------
- A face point (``"face:x,y,z"``, in metres) treats every edge bounding the
  face it lies on, in one feature. For the face the hole opens onto, that is
  the hole rim and the face's four 30 mm edges.
- An edge point (``"x,y,z"``) treats the one edge it lies on.

The exact volumes
-----------------
- A 45° chamfer of width ``w`` along a straight edge of length ``L``:
  ``w²·L/2``. Around a hole of radius ``r``:
  ``π·(((r + w)³ − r³)/3 − r²·w)``.
- A fillet of radius ``R`` along a straight edge: ``(1 − π/4)·R²·L``.
- Where two chamfered edges meet at a square corner they mitre, and the
  corner's ``w³/3`` is removed once, not twice.

Only cases whose geometry is certain are checked. Three chamfers meeting at
one corner, and fillets meeting at a corner, came out 0.010 mm³ and
0.103 mm³ from the simple models of those corners, so they aren't used.

Where the points come from
--------------------------
The coupon is sketched on the Top Plane and extruded 15 mm, so its height
runs along Y. Earlier versions of these tests hard-coded points that
assumed Z, and chamfered a side face where they meant the hole face (#199).
An older note here said an edge point aimed at the hole rim
(``"0.01775,0.015,0.0"``) "silently landed on a 30 mm outer edge". That
point is at y = 15, z = 0: on that outer edge. The pick did what it was
told; the test's axes were wrong. So every point is now derived from the
measured bounding box.

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live import coupon
from tests.live.evidence import evidence

_CHAMFER_MM = 0.5
_FILLET_MM = 1.0

#: The hole rim plus the hole face's four 30 mm edges, which meet at four
#: corners: 17.1241 mm³.
_HOLE_FACE_CHAMFER = (
    coupon.circular_chamfer_volume(coupon.HOLE_RADIUS_MM, _CHAMFER_MM)
    + 4 * coupon.straight_chamfer_volume(coupon.EDGE_MM, _CHAMFER_MM)
    - 4 * coupon.chamfer_corner_overlap(_CHAMFER_MM)
)
#: A side face's two 30 mm and two 15 mm edges, four corners: 11.0833 mm³.
_SIDE_FACE_CHAMFER = (
    2 * coupon.straight_chamfer_volume(coupon.EDGE_MM, _CHAMFER_MM)
    + 2 * coupon.straight_chamfer_volume(coupon.HEIGHT_MM, _CHAMFER_MM)
    - 4 * coupon.chamfer_corner_overlap(_CHAMFER_MM)
)
#: One 30 mm edge with no treated neighbour, chamfered: 3.75 mm³.
_ONE_EDGE_CHAMFER = coupon.straight_chamfer_volume(coupon.EDGE_MM, _CHAMFER_MM)
#: One 30 mm edge with no treated neighbour, filleted: 6.4381 mm³.
_ONE_EDGE_FILLET = coupon.straight_fillet_volume(coupon.EDGE_MM, _FILLET_MM)


def _assert_volume(what: str, removed: float, expected: float) -> None:
    """Check a removed volume against its exact value.

    Args:
        what: What was treated, for the failure message.
        removed: The measured removed volume in mm³.
        expected: The exact volume for the edges meant to be treated, in mm³.
    """
    assert removed == pytest.approx(expected, abs=coupon.VOLUME_TOLERANCE_MM3), (
        f"{what} removed {removed:.4f} mm^3; the exact value is "
        f"{expected:.4f} mm^3 (within {coupon.VOLUME_TOLERANCE_MM3} mm^3)."
    )


def _removal(removed: float, expected: float) -> dict[str, float]:
    """The evidence line for a removal: measured, exact and the difference."""
    return {
        "removed": round(removed, 4),
        "exact": round(expected, 4),
        "difference": round(removed - expected, 4),
    }


async def _built(adapter: Any) -> coupon.Coupon:
    """Build the coupon and show its box and derived points as evidence."""
    part = await coupon.build(adapter)
    evidence(
        "The coupon as built: its points come from this box",
        {"bounding_box_mm": part.box, **part.points()},
        quick=True,
    )
    return part


@pytest.mark.asyncio
async def test_a_chamfer_on_the_hole_face(scratch: Any) -> None:
    """A face point on the hole face chamfers the hole rim and its four edges."""
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    part = await _built(adapter)
    add_chamfer = await coupon.add_chamfer_tool(adapter)

    before = await coupon.volume(adapter)
    response = await add_chamfer(
        AddChamferInput(distance=_CHAMFER_MM, edge_names=[part.hole_face])
    )
    removed = before - await coupon.volume(adapter)
    evidence(
        "Chamfer on the hole face: the rim and four 30 mm edges (mm^3)",
        _removal(removed, _HOLE_FACE_CHAMFER),
    )

    assert response["status"] == "success", response
    assert response["chamfer"]["distance"] == _CHAMFER_MM
    assert response["chamfer"]["name"] in await coupon.feature_names(adapter)
    _assert_volume("A chamfer on the hole face", removed, _HOLE_FACE_CHAMFER)


@pytest.mark.asyncio
async def test_a_chamfer_on_a_side_face(scratch: Any) -> None:
    """A face point on a 30x15 mm side face chamfers only that face's four edges."""
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    part = await _built(adapter)
    add_chamfer = await coupon.add_chamfer_tool(adapter)

    before = await coupon.volume(adapter)
    response = await add_chamfer(
        AddChamferInput(distance=_CHAMFER_MM, edge_names=[part.side_face])
    )
    removed = before - await coupon.volume(adapter)
    evidence(
        "Chamfer on a side face: two 30 mm and two 15 mm edges (mm^3)",
        _removal(removed, _SIDE_FACE_CHAMFER),
    )

    assert response["status"] == "success", response
    assert response["chamfer"]["name"] in await coupon.feature_names(adapter)
    _assert_volume("A chamfer on a side face", removed, _SIDE_FACE_CHAMFER)


@pytest.mark.asyncio
async def test_a_chamfer_on_a_face_and_an_edge_together(scratch: Any) -> None:
    """A face point and an edge point are both chamfered, in one feature."""
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    part = await _built(adapter)
    add_chamfer = await coupon.add_chamfer_tool(adapter)

    entries = [part.hole_face, part.opposite_edge]
    expected = _HOLE_FACE_CHAMFER + _ONE_EDGE_CHAMFER
    before = await coupon.volume(adapter)
    response = await add_chamfer(
        AddChamferInput(distance=_CHAMFER_MM, edge_names=entries)
    )
    removed = before - await coupon.volume(adapter)
    evidence(
        "Chamfer on the hole face plus one 30 mm edge of the opposite face (mm^3)",
        _removal(removed, expected),
    )

    assert response["status"] == "success", response
    assert response["chamfer"]["edges"] == entries
    names = await coupon.feature_names(adapter)
    assert response["chamfer"]["name"] in names
    assert sum("Chamfer" in n for n in names) == 1, names
    _assert_volume("The hole face plus one edge", removed, expected)


@pytest.mark.asyncio
async def test_a_fillet_on_one_edge(scratch: Any) -> None:
    """An edge point fillets that one 30 mm edge."""
    adapter = scratch.adapter
    part = await _built(adapter)

    before = await coupon.volume(adapter)
    fillet = await adapter.add_fillet(
        radius=_FILLET_MM, edge_names=[part.opposite_edge]
    )
    removed = before - await coupon.volume(adapter)
    evidence(
        "Fillet on one 30 mm edge of the face opposite the hole (mm^3)",
        _removal(removed, _ONE_EDGE_FILLET),
    )

    assert fillet.is_success, fillet.error
    assert any("Fillet" in n for n in await coupon.feature_names(adapter))
    _assert_volume("A fillet on one edge", removed, _ONE_EDGE_FILLET)
