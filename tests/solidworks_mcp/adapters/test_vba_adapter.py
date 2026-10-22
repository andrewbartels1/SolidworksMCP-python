"""Tests for the VBA generator adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    SweepParameters,
)
from solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter
from solidworks_mcp.adapters.vba_macro_executor import MacroExecutionRequest


@pytest.mark.asyncio
async def test_connect_disconnect_and_is_connected_delegate() -> None:
    """Connect/disconnect/is_connected should delegate to backing adapter."""
    # Ensure basic delegation calls the backing adapter methods.
    backing = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        is_connected=lambda: True,
    )
    adapter = VbaGeneratorAdapter(backing)

    await adapter.connect()
    await adapter.disconnect()
    assert adapter.is_connected() is True


@pytest.mark.asyncio
async def test_health_check_adds_vba_route() -> None:
    """health_check should append vba route to metrics."""
    # Validate the route marker is injected into metrics.
    health = SimpleNamespace(metrics={"foo": "bar"})
    backing = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        is_connected=lambda: True,
        health_check=AsyncMock(return_value=health),
    )
    adapter = VbaGeneratorAdapter(backing)
    result = await adapter.health_check()
    assert result.metrics["route"] == "vba"


def test_generate_sweep_and_loft_vba() -> None:
    """VBA helpers should render snippets for sweep/loft."""
    # Ensure the helper functions embed key values.
    backing = SimpleNamespace(
        connect=AsyncMock(), disconnect=AsyncMock(), is_connected=lambda: True
    )
    adapter = VbaGeneratorAdapter(backing)
    sweep = adapter._generate_sweep_vba(SweepParameters(path="Path1"))
    assert "Path1" in sweep

    loft = adapter._generate_loft_vba(SimpleNamespace(profiles=[1, 2]))
    assert "Profiles: 2" in loft


@pytest.mark.asyncio
async def test_execute_macro_delegates_executor() -> None:
    """execute_macro should call the macro executor with a request."""
    # Validate MacroExecutionRequest is passed through.
    executor = SimpleNamespace(
        execute_macro=AsyncMock(
            return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="ok")
        )
    )
    backing = SimpleNamespace(
        connect=AsyncMock(), disconnect=AsyncMock(), is_connected=lambda: True
    )
    adapter = VbaGeneratorAdapter(backing, macro_executor=executor)

    result = await adapter.execute_macro("code", macro_name="Macro", subroutine="Main")
    assert result.is_success
    executor.execute_macro.assert_awaited()
    request = executor.execute_macro.await_args.kwargs["request"]
    assert isinstance(request, MacroExecutionRequest)


def test_get_macro_execution_history_returns_dict() -> None:
    """Macro history should serialize to plain dicts."""
    # Provide a fake execution history and ensure dict output.
    history = {"Macro": SimpleNamespace(status="ok")}
    executor = SimpleNamespace(get_execution_history=lambda _name=None: history)
    backing = SimpleNamespace(
        connect=AsyncMock(), disconnect=AsyncMock(), is_connected=lambda: True
    )
    adapter = VbaGeneratorAdapter(backing, macro_executor=executor)
    result = adapter.get_macro_execution_history()
    assert result["Macro"]["status"] == "ok"


@pytest.mark.asyncio
async def test_vba_adapter_create_sweep_calls_backing(monkeypatch):
    """create_sweep should call _run_with_vba_metadata. Covers vba_adapter.py line 153."""
    from solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter

    mock_backing = AsyncMock()
    mock_backing.create_sweep = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    adapter = VbaGeneratorAdapter.__new__(VbaGeneratorAdapter)
    adapter._backing_adapter = mock_backing
    adapter._generate_sweep_vba = lambda params: "# sweep vba"

    sweep_params = SimpleNamespace(
        profile_sketch="sketch1",
        path_sketch="path1",
        twist_angle=0.0,
        start_tangent_type="None",
        end_tangent_type="None",
    )

    result = await adapter.create_sweep(sweep_params)
    assert result.is_success
    mock_backing.create_sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_vba_adapter_create_loft_calls_backing(monkeypatch):
    """create_loft should call _run_with_vba_metadata. Covers vba_adapter.py line 172."""
    from solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter

    mock_backing = AsyncMock()
    mock_backing.create_loft = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    adapter = VbaGeneratorAdapter.__new__(VbaGeneratorAdapter)
    adapter._backing_adapter = mock_backing
    adapter._generate_loft_vba = lambda params: "# loft vba"

    loft_params = SimpleNamespace(
        profile_sketches=["s1", "s2"],
        guide_curves=[],
        start_tangent_type="None",
        end_tangent_type="None",
    )

    result = await adapter.create_loft(loft_params)
    assert result.is_success
    mock_backing.create_loft.assert_awaited_once()
