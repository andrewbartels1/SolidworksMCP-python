"""The engineering-data methods pass through ConnectionPoolAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter

from .engineering_data_stub import EngineeringDataStub, exercise_engineering_data


@pytest.mark.asyncio
async def test_every_engineering_data_method_is_forwarded() -> None:
    stub = EngineeringDataStub()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: stub, max_size=1)
    await pool.connect()
    try:
        await exercise_engineering_data(pool)
    finally:
        await pool.disconnect()

    assert stub.calls == EngineeringDataStub.EXPECTED_CALLS
