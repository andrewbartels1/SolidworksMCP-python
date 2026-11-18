"""The equation tools, through the error boundary, on the mock adapter.

Spec: tools/equations.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.tools.equations import register_equation_tools

pytestmark = pytest.mark.asyncio


async def _tools(adapter: Any = None) -> dict[str, Any]:
    if adapter is None:
        adapter = MockSolidWorksAdapter({})
        await adapter.connect()
        await adapter.create_part()
    mcp = FastMCP("equations")
    assert await register_equation_tools(mcp, adapter, {}) == 3
    return {t.name: t.fn for t in await mcp.list_tools()}


async def test_set_list_and_delete() -> None:
    tools = await _tools()
    added = await tools["set_equation"]({"name": " Width ", "expression": "60mm"})
    driven = await tools["set_equation"](
        {"name": "D1@Sketch1", "expression": '"Width" / 2', "configurations": "this"}
    )
    listed = await tools["list_equations"]()
    deleted = await tools["delete_equation"]({"name": "D1@Sketch1"})

    assert added["message"] == "Added Width = 60mm"
    assert driven["equation"]["value"] == 30.0
    assert listed["count"] == 2
    assert [row["kind"] for row in listed["equations"]] == [
        "global_variable",
        "dimension",
    ]
    assert deleted["message"] == "Deleted equation D1@Sketch1"
    assert deleted["equations"] == ["Width"]


async def test_a_refused_expression_is_equation_refused() -> None:
    tools = await _tools()
    result = await tools["set_equation"]({"name": "X", "expression": '"Nope" * 2'})
    assert result["status"] == "error"
    assert result["error_type"] == "equation_refused"
    assert "list_equations" in result["hint"]


@pytest.mark.parametrize(
    ("call", "payload"),
    [
        ("set_equation", {"name": "D9@Nowhere", "expression": "1"}),
        ("delete_equation", {"name": "Ghost"}),
    ],
)
async def test_unknown_names_are_invalid_input(
    call: str, payload: dict[str, Any]
) -> None:
    result = await (await _tools())[call](payload)
    assert result["error_type"] == "invalid_input", result
    assert "list_" in result["hint"]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "expression": "1"},
        {"name": '"Width"', "expression": "1"},
        {"name": "A=B", "expression": "1"},
        {"name": "Width", "expression": " "},
        {"name": "Width", "expression": "1\n2"},
        {"name": "Width", "expression": "1", "configurations": []},
    ],
)
async def test_bad_inputs_are_refused_before_anything_runs(
    payload: dict[str, Any],
) -> None:
    result = await (await _tools())["set_equation"](payload)
    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"


async def test_a_blank_name_to_delete_is_refused() -> None:
    result = await (await _tools())["delete_equation"]({"name": "  "})
    assert result["error_type"] == "invalid_input"


async def test_no_open_document_is_no_active_document() -> None:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    result = await (await _tools(adapter))["list_equations"]()
    assert result["error_type"] == "no_active_document"
