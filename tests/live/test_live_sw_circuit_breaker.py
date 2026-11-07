"""The circuit breaker inside the server's routing, on real SolidWorks (#208).

A failed ``create_extrusion`` used to be counted many times (the router's
VBA fallback re-entered the routed method) and paused extrusion at once.
Here a real extrusion fails (no sketch to extrude), and the test checks it
counts once, that the next good extrusion goes through, and that
``reset_circuit_breaker`` re-opens a paused operation.

Run it with::

    powershell -ExecutionPolicy Bypass -File tests\\scripts\\live_demo.ps1 `
        -Test tests/live/test_live_sw_circuit_breaker.py

Collected only with ``SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=1`` on Windows (see
``tests/live/conftest.py``).
"""

from __future__ import annotations

from typing import Any

import pytest

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter, CircuitState
from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.tools.server_admin import register_server_admin_tools
from tests.live.evidence import evidence


@pytest.mark.asyncio
async def test_a_failed_extrusion_counts_once_and_reset_reopens(scratch: Any) -> None:
    """One real failure counts once; a good extrusion follows; reset re-opens."""
    breaker = CircuitBreakerAdapter(adapter=scratch.adapter, failure_threshold=5)
    server = SolidWorksMCPServer(
        SolidWorksMCPConfig(mock_solidworks=False, enable_intelligent_routing=True)
    )
    server.adapter = breaker
    server._configure_runtime_services()
    adapter = server.adapter
    bucket = breaker._get_bucket("create_extrusion")

    assert (await adapter.create_part()).is_success
    failed = await adapter.create_extrusion(ExtrusionParameters(depth=10))
    evidence(
        "an extrusion with no sketch fails, and counts once",
        {
            "error": failed.error,
            "failures": bucket.failure_count,
            "state": bucket.state.value,
        },
    )
    assert failed.is_error
    assert bucket.failure_count == 1 and bucket.state == CircuitState.CLOSED

    assert (await adapter.create_sketch("Top")).is_success
    assert (await adapter.add_rectangle(-20, -10, 20, 10)).is_success
    assert (await adapter.exit_sketch()).is_success
    made = await adapter.create_extrusion(ExtrusionParameters(depth=10))
    evidence(
        "the next extrusion goes through",
        {"success": made.is_success, "failures": bucket.failure_count},
    )
    assert made.is_success and bucket.failure_count == 0

    bucket.state = CircuitState.OPEN  # as after five real failures
    from fastmcp import FastMCP

    mcp = FastMCP("breaker-check")
    await register_server_admin_tools(mcp, breaker, {})
    reset = next(
        t.fn for t in await mcp.list_tools() if t.name == "reset_circuit_breaker"
    )
    result = await reset({"operation": "create_extrusion"})
    evidence("reset_circuit_breaker re-opens it", result)
    assert result["data"] == {"reset": ["create_extrusion"]}
    assert bucket.state == CircuitState.CLOSED
