"""Mock-based composition tests for the new sketch ops.

Every method that landed under issue #1 returns an entity ID.  PRs #11-#21
shipped isolated regression tests for each method but **none** chained an
op's returned ID into another op's input — the structural gap that let
three latent live bugs ride through review:

  1. ``add_polygon`` returned a synthesised ID that was never registered
     in ``adapter._sketch_entities``.  Downstream ops failed with
     ``Unknown sketch entity 'Polygon_6sided_*'``.
  2. ``_select_sketch_entities`` couldn't ``Select4`` on the
     tuple-of-segments that ``ISketchManager::CreatePolygon`` returns.
  3. ``sketch_circular_pattern`` silently rejected ``ArcAngle = -π`` —
     the value ``math.atan2(-0.0, -seed_x)`` produces for a seed on the
     positive X axis.

These tests guard the **API contract between creator and consumer**.  A
new creator op must keep them green; a new consumer op should add a
matching row to the matrix below.  Mock-based so they run cross-platform
in ``pedro-ci`` — the live counterparts live in
``tests/test_live_sw_regression.py`` and run on Windows with SW.
"""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResultStatus
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


@pytest.fixture
async def sketch_adapter() -> MockSolidWorksAdapter:
    """A connected mock adapter sitting in an open Front-plane sketch."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Front")
    return adapter


# ---------------------------------------------------------------------------
# add_<creator> ID must be registered in the adapter's sketch-entity table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("creator_name", "args"),
    [
        ("add_arc", (0.0, 0.0, 10.0, 0.0, 0.0, 10.0)),
        ("add_spline", ([{"x": 0.0, "y": 0.0}, {"x": 20.0, "y": 10.0}],)),
        ("add_centerline", (0.0, -20.0, 0.0, 20.0)),
        ("add_polygon", (0.0, 0.0, 10.0, 6)),
        ("add_ellipse", (0.0, 0.0, 30.0, 15.0)),
    ],
)
async def test_creator_id_is_registered(
    sketch_adapter: MockSolidWorksAdapter,
    creator_name: str,
    args: tuple,
) -> None:
    """The ID returned by every ``add_*`` op must live in
    ``_sketch_entity_ids`` so a downstream selector can resolve it.

    Regression: pre-fix, ``add_polygon`` returned an ID without
    registering it; mock had the same divergence between adapters
    even though both passed their isolated unit tests.
    """
    result = await getattr(sketch_adapter, creator_name)(*args)
    assert result.is_success, f"{creator_name} failed: {result.error}"
    assert result.data in sketch_adapter._sketch_entity_ids, (
        f"{creator_name} returned {result.data!r} but did not register it; "
        f"downstream sketch_linear_pattern / _mirror / _offset / _circular_pattern "
        f"will fail with 'Unknown sketch entity'."
    )


# ---------------------------------------------------------------------------
# Creator → consumer chains.  Each row picks the cheapest valid chain.
# ---------------------------------------------------------------------------


async def test_polygon_flows_into_linear_pattern(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Polygon seed must be a valid input to ``sketch_linear_pattern``.

    Regression: the live demo's first failure — ``add_polygon`` returning
    an unregistered ID surfaced as ``Unknown sketch entity 'Polygon_*'``.
    """
    seed = await sketch_adapter.add_polygon(0.0, 0.0, 10.0, 6)
    assert seed.is_success
    pattern = await sketch_adapter.sketch_linear_pattern(
        entities=[seed.data],
        direction_x=1.0,
        direction_y=0.0,
        spacing=20.0,
        count=5,
    )
    assert pattern.is_success, (
        f"polygon -> linear_pattern composition failed: {pattern.error}"
    )


async def test_polygon_flows_into_mirror(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Polygon seed + centerline mirror axis -> sketch_mirror must succeed."""
    poly = await sketch_adapter.add_polygon(20.0, 20.0, 5.0, 6)
    cl = await sketch_adapter.add_centerline(-50.0, 0.0, 50.0, 0.0)
    assert poly.is_success and cl.is_success
    mirrored = await sketch_adapter.sketch_mirror(
        entities=[poly.data], mirror_line=cl.data
    )
    assert mirrored.is_success, (
        f"polygon -> mirror composition failed: {mirrored.error}"
    )


async def test_polygon_flows_into_offset(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Polygon seed -> sketch_offset must succeed."""
    poly = await sketch_adapter.add_polygon(0.0, 0.0, 10.0, 6)
    assert poly.is_success
    offset = await sketch_adapter.sketch_offset(
        entities=[poly.data], offset_distance=2.0, reverse_direction=False
    )
    assert offset.is_success, (
        f"polygon -> offset composition failed: {offset.error}"
    )


async def test_ellipse_flows_into_circular_pattern(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Ellipse seed on +X axis -> sketch_circular_pattern around origin.

    Regression: the live circular-pattern impl was hard-coded to flag
    ``ISketchArc`` only when probing the seed for ``GetCenterPoint``;
    an ellipse seed silently fell through to the 1 mm placeholder
    radius.  The mock has no such method-flagging step, so this test
    only pins the **API shape** — but a future divergence in the
    accepted-types list between adapters would surface here.
    """
    seed = await sketch_adapter.add_ellipse(30.0, 0.0, 12.0, 6.0)
    assert seed.is_success
    pattern = await sketch_adapter.sketch_circular_pattern(
        entities=[seed.data],
        angle=360.0,
        count=6,
    )
    assert pattern.is_success, (
        f"ellipse -> circular_pattern composition failed: {pattern.error}"
    )


async def test_arc_flows_into_mirror_and_offset(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Arc seed -> both sketch_mirror and sketch_offset must succeed.

    Mirrors the bottom band of the live demo (arc + spline +
    mirror + offset) but in a chain so a future ID-format change in
    ``add_arc`` breaks here without needing a live SW box.
    """
    arc = await sketch_adapter.add_arc(0.0, 0.0, 10.0, 0.0, 0.0, 10.0)
    cl = await sketch_adapter.add_centerline(-50.0, 0.0, 50.0, 0.0)
    assert arc.is_success and cl.is_success
    mirrored = await sketch_adapter.sketch_mirror(
        entities=[arc.data], mirror_line=cl.data
    )
    assert mirrored.is_success, f"arc -> mirror failed: {mirrored.error}"
    offset = await sketch_adapter.sketch_offset(
        entities=[arc.data], offset_distance=3.0, reverse_direction=False
    )
    assert offset.is_success, f"arc -> offset failed: {offset.error}"


async def test_spline_flows_into_mirror(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """Spline seed + centerline -> sketch_mirror must succeed."""
    spl = await sketch_adapter.add_spline(
        [{"x": 0.0, "y": 5.0}, {"x": 10.0, "y": 15.0}, {"x": 20.0, "y": 5.0}]
    )
    cl = await sketch_adapter.add_centerline(-30.0, 0.0, 30.0, 0.0)
    assert spl.is_success and cl.is_success
    mirrored = await sketch_adapter.sketch_mirror(
        entities=[spl.data], mirror_line=cl.data
    )
    assert mirrored.is_success, f"spline -> mirror failed: {mirrored.error}"


# ---------------------------------------------------------------------------
# Negative composition: pattern/mirror/offset must reject unregistered IDs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("consumer", "extra_kwargs"),
    [
        ("sketch_linear_pattern", {
            "direction_x": 1.0,
            "direction_y": 0.0,
            "spacing": 20.0,
            "count": 3,
        }),
        ("sketch_circular_pattern", {
            "angle": 360.0,
            "count": 6,
        }),
        ("sketch_offset", {
            "offset_distance": 2.0,
            "reverse_direction": False,
        }),
    ],
)
async def test_consumer_rejects_unregistered_id(
    sketch_adapter: MockSolidWorksAdapter,
    consumer: str,
    extra_kwargs: dict,
) -> None:
    """A consumer must surface ``Unknown sketch entity`` for a bogus ID
    rather than silently no-op.  The error message points the caller at
    the right ``add_*`` family — a contract the live adapter and the
    mock must both honour."""
    result = await getattr(sketch_adapter, consumer)(
        entities=["NotARealEntity_999"], **extra_kwargs
    )
    assert result.status == AdapterResultStatus.ERROR
    assert "Unknown sketch entity" in (result.error or "")


async def test_mirror_rejects_unregistered_line(
    sketch_adapter: MockSolidWorksAdapter,
) -> None:
    """``sketch_mirror`` has two ID inputs; the mirror_line check is the
    one that distinguishes it from the other consumers."""
    arc = await sketch_adapter.add_arc(0.0, 0.0, 10.0, 0.0, 0.0, 10.0)
    assert arc.is_success
    result = await sketch_adapter.sketch_mirror(
        entities=[arc.data], mirror_line="NotACenterline_42"
    )
    assert result.status == AdapterResultStatus.ERROR
