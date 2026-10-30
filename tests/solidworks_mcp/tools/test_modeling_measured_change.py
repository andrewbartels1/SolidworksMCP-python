"""Tests for the measured_change block on extrude, revolve and cut-extrude."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.tools.modeling import register_modeling_tools


def _ok(data: Any) -> AdapterResult[Any]:
    return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)


def _err(message: str) -> AdapterResult[Any]:
    return AdapterResult(status=AdapterResultStatus.ERROR, error=message)


def _summary(volume: float | None, size: list[float] | None, bodies: int | None):
    box = None if size is None else {"min": [0, 0, 0], "max": size, "size": size}
    return _ok(
        {
            "document_type": "part",
            "volume_mm3": volume,
            "bounding_box_mm": box,
            "bounding_box_method": "extreme_points",
            "solid_body_count": bodies,
        }
    )


_EMPTY = _summary(0.0, None, 0)
_BLOCK = _summary(4000.0, [20.0, 20.0, 10.0], 1)

_CALLS = {
    "create_extrusion": {"sketch_name": "Sketch1", "depth": 10.0},
    "create_revolve": {"sketch_name": "Sketch1", "axis_entity": "Line1", "angle": 360},
    "create_cut_extrude": {"sketch_name": "Sketch2", "depth": 5.0},
}


async def _tool(mcp_server, adapter, name: str):
    await register_modeling_tools(mcp_server, adapter, {})
    tools = {t.name: t.fn for t in await mcp_server.list_tools()}
    return tools[name]


def _feature_ok(adapter, name: str) -> None:
    setattr(adapter, name, AsyncMock(return_value=_ok({"feature_name": "Feature1"})))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(_CALLS))
async def test_reports_volume_and_size_change(mcp_server, mock_adapter, name):
    _feature_ok(mock_adapter, name)
    mock_adapter.get_model_geometry_summary = AsyncMock(side_effect=[_EMPTY, _BLOCK])

    result = await (await _tool(mcp_server, mock_adapter, name))(_CALLS[name])

    assert result["status"] == "success"
    assert result["measured_change"] == {
        "volume_before_mm3": 0.0,
        "volume_after_mm3": 4000.0,
        "volume_delta_mm3": 4000.0,
        "bounding_box_before_mm": None,
        "bounding_box_after_mm": [20.0, 20.0, 10.0],
        "solid_body_count_before": 0,
        "solid_body_count_after": 1,
    }
    assert "warning" not in result


@pytest.mark.asyncio
async def test_cut_that_removes_nothing_warns(mcp_server, mock_adapter):
    _feature_ok(mock_adapter, "create_cut_extrude")
    mock_adapter.get_model_geometry_summary = AsyncMock(side_effect=[_BLOCK, _BLOCK])

    result = await (await _tool(mcp_server, mock_adapter, "create_cut_extrude"))(
        _CALLS["create_cut_extrude"]
    )

    assert result["status"] == "success"
    assert result["measured_change"]["volume_delta_mm3"] == 0
    assert "changed no volume" in result["warning"]


@pytest.mark.asyncio
async def test_adapter_without_the_read_leaves_reply_unchanged(mcp_server):
    class _BareAdapter:
        create_extrusion = AsyncMock(return_value=_ok({"feature_name": "Boss1"}))

    result = await (await _tool(mcp_server, _BareAdapter(), "create_extrusion"))(
        _CALLS["create_extrusion"]
    )

    assert set(result) == {"status", "message", "extrusion", "execution_time"}


@pytest.mark.asyncio
async def test_failed_before_read_omits_the_block(mcp_server, mock_adapter):
    _feature_ok(mock_adapter, "create_extrusion")
    mock_adapter.get_model_geometry_summary = AsyncMock(
        return_value=_err("No active model")
    )

    result = await (await _tool(mcp_server, mock_adapter, "create_extrusion"))(
        _CALLS["create_extrusion"]
    )

    assert result["status"] == "success"
    assert "measured_change" not in result


@pytest.mark.asyncio
async def test_failed_after_read_does_not_fail_the_feature(mcp_server, mock_adapter):
    _feature_ok(mock_adapter, "create_revolve")
    mock_adapter.get_model_geometry_summary = AsyncMock(
        side_effect=[_EMPTY, _err("COM call timed out")]
    )

    result = await (await _tool(mcp_server, mock_adapter, "create_revolve"))(
        _CALLS["create_revolve"]
    )

    assert result["status"] == "success"
    change = result["measured_change"]
    assert change["volume_after_mm3"] is None
    assert change["volume_delta_mm3"] is None
    assert change["solid_body_count_after"] is None
    assert change["note"].endswith("COM call timed out")
    assert "warning" not in result


@pytest.mark.asyncio
async def test_mock_adapter_reports_nulls_with_a_note(mcp_server, mock_adapter):
    await mock_adapter.open_model("C:\\mock\\Bracket.sldprt")
    _feature_ok(mock_adapter, "create_extrusion")

    result = await (await _tool(mcp_server, mock_adapter, "create_extrusion"))(
        _CALLS["create_extrusion"]
    )

    change = result["measured_change"]
    assert change["volume_delta_mm3"] is None
    assert change["note"] == "Volume is not determinable with the active adapter"


@pytest.mark.asyncio
async def test_failed_feature_skips_the_after_read(mcp_server, mock_adapter):
    mock_adapter.create_extrusion = AsyncMock(return_value=_err("Sketch not found"))
    mock_adapter.get_model_geometry_summary = AsyncMock(return_value=_EMPTY)

    result = await (await _tool(mcp_server, mock_adapter, "create_extrusion"))(
        _CALLS["create_extrusion"]
    )

    assert result["status"] == "error"
    assert mock_adapter.get_model_geometry_summary.await_count == 1
