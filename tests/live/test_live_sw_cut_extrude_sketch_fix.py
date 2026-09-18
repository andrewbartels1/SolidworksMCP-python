"""Real-SolidWorks regression tests for the create_cut_extrude fix.

Covers the chain of bugs found and fixed while debugging a reported
"Parameter not optional" failure on every create_cut_extrude call:

1. ``FeatureCut3``'s broken 19-parameter "legacy" fallback (wrong argument
   count, never matched any real SolidWorks API signature) — replaced by the
   confirmed-correct 26-parameter signature shared with ``FeatureCut4``.
2. The adapter-wide ``CircuitBreakerAdapter`` state — one failing tool used
   to trip the breaker for every other tool, including reads. Covered by
   the mock suite (test_adapters.py); not re-tested here since it needs no
   real SolidWorks.
3. ``create_sketch`` trusting ``InsertSketch``'s return value for the
   sketch name, which SolidWorks sometimes doesn't populate synchronously —
   fixed by also reading ``ISketchManager.ActiveSketch``.
4. ``create_cut_extrude``'s sketch resolution: rewritten to require either
   an explicit ``sketch_name`` or a tree-verified ``_last_sketch_name``,
   with a clear, actionable error otherwise instead of a blind ``Sketch<N>``
   guess.
5. ``SelectByID2``'s ``Callout`` argument being passed as bare ``None``
   (marshals as ``VT_NULL``; SolidWorks silently rejects the whole call) —
   fixed with the existing ``_null_callout()`` VT_DISPATCH helper.

Gating, the ``scratch`` fixture and scratch-doc cleanup are shared from
``tests/live/conftest.py`` (not collected unless
``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows).
"""

from __future__ import annotations

import pytest


async def _dimensioned_block_with_centered_sketch(adapter) -> str:  # noqa: ANN001
    """Build a 30x30x15mm block and leave a centered, unconsumed circle sketch.

    Returns the real (tree-verified) name of that circle sketch. Mirrors the
    manual live verification done for this fix: a block sized/positioned via
    smart dimensions (not just raw sketch coordinates), then a hole profile
    ready to be cut.
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
    # Sketch1 (the consumed block profile) plus exactly one unconsumed circle.
    unconsumed = [n for n in sketch_names if n != "Sketch1"]
    assert len(unconsumed) == 1, f"expected one unconsumed sketch, got {sketch_names}"
    return unconsumed[0]


@pytest.mark.asyncio
async def test_cut_extrude_with_explicit_sketch_name_creates_the_hole(scratch):
    """The full, real-SolidWorks happy path: dimensioned block + centered hole.

    This is the exact scenario from the original bug report (an M4
    heat-set-insert validation coupon: Ø5.5mm hole, 6mm deep) and is the
    live proof the FeatureCut3/4 argument-count fix, the VT_DISPATCH callout
    fix, and the explicit sketch_name resolution all work together.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    sketch_name = await _dimensioned_block_with_centered_sketch(adapter)

    cut = await adapter.create_cut_extrude(
        ExtrusionParameters(depth=6.0, sketch_name=sketch_name)
    )
    assert cut.is_success, cut.error
    assert cut.data.type == "Cut-Extrude"
    assert cut.data.parameters["sketch_name"] == sketch_name

    features = await adapter.list_features()
    assert features.is_success
    assert any(f["name"] == cut.data.name for f in features.data)


@pytest.mark.asyncio
async def test_cut_extrude_unknown_sketch_name_fails_fast_and_lists_real_ones(scratch):
    """An explicit but wrong sketch_name must error before touching FeatureCut.

    Regression for the "no default sketch, ever" requirement: previously a
    caller had no way to target a sketch explicitly at all, and any failure
    to resolve one silently tried a blind Sketch<N> enumeration.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    real_sketch_name = await _dimensioned_block_with_centered_sketch(adapter)

    result = await adapter.create_cut_extrude(
        ExtrusionParameters(depth=6.0, sketch_name="DefinitelyNotARealSketchName")
    )
    assert not result.is_success
    assert "DefinitelyNotARealSketchName" in (result.error or "")
    assert real_sketch_name in (result.error or "")


@pytest.mark.asyncio
async def test_cut_extrude_lost_session_tracking_fails_clearly_instead_of_guessing(
    scratch,
):
    """Reproduces the original bug's actual root cause: stale/lost tracking.

    If ``_last_sketch_name`` doesn't match anything real in the model (e.g.
    because the adapter process restarted, or create_sketch's return value
    didn't match SolidWorks' real auto-assigned name), create_cut_extrude
    must fail with a clear, actionable message rather than silently
    enumerating ``Sketch<N>`` candidates and possibly cutting the wrong
    profile.
    """
    from solidworks_mcp.adapters.base import ExtrusionParameters

    adapter = scratch.adapter
    real_sketch_name = await _dimensioned_block_with_centered_sketch(adapter)

    # Simulate lost/incorrect session tracking (e.g. after a server restart,
    # or a create_sketch call that fell back to a synthetic name).
    adapter._last_sketch_name = "Sketch_stale_guess"

    result = await adapter.create_cut_extrude(ExtrusionParameters(depth=6.0))
    assert not result.is_success
    assert "sketch_name explicitly" in (result.error or "")
    assert real_sketch_name in (result.error or "")

    # And the real sketch is still there, untouched.
    features = await adapter.list_features()
    assert any(f["name"] == real_sketch_name for f in features.data)
