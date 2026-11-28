"""The thread tools on the mock adapter (queue item 43). Spec: tools/threads."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.threads import (
    CreateThreadInput,
    ThreadSizesInput,
    register_thread_tools,
)


async def _tools(adapter: Any) -> dict[str, Any]:
    mcp = FastMCP("threads")
    assert await register_thread_tools(mcp, adapter, {}) == 2
    return {t.name: t.fn for t in await mcp.list_tools()}


@pytest.fixture
async def rod() -> MockSolidWorksAdapter:
    """A mock 6 mm rod, 25 mm long."""
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    await adapter.create_part()
    await adapter.create_sketch("Top")
    await adapter.add_circle(0, 0, 3)
    await adapter.exit_sketch()
    await adapter.create_extrusion(ExtrusionParameters(depth=25))
    return adapter


@pytest.mark.asyncio
async def test_list_sizes(rod: MockSolidWorksAdapter) -> None:
    tools = await _tools(rod)

    metric = await tools["list_thread_sizes"]()
    inch = await tools["list_thread_sizes"](ThreadSizesInput(standard="inch"))

    assert metric["message"] == "8 metric thread sizes"
    assert inch["message"] == "5 inch thread sizes"


@pytest.mark.asyncio
async def test_cut_a_thread(rod: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(rod))["create_thread"](
        CreateThreadInput(size="M6x1.0", edge_point=[3, 25, 0], length=12)
    )

    assert reply["message"].startswith("Thread1: M6x1.0 external, 12 mm, -")
    assert reply["thread"]["runout_mm"] == {"normal": 2.5, "short": 1.25}


@pytest.mark.asyncio
async def test_an_unknown_size_is_an_error_reply(rod: MockSolidWorksAdapter) -> None:
    reply = await (await _tools(rod))["create_thread"](
        {"size": "M7x1.0", "edge_point": [3, 25, 0], "length": 12}
    )

    assert reply["status"] == "error"
    assert reply["error_type"] == "invalid_input"


@pytest.mark.parametrize(
    "values",
    [
        {"size": "M6x1.0", "edge_point": [3, 25], "length": 12},
        {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 0},
        {"size": "M6x1.0", "edge_point": [3, 25, 0], "length": 5, "kind": "male"},
    ],
)
def test_inputs_are_strict(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CreateThreadInput(**values)
