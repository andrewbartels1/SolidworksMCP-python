"""Tests for the drawing-automation tools (``tools/drawing_automation.py``).

Every tool has a success case against the mock adapter, its failures with an
actionable ``error_type``, and the missing-capability refusal.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.tools.drawing_automation import (
    ArrangeDimensionsInput,
    InsertModelDimensionsInput,
    register_drawing_automation_tools,
)

_TOOLS = ("insert_model_dimensions", "arrange_dimensions")


async def _tool(mcp_server: Any, name: str) -> Any:
    return next(t.fn for t in await mcp_server.list_tools() if t.name == name)


async def _drawing_with_views(mock_adapter: Any, tmp_path: Path) -> None:
    model = tmp_path / "bracket.SLDPRT"
    model.write_bytes(b"")
    await mock_adapter.create_drawing()
    await mock_adapter.create_technical_drawing({"model_path": str(model)})


class TestDrawingAutomationTools:
    """Tools exercised end to end against the mock adapter."""

    @pytest.mark.asyncio
    async def test_register_count(self, mcp_server, mock_adapter, mock_config) -> None:
        count = await register_drawing_automation_tools(
            mcp_server, mock_adapter, mock_config
        )
        names = {t.name for t in await mcp_server.list_tools()}
        assert count == len(names) == len(_TOOLS)
        assert names == set(_TOOLS)

    @pytest.mark.asyncio
    async def test_insert_then_arrange(
        self, mcp_server, mock_adapter, mock_config, tmp_path: Path
    ) -> None:
        await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
        await _drawing_with_views(mock_adapter, tmp_path)

        dims = await (await _tool(mcp_server, "insert_model_dimensions"))(
            input_data=InsertModelDimensionsInput()
        )
        views = len(dims["data"]["views"])
        assert dims["status"] == "success"
        assert dims["message"] == (
            f"Added {3 * views} dimension(s) to {views} view(s) "
            "(insert_model_annotations)"
        )
        again = await (await _tool(mcp_server, "insert_model_dimensions"))({})
        assert again["data"]["dimensions_added"] == 0  # no duplicates on a re-run

        arranged = await (await _tool(mcp_server, "arrange_dimensions"))(
            input_data=ArrangeDimensionsInput()
        )
        assert arranged["status"] == "success"
        assert arranged["message"] == (
            f"Arranged {3 * views} dimension(s): {3 * views} overlap(s) before, 0 after"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "setup", "error_type"),
    [
        ("insert_model_dimensions", {}, "create_part", "wrong_document_type"),
        ("insert_model_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("insert_model_dimensions", {}, "create_drawing", "not_found"),
        ("arrange_dimensions", {}, "create_assembly", "wrong_document_type"),
        ("arrange_dimensions", {"view_name": "Side"}, "views", "not_found"),
        ("arrange_dimensions", {"view_name": 7}, "views", "invalid_input"),
    ],
)
async def test_failures_carry_an_actionable_error_type(
    mcp_server, mock_adapter, mock_config, tmp_path, tool, payload, setup, error_type
) -> None:
    await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
    if setup == "views":
        await _drawing_with_views(mock_adapter, tmp_path)
    else:
        await getattr(mock_adapter, setup)()

    result = await (await _tool(mcp_server, tool))(payload)

    assert result["status"] == "error"
    assert result["error_type"] == error_type, result
    assert result["hint"]
    assert isinstance(result["execution_time"], float)


@pytest.mark.asyncio
async def test_remaining_overlaps_come_back_with_the_error(
    mcp_server, mock_config
) -> None:
    overlaps = [{"dimension": "Front#0", "conflicts_with": "Front", "kind": "x"}]

    async def arrange_dimensions(_view):
        return AdapterResult(
            status=AdapterResultStatus.ERROR,
            error="1 dimension overlap(s) remain after arranging 2 dimension(s)",
            data={"overlaps_after": 1, "remaining_overlaps": overlaps},
        )

    adapter = SimpleNamespace(arrange_dimensions=arrange_dimensions)
    await register_drawing_automation_tools(mcp_server, adapter, mock_config)

    result = await (await _tool(mcp_server, "arrange_dimensions"))({})

    assert result["status"] == "error"
    assert result["message"].startswith("Failed to arrange dimensions: 1 dimension")
    assert result["data"]["remaining_overlaps"] == overlaps


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_missing_adapter_method_is_reported(
    mcp_server, mock_config, tool
) -> None:
    await register_drawing_automation_tools(mcp_server, object(), mock_config)

    result = await (await _tool(mcp_server, tool))({})

    assert result["error_type"] == "not_supported"
    assert f"does not support {tool}" in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", _TOOLS)
async def test_docstrings_follow_the_tool_standard(
    mcp_server, mock_adapter, mock_config, tool
) -> None:
    """Every tool documents Args, Returns and an Example, as the others do."""
    await register_drawing_automation_tools(mcp_server, mock_adapter, mock_config)
    doc = (await _tool(mcp_server, tool)).__doc__ or ""
    for section in ("Args:", "Returns:", "Example:"):
        assert section in doc, (tool, section)
