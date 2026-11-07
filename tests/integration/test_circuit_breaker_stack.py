"""The circuit breaker inside the server's routing, as in production (#208).

In a measured agent session one failed ``create_extrusion`` opened the
breaker at once: the server's router fell back to the VBA adapter, whose
methods call the same (routed) adapter, so the failure re-entered the router
and was counted again and again. These tests drive the server's real
instrumentation around a real ``CircuitBreakerAdapter``.
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import (
    AdapterResult,
    AdapterResultStatus,
    ExtrusionParameters,
)
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter, CircuitState
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.server import SolidWorksMCPServer


class _Extruder(MockSolidWorksAdapter):
    """A mock whose extrusion raises (as the COM adapter does) until told not to."""

    def __init__(self) -> None:
        super().__init__({})
        self.fail = True
        self.calls = 0

    async def create_extrusion(self, params: Any) -> AdapterResult[Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("Failed to create extrusion feature")
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"name": "Boss-Extrude1"}
        )


#: What the create_extrusion tool passes the adapter.
_PARAMS = ExtrusionParameters(depth=10)


def _server(breaker: CircuitBreakerAdapter) -> SolidWorksMCPServer:
    cfg = SolidWorksMCPConfig(mock_solidworks=True, enable_intelligent_routing=True)
    server = SolidWorksMCPServer(cfg)
    server.adapter = breaker
    server._configure_runtime_services()
    return server


@pytest.mark.asyncio
async def test_one_failure_counts_once_and_does_not_open_the_breaker() -> None:
    fake = _Extruder()
    breaker = CircuitBreakerAdapter(
        adapter=fake, failure_threshold=5, recovery_timeout=60
    )
    server = _server(breaker)

    result = await server.adapter.create_extrusion(_PARAMS)

    bucket = breaker._get_bucket("create_extrusion")
    assert result.is_error
    assert fake.calls == 1
    assert bucket.failure_count == 1
    assert bucket.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_a_success_after_failures_leaves_the_next_call_allowed() -> None:
    fake = _Extruder()
    breaker = CircuitBreakerAdapter(
        adapter=fake, failure_threshold=5, recovery_timeout=60
    )
    server = _server(breaker)
    for _ in range(4):
        await server.adapter.create_extrusion(_PARAMS)

    fake.fail = False
    first = await server.adapter.create_extrusion(_PARAMS)
    second = await server.adapter.create_extrusion(_PARAMS)

    assert first.is_success and second.is_success
    assert breaker._get_bucket("create_extrusion").state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_an_open_breaker_recovers_after_its_timeout() -> None:
    fake = _Extruder()
    breaker = CircuitBreakerAdapter(
        adapter=fake, failure_threshold=2, recovery_timeout=60
    )
    server = _server(breaker)
    for _ in range(2):
        await server.adapter.create_extrusion(_PARAMS)
    bucket = breaker._get_bucket("create_extrusion")
    assert bucket.state == CircuitState.OPEN

    bucket.last_failure_time -= 61  # the timeout has passed
    fake.fail = False
    result = await server.adapter.create_extrusion(_PARAMS)

    assert result.is_success
    assert bucket.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_reset_reopens_a_paused_operation_at_once() -> None:
    fake = _Extruder()
    breaker = CircuitBreakerAdapter(
        adapter=fake, failure_threshold=1, recovery_timeout=60
    )
    server = _server(breaker)
    await server.adapter.create_extrusion(_PARAMS)
    refused = await server.adapter.create_extrusion(_PARAMS)
    assert "Circuit breaker is open" in str(refused.error)

    reset = await breaker.reset_circuit_breakers("create_extrusion")
    fake.fail = False
    result = await server.adapter.create_extrusion(_PARAMS)

    assert reset.data == {"reset": ["create_extrusion"]}
    assert result.is_success
