"""get_application_info passes through ConnectionPoolAdapter."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.connection_pool import ConnectionPoolAdapter


class _InfoStub:
    def __init__(self) -> None:
        self.calls = 0

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    async def get_application_info(self) -> AdapterResult[dict]:
        self.calls += 1
        return AdapterResult(
            status=AdapterResultStatus.SUCCESS, data={"language": "english"}
        )


def test_pool_defines_its_own_passthrough() -> None:
    assert "get_application_info" in vars(ConnectionPoolAdapter)


@pytest.mark.asyncio
async def test_info_is_forwarded() -> None:
    stub = _InfoStub()
    pool = ConnectionPoolAdapter(adapter_factory=lambda: stub, max_size=1)
    await pool.connect()
    try:
        result = await pool.get_application_info()
    finally:
        await pool.disconnect()

    assert result.is_success
    assert result.data == {"language": "english"}
    assert stub.calls == 1
