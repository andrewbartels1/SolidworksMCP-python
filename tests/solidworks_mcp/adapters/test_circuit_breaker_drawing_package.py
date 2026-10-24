"""The drawing-package methods pass through CircuitBreakerAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter

from .drawing_package_stub import DrawingPackageStub, exercise_drawing_package


@pytest.mark.asyncio
async def test_every_drawing_package_method_is_forwarded() -> None:
    stub = DrawingPackageStub()
    await exercise_drawing_package(CircuitBreakerAdapter(adapter=stub))
    assert stub.calls == DrawingPackageStub.EXPECTED_CALLS
