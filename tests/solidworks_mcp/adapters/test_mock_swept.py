"""The mock adapter's helices and sweeps refuse what the real adapter refuses (queue item 34)."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import HelixParameters, SweepParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


async def _part(*circles: int) -> MockSolidWorksAdapter:
    """A connected mock part with one sketch per entry, holding that many circles."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    for count in circles:
        await adapter.create_sketch("Top")
        for _ in range(count):
            await adapter.add_circle(0.0, 0.0, 10.0)
        await adapter.exit_sketch()
    return adapter


def _helix(**overrides: Any) -> HelixParameters:
    values: dict[str, Any] = {"sketch": "Sketch1", "height": 48, "pitch": 6}
    return HelixParameters(**{**values, **overrides})


@pytest.mark.asyncio
async def test_a_helix_reports_its_turns_length_and_start() -> None:
    adapter = await _part(1)

    result = await adapter.create_helix(_helix(sketch="sketch1"))

    assert result.is_success, result.error
    data = result.data
    assert (data["name"], data["sketch"], data["revolutions"]) == (
        "Helix/Spiral1",
        "Sketch1",
        8,
    )
    assert data["length_mm"] == pytest.approx(504.924, rel=1e-4)
    assert data["start_point_mm"] == [10.0, 0.0, 0.0]
    assert data["taper_angle"] is None


@pytest.mark.asyncio
async def test_a_tapered_helix_keeps_its_taper() -> None:
    adapter = await _part(1)

    result = await adapter.create_helix(_helix(taper_angle=5, taper_outward=True))

    assert (result.data["taper_angle"], result.data["taper_outward"]) == (5, True)


@pytest.mark.parametrize(
    ("circles", "params", "message"),
    [
        ((1,), _helix(pitch=None), "needs pitch"),
        ((1,), _helix(sketch="Sketch9"), "No sketch named 'Sketch9'"),
        ((), _helix(), "Sketches: none"),
        ((2,), _helix(), "holds 2 circles"),
    ],
)
@pytest.mark.asyncio
async def test_a_helix_refused(
    circles: tuple[int, ...], params: HelixParameters, message: str
) -> None:
    adapter = await _part(*circles)

    result = await adapter.create_helix(params)

    assert message in (result.error or "")


@pytest.mark.asyncio
async def test_no_active_model() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    helix = await adapter.create_helix(_helix())
    sweep = await adapter.create_cut_sweep(SweepParameters(path="Sketch1"))

    assert helix.error == sweep.error == "No active model"


@pytest.mark.asyncio
async def test_a_circle_swept_along_a_helix() -> None:
    adapter = await _part(1)
    await adapter.create_helix(_helix())

    result = await adapter.create_sweep(
        SweepParameters(path="helix/spiral1", circular_profile_diameter=2)
    )

    assert result.is_success, result.error
    assert result.data.type == "Sweep"
    assert result.data.parameters["path"] == "Helix/Spiral1"
    assert result.data.parameters["profile"] is None
    assert result.data.parameters["merge_result"] is True


@pytest.mark.asyncio
async def test_a_cut_takes_the_latest_other_sketch_or_the_named_one() -> None:
    adapter = await _part(1, 1, 0)

    latest = await adapter.create_cut_sweep(SweepParameters(path="Sketch1"))
    named = await adapter.create_cut_sweep(
        SweepParameters(path="Sketch1", profile="Sketch2")
    )

    assert latest.data.parameters["profile"] == "Sketch3"
    assert named.data.parameters["profile"] == "Sketch2"
    assert latest.data.type == "CutSweep"
    assert "merge_result" not in latest.data.parameters


@pytest.mark.asyncio
async def test_the_sketch_closed_last_is_preferred() -> None:
    adapter = await _part(1, 1, 0)
    adapter._last_sketch_name = "Sketch2"  # type: ignore[attr-defined]

    result = await adapter.create_sweep(SweepParameters(path="Sketch1"))

    assert result.data.parameters["profile"] == "Sketch2"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (SweepParameters(path=""), "needs a 'path'"),
        (
            SweepParameters(path="Sketch1", circular_profile_diameter=-1),
            "must be greater than 0",
        ),
        (SweepParameters(path="Path9"), "no sketch or curve named 'Path9'"),
        (SweepParameters(path="Sketch1", profile="SKETCH1"), "is the path itself"),
        (
            SweepParameters(path="Sketch1", profile="Sketch9"),
            "no sketch named 'Sketch9' for the profile",
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_sweep_refused(params: SweepParameters, message: str) -> None:
    adapter = await _part(1, 0)

    result = await adapter.create_sweep(params)

    assert message in (result.error or "")


@pytest.mark.asyncio
async def test_a_helix_is_no_profile() -> None:
    adapter = await _part(1)
    await adapter.create_helix(_helix())

    named = await adapter.create_sweep(
        SweepParameters(path="Sketch1", profile="Helix/Spiral1")
    )
    alone = await adapter.create_sweep(SweepParameters(path="Sketch1"))

    assert "no sketch named 'Helix/Spiral1'" in (named.error or "")
    assert "needs a profile sketch distinct from the path" in (alone.error or "")
