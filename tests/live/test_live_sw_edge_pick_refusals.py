"""Real-SolidWorks tests: add_chamfer and add_fillet refuse picks that match nothing (#191, #199).

Every test here is meant to be refused. Each builds the M4 heat-set-insert
coupon (``tests/live/coupon.py``), makes a call that names no real edge or
face, and passes only when the tool returns an error that says why, and the
part is left exactly as it was: no new feature, and no change in volume.

The chamfers and fillets that should succeed are in
``test_live_sw_add_chamfer_tool.py``.

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.live import coupon
from tests.live.evidence import evidence

_BAD_EDGE = "Edge_that_does_not_exist<99>"


async def _assert_untouched(adapter: Any, before: float, kind: str) -> None:
    """Check the refused call left no feature of ``kind`` and the same volume.

    Args:
        adapter: The connected SolidWorks adapter.
        before: The part's volume before the call, in mm³.
        kind: ``"Chamfer"`` or ``"Fillet"``.
    """
    names = await coupon.feature_names(adapter)
    assert not any(kind in n for n in names), names
    assert await coupon.volume(adapter) == pytest.approx(before, abs=1e-6)


@pytest.mark.asyncio
async def test_refused_an_edge_name_that_does_not_exist(scratch: Any) -> None:
    """Refused: an edge name that isn't in the part."""
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    await coupon.build(adapter)
    add_chamfer = await coupon.add_chamfer_tool(adapter)

    before = await coupon.volume(adapter)
    response = await add_chamfer(AddChamferInput(distance=0.5, edge_names=[_BAD_EDGE]))
    evidence(
        "Refused, as it should be: a chamfer on an edge name that doesn't exist",
        {"status": response["status"], "message": response["message"]},
    )

    assert response["status"] == "error"
    assert _BAD_EDGE in response["message"]
    await _assert_untouched(adapter, before, "Chamfer")


@pytest.mark.asyncio
async def test_refused_a_good_entry_with_a_bad_one(scratch: Any) -> None:
    """Refused as a whole: one real face and one bad name makes no partial chamfer."""
    from solidworks_mcp.tools.modeling import AddChamferInput

    adapter = scratch.adapter
    part = await coupon.build(adapter)
    add_chamfer = await coupon.add_chamfer_tool(adapter)

    before = await coupon.volume(adapter)
    response = await add_chamfer(
        AddChamferInput(distance=0.5, edge_names=[part.hole_face, _BAD_EDGE])
    )
    evidence(
        "Refused, as it should be: the hole face plus a bad name",
        {"status": response["status"], "message": response["message"]},
    )

    assert response["status"] == "error"
    assert _BAD_EDGE in response["message"]
    await _assert_untouched(adapter, before, "Chamfer")


@pytest.mark.asyncio
async def test_refused_a_point_inside_the_block(scratch: Any) -> None:
    """Refused: a face point 5 mm inside the block is on no face."""
    adapter = scratch.adapter
    part = await coupon.build(adapter)

    before = await coupon.volume(adapter)
    fillet = await adapter.add_fillet(radius=1.0, edge_names=[part.inside])
    evidence(
        "Refused, as it should be: a fillet at a point 5 mm inside the block",
        {"point": part.inside, "error": fillet.error},
    )

    assert not fillet.is_success
    assert "the nearest is 5.000 mm away" in str(fillet.error), fillet.error
    await _assert_untouched(adapter, before, "Fillet")
