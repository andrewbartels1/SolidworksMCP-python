"""``reset_circuit_breaker`` (spec: adapters/circuit-breaker, the reset requirement)."""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter, CircuitState
from solidworks_mcp.tools.server_admin import (
    ResetCircuitBreakerInput,
    register_server_admin_tools,
)


async def _reset_tool(mcp_server: Any, adapter: Any) -> Any:
    await register_server_admin_tools(mcp_server, adapter, {})
    return next(
        t.fn for t in await mcp_server.list_tools() if t.name == "reset_circuit_breaker"
    )


def _breaker_with_open(*operations: str) -> CircuitBreakerAdapter:
    breaker = CircuitBreakerAdapter(failure_threshold=1)
    for name in operations:
        breaker._get_bucket(name).state = CircuitState.OPEN
    return breaker


@pytest.mark.asyncio
async def test_registers_one_tool(mcp_server, mock_adapter) -> None:
    assert await register_server_admin_tools(mcp_server, mock_adapter, {}) == 1


@pytest.mark.asyncio
async def test_without_a_breaker_nothing_was_paused(mcp_server, mock_adapter) -> None:
    tool = await _reset_tool(mcp_server, mock_adapter)

    result = await tool()

    assert result["status"] == "success"
    assert result["data"] == {"reset": []}
    assert result["message"] == "No operation was paused"


@pytest.mark.asyncio
async def test_resets_every_open_operation(mcp_server) -> None:
    breaker = _breaker_with_open("create_extrusion", "add_mate")
    tool = await _reset_tool(mcp_server, breaker)

    result = await tool()

    assert result["data"] == {"reset": ["add_mate", "create_extrusion"]}
    assert result["message"] == "Reset add_mate, create_extrusion"
    assert breaker._get_bucket("add_mate").state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_resets_only_the_named_operation(mcp_server) -> None:
    breaker = _breaker_with_open("create_extrusion", "add_mate")
    tool = await _reset_tool(mcp_server, breaker)

    result = await tool(ResetCircuitBreakerInput(operation="create_extrusion"))

    assert result["data"] == {"reset": ["create_extrusion"]}
    assert breaker._get_bucket("add_mate").state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_a_failed_reset_is_an_error(mcp_server) -> None:
    class _Broken:
        async def reset_circuit_breakers(
            self, operation: str | None
        ) -> AdapterResult[Any]:
            return AdapterResult(status=AdapterResultStatus.ERROR, error="pool closed")

    tool = await _reset_tool(mcp_server, _Broken())

    result = await tool()

    assert result["status"] == "error"
    assert "Failed to reset the circuit breaker" in result["message"]
