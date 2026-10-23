"""The drawing-dimension methods pass through CircuitBreakerAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter

from .drawing_dimensions_stub import (
    DrawingDimensionsStub,
    exercise_drawing_dimensions,
)


@pytest.mark.asyncio
async def test_every_drawing_dimension_method_is_forwarded() -> None:
    stub = DrawingDimensionsStub()
    await exercise_drawing_dimensions(CircuitBreakerAdapter(adapter=stub))
    assert stub.calls == DrawingDimensionsStub.EXPECTED_CALLS
