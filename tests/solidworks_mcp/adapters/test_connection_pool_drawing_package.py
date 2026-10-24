"""The drawing-package methods pass through ConnectionPoolAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter

from .drawing_package_stub import DrawingPackageStub, exercise_drawing_package


@pytest.mark.asyncio
async def test_every_drawing_package_method_is_forwarded() -> None:
    stub = DrawingPackageStub()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: stub, max_size=1)
    await pool.connect()
    try:
        await exercise_drawing_package(pool)
    finally:
        await pool.disconnect()

    assert stub.calls == DrawingPackageStub.EXPECTED_CALLS
