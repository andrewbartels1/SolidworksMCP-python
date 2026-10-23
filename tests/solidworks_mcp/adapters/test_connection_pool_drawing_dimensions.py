"""The drawing-dimension methods pass through ConnectionPoolAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter

from .drawing_dimensions_stub import (
    DrawingDimensionsStub,
    exercise_drawing_dimensions,
)


@pytest.mark.asyncio
async def test_every_drawing_dimension_method_is_forwarded() -> None:
    stub = DrawingDimensionsStub()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: stub, max_size=1)
    await pool.connect()
    try:
        await exercise_drawing_dimensions(pool)
    finally:
        await pool.disconnect()

    assert stub.calls == DrawingDimensionsStub.EXPECTED_CALLS
