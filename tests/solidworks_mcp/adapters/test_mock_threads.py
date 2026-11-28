"""The mock adapter's modelled threads (queue item 43). Spec: tools/threads."""

from __future__ import annotations

import math

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters, ThreadParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter


async def _part(rod: bool) -> MockSolidWorksAdapter:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    if rod:
        await adapter.create_sketch("Top")
        await adapter.add_circle(0, 0, 3)
        await adapter.exit_sketch()
        await adapter.create_extrusion(ExtrusionParameters(depth=25))
    return adapter


@pytest.mark.asyncio
async def test_sizes() -> None:
    adapter = await _part(False)

    metric = await adapter.list_thread_sizes("metric")
    inch = await adapter.list_thread_sizes("inch")
    other = await adapter.list_thread_sizes("din")

    assert {e["size"]: e["pitch_class"] for e in metric.data["sizes"]}[
        "M8x1.0"
    ] == "fine"
    assert inch.data["profile"] == "Inch Die"
    assert "standard must be" in str(other.error)


@pytest.mark.asyncio
async def test_a_thread_removes_its_groove() -> None:
    adapter = await _part(True)

    result = await adapter.create_thread(
        ThreadParameters(size="M6x1.0", edge_point=[3, 25, 0], length=12)
    )

    groove = math.pi * 6 * 0.5413 / 2 * 12
    assert result.data["volume_change"] == pytest.approx(-groove)
    assert result.data["turns"] == 12


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rod", "params", "words"),
    [
        (True, {"size": "M7x1.0"}, "No thread size"),
        (True, {"hand": "both"}, "hand must be"),
        (False, {}, "the part has no body"),
    ],
)
async def test_refusals(rod: bool, params: dict, words: str) -> None:
    adapter = await _part(rod)
    values = {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 12, **params}

    result = await adapter.create_thread(ThreadParameters(**values))

    assert words in str(result.error)


@pytest.mark.asyncio
async def test_no_document() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()

    result = await adapter.create_thread(
        ThreadParameters(size="M6x1.0", edge_point=[3, 25, 0], length=12)
    )

    assert result.error == "No active model"
