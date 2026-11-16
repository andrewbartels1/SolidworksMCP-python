"""The part-feature tools: holes, threads, linear patterns, shell, draft, rib.

Specs: tools/hole-wizard, tools/cosmetic-thread, tools/shell-draft-rib,
tools/feature-patterns.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from solidworks_mcp.tools.modeling import (
    AddCosmeticThreadInput,
    AddDraftInput,
    CreateHoleInput,
    CreateRibInput,
    CreateShellInput,
    ListHoleSizesInput,
    PatternLinearInput,
    metric_diameter,
    register_modeling_tools,
)


async def _tool(mcp_server: Any, adapter: Any, config: Any, name: str) -> Any:
    await register_modeling_tools(mcp_server, adapter, config)
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


@pytest.mark.parametrize(
    ("size", "diameter"),
    [("M6", 6.0), ("m10x1.5", 10.0), (" M2.5", 2.5), ("#10-24", None), ("1/4", None)],
)
def test_metric_diameter(size: str, diameter: float | None) -> None:
    assert metric_diameter(size) == diameter


def test_a_hole_size_is_passed_on_as_given() -> None:
    """The size is checked by the adapter against the library, not here."""
    made = CreateHoleInput(
        face_point=[0, 0, 20], hole_type="simple", standard="din", size="6"
    )
    assert (made.size, made.standard, made.fastener) == ("6", "din", None)


CASES = [
    (
        "create_hole",
        CreateHoleInput(face_point=[0, 0, 20], hole_type="counterbore", size="M6"),
        "hole",
        "Added a M6 counterbore hole",
    ),
    (
        "create_hole",
        CreateHoleInput(
            face_point=[0, 0, 20],
            hole_type="counterbore",
            size="M6",
            positions=[[10, 0, 20], [-10, 0, 20]],
        ),
        "hole",
        "Added 3 M6 counterbore holes",
    ),
    (
        "add_cosmetic_thread",
        AddCosmeticThreadInput(edge_point=[3, 0, 20], size="M6x1.0", depth=8),
        "thread",
        "Added a M6x1.0 cosmetic thread",
    ),
    (
        "pattern_linear",
        PatternLinearInput(features=["Hole1"], direction="Axis1", count=3, spacing=10),
        "pattern",
        "Patterned Hole1 (3 instances)",
    ),
    (
        "pattern_linear",
        PatternLinearInput(
            features=["Hole1"],
            direction=[0, -20, 20],
            count=3,
            spacing=10,
            direction2=[20, 0, 20],
            count2=2,
            spacing2=5,
        ),
        "pattern",
        "Patterned Hole1 (3 x 2 instances)",
    ),
    (
        "create_shell",
        CreateShellInput(thickness=2, faces=[[0, 0, 20]]),
        "shell",
        "Shelled the part to 2.0 mm walls",
    ),
    (
        "add_draft",
        AddDraftInput(angle=3, faces=[[20, 0, 10]], neutral_face=[0, 0, 0]),
        "draft",
        "Drafted 1 face(s) by 3.0 degrees",
    ),
    (
        "create_rib",
        CreateRibInput(sketch="Sketch3", thickness=2),
        "rib",
        "Added a 2.0 mm rib from Sketch3",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "data", "key", "message"), CASES)
async def test_each_tool_on_the_mock(
    mcp_server: Any,
    mock_adapter: Any,
    mock_config: Any,
    name: str,
    data: Any,
    key: str,
    message: str,
) -> None:
    tool = await _tool(mcp_server, mock_adapter, mock_config, name)

    result = await tool(data)

    assert result["status"] == "success", result
    assert result["message"] == message
    assert "volume_change" in result[key]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "data", "key", "message"), CASES[:1])
async def test_a_missing_capability_is_an_error(
    mcp_server: Any, mock_config: Any, name: str, data: Any, key: str, message: str
) -> None:
    tool = await _tool(mcp_server, object(), mock_config, name)

    assert (await tool(data))["status"] == "error"


@pytest.mark.parametrize(
    ("model", "kwargs", "match"),
    [
        (
            PatternLinearInput,
            {"features": [" "], "direction": "A", "count": 2, "spacing": 1},
            "at least one name",
        ),
        (
            PatternLinearInput,
            {"features": ["F"], "direction": "A", "count": 1, "spacing": 1},
            "count must be at least 2",
        ),
        (
            PatternLinearInput,
            {"features": ["F"], "direction": [1, 2], "count": 2, "spacing": 1},
            r"direction must be \[x, y, z\]",
        ),
        (
            PatternLinearInput,
            {
                "features": ["F"],
                "direction": "A",
                "count": 2,
                "spacing": 1,
                "direction2": [1],
            },
            "direction2 must be",
        ),
        (
            PatternLinearInput,
            {
                "features": ["F"],
                "direction": "A",
                "count": 2,
                "spacing": 1,
                "direction2": "B",
            },
            "count2 of 2",
        ),
        (CreateShellInput, {"thickness": 1, "faces": [[1, 2]]}, "each face point"),
        (
            AddDraftInput,
            {"angle": 3, "faces": [], "neutral_face": [0, 0, 0]},
            "at least one point",
        ),
        (
            AddDraftInput,
            {"angle": 3, "faces": [[0, 0, 0]], "neutral_face": [0]},
            "neutral_face must be",
        ),
        (CreateRibInput, {"sketch": " ", "thickness": 1}, "sketch is required"),
        (
            CreateHoleInput,
            {"face_point": [0, 0], "hole_type": "simple", "size": "M6"},
            "face_point must be",
        ),
        (
            CreateHoleInput,
            {"face_point": [0, 0, 0], "hole_type": "simple", "size": " "},
            "size is required",
        ),
        (
            CreateHoleInput,
            {
                "face_point": [0, 0, 0],
                "hole_type": "simple",
                "size": "M6",
                "positions": [[1, 2]],
            },
            "each of positions must be",
        ),
        (
            CreateHoleInput,
            {
                "face_point": [0, 0, 0],
                "hole_type": "simple",
                "size": "M6",
                "end_condition": "blind",
            },
            "needs depth",
        ),
        (
            AddCosmeticThreadInput,
            {"edge_point": [0, 0, 0], "size": "1/4-20", "depth": 5},
            "diameter is required",
        ),
        (
            AddCosmeticThreadInput,
            {"edge_point": [0, 0, 0], "size": "M6"},
            "a blind thread needs depth",
        ),
        (
            AddCosmeticThreadInput,
            {"edge_point": [0, 0], "size": "M6", "depth": 1},
            "edge_point must be",
        ),
    ],
)
def test_inputs_refuse_bad_values(
    model: Any, kwargs: dict[str, Any], match: str
) -> None:
    with pytest.raises((ValueError, ValidationError), match=match):
        model(**kwargs)


def test_a_metric_thread_reads_its_diameter() -> None:
    data = AddCosmeticThreadInput(
        edge_point=[0, 0, 0], size="M10x1.5", end_type="through"
    )

    assert data.diameter == 10.0


@pytest.mark.asyncio
async def test_a_simple_hole_names_the_size_it_used(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    tool = await _tool(mcp_server, mock_adapter, mock_config, "create_hole")

    result = await tool(
        CreateHoleInput(
            face_point=[0, 0, 20],
            hole_type="simple",
            size="6",
            end_condition="blind",
            depth=5,
        )
    )

    assert result["message"] == "Added a Ø6.0 simple hole"
    assert result["hole"]["fastener"] == "Drill sizes"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            ListHoleSizesInput(hole_type="simple"),
            "simple hole types (iso): Drill sizes, Screw Clearances",
        ),
        (
            ListHoleSizesInput(hole_type="counterbore", size="M6"),
            "Cap (4762) M6 dimensions",
        ),
    ],
)
async def test_list_hole_sizes(
    mcp_server: Any, mock_adapter: Any, mock_config: Any, data: Any, message: str
) -> None:
    tool = await _tool(mcp_server, mock_adapter, mock_config, "list_hole_sizes")

    result = await tool(data)

    assert result["status"] == "success", result
    assert result["message"] == message
    assert result["library"]["units"] == "mm"


@pytest.mark.asyncio
async def test_list_hole_sizes_names_the_nearest(
    mcp_server: Any, mock_adapter: Any, mock_config: Any
) -> None:
    tool = await _tool(mcp_server, mock_adapter, mock_config, "list_hole_sizes")

    result = await tool(ListHoleSizesInput(hole_type="tapped", size="M7"))

    assert result["status"] == "error"
    assert "nearest: M4, M5, M6, M8, M8x1.0" in result["message"]
