"""get_model_geometry_summary passes through ConnectionPoolAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter


class _SummaryStub:
    def __init__(self) -> None:
        self.calls = 0

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    async def get_model_geometry_summary(self) -> AdapterResult[dict]:
        self.calls += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"document_type": "assembly"}
        )


def test_pool_defines_its_own_passthrough() -> None:
    assert "get_model_geometry_summary" in vars(ConnectionPoolAdapter)


@pytest.mark.asyncio
async def test_summary_is_forwarded() -> None:
    stub = _SummaryStub()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: stub, max_size=1)
    await pool.connect()
    try:
        result = await pool.get_model_geometry_summary()
    finally:
        await pool.disconnect()

    assert result.is_success
    assert result.data == {"document_type": "assembly"}
    assert stub.calls == 1
