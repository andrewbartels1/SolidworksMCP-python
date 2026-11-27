"""The helix and sweep tools on the mock adapter (queue item 34).

Spec: tools/helix and tools/swept-features.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.modeling import (
    CreateCutSweepInput,
    CreateHelixInput,
    CreateSweepInput,
    register_modeling_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("swept")
    await register_modeling_tools(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def part() -> MockSolidWorksAdapter:
    """A mock part with a 20 mm circle in Sketch1, closed."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part("Spring")
    await adapter.create_sketch("Top")
    await adapter.add_circle(0.0, 0.0, 10.0)
    await adapter.exit_sketch()
    return adapter


@pytest.mark.asyncio
async def test_a_spring_from_a_helix_and_a_wire(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    helix = await tools["create_helix"](
        CreateHelixInput(sketch="Sketch1", height=48, pitch=6)
    )
    wire = await tools["create_sweep"](
        CreateSweepInput(path=helix["helix"]["name"], circular_profile_diameter=2)
    )

    assert helix["message"] == (
        "Made Helix/Spiral1: 8 turns at 6 mm pitch, 504.941 mm long"
    )
    assert helix["helix"]["start_point_mm"] == [10.0, 0.0, 0.0]
    assert wire["message"].startswith("Swept a 2 mm circle along Helix/Spiral1: ")
    assert wire["sweep"]["circular_profile_diameter_mm"] == 2
    assert wire["sweep"]["merge_result"] is True


@pytest.mark.asyncio
async def test_a_cut_sweep_names_its_profile(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)
    await part.create_sketch("Front")
    await part.exit_sketch()

    cut = await tools["create_cut_sweep"](
        CreateCutSweepInput(path="Sketch1", profile="Sketch2", twist_angle=0)
    )

    assert cut["message"].startswith("Cut Sketch2 along Sketch1: Cut-Sweep")
    assert cut["cut_sweep"]["profile"] == "Sketch2"
    assert "merge_result" not in cut["cut_sweep"]


@pytest.mark.asyncio
async def test_a_refused_sweep_is_an_error_reply(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    reply = await tools["create_cut_sweep"]({"path": "Sketch1"})

    assert reply["status"] == "error"
    assert "needs a profile sketch distinct from the path" in reply["message"]


@pytest.mark.asyncio
async def test_a_sweep_reply_without_parameters(part: MockSolidWorksAdapter) -> None:
    """An adapter that returns only a name still gets a readable reply."""
    tools = await _tools(part)

    async def bare(params: Any) -> Any:
        from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"feature_name": "Sweep1"}
        )

    part.create_sweep = bare  # type: ignore[method-assign]

    reply = await tools["create_sweep"]({"path": "Sketch1"})

    assert reply["message"] == "Swept the profile along Sketch1: Sweep1"


@pytest.mark.asyncio
async def test_a_helix_reply_without_data(part: MockSolidWorksAdapter) -> None:
    tools = await _tools(part)

    async def empty(params: Any) -> Any:
        from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=None)

    part.create_helix = empty  # type: ignore[method-assign]

    reply = await tools["create_helix"]({"sketch": "Sketch1", "height": 1, "pitch": 1})

    assert reply["message"] == "Made a helix: 0 turns at 0 mm pitch, 0 mm long"


@pytest.mark.parametrize(
    ("values", "missing"),
    [
        ({"defined_by": "height_and_pitch", "height": 48}, "needs pitch"),
        ({"defined_by": "spiral"}, "needs pitch and revolutions"),
        (
            {"defined_by": "height_and_revolutions", "pitch": 2},
            "needs height and revolutions",
        ),
        ({"defined_by": "pitch_and_revolutions", "pitch": 2}, "needs revolutions"),
    ],
)
def test_the_helix_input_needs_its_two_values(
    values: dict[str, Any], missing: str
) -> None:
    with pytest.raises(ValidationError, match=missing):
        CreateHelixInput(sketch="Sketch1", **values)


@pytest.mark.parametrize("field", ["height", "pitch", "revolutions"])
def test_the_helix_values_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        CreateHelixInput(sketch="Sketch1", **{field: 0})


def test_a_circular_profile_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CreateSweepInput(path="Helix/Spiral1", circular_profile_diameter=0)
    with pytest.raises(ValidationError):
        CreateCutSweepInput(path="Helix/Spiral1", circular_profile_diameter=-1)
